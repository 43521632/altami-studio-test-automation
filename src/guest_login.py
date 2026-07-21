"""Automatic sign-in to the guest OS, performed once per pytest session.

This is setup, not a test: the VM boots to a greeter, and every UI test that
follows needs a desktop. The login is driven through the same QMP input
injection as the tests themselves — nothing is installed in the guest.

The sequence is described in `vms_config.yaml`, not in code, because it is
pure UI choreography and differs per OS — Astra alone needs four clicks after
the password (integrity level, Войти, and a warning about the home directory).
Coordinates are guest pixels; see docs/writing-tests.md on how to read them
off a screenshot.

Passwords are the exception: they come from `.env` (gitignored) as
`<VM_ID>_LOGIN_PASSWORD`, never from `vms_config.yaml`, which is committed.

Two things this module is careful about:

* **Typing speed.** A greeter on a freshly booted VM drops keystrokes: fly-dm
  took only «t» out of «test» at the 0.02s default. Hence `type_delay`.
* **Not typing into a live desktop.** The VM keeps running between runs, so
  the guest may already be logged in. After the first successful login the
  greeter is stored as `baseline/<vm_id>/login_screen.png`; when the screen on
  arrival does not match it, the login is skipped instead of clicking blindly.

Wired in by the autouse `guest_login` fixture in tests/conftest.py; call it
directly only when driving a VM outside pytest.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import BASELINE_DIR
from src.qmp_client import probe_path

logger = logging.getLogger(__name__)

#: Имя эталона экрана входа в baseline/<vm_id>/
LOGIN_SCREEN_BASELINE = "login_screen"

#: Подстановки, доступные в шагах `type:`
USERNAME_PLACEHOLDER = "$username"
PASSWORD_PLACEHOLDER = "$password"

# Настройки по умолчанию, если в vms_config.yaml они не заданы
DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "username": "",
    "password": "",
    #: Шаги входа, см. docstring модуля и vms_config.yaml
    "steps": [],
    # Сколько ждать от старта ВМ до экрана входа. Astra: GRUB (2с) + выбор
    # загрузчика (3с) + около 30с на загрузку.
    "boot_delay": 40.0,
    # Пауза между символами. При 0.02с гритер теряет символы.
    "type_delay": 0.15,
    # Сколько ещё ждать экрана входа, если он не совпал с эталоном сразу
    "greeter_timeout": 120.0,
    # Сколько ждать, пока после входа дорисуется рабочий стол. Windows
    # показывает «Добро пожаловать» со спиннером ещё долго после пароля.
    "settle_timeout": 90.0,
    # SSIM выше порога = экран совпал с эталоном экрана входа. Ниже, чем у
    # тестов: на экране входа тикают часы.
    "match_threshold": 0.90,
    # Какая доля пикселей должна смениться, чтобы вход считался выполненным.
    # SSIM здесь бесполезен: у гритера и рабочего стола Astra общие обои, и
    # неудачный вход даёт тот же SSIM (0.933), что и удачный.
    "min_change_ratio": 0.05,
}


class GuestLoginError(RuntimeError):
    """Raised when the guest OS could not be signed into."""


def login_settings(vm_id: str, vm_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the VM's `login:` block with defaults and environment overrides.

    Passwords come from the environment — `<VM_ID>_LOGIN_PASSWORD`, kept in
    `.env`, which is gitignored — because `vms_config.yaml` is committed.
    `<VM_ID>_LOGIN_USER` overrides the username the same way.
    """
    block = vm_config.get("login") or {}
    settings = {**DEFAULTS, **block}

    prefix = vm_id.upper()
    if env_user := os.getenv(f"{prefix}_LOGIN_USER"):
        settings["username"] = env_user
    if env_password := os.getenv(f"{prefix}_LOGIN_PASSWORD"):
        settings["password"] = env_password
    elif block.get("password"):
        # Не роняем прогон, но молчать нельзя: файл под git, и пароль уедет
        # в историю при первом же коммите, откуда его уже не вычистить.
        logger.warning(
            "%s: пароль задан в config/vms_config.yaml, а этот файл под git. "
            "Перенесите его в .env как %s_LOGIN_PASSWORD.", vm_id, prefix,
        )

    return settings


def login_screen_baseline(vm_id: str) -> Path:
    """Path of the stored login-screen reference for a VM."""
    return Path(BASELINE_DIR) / vm_id / f"{LOGIN_SCREEN_BASELINE}.png"


def _similarity(first: Path, second: Path) -> float:
    """SSIM between two screendumps, 1.0 = identical.

    A dedicated comparator with threshold 0 and no diff writing: we only want
    the number, and `screenshots/diff/` should not fill up with login frames.
    """
    from src.screenshot_compare import ScreenshotComparator

    comparator = ScreenshotComparator(threshold=0.0, save_diff=False)
    return comparator.compare_images(first, second, label="login").score


def _change_ratio(first: Path, second: Path, tolerance: int = 12) -> float:
    """Fraction of pixels that differ between two screendumps.

    SSIM answers "does this look like the same screen" and is the right metric
    for baselines. It is the wrong one for "did we get from the greeter to the
    desktop": those two share a wallpaper in Astra and score 0.933 whether the
    login succeeded or not. Counting pixels separates them cleanly.
    """
    import numpy as np
    from PIL import Image

    with Image.open(first) as fi, Image.open(second) as si:
        a = np.asarray(fi.convert("RGB"), dtype=np.int16)
        b = np.asarray(si.convert("RGB"), dtype=np.int16)

    if a.shape != b.shape:
        return 1.0  # сменился видеорежим — экран точно другой
    return float((np.abs(a - b).max(axis=-1) > tolerance).mean())


async def _wait_for_login_screen(session, settings: Dict[str, Any], arrival: Path) -> bool:
    """Wait out the boot, then leave the arrival frame in `arrival`.

    Returns:
        True if the login sequence should run. False means the screen does not
        match the stored login screen — the guest is already signed in.
    """
    logger.info("%s: ждём загрузки ОС, %.0fс", session.vm_id, settings["boot_delay"])
    await asyncio.sleep(settings["boot_delay"])
    await session.qmp.screendump(arrival)

    baseline = login_screen_baseline(session.vm_id)
    if not baseline.exists():
        # Первый прогон: сверяться не с чем. Эталон появится после того, как
        # вход подтверждённо удастся — тогда следующие прогоны будут точными.
        logger.info(
            "%s: эталона экрана входа нет (%s) — считаем, что на экране вход",
            session.vm_id, baseline,
        )
        return True

    # Экран входа мог ещё не появиться: загрузка бывает медленнее boot_delay.
    loop = asyncio.get_event_loop()
    deadline = loop.time() + settings["greeter_timeout"]
    while True:
        score = _similarity(arrival, baseline)
        if score > settings["match_threshold"]:
            logger.info("%s: узнан экран входа (SSIM=%.6f)", session.vm_id, score)
            return True
        if loop.time() >= deadline:
            logger.info(
                "%s: экран не похож на экран входа (SSIM=%.6f) — "
                "вход уже выполнен, пропускаем", session.vm_id, score,
            )
            return False
        await asyncio.sleep(3.0)
        await session.qmp.screendump(arrival)


def _resolve_text(value: str, settings: Dict[str, Any]) -> str:
    """Substitute $username / $password in a step's text."""
    return (
        str(value)
        .replace(USERNAME_PLACEHOLDER, settings["username"])
        .replace(PASSWORD_PLACEHOLDER, settings["password"])
    )


async def _run_step(session, step: Dict[str, Any], settings: Dict[str, Any],
                    index: int) -> None:
    """Execute one step of the login sequence.

    A step is a mapping with exactly one action and an optional `wait`:
        {click: [x, y], wait: 0.5}   — клик по координатам гостя
        {type: "$password"}          — набор текста
        {key: [ctrl, a]}             — нажатие клавиши или комбинации
    """
    if (target := step.get("click")) is not None:
        x, y = target
        await session.qmp.mouse_click(int(x), int(y))
        action = f"клик ({x}, {y})"
    elif (text := step.get("type")) is not None:
        resolved = _resolve_text(text, settings)
        await session.qmp.type_text(resolved, delay_s=settings["type_delay"])
        # Пароль в лог не пишем — только длину
        action = (f"набор пароля ({len(resolved)} символов)"
                  if PASSWORD_PLACEHOLDER in str(text)
                  else f"набор {resolved!r}")
    elif (keys := step.get("key")) is not None:
        keys = [keys] if isinstance(keys, str) else list(keys)
        await session.qmp.send_keys(keys)
        action = f"клавиши {'+'.join(keys)}"
    else:
        raise GuestLoginError(
            f"{session.vm_id}: шаг {index} не содержит действия "
            f"(нужен один из ключей click / type / key): {step}"
        )

    logger.debug("%s: шаг %d — %s", session.vm_id, index, action)
    if (pause := step.get("wait")):
        await asyncio.sleep(float(pause))


async def ensure_logged_in(session, save_screenshots: bool = True) -> bool:
    """Sign into the guest OS unless it is already signed in.

    Args:
        session: a live :class:`~src.vm_manager.VMSession`.
        save_screenshots: keep before/after frames for debugging.

    Returns:
        True if a login was performed, False if it was not needed.

    Raises:
        GuestLoginError: the login sequence is missing or misconfigured, or
            the screen did not change after it ran.
    """
    settings = login_settings(session.vm_id, session.config)

    if not settings["enabled"]:
        logger.info("%s: автологин выключен в конфиге — пропускаем", session.vm_id)
        return False

    steps: List[Dict[str, Any]] = settings["steps"]
    if not steps:
        raise GuestLoginError(
            f"{session.vm_id}: не задана последовательность входа "
            f"vms.{session.vm_id}.login.steps в config/vms_config.yaml."
        )
    if not settings["password"]:
        raise GuestLoginError(
            f"{session.vm_id}: не задан пароль для входа. Заполните "
            f"{session.vm_id.upper()}_LOGIN_PASSWORD в файле .env "
            f"(шаблон — .env.example). В config/vms_config.yaml паролю не "
            f"место: этот файл под git."
        )

    with probe_path(".png") as arrival:
        if not await _wait_for_login_screen(session, settings, arrival):
            return False

        if save_screenshots:
            await session.screenshot("login_before")

        # Координаты шагов пересчитываются в абсолютный диапазон QMP по
        # разрешению экрана, а в сессии лежит режим из конфига — режим
        # РАБОЧЕГО СТОЛА. Экран входа нередко в другом: гритер Astra идёт в
        # 1280x800, а рабочий стол — в 1920x1200. По конфигу клики уходили бы
        # мимо, поэтому спрашиваем реальный режим у самого гостя.
        await session.qmp.detect_resolution()

        for index, step in enumerate(steps, start=1):
            await _run_step(session, step, settings, index)

        # Тесты стартуют сразу после фикстуры, поэтому возвращаем управление
        # только по готовому рабочему столу, а не по «Добро пожаловать».
        if not await session.wait_until_screen_stable(timeout=settings["settle_timeout"]):
            logger.warning(
                "%s: рабочий стол не стабилизировался за %.0fс после входа — "
                "продолжаем, но проверьте скриншоты",
                session.vm_id, settings["settle_timeout"],
            )

        with probe_path(".png") as final:
            await session.qmp.screendump(final)
            ratio = _change_ratio(arrival, final)
            if ratio < settings["min_change_ratio"]:
                raise GuestLoginError(
                    f"{session.vm_id}: вход не выполнен — сменилось лишь "
                    f"{ratio:.1%} экрана (нужно ≥ {settings['min_change_ratio']:.0%}).\n"
                    f"  Обычные причины: сдвинулись координаты в login.steps, "
                    f"ОС не успела догрузиться до экрана входа (login.boot_delay) "
                    f"или пароль не принят.\n"
                    f"  Что на экране: {await session.screenshot('login_failed')}"
                )
            logger.info("%s: вход выполнен — сменилось %.1f%% экрана",
                        session.vm_id, ratio * 100)

        # После входа гость может переключить видеорежим — обновляем кэш,
        # иначе клики в тестах считались бы по разрешению экрана входа.
        await session.qmp.detect_resolution()

        if save_screenshots:
            await session.screenshot("login_after")

        # Вход удался — значит, экран, с которого мы начали, и есть экран
        # входа. Сохраняем его эталоном: на следующем прогоне уже видно,
        # нужен вход или гость и так в системе.
        _save_login_baseline(session.vm_id, arrival)

    return True


def _save_login_baseline(vm_id: str, frame: Path) -> None:
    """Store `frame` as the login-screen reference, unless one already exists."""
    baseline = login_screen_baseline(vm_id)
    if baseline.exists():
        return
    try:
        from PIL import Image

        baseline.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(frame) as img:
            img.convert("RGB").save(baseline)
        logger.info("%s: сохранён эталон экрана входа: %s", vm_id, baseline)
    except Exception as e:  # noqa: BLE001 — эталон лишь ускоряет следующий прогон
        logger.warning("%s: не удалось сохранить эталон экрана входа: %s", vm_id, e)
