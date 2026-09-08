"""pytest plugin to report test results to Kiwi TCMS."""

import logging
import os
from pathlib import Path
from typing import Optional

import pytest

from .kiwi_client import KiwiClient

logger = logging.getLogger(__name__)

# Global client instance
_kiwi_client: Optional[KiwiClient] = None
_testrun_id: Optional[int] = None


def pytest_configure(config: pytest.Config) -> None:
    """Initialize Kiwi client if reporting is enabled."""
    global _kiwi_client, _testrun_id

    enabled = os.environ.get("KIWI_REPORTING_ENABLED", "true").lower() == "true"
    if not enabled:
        logger.info("Отправка в Kiwi TCMS отключена")
        return

    testrun_id_str = os.environ.get("KIWI_TESTRUN_ID")
    if not testrun_id_str:
        logger.info("KIWI_TESTRUN_ID не задан — отправка в Kiwi не выполняется")
        return

    try:
        _testrun_id = int(testrun_id_str)
    except ValueError:
        logger.warning("KIWI_TESTRUN_ID должен быть числом, получено: %s", testrun_id_str)
        return

    try:
        _kiwi_client = KiwiClient()
        logger.info("Инициализирован клиент Kiwi TCMS для тест-рана %d", _testrun_id)
    except Exception as e:
        logger.warning("Не удалось инициализировать клиент Kiwi: %s", e)
        _kiwi_client = None


def _get_case_id(item: pytest.Item) -> Optional[str]:
    """Get case ID from item.nodeid using case_id_for function."""
    try:
        from src.case_ids import case_id_for
        case_id = case_id_for(item.nodeid)
        return case_id
    except (ImportError, AttributeError):
        return None


def _collect_attachments(item: pytest.Item) -> list[Path]:
    """Collect attachments for this test (screenshots, logs, diff)."""
    attachments = []

    # 1. Screenshot on failure (if exists)
    # The screenshot is stored in the node with attribute 'rep_call' or via fixture
    # We'll check the common screenshot directory
    from config.settings import SCREENSHOT_DIR
    vm_id = os.environ.get("VM_ID", "windows")
    screenshot_dir = Path(SCREENSHOT_DIR) / vm_id
    if screenshot_dir.exists():
        # Look for screenshots with the test name
        for f in screenshot_dir.glob(f"*{item.name}*.png"):
            attachments.append(f)

    # 2. Log file (the run's log)
    # The log file path is set in conftest.py via _per_run_log_file()
    log_dir = Path("logs")
    if log_dir.exists():
        # Find the latest log for this run
        for f in log_dir.glob(f"pytest_{vm_id}_*.log"):
            attachments.append(f)
            break

    # 3. Diff image (if exists)
    diff_dir = screenshot_dir / "diff"
    if diff_dir.exists():
        for f in diff_dir.glob(f"*{item.name}*.png"):
            attachments.append(f)

    return attachments


def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    """Collect test result for Kiwi reporting."""
    if _kiwi_client is None or _testrun_id is None:
        return

    # Only process the 'call' phase
    if call.when != "call":
        return

    # Get case ID
    case_id = _get_case_id(item)
    if not case_id:
        logger.debug("Нет ID кейса для %s — пропускаем отправку", item.nodeid)
        return

    # Determine status
    if call.excinfo is None:
        status = "PASS"
        comment = ""
    else:
        if hasattr(call.excinfo, "type") and call.excinfo.type is pytest.skip.Exception:
            status = "SKIP"
            comment = str(call.excinfo.value)
        else:
            status = "FAIL"
            comment = str(call.excinfo.value) if call.excinfo.value else "Test failed"

    # Collect attachments
    attachments = _collect_attachments(item)

    # Send result to Kiwi
    try:
        _kiwi_client.add_case_result(
            testrun_id=_testrun_id,
            case_id=case_id,
            status=status,
            comment=comment,
            attachments=attachments,
        )
        logger.info("Результат для кейса %s отправлен в Kiwi: %s", case_id, status)
    except Exception as e:
        logger.error("Ошибка при отправке результата для кейса %s: %s", case_id, e)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Close the test run after all tests complete."""
    if _kiwi_client is None or _testrun_id is None:
        return

    try:
        _kiwi_client.close_testrun(_testrun_id)
        logger.info("Тест-ран %d закрыт", _testrun_id)
    except Exception as e:
        logger.error("Не удалось закрыть тест-ран %d: %s", _testrun_id, e)
