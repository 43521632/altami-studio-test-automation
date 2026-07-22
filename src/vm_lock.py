"""Блокировка ВМ: одна тестовая консоль на одну ВМ.

Гостя нельзя вести двумя прогонами сразу — клики и скриншоты второй консоли
перемешаются с первой. Замок держит процесс сеанса (src/session_console.py),
а лаунчер консолей проверяет его перед открытием нового окна.

Замок снимается ядром при завершении процесса, поэтому упавшая консоль не
оставляет ВМ заблокированной навсегда.
"""

import fcntl
import logging
import os
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR

logger = logging.getLogger(__name__)

LOCK_DIR = BASE_DIR / ".locks"


class VMLockBusy(Exception):
    """Raised when the VM is already driven by another console."""


def lock_path(vm_id: str) -> Path:
    """Path of the lock file for one VM."""
    return LOCK_DIR / f"{vm_id}.lock"


class VMLock:
    """Exclusive per-VM lock held for the lifetime of a test console."""

    def __init__(self, vm_id: str) -> None:
        self.vm_id = vm_id
        self.path = lock_path(vm_id)
        self._file = None

    def acquire(self) -> "VMLock":
        """Take the lock.

        Raises:
            VMLockBusy: another console is already testing this VM.
        """
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            owner = self._read_owner()
            self._file.close()
            self._file = None
            raise VMLockBusy(
                f"ВМ '{self.vm_id}' уже тестируется в другой консоли"
                + (f" (pid {owner})" if owner else "")
            )
        self._file.seek(0)
        self._file.truncate()
        self._file.write(str(os.getpid()))
        self._file.flush()
        return self

    def release(self) -> None:
        """Release the lock, if held."""
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._file.close()
        self._file = None

    def _read_owner(self) -> Optional[str]:
        """Pid recorded in the lock file, if it is readable."""
        try:
            return self.path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def __enter__(self) -> "VMLock":
        return self.acquire()

    def __exit__(self, *exc_info) -> None:
        self.release()


def is_busy(vm_id: str) -> bool:
    """True when some other process holds the lock for this VM."""
    path = lock_path(vm_id)
    if not path.exists():
        return False
    try:
        with open(path, "a+", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as e:
        logger.warning("Не удалось проверить замок %s: %s", path, e)
    return False


def owner_pid(vm_id: str) -> Optional[str]:
    """Pid written in the VM's lock file, or None."""
    try:
        return lock_path(vm_id).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
