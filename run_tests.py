#!/usr/bin/env python3
"""CLI entry point: run UI tests across virt-manager VMs.

Examples:
    python run_tests.py --check                     # проверка ВМ без запуска тестов
    python run_tests.py --os windows                # тесты только для Windows
    python run_tests.py --os all --parallel 3       # все ОС параллельно
    python run_tests.py --os windows --kiwi         # с отправкой в Kiwi TCMS
    python run_tests.py --restart                   # доделать прерванный прогон
    python run_tests.py --menu                      # интерактивное меню управления ВМ
    python run_tests.py --console windows           # отдельная консоль: интерактивный
                                                    # прогон тестов Windows с паузой
                                                    # при падении теста
    python run_tests.py --session windows           # то же, но в текущем окне
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table

from config.settings import PARALLEL_WORKERS, REPORT_DIR, RETRY_COUNT
from src.kiwi_reporter import KiwiReporter
from src.libvirt_manager import LibvirtManagerError, LibvirtNotAvailable
from src.logging_setup import setup_logging
from src.test_runner import TestRunner
from src.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)
console = Console()


def resolve_vm_ids(os_arg: str, manager: VMManager) -> List[str]:
    """Translate the --os argument into a list of VM ids.

    Raises:
        VMManagerError: an unknown OS was requested.
    """
    if os_arg == "all":
        vm_ids = manager.enabled_vm_ids()
        if not vm_ids:
            raise VMManagerError(
                "Нет ни одной ВМ с enabled: true в config/vms_config.yaml"
            )
        return vm_ids

    requested = [name.strip() for name in os_arg.split(",") if name.strip()]
    known = manager.all_vm_ids()
    unknown = [name for name in requested if name not in known]
    if unknown:
        raise VMManagerError(
            f"Неизвестные ОС: {', '.join(unknown)}. Доступны: {', '.join(known)}"
        )
    return requested


def print_check(
    manager: VMManager, vm_ids: List[str], vm_name_override: Optional[str] = None
) -> bool:
    """Print a pre-flight table for the given VMs. Returns True if all are ok."""
    table = Table(title="Проверка готовности ВМ", header_style="bold cyan")
    table.add_column("ВМ")
    table.add_column("Домен в libvirt")
    table.add_column("Состояние")
    table.add_column("Готова")
    table.add_column("Замечания")

    all_ok = True
    for vm_id in vm_ids:
        report = manager.preflight(vm_id, vm_name_override)
        ok = report["ok"]
        all_ok = all_ok and ok
        notes = report["problems"] + report["warnings"]
        state = report.get("state")
        table.add_row(
            vm_id,
            report.get("vm_name") or "—",
            state.value if state else "—",
            "[green]да[/green]" if ok else "[bold red]нет[/bold red]",
            "; ".join(notes) if notes else "—",
        )
    console.print(table)

    resources = manager.check_host_resources(vm_ids)
    if resources.get("host_total_mb"):
        console.print(
            f"Ресурсы хоста: требуется {resources['required_mb']} МБ, "
            f"свободно {resources['host_free_mb']} МБ "
            f"из {resources['host_total_mb']} МБ"
        )
    for warning in resources["warnings"]:
        console.print(f"[yellow]Внимание:[/yellow] {warning}")
    return all_ok


def print_summary(summary: dict) -> None:
    """Print the run summary table."""
    totals = summary["totals"]
    table = Table(title=summary["run_name"], header_style="bold cyan")
    table.add_column("ВМ")
    table.add_column("Всего", justify="right")
    table.add_column("Прошло", justify="right", style="green")
    table.add_column("Упало", justify="right", style="red")
    table.add_column("Ошибки", justify="right", style="red")
    table.add_column("Пропущено", justify="right", style="dim")

    for vm_id, stats in summary["by_vm"].items():
        table.add_row(
            vm_id, str(stats["total"]), str(stats["passed"]),
            str(stats["failed"]), str(stats["error"]), str(stats["skipped"]),
        )
    table.add_section()
    table.add_row(
        "[bold]ИТОГО[/bold]", str(totals["total"]), str(totals["passed"]),
        str(totals["failed"]), str(totals["error"]), str(totals["skipped"]),
    )
    console.print(table)
    console.print(f"Отчёты: {REPORT_DIR}")

    if summary.get("interrupted"):
        console.print(
            "[yellow]Прогон прерван. Продолжить: "
            "python run_tests.py --restart[/yellow]"
        )


async def run(args: argparse.Namespace) -> int:
    """Execute the requested action. Returns a process exit code."""
    manager = VMManager()

    try:
        vm_ids = resolve_vm_ids(args.os, manager)
    except VMManagerError as e:
        console.print(f"[bold red]Ошибка:[/bold red] {e}")
        return 2

    if args.vm_name:
        if len(vm_ids) != 1:
            console.print(
                "[bold red]Ошибка:[/bold red] --vm-name применим только к одной ОС "
                "(укажите --os windows, а не --os all)"
            )
            return 2
        console.print(
            f"Переопределение домена: '{vm_ids[0]}' -> '{args.vm_name}'"
        )

    if args.restart:
        state = TestRunner.load_state()
        if not state:
            console.print("[yellow]Нет сохранённого состояния — обычный прогон.[/yellow]")
        else:
            pending = state.get("pending_vms") or state.get("failed_vms") or []
            if pending:
                console.print(f"Возобновление прогона: {', '.join(pending)}")
                vm_ids = pending
            else:
                console.print("[yellow]В сохранённом состоянии нет незавершённых ВМ.[/yellow]")

    if args.check:
        return 0 if print_check(manager, vm_ids, args.vm_name) else 1

    if not print_check(manager, vm_ids, args.vm_name):
        console.print(
            "[bold red]Не все ВМ готовы.[/bold red] Исправьте замечания выше "
            "или запустите с --check для подробностей."
        )
        return 1

    reporter = KiwiReporter(enabled=args.kiwi and not args.local)
    runner = TestRunner(
        vm_manager=manager,
        reporter=reporter,
        parallel_workers=args.parallel,
        stop_on_fail=args.stop_on_fail,
        retry_count=0 if args.no_retry else args.retry,
        vm_name_override=args.vm_name,
    )

    runner.add_listener(
        lambda event, payload: console.print(
            f"[dim]{event}: {payload.get('vm_id', '')}[/dim]"
        )
        if event in ("vm_started", "vm_finished")
        else None
    )

    console.print(f"\nЗапуск тестов: {', '.join(vm_ids)} "
                  f"(параллельно до {args.parallel} ВМ)\n")
    summary = await runner.run(vm_ids)
    console.print()
    print_summary(summary)

    totals = summary["totals"]
    if summary.get("interrupted"):
        return 130
    return 1 if (totals["failed"] or totals["error"]) else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Запуск UI-тестов на виртуальных машинах virt-manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--os", default="all",
        help="ОС для тестирования: windows | astra | macos | all | "
             "список через запятую (по умолчанию: all)",
    )
    parser.add_argument(
        "--parallel", type=int, default=PARALLEL_WORKERS,
        help=f"Максимум одновременно тестируемых ВМ (по умолчанию: {PARALLEL_WORKERS})",
    )
    parser.add_argument(
        "--stop-on-fail", action="store_true",
        help="Остановить весь прогон при первом падении",
    )
    parser.add_argument(
        "--restart", action="store_true",
        help="Продолжить прерванный прогон с недоделанных ВМ",
    )
    parser.add_argument(
        "--retry", type=int, default=RETRY_COUNT,
        help=f"Попыток перезапуска упавших тестов (по умолчанию: {RETRY_COUNT})",
    )
    parser.add_argument(
        "--no-retry", action="store_true",
        help="Не перезапускать упавшие тесты",
    )
    parser.add_argument(
        "--kiwi", action="store_true",
        help="Включить интеграцию с Kiwi TCMS (сейчас заглушка)",
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Локальный режим: только логи и отчёты, без Kiwi (перекрывает --kiwi)",
    )
    parser.add_argument(
        "--vm-name",
        help="Имя домена в virt-manager, если отличается от указанного в конфиге",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Только проверить готовность ВМ, тесты не запускать",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Показать ВМ из конфига и выйти",
    )
    parser.add_argument(
        "--menu", action="store_true",
        help="Открыть интерактивное меню управления ВМ",
    )
    parser.add_argument(
        "--console", metavar="ВМ",
        help="Открыть отдельную консоль с интерактивным прогоном тестов этой ВМ",
    )
    parser.add_argument(
        "--session", metavar="ВМ",
        help="Провести интерактивный сеанс тестов в ТЕКУЩЕЙ консоли "
             "(так лаунчер запускает сеанс внутри открытого окна)",
    )
    parser.add_argument(
        "--log-level", default=None,
        help="Уровень логирования: DEBUG | INFO | WARNING | ERROR",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    args = build_parser().parse_args()
    setup_logging(level=args.log_level)

    if args.session:
        from src.session_console import run_console_session

        return run_console_session(args.session, args.vm_name)

    if args.console:
        from src.console_launcher import ConsoleLauncherError, launch_console

        try:
            console.print(f"[green]OK[/green] {launch_console(args.console, args.vm_name)}")
        except ConsoleLauncherError as e:
            console.print(f"[bold red]Ошибка:[/bold red] {e}")
            return 2
        return 0

    if args.menu:
        from src.vm_menu import VMMenu

        return VMMenu().run()

    if args.list:
        manager = VMManager()
        table = Table(title="ВМ в конфигурации", header_style="bold cyan")
        table.add_column("ID")
        table.add_column("Домен в virt-manager")
        table.add_column("ОС")
        table.add_column("Включена")
        table.add_column("Тесты")
        for vm_id in manager.all_vm_ids():
            config = manager.config_for(vm_id)
            table.add_row(
                vm_id,
                config.get("vm_name", "—"),
                config.get("os_type", "—"),
                "да" if config.get("enabled") else "нет",
                config.get("test_path", "—"),
            )
        console.print(table)
        return 0

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
        return 130
    except LibvirtNotAvailable as e:
        console.print(f"[bold red]libvirt не установлен:[/bold red]\n{e}")
        return 2
    except (LibvirtManagerError, VMManagerError) as e:
        console.print(f"[bold red]Ошибка:[/bold red] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
