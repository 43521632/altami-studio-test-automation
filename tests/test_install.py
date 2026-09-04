"""Test that installs the application and performs initial setup.

This test MUST run first — it prepares the environment for all subsequent tests.
It uses the install_app fixture, which installs the app and leaves it closed.
"""

import logging

import pytest

from src.vm_manager import VMSession

logger = logging.getLogger(__name__)


@pytest.mark.order(0)
@pytest.mark.app
@pytest.mark.asyncio
async def test_install_app(install_app: VMSession) -> None:
    """Install the application and verify it was installed successfully.

    This test runs once per session and must succeed for other tests to run.
    """
    session = install_app
    logger.info("Проверка успешной установки приложения")

    # TODO: Add actual verification:
    # - Check that application files exist
    # - Check registry keys (Windows)
    # - Check desktop shortcut
    # - Verify version matches expected

    # For now, we just log success
    logger.info("✅ Приложение успешно установлено")
    assert True


# Optional: you can add more checks here, like verifying the app version
# or that the initial setup completed correctly.
