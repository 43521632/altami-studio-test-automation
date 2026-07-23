"""Interactive terminal menu for managing virt-manager VMs via libvirt.

Run standalone:
    python -m src.vm_menu
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from config.settings import SCREENSHOT_DIR, get_all_vm_ids, get_vm_config
from src.libvirt_manager import (
    LibvirtManager,
    LibvirtManagerError,
    LibvirtNotAvailable,
    VMState,
)

logger = logging.getLogger(__name__)
console = Console()

# Цвет строки состояния в таблице
_STATE_STYLE = {
    VMState.RUNNING: "bold green",
    VMState.PAUSED: "yellow",
    VMState.SHUTOFF: "dim",
    VMState.CRASHED: "bold red",
    VMState.NOT_FOUND: "bold red",
}


class VMMenu:
    """Rich-based interactive menu over :class:`LibvirtManager`."""

    def __init__(self, manager: Optional[LibvirtManager] = None) -> None:
        self.manager = manager or LibvirtManager()

    # --- Отображение -----------------------------------------------------

    def _state_text(self, state: VMState) -> str:
        style = _STATE_STYLE.get(state, "white")
        return f"[{style}]{state.value}[/{style}]"

    def show_vms(self) -> List[str]:
        """Print a table of all libvirt domains. Returns their names."""
        try:
            vms = self.manager.list_vms()
        except LibvirtManagerError as e:
            console.print(f"[bold red]Ошибка:[/bold red] {e}")
            return []

        if not vms:
            console.print("[yellow]В libvirt нет ни одной ВМ.[/yellow]")
            console.print("Создайте ВМ в virt-manager, затем вернитесь сюда.")
            return []

        # Обратная карта: имя домена -> id из конфига, чтобы показать привязку
        name_to_id = {
            get_vm_config(vm_id).get("vm_name"): vm_id for vm_id in get_all_vm_ids()
        }

        table = Table(title="Виртуальные машины (libvirt)", header_style="bold cyan")
        table.add_column("#", justify="right", width=3)
        table.add_column("Имя в virt-manager", style="bold")
        table.add_column("Состояние")
        table.add_column("ID", justify="right", width=5)
        table.add_column("В конфиге", style="magenta")

        for idx, vm in enumerate(vms, 1):
            table.add_row(
                str(idx),
                vm["name"],
                self._state_text(vm["state"]),
                str(vm["id"]) if vm["id"] is not None else "—",
                name_to_id.get(vm["name"], "—"),
            )

        console.print(table)

        # Предупреждаем о ВМ из конфига, которых нет в libvirt — частая причина падений
        missing = [
            f"{vm_id} -> '{name}'"
            for name, vm_id in name_to_id.items()
            if name and name not in {vm["name"] for vm in vms}
        ]
        if missing:
            console.print(
                Panel(
                    "\n".join(missing),
                    title="[yellow]Есть в vms_config.yaml, но не найдены в libvirt[/yellow]",
                    border_style="yellow",
                )
            )
        return [vm["name"] for vm in vms]

    def show_status(self, vm_name: str) -> None:
        """Print a detailed status panel for one domain."""
        info = self.manager.status(vm_name)
        if not info.get("exists"):
            console.print(f"[bold red]ВМ '{vm_name}' не найдена в libvirt[/bold red]")
            return

        lines = [
            f"Состояние:   {info['state'].value}",
            f"UUID:        {info.get('uuid', '—')}",
            f"Домен ID:    {info.get('id', '—')}",
            f"Память:      {info.get('memory_mb', '—')} / {info.get('max_memory_mb', '—')} МБ",
            f"vCPU:        {info.get('vcpus', '—')}",
            f"CPU time:    {info.get('cpu_time_s', '—')} с",
            f"Автозапуск:  {'да' if info.get('autostart') else 'нет'}",
        ]
        if info["state"] is VMState.RUNNING:
            ips = self.manager.get_ip_addresses(vm_name)
            lines.append(f"IP-адреса:   {', '.join(ips) if ips else 'нет DHCP-аренды'}")
        if info.get("error"):
            lines.append(f"[yellow]Предупреждение: {info['error']}[/yellow]")

        console.print(Panel("\n".join(lines), title=f"[bold]{vm_name}[/bold]", border_style="cyan"))

    def show_host(self) -> None:
        """Print libvirt host capacity info."""
        try:
            info = self.manager.get_host_info()
        except LibvirtManagerError as e:
            console.print(f"[bold red]Ошибка:[/bold red] {e}")
            return
        console.print(
            Panel(
                "\n".join(
                    [
                        f"Хост:            {info['hostname']}",
                        f"CPU:             {info['cpu_model']} x{info['cpus']} @ {info['cpu_mhz']} МГц",
                        f"Память всего:    {info['memory_mb']} МБ",
                        f"Память свободно: {info['free_memory_mb']} МБ",
                        f"Версия libvirt:  {info['libvirt_version']}",
                    ]
                ),
                title="[bold]Хост-система[/bold]",
                border_style="green",
            )
        )

    # --- Выбор ВМ --------------------------------------------------------

    def select_vms(self, vm_names: List[str], allow_multiple: bool = True) -> List[str]:
        """Prompt for VM selection by number.

        Accepts "1", "1,3", or "all". Returns the chosen domain names.
        """
        if not vm_names:
            return []
        hint = "номера через запятую или 'all'" if allow_multiple else "номер"
        raw = Prompt.ask(f"Выберите ВМ ({hint}), Enter — отмена", default="").strip()
        if not raw:
            return []
        if allow_multiple and raw.lower() in ("all", "все", "*"):
            return list(vm_names)

        selected: List[str] = []
        for token in raw.split(","):
            token = token.strip()
            if not token.isdigit():
                console.print(f"[yellow]Пропущено (не число): '{token}'[/yellow]")
                continue
            idx = int(token)
            if 1 <= idx <= len(vm_names):
                name = vm_names[idx - 1]
                if name not in selected:
                    selected.append(name)
            else:
                console.print(f"[yellow]Номер вне диапазона: {idx}[/yellow]")
            if not allow_multiple and selected:
                break
        return selected

    # --- Действия --------------------------------------------------------

    def _apply(self, vm_names: List[str], action: str, **kwargs) -> None:
        """Run a manager action over several VMs, reporting each outcome."""
        for name in vm_names:
            try:
                with console.status(f"[cyan]{action} '{name}'...[/cyan]"):
                    ok = getattr(self.manager, action)(name, **kwargs)
                if ok:
                    console.print(f"[green]OK[/green] {name}: {action} выполнено")
                else:
                    console.print(
                        f"[yellow]ВНИМАНИЕ[/yellow] {name}: {action} завершилось без подтверждения "
                        f"(возможен таймаут ожидания состояния)"
                    )
            except LibvirtManagerError as e:
                console.print(f"[bold red]ОШИБКА[/bold red] {name}: {e}")

    def action_start(self) -> None:
        """Menu action: start selected VMs."""
        names = self.select_vms(self.show_vms())
        if not names:
            return
        wait = Confirm.ask("Дождаться перехода в состояние 'работает'?", default=True)
        self._apply(names, "start", wait=wait)

    def action_stop(self) -> None:
        """Menu action: stop selected VMs (graceful, with optional force)."""
        names = self.select_vms(self.show_vms())
        if not names:
            return
        force = Confirm.ask(
            "Принудительное выключение (destroy, без ACPI)?", default=False
        )
        if force and not Confirm.ask(
            f"[bold red]Данные в гостевой ОС могут быть потеряны. Продолжить?[/bold red]",
            default=False,
        ):
            console.print("Отменено.")
            return
        self._apply(names, "stop", force=force)

    def action_restart(self) -> None:
        """Menu action: restart selected VMs."""
        names = self.select_vms(self.show_vms())
        if not names:
            return
        self._apply(names, "restart")

    def action_status(self) -> None:
        """Menu action: show detailed status for selected VMs."""
        for name in self.select_vms(self.show_vms()):
            self.show_status(name)

    def action_screenshot(self) -> None:
        """Menu action: capture console screenshots of selected VMs."""
        names = self.select_vms(self.show_vms())
        for name in names:
            # Имя файла без timestamp — здесь это ручной снимок для отладки/эталона
            out = Path(SCREENSHOT_DIR) / f"{name}_manual.png"
            try:
                self.manager.screenshot(name, out)
                console.print(f"[green]OK[/green] {name}: скриншот -> {out}")
            except LibvirtManagerError as e:
                console.print(f"[bold red]ОШИБКА[/bold red] {name}: {e}")

    # --- Запуск тестов ---------------------------------------------------

    def _show_test_targets(self) -> List[str]:
        """Print the VMs available for testing. Returns their config ids."""
        from src.vm_lock import is_busy

        vm_ids = [
            vm_id for vm_id in get_all_vm_ids()
            if get_vm_config(vm_id).get("enabled")
        ]
        if not vm_ids:
            console.print(
                "[yellow]Нет ни одной ВМ с enabled: true в "
                "config/vms_config.yaml[/yellow]"
            )
            return []

        table = Table(title="ВМ для тестирования", header_style="bold cyan")
        table.add_column("#", justify="right", width=3)
        table.add_column("ВМ", style="bold")
        table.add_column("Домен в virt-manager")
        table.add_column("Тесты")
        table.add_column("Консоль")

        for idx, vm_id in enumerate(vm_ids, 1):
            config = get_vm_config(vm_id)
            busy = is_busy(vm_id)
            table.add_row(
                str(idx),
                vm_id,
                config.get("vm_name", "—"),
                config.get("test_path", "—"),
                "[yellow]уже открыта[/yellow]" if busy else "[green]свободна[/green]",
            )
        console.print(table)
        return vm_ids

    def action_run_tests(self) -> None:
        """Menu action: open a dedicated test console per selected VM.

        Одна ВМ — одна консоль. Разные ВМ можно гонять параллельно, каждую в
        своём окне.
        """
        from src.console_launcher import ConsoleLauncherError, launch_console

        vm_ids = self._show_test_targets()
        if not vm_ids:
            return
        for vm_id in self.select_vms(vm_ids):
            try:
                console.print(f"[green]OK[/green] {launch_console(vm_id)}")
            except ConsoleLauncherError as e:
                console.print(f"[bold red]ОШИБКА[/bold red] {vm_id}: {e}")

    def _show_cases(self, vm_id: str) -> List[Tuple[str, str]]:
        """Print the tests of one VM that have a case id. Returns (id, nodeid)."""
        from src.case_ids import mapped_cases

        test_path = get_vm_config(vm_id).get("test_path") or f"tests/{vm_id}"
        cases = mapped_cases(test_path)
        if not cases:
            console.print(
                f"[yellow]У ВМ '{vm_id}' нет ни одного теста с проставленным ID.[/yellow]\n"
                f"ID кейсов из Kiwi TCMS проставляются вручную в "
                f"[bold]src/case_ids.py[/bold] — тест без ID сюда не попадёт."
            )
            return []

        table = Table(title=f"Тесты с ID — {vm_id}", header_style="bold cyan")
        table.add_column("#", justify="right", width=3)
        table.add_column("ID кейса", style="bold magenta")
        table.add_column("Тест")
        table.add_column("Файл", style="dim")

        for idx, (case_id, nodeid) in enumerate(cases, 1):
            path, _, name = nodeid.partition("::")
            table.add_row(str(idx), case_id, name.replace("::", " → "), path)
        console.print(table)
        return cases

    def action_dev_test(self) -> None:
        """Menu action: run ONE test by case id on ONE VM, in this console.

        Режим разработки очередного теста. Регрессия гоняет цепочку целиком,
        и состояние каждому тесту достаётся от предыдущего — но прогонять всю
        цепочку ради состояния для нового теста избыточно. Здесь состояние ВМ
        готовит пользователь (снапшот, клики руками), а мы запускаем ровно
        один тест поверх готового состояния и НИЧЕГО не проверяем до него.

        Запуск идёт в этой же консоли, а не в отдельном окне: при разработке
        вывод теста нужен здесь и сейчас, рядом с правками.
        """
        from src.dev_run import run_single_case

        vm_ids = self._show_test_targets()
        if not vm_ids:
            return
        selected = self.select_vms(vm_ids, allow_multiple=False)
        if not selected:
            return
        vm_id = selected[0]

        console.print()
        cases = self._show_cases(vm_id)
        if not cases:
            return

        raw = Prompt.ask(
            "Выберите тест (номер или ID кейса), Enter — отмена", default=""
        ).strip()
        if not raw:
            return

        if raw.isdigit() and 1 <= int(raw) <= len(cases):
            case_id = cases[int(raw) - 1][0]
        else:
            wanted = raw.upper()
            match = next((cid for cid, _ in cases if cid.upper() == wanted), None)
            if not match:
                console.print(f"[yellow]Нет теста с номером или ID '{raw}'[/yellow]")
                return
            case_id = match

        console.print(
            Panel(
                f"ВМ: [bold]{vm_id}[/bold]\nКейс: [bold magenta]{case_id}[/bold magenta]\n\n"
                "[yellow]Состояние ВМ не проверяется[/yellow] — тест пойдёт "
                "поверх того, что сейчас на машине.",
                title="[bold cyan]Режим разработчика[/bold cyan]",
                border_style="cyan",
            )
        )
        code = run_single_case(vm_id, case_id)
        style = "green" if code == 0 else "bold red"
        console.print(f"[{style}]pytest завершился с кодом {code}[/{style}]")

    # --- Главный цикл ----------------------------------------------------

    _ACTIONS = [
        ("1", "Список ВМ", "show_vms"),
        ("2", "Статус ВМ", "action_status"),
        ("3", "Запустить ВМ", "action_start"),
        ("4", "Остановить ВМ", "action_stop"),
        ("5", "Перезапустить ВМ", "action_restart"),
        ("6", "Скриншот ВМ", "action_screenshot"),
        ("7", "Информация о хосте", "show_host"),
        ("8", "Запустить тесты (отдельная консоль на ВМ)", "action_run_tests"),
        ("9", "Режим разработчика: один тест по ID кейса", "action_dev_test"),
        ("0", "Выход", None),
    ]

    def show_menu(self) -> None:
        """Print the main menu."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        for key, label, _ in self._ACTIONS:
            table.add_row(f"[bold cyan]{key}[/bold cyan]", label)
        console.print(Panel(table, title="[bold]Менеджер ВМ (libvirt)[/bold]", border_style="cyan"))

    def run(self) -> int:
        """Run the interactive loop. Returns a process exit code."""
        try:
            self.manager.connect()
        except LibvirtNotAvailable as e:
            console.print(Panel(str(e), title="[bold red]libvirt не установлен[/bold red]",
                                border_style="red"))
            return 2
        except LibvirtManagerError as e:
            console.print(Panel(str(e), title="[bold red]Нет подключения к libvirt[/bold red]",
                                border_style="red"))
            return 2

        console.print(f"[green]Подключено к libvirt:[/green] {self.manager.uri}\n")
        handlers = {key: name for key, _, name in self._ACTIONS}

        try:
            while True:
                self.show_menu()
                choice = Prompt.ask("Действие", choices=list(handlers), default="1")
                if choice == "0":
                    break
                console.print()
                try:
                    getattr(self, handlers[choice])()
                except LibvirtManagerError as e:
                    console.print(f"[bold red]Ошибка libvirt:[/bold red] {e}")
                console.print()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Прервано пользователем[/yellow]")
        finally:
            self.manager.close()

        console.print("[dim]Соединение с libvirt закрыто.[/dim]")
        return 0


def main() -> int:
    """Entry point for `python -m src.vm_menu`."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    return VMMenu().run()


if __name__ == "__main__":
    sys.exit(main())
