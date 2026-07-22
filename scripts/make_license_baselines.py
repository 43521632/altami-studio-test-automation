#!/usr/bin/env python3
"""Пересобрать эталоны теста активации лицензии из кадров разведки.

Эталоны (baseline/) не версионируются, поэтому здесь зафиксировано, ИЗ ЧЕГО их
нарезали: полные кадры сценария, снятые `scripts/ui_probe.py shot` на живой ВМ
win_11_auto-test 22.07.2026 в видеорежиме 1920x1200.

Кадры лежат там, куда пишет QEMU (SCREENSHOT_DIR/windows) и со временем
затираются. Если их уже нет, а эталоны надо пересобрать — пройдите сценарий
`tests/windows/test_windows_license_activation.py` пробником заново, снимая
кадры под теми же именами, и запустите:

    venv/bin/python scripts/make_license_baselines.py

Области здесь ДОЛЖНЫ совпадать с константами *_BOX в самом тесте.
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import SCREENSHOT_DIR  # noqa: E402

SHOTS = Path(SCREENSHOT_DIR) / "windows"
OUT = ROOT / "baseline" / "windows"

# имя эталона -> (кадр разведки, область (left, top, right, bottom))
CROPS = {
    "altami_activation_title":   ("probe_s5_activation.png",     (466, 292, 780, 314)),
    "altami_activation_methods": ("probe_s5_activation.png",     (484, 328, 1240, 366)),
    "altami_file_dialog_title":  ("probe_s6_filedialog.png",     (476, 322, 780, 346)),
    "altami_file_name_field":    ("probe_s10_selected.png",      (672, 840, 900, 862)),
    "altami_activation_done":    ("probe_s12_next.png",          (484, 328, 900, 378)),
    "altami_activation_toast":   ("probe_s13_finish.png",        (1715, 1055, 1870, 1092)),
    # Заставка лицензированной версии живёт ~1.5с, поэтому её ловили серией
    # кадров: banner_NN.png через каждые 0.5с после двойного клика по ярлыку.
    "altami_licensed_banner":    ("banner_02.png",               (690, 730, 1260, 895)),
    "altami_licensed_title":     ("probe_s18_closed_info.png",   (24, 2, 200, 22)),
    "altami_license_info_title": ("probe_s17_license_info.png",  (737, 412, 900, 434)),
    "altami_license_email":      ("probe_s17_license_info.png",  (971, 462, 1170, 484)),
    "altami_license_regnum":     ("probe_s17_license_info.png",  (971, 492, 1170, 514)),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, (shot, box) in CROPS.items():
        src = SHOTS / shot
        if not src.exists():
            missing.append(shot)
            continue
        with Image.open(src) as img:
            img.crop(box).save(OUT / f"{name}.png")
        print(f"{name}: {box} из {shot}")
    if missing:
        print(f"\nНЕТ КАДРОВ ({len(missing)}): {', '.join(sorted(set(missing)))}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
