"""Соответствие автотестов и ID тест-кейсов во внешней тестовой системе.

Мэтчинг ручной: ID кейсов живут только здесь, в тестах их прописывать не надо.
Консоль прогона показывает ID рядом со статусом теста, а отчёты для Kiwi берут
его отсюда же.

Ключ — nodeid теста из pytest. Посмотреть точные ключи:
    python -m pytest tests/windows --collect-only -q
"""

import re
from typing import List, Optional, Tuple

# ==============================================================================
# MANUAL CASE ID MATCHING (BEGIN)
# В этом блоке указывать ID кейсов из тестовой системы.
# Ключ: путь::Класс::тест (nodeid) либо просто имя теста — совпадёт по любому
# из вариантов. Значение: ID кейса, например "TC-101".
# Пустая строка или отсутствие ключа = кейс ещё не смэтчен.
# ==============================================================================
TEST_CASE_MAP = {
    # --- Windows -------------------------------------------------------------
    "tests/windows/test_windows_system.py::TestWindowsSystem::test_windows_status": "",
    "tests/windows/test_windows_system.py::TestWindowsSystem::test_windows_cpu_info": "",
    "tests/windows/test_windows_system.py::TestWindowsSystem::test_windows_cpu_count_matches_config": "",
    "tests/windows/test_windows_system.py::TestWindowsSystem::test_windows_memory_info": "",
    "tests/windows/test_windows_system.py::TestWindowsUI::test_desktop_matches_baseline": "",
    "tests/windows/test_windows_system.py::TestWindowsUI::test_screenshot_is_captured": "",
    "tests/windows/test_windows_system.py::TestWindowsUI::test_resolution_matches_config": "",
    "tests/windows/test_windows_system.py::TestWindowsUI::test_input_injection_works": "",
    "tests/windows/test_windows_altami_studio.py::TestWindowsAltamiStudio::test_altami_studio_demo_launch": "TC-85",
    "tests/windows/test_windows_license_activation.py::TestWindowsLicenseActivation::test_license_activation_from_file": "TC-86",
    # --- Astra Linux ---------------------------------------------------------
    "tests/Astra/test_astra_system.py::TestAstraSystem::test_astra_status": "",
    "tests/Astra/test_astra_system.py::TestAstraSystem::test_astra_cpu_info": "",
    "tests/Astra/test_astra_system.py::TestAstraSystem::test_astra_cpu_count_matches_config": "",
    "tests/Astra/test_astra_system.py::TestAstraSystem::test_astra_memory_info": "",
    "tests/Astra/test_astra_system.py::TestAstraUI::test_desktop_matches_baseline": "",
    "tests/Astra/test_astra_system.py::TestAstraUI::test_screenshot_is_captured": "",
    "tests/Astra/test_astra_system.py::TestAstraUI::test_resolution_matches_config": "",
    "tests/Astra/test_astra_system.py::TestAstraUI::test_input_injection_works": "",
    "tests/Astra/test_astra_altami_studio.py::TestAstraAltamiStudio::test_altami_studio_demo_launch": "TC-84",
    # --- macOS ---------------------------------------------------------------
    "tests/macos/test_macos_system.py::TestMacosSystem::test_macos_status": "",
    "tests/macos/test_macos_system.py::TestMacosSystem::test_macos_cpu_info": "",
    "tests/macos/test_macos_system.py::TestMacosUI::test_desktop_matches_baseline": "",
}
# ==============================================================================
# MANUAL CASE ID MATCHING (END)
# ==============================================================================


def case_id_for(nodeid: str) -> Optional[str]:
    """Return the case id for a pytest nodeid, or None if it is not mapped.

    Ищет по полному nodeid, затем по «Класс::тест» и по имени теста — чтобы
    переезд файла не рвал мэтчинг.
    """
    if not nodeid:
        return None

    candidates = [nodeid]
    parts = nodeid.split("::")
    if len(parts) >= 2:
        candidates.append("::".join(parts[1:]))  # Класс::тест
        candidates.append(parts[-1])  # только имя теста

    normalized = {k.replace("\\", "/"): v for k, v in TEST_CASE_MAP.items()}
    for candidate in candidates:
        value = normalized.get(candidate.replace("\\", "/"))
        if value:
            return value

    # Ключ есть, но ID ещё не проставлен — это не «не найдено», а «не смэтчено»
    return None


def _id_sort_key(case_id: str) -> Tuple[str, int, str]:
    """Sort key that puts TC-9 before TC-10 instead of after it."""
    match = re.match(r"^(\D*)(\d+)(.*)$", case_id)
    if not match:
        return (case_id, 0, "")
    prefix, number, rest = match.groups()
    return (prefix.upper(), int(number), rest)


def mapped_cases(test_path: Optional[str] = None) -> List[Tuple[str, str]]:
    """Return (case_id, nodeid) for tests that HAVE a case id, sorted by id.

    Тесты без проставленного ID сюда не попадают: режим разработчика работает
    только с теми, что заведены в тестовой системе, — по ID их и называют.

    `test_path` отбирает по началу пути («tests/windows») — так список
    сужается до одной ВМ.
    """
    prefix = test_path.replace("\\", "/").lstrip("./").rstrip("/") if test_path else ""

    cases = [
        (case_id, nodeid)
        for nodeid, case_id in TEST_CASE_MAP.items()
        if case_id and (not prefix or nodeid.replace("\\", "/").startswith(prefix))
    ]
    return sorted(cases, key=lambda pair: (_id_sort_key(pair[0]), pair[1]))
