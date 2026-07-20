"""System and UI smoke tests for the macOS VM."""

import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)


@pytest.mark.macos
@pytest.mark.system
class TestMacosSystem(BaseVMTest):
    """QMP-level checks that the macOS VM is alive and sane."""

    vm_id = "macos"

    @pytest.mark.smoke
    async def test_macos_status(self):
        """VM reports a running QEMU state."""
        status = await self.get_vm_status()
        assert status["status"] == "running", f"ВМ не запущена: {status}"
        logger.info("Статус ВМ: %s", status["status"])

    async def test_macos_cpu_info(self):
        """QEMU reports at least one vCPU."""
        cpu_info = await self.qmp_execute("query-cpus-fast")
        assert len(cpu_info) > 0, "Нет информации о CPU"
        logger.info("Количество vCPU: %d", len(cpu_info))


@pytest.mark.macos
@pytest.mark.ui
class TestMacosUI(BaseVMTest):
    """UI checks driven through QMP input injection and SSIM comparison."""

    vm_id = "macos"

    async def test_desktop_matches_baseline(self):
        """The idle desktop matches its stored baseline."""
        await self.assert_screen("desktop")
