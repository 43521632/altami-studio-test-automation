"""Системные тесты для Windows"""

import logging
import pytest
from tests.base_test import BaseVMTest

logger = logging.getLogger(__name__)

@pytest.mark.windows
@pytest.mark.system
class TestWindowsSystem(BaseVMTest):
    vm_id = "windows11"
    
    async def test_windows_status(self):
        """Тест статуса Windows ВМ"""
        logger.info(f"🔍 {self.vm_id}: Проверка статуса")
        status = await self.get_vm_status()
        assert status['status'] == 'running', "ВМ не запущена"
        logger.info(f"✅ {self.vm_id}: Статус ВМ: {status['status']}")
    
    async def test_windows_cpu_info(self):
        """Тест информации о CPU"""
        logger.info(f"🔍 {self.vm_id}: Получение информации о CPU")
        cpu_info = await self.execute_qmp_command("query-cpus")
        assert len(cpu_info) > 0, "Нет информации о CPU"
        logger.info(f"✅ {self.vm_id}: Количество CPU: {len(cpu_info)}")
    
    async def test_windows_memory_info(self):
        """Тест информации о памяти"""
        logger.info(f"🔍 {self.vm_id}: Получение информации о памяти")
        memory_info = await self.execute_qmp_command("query-balloon")
        if memory_info:
            logger.info(f"✅ {self.vm_id}: Использование памяти: {memory_info.get('actual', 0) / 1024 / 1024:.0f} MB")
        else:
            logger.warning(f"⚠️ {self.vm_id}: Информация о памяти недоступна")
