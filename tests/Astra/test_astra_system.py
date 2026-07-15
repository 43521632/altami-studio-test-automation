"""Системные тесты для Astra Linux"""

import logging
import pytest
from tests.base_test import BaseVMTest

logger = logging.getLogger(__name__)

@pytest.mark.astra
@pytest.mark.system
class TestAstraSystem(BaseVMTest):
    vm_id = "astra"
    
    async def test_astra_status(self):
        """Тест статуса Astra Linux"""
        logger.info(f"🔍 {self.vm_id}: Проверка статуса")
        status = await self.get_vm_status()
        assert status['status'] == 'running', "ВМ не запущена"
        logger.info(f"✅ {self.vm_id}: Статус ВМ: {status['status']}")
    
    async def test_astra_cpu_info(self):
        """Тест информации о CPU"""
        logger.info(f"🔍 {self.vm_id}: Получение информации о CPU")
        cpu_info = await self.execute_qmp_command("query-cpus")
        assert len(cpu_info) > 0, "Нет информации о CPU"
        logger.info(f"✅ {self.vm_id}: Количество CPU: {len(cpu_info)}")
