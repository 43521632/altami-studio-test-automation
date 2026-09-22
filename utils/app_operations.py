"""Application installation and lifecycle management."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.vm_manager import VMSession

logger = logging.getLogger(__name__)


async def install_app(session: VMSession, timeout: float = 300.0) -> bool:
    """Установить приложение в госте через UI.

    Заглушка: установщик уже скачан браузером гостя (tests/test_install.py),
    но сам мастер установки ещё не автоматизирован — его шаги снимаются с
    живой ВМ.
    """
    logger.info("Установка приложения (мастер установки ещё не автоматизирован)")
    # TODO: запустить скачанный установщик из папки загрузок и пройти мастер
    return True


async def start_app(session: VMSession) -> bool:
    """Launch the application and wait for it to be ready."""
    logger.info("Запуск приложения")
    # TODO: Implement app start via UI (click desktop icon, start menu, etc.)
    # For now, assume app is already running
    return True


async def stop_app(session: VMSession) -> bool:
    """Close the application gracefully."""
    logger.info("Остановка приложения")
    # TODO: Implement app close (Alt+F4, click close button, etc.)
    return True


async def app_is_installed(session: VMSession) -> bool:
    """Check if the application is installed."""
    # TODO: Check for existence of app files, registry keys, etc.
    # For now, assume it's installed
    return True
