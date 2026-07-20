#!/usr/bin/env python3
"""Pre-flight check for every configured VM.

Verifies libvirt reachability, domain existence, state, QMP socket presence
and guest network leases — everything the test run depends on.

Usage:
    python scripts/check_vms.py
    python scripts/check_vms.py --vm windows
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.libvirt_manager import (
    LibvirtManager,
    LibvirtManagerError,
    LibvirtNotAvailable,
    VMState,
)
from src.vm_manager import VMManager

console = Console()


def main() -> int:
    """Run the pre-flight check. Returns a process exit code."""
    parser = argparse.ArgumentParser(description="Проверка состояния ВМ")
    parser.add_argument("--vm", help="Проверить только одну ВМ (id из конфига)")
    args = parser.parse_args()

    manager = VMManager()

    console.print("[bold]1. Подключение к libvirt[/bold]")
    try:
        manager.libvirt.connect()
        host = manager.libvirt.get_host_info()
        console.print(f"   [green]OK[/green] {manager.libvirt.uri}")
        console.print(
            f"   Хост: {host['hostname']}, CPU x{host['cpus']}, "
            f"память {host['free_memory_mb']}/{host['memory_mb']} МБ свободно"
        )
    except LibvirtNotAvailable as e:
        console.print(f"   [bold red]libvirt не установлен[/bold red]\n{e}")
        return 2
    except LibvirtManagerError as e:
        console.print(f"   [bold red]Нет подключения[/bold red]\n   {e}")
        return 2

    console.print("\n[bold]2. Домены в libvirt[/bold]")
    try:
        domains = manager.libvirt.list_vms()
        if domains:
            for domain in domains:
                console.print(f"   • {domain['name']} — {domain['state'].value}")
        else:
            console.print("   [yellow]Ни одного домена не найдено[/yellow]")
    except LibvirtManagerError as e:
        console.print(f"   [bold red]Ошибка:[/bold red] {e}")
        return 2

    console.print("\n[bold]3. ВМ из конфигурации[/bold]")
    # Только enabled: выключенная в конфиге ВМ — это намеренный выбор, а не
    # проблема готовности. Иначе она и роняет общий вердикт, и добавляет свою
    # память в требуемую по хосту.
    if args.vm:
        vm_ids = [args.vm]
    else:
        vm_ids = manager.enabled_vm_ids()
        skipped = [v for v in manager.all_vm_ids() if v not in vm_ids]
        if skipped:
            console.print(
                f"   [dim]Пропущены (enabled: false): {', '.join(skipped)}[/dim]"
            )

    table = Table(header_style="bold cyan")
    table.add_column("ВМ")
    table.add_column("Домен")
    table.add_column("Состояние")
    table.add_column("QMP-сокет")
    table.add_column("IP")
    table.add_column("Готова")
    table.add_column("Замечания")

    all_ok = True
    for vm_id in vm_ids:
        report = manager.preflight(vm_id)
        vm_name = report.get("vm_name")
        state = report.get("state")

        socket_path = report.get("qmp_socket")
        if not socket_path:
            socket_status = "[red]не задан[/red]"
        elif Path(socket_path).exists():
            socket_status = "[green]есть[/green]"
        elif state is VMState.RUNNING:
            # ВМ работает, но сокета нет — почти всегда забыт qemu:commandline
            socket_status = "[bold red]отсутствует[/bold red]"
        else:
            socket_status = "[dim]ВМ выключена[/dim]"

        ips = "—"
        if vm_name and state is VMState.RUNNING:
            try:
                found = manager.libvirt.get_ip_addresses(vm_name)
                ips = ", ".join(found) if found else "нет аренды"
            except LibvirtManagerError:
                ips = "—"

        ok = report["ok"]
        all_ok = all_ok and ok
        notes = report["problems"] + report["warnings"]
        table.add_row(
            vm_id,
            vm_name or "—",
            state.value if state else "—",
            socket_status,
            ips,
            "[green]да[/green]" if ok else "[bold red]нет[/bold red]",
            "; ".join(notes) if notes else "—",
        )

    console.print(table)

    console.print("\n[bold]4. Ресурсы хоста[/bold]")
    resources = manager.check_host_resources(vm_ids)
    console.print(
        f"   Суммарно требуется ВМ: {resources['required_mb']} МБ"
    )
    for warning in resources["warnings"]:
        console.print(f"   [yellow]{warning}[/yellow]")
    if not resources["warnings"]:
        console.print("   [green]Достаточно[/green]")

    manager.close()

    if all_ok:
        console.print("\n[bold green]Все ВМ готовы к тестированию.[/bold green]")
        return 0
    console.print(
        "\n[bold red]Не все ВМ готовы.[/bold red] "
        "Если отсутствует QMP-сокет — см. README, раздел «Второй QMP-сокет»."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
