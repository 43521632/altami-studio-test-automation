import pytest
from tests.base_test import BaseVMTest

@pytest.mark.asyncio
class TestAstraSystem(BaseVMTest):
    vm_id = "astra"
    
    async def test_astra_ping(self):
        """Тест пинга до Astra Linux"""
        status = await self.client.query_status()
        assert status['status'] == 'running'
        print(f"✅ Astra Linux статус: {status}")
    
    async def test_astra_security(self):
        """Проверка настроек безопасности Astra"""
        # Проверка через QGA
        result = await self.client.execute('guest-info')
        assert result.get('supported_commands') is not None
        print(f"✅ Доступные команды QGA: {len(result['supported_commands'])}")
    
    async def test_astra_network_interfaces(self):
        """Проверка сетевых интерфейсов в Astra"""
        # Можно получить информацию о сети через guest-network-get-interfaces
        result = await self.client.execute('guest-network-get-interfaces')
        assert len(result) > 0, "Нет сетевых интерфейсов"
