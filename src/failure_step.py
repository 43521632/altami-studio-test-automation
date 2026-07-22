"""Разбор падения теста: на каком шаге упал и почему.

«Шаг» здесь — строка самого теста, на которой всё сломалось. Отдельного
механизма шагов в тестах нет, и он не нужен: трассировка знает точное место, а
внутренние кадры (base_tests, screenshot_compare, pytest.fail) для отчёта
бесполезны — они одинаковы у всех падений. Поэтому берём самый глубокий кадр,
который лежит внутри tests/, и показываем его строку.

Используется и логом прогона (tests/conftest.py), и консолью
(src/interactive_plugin.py), чтобы формулировка была одна и та же.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, Optional

from config.settings import TESTS_DIR

logger = logging.getLogger(__name__)


class FailureInfo(NamedTuple):
    """Where a test failed and why."""

    #: «test_windows_altami_studio.py:152  await self.assert_region(...)»
    step: Optional[str]
    #: Первая строка сообщения об ошибке
    reason: str
    #: Путь к diff-изображению, если сравнение скриншотов его сохранило
    diff: Optional[str]

    def as_log_line(self) -> str:
        """Single-line form for the run log."""
        parts = [self.reason]
        if self.step:
            parts.insert(0, f"шаг: {self.step}")
        if self.diff:
            parts.append(self.diff)
        return " | ".join(parts)


def _entry_path(entry: Any) -> Optional[Path]:
    """Resolved path of a traceback entry, or None if it has none."""
    try:
        return Path(str(entry.path)).resolve()
    except (OSError, ValueError, TypeError):
        return None


def _test_frame(excinfo: Any):
    """Deepest traceback entry that is a line of a test itself.

    Приоритет — кадр из файла test_*.py: это и есть шаг сценария. Кадры
    помощников (tests/base_tests.py) и внутренностей pytest (outcomes.py, где
    исполняется pytest.fail) в отчёте бесполезны: они одинаковы у всех падений
    и не говорят, что именно делал тест.
    """
    try:
        entries = list(excinfo.traceback)
    except Exception:  # noqa: BLE001 — разбор падения не должен ронять прогон
        return None
    if not entries:
        return None

    tests_dir = Path(TESTS_DIR).resolve()

    # 1. Строка самого теста
    for entry in reversed(entries):
        path = _entry_path(entry)
        if path is not None and path.name.startswith("test_"):
            return entry

    # 2. Любой кадр из tests/ — помощник, но всё ещё наш код
    for entry in reversed(entries):
        path = _entry_path(entry)
        if path is not None and str(path).startswith(str(tests_dir)):
            return entry

    # 3. Последний кадр вне библиотек: лучше показать наш src, чем pytest
    for entry in reversed(entries):
        path = _entry_path(entry)
        if path is not None and "site-packages" not in path.parts:
            return entry

    return entries[-1]


def _statement(entry: Any) -> str:
    """The source line of a traceback entry, collapsed to one line."""
    try:
        text = str(entry.statement)
    except Exception:  # noqa: BLE001 — исходника может не быть под рукой
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    statement = " ".join(lines)
    # Длинные многострочные вызовы разносят и лог, и консоль — обрезаем
    return statement if len(statement) <= 120 else statement[:117] + "…"


def describe_failure(excinfo: Any) -> FailureInfo:
    """Summarise a failure: the test line that broke, the reason, the diff."""
    reason, diff = "", None
    try:
        message = excinfo.exconly()
    except Exception:  # noqa: BLE001
        message = str(excinfo)

    for line in str(message).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not reason:
            # «Failed: Область ... не совпала» — префикс исключения не нужен
            reason = stripped.split("Failed: ", 1)[-1]
        elif stripped.startswith("различия:"):
            diff = stripped

    entry = _test_frame(excinfo)
    step = None
    if entry is not None:
        try:
            # entry.lineno отсчитывается от нуля, в файле нумерация с единицы
            location = f"{Path(str(entry.path)).name}:{entry.lineno + 1}"
        except Exception:  # noqa: BLE001
            location = None
        if location:
            statement = _statement(entry)
            step = f"{location}  {statement}" if statement else location

    return FailureInfo(step=step, reason=reason or "причина не определена", diff=diff)
