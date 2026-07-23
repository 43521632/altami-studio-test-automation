"""Running a single test case on a prepared VM — the test-development mode.

Регрессия гоняет тесты одной ВМ цепочкой: состояние, оставленное одним
тестом, достаётся следующему. Для прогона это правильно, а для РАЗРАБОТКИ
очередного теста — нет: чтобы получить состояние для нового теста, пришлось
бы каждый раз прогонять всю цепочку перед ним, и чем длиннее цепочка, тем
абсурднее цена одной правки.

Здесь состояние готовит человек — снапшотом, кликами, как удобно, — а мы
запускаем ровно один тест поверх готового состояния. Предусловия НЕ
проверяются намеренно: это ответственность того, кто готовил ВМ.

Тест выбирается по ID кейса из тестовой системы (Kiwi TCMS), а не по пути к
файлу: ID — это то, чем кейс называют в работе. Проставляются они вручную в
`src/case_ids.py`; тест без ID в этом режиме недоступен.

Точка входа для меню — :func:`run_single_case` (пункт 9 в src/vm_menu.py).
То же самое из командной строки:

    VM_ID=windows python -m pytest --case TC-85
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR, TEST_TIMEOUT
from src.vm_manager import VMManager

logger = logging.getLogger(__name__)


def pytest_args(vm_id: str, case_id: str, test_path: str) -> list:
    """Command line for one developer-mode pytest run."""
    return [
        sys.executable, "-m", "pytest",
        # Путь сужает сбор до тестов этой ВМ, --case выбирает нужный кейс
        test_path,
        f"--case={case_id}",
        # -s: вывод теста идёт в консоль как есть, без перехвата — при
        # разработке нужен сам ход теста, а не сводка после него
        "-s",
        "-v",
        "--no-header",
        # Внутри одной ВМ параллелить нельзя — гость один
        "-p", "no:xdist",
        f"--timeout={TEST_TIMEOUT}",
        # Разработчику нужен полный traceback, а не одна строка
        "--tb=long",
    ]


def run_single_case(
    vm_id: str, case_id: str, vm_name_override: Optional[str] = None
) -> int:
    """Run the test with `case_id` on `vm_id`. Returns pytest's exit code.

    ВМ считается готовой: состояние не проверяется и не подготавливается.
    """
    config = VMManager().config_for(vm_id)
    test_path = config.get("test_path") or f"./tests/{vm_id}"

    env = os.environ.copy()
    # conftest.py читает VM_ID, чтобы понять, к какой ВМ подключаться
    env["VM_ID"] = vm_id
    if vm_name_override:
        env["VM_NAME_OVERRIDE"] = vm_name_override
    env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    args = pytest_args(vm_id, case_id, test_path)
    logger.info("[%s] Режим разработчика, кейс %s: %s", vm_id, case_id, " ".join(args))
    # stdin/stdout наследуются: вывод идёт прямо в эту консоль
    return subprocess.run(args, cwd=str(Path(BASE_DIR)), env=env).returncode
