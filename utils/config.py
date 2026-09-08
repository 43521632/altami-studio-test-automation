"""Configuration helpers: revision, version, platform."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

from .kiwi_client import get_revision_from_kiwi

logger = logging.getLogger(__name__)


def _get_revision_from_kiwi_if_available() -> Optional[str]:
    """Try to get revision from Kiwi TCMS using KIWI_TESTRUN_ID."""
    testrun_id = os.environ.get("KIWI_TESTRUN_ID")
    if not testrun_id:
        return None
    try:
        testrun_id_int = int(testrun_id)
        logger.info("Попытка получить ревизию из Kiwi TCMS для тест-рана %d", testrun_id_int)
        revision = get_revision_from_kiwi(testrun_id_int)
        if revision:
            logger.info("Ревизия из Kiwi TCMS: %s", revision)
            return revision
        else:
            logger.warning("Не удалось извлечь ревизию из тест-рана %d", testrun_id_int)
    except ValueError:
        logger.warning("KIWI_TESTRUN_ID должен быть числом, получено: %s", testrun_id)
    except Exception as e:
        logger.error("Ошибка при получении ревизии из Kiwi: %s", e)
    return None


def get_revision() -> str:
    """Get build revision from various sources in priority order:
    1. Environment variable BUILD_REVISION
    2. Pytest argument --revision
    3. Kiwi TCMS (if KIWI_TESTRUN_ID is set)
    4. Raise error if none found.
    """
    # 1. Environment variable
    rev = os.environ.get("BUILD_REVISION")
    if rev:
        return rev

    # 2. Pytest command-line argument (if pytest is running)
    if hasattr(pytest, "config"):
        rev = pytest.config.getoption("--revision", None)
        if rev:
            return rev

    # 3. Kiwi TCMS (if KIWI_TESTRUN_ID is set)
    rev = _get_revision_from_kiwi_if_available()
    if rev:
        return rev

    raise RuntimeError(
        "Не задана ревизия сборки. Укажите BUILD_REVISION, --revision или настройте KIWI_TESTRUN_ID и KIWI_URL/KIWI_USER/KIWI_PASSWORD."
    )


def get_app_version() -> str:
    """Get application version from environment, pytest arg, or VERSION file."""
    # 1. Environment variable
    ver = os.environ.get("APP_VERSION")
    if ver:
        return ver

    # 2. Pytest command-line argument
    if hasattr(pytest, "config"):
        ver = pytest.config.getoption("--app-version", None)
        if ver:
            return ver

    # 3. VERSION file in project root
    root = Path(__file__).parent.parent
    version_file = root / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()

    raise RuntimeError(
        "Не удалось определить версию продукта. Задайте APP_VERSION, --app-version или создайте файл VERSION в корне проекта."
    )


def get_platform() -> str:
    """Return platform string for URL (windows-x86_64 or linux-x86_64)."""
    # Can be overridden by env or arg if needed
    plat = os.environ.get("TEST_PLATFORM")
    if plat:
        return plat

    # Determine from VM_ID if running in pytest
    vm_id = os.environ.get("VM_ID", "windows")
    if vm_id == "windows":
        return "windows-x86_64"
    elif vm_id in ("astra", "linux"):
        return "linux-x86_64"
    elif vm_id == "macos":
        return "darwin-x86_64"
    else:
        # Fallback
        return "windows-x86_64"


def get_installer_extension() -> str:
    """Return file extension for installer based on platform."""
    plat = get_platform()
    if "windows" in plat:
        return ".exe"
    elif "linux" in plat:
        return ".deb"
    elif "darwin" in plat:
        return ".dmg"
    else:
        return ".exe"
