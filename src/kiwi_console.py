"""Диалог настройки отправки в Kiwi TCMS для консольных режимов прогона.

Зачем отдельный модуль: интерактивный сеанс (src/session_console.py) и режим
разработчика (src/dev_run.py) запускают pytest в дочернем процессе, а плагин
utils/pytest_kiwi_plugin.py читает всё нужное из ОКРУЖЕНИЯ этого процесса —
KIWI_URL, KIWI_USER, KIWI_PASSWORD, KIWI_TESTRUN_ID, KIWI_REPORTING_ENABLED.
Значит, весь проброс сводится к тому, чтобы положить эти значения в env перед
запуском. Здесь они и собираются — одним диалогом, из одного места.

Что важно знать про имена переменных:

    KIWI_URL        — БАЗОВЫЙ АДРЕС СЕРВЕРА Kiwi (https://kiwitcms.altami.ru),
                      а НЕ ссылка на тест-ран. Логин и пароль клиент берёт из
                      KIWI_USER / KIWI_PASSWORD (см. utils/kiwi_client.py).
    KIWI_TESTRUN_ID — номер тест-рана, целое число. Именно его ждёт
                      KiwiClient.get_testrun(id) и плагин отчётов.

Поэтому «вставить одну строку» можно: полная ссылка вида
https://kiwitcms.altami.ru/testruns/123/ принимается и распаривается на адрес
сервера и номер рана. А можно ответить на два вопроса раздельно.

Договорённость по Enter: Enter = «как настроено в .env». То есть если в .env
задан KIWI_TESTRUN_ID, нажатие Enter берёт ран из .env, а не отменяет
отправку. Полностью локальный прогон — это явный отказ: `--no-kiwi` в
командной строке или ввод `-` в диалоге.
"""

import logging
import os
import re
import sys
from typing import Dict, Optional, Tuple

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()

# Значения, которые диалог кладёт в env дочернего pytest
KIWI_ENV_KEYS = (
    "KIWI_URL",
    "KIWI_USER",
    "KIWI_PASSWORD",
    "KIWI_TESTRUN_ID",
    "KIWI_REPORTING_ENABLED",
)

# Отказ от отправки, введённый руками
_OFF_MARKS = {"-", "нет", "no", "off", "локально", "local"}

# Ссылка на тест-ран: .../testruns/123/ или .../runs/123
_TESTRUN_URL_RE = re.compile(r"/(?:testruns|runs)/(\d+)")


def kiwi_env_from_environment() -> Dict[str, str]:
    """Вернуть текущие kiwi-настройки окружения (то, что видно из .env)."""
    return {key: os.environ[key] for key in KIWI_ENV_KEYS if os.environ.get(key)}


def parse_kiwi_target(raw: str) -> Tuple[str, str]:
    """Разобрать то, что ввёл пользователь. Возвращает (адрес сервера, номер).

    Принимает и голый адрес сервера, и полную ссылку на тест-ран:

        https://kiwitcms.altami.ru                 -> (адрес, "")
        https://kiwitcms.altami.ru/testruns/123/   -> (адрес, "123")
        123                                        -> ("", "123")
    """
    value = (raw or "").strip().rstrip("/")
    if not value:
        return "", ""

    if value.isdigit():
        return "", value

    match = _TESTRUN_URL_RE.search(value)
    if match:
        return value[: match.start()], match.group(1)

    return value, ""


def kiwi_env_from_args(args) -> Dict[str, str]:
    """Собрать настройки Kiwi из аргументов командной строки.

    Нужна лаунчеру: сеанс открывается в ОТДЕЛЬНОМ окне, спросить в нём
    пользователя можно, но значения должны приехать из уже отвеченного
    диалога — и лучше флагами, а не через env, чтобы их было видно в `ps`.

    Возвращает только те переменные, которые реально заданы аргументами.
    """
    env: Dict[str, str] = {}
    url = getattr(args, "kiwi_url", None)
    testrun = getattr(args, "kiwi_testrun", None)
    if url:
        base, run_id = parse_kiwi_target(url)
        env["KIWI_URL"] = base or url.rstrip("/")
        if run_id and not testrun:
            testrun = run_id
    if testrun:
        env["KIWI_TESTRUN_ID"] = str(testrun)
    if getattr(args, "no_kiwi", False):
        env["KIWI_REPORTING_ENABLED"] = "false"
        env.pop("KIWI_TESTRUN_ID", None)
    return env


def _check_testrun(env: Dict[str, str], vm_id: str = "") -> None:
    """Проверить ран до старта тестов и сказать внятно, если что-то не так.

    Проверка не блокирует прогон: если связи нет, тесты всё равно пойдут —
    но пользователь узнает об этом СЕЙЧАС, а не после часа прогона, когда
    результаты некуда будет отправить.
    """
    run_id = env.get("KIWI_TESTRUN_ID")
    if not run_id:
        return

    try:
        from utils.kiwi_client import KiwiClient

        client = KiwiClient(
            base_url=env.get("KIWI_URL"),
            username=env.get("KIWI_USER"),
            password=env.get("KIWI_PASSWORD"),
        )
        data = client.get_testrun(int(run_id))
    except ValueError as e:
        # Нет адреса или учётных данных — это не сбой связи, а неполный .env
        console.print(f"[yellow]Kiwi не проверен:[/yellow] {e}")
        return
    except Exception as e:
        console.print(
            f"[bold red]Kiwi недоступен:[/bold red] {e}\n"
            "[dim]Тесты пойдут, но результаты в ран не попадут — "
            "проверьте адрес, логин и пароль.[/dim]"
        )
        return

    summary = data.get("summary") or "(без названия)"
    assignee = data.get("assignee")
    if isinstance(assignee, dict):
        assignee = assignee.get("username")
    # Ран, назначенный на другого, — почти всегда ошибка в номере: писать
    # свои результаты в чужой ран нельзя, и молчать об этом нечестно.
    if assignee and env.get("KIWI_USER") and assignee != env["KIWI_USER"]:
        console.print(
            f"[bold yellow]Внимание:[/bold yellow] ран {run_id} назначен на "
            f"'{assignee}', а не на '{env['KIWI_USER']}'."
        )
    where = f" [dim]({vm_id})[/dim]" if vm_id else ""
    console.print(f"[green]Kiwi:[/green] ран {run_id} — {summary}{where}")


def describe_kiwi(env: Optional[Dict[str, str]]) -> str:
    """Строка для шапки сеанса: куда уйдут результаты.

    Используется и в Panel сеанса, и в итоговой таблице — чтобы ответ на
    вопрос «а оно вообще отправилось?» был перед глазами, а не в логе.
    """
    env = env or {}
    run_id = env.get("KIWI_TESTRUN_ID")
    if not run_id or env.get("KIWI_REPORTING_ENABLED", "true").lower() != "true":
        return "локальный прогон, без отправки"

    url = (env.get("KIWI_URL") or "").rstrip("/")
    host = url.split("//")[-1] if url else "Kiwi"
    return f"{host}, тест-ран {run_id}"


def no_kiwi_env() -> Dict[str, str]:
    """Переменные для заведомо локального прогона (--no-kiwi)."""
    return {"KIWI_REPORTING_ENABLED": "false"}


def _is_off(raw: str) -> bool:
    """Явный отказ от отправки: `-`, «нет», «локально» и т.п."""
    return raw.strip().lower() in _OFF_MARKS


def _reporting_state(env: Dict[str, str]) -> str:
    """Короткая подпись «куда уйдут результаты» для заголовков диалога."""
    if env.get("KIWI_REPORTING_ENABLED", "true").lower() != "true":
        return "локально, без отправки"
    run_id = env.get("KIWI_TESTRUN_ID")
    return f"ран {run_id}" if run_id else "Kiwi не настроен"


def ask_kiwi(
    current: Optional[Dict[str, str]] = None,
    case_id: Optional[str] = None,
    vm_id: str = "",
    title: str = "Отправка в Kiwi TCMS",
) -> Optional[Dict[str, str]]:
    """Спросить у пользователя, куда отправлять результаты. Вернуть env-набор.

    Возвращает словарь переменных для дочернего pytest или ``None``, если
    пользователь прервал диалог (Ctrl+C / EOF) — вызывающий код в этом случае
    решает сам, продолжать ли прогон.

    Диалог задаёт ДВА вопроса раздельно, как договорились: адрес сервера и
    номер тест-рана. При этом на любой из них можно вставить одну строку —
    полную ссылку ``https://kiwitcms.altami.ru/testruns/123/``: номер из неё
    выдёргивается, а адрес сервера остаётся.

    Enter = «как настроено в .env»: если ``KIWI_TESTRUN_ID`` там задан, Enter
    берёт ран оттуда, а не отменяет отправку. Полностью локальный прогон —
    явный отказ: ``-`` (или --no-kiwi в командной строке).
    """
    base = dict(current if current is not None else kiwi_env_from_environment())
    default_url = base.get("KIWI_URL", "")
    default_run = base.get("KIWI_TESTRUN_ID", "")

    # Значения из .env уже проставлены — диалог их только уточняет
    env: Dict[str, str] = dict(base)
    env.setdefault("KIWI_REPORTING_ENABLED", "true")

    head = (
        f"ВМ: [bold]{vm_id}[/bold]\n" if vm_id else ""
    ) + (f"Кейс: [bold magenta]{case_id}[/bold magenta]\n" if case_id else "")
    console.print(
        Panel(
            head
            + f"Сейчас: [bold]{_reporting_state(env)}[/bold]\n\n"
            "Enter — оставить как настроено в .env.\n"
            "``-`` — локальный прогон, без отправки.\n"
            "Можно вставить полную ссылку на ран: "
            "[dim]https://kiwitcms.altami.ru/testruns/123/[/dim]",
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
        )
    )

    if not sys.stdin or not sys.stdin.isatty():
        # Спросить некого (не терминал): молча оставляем как в .env
        logger.info("stdin не терминал — Kiwi оставлен как в .env")
        return env

    try:
        # --- Вопрос 1: адрес сервера (или ссылка на ран целиком) -------------
        raw_url = input(
            f"Адрес сервера Kiwi [{default_url or 'не задан'}]: "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Диалог Kiwi прерван[/yellow]")
        return None

    if _is_off(raw_url):
        console.print("[yellow]Kiwi: локальный прогон, без отправки[/yellow]")
        return no_kiwi_env()

    if raw_url:
        url, run_from_url = parse_kiwi_target(raw_url)
        if url:
            env["KIWI_URL"] = url
        if run_from_url:
            env["KIWI_TESTRUN_ID"] = run_from_url

    # --- Вопрос 2: номер тест-рана --------------------------------------
    run_now = env.get("KIWI_TESTRUN_ID", "")
    hint = run_now or (default_run or "не задан")
    try:
        raw_run = input(f"Номер тест-рана [{hint}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Диалог Kiwi прерван[/yellow]")
        return None

    if _is_off(raw_run):
        console.print("[yellow]Kiwi: локальный прогон, без отправки[/yellow]")
        return no_kiwi_env()

    if raw_run:
        # Во второй вопрос тоже можно вставить ссылку — распарсим её
        _, run_from_url = parse_kiwi_target(raw_run)
        env["KIWI_TESTRUN_ID"] = run_from_url or raw_run

    if not env.get("KIWI_TESTRUN_ID"):
        # Ни .env, ни ответ не дали номера — отправлять некуда. Молча гадать
        # нельзя: прогон уйдёт «в пустоту», а узнается это только в конце.
        console.print(
            "[yellow]Номер тест-рана не задан — прогон будет локальным.[/yellow]"
        )
        return no_kiwi_env()

    if not str(env.get("KIWI_TESTRUN_ID", "")).isdigit():
        console.print(
            f"[yellow]'{env['KIWI_TESTRUN_ID']}' не похоже на номер рана — "
            "прогон будет локальным.[/yellow]"
        )
        return no_kiwi_env()

    _check_testrun(env, vm_id)
    return env


def ask_kiwi_link(
    current: Optional[Dict[str, str]] = None,
    vm_id: str = "",
) -> Dict[str, str]:
    """Один вопрос для ЦЕПОЧКИ тестов: ссылка на тест-ран Kiwi.

    Для запуска цепочки отдельный вопрос про адрес сервера — лишний: адрес и
    так есть в ``.env``, а пользователю важно ответить на единственный вопрос
    «в какой ран писать». Поэтому здесь ОДИН ввод, который принимает и полную
    ссылку ``https://kiwitcms.altami.ru/testruns/123/``, и просто номер рана,
    и пустую строку.

    Пустой ввод (Enter) = локальный прогон, без отправки. Раньше Enter означал
    «как в .env», но для цепочки это опасно: прогон уходил в общий ран, когда
    пользователь этого не хотел. Явное правило проще и безопаснее —
    «ничего не передал, значит локально».

    Возвращает готовый env-набор (никогда ``None``): отказ — это просто
    локальный прогон, а не отмена запуска.
    """
    base = dict(current if current is not None else kiwi_env_from_environment())
    default_url = (base.get("KIWI_URL") or "https://kiwitcms.altami.ru").rstrip("/")
    default_run = base.get("KIWI_TESTRUN_ID", "")

    console.print(
        Panel(
            (f"ВМ: [bold]{vm_id}[/bold]\n" if vm_id else "")
            + "Ссылка на тест-ран Kiwi или его номер.\n"
            "Пусто (Enter) — локальный прогон, без отправки.\n\n"
            f"Пример: [dim]{default_url}/testruns/12345/[/dim]\n"
            f"Или просто: [dim]12345[/dim]"
            + (f"   (в .env: ран {default_run})" if default_run else ""),
            title="[bold cyan]Куда отправить результаты[/bold cyan]",
            border_style="cyan",
        )
    )

    if not sys.stdin or not sys.stdin.isatty():
        # Спросить некого (не терминал): локальный прогон — безопасный выбор
        logger.info("stdin не терминал — цепочка идёт локально")
        return no_kiwi_env()

    try:
        raw = input("Тест-ран Kiwi (Enter — локально): ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Ввод прерван — прогон будет локальным[/yellow]")
        return no_kiwi_env()

    if not raw or _is_off(raw):
        console.print("[yellow]Kiwi: локальный прогон, без отправки[/yellow]")
        return no_kiwi_env()

    url, run_id = parse_kiwi_target(raw)
    if not url:
        url = base.get("KIWI_URL") or default_url
    if not run_id:
        run_id = raw  # пользователь ввёл голый номер

    if not str(run_id).isdigit():
        console.print(
            f"[yellow]'{raw}' не похоже на ссылку или номер рана — "
            "прогон будет локальным.[/yellow]"
        )
        return no_kiwi_env()

    env = dict(base)
    env["KIWI_URL"] = url.rstrip("/")
    env["KIWI_TESTRUN_ID"] = str(run_id)
    env["KIWI_REPORTING_ENABLED"] = "true"
    _check_testrun(env, vm_id)
    console.print(f"[green]Kiwi:[/green] {describe_kiwi(env)}")
    return env
