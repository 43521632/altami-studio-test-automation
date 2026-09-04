"""Low-level VM operations: copying files, executing commands."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.vm_manager import VMSession

logger = logging.getLogger(__name__)


async def copy_file_to_vm(
    session: VMSession,
    local_path: Path,
    remote_path: Optional[str] = None,
) -> str:
    """Copy a file from host to the guest VM.

    Uses QEMU guest agent if available (via qmp) or falls back to SCP.
    Returns the remote path.
    """
    if remote_path is None:
        remote_path = f"/tmp/{local_path.name}"

    # Try QEMU guest agent file copy
    try:
        # QEMU guest agent supports file copy via guest-file-open/write/close
        # but this is not yet implemented in our QMP client.
        # For now, we'll use a simpler approach: expect SCP or shared folder.
        pass
    except Exception as e:
        logger.warning("QEMU guest agent copy failed: %s", e)

    # Fallback: use libvirt domain's shared folder or SCP.
    # For now, we assume a shared folder mounted at /mnt/host
    # or we use the VM's built-in browser to download (handled by test).
    raise NotImplementedError(
        "Копирование файлов на ВМ пока не реализовано. "
        "Используйте браузер внутри ВМ для скачивания установщика."
    )


async def execute_on_vm(
    session: VMSession,
    command: str,
    timeout: float = 60.0,
) -> tuple[int, str, str]:
    """Execute a command inside the guest VM via QEMU guest agent or SSH."""
    # We don't have guest agent command execution yet.
    # For now, we rely on keyboard/mouse UI interactions.
    raise NotImplementedError(
        "Выполнение команд на ВМ пока не реализовано. "
        "Используйте UI-взаимодействие через QMP."
    )
