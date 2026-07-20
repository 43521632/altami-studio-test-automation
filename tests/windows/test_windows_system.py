"""System and UI smoke tests for the Windows VM."""

import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)


@pytest.mark.windows
@pytest.mark.system
class TestWindowsSystem(BaseVMTest):
    """QMP-level checks that the Windows VM is alive and sane."""

    vm_id = "windows"

    @pytest.mark.smoke
    async def test_windows_status(self):
        """VM reports a running QEMU state."""
        status = await self.get_vm_status()
        assert status["status"] == "running", f"ВМ не запущена: {status}"
        logger.info("Статус ВМ: %s", status["status"])

    async def test_windows_cpu_info(self):
        """QEMU reports at least one vCPU."""
        # query-cpus устарел и удалён в новых QEMU — используем query-cpus-fast
        cpu_info = await self.qmp_execute("query-cpus-fast")
        assert len(cpu_info) > 0, "Нет информации о CPU"
        logger.info("Количество vCPU: %d", len(cpu_info))

    async def test_windows_memory_info(self):
        """Balloon memory is readable when the balloon device is present."""
        try:
            memory_info = await self.qmp_execute("query-balloon")
        except Exception as e:
            pytest.skip(f"Устройство balloon недоступно: {e}")
        actual_mb = memory_info.get("actual", 0) / 1024 / 1024
        assert actual_mb > 0, "Balloon вернул нулевой объём памяти"
        logger.info("Память гостя: %.0f МБ", actual_mb)


@pytest.mark.windows
@pytest.mark.ui
class TestWindowsUI(BaseVMTest):
    """UI checks driven through QMP input injection and SSIM comparison.

    NOTE: the first run creates the baseline from whatever is on screen.
    Review baseline/windows/*.png by eye before trusting later results.
    """

    vm_id = "windows"

    async def test_desktop_matches_baseline(self):
        """The idle desktop matches its stored baseline."""
        await self.assert_screen("desktop")

    async def test_screenshot_is_captured(self):
        """A screenshot can be captured and is non-empty."""
        path = await self.capture("smoke_capture")
        assert path.exists(), f"Скриншот не создан: {path}"
        assert path.stat().st_size > 0, f"Скриншот пустой: {path}"
        logger.info("Скриншот: %s (%d байт)", path, path.stat().st_size)
