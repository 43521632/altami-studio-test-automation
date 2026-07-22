"""Открытие отдельной консоли под тестовый сеанс одной ВМ.

Каждая ВМ получает своё окно терминала: прогоны разных ВМ идут параллельно и
не мешают друг другу, а вывод и меню каждой ВМ остаются в своём окне. Вторая
консоль на ту же ВМ не откроется — мешает замок из src/vm_lock.py.

Если графического терминала нет (ssh, headless), сеанс запускается прямо в
текущем окне.
"""

import logging
import os
import shlex
import shutil
import subprocess
import sys
from typing import Callable, List, Optional

from config.settings import BASE_DIR, get_all_vm_ids
from src.vm_lock import is_busy, owner_pid

logger = logging.getLogger(__name__)


class ConsoleLauncherError(Exception):
    """Raised when a console for the VM cannot be opened."""


# Поддерживаемые эмуляторы терминала: первый найденный в PATH и выигрывает.
# Каждый билдер получает заголовок окна и строку команды для bash -lc.
_TERMINALS: List[tuple] = [
    ("gnome-terminal", lambda title, cmd: [
        "gnome-terminal", f"--title={title}", "--", "bash", "-lc", cmd]),
    ("konsole", lambda title, cmd: [
        "konsole", "-p", f"tabtitle={title}", "-e", "bash", "-lc", cmd]),
    ("xfce4-terminal", lambda title, cmd: [
        "xfce4-terminal", f"--title={title}",
        f"--command=bash -lc {shlex.quote(cmd)}"]),
    ("mate-terminal", lambda title, cmd: [
        "mate-terminal", f"--title={title}", "--", "bash", "-lc", cmd]),
    ("tilix", lambda title, cmd: [
        "tilix", "-t", title, "-e", "bash", "-lc", cmd]),
    ("kitty", lambda title, cmd: [
        "kitty", "-T", title, "bash", "-lc", cmd]),
    ("alacritty", lambda title, cmd: [
        "alacritty", "-t", title, "-e", "bash", "-lc", cmd]),
    ("xterm", lambda title, cmd: [
        "xterm", "-T", title, "-e", "bash", "-lc", cmd]),
]


def find_terminal() -> Optional[tuple]:
    """Return (name, builder) for the first available terminal emulator."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for name, builder in _TERMINALS:
        if shutil.which(name):
            return name, builder
    return None


def session_command(vm_id: str, vm_name_override: Optional[str] = None) -> str:
    """Shell command that runs the test session for one VM."""
    parts = [
        sys.executable,
        str(BASE_DIR / "run_tests.py"),
        "--session", vm_id,
    ]
    if vm_name_override:
        parts += ["--vm-name", vm_name_override]
    return f"cd {shlex.quote(str(BASE_DIR))} && exec " + " ".join(
        shlex.quote(p) for p in parts
    )


def launch_console(
    vm_id: str,
    vm_name_override: Optional[str] = None,
    force_inline: bool = False,
) -> str:
    """Open a console running the test session for `vm_id`.

    Returns a short description of what was started.

    Raises:
        ConsoleLauncherError: the VM is already under test in another console.
    """
    known = get_all_vm_ids()
    if vm_id not in known:
        raise ConsoleLauncherError(
            f"ВМ '{vm_id}' не найдена в config/vms_config.yaml. "
            f"Доступны: {', '.join(known) or '(пусто)'}"
        )

    if is_busy(vm_id):
        pid = owner_pid(vm_id)
        raise ConsoleLauncherError(
            f"Для ВМ '{vm_id}' уже открыта тестовая консоль"
            + (f" (pid {pid})" if pid else "")
            + ". Одна ВМ — одна консоль: закройте её или дождитесь завершения."
        )

    command = session_command(vm_id, vm_name_override)
    terminal = None if force_inline else find_terminal()

    if terminal is None:
        # Ни X/Wayland, ни эмулятора — гоняем в этом же окне
        logger.info("Терминал не найден, сеанс '%s' идёт в текущем окне", vm_id)
        from src.session_console import run_console_session

        run_console_session(vm_id, vm_name_override)
        return f"сеанс '{vm_id}' завершён в текущем окне"

    name, builder = terminal
    argv = builder(f"Тесты: {vm_id}", command)
    logger.info("[%s] Открываю консоль: %s", vm_id, " ".join(argv))
    try:
        # start_new_session: окно живёт независимо от меню, из которого открыто
        subprocess.Popen(
            argv, cwd=str(BASE_DIR), start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        raise ConsoleLauncherError(f"Не удалось открыть {name}: {e}") from e
    return f"консоль '{name}' открыта для ВМ '{vm_id}'"
