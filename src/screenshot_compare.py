"""Baseline screenshot comparison using the SSIM structural metric.

A capture passes when SSIM(current, baseline) > threshold (default 0.99).
On mismatch a side-by-side diff image is written for visual triage.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config.settings import (
    BASELINE_DIR,
    DIFF_DIR,
    SSIM_RESIZE_ON_MISMATCH,
    SSIM_SAVE_DIFF,
    SSIM_THRESHOLD,
)

logger = logging.getLogger(__name__)

_DEPS_HINT = (
    "Для сравнения скриншотов нужны numpy, Pillow и scikit-image:\n"
    "  pip install numpy Pillow scikit-image"
)


class ScreenshotCompareError(RuntimeError):
    """Raised when a comparison cannot be performed (missing deps or files)."""


@dataclass
class ComparisonResult:
    """Outcome of a single baseline comparison."""

    passed: bool
    score: float
    threshold: float
    current_path: Path
    baseline_path: Optional[Path] = None
    diff_path: Optional[Path] = None
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for JSON reports."""
        return {
            "passed": self.passed,
            "score": round(self.score, 6),
            "threshold": self.threshold,
            "current": str(self.current_path),
            "baseline": str(self.baseline_path) if self.baseline_path else None,
            "diff": str(self.diff_path) if self.diff_path else None,
            "reason": self.reason,
            **self.details,
        }

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return f"[{verdict}] SSIM={self.score:.6f} (порог > {self.threshold}) {self.reason}".strip()


def _load_deps():
    """Import numpy / PIL / skimage lazily with a single actionable error."""
    try:
        import numpy as np
        from PIL import Image
        from skimage.metrics import structural_similarity
    except ImportError as e:
        raise ScreenshotCompareError(f"{_DEPS_HINT}\nПричина: {e}") from e
    return np, Image, structural_similarity


class ScreenshotComparator:
    """Compares captures against stored baselines with the SSIM metric."""

    def __init__(
        self,
        threshold: float = SSIM_THRESHOLD,
        baseline_dir: Path = BASELINE_DIR,
        diff_dir: Path = DIFF_DIR,
        save_diff: bool = SSIM_SAVE_DIFF,
        resize_on_mismatch: bool = SSIM_RESIZE_ON_MISMATCH,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Порог SSIM должен быть в диапазоне [0, 1], получено: {threshold}")
        self.threshold = threshold
        self.baseline_dir = Path(baseline_dir)
        self.diff_dir = Path(diff_dir)
        self.save_diff = save_diff
        self.resize_on_mismatch = resize_on_mismatch

    # --- Пути к эталонам --------------------------------------------------

    def baseline_path_for(self, test_name: str, vm_id: str) -> Path:
        """Return the baseline path for a given test on a given VM."""
        return self.baseline_dir / vm_id / f"{test_name}.png"

    def save_baseline(self, image_path: Path, test_name: str, vm_id: str,
                      overwrite: bool = False) -> Path:
        """Promote a capture to be the baseline for a test.

        Raises:
            FileExistsError: baseline exists and `overwrite` is False.
        """
        _, Image, _ = _load_deps()
        target = self.baseline_path_for(test_name, vm_id)
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"Эталон уже существует: {target}\n"
                f"Передайте overwrite=True, чтобы перезаписать."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(image_path) as img:
            img.convert("RGB").save(target)
        logger.info("Эталон сохранён: %s", target)
        return target

    # --- Сравнение --------------------------------------------------------

    def compare(
        self, current_path: Path, test_name: str, vm_id: str
    ) -> ComparisonResult:
        """Compare a capture against the stored baseline for `test_name`.

        A missing baseline is *not* a failure: the capture is promoted to
        baseline and the result passes with score 1.0, so the first run of a
        new test bootstraps itself.
        """
        current_path = Path(current_path)
        if not current_path.exists():
            raise ScreenshotCompareError(f"Скриншот не найден: {current_path}")

        baseline = self.baseline_path_for(test_name, vm_id)
        if not baseline.exists():
            self.save_baseline(current_path, test_name, vm_id)
            logger.warning(
                "Эталон для '%s' (%s) отсутствовал — создан из текущего скриншота. "
                "Проверьте его глазами перед тем, как доверять результатам.",
                test_name, vm_id,
            )
            return ComparisonResult(
                passed=True,
                score=1.0,
                threshold=self.threshold,
                current_path=current_path,
                baseline_path=baseline,
                reason="эталон создан из первого прогона (не проверен)",
                details={"baseline_created": True},
            )

        return self.compare_images(current_path, baseline, label=f"{vm_id}_{test_name}")

    def compare_images(
        self, current_path: Path, baseline_path: Path, label: str = "diff"
    ) -> ComparisonResult:
        """Compare two image files directly and return the SSIM verdict."""
        np, Image, structural_similarity = _load_deps()

        current_path, baseline_path = Path(current_path), Path(baseline_path)
        for p in (current_path, baseline_path):
            if not p.exists():
                raise ScreenshotCompareError(f"Файл не найден: {p}")

        with Image.open(current_path) as ci, Image.open(baseline_path) as bi:
            current = ci.convert("RGB")
            baseline = bi.convert("RGB")

            if current.size != baseline.size:
                if not self.resize_on_mismatch:
                    return ComparisonResult(
                        passed=False,
                        score=0.0,
                        threshold=self.threshold,
                        current_path=current_path,
                        baseline_path=baseline_path,
                        reason=(
                            f"размеры не совпадают: текущий {current.size} != "
                            f"эталон {baseline.size}"
                        ),
                        details={
                            "current_size": list(current.size),
                            "baseline_size": list(baseline.size),
                        },
                    )
                logger.warning(
                    "Размеры различаются (%s != %s) — масштабируем к эталону; "
                    "SSIM после масштабирования менее надёжен.",
                    current.size, baseline.size,
                )
                current = current.resize(baseline.size, Image.LANCZOS)

            cur_arr = np.asarray(current)
            base_arr = np.asarray(baseline)

        # SSIM по трём каналам: channel_axis=-1 учитывает цвет, а не только яркость.
        score, diff_map = structural_similarity(
            base_arr, cur_arr, channel_axis=-1, full=True, data_range=255
        )
        score = float(score)
        passed = score > self.threshold

        result = ComparisonResult(
            passed=passed,
            score=score,
            threshold=self.threshold,
            current_path=current_path,
            baseline_path=baseline_path,
            reason="" if passed else f"SSIM {score:.6f} <= порога {self.threshold}",
            details={"size": list(baseline.size)},
        )

        if not passed and self.save_diff:
            try:
                result.diff_path = self._write_diff(
                    base_arr, cur_arr, diff_map, label, np, Image
                )
            except Exception as e:
                # diff — диагностика, его сбой не должен ломать сам тест
                logger.error("Не удалось сохранить diff-изображение: %s", e)

        logger.info("Сравнение '%s': %s", label, result)
        return result

    def _write_diff(self, base_arr, cur_arr, diff_map, label: str, np, Image) -> Path:
        """Write a 3-panel diff image: baseline | current | difference heatmap."""
        # diff_map в диапазоне [-1, 1], где 1 = идентично. Инвертируем в "непохожесть".
        dissimilarity = (1.0 - diff_map.mean(axis=-1)) / 2.0
        dissimilarity = np.clip(dissimilarity, 0.0, 1.0)

        # Красная подсветка изменённых областей поверх приглушённого эталона
        heat = np.zeros_like(base_arr, dtype=np.float32)
        gray = base_arr.mean(axis=-1)
        heat[..., 0] = gray * 0.3 + dissimilarity * 255.0 * 0.7
        heat[..., 1] = gray * 0.3
        heat[..., 2] = gray * 0.3
        heat_img = Image.fromarray(np.clip(heat, 0, 255).astype(np.uint8))

        h, w = base_arr.shape[:2]
        canvas = Image.new("RGB", (w * 3 + 20, h), color=(20, 20, 20))
        canvas.paste(Image.fromarray(base_arr), (0, 0))
        canvas.paste(Image.fromarray(cur_arr), (w + 10, 0))
        canvas.paste(heat_img, (w * 2 + 20, 0))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.diff_dir / f"{label}_{timestamp}_diff.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out)
        logger.info("Diff-изображение сохранено: %s (эталон | текущий | различия)", out)
        return out


def compare_screenshot(
    current_path: Path, test_name: str, vm_id: str,
    threshold: float = SSIM_THRESHOLD,
) -> ComparisonResult:
    """Convenience wrapper for a one-off comparison."""
    return ScreenshotComparator(threshold=threshold).compare(current_path, test_name, vm_id)
