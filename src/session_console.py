"""Тестовый сеанс одной ВМ — то, что работает внутри отдельной консоли.

Запускается лаунчером (src/console_launcher.py) как
``python run_tests.py --session <vm_id>``.

Сеанс: берёт замок ВМ (вторая консоль на ту же ВМ не откроется), гоняет тесты
этой ОС строго последовательно, показывает статусы в реальном времени, а по
завершении печатает «All done», итоги и меню: перезапустить весь набор или
завершить. Окно после завершения не закрывается — лог остаётся перед глазами.
"""

import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import BASE_DIR, REPORT_DIR, TEST_TIMEOUT
from src.vm_lock import VMLock, VMLockBusy
from src.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)
console = Console()


def _pytest_args(vm_id: str, test_path: str, junit: Path) -> list:
    """Command line for one interactive pytest run."""
    return [
        sys.executable, "-m", "pytest",
        test_path,
        # -s обязателен: без него меню при падении не прочитает ответ из stdin
        "-s",
        "-q",
        "--no-header",
        # Плагин печатает PASSED/FAILED/SKIPPED и ставит паузу при падении
        "-p", "src.interactive_plugin",
        # Внутри одной ВМ параллелить нельзя — гость один
        "-p", "no:xdist",
        f"--junitxml={junit}",
        f"--timeout={TEST_TIMEOUT}",
        "--tb=no",
    ]


def _run_pytest(vm_id: str, junit: Path, vm_name_override: Optional[str]) -> int:
    """Run the suite for one VM in this terminal. Returns pytest's exit code."""
    config = VMManager().config_for(vm_id)
    test_path = config.get("test_path") or f"./tests/{vm_id}"

    env = os.environ.copy()
    env["VM_ID"] = vm_id
    if vm_name_override:
        env["VM_NAME_OVERRIDE"] = vm_name_override
    env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    args = _pytest_args(vm_id, test_path, junit)
    logger.info("[%s] Запуск: %s", vm_id, " ".join(args))
    # stdin/stdout наследуются — иначе плагин не сможет спросить пользователя
    return subprocess.run(args, cwd=str(BASE_DIR), env=env).returncode


def _summary(junit: Path) -> Dict[str, int]:
    """Count outcomes in the JUnit report of the last run."""
    totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    if not junit.exists():
        return totals
    try:
        tree = ET.parse(junit)
    except ET.ParseError as e:
        logger.error("Повреждён JUnit XML %s: %s", junit, e)
        return totals

    for case in tree.iter("testcase"):
        totals["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            totals["failed"] += 1
        elif case.find("skipped") is not None:
            totals["skipped"] += 1
        else:
            totals["passed"] += 1
    return totals


def _print_summary(vm_id: str, totals: Dict[str, int], junit: Path) -> None:
    """Print the end-of-run table."""
    table = Table(title=f"Итоги прогона: {vm_id}", header_style="bold cyan")
    table.add_column("Всего", justify="right")
    table.add_column("PASSED", justify="right", style="green")
    table.add_column("FAILED", justify="right", style="red")
    table.add_column("SKIPPED", justify="right", style="yellow")
    table.add_row(
        str(totals["total"]), str(totals["passed"]),
        str(totals["failed"]), str(totals["skipped"]),
    )
    console.print(table)
    console.print(f"[dim]Отчёт: {junit}[/dim]")


def _final_menu() -> str:
    """Ask what to do after the whole suite finished. Returns "restart"|"finish"."""
    console.print("\n[bold]Что дальше?[/bold]")
    console.print("  [bold]1[/bold] — перезапустить все тесты на этой ВМ")
    console.print("  [bold]2[/bold] — завершить работу (окно останется открытым)")

    if not sys.stdin or not sys.stdin.isatty():
        return "finish"

    while True:
        try:
            choice = input("Действие [1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "finish"
        if choice == "1":
            return "restart"
        if choice == "2":
            return "finish"
        console.print("[yellow]Введите 1 или 2.[/yellow]")


def _hold_window() -> None:
    """Keep the console open so the user can read the log at their own pace."""
    console.print(
        "\n[dim]Сеанс завершён. Окно оставлено открытым — закройте его вручную, "
        "когда изучите лог.[/dim]"
    )
    try:
        while True:
            input()
    except (EOFError, KeyboardInterrupt):
        pass


def _print_preflight(vm_id: str, vm_name_override: Optional[str]) -> None:
    """Warn about VM problems before the run, without blocking it."""
    try:
        report = VMManager().preflight(vm_id, vm_name_override)
    except VMManagerError as e:
        console.print(f"[yellow]Проверка ВМ не выполнена:[/yellow] {e}")
        return
    for problem in report["problems"]:
        console.print(f"[bold red]Проблема:[/bold red] {problem}")
    for warning in report["warnings"]:
        console.print(f"[yellow]Внимание:[/yellow] {warning}")


def run_console_session(vm_id: str, vm_name_override: Optional[str] = None) -> int:
    """Run the interactive test session for one VM. Returns a process exit code."""
    try:
        VMManager().config_for(vm_id)
    except VMManagerError as e:
        # Ошибку показываем в самом окне: иначе консоль закроется быстрее, чем
        # её успеют прочитать
        console.print(Panel(str(e), title="[bold red]Ошибка[/bold red]",
                            border_style="red"))
        _hold_window()
        return 2

    try:
        lock = VMLock(vm_id).acquire()
    except VMLockBusy as e:
        console.print(Panel(str(e), title="[bold red]ВМ занята[/bold red]",
                            border_style="red"))
        _hold_window()
        return 2

    report_dir = Path(REPORT_DIR) / vm_id
    report_dir.mkdir(parents=True, exist_ok=True)
    last_totals: Dict[str, int] = {}

    try:
        run = 0
        while True:
            run += 1
            console.print(
                Panel(
                    f"ВМ: [bold]{vm_id}[/bold]\n"
                    f"Прогон №{run}, старт {datetime.now():%H:%M:%S}\n"
                    "Тесты идут последовательно. При падении — пауза и выбор "
                    "действия.",
                    title="[bold cyan]Тестовый сеанс[/bold cyan]",
                    border_style="cyan",
                )
            )
            _print_preflight(vm_id, vm_name_override)

            junit = report_dir / f"junit_console_run{run}.xml"
            _run_pytest(vm_id, junit, vm_name_override)

            console.print("\n[bold green]All done[/bold green]")
            last_totals = _summary(junit)
            _print_summary(vm_id, last_totals, junit)

            if _final_menu() == "finish":
                break
    except KeyboardInterrupt:
        console.print("\n[yellow]Сеанс прерван пользователем[/yellow]")
    finally:
        # Замок снимаем до ожидания: ВМ свободна, окно живёт только ради лога
        lock.release()

    _hold_window()
    return 1 if last_totals.get("failed") else 0
