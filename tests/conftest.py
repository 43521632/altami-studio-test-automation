"""Shared pytest fixtures: VM session, screenshot assertions, failure capture.

The VM under test is chosen by the VM_ID environment variable, which
`run_tests.py` sets for each pytest subprocess. Running pytest directly
defaults to VM_ID=windows.

The VM boots once per pytest session and every test in that session runs
against it sequentially — a single guest cannot be driven concurrently.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from config.settings import SCREENSHOT_DIR
from src.logging_setup import setup_logging
from src.screenshot_compare import ComparisonResult, ScreenshotComparator
from src.vm_manager import VMManager, VMSession

logger = logging.getLogger(__name__)

# Какая ВМ тестируется в этом процессе pytest
VM_ID = os.environ.get("VM_ID", "windows")
# Домен libvirt из run_tests.py --vm-name, если он переопределён
VM_NAME_OVERRIDE = os.environ.get("VM_NAME_OVERRIDE") or None


def pytest_configure(config: pytest.Config) -> None:
    """Register OS markers and initialise logging."""
    for marker, description in [
        ("windows", "Тесты для Windows ВМ"),
        ("astra", "Тесты для Astra Linux ВМ"),
        ("macos", "Тесты для macOS ВМ"),
        ("ui", "UI-тесты со сравнением скриншотов"),
        ("smoke", "Быстрые проверки доступности ВМ"),
        ("network", "Сетевые тесты"),
        ("security", "Тесты безопасности"),
        ("system", "Системные тесты"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {description}")
    setup_logging()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report on the item, so fixtures can see failures."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


# --- Фикстуры ВМ ------------------------------------------------------------


@pytest.fixture(scope="session")
def vm_id() -> str:
    """The VM id under test in this pytest process."""
    return VM_ID


@pytest.fixture(scope="session")
def vm_manager() -> VMManager:
    """Session-wide VM manager."""
    manager = VMManager()
    yield manager
    manager.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def vm_session(vm_manager: VMManager, vm_id: str) -> VMSession:
    """Boot the VM (if needed), open a QMP session, and yield it.

    Skips the whole session — rather than failing every test — when the VM
    is unavailable, so a missing macOS host does not look like 40 bugs.
    """
    from src.vm_manager import VMManagerError

    try:
        async with vm_manager.session(
            vm_id, vm_name_override=VM_NAME_OVERRIDE, wait_for_boot=True
        ) as session:
            logger.info("ВМ '%s' готова к тестам", vm_id)
            yield session
    except VMManagerError as e:
        pytest.skip(f"ВМ '{vm_id}' недоступна: {e}")
    except Exception as e:  # noqa: BLE001 — сюда попадают ошибки libvirt/QMP
        pytest.skip(f"Не удалось подготовить ВМ '{vm_id}': {e}")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def guest_login(vm_session: VMSession) -> bool:
    """Sign into the guest OS once, before any test runs.

    Setup, not a test: UI tests need a desktop, and the VM boots to a lock
    screen. Skips itself when the desktop is already up (the VM keeps running
    between runs). Credentials come from the VM's `login:` block.
    """
    from src.guest_login import ensure_logged_in

    performed = await ensure_logged_in(vm_session)
    logger.info(
        "%s: автологин %s", vm_session.vm_id,
        "выполнен" if performed else "не потребовался",
    )
    return performed


@pytest_asyncio.fixture(loop_scope="session")
async def screenshot_on_failure(request, vm_session: VMSession):
    """Capture a screenshot automatically when a test fails."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        try:
            path = await vm_session.screenshot(f"FAILED_{request.node.name}")
            logger.error("Тест упал — скриншот сохранён: %s", path)
        except Exception as e:
            logger.error("Не удалось снять скриншот после падения: %s", e)


# --- Сравнение скриншотов ---------------------------------------------------


class ScreenshotAsserter:
    """Helper bound to one VM: capture, compare against baseline, assert."""

    def __init__(self, session: VMSession, comparator: ScreenshotComparator) -> None:
        self.session = session
        self.comparator = comparator
        self.last_result: Optional[ComparisonResult] = None

    async def capture(self, name: str) -> Path:
        """Take a screenshot without comparing it."""
        return await self.session.screenshot(name)

    async def compare(self, test_name: str) -> ComparisonResult:
        """Capture and compare against the baseline, without asserting."""
        current = await self.session.screenshot(test_name)
        self.last_result = self.comparator.compare(current, test_name, self.session.vm_id)
        return self.last_result

    async def assert_matches(self, test_name: str) -> ComparisonResult:
        """Capture, compare, and fail the test if SSIM is below threshold."""
        result = await self.compare(test_name)
        if not result.passed:
            message = [
                f"Скриншот не совпал с эталоном: SSIM={result.score:.6f} "
                f"(нужно > {result.threshold})",
                f"  текущий: {result.current_path}",
                f"  эталон:  {result.baseline_path}",
            ]
            if result.diff_path:
                message.append(f"  различия: {result.diff_path}")
            if result.reason:
                message.append(f"  причина: {result.reason}")
            pytest.fail("\n".join(message))
        return result


@pytest_asyncio.fixture(loop_scope="session")
async def screenshot(vm_session: VMSession) -> ScreenshotAsserter:
    """Screenshot capture and SSIM baseline assertions for the current VM."""
    return ScreenshotAsserter(vm_session, ScreenshotComparator())


@pytest.fixture(scope="session")
def screenshot_dir(vm_id: str) -> Path:
    """Per-VM screenshot directory."""
    path = Path(SCREENSHOT_DIR) / vm_id
    path.mkdir(parents=True, exist_ok=True)
    return path
