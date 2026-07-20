"""Orchestrates pytest runs across VMs.

One pytest subprocess per OS: tests run sequentially inside a VM (a single
guest cannot be driven concurrently), while different VMs run in parallel up
to `parallel_workers`. Results are collected from pytest's built-in JUnit XML.

Emergency stop (Ctrl+C / SIGTERM) terminates children and persists state so
`--restart` can resume with only the failures.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config.settings import (
    BASE_DIR,
    PARALLEL_WORKERS,
    REPORT_DIR,
    RETRY_COUNT,
    TEST_TIMEOUT,
)
from src.kiwi_reporter import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    KiwiReporter,
    TestResult,
)
from src.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)

STATE_FILE = BASE_DIR / ".test_state.json"


class EmergencyStop:
    """Cooperative shutdown flag wired to SIGINT and SIGTERM.

    The first signal requests a graceful stop; a second one is left to the
    default handler so an unresponsive run can still be killed.
    """

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self._original: Dict[int, Any] = {}

    @property
    def requested(self) -> bool:
        """True once a stop has been requested."""
        return self.event.is_set()

    def _handle(self, signum: int, _frame) -> None:
        if self.requested:
            # Второй сигнал — снимаем обработчик и падаем штатным образом
            logger.warning("Повторный сигнал %d — немедленное завершение", signum)
            signal.signal(signum, self._original.get(signum, signal.SIG_DFL))
            os.kill(os.getpid(), signum)
            return
        logger.warning(
            "Получен сигнал %d — аварийная остановка. Состояние будет сохранено. "
            "Повторный Ctrl+C завершит процесс немедленно.",
            signum,
        )
        self.event.set()

    def install(self) -> None:
        """Install handlers for SIGINT/SIGTERM."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._original[sig] = signal.getsignal(sig)
                signal.signal(sig, self._handle)
            except (ValueError, OSError):
                # Не главный поток — обработчик поставить нельзя
                logger.debug("Не удалось установить обработчик сигнала %d", sig)

    def restore(self) -> None:
        """Restore the previous signal handlers."""
        for sig, handler in self._original.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
        self._original.clear()


class TestRunner:
    """Runs the pytest suite for each VM and aggregates results.

    Args:
        vm_manager: used for pre-flight checks and VM startup.
        reporter: receives every :class:`TestResult`.
        parallel_workers: max VMs under test at once.
        stop_on_fail: abort the whole run after the first failing VM.
        retry_count: extra attempts for failed tests (via pytest --last-failed).
    """

    def __init__(
        self,
        vm_manager: Optional[VMManager] = None,
        reporter: Optional[KiwiReporter] = None,
        parallel_workers: int = PARALLEL_WORKERS,
        stop_on_fail: bool = False,
        retry_count: int = RETRY_COUNT,
        test_timeout: int = TEST_TIMEOUT,
        vm_name_override: Optional[str] = None,
    ) -> None:
        self.vm_manager = vm_manager or VMManager()
        self.reporter = reporter or KiwiReporter()
        self.parallel_workers = max(1, parallel_workers)
        self.stop_on_fail = stop_on_fail
        self.retry_count = max(0, retry_count)
        self.test_timeout = test_timeout
        # Применяется только при прогоне одной ВМ — проверяется в run_tests.py
        self.vm_name_override = vm_name_override

        self.emergency = EmergencyStop()
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        # Наблюдатели (паттерн Observer): вызываются на каждое событие прогона
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []

    # --- Observer ----------------------------------------------------------

    def add_listener(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a callback invoked as ``callback(event, payload)``.

        Events: vm_started, vm_finished, vm_failed, run_finished.
        """
        self._listeners.append(callback)

    def _emit(self, event: str, **payload: Any) -> None:
        """Notify listeners, isolating them from each other's failures."""
        for listener in self._listeners:
            try:
                listener(event, payload)
            except Exception as e:
                logger.error("Наблюдатель на событии '%s' упал: %s", event, e)

    # --- Состояние для перезапуска -----------------------------------------

    def save_state(self, state: Dict[str, Any]) -> Path:
        """Persist run state so `--restart` can resume."""
        state["saved_at"] = datetime.now().isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info("Состояние прогона сохранено: %s", STATE_FILE)
        return STATE_FILE

    @staticmethod
    def load_state() -> Optional[Dict[str, Any]]:
        """Load the persisted run state, or None if there is none."""
        if not STATE_FILE.exists():
            return None
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Не удалось прочитать %s: %s", STATE_FILE, e)
            return None

    @staticmethod
    def clear_state() -> None:
        """Remove the persisted run state."""
        STATE_FILE.unlink(missing_ok=True)

    # --- Запуск pytest ------------------------------------------------------

    def _build_pytest_args(
        self, vm_id: str, junit_path: Path, html_path: Path, only_failed: bool
    ) -> List[str]:
        """Assemble the pytest command line for one VM."""
        config = self.vm_manager.config_for(vm_id)
        test_path = config.get("test_path") or f"./tests/{vm_id}"

        args = [
            sys.executable, "-m", "pytest",
            str(test_path),
            f"--junitxml={junit_path}",
            f"--timeout={self.test_timeout}",
            "-p", "no:cacheprovider" if not only_failed else "cacheprovider",
            # Внутри одной ВМ строго последовательно: гость один, параллелить нельзя
            "-p", "no:xdist",
            "--tb=short",
            "-v",
        ]
        if only_failed:
            # Повтор только упавших — используем кэш прошлого прогона
            args = [a for a in args if a != "no:cacheprovider"]
            args.append("--last-failed")
        try:
            import importlib.util

            if importlib.util.find_spec("pytest_html"):
                args.append(f"--html={html_path}")
                args.append("--self-contained-html")
        except ImportError:
            pass
        return args

    async def _run_pytest(
        self, vm_id: str, junit_path: Path, html_path: Path, only_failed: bool = False
    ) -> int:
        """Run pytest for one VM and return its exit code."""
        args = self._build_pytest_args(vm_id, junit_path, html_path, only_failed)

        env = os.environ.copy()
        # conftest.py читает VM_ID, чтобы понять, к какой ВМ подключаться
        env["VM_ID"] = vm_id
        if self.vm_name_override:
            # Домен из --vm-name вместо vm_name из конфига
            env["VM_NAME_OVERRIDE"] = self.vm_name_override
        env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

        logger.info("[%s] Запуск: %s", vm_id, " ".join(args))
        process = await asyncio.create_subprocess_exec(
            *args, cwd=str(BASE_DIR), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[vm_id] = process

        try:
            stdout, _ = await process.communicate()
        finally:
            self._processes.pop(vm_id, None)

        if stdout:
            for line in stdout.decode(errors="replace").splitlines():
                logger.debug("[%s] %s", vm_id, line)
        return process.returncode

    async def _terminate_all(self) -> None:
        """Terminate every running pytest subprocess, escalating to kill."""
        for vm_id, process in list(self._processes.items()):
            if process.returncode is not None:
                continue
            logger.warning("[%s] Завершение pytest (pid %s)", vm_id, process.pid)
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("[%s] Не отвечает — kill", vm_id)
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

    # --- Разбор результатов -------------------------------------------------

    @staticmethod
    def _parse_junit(junit_path: Path, vm_id: str, attempt: int = 1) -> List[TestResult]:
        """Convert a pytest JUnit XML report into TestResult objects."""
        if not junit_path.exists():
            logger.warning("[%s] Отчёт JUnit не создан: %s", vm_id, junit_path)
            return []

        try:
            tree = ET.parse(junit_path)
        except ET.ParseError as e:
            logger.error("[%s] Повреждён JUnit XML %s: %s", vm_id, junit_path, e)
            return []

        results: List[TestResult] = []
        now = datetime.now().isoformat()

        for case in tree.iter("testcase"):
            name = case.get("name", "unknown")
            classname = case.get("classname", "")
            full_name = f"{classname}::{name}" if classname else name
            duration = float(case.get("time", 0) or 0)

            status, error = STATUS_PASS, None
            if case.find("failure") is not None:
                node = case.find("failure")
                status = STATUS_FAIL
                error = (node.get("message") or node.text or "").strip()[:2000]
            elif case.find("error") is not None:
                node = case.find("error")
                status = STATUS_ERROR
                error = (node.get("message") or node.text or "").strip()[:2000]
            elif case.find("skipped") is not None:
                node = case.find("skipped")
                status = STATUS_SKIP
                error = (node.get("message") or "").strip()[:2000]

            results.append(
                TestResult(
                    test_name=full_name,
                    vm_id=vm_id,
                    status=status,
                    started_at=now,
                    finished_at=now,
                    duration_s=round(duration, 3),
                    error=error,
                    attempt=attempt,
                )
            )
        return results

    # --- Прогон одной ВМ ----------------------------------------------------

    async def run_vm(self, vm_id: str) -> List[TestResult]:
        """Run the suite for one VM, retrying failures up to `retry_count`."""
        report_dir = Path(REPORT_DIR) / vm_id
        report_dir.mkdir(parents=True, exist_ok=True)

        self._emit("vm_started", vm_id=vm_id)
        logger.info("[%s] Проверка перед запуском", vm_id)

        preflight = self.vm_manager.preflight(vm_id, self.vm_name_override)
        for warning in preflight["warnings"]:
            logger.warning("[%s] %s", vm_id, warning)
        if not preflight["ok"]:
            problems = "; ".join(preflight["problems"])
            logger.error("[%s] Проверка не пройдена: %s", vm_id, problems)
            self._emit("vm_failed", vm_id=vm_id, reason=problems)
            now = datetime.now().isoformat()
            return [
                TestResult(
                    test_name=f"{vm_id}::preflight",
                    vm_id=vm_id, status=STATUS_ERROR,
                    started_at=now, finished_at=now,
                    error=f"ВМ не готова к тестированию: {problems}",
                )
            ]

        results: List[TestResult] = []
        for attempt in range(1, self.retry_count + 2):
            if self.emergency.requested:
                logger.warning("[%s] Прогон отменён по аварийной остановке", vm_id)
                break

            junit = report_dir / f"junit_attempt{attempt}.xml"
            html = report_dir / f"report_attempt{attempt}.html"
            only_failed = attempt > 1

            if only_failed:
                logger.info("[%s] Повтор упавших тестов, попытка %d", vm_id, attempt)

            code = await self._run_pytest(vm_id, junit, html, only_failed)
            attempt_results = self._parse_junit(junit, vm_id, attempt)

            if attempt == 1:
                results = attempt_results
            else:
                # Заменяем прежние результаты по имени теста на свежие
                by_name = {r.test_name: r for r in results}
                by_name.update({r.test_name: r for r in attempt_results})
                results = list(by_name.values())

            # exit code 0 = всё прошло, 1 = есть падения, 5 = тесты не найдены
            if code == 0:
                logger.info("[%s] Все тесты прошли (попытка %d)", vm_id, attempt)
                break
            if code == 5:
                logger.warning("[%s] Тесты не найдены в %s", vm_id,
                               self.vm_manager.config_for(vm_id).get("test_path"))
                break
            if not any(r.status in (STATUS_FAIL, STATUS_ERROR) for r in results):
                break

        self._emit("vm_finished", vm_id=vm_id, results=results)
        return results

    # --- Прогон всех ВМ -----------------------------------------------------

    async def run(self, vm_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run the suite across the given VMs and return the run summary."""
        vm_ids = vm_ids or self.vm_manager.enabled_vm_ids()
        if not vm_ids:
            raise VMManagerError(
                "Не выбрано ни одной ВМ. Проверьте enabled в config/vms_config.yaml"
            )

        resources = self.vm_manager.check_host_resources(vm_ids)
        for warning in resources["warnings"]:
            logger.warning("Ресурсы хоста: %s", warning)

        self.emergency.install()
        semaphore = asyncio.Semaphore(self.parallel_workers)
        completed: List[str] = []
        failed_vms: List[str] = []

        async def run_one(vm_id: str) -> List[TestResult]:
            async with semaphore:
                if self.emergency.requested:
                    return []
                try:
                    results = await self.run_vm(vm_id)
                except Exception as e:
                    logger.exception("[%s] Непредвиденная ошибка прогона", vm_id)
                    failed_vms.append(vm_id)
                    now = datetime.now().isoformat()
                    return [
                        TestResult(
                            test_name=f"{vm_id}::runner",
                            vm_id=vm_id, status=STATUS_ERROR,
                            started_at=now, finished_at=now, error=str(e),
                        )
                    ]
                completed.append(vm_id)
                if any(r.status in (STATUS_FAIL, STATUS_ERROR) for r in results):
                    failed_vms.append(vm_id)
                    if self.stop_on_fail:
                        logger.warning(
                            "[%s] Есть падения и включён --stop-on-fail — останавливаем прогон",
                            vm_id,
                        )
                        self.emergency.event.set()
                return results

        tasks = [asyncio.create_task(run_one(vm_id)) for vm_id in vm_ids]
        stop_watcher = asyncio.create_task(self.emergency.event.wait())

        try:
            done, pending = await asyncio.wait(
                [*tasks, stop_watcher], return_when=asyncio.FIRST_COMPLETED
            )
            # Ждём завершения задач, пока не запрошена остановка
            while not self.emergency.requested and any(not t.done() for t in tasks):
                await asyncio.wait(
                    [t for t in tasks if not t.done()] + [stop_watcher],
                    return_when=asyncio.FIRST_COMPLETED,
                )

            if self.emergency.requested:
                await self._terminate_all()
                for task in tasks:
                    if not task.done():
                        task.cancel()

            gathered = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            stop_watcher.cancel()
            self.emergency.restore()

        for item in gathered:
            if isinstance(item, BaseException):
                if not isinstance(item, asyncio.CancelledError):
                    logger.error("Задача завершилась с ошибкой: %s", item)
                continue
            for result in item:
                self.reporter.report_result(result)

        summary = self.reporter.finalize()
        summary["interrupted"] = self.emergency.requested

        if self.emergency.requested:
            self.save_state(
                {
                    "interrupted": True,
                    "requested_vms": vm_ids,
                    "completed_vms": completed,
                    "failed_vms": failed_vms,
                    "pending_vms": [v for v in vm_ids if v not in completed],
                }
            )
        else:
            self.clear_state()

        self._emit("run_finished", summary=summary)
        return summary
