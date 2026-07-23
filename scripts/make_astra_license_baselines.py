#!/usr/bin/env python3
"""Пересобрать эталоны теста активации лицензии на Astra из кадров разведки.

Эталоны (baseline/) не версионируются, поэтому здесь зафиксировано, ИЗ ЧЕГО их
нарезали: полные кадры сценария, снятые `scripts/ui_probe.py shot` на живой ВМ
Astra_1_8_auto-test 23.07.2026 в видеорежиме рабочего стола 1920x1200.

Кадры лежат там, куда пишет QEMU (SCREENSHOT_DIR/astra) и со временем
затираются. Если их уже нет, а эталоны надо пересобрать — пройдите сценарий
`tests/Astra/test_astra_license_activation.py` пробником заново, снимая кадры
под теми же именами, и запустите:

    venv/bin/python scripts/make_astra_license_baselines.py

Области здесь ДОЛЖНЫ совпадать с константами *_BOX в самом тесте.

Эталоны `altami_restore_title` и `altami_app_toolbar` тут НЕ пересобираются:
они общие с TC-84 (tests/Astra/test_astra_altami_studio.py) и сняты им.
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import SCREENSHOT_DIR  # noqa: E402

SHOTS = Path(SCREENSHOT_DIR) / "astra"
OUT = ROOT / "baseline" / "astra"

# имя эталона -> (кадр разведки, область (left, top, right, bottom))
CROPS = {
    "altami_activation_title":    ("probe_probe_a3_activation.png", (460, 266, 780, 286)),
    "altami_activation_methods":  ("probe_probe_a3_activation.png", (483, 302, 1240, 336)),
    "altami_file_dialog_title":   ("probe_probe_a4_filedialog.png", (630, 288, 900, 308)),
    "altami_file_name_field":     ("probe_probe_a8_selected.png",   (730, 662, 900, 684)),
    "altami_license_file_field":  ("probe_probe_a9_back.png",       (623, 398, 900, 418)),
    "altami_activation_done":     ("probe_probe_a10_next.png",      (483, 302, 900, 352)),
    "altami_activation_toast":    ("probe_probe_a11_finish.png",    (1718, 1056, 1870, 1078)),
    "altami_demo_dialog":         ("probe_probe_a7b.png",           (730, 466, 910, 490)),
    "altami_licensed_title":      ("probe_probe_a13_skipped.png",   (26, 4, 200, 26)),
    "altami_license_info_title":  ("probe_probe_a14_info.png",      (696, 382, 870, 402)),
    "altami_license_email":       ("probe_probe_a14_info.png",      (983, 431, 1181, 453)),
    "altami_license_regnum":      ("probe_probe_a14_info.png",      (983, 462, 1181, 484)),
    # Заставка лицензированной версии живёт ~2с, поэтому её ловили серией
    # кадров через каждые 0.15с после клика по ярлыку в меню «Пуск».
    "altami_licensed_banner":     ("relaunch_20.ppm",               (668, 712, 1256, 878)),
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
            img.convert("RGB").crop(box).save(OUT / f"{name}.png")
        print(f"{name}: {box} из {shot}")
    if missing:
        print("\nНЕ НАЙДЕНЫ кадры разведки:", ", ".join(sorted(set(missing))))
        print("Снимите их заново пробником — см. docstring этого файла.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
