"""System and UI smoke tests for the Astra Linux VM."""

import logging

import pytest

from tests.base_tests import BaseVMTest

logger = logging.getLogger(__name__)


@pytest.mark.astra
@pytest.mark.system
class TestAstraSystem(BaseVMTest):
    """QMP-level checks that the Astra Linux VM is alive and sane."""

    vm_id = "astra"

    @pytest.mark.smoke
    async def test_astra_status(self):
        """VM reports a running QEMU state."""
        status = await self.get_vm_status()
        assert status["status"] == "running", f"ВМ не запущена: {status}"
        logger.info("Статус ВМ: %s", status["status"])

    async def test_astra_cpu_info(self):
        """QEMU reports at least one vCPU."""
        # query-cpus устарел и удалён в новых QEMU — используем query-cpus-fast
        cpu_info = await self.qmp_execute("query-cpus-fast")
        assert len(cpu_info) > 0, "Нет информации о CPU"
        logger.info("Количество vCPU: %d", len(cpu_info))

    async def test_astra_cpu_count_matches_config(self):
        """vCPU count matches `cpu_cores` from vms_config.yaml."""
        expected = self.config.get("cpu_cores")
        if not expected:
            pytest.skip("cpu_cores не задан в конфиге")
        cpu_info = await self.qmp_execute("query-cpus-fast")
        assert len(cpu_info) == expected, (
            f"vCPU в конфиге {expected}, у домена {len(cpu_info)} — "
            f"конфиг разошёлся с virt-manager"
        )

    async def test_astra_memory_info(self):
        """Balloon memory is readable when the balloon device is present."""
        try:
            memory_info = await self.qmp_execute("query-balloon")
        except Exception as e:
            pytest.skip(f"Устройство balloon недоступно: {e}")
        actual_mb = memory_info.get("actual", 0) / 1024 / 1024
        assert actual_mb > 0, "Balloon вернул нулевой объём памяти"
        logger.info("Память гостя: %.0f МБ", actual_mb)


@pytest.mark.astra
@pytest.mark.ui
class TestAstraUI(BaseVMTest):
    """UI checks driven through QMP input injection and SSIM comparison.

    NOTE: the first run creates the baseline from whatever is on screen.
    Review baseline/astra/*.png by eye before trusting later results.
    """

    vm_id = "astra"

    async def test_desktop_matches_baseline(self):
        """The idle desktop matches its stored baseline."""
        await self.assert_screen("desktop")

    async def test_screenshot_is_captured(self):
        """A screenshot can be captured and is non-empty."""
        path = await self.capture("smoke_capture")
        assert path.exists(), f"Скриншот не создан: {path}"
        assert path.stat().st_size > 0, f"Скриншот пустой: {path}"
        logger.info("Скриншот: %s (%d байт)", path, path.stat().st_size)

    async def test_resolution_matches_config(self):
        """Guest video mode matches `ui_settings.resolution`.

        A mismatch here almost always means the VM booted into a different
        video mode, which makes every baseline comparison fail on size.
        """
        expected = self.config.get("ui_settings", {}).get("resolution")
        if not expected:
            pytest.skip("ui_settings.resolution не задан в конфиге")

        width, height = await self.qmp.detect_resolution()
        assert f"{width}x{height}" == expected, (
            f"Разрешение гостя {width}x{height}, в конфиге {expected} — "
            f"эталоны не совпадут по размеру"
        )
        logger.info("Разрешение гостя: %dx%d", width, height)

    @pytest.mark.smoke
    async def test_input_injection_works(self):
        """Mouse and keyboard events are accepted by the guest.

        Deliberately harmless: the pointer is moved without clicking and only
        Esc is pressed, so the guest UI is left in the state the other tests
        expect. A click at arbitrary coordinates could open something.
        """
        width, height = await self.qmp.detect_resolution()
        await self.qmp.mouse_move(width // 2, height // 2)
        await self.press("esc")
        logger.info("Инжекция ввода принята гостем")
