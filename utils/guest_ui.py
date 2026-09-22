"""UI-хелперы для действий внутри гостя, не относящихся к конкретному тесту.

Сейчас здесь одно действие — скачивание установщика браузером гостя. Это
вынужденная мера: в доменах нет ни QEMU guest agent, ни virtiofs/9p, ни SSH,
поэтому выполнить команду внутри гостя программно нельзя (см. п. 12.7
INSTRUCTION_FOR_AI.md). Как только guest agent появится, скачивание переедет
на него, а этот модуль можно будет удалить.

Модуль намеренно НЕ наследует BaseVMTest: им пользуются и тесты, и фикстуры,
а BaseVMTest привязан к pytest-фикстурам и пропускает тесты «не для этой ВМ».
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from src.vm_manager import VMSession

logger = logging.getLogger(__name__)

# Куда гость складывает скачанный файл. Путь относительный: браузер сам
# подставит домашний каталог пользователя (Windows — C:\Users\Test1).
GUEST_DOWNLOAD_DIR = "Downloads"

# Сколько ждать закрытия диалога аутентификации JFrog после ввода кредов
_AUTH_SETTLE_S = 2.0


def installer_filename(url: str) -> str:
    """Имя файла установщика из URL артефакта."""
    return Path(url.split("?", 1)[0]).name


def jfrog_credentials() -> Optional[tuple]:
    """Логин/пароль JFrog из окружения или None, если они не заданы."""
    user = os.environ.get("CACHE_USER")
    password = os.environ.get("CACHE_PASSWORD")
    if user and password:
        return user, password
    return None


async def open_browser(session: VMSession, url: str) -> None:
    """Открыть URL в браузере гостя.

    Способ запуска отдан в `vms_config.yaml` (`download.browser`) — он разный
    для Windows и Astra, а зашивать его в код значило бы плодить ветки по
    os_type на каждый новый способ.

    Поддерживаются:
        run-dialog — Win+R, затем `cmd /c start <url>` (Windows);
        terminal   — Ctrl+Alt+T, затем `xdg-open <url>` (Astra).
    """
    method = (session.config.get("download") or {}).get("browser", "")
    qmp = session.qmp

    if method == "run-dialog":
        # Win+R не умеет открывать URL в браузере по умолчанию, а `start`
        # делает это через оболочку. META в QKeyCode зовётся `meta_l`.
        await qmp.send_keys(["meta_l", "r"])
        await asyncio.sleep(1.0)
        await qmp.type_text(f"cmd /c start {url}", delay_s=0.01)
        await qmp.send_keys(["ret"])
        await asyncio.sleep(2.0)
        return

    if method == "terminal":
        await qmp.send_keys(["ctrl", "alt", "t"])
        await asyncio.sleep(3.0)
        await qmp.type_text(f"xdg-open {url}", delay_s=0.02)
        await qmp.send_keys(["ret"])
        await asyncio.sleep(3.0)
        return

    raise RuntimeError(
        f"Не задан способ запуска браузера для ВМ '{session.vm_id}': "
        f"добавьте download.browser в config/vms_config.yaml"
    )


async def focus_address_bar(session: VMSession) -> None:
    """Перевести фокус в адресную строку браузера."""
    await session.qmp.send_keys(["ctrl", "l"])


async def goto_url(session: VMSession, url: str) -> None:
    """Открыть URL в уже запущенном браузере гостя."""
    await focus_address_bar(session)
    await asyncio.sleep(0.3)
    await session.qmp.type_text(url, delay_s=0.005)
    await session.qmp.send_keys(["ret"])


async def enter_jfrog_credentials(session: VMSession) -> bool:
    """Ввести логин/пароль JFrog в диалоге аутентификации браузера.

    Возвращает False, если креды не заданы. Диалог аутентификации у разных
    браузеров выглядит по-разному, поэтому это самый хрупкий шаг: если он не
    сработает, тест упадёт с внятным сообщением, а не молча скачает HTML
    страницы вместо установщика.
    """
    creds = jfrog_credentials()
    if not creds:
        return False
    user, password = creds

    qmp = session.qmp
    # Диалог аутентификации получает фокус сам. Tab перемещает между полями
    # «Логин» и «Пароль», Enter подтверждает.
    await asyncio.sleep(_AUTH_SETTLE_S)
    await qmp.type_text(user, delay_s=0.02)
    await qmp.send_keys(["tab"])
    await asyncio.sleep(0.3)
    await qmp.type_text(password, delay_s=0.02)
    await qmp.send_keys(["ret"])
    await asyncio.sleep(2.0)
    logger.info("%s: учётные данные JFrog введены", session.vm_id)
    return True
