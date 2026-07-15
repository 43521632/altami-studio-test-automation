"""Общие настройки проекта"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
TESTS_DIR = BASE_DIR / "tests"

# Создание директорий
LOGS_DIR.mkdir(exist_ok=True)

# Настройки логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Настройки QMP
QMP_TIMEOUT = int(os.getenv("QMP_TIMEOUT", "30"))
QMP_RETRIES = int(os.getenv("QMP_RETRIES", "3"))

# Настройки тестов
TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))
PARALLEL_TESTS = os.getenv("PARALLEL_TESTS", "true").lower() == "true"

# Конфигурация ВМ
VMS_CONFIG_PATH = CONFIG_DIR / "vms_config.yaml"
