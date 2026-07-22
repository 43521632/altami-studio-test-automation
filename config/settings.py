"""Project-wide settings loaded from environment and vms_config.yaml."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv опционален — без него читаем чистый env
    pass

# --- Базовые пути --------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
TESTS_DIR = BASE_DIR / "tests"
VMS_CONFIG_PATH = CONFIG_DIR / "vms_config.yaml"


def load_vms_config(path: Path = VMS_CONFIG_PATH) -> Dict[str, Any]:
    """Load and parse vms_config.yaml.

    Raises:
        FileNotFoundError: config file is missing.
        ValueError: config file contains invalid YAML.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Файл конфигурации не найден: {path}\n"
            f"Создайте его на основе config/vms_config.yaml из репозитория."
        )
    except yaml.YAMLError as e:
        raise ValueError(f"Ошибка парсинга YAML в {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Ожидался словарь в корне {path}, получено: {type(data)}")
    return data


# Конфиг загружается один раз при импорте модуля.
CONFIG: Dict[str, Any] = load_vms_config()

# --- libvirt -------------------------------------------------------------
_libvirt_cfg = CONFIG.get("libvirt", {})
LIBVIRT_URI = os.getenv("LIBVIRT_URI", _libvirt_cfg.get("uri", "qemu:///system"))
LIBVIRT_CONNECT_TIMEOUT = int(_libvirt_cfg.get("connect_timeout", 10))
LIBVIRT_CONNECT_RETRIES = int(_libvirt_cfg.get("connect_retries", 3))
LIBVIRT_RETRY_BACKOFF = float(_libvirt_cfg.get("retry_backoff", 2.0))

# --- Тесты ---------------------------------------------------------------
_test_cfg = CONFIG.get("test_settings", {})
TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", _test_cfg.get("timeout", 300)))
RETRY_COUNT = int(_test_cfg.get("retry_count", 3))
PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", _test_cfg.get("parallel_workers", 2)))

_screenshot_cfg = _test_cfg.get("screenshot_comparison", {})
SSIM_THRESHOLD = float(_screenshot_cfg.get("threshold", 0.99))
SSIM_SAVE_DIFF = bool(_screenshot_cfg.get("save_diff", True))
SSIM_RESIZE_ON_MISMATCH = bool(_screenshot_cfg.get("resize_on_mismatch", False))

# --- Логирование и артефакты --------------------------------------------
_log_cfg = CONFIG.get("logging", {})


def _resolve(value: str, default: str) -> Path:
    """Resolve a config path relative to BASE_DIR unless it is absolute."""
    p = Path(value or default)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


LOGS_DIR = _resolve(_log_cfg.get("log_dir"), "./logs")
SCREENSHOT_DIR = _resolve(_log_cfg.get("screenshot_dir"), "./screenshots")
BASELINE_DIR = _resolve(_log_cfg.get("baseline_dir"), "./baseline")
DIFF_DIR = _resolve(_log_cfg.get("diff_dir"), "./screenshots/diff")
REPORT_DIR = _resolve(_log_cfg.get("report_dir"), "./reports")

LOG_LEVEL = os.getenv("LOG_LEVEL", _log_cfg.get("log_level", "INFO"))
# Уровень для КОНСОЛИ отдельно от файла: в файл пишем всё (до DEBUG), а в
# консоли нужны только проблемы — статусы тестов туда печатает
# src/interactive_plugin.py, и поток INFO от QMP их заглушал.
CONSOLE_LOG_LEVEL = os.getenv("CONSOLE_LOG_LEVEL", "WARNING")
# Сколько логов прогонов держать на каждую ВМ (logs/pytest_<вм>_<дата>.log).
# Старые удаляются при старте нового прогона — см. tests/conftest.py.
LOG_RETENTION_RUNS = int(os.getenv("LOG_RETENTION_RUNS", "30"))
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_ROTATION_MAX_BYTES = int(_log_cfg.get("rotation_max_bytes", 10 * 1024 * 1024))
LOG_ROTATION_BACKUP_COUNT = int(_log_cfg.get("rotation_backup_count", 5))

# Создание рабочих директорий (idempotent)
for _d in (LOGS_DIR, SCREENSHOT_DIR, BASELINE_DIR, DIFF_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Kiwi TCMS (заглушка) ------------------------------------------------
_kiwi_cfg = CONFIG.get("kiwi", {})
KIWI_ENABLED = os.getenv("KIWI_ENABLED", str(_kiwi_cfg.get("enabled", False))).lower() == "true"
KIWI_URL = os.getenv("KIWI_URL", _kiwi_cfg.get("url", ""))
KIWI_API_KEY = os.getenv("KIWI_API_KEY", _kiwi_cfg.get("api_key", ""))
KIWI_PROJECT_ID = _kiwi_cfg.get("project_id")
KIWI_TEST_RUN_NAME = _kiwi_cfg.get("test_run_name", "Automated UI Tests")

_kiwi_export = _kiwi_cfg.get("local_export", {})
KIWI_EXPORT_ENABLED = bool(_kiwi_export.get("enabled", True))
KIWI_EXPORT_JSON = _resolve(_kiwi_export.get("json_path"), "./reports/kiwi_export.json")
KIWI_EXPORT_CSV = _resolve(_kiwi_export.get("csv_path"), "./reports/kiwi_export.csv")


def get_vm_config(vm_id: str) -> Dict[str, Any]:
    """Return the config block for a single VM id (e.g. "windows")."""
    return CONFIG.get("vms", {}).get(vm_id, {})


def get_all_vm_ids() -> list:
    """Return every VM id declared in the config."""
    return list(CONFIG.get("vms", {}).keys())


def get_enabled_vm_ids() -> list:
    """Return VM ids with `enabled: true`."""
    return [vm_id for vm_id, cfg in CONFIG.get("vms", {}).items() if cfg.get("enabled")]
