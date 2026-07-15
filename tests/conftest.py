"""Общие фикстуры для pytest"""

import asyncio
import logging
import pytest
from typing import Dict, AsyncGenerator

from src.vm_manager import VMManager
from config.settings import VMS_CONFIG_PATH

logger = logging.getLogger(__name__)

# Глобальный менеджер ВМ
_vm_manager = None

@pytest.fixture(scope="session")
def vm_manager() -> VMManager:
    """Фикстура для менеджера ВМ"""
    global _vm_manager
    if _vm_manager is None:
        _vm_manager = VMManager(VMS_CONFIG_PATH)
    return _vm_manager

@pytest.fixture(scope="function")
async def vm_client(vm_manager: VMManager, vm_id: str):
    """Фикстура для клиента ВМ"""
    client = await vm_manager.connect_to_vm(vm_id)
    yield client
    await vm_manager.disconnect_from_vm(vm_id)

@pytest.fixture(scope="function")
def vm_config(vm_manager: VMManager, vm_id: str) -> Dict:
    """Фикстура для конфигурации ВМ"""
    return vm_manager.get_vm_config(vm_id)

# Маркеры для тестов
def pytest_configure(config):
    config.addinivalue_line("markers", "windows: Тесты для Windows ВМ")
    config.addinivalue_line("markers", "astra: Тесты для Astra Linux ВМ")
    config.addinivalue_line("markers", "macos: Тесты для macOS ВМ")
    config.addinivalue_line("markers", "network: Сетевые тесты")
    config.addinivalue_line("markers", "security: Тесты безопасности")
    config.addinivalue_line("markers", "system: Системные тесты")

@pytest.fixture(autouse=True)
def test_logging(request):
    """Фикстура для логирования тестов"""
    logger.info(f"🏃 Запуск теста: {request.node.nodeid}")
    yield
    logger.info(f"✅ Тест завершен: {request.node.nodeid}")
