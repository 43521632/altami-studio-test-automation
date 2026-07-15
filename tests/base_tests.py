"""Базовый класс для тестов ВМ"""

import logging
import pytest
from typing import Dict, Any, Optional

from src.vm_manager import VMManager
from src.qmp_client import QMPClientWrapper

logger = logging.getLogger(__name__)

class BaseVMTest:
    """Базовый класс для тестов ВМ"""
    
    vm_id: Optional[str] = None
    vm_config: Optional[Dict] = None
    client: Optional[QMPClientWrapper] = None
    
    @pytest.fixture(autouse=True)
    async def setup_vm(self, vm_manager: VMManager):
        """Фикстура для настройки ВМ перед тестом"""
        if not self.vm_id:
            pytest.skip("vm_id не указан")
        
        self.vm_config = vm_manager.get_vm_config(self.vm_id)
        if not self.vm_config:
            pytest.skip(f"Конфигурация для {self.vm_id} не найдена")
        
        # Проверка, что ВМ запущена
        if not vm_manager.check_vm_running(self.vm_id):
            pytest.skip(f"ВМ {self.vm_id} не запущена")
        
        # Подключение к ВМ
        try:
            self.client = await vm_manager.connect_to_vm(self.vm_id)
            status = await self.client.query_status()
            if status.get('status') != 'running':
                pytest.skip(f"ВМ {self.vm_id} не запущена (статус: {status.get('status')})")
        except Exception as e:
            pytest.skip(f"Не удалось подключиться к {self.vm_id}: {e}")
        
        logger.info(f"✅ {self.vm_id}: Тест готов к выполнению")
        yield
        # Очистка после теста
        logger.info(f"🧹 {self.vm_id}: Очистка после теста")
        await vm_manager.disconnect_from_vm(self.vm_id)
    
    async def execute_qmp_command(self, command: str, **kwargs) -> Dict:
        """Выполнение команды QMP"""
        if not self.client:
            raise Exception("Клиент не инициализирован")
        return await self.client.execute(command, kwargs if kwargs else None)
    
    async def get_vm_status(self) -> Dict:
        """Получение статуса ВМ"""
        return await self.execute_qmp_command("query-status")
