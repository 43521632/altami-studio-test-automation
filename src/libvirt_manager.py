"""Low-level VM lifecycle management via libvirt (virt-manager backend).

This module talks to an *existing* libvirt instance and drives domains that
were already created in virt-manager. It never defines or deletes domains.

The libvirt Python binding is fully synchronous, so every blocking call is
offloaded to a thread executor by the ``a*`` async wrappers.
"""

import asyncio
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from config.settings import (
    LIBVIRT_CONNECT_RETRIES,
    LIBVIRT_RETRY_BACKOFF,
    LIBVIRT_URI,
    get_vm_config,
)

logger = logging.getLogger(__name__)

# libvirt импортируется лениво: модуль должен импортироваться и на машинах
# без установленного libvirt (например, на машине разработчика).
_libvirt = None

_INSTALL_HINT = (
    "Модуль libvirt недоступен. Установите на Ubuntu-хосте:\n"
    "  sudo apt install -y virt-manager libvirt-daemon-system python3-libvirt\n"
    "  sudo usermod -aG libvirt $USER   # затем перелогиньтесь\n"
    "или в venv:  pip install libvirt-python  (нужен пакет libvirt-dev)"
)


class LibvirtNotAvailable(RuntimeError):
    """Raised when the libvirt Python binding is not installed."""


class LibvirtManagerError(RuntimeError):
    """Raised for libvirt operation failures (connection, lookup, lifecycle)."""


class VMNotFoundError(LibvirtManagerError):
    """Raised when a domain name is absent from the libvirt instance."""


def _get_libvirt():
    """Import and cache the libvirt binding, or raise a helpful error."""
    global _libvirt
    if _libvirt is None:
        try:
            import libvirt  # noqa: PLC0415 — намеренно ленивый импорт
        except ImportError as e:
            raise LibvirtNotAvailable(_INSTALL_HINT) from e
        # Подавляем печать ошибок libvirt в stderr — логируем их сами.
        libvirt.registerErrorHandler(lambda _ctx, _err: None, None)
        _libvirt = libvirt
    return _libvirt


class VMState(str, Enum):
    """Human-readable domain states mapped from libvirt VIR_DOMAIN_* codes."""

    NOSTATE = "нет состояния"
    RUNNING = "работает"
    BLOCKED = "заблокирована"
    PAUSED = "пауза"
    SHUTDOWN = "выключается"
    SHUTOFF = "выключена"
    CRASHED = "аварийно завершена"
    PMSUSPENDED = "приостановлена"
    UNKNOWN = "неизвестно"
    NOT_FOUND = "не найдена"

    @classmethod
    def from_code(cls, code: int) -> "VMState":
        """Map a libvirt domain state code to a VMState member."""
        return {
            0: cls.NOSTATE,
            1: cls.RUNNING,
            2: cls.BLOCKED,
            3: cls.PAUSED,
            4: cls.SHUTDOWN,
            5: cls.SHUTOFF,
            6: cls.CRASHED,
            7: cls.PMSUSPENDED,
        }.get(code, cls.UNKNOWN)


class LibvirtManager:
    """Singleton connection to a libvirt instance, one per URI.

    Example:
        mgr = LibvirtManager()
        mgr.start("windows-10-test")
        mgr.wait_for_state("windows-10-test", VMState.RUNNING, timeout=180)
    """

    _instances: Dict[str, "LibvirtManager"] = {}

    def __new__(cls, uri: str = LIBVIRT_URI) -> "LibvirtManager":
        # Singleton по URI: одно соединение на процесс для каждого URI.
        if uri not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[uri] = instance
        return cls._instances[uri]

    def __init__(self, uri: str = LIBVIRT_URI) -> None:
        if self._initialized:
            return
        self.uri = uri
        self._conn = None
        self._initialized = True

    # --- Соединение ------------------------------------------------------

    @property
    def connected(self) -> bool:
        """True if the libvirt connection is open and alive."""
        if self._conn is None:
            return False
        try:
            return bool(self._conn.isAlive())
        except Exception:
            return False

    def connect(self, force: bool = False):
        """Open (or reuse) the libvirt connection, retrying with backoff.

        Args:
            force: drop any existing connection and reconnect from scratch.

        Raises:
            LibvirtNotAvailable: libvirt binding is not installed.
            LibvirtManagerError: all connection attempts failed.
        """
        libvirt = _get_libvirt()

        if force:
            self.close()
        if self.connected:
            return self._conn

        last_error: Optional[Exception] = None
        delay = 1.0
        for attempt in range(1, LIBVIRT_CONNECT_RETRIES + 1):
            try:
                self._conn = libvirt.open(self.uri)
                if self._conn is None:
                    raise LibvirtManagerError(f"libvirt.open({self.uri}) вернул None")
                logger.info("Подключение к libvirt установлено: %s", self.uri)
                return self._conn
            except Exception as e:
                last_error = e
                logger.warning(
                    "Попытка %d/%d подключения к libvirt (%s) не удалась: %s",
                    attempt, LIBVIRT_CONNECT_RETRIES, self.uri, e,
                )
                if attempt < LIBVIRT_CONNECT_RETRIES:
                    time.sleep(delay)
                    delay *= LIBVIRT_RETRY_BACKOFF

        raise LibvirtManagerError(
            f"Не удалось подключиться к libvirt по {self.uri} "
            f"за {LIBVIRT_CONNECT_RETRIES} попыт(ок): {last_error}\n"
            f"Проверьте: systemctl status libvirtd, членство в группе libvirt."
        )

    def close(self) -> None:
        """Close the libvirt connection if open (errors are swallowed)."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as e:
                logger.debug("Ошибка при закрытии соединения libvirt: %s", e)
            finally:
                self._conn = None

    def _ensure_conn(self):
        """Return a live connection, reconnecting transparently if needed."""
        if not self.connected:
            logger.info("Соединение с libvirt потеряно — переподключаемся")
            return self.connect(force=True)
        return self._conn

    def __enter__(self) -> "LibvirtManager":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- Поиск доменов ---------------------------------------------------

    def list_vms(self) -> List[Dict[str, Any]]:
        """List every domain known to libvirt (running and stopped)."""
        conn = self._ensure_conn()
        try:
            domains = conn.listAllDomains(0)
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось получить список ВМ: {e}") from e

        result: List[Dict[str, Any]] = []
        for dom in domains:
            try:
                state_code, _ = dom.state()
                result.append(
                    {
                        "name": dom.name(),
                        "uuid": dom.UUIDString(),
                        "id": dom.ID() if dom.isActive() else None,
                        "state": VMState.from_code(state_code),
                        "autostart": bool(dom.autostart()),
                        "persistent": bool(dom.isPersistent()),
                    }
                )
            except Exception as e:
                logger.warning("Не удалось прочитать состояние домена: %s", e)
        return sorted(result, key=lambda d: d["name"])

    def list_vm_names(self) -> List[str]:
        """Return just the domain names."""
        return [vm["name"] for vm in self.list_vms()]

    def get_domain(self, vm_name: str):
        """Look up a libvirt domain object by name.

        Raises:
            VMNotFoundError: no domain with that name exists.
        """
        conn = self._ensure_conn()
        libvirt = _get_libvirt()
        try:
            return conn.lookupByName(vm_name)
        except libvirt.libvirtError as e:
            available = ", ".join(self.list_vm_names()) or "(список пуст)"
            raise VMNotFoundError(
                f"ВМ '{vm_name}' не найдена в libvirt ({self.uri}).\n"
                f"Доступные ВМ: {available}\n"
                f"Проверьте поле vm_name в config/vms_config.yaml. Причина: {e}"
            ) from e

    def resolve_vm_name(self, vm_id: str) -> str:
        """Translate a config VM id (e.g. "windows") into its libvirt name."""
        cfg = get_vm_config(vm_id)
        vm_name = cfg.get("vm_name")
        if not vm_name:
            raise LibvirtManagerError(
                f"Для '{vm_id}' не задан vm_name в config/vms_config.yaml"
            )
        return vm_name

    # --- Состояние -------------------------------------------------------

    def get_state(self, vm_name: str) -> VMState:
        """Return the current state of a domain."""
        dom = self.get_domain(vm_name)
        try:
            state_code, _ = dom.state()
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось получить состояние '{vm_name}': {e}") from e
        return VMState.from_code(state_code)

    def is_running(self, vm_name: str) -> bool:
        """True if the domain is active. Missing domains return False."""
        try:
            return self.get_state(vm_name) is VMState.RUNNING
        except VMNotFoundError:
            return False

    def status(self, vm_name: str) -> Dict[str, Any]:
        """Return a detailed status dict for a domain (never raises on lookup)."""
        try:
            dom = self.get_domain(vm_name)
        except VMNotFoundError:
            return {"name": vm_name, "exists": False, "state": VMState.NOT_FOUND}

        info: Dict[str, Any] = {"name": vm_name, "exists": True}
        try:
            state_code, _ = dom.state()
            # dom.info() -> [state, maxMem(KiB), memory(KiB), nrVirtCpu, cpuTime]
            raw = dom.info()
            info.update(
                {
                    "state": VMState.from_code(state_code),
                    "uuid": dom.UUIDString(),
                    "id": dom.ID() if dom.isActive() else None,
                    "max_memory_mb": raw[1] // 1024,
                    "memory_mb": raw[2] // 1024,
                    "vcpus": raw[3],
                    "cpu_time_s": round(raw[4] / 1e9, 2),
                    "autostart": bool(dom.autostart()),
                    "persistent": bool(dom.isPersistent()),
                }
            )
        except Exception as e:
            logger.warning("Частичный статус для '%s': %s", vm_name, e)
            info.setdefault("state", VMState.UNKNOWN)
            info["error"] = str(e)
        return info

    def wait_for_state(
        self, vm_name: str, target: VMState, timeout: int = 180, poll_interval: float = 2.0
    ) -> bool:
        """Poll until the domain reaches `target` or `timeout` elapses.

        Returns:
            True if the target state was reached, False on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.get_state(vm_name) is target:
                    return True
            except LibvirtManagerError as e:
                logger.debug("Опрос состояния '%s': %s", vm_name, e)
            time.sleep(poll_interval)
        logger.warning(
            "ВМ '%s' не перешла в состояние '%s' за %dс", vm_name, target.value, timeout
        )
        return False

    # --- Управление жизненным циклом -------------------------------------

    def start(self, vm_name: str, wait: bool = False, timeout: int = 180) -> bool:
        """Start a domain. Returns True if it is running afterwards.

        Args:
            wait: block until the domain reports RUNNING.
            timeout: seconds to wait when `wait` is True.
        """
        dom = self.get_domain(vm_name)
        if dom.isActive():
            logger.info("ВМ '%s' уже запущена", vm_name)
            return True
        try:
            dom.create()
            logger.info("ВМ '%s' запускается", vm_name)
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось запустить '{vm_name}': {e}") from e

        if wait:
            return self.wait_for_state(vm_name, VMState.RUNNING, timeout)
        return True

    def stop(self, vm_name: str, force: bool = False, timeout: int = 120) -> bool:
        """Stop a domain: graceful ACPI shutdown, falling back to destroy.

        Args:
            force: skip the graceful attempt and destroy immediately.
            timeout: seconds to wait for graceful shutdown before forcing.
        """
        dom = self.get_domain(vm_name)
        if not dom.isActive():
            logger.info("ВМ '%s' уже выключена", vm_name)
            return True

        if force:
            return self._destroy(dom, vm_name)

        try:
            dom.shutdown()
            logger.info("ВМ '%s': отправлен ACPI shutdown, ожидание %dс", vm_name, timeout)
        except Exception as e:
            logger.warning("ACPI shutdown для '%s' не сработал (%s) — принудительно", vm_name, e)
            return self._destroy(dom, vm_name)

        if self.wait_for_state(vm_name, VMState.SHUTOFF, timeout):
            logger.info("ВМ '%s' корректно выключена", vm_name)
            return True

        # Гость не отреагировал на ACPI — гасим принудительно.
        logger.warning("ВМ '%s' не выключилась за %dс — принудительное завершение", vm_name, timeout)
        return self._destroy(dom, vm_name)

    def _destroy(self, dom, vm_name: str) -> bool:
        """Force-kill a domain (equivalent to pulling the power cord)."""
        try:
            dom.destroy()
            logger.info("ВМ '%s' принудительно остановлена", vm_name)
            return True
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось остановить '{vm_name}': {e}") from e

    def restart(self, vm_name: str, force: bool = False, timeout: int = 180) -> bool:
        """Restart a domain: stop (if active), then start and wait for RUNNING."""
        dom = self.get_domain(vm_name)
        if dom.isActive():
            self.stop(vm_name, force=force, timeout=timeout)
            self.wait_for_state(vm_name, VMState.SHUTOFF, timeout=timeout)
        return self.start(vm_name, wait=True, timeout=timeout)

    def suspend(self, vm_name: str) -> bool:
        """Pause a running domain."""
        try:
            self.get_domain(vm_name).suspend()
            logger.info("ВМ '%s' приостановлена", vm_name)
            return True
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось приостановить '{vm_name}': {e}") from e

    def resume(self, vm_name: str) -> bool:
        """Resume a paused domain."""
        try:
            self.get_domain(vm_name).resume()
            logger.info("ВМ '%s' возобновлена", vm_name)
            return True
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось возобновить '{vm_name}': {e}") from e

    # --- Скриншоты и сеть -------------------------------------------------

    def screenshot(self, vm_name: str, output_path: Path, screen: int = 0) -> Path:
        """Capture the VM console screen and write it to `output_path`.

        libvirt returns PPM; Pillow converts it to the extension of
        `output_path` (PNG recommended).

        Raises:
            LibvirtManagerError: the domain is not running or capture failed.
        """
        dom = self.get_domain(vm_name)
        if not dom.isActive():
            raise LibvirtManagerError(
                f"Скриншот ВМ '{vm_name}' невозможен: ВМ не запущена"
            )

        conn = self._ensure_conn()
        buffer = bytearray()
        stream = None
        try:
            stream = conn.newStream()
            dom.screenshot(stream, screen, 0)
            stream.recvAll(lambda _s, data, buf: buf.extend(data), buffer)
            stream.finish()
            stream = None
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось снять скриншот '{vm_name}': {e}") from e
        finally:
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass

        try:
            import io

            from PIL import Image

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(io.BytesIO(bytes(buffer))) as img:
                img.convert("RGB").save(output_path)
        except ImportError as e:
            raise LibvirtManagerError(
                "Для сохранения скриншотов нужен Pillow: pip install Pillow"
            ) from e
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось сохранить скриншот в {output_path}: {e}") from e

        logger.info("Скриншот ВМ '%s' сохранён: %s", vm_name, output_path)
        return output_path

    def get_ip_addresses(self, vm_name: str) -> List[str]:
        """Return guest IPv4 addresses reported by the DHCP lease table.

        Returns an empty list when the guest has no lease yet or the
        network backend does not expose leases.
        """
        dom = self.get_domain(vm_name)
        if not dom.isActive():
            return []
        libvirt = _get_libvirt()
        try:
            ifaces = dom.interfaceAddresses(
                libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE, 0
            )
        except Exception as e:
            logger.debug("Не удалось получить IP для '%s': %s", vm_name, e)
            return []

        addresses: List[str] = []
        for iface in (ifaces or {}).values():
            for addr in iface.get("addrs") or []:
                if addr.get("type") == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                    addresses.append(addr["addr"])
        return addresses

    def get_host_info(self) -> Dict[str, Any]:
        """Return host capacity info, used for resource pre-flight checks."""
        conn = self._ensure_conn()
        try:
            # getInfo() -> [model, memory(MiB), cpus, mhz, nodes, sockets, cores, threads]
            info = conn.getInfo()
            return {
                "cpu_model": info[0],
                "memory_mb": info[1],
                "cpus": info[2],
                "cpu_mhz": info[3],
                "hostname": conn.getHostname(),
                "libvirt_version": conn.getLibVersion(),
                # ВАЖНО: не conn.getFreeMemory() — она не учитывает страничный
                # кэш, который ядро отдаёт по первому требованию. На хосте с
                # прогретым кэшем она показывает ~1 ГБ при 47 ГБ реально
                # доступных и даёт ложную тревогу о нехватке памяти.
                "free_memory_mb": psutil.virtual_memory().available // (1024 * 1024),
            }
        except Exception as e:
            raise LibvirtManagerError(f"Не удалось получить информацию о хосте: {e}") from e

    # --- Async-обёртки ----------------------------------------------------
    # libvirt блокирующий, поэтому вызовы уходят в пул потоков.

    async def _to_thread(self, func, *args, **kwargs):
        """Run a blocking libvirt call in the default executor."""
        loop = asyncio.get_event_loop()
        if kwargs:
            from functools import partial

            func = partial(func, **kwargs)
        return await loop.run_in_executor(None, func, *args)

    async def astart(self, vm_name: str, wait: bool = False, timeout: int = 180) -> bool:
        """Async wrapper around :meth:`start`."""
        return await self._to_thread(self.start, vm_name, wait=wait, timeout=timeout)

    async def astop(self, vm_name: str, force: bool = False, timeout: int = 120) -> bool:
        """Async wrapper around :meth:`stop`."""
        return await self._to_thread(self.stop, vm_name, force=force, timeout=timeout)

    async def arestart(self, vm_name: str, force: bool = False, timeout: int = 180) -> bool:
        """Async wrapper around :meth:`restart`."""
        return await self._to_thread(self.restart, vm_name, force=force, timeout=timeout)

    async def astatus(self, vm_name: str) -> Dict[str, Any]:
        """Async wrapper around :meth:`status`."""
        return await self._to_thread(self.status, vm_name)

    async def alist_vms(self) -> List[Dict[str, Any]]:
        """Async wrapper around :meth:`list_vms`."""
        return await self._to_thread(self.list_vms)

    async def ascreenshot(self, vm_name: str, output_path: Path, screen: int = 0) -> Path:
        """Async wrapper around :meth:`screenshot`."""
        return await self._to_thread(self.screenshot, vm_name, output_path, screen)

    async def await_for_state(
        self, vm_name: str, target: VMState, timeout: int = 180
    ) -> bool:
        """Async wrapper around :meth:`wait_for_state`."""
        return await self._to_thread(self.wait_for_state, vm_name, target, timeout=timeout)
