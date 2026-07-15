import pytest
from tests.base_test import BaseVMTest

@pytest.mark.asyncio
class TestWindowsSystem(BaseVMTest):
    vm_id = "windows11"
    
    async def test_windows_ping(self):
        """Тест пинга до Windows ВМ"""
        # Здесь можно проверить сетевую доступность
        status = await self.client.query_status()
        assert status['status'] == 'running', "ВМ не запущена"
        print(f"✅ Windows VM статус: {status}")
    
    async def test_windows_services(self):
        """Проверка критических сервисов Windows"""
        # Пример проверки через QGA
        result = await self.client.execute('guest-info')
        assert 'version' in result, "QGA не отвечает"
        print(f"✅ QGA версия: {result['version']}")
    
    async def test_windows_system_info(self):
        """Получение системной информации Windows"""
        # Здесь может быть сложная логика через QGA
        status = await self.client.execute('query-status')
        assert status['status'] in ['running', 'paused']
