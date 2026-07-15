import pytest
import logging
from typing import Dict, Any
from src.vm_manager import VMManager
from src.qmp_client import QMPClientWrapper

logger = logging.getLogger(__name__)

class BaseVMTest:
    """Базовый класс для тестов ВМ"""
    
    vm_id: str = None
    vm_config: Dict = None
    
    @pytest.fixture(autouse=True)
    async def setup_vm(self, vm_manager: VMManager):
        """Фикстура для настройки ВМ перед тестом"""
        if not self.vm_id:
            pytest.skip("vm_id не указан")
        
        self.vm_config = vm_manager.get_vm_config(self.vm_id)
        if not self.vm_config:
            pytest.skip(f"Конфигурация для {self.vm_id} не найдена")
        
        self.client = vm_manager.get_vm_client(self.vm_id)
        
        # Проверка доступности ВМ
        try:
            status = await self.client.query_status()
            if status.get('status') != 'running':
                pytest.skip(f"ВМ {self.vm_id} не запущена (статус: {status.get('status')})")
        except Exception as e:
            pytest.skip(f"Не удалось подключиться к {self.vm_id}: {e}")
        
        logger.info(f"✅ Тест для {self.vm_id} готов к выполнению")
        yield
        # Очистка после теста
        logger.info(f"🧹 Очистка после теста для {self.vm_id}")
    
    async def check_vm_os(self, expected_os: str) -> bool:
        """Проверка ОС на ВМ (зависит от реализации)"""
        # Здесь можно реализовать проверку через QMP или другие методы
        return True
    
    async def execute_guest_command(self, command: str) -> Dict:
        """Выполнение команды в гостевой ОС через QGA"""
        # Пример для QEMU Guest Agent
        return await self.client.execute('guest-exec', {'path': command})
