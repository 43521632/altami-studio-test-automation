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

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytest

from config.settings import SCREENSHOT_DIR
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
        # Падение логирует хук в tests/conftest.py — с ID кейса, шагом и
        # причиной. Дублировать его здесь строкой «тест упал» смысла нет.

    # --- Ввод ---------------------------------------------------------------

    #: последняя позиция указателя — старт для плавного перемещения glide()
    _ptr: Tuple[int, int] = (960, 600)

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at absolute guest pixel coordinates."""
        await self.qmp.mouse_click(x, y, button)
        self._ptr = (x, y)

    async def glide(
        self, x: int, y: int, steps: int = 24, step_delay: float = 0.015
    ) -> None:
        """Move the pointer to (x, y) as continuous motion, not a teleport.

        A single absolute-position event does not reliably trigger Qt hover /
        submenu-open logic in the fly menu — the widget needs a stream of
        movement events. We interpolate from the last known pointer position
        in small steps so menus highlight and expand the way they do under a
        real mouse.
        """
        x0, y0 = self._ptr
        for i in range(1, steps + 1):
            nx = round(x0 + (x - x0) * i / steps)
            ny = round(y0 + (y - y0) * i / steps)
            await self.qmp.mouse_move(nx, ny)
            if step_delay:
                await asyncio.sleep(step_delay)
        self._ptr = (x, y)

    async def glide_click(
        self, x: int, y: int, button: str = "left", settle: float = 0.4
    ) -> None:
        """Glide the pointer onto (x, y), let it highlight, then click."""
        await self.glide(x, y)
        await asyncio.sleep(settle)
        await self.click(x, y, button)

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

    # --- Скриншоты: сравнение по области -----------------------------------
    # Полноэкранное сравнение ломается, когда в кадре есть меняющиеся зоны
    # (часы, список сессий с датами, курсор). Тогда тест строят вокруг
    # статичной области — вырезают её из кадра и сверяют только ей.

    async def capture_region(
        self, name: str, box: Tuple[int, int, int, int], fast: bool = False,
        margin: int = 0,
    ) -> Path:
        """Capture the screen and crop it to `box` = (left, top, right, bottom).

        Returns the path to the cropped PNG (a sibling of the full capture).
        Coordinates are guest pixels from the top-left corner.

        `fast=True` не сохраняет кадр целиком: QEMU пишет сырой PPM, из него
        сразу вырезается область, PPM удаляется. Замер на живой ВМ 23.07.2026
        (1920x1200): screendump в PPM — 13 мс, кроп — 8 мс, тогда как обычный
        путь тратит ~1 с на кодирование полного кадра в PNG и чтение его
        обратно. Нужен там, где окно живёт секунду-полторы и медленный цикл
        успевает заглянуть в него от силы один раз. Платой идёт диагностика:
        полного кадра на диске не остаётся, только вырезанная область.

        `margin` расширяет вырезаемую область на N пикселей с каждой стороны —
        запас, по которому потом ищут эталон со сдвигом, см.
        :meth:`~src.screenshot_compare.ScreenshotComparator.compare_shifted`.
        """
        from PIL import Image

        if margin:
            left, top, right, bottom = box
            box = (left - margin, top - margin, right + margin, bottom + margin)

        if fast:
            directory = Path(SCREENSHOT_DIR) / self.session.vm_id
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            raw = await self.qmp.screendump(directory / f"{name}_{stamp}.ppm")
            crop_path = raw.with_name(f"{raw.stem}_region.png")
            try:
                with Image.open(raw) as img:
                    img.crop(box).save(crop_path)
            finally:
                raw.unlink(missing_ok=True)
            return crop_path

        full = await self.capture(name)
        crop_path = full.with_name(f"{full.stem}_region.png")
        with Image.open(full) as img:
            img.crop(box).save(crop_path)
        return crop_path

    async def compare_region(
        self,
        name: str,
        box: Tuple[int, int, int, int],
        threshold: Optional[float] = None,
        fast: bool = False,
        shift: int = 0,
    ) -> ComparisonResult:
        """Crop the screen to `box` and compare it against the baseline (no fail).

        A missing baseline is created from the crop and the result passes —
        same bootstrap rule as :meth:`assert_screen`.

        `threshold` переопределяет порог SSIM для этого сравнения. Пригодно для
        «мягких» проверок наличия (значок есть, но может быть выделен/в фокусе),
        где попиксельная строгость 0.99 не нужна.

        `fast` — быстрая съёмка, см. :meth:`capture_region`. Заодно отключает
        запись diff-картинок: быстрым путём опрашивают в цикле, и промах на
        каждой итерации — норма, а не повод оставить файл в screenshots/diff.

        `shift` — допуск на смещение окна: область снимается с запасом, и
        эталон ищется по ней со сдвигом до N пикселей в каждую сторону. Нужен
        окнам, которые встают по-разному от запуска к запуску, см.
        :meth:`~src.screenshot_compare.ScreenshotComparator.compare_shifted`.
        """
        crop = await self.capture_region(name, box, fast=fast, margin=shift)
        comparator = self.screenshot.comparator
        save_diff = comparator.save_diff and not fast
        if ((threshold is not None and threshold != comparator.threshold)
                or save_diff != comparator.save_diff):
            from src.screenshot_compare import ScreenshotComparator

            comparator = ScreenshotComparator(
                threshold=comparator.threshold if threshold is None else threshold,
                save_diff=save_diff,
            )
        if not shift:
            return comparator.compare(crop, name, self.session.vm_id)

        baseline = comparator.baseline_path_for(name, self.session.vm_id)
        if not baseline.exists():
            # Эталона ещё нет: сдвигать нечего, и создавать эталон из кадра с
            # запасом нельзя — он был бы больше нужной области. Снимаем ровно
            # по границам и отдаём обычному пути с его правилом бутстрапа.
            crop = await self.capture_region(name, box, fast=fast)
            return comparator.compare(crop, name, self.session.vm_id)
        return comparator.compare_shifted(
            crop, baseline, shift, label=f"{self.session.vm_id}_{name}"
        )

    async def assert_region(
        self,
        name: str,
        box: Tuple[int, int, int, int],
        threshold: Optional[float] = None,
        shift: int = 0,
    ) -> ComparisonResult:
        """Crop the screen to `box`, compare against baseline, fail on mismatch."""
        result = await self.compare_region(name, box, threshold, shift=shift)
        if not result.passed:
            message = [
                f"Область '{name}' не совпала с эталоном: SSIM={result.score:.6f} "
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

    # --- Состояние ВМ -------------------------------------------------------

    async def qmp_execute(self, command: str, **kwargs) -> Any:
        """Execute a raw QMP command against the guest's QEMU process."""
        return await self.qmp.execute(command, kwargs or None)

    async def get_vm_status(self) -> Dict:
        """Return the QEMU run state (`{"status": "running", ...}`)."""
        return await self.qmp.query_status()
