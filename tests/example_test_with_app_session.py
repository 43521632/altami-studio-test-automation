"""Example test using app_session fixture.

This shows how to write tests that start the application,
do something, and close it — all isolated from other tests.
"""

import logging

import pytest

from src.vm_manager import VMSession

logger = logging.getLogger(__name__)


@pytest.mark.app
@pytest.mark.asyncio
async def test_app_does_something(app_session: VMSession) -> None:
    """Example test that uses the running application.

    The app is started before the test and stopped after.
    Every test using app_session is isolated and can run in any order.
    """
    session = app_session
    logger.info("Запуск теста с приложением")

    # TODO: Add your test logic here using session.qmp
    # Examples:
    # - Click on UI elements
    # - Wait for specific screens
    # - Compare screenshots
    # - Enter text

    # For demo, just log success
    logger.info("✅ Тест успешно выполнен")
    assert True


# You can have many tests using app_session — they are all independent.
# No test modifies the app state permanently because it's restarted each time.
