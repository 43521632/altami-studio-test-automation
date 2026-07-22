"""Pytest-плагин интерактивного прогона: статусы в реальном времени и пауза
при падении теста.

Плагин работает внутри процесса pytest — только он владеет терминалом консоли
и может спрашивать пользователя, пока идёт прогон. Подключается флагом
``-p src.interactive_plugin`` (это делает src/session_console.py) и требует
запуска pytest с ``-s``: без него stdin у теста подменён и меню не прочитает
ответ.

Поведение:
    * тесты идут строго последовательно, после каждого печатается
      PASSED / FAILED / SKIPPED и ID кейса из src/case_ids.py;
    * при FAILED прогон встаёт на паузу и предлагает: перезапустить тест
      или пропустить его (тест уйдёт в отчёт как SKIPPED).
"""

import logging
import sys
from typing import List, Optional

import pytest
from _pytest.runner import runtestprotocol
from rich.console import Console

from src.case_ids import case_id_for

logger = logging.getLogger(__name__)
console = Console()

PASSED, FAILED, SKIPPED = "PASSED", "FAILED", "SKIPPED"

_STATUS_STYLE = {
    PASSED: "bold green",
    FAILED: "bold red",
    SKIPPED: "bold yellow",
}


class InteractiveRunControl:
    """Sequential test protocol with a pause-and-choose menu on failure."""

    def __init__(self) -> None:
        # Тесты, пропущенные вручную: нужны для итогов в консоли
        self.manually_skipped: List[str] = []
        self.restarted: List[str] = []

    # --- Служебное ----------------------------------------------------------

    @staticmethod
    def _label(item: pytest.Item) -> str:
        """Human-readable test name with its case id, when mapped."""
        case_id = case_id_for(item.nodeid)
        return f"{item.nodeid}" + (f"  [magenta]({case_id})[/magenta]" if case_id else "")

    @staticmethod
    def _outcome(reports) -> str:
        """Collapse setup/call/teardown reports into a single status."""
        if any(r.failed for r in reports):
            return FAILED
        if any(r.skipped for r in reports):
            return SKIPPED
        return PASSED

    def _print_status(self, item: pytest.Item, status: str) -> None:
        """Print the real-time status line for one finished test."""
        style = _STATUS_STYLE[status]
        console.print(f"[{style}]{status:<8}[/{style}] {self._label(item)}")

    @staticmethod
    def _print_failure(reports) -> None:
        """Print the tail of the traceback so the failure is diagnosable in place."""
        for report in reports:
            if not report.failed:
                continue
            text = (report.longreprtext or "").strip()
            if text:
                tail = text.splitlines()[-12:]
                console.print("[dim]" + "\n".join(tail) + "[/dim]")

    def pytest_report_teststatus(self, report):
        """Silence pytest's own progress marks — статус печатает плагин.

        Категорию оставляем прежней, чтобы итоговая статистика pytest не
        разъехалась; пустыми делаем только букву прогресса и слово.
        """
        if report.when == "call" or report.skipped:
            return report.outcome, "", ""
        return None

    @staticmethod
    def _log(item: pytest.Item, reports) -> None:
        """Hand the accepted attempt to pytest: terminal summary, JUnit, HTML."""
        for report in reports:
            item.ihook.pytest_runtest_logreport(report=report)

    # --- Меню при падении ---------------------------------------------------

    def _ask_on_failure(self, item: pytest.Item) -> str:
        """Block until the user chooses what to do with a failed test.

        Returns "restart" or "skip". Если stdin недоступен (не tty), считаем
        выбор «пропустить» — иначе прогон повис бы навсегда.
        """
        console.print(
            f"\n[bold yellow]ПАУЗА:[/bold yellow] тест упал. Можно подправить "
            f"состояние ВМ вручную, затем выбрать действие."
        )
        console.print("  [bold]1[/bold] — перезапустить тест")
        console.print("  [bold]2[/bold] — пропустить тест (SKIPPED) и идти дальше")

        if not sys.stdin or not sys.stdin.isatty():
            console.print("[dim]Терминал недоступен — тест пропущен.[/dim]")
            return "skip"

        while True:
            try:
                choice = input("Действие [1/2]: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Ввод прерван — тест пропущен.[/dim]")
                return "skip"
            if choice == "1":
                return "restart"
            if choice == "2":
                return "skip"
            console.print("[yellow]Введите 1 или 2.[/yellow]")

    # --- Протокол одного теста ----------------------------------------------

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem) -> Optional[bool]:
        """Run one test, pausing for a decision whenever it fails."""
        attempt = 0
        while True:
            attempt += 1
            if attempt > 1:
                # Без сброса запроса фикстур повтор падает на кэше прошлой попытки
                if hasattr(item, "_initrequest"):
                    item._initrequest()
                console.print(f"[cyan]Перезапуск (попытка {attempt}):[/cyan] {item.nodeid}")

            reports = runtestprotocol(item, nextitem=nextitem, log=False)
            status = self._outcome(reports)

            if status != FAILED:
                self._print_status(item, status)
                self._log(item, reports)
                return True

            self._print_status(item, FAILED)
            self._print_failure(reports)

            if self._ask_on_failure(item) == "restart":
                self.restarted.append(item.nodeid)
                continue

            self.manually_skipped.append(item.nodeid)
            self._run_as_skipped(item, nextitem)
            return True

    def _run_as_skipped(self, item: pytest.Item, nextitem) -> None:
        """Re-run the item as skipped so reports and JUnit XML say SKIPPED."""
        item.add_marker(pytest.mark.skip(reason="Пропущен пользователем после падения"))
        if hasattr(item, "_initrequest"):
            item._initrequest()
        reports = runtestprotocol(item, nextitem=nextitem, log=True)
        self._print_status(item, self._outcome(reports))


def pytest_configure(config: pytest.Config) -> None:
    """Register the plugin when pytest is started with -p src.interactive_plugin."""
    config.pluginmanager.register(InteractiveRunControl(), "interactive-run-control")
