"""High-level VM orchestration: libvirt lifecycle + QMP guest-UI session.

`LibvirtManager` starts and stops domains; `QMPSession` drives the guest UI.
This module joins them into a single object a test can hold: :class:`VMSession`.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from config.settings import (
    SCREENSHOT_DIR,
    get_all_vm_ids,
    get_enabled_vm_ids,
    get_vm_config,
)
from src.libvirt_manager import (
    LibvirtManager,
    LibvirtManagerError,
    VMNotFoundError,
    VMState,
)
from src.qmp_client import QMPError, QMPSession

logger = logging.getLogger(__name__)


class VMManagerError(RuntimeError):
    """Raised when a VM cannot be prepared for testing."""


def _parse_resolution(value: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse a "1920x1080" string into (width, height)."""
    if not value:
        return None
    try:
        width, height = value.lower().split("x")
        return int(width), int(height)
    except (ValueError, AttributeError):
        logger.warning("Не удалось разобрать разрешение %r — определим автоматически", value)
        return None


class VMSession:
    """A running VM with an open QMP session, ready to receive UI actions.

    Obtained from :meth:`VMManager.session`, which handles setup and teardown.
    """

    def __init__(
        self,
        vm_id: str,
        vm_name: str,
        config: Dict[str, Any],
        libvirt: LibvirtManager,
        qmp: QMPSession,
    ) -> None:
        self.vm_id = vm_id
        self.vm_name = vm_name
        self.config = config
        self.libvirt = libvirt
        self.qmp = qmp

    def __repr__(self) -> str:
        return f"<VMSession {self.vm_id} ({self.vm_name})>"

    @property
    def os_type(self) -> str:
        """Guest OS family from config ("windows" | "linux" | "macos")."""
        return self.config.get("os_type", "unknown")

    # --- Скриншоты --------------------------------------------------------

    async def screenshot(self, name: str, directory: Optional[Path] = None) -> Path:
        """Capture a timestamped screenshot into the per-VM screenshot dir."""
        directory = Path(directory or SCREENSHOT_DIR) / self.vm_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return await self.qmp.screendump(directory / f"{name}_{timestamp}.png")

    async def wait_until_screen_stable(
        self,
        timeout: float = 120.0,
        poll_interval: float = 3.0,
        stable_threshold: float = 0.999,
        required_stable_polls: int = 2,
    ) -> bool:
        """Wait until the console stops changing — a proxy for "boot finished".

        Compares consecutive screendumps with SSIM. Useful after starting a VM,
        since libvirt reports RUNNING as soon as the CPU starts, long before
        the desktop is usable.

        Returns:
            True if the screen settled, False on timeout.
        """
        # Импорт здесь: сравнение нужно не всем сценариям, а зависимости тяжёлые
        from src.screenshot_compare import ScreenshotComparator, ScreenshotCompareError

        import tempfile

        comparator = ScreenshotComparator(threshold=stable_threshold)
        deadline = asyncio.get_event_loop().time() + timeout
        stable_count = 0

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            previous: Optional[Path] = None
            index = 0

            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                index += 1
                current = tmp_dir / f"probe_{index}.png"
                try:
                    await self.qmp.screendump(current)
                except QMPError as e:
                    logger.debug("%s: скриншот при ожидании загрузки не удался: %s",
                                 self.vm_id, e)
                    continue

                if previous is not None:
                    try:
                        result = comparator.compare_images(
                            current, previous, label=f"{self.vm_id}_boot"
                        )
                    except ScreenshotCompareError as e:
                        logger.warning("%s: не удалось сравнить кадры загрузки: %s",
                                       self.vm_id, e)
                        return False

                    if result.score > stable_threshold:
                        stable_count += 1
                        if stable_count >= required_stable_polls:
                            logger.info("%s: экран стабилизировался — ОС загружена",
                                        self.vm_id)
                            return True
                    else:
                        # Экран ещё меняется — счётчик стабильности сбрасываем
                        stable_count = 0
                previous = current

        logger.warning("%s: экран не стабилизировался за %.0fс", self.vm_id, timeout)
        return False


class VMManager:
    """Prepares VMs for testing: pre-flight checks, boot, QMP session, teardown.

    Example:
        async with VMManager().session("windows") as vm:
            await vm.qmp.mouse_click(960, 540)
    """

    def __init__(self, libvirt: Optional[LibvirtManager] = None) -> None:
        self.libvirt = libvirt or LibvirtManager()

    # --- Конфигурация -----------------------------------------------------

    @staticmethod
    def all_vm_ids() -> List[str]:
        """Every VM id in the config."""
        return get_all_vm_ids()

    @staticmethod
    def enabled_vm_ids() -> List[str]:
        """VM ids with `enabled: true`."""
        return get_enabled_vm_ids()

    @staticmethod
    def config_for(vm_id: str) -> Dict[str, Any]:
        """Config block for one VM.

        Raises:
            VMManagerError: the id is absent from vms_config.yaml.
        """
        config = get_vm_config(vm_id)
        if not config:
            raise VMManagerError(
                f"ВМ '{vm_id}' не найдена в config/vms_config.yaml. "
                f"Доступны: {', '.join(get_all_vm_ids()) or '(пусто)'}"
            )
        return config

    # --- Проверки перед запуском ------------------------------------------

    def preflight(self, vm_id: str, vm_name_override: Optional[str] = None) -> Dict[str, Any]:
        """Validate that a VM can be tested, without starting it.

        Checks config completeness, domain existence and libvirt reachability.

        Returns:
            A report dict with "ok" plus any "problems" / "warnings".
        """
        report: Dict[str, Any] = {"vm_id": vm_id, "ok": False,
                                  "problems": [], "warnings": []}
        try:
            config = self.config_for(vm_id)
        except VMManagerError as e:
            report["problems"].append(str(e))
            return report

        vm_name = vm_name_override or config.get("vm_name")
        report["vm_name"] = vm_name
        if not vm_name:
            report["problems"].append("не задан vm_name в конфиге")

        qmp_socket = config.get("qmp_socket")
        report["qmp_socket"] = qmp_socket
        if not qmp_socket:
            report["problems"].append(
                "не задан qmp_socket — без него управление UI невозможно"
            )

        if vm_name:
            try:
                status = self.libvirt.status(vm_name)
                report["state"] = status.get("state", VMState.UNKNOWN)
                if not status.get("exists"):
                    report["problems"].append(
                        f"домен '{vm_name}' отсутствует в libvirt "
                        f"(проверьте: virsh list --all)"
                    )
                else:
                    # Расхождение ресурсов — не ошибка, но стоит знать
                    expected_mb = config.get("memory")
                    actual_mb = status.get("max_memory_mb")
                    if expected_mb and actual_mb and abs(expected_mb - actual_mb) > 64:
                        report["warnings"].append(
                            f"память: в конфиге {expected_mb} МБ, у домена {actual_mb} МБ"
                        )
                    expected_cpu = config.get("cpu_cores")
                    actual_cpu = status.get("vcpus")
                    if expected_cpu and actual_cpu and expected_cpu != actual_cpu:
                        report["warnings"].append(
                            f"vCPU: в конфиге {expected_cpu}, у домена {actual_cpu}"
                        )
            except LibvirtManagerError as e:
                report["problems"].append(f"libvirt недоступен: {e}")

        report["ok"] = not report["problems"]
        return report

    def check_host_resources(self, vm_ids: List[str]) -> Dict[str, Any]:
        """Check that the host can hold the requested VMs simultaneously.

        Returns a report; `ok=False` means the VMs may fail to start or swap.
        """
        required_mb = sum(
            int(get_vm_config(vm_id).get("memory", 0) or 0) for vm_id in vm_ids
        )
        report: Dict[str, Any] = {"required_mb": required_mb, "ok": True, "warnings": []}
        try:
            host = self.libvirt.get_host_info()
        except LibvirtManagerError as e:
            report["warnings"].append(f"не удалось получить данные о хосте: {e}")
            return report

        report["host_total_mb"] = host["memory_mb"]
        report["host_free_mb"] = host["free_memory_mb"]

        if required_mb > host["memory_mb"]:
            report["ok"] = False
            report["warnings"].append(
                f"запрошено {required_mb} МБ, всего на хосте {host['memory_mb']} МБ — "
                f"запустить одновременно не получится"
            )
        elif required_mb > host["free_memory_mb"]:
            report["warnings"].append(
                f"запрошено {required_mb} МБ, свободно {host['free_memory_mb']} МБ — "
                f"возможен своп и деградация UI-тестов"
            )
        return report

    # --- Сессия -----------------------------------------------------------

    async def _ensure_running(self, vm_name: str, config: Dict[str, Any]) -> None:
        """Start the domain if needed and wait for it to report RUNNING."""
        boot_timeout = int(config.get("boot_timeout", 180))
        if self.libvirt.is_running(vm_name):
            logger.info("ВМ '%s' уже запущена", vm_name)
            return

        logger.info("Запуск ВМ '%s' (ожидание до %dс)", vm_name, boot_timeout)
        await self.libvirt.astart(vm_name, wait=True, timeout=boot_timeout)
        if not self.libvirt.is_running(vm_name):
            raise VMManagerError(
                f"ВМ '{vm_name}' не перешла в состояние 'работает' за {boot_timeout}с"
            )

    async def _wait_for_socket(self, socket_path: str, timeout: float = 60.0) -> None:
        """Wait for QEMU to create the QMP socket after domain start."""
        path = Path(socket_path)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if path.exists():
                return
            await asyncio.sleep(1.0)
        raise VMManagerError(
            f"QMP-сокет {socket_path} не появился за {timeout:.0f}с.\n"
            f"Обычная причина — в XML домена не добавлен второй QMP-сокет через\n"
            f"<qemu:commandline> (см. README, раздел «Второй QMP-сокет»)."
        )

    @asynccontextmanager
    async def session(
        self,
        vm_id: str,
        vm_name_override: Optional[str] = None,
        start_if_stopped: bool = True,
        wait_for_boot: bool = False,
        stop_on_exit: bool = False,
    ) -> AsyncIterator[VMSession]:
        """Yield a ready :class:`VMSession`, tearing it down afterwards.

        Args:
            vm_name_override: use this libvirt domain name instead of the config one.
            start_if_stopped: start the VM if it is not running.
            wait_for_boot: additionally wait until the console screen settles.
            stop_on_exit: shut the VM down when the session ends.
        """
        config = self.config_for(vm_id)
        vm_name = vm_name_override or config.get("vm_name")
        if not vm_name:
            raise VMManagerError(f"Для '{vm_id}' не задан vm_name в конфиге")

        socket_path = config.get("qmp_socket")
        if not socket_path:
            raise VMManagerError(
                f"Для '{vm_id}' не задан qmp_socket — управление UI невозможно"
            )

        try:
            self.libvirt.get_domain(vm_name)
        except VMNotFoundError as e:
            raise VMManagerError(str(e)) from e

        if start_if_stopped:
            await self._ensure_running(vm_name, config)
        elif not self.libvirt.is_running(vm_name):
            raise VMManagerError(f"ВМ '{vm_name}' не запущена (start_if_stopped=False)")

        await self._wait_for_socket(socket_path)

        resolution = _parse_resolution(
            (config.get("ui_settings") or {}).get("resolution")
        )
        qmp = QMPSession(vm_id, socket_path, resolution=resolution)
        await qmp.connect()

        session = VMSession(vm_id, vm_name, config, self.libvirt, qmp)
        try:
            if wait_for_boot:
                await session.wait_until_screen_stable(
                    timeout=float(config.get("boot_timeout", 180))
                )
            yield session
        finally:
            await qmp.disconnect()
            if stop_on_exit:
                try:
                    await self.libvirt.astop(
                        vm_name, timeout=int(config.get("shutdown_timeout", 120))
                    )
                except LibvirtManagerError as e:
                    logger.error("Не удалось остановить '%s': %s", vm_name, e)

    def close(self) -> None:
        """Close the underlying libvirt connection."""
        self.libvirt.close()
