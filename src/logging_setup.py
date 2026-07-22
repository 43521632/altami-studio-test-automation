"""Logging configuration: rotating run log, per-test log files, rich console."""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from config.settings import (
    CONSOLE_LOG_LEVEL,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_ROTATION_BACKUP_COUNT,
    LOG_ROTATION_MAX_BYTES,
    LOGS_DIR,
)

_configured = False


class ConsoleFilter(logging.Filter):
    """Hide records marked with ``extra={"console": False}`` from the console.

    Так помечают строки, которые в консоли уже показаны в более удобном виде:
    статусы тестов печатает src/interactive_plugin.py, и дублировать их
    лог-записями значит удваивать вывод. В файле лога они остаются.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "console", True)


def setup_logging(
    level: Optional[str] = None,
    log_dir: Path = LOGS_DIR,
    use_rich: bool = True,
    console_level: Optional[str] = None,
) -> Path:
    """Configure root logging: rotating file handler plus console output.

    Файл и консоль намеренно живут на разных уровнях. В файл идёт всё вплоть до
    DEBUG — по нему разбирают падения. В консоль (`console_level`, по умолчанию
    CONSOLE_LOG_LEVEL=WARNING) — только проблемы: ход прогона там печатает
    src/interactive_plugin.py, и поток INFO от QMP и сравнения скриншотов делал
    вывод нечитаемым.

    Safe to call more than once — later calls are no-ops.

    Returns:
        Path of the main run log file.
    """
    global _configured
    run_log = Path(log_dir) / "test_run.log"
    if _configured:
        return run_log

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO))

    file_handler = RotatingFileHandler(
        run_log,
        maxBytes=LOG_ROTATION_MAX_BYTES,
        backupCount=LOG_ROTATION_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    console: logging.Handler
    if use_rich:
        try:
            from rich.logging import RichHandler

            console = RichHandler(rich_tracebacks=True, show_path=False)
            console.setFormatter(logging.Formatter("%(message)s", LOG_DATE_FORMAT))
        except ImportError:
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    else:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    console.setLevel(
        getattr(logging, (console_level or CONSOLE_LOG_LEVEL).upper(), logging.WARNING)
    )
    console.addFilter(ConsoleFilter())
    root.addHandler(console)

    # libvirt и asyncio на DEBUG слишком шумные — держим их на WARNING
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _configured = True
    return run_log


class TestLogContext:
    """Attach a dedicated log file to one test, for Kiwi attachment later.

    Example:
        with TestLogContext("test_login", "windows") as ctx:
            ...
        result.log_file = str(ctx.path)
    """

    def __init__(self, test_name: str, vm_id: str, log_dir: Path = LOGS_DIR) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Имя файла = имя теста + timestamp, как требуется для привязки к Kiwi
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in test_name)
        self.path = Path(log_dir) / vm_id / f"{safe_name}_{timestamp}.log"
        self._handler: Optional[logging.Handler] = None

    def __enter__(self) -> "TestLogContext":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handler = logging.FileHandler(self.path, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        self._handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler.close()
            self._handler = None
