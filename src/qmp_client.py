"""QMP session for driving guest UI from the host, built on `qemu.qmp`.

libvirt manages the VM lifecycle but holds the domain's own QMP monitor
exclusively. This module talks to a *second*, dedicated QMP socket added to
the domain XML via <qemu:commandline> (see README: "Второй QMP-сокет").

What QMP gives us that libvirt does not:
  * input-send-event — inject keyboard AND absolute mouse events
  * screendump       — capture the console framebuffer to a host file

Nothing is installed inside the guest: UI automation is fully black-box.
"""

import asyncio
import logging
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config.settings import SCREENSHOT_DIR

logger = logging.getLogger(__name__)

# Абсолютные координаты QMP нормализованы в диапазон 0..32767 независимо
# от реального разрешения экрана гостя.
ABS_MAX = 32767

_QMP_HINT = (
    "Не установлена библиотека qemu.qmp. Установите:\n"
    "  pip install qemu.qmp>=0.0.6"
)


def _ensure_qemu_writable(directory: Path) -> None:
    """Create `directory` so the QEMU process can write screenshots into it.

    A plain mkdir() gives romand:romand 0755 under the usual umask 022, and
    QEMU (user `libvirt-qemu`) then fails with «Permission denied» on the
    per-VM subdirectory. We hand the directory the same group as SCREENSHOT_DIR
    (kvm, prepared per README) and add group write.

    Best-effort: on a directory we do not own — e.g. SCREENSHOT_DIR itself,
    owned by libvirt-qemu — chown/chmod raise PermissionError, which is fine
    precisely because such a directory is already set up correctly.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        gid = Path(SCREENSHOT_DIR).stat().st_gid
        if directory.stat().st_gid != gid:
            os.chown(directory, -1, gid)
        directory.chmod(0o775)
    except (PermissionError, OSError) as e:
        logger.debug("Не удалось расширить права на %s: %s", directory, e)


@contextmanager
def probe_path(suffix: str = ".ppm"):
    """Yield a throwaway screendump path QEMU is actually allowed to write to.

    NOT tempfile.TemporaryDirectory(): screendump is performed by the QEMU
    process (user `libvirt-qemu`), which cannot write into /tmp under the
    stock AppArmor profile, nor into a 0700 temp dir owned by us. SCREENSHOT_DIR
    is the one location prepared for it — see README, «Права на каталог
    скриншотов». Failures here surface as «QEMU не создал файл скриншота».
    """
    path = Path(SCREENSHOT_DIR) / f".probe_{os.getpid()}_{uuid.uuid4().hex}{suffix}"
    try:
        yield path
    finally:
        # Файл создаёт QEMU, владелец — libvirt-qemu; удаление опирается на
        # право записи в каталог (мы в группе kvm), а не на владение файлом.
        path.unlink(missing_ok=True)
        path.with_suffix(".ppm").unlink(missing_ok=True)


class QMPError(RuntimeError):
    """Raised for QMP connection or command failures."""


class QMPNotAvailable(RuntimeError):
    """Raised when the qemu.qmp package is not installed."""


def _get_qmp_client_cls():
    """Import qemu.qmp lazily so this module imports without it installed."""
    try:
        from qemu.qmp import QMPClient
    except ImportError as e:
        raise QMPNotAvailable(f"{_QMP_HINT}\nПричина: {e}") from e
    return QMPClient


# --- Раскладка: ASCII -> QKeyCode -------------------------------------------
# Имена взяты из перечисления QKeyCode в qapi/ui.json.
_QCODE_UNSHIFTED: Dict[str, str] = {
    " ": "spc", "\t": "tab", "\n": "ret", "\r": "ret",
    "-": "minus", "=": "equal", "[": "bracket_left", "]": "bracket_right",
    "\\": "backslash", ";": "semicolon", "'": "apostrophe", "`": "grave_accent",
    ",": "comma", ".": "dot", "/": "slash",
}
# Символы, которые набираются с Shift, и их база на клавиатуре US
_QCODE_SHIFTED: Dict[str, str] = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right",
    "|": "backslash", ":": "semicolon", '"': "apostrophe", "~": "grave_accent",
    "<": "comma", ">": "dot", "?": "slash",
}
_DIGIT_QCODE = {str(d): str(d) for d in range(10)}


def char_to_qcode(char: str) -> Tuple[str, bool]:
    """Map a single ASCII character to (qcode, needs_shift).

    Raises:
        ValueError: the character has no US-layout mapping.
    """
    if len(char) != 1:
        raise ValueError(f"Ожидался один символ, получено: {char!r}")

    if char.islower() and char.isalpha() and char.isascii():
        return char, False
    if char.isupper() and char.isalpha() and char.isascii():
        return char.lower(), True
    if char in _DIGIT_QCODE:
        return _DIGIT_QCODE[char], False
    if char in _QCODE_UNSHIFTED:
        return _QCODE_UNSHIFTED[char], False
    if char in _QCODE_SHIFTED:
        base = _QCODE_SHIFTED[char]
        return _DIGIT_QCODE.get(base, base), True

    raise ValueError(
        f"Символ {char!r} не поддерживается раскладкой US. "
        f"Для не-ASCII текста (кириллица) вводите его через буфер обмена "
        f"или переключение раскладки в гостевой ОС."
    )


def pixel_to_abs(value: int, extent: int) -> int:
    """Convert a pixel coordinate to the QMP absolute 0..32767 range.

    Args:
        value: pixel coordinate along the axis.
        extent: screen size along that axis, in pixels.
    """
    if extent <= 1:
        raise ValueError(f"Размер экрана должен быть > 1 пикселя, получено: {extent}")
    # Зажимаем в границы экрана: клик за краем гость всё равно проигнорирует
    value = max(0, min(int(value), extent - 1))
    return round(value * ABS_MAX / (extent - 1))


class QMPSession:
    """Async QMP session over a dedicated monitor socket.

    Example:
        async with QMPSession("windows", "/var/lib/libvirt/qemu/win.qmp",
                              resolution=(1920, 1080)) as qmp:
            await qmp.mouse_click(960, 540)
            await qmp.type_text("hello")
            await qmp.screendump(Path("shot.png"))
    """

    def __init__(
        self,
        vm_id: str,
        socket_path: str,
        resolution: Optional[Tuple[int, int]] = None,
        connect_timeout: float = 10.0,
    ) -> None:
        self.vm_id = vm_id
        self.socket_path = str(socket_path)
        self.resolution = resolution
        self.connect_timeout = connect_timeout
        self._client = None

    # --- Соединение ------------------------------------------------------

    @property
    def connected(self) -> bool:
        """True if the QMP client is currently connected."""
        return self._client is not None

    async def connect(self) -> None:
        """Open the QMP session and negotiate capabilities.

        Raises:
            QMPNotAvailable: qemu.qmp is not installed.
            QMPError: the socket is missing or the handshake failed.
        """
        if self.connected:
            return

        qmp_client_cls = _get_qmp_client_cls()

        if not Path(self.socket_path).exists():
            raise QMPError(
                f"{self.vm_id}: QMP-сокет не найден: {self.socket_path}\n"
                f"Проверьте, что ВМ запущена и что в XML домена добавлен второй\n"
                f"QMP-сокет через <qemu:commandline> (см. README)."
            )

        client = qmp_client_cls(self.vm_id)
        try:
            # qemu.qmp сам выполняет qmp_capabilities после подключения
            await asyncio.wait_for(
                client.connect(self.socket_path), timeout=self.connect_timeout
            )
        except asyncio.TimeoutError as e:
            raise QMPError(
                f"{self.vm_id}: таймаут подключения к QMP ({self.connect_timeout}с). "
                f"Возможно, к сокету уже подключён другой клиент."
            ) from e
        except Exception as e:
            raise QMPError(f"{self.vm_id}: не удалось подключиться к QMP: {e}") from e

        self._client = client
        logger.info("%s: QMP-сессия установлена (%s)", self.vm_id, self.socket_path)

    async def disconnect(self) -> None:
        """Close the QMP session, swallowing shutdown errors."""
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        except Exception as e:
            logger.debug("%s: ошибка при закрытии QMP: %s", self.vm_id, e)
        finally:
            self._client = None
            logger.info("%s: QMP-сессия закрыта", self.vm_id)

    async def __aenter__(self) -> "QMPSession":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.disconnect()

    async def execute(self, command: str, arguments: Optional[Dict] = None) -> Any:
        """Execute a raw QMP command.

        Raises:
            QMPError: not connected, or the command returned an error.
        """
        if self._client is None:
            raise QMPError(f"{self.vm_id}: нет QMP-соединения (вызовите connect())")
        try:
            return await self._client.execute(command, arguments or {})
        except Exception as e:
            raise QMPError(f"{self.vm_id}: команда QMP '{command}' не выполнена: {e}") from e

    # --- Состояние -------------------------------------------------------

    async def query_status(self) -> Dict:
        """Return the VM run state (`{"status": "running", ...}`)."""
        return await self.execute("query-status")

    async def is_running(self) -> bool:
        """True if the guest CPU is running (not paused)."""
        try:
            return (await self.query_status()).get("status") == "running"
        except QMPError:
            return False

    # --- Скриншоты -------------------------------------------------------

    async def screendump(self, output_path: Path, device: Optional[str] = None) -> Path:
        """Capture the console framebuffer to `output_path`.

        IMPORTANT: the file is written by the QEMU process itself, not by us.
        The target directory must be writable by the QEMU user (usually
        `libvirt-qemu`) and permitted by AppArmor. QEMU writes PPM; if
        `output_path` is not .ppm it is converted with Pillow.
        """
        output_path = Path(output_path)
        _ensure_qemu_writable(output_path.parent)

        # QEMU пишет PPM; если нужен другой формат — снимаем во временный PPM.
        wants_conversion = output_path.suffix.lower() != ".ppm"
        raw_path = output_path.with_suffix(".ppm") if wants_conversion else output_path

        args: Dict[str, Any] = {"filename": str(raw_path)}
        if device:
            args["device"] = device

        await self.execute("screendump", args)

        if not raw_path.exists():
            raise QMPError(
                f"{self.vm_id}: QEMU не создал файл скриншота {raw_path}.\n"
                f"Обычная причина — нет прав на запись у пользователя QEMU "
                f"(libvirt-qemu) или запрет AppArmor. Попробуйте каталог,\n"
                f"принадлежащий libvirt-qemu, либо /tmp."
            )

        if wants_conversion:
            try:
                from PIL import Image

                with Image.open(raw_path) as img:
                    img.convert("RGB").save(output_path)
                raw_path.unlink(missing_ok=True)
            except ImportError as e:
                raise QMPError("Для конвертации скриншота нужен Pillow") from e
            except Exception as e:
                raise QMPError(f"{self.vm_id}: не удалось конвертировать скриншот: {e}") from e

        logger.debug("%s: скриншот сохранён: %s", self.vm_id, output_path)
        return output_path

    async def detect_resolution(self) -> Tuple[int, int]:
        """Detect guest screen size by taking a throwaway screendump.

        The result is cached on the session for coordinate conversion.
        """
        from PIL import Image

        with probe_path() as shot:
            await self.screendump(shot)
            with Image.open(shot) as img:
                self.resolution = img.size
        logger.info("%s: определено разрешение экрана: %s", self.vm_id, self.resolution)
        return self.resolution

    async def _get_resolution(self) -> Tuple[int, int]:
        """Return the cached resolution, detecting it on first use."""
        if self.resolution is None:
            await self.detect_resolution()
        return self.resolution

    # --- Ввод: клавиатура -------------------------------------------------

    async def send_keys(self, keys: Sequence[str], hold_time_ms: int = 50) -> None:
        """Press a key combination simultaneously (e.g. ctrl+alt+delete).

        Args:
            keys: QKeyCode names, e.g. ["ctrl", "alt", "delete"].
            hold_time_ms: how long to hold the combination.
        """
        await self.execute(
            "send-key",
            {
                "keys": [{"type": "qcode", "data": k} for k in keys],
                "hold-time": hold_time_ms,
            },
        )
        logger.debug("%s: нажато %s", self.vm_id, "+".join(keys))

    async def type_text(self, text: str, delay_s: float = 0.02) -> None:
        """Type an ASCII string into the guest, one character at a time.

        Non-ASCII text (e.g. Cyrillic) is not supported by the US qcode
        layout — see :func:`char_to_qcode`.
        """
        for char in text:
            qcode, needs_shift = char_to_qcode(char)
            keys = ["shift", qcode] if needs_shift else [qcode]
            await self.send_keys(keys)
            if delay_s:
                await asyncio.sleep(delay_s)
        logger.debug("%s: введён текст длиной %d символов", self.vm_id, len(text))

    # --- Ввод: мышь -------------------------------------------------------

    async def mouse_move(self, x: int, y: int) -> None:
        """Move the pointer to absolute pixel coordinates (x, y).

        Requires a USB tablet device in the VM (virt-manager:
        Add Hardware -> Input -> EvTouch USB Graphics Tablet). Without it the
        guest only receives relative motion and coordinates will not land.
        """
        width, height = await self._get_resolution()
        await self.execute(
            "input-send-event",
            {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": pixel_to_abs(x, width)}},
                    {"type": "abs", "data": {"axis": "y", "value": pixel_to_abs(y, height)}},
                ]
            },
        )

    async def mouse_button(self, down: bool, button: str = "left") -> None:
        """Press or release a mouse button ("left" | "right" | "middle")."""
        await self.execute(
            "input-send-event",
            {"events": [{"type": "btn", "data": {"down": down, "button": button}}]},
        )

    async def mouse_click(
        self, x: int, y: int, button: str = "left", settle_s: float = 0.05
    ) -> None:
        """Move to (x, y) and perform a full click."""
        await self.mouse_move(x, y)
        # Небольшая пауза: гостевой ОС нужно время обработать перемещение
        # до нажатия, иначе клик уходит по старым координатам.
        await asyncio.sleep(settle_s)
        await self.mouse_button(True, button)
        await asyncio.sleep(settle_s)
        await self.mouse_button(False, button)
        logger.debug("%s: клик %s в (%d, %d)", self.vm_id, button, x, y)

    async def mouse_double_click(self, x: int, y: int, interval_s: float = 0.1) -> None:
        """Perform a double click at (x, y)."""
        await self.mouse_click(x, y)
        await asyncio.sleep(interval_s)
        await self.mouse_click(x, y)

    async def mouse_drag(
        self, x1: int, y1: int, x2: int, y2: int, steps: int = 10, settle_s: float = 0.02
    ) -> None:
        """Drag from (x1, y1) to (x2, y2) with intermediate motion steps."""
        await self.mouse_move(x1, y1)
        await asyncio.sleep(settle_s)
        await self.mouse_button(True)
        # Промежуточные шаги: резкий скачок гость может не распознать как drag
        for i in range(1, steps + 1):
            await self.mouse_move(
                round(x1 + (x2 - x1) * i / steps),
                round(y1 + (y2 - y1) * i / steps),
            )
            await asyncio.sleep(settle_s)
        await self.mouse_button(False)
        logger.debug("%s: drag (%d,%d) -> (%d,%d)", self.vm_id, x1, y1, x2, y2)

    # --- Управление питанием (дублирует libvirt, но через QMP) -------------

    async def system_powerdown(self) -> None:
        """Send an ACPI shutdown request to the guest."""
        await self.execute("system_powerdown")

    async def system_reset(self) -> None:
        """Hard-reset the guest."""
        await self.execute("system_reset")
