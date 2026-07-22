#!/usr/bin/env python3
"""Ручной драйвер гостевого UI для разведки координат и отладки шагов теста.

Чёрный ящик через QMP: двигает мышь, кликает, набирает текст и снимает
скриншоты той же ВМ, что и тесты. Нужен, чтобы ГЛАЗАМИ найти координаты
кнопок и подобрать области для сравнения, прежде чем писать тест.

Какую ВМ вести — берётся из переменной окружения VM_ID (как в тестах):

    VM_ID=astra   python scripts/ui_probe.py shot desktop
    VM_ID=windows python scripts/ui_probe.py glideclick 960 540

Команды:
    shot NAME            снять скриншот -> печатает путь к PNG
    res                  определить разрешение экрана гостя
    move X Y             телепорт указателя в точку
    glide X Y            плавное перемещение (нужно для меню, см. док)
    click X Y [btn]      клик (btn: left|right|middle, по умолчанию left)
    glideclick X Y [btn] плавно навести и кликнуть (надёжно для меню/кнопок)
    dclick X Y           двойной клик
    scroll up|down [N]   прокрутить колесо под курсором (N щелчков, по умолч. 3)
    key K [K2 ...]       нажать клавишу/комбинацию (qcode: ret esc ctrl ...)
    type "текст"         набрать ASCII-строку (кириллица не поддерживается)
    boot                 запустить ВМ, дождаться загрузки и войти (как тесты)

Последняя позиция указателя запоминается между вызовами (файл в TMPDIR),
поэтому `glide` ведёт курсор от предыдущей точки — как настоящая мышь.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import SCREENSHOT_DIR, get_vm_config  # noqa: E402
from src.qmp_client import QMPSession  # noqa: E402

VM_ID = os.environ.get("VM_ID", "astra")
_CFG = get_vm_config(VM_ID) or {}
_SOCK = _CFG.get("qmp_socket")
_POS_FILE = Path(tempfile.gettempdir()) / f"ui_probe_{VM_ID}.pos"


def _parse_res(value):
    try:
        w, h = str(value).lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return None


_RES = _parse_res((_CFG.get("ui_settings") or {}).get("resolution"))


def _load_pos():
    try:
        x, y = _POS_FILE.read_text().split()
        return int(x), int(y)
    except (OSError, ValueError):
        # старт по центру экрана, если позиция ещё не сохранялась
        w, h = _RES or (1920, 1080)
        return w // 2, h // 2


def _save_pos(x, y):
    try:
        _POS_FILE.write_text(f"{x} {y}")
    except OSError:
        pass


async def _with_qmp(fn):
    if not _SOCK:
        raise SystemExit(f"Для ВМ '{VM_ID}' не задан qmp_socket в конфиге")
    qmp = QMPSession(VM_ID, _SOCK, resolution=_RES)
    await qmp.connect()
    try:
        return await fn(qmp)
    finally:
        await qmp.disconnect()


async def _glide(qmp, x, y, steps=24, delay=0.015):
    x0, y0 = _load_pos()
    for i in range(1, steps + 1):
        nx = round(x0 + (x - x0) * i / steps)
        ny = round(y0 + (y - y0) * i / steps)
        await qmp.mouse_move(nx, ny)
        if delay:
            await asyncio.sleep(delay)
    _save_pos(x, y)


# --- Команды ---------------------------------------------------------------

async def cmd_shot(name):
    async def _f(qmp):
        out = Path(SCREENSHOT_DIR) / VM_ID / f"probe_{name}.png"
        await qmp.screendump(out)
        return out
    print(f"SHOT={await _with_qmp(_f)}")


async def cmd_res():
    print(f"RES={await _with_qmp(lambda q: q.detect_resolution())}")


async def cmd_move(x, y):
    await _with_qmp(lambda q: q.mouse_move(x, y))
    _save_pos(x, y)
    print(f"move {x},{y}")


async def cmd_glide(x, y):
    await _with_qmp(lambda q: _glide(q, x, y))
    print(f"glide -> {x},{y}")


async def cmd_click(x, y, btn="left"):
    await _with_qmp(lambda q: q.mouse_click(x, y, btn))
    _save_pos(x, y)
    print(f"click {btn} {x},{y}")


async def cmd_glideclick(x, y, btn="left"):
    async def _f(qmp):
        await _glide(qmp, x, y)
        await asyncio.sleep(0.4)
        await qmp.mouse_click(x, y, btn)
    await _with_qmp(_f)
    _save_pos(x, y)
    print(f"glideclick {btn} {x},{y}")


async def cmd_dclick(x, y):
    await _with_qmp(lambda q: q.mouse_double_click(x, y))
    _save_pos(x, y)
    print(f"dclick {x},{y}")


async def cmd_scroll(direction, clicks):
    """Прокрутить колесо под текущим курсором: scroll up|down [щелчков]."""
    up = direction == "up"
    await _with_qmp(lambda q: q.mouse_wheel(clicks, up=up))
    print(f"scroll {direction} x{clicks}")


async def cmd_key(keys):
    await _with_qmp(lambda q: q.send_keys(keys))
    print(f"key {'+'.join(keys)}")


async def cmd_type(text):
    await _with_qmp(lambda q: q.type_text(text))
    print(f"type {len(text)} chars")


async def cmd_boot():
    from src.vm_manager import VMManager
    from src.guest_login import ensure_logged_in
    mgr = VMManager()
    async with mgr.session(VM_ID, wait_for_boot=True) as session:
        performed = await ensure_logged_in(session)
        print(f"boot ok, autologin performed={performed}")
        p = await session.screenshot("probe_after_boot")
        print(f"SHOT={p}")
    mgr.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    table = {
        "shot": lambda: cmd_shot(args[0]),
        "res": lambda: cmd_res(),
        "move": lambda: cmd_move(int(args[0]), int(args[1])),
        "glide": lambda: cmd_glide(int(args[0]), int(args[1])),
        "click": lambda: cmd_click(int(args[0]), int(args[1]), *args[2:3]),
        "glideclick": lambda: cmd_glideclick(int(args[0]), int(args[1]), *args[2:3]),
        "dclick": lambda: cmd_dclick(int(args[0]), int(args[1])),
        "scroll": lambda: cmd_scroll(args[0], int(args[1]) if len(args) > 1 else 3),
        "key": lambda: cmd_key(args),
        "type": lambda: cmd_type(args[0]),
        "boot": lambda: cmd_boot(),
    }
    if cmd not in table:
        print(f"Неизвестная команда: {cmd}\n{__doc__}")
        raise SystemExit(1)
    asyncio.run(table[cmd]())


if __name__ == "__main__":
    main()
