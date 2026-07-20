"""Base class for VM tests.

Provides QMP shortcuts and screenshot assertions on top of the `vm_session`
fixture. Subclasses declare which VM they target via `vm_id`; tests are
skipped automatically when running against a different VM.

Example:
    @pytest.mark.windows
    class TestLogin(BaseVMTest):
        vm_id = "windows"

        async def test_login_screen(self):
            await self.click(960, 540)
            await self.assert_screen("login_screen")
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.screenshot_compare import ComparisonResult
from src.vm_manager import VMSession

logger = logging.getLogger(__name__)


class BaseVMTest:
    """Base class wiring the `vm_session` and `screenshot` fixtures in."""

    #: VM id from vms_config.yaml this test class targets
    vm_id: Optional[str] = None

    @pytest.fixture(autouse=True)
    def _bind_fixtures(self, request, vm_session: VMSession, screenshot, vm_id: str):
        """Attach the session to the instance and skip mismatched VMs."""
        if self.vm_id and self.vm_id != vm_id:
            pytest.skip(
                f"Тест предназначен для ВМ '{self.vm_id}', "
                f"а прогон идёт на '{vm_id}'"
            )
        self.session = vm_session
        self.qmp = vm_session.qmp
        self.screenshot = screenshot
        self.config: Dict[str, Any] = vm_session.config
        yield
        # Скриншот при падении — диагностика, ради которой стоит потерпеть I/O
        report = getattr(request.node, "rep_call", None)
        if report is not None and report.failed:
            logger.error("Тест '%s' упал", request.node.name)

    # --- Ввод ---------------------------------------------------------------

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at absolute guest pixel coordinates."""
        await self.qmp.mouse_click(x, y, button)

    async def double_click(self, x: int, y: int) -> None:
        """Double-click at absolute guest pixel coordinates."""
        await self.qmp.mouse_double_click(x, y)

    async def type_text(self, text: str) -> None:
        """Type an ASCII string into the guest."""
        await self.qmp.type_text(text)

    async def press(self, *keys: str) -> None:
        """Press a key combination, e.g. `await self.press("ctrl", "c")`."""
        await self.qmp.send_keys(list(keys))

    # --- Скриншоты ----------------------------------------------------------

    async def capture(self, name: str) -> Path:
        """Take a screenshot without comparing it to a baseline."""
        return await self.session.screenshot(name)

    async def assert_screen(self, name: str) -> ComparisonResult:
        """Capture and assert the screen matches its baseline (SSIM)."""
        return await self.screenshot.assert_matches(name)

    # --- Состояние ВМ -------------------------------------------------------

    async def qmp_execute(self, command: str, **kwargs) -> Any:
        """Execute a raw QMP command against the guest's QEMU process."""
        return await self.qmp.execute(command, kwargs or None)

    async def get_vm_status(self) -> Dict:
        """Return the QEMU run state (`{"status": "running", ...}`)."""
        return await self.qmp.query_status()
