"""Shared pytest fixtures: VM session, screenshot assertions, failure capture.

The VM under test is chosen by the VM_ID environment variable, which
`run_tests.py` sets for each pytest subprocess. Running pytest directly
defaults to VM_ID=windows.

The VM boots once per pytest session and every test in that session runs
against it sequentially — a single guest cannot be driven concurrently.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from config.settings import LOG_RETENTION_RUNS, LOGS_DIR, SCREENSHOT_DIR
from src.case_ids import TEST_CASE_MAP, case_id_for
from src.failure_step import describe_failure
from src.logging_setup import setup_logging
from src.screenshot_compare import ComparisonResult, ScreenshotComparator
from src.vm_manager import VMManager, VMSession

logger = logging.getLogger(__name__)

# Какая ВМ тестируется в этом процессе pytest
VM_ID = os.environ.get("VM_ID", "windows")
# Домен libvirt из run_tests.py --vm-name, если он переопределён
VM_NAME_OVERRIDE = os.environ.get("VM_NAME_OVERRIDE") or None


def _per_run_log_file() -> Path:
    """Path of this run's pytest log: `logs/pytest_<вм>_<дата>_<время>.log`.

    Имя с ВМ, а не только с временем: два прогона разных ОС идут параллельно и
    писали бы в один файл.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(LOGS_DIR) / f"pytest_{VM_ID}_{stamp}.log"


def _prune_old_logs(current: Path, keep: int = LOG_RETENTION_RUNS) -> None:
    """Keep only the newest `keep` run logs of this VM, delete the rest.

    Удаляются исключительно файлы, которые мы сами и создали: маска строгая —
    `pytest_<вм>_<8 цифр>_<6 цифр>.log`. Ссылка `..._last.log` под неё не
    подходит, чужие файлы в logs/ — тоже.

    Лог текущего прогона (`current`) не трогаем никогда. Сортировка идёт по
    имени, то есть по времени старта, и при сбитых часах свежий файл мог бы
    оказаться «старым» — прогон остался бы без своего лога.
    """
    if keep <= 0:
        return

    pattern = re.compile(rf"^pytest_{re.escape(VM_ID)}_\d{{8}}_\d{{6}}\.log$")
    try:
        files = [
            path for path in Path(LOGS_DIR).iterdir()
            if path.is_file() and not path.is_symlink() and pattern.match(path.name)
        ]
    except OSError as e:
        logger.debug("Не удалось просмотреть %s: %s", LOGS_DIR, e)
        return

    # Имя содержит дату и время, поэтому обычная сортировка по имени = по времени
    for old in sorted(files, key=lambda p: p.name, reverse=True)[keep:]:
        if old.name == current.name:
            continue
        try:
            old.unlink()
            logger.debug("Удалён старый лог прогона: %s", old)
        except OSError as e:
            logger.debug("Не удалось удалить %s: %s", old, e)


def _link_latest(target: Path) -> None:
    """Point `logs/pytest_<вм>_last.log` at this run's log, for `tail -f`.

    Обычный файл с таким именем не трогаем — удаляем только собственную ссылку.
    """
    link = Path(LOGS_DIR) / f"pytest_{VM_ID}_last.log"
    try:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            return
        link.symlink_to(target.name)
    except OSError as e:
        logger.debug("Не удалось обновить ссылку %s: %s", link, e)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add `--case TC-85` — run exactly the tests with these case ids."""
    parser.addoption(
        "--case",
        action="append",
        default=[],
        metavar="TC-85",
        help=(
            "Прогнать только тест(ы) с этим ID кейса из src/case_ids.py. "
            "Можно повторять: --case TC-85 --case TC-84. Регистр не важен."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register OS markers, point the log at this run's file, start logging."""
    for marker, description in [
        ("windows", "Тесты для Windows ВМ"),
        ("astra", "Тесты для Astra Linux ВМ"),
        ("macos", "Тесты для macOS ВМ"),
        ("ui", "UI-тесты со сравнением скриншотов"),
        ("app", "Тесты, запускающие Altami Studio (идут в конце прогона)"),
        ("smoke", "Быстрые проверки доступности ВМ"),
        ("network", "Сетевые тесты"),
        ("security", "Тесты безопасности"),
        ("system", "Системные тесты"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {description}")

    # Свой файл на каждый прогон вместо вечно дописываемого logs/pytest.log.
    # Явный --log-file в командной строке уважаем. Плагин логирования создаётся
    # в pytest_configure с trylast, то есть уже после этого хука, и подхватит
    # подменённое значение.
    if not config.getoption("log_file"):
        run_log = _per_run_log_file()
        run_log.parent.mkdir(parents=True, exist_ok=True)
        config.option.log_file = str(run_log)
        # Создаём файл сразу: плагин логирования откроет его позже, а нам он
        # нужен уже сейчас, чтобы попасть в счёт хранимых прогонов
        run_log.touch(exist_ok=True)
        _link_latest(run_log)
        _prune_old_logs(run_log)

    setup_logging()


def _select_by_case_id(config: pytest.Config, items) -> None:
    """Оставить в прогоне только тесты с ID кейсов из `--case`.

    Отбор по ID, а не по имени файла: ID — это то, чем кейс называют в
    тестовой системе и в разговоре, а где лежит тест, помнить не обязано.
    Несовпавшие тесты именно снимаются с прогона (deselect), а не помечаются
    пропущенными: пропуски засоряли бы отчёт десятками строк.
    """
    wanted = {case.strip().upper() for case in config.getoption("--case") if case.strip()}
    if not wanted:
        return

    selected, deselected = [], []
    for item in items:
        case_id = case_id_for(item.nodeid)
        (selected if case_id and case_id.upper() in wanted else deselected).append(item)

    if not selected:
        known = sorted({cid for cid in TEST_CASE_MAP.values() if cid})
        raise pytest.UsageError(
            f"Ни один тест не смэтчен с ID {', '.join(sorted(wanted))}.\n"
            f"  Известные ID: {', '.join(known) if known else '(ни одного)'}\n"
            f"  ID проставляются вручную в src/case_ids.py."
        )

    # Найденные ID могли покрыть не все запрошенные — молчать об этом нельзя,
    # иначе опечатка в одном ID выглядела бы как успешный прогон по обоим.
    found = {case_id_for(item.nodeid).upper() for item in selected}
    if missing := wanted - found:
        logger.warning(
            "Не найдены тесты для ID: %s — прогон пойдёт без них",
            ", ".join(sorted(missing)),
        )

    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_collection_modifyitems(config: pytest.Config, items) -> None:
    """Отобрать тесты по `--case` и отправить тесты с маркером `app` в конец.

    Altami Studio остаётся открытым после своих тестов — так задумано, на нём
    будут строиться следующие сценарии. Но окно приложения закрывает рабочий
    стол, а `test_desktop_matches_baseline` сверяет именно чистый стол с
    эталоном. По алфавиту файл ...altami_studio.py собирается раньше
    ...system.py, поэтому без этой сортировки тест стола падал бы с SSIM ~0.88.

    Сортировка стабильна: порядок остальных тестов не меняется.
    """
    _select_by_case_id(config, items)
    items.sort(key=lambda item: 1 if item.get_closest_marker("app") else 0)


def case_label(nodeid: str) -> str:
    """Test name prefixed with its case id from src/case_ids.py, when mapped."""
    case_id = case_id_for(nodeid)
    return f"[{case_id}] {nodeid}" if case_id else nodeid


# Статусы тестов в консоли печатает src/interactive_plugin.py — в более
# читаемом виде. Лог-записи об этом же помечаем как «не для консоли», иначе
# каждый тест выводился бы дважды. В файле лога они остаются.
_LOG_ONLY = {"console": False}


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Log the start of every test together with its case id."""
    logger.info("СТАРТ %s", case_label(item.nodeid), extra=_LOG_ONLY)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report on the item, so fixtures can see failures.

    Здесь же в лог уходит итог теста с ID кейса, а у падения — шаг и причина.
    Разбор падения кладётся на отчёт (`report.failure_info`), чтобы консоль
    (src/interactive_plugin.py) показывала ровно то же, что попало в лог.
    """
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    if report.failed and call.excinfo is not None:
        report.failure_info = describe_failure(call.excinfo)

    # Итог: обычный тест закрывается фазой call, пропущенный — фазой setup
    if report.when != "call" and not report.skipped:
        return

    label = case_label(item.nodeid)
    if report.failed:
        info = getattr(report, "failure_info", None)
        logger.error(
            "FAILED %s — %s", label, info.as_log_line() if info else "",
            extra=_LOG_ONLY,
        )
    elif report.skipped:
        logger.info("SKIPPED %s", label, extra=_LOG_ONLY)
    else:
        logger.info("PASSED %s", label, extra=_LOG_ONLY)


# --- Фикстуры ВМ ------------------------------------------------------------


@pytest.fixture(scope="session")
def vm_id() -> str:
    """The VM id under test in this pytest process."""
    return VM_ID


@pytest.fixture(scope="session")
def vm_manager() -> VMManager:
    """Session-wide VM manager."""
    manager = VMManager()
    yield manager
    manager.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def vm_session(vm_manager: VMManager, vm_id: str) -> VMSession:
    """Boot the VM (if needed), open a QMP session, and yield it.

    Skips the whole session — rather than failing every test — when the VM
    is unavailable, so a missing macOS host does not look like 40 bugs.
    """
    from src.vm_manager import VMManagerError

    try:
        async with vm_manager.session(
            vm_id, vm_name_override=VM_NAME_OVERRIDE, wait_for_boot=True
        ) as session:
            logger.info("ВМ '%s' готова к тестам", vm_id)
            yield session
    except VMManagerError as e:
        pytest.skip(f"ВМ '{vm_id}' недоступна: {e}")
    except Exception as e:  # noqa: BLE001 — сюда попадают ошибки libvirt/QMP
        pytest.skip(f"Не удалось подготовить ВМ '{vm_id}': {e}")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def guest_login(vm_session: VMSession) -> bool:
    """Sign into the guest OS once, before any test runs.

    Setup, not a test: UI tests need a desktop, and the VM boots to a lock
    screen. Skips itself when the desktop is already up (the VM keeps running
    between runs). Credentials come from the VM's `login:` block.
    """
    from src.guest_login import ensure_logged_in

    performed = await ensure_logged_in(vm_session)
    logger.info(
        "%s: автологин %s", vm_session.vm_id,
        "выполнен" if performed else "не потребовался",
    )
    return performed


@pytest_asyncio.fixture(loop_scope="session")
async def screenshot_on_failure(request, vm_session: VMSession):
    """Capture a screenshot automatically when a test fails."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        try:
            path = await vm_session.screenshot(f"FAILED_{request.node.name}")
            logger.error("Тест упал — скриншот сохранён: %s", path)
        except Exception as e:
            logger.error("Не удалось снять скриншот после падения: %s", e)


# --- Сравнение скриншотов ---------------------------------------------------


class ScreenshotAsserter:
    """Helper bound to one VM: capture, compare against baseline, assert."""

    def __init__(self, session: VMSession, comparator: ScreenshotComparator) -> None:
        self.session = session
        self.comparator = comparator
        self.last_result: Optional[ComparisonResult] = None

    async def capture(self, name: str) -> Path:
        """Take a screenshot without comparing it."""
        return await self.session.screenshot(name)

    async def compare(self, test_name: str) -> ComparisonResult:
        """Capture and compare against the baseline, without asserting."""
        current = await self.session.screenshot(test_name)
        self.last_result = self.comparator.compare(current, test_name, self.session.vm_id)
        return self.last_result

    async def assert_matches(self, test_name: str) -> ComparisonResult:
        """Capture, compare, and fail the test if SSIM is below threshold."""
        result = await self.compare(test_name)
        if not result.passed:
            message = [
                f"Скриншот не совпал с эталоном: SSIM={result.score:.6f} "
                f"(нужно > {result.threshold})",
                f"  текущий: {result.current_path}",
                f"  эталон:  {result.baseline_path}",
            ]
            if result.diff_path:
                message.append(f"  различия: {result.diff_path}")
            if result.reason:
                message.append(f"  причина: {result.reason}")
            pytest.fail("\n".join(message))
        return result


@pytest_asyncio.fixture(loop_scope="session")
async def screenshot(vm_session: VMSession) -> ScreenshotAsserter:
    """Screenshot capture and SSIM baseline assertions for the current VM."""
    return ScreenshotAsserter(vm_session, ScreenshotComparator())


@pytest.fixture(scope="session")
def screenshot_dir(vm_id: str) -> Path:
    """Per-VM screenshot directory."""
    path = Path(SCREENSHOT_DIR) / vm_id
    path.mkdir(parents=True, exist_ok=True)
    return path
