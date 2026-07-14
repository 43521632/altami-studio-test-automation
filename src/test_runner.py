import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

from .vm_manager import VMManager
from .qmp_client import QMPClientWrapper

logger = logging.getLogger(__name__)

class TestRunner:
    """Запуск тестов на ВМ"""
    
    def __init__(self, vm_manager: VMManager):
        self.vm_manager = vm_manager
        self.results = {}
    
    async def run_test_on_vm(self, vm_id: str, test_name: str, test_func) -> Dict:
        """Запуск отдельного теста на ВМ"""
        result = {
            'vm_id': vm_id,
            'test_name': test_name,
            'timestamp': datetime.now().isoformat(),
            'status': 'unknown',
            'output': None,
            'error': None
        }
        
        try:
            # Проверяем, что ВМ запущена
            if not self.vm_manager.check_vm_running(vm_id):
                result['status'] = 'skipped'
                result['error'] = 'ВМ не запущена'
                logger.warning(f"⚠️ {vm_id}: ВМ не запущена, тест пропущен")
                return result
            
            # Подключаемся к ВМ
            client = await self.vm_manager.connect_to_vm(vm_id)
            
            # Запускаем тест
            logger.info(f"▶️ {vm_id}: Запуск теста {test_name}")
            test_result = await test_func(client)
            
            result['status'] = 'passed' if test_result.get('success', False) else 'failed'
            result['output'] = test_result.get('output')
            
            logger.info(f"✅ {vm_id}: Тест {test_name} - {result['status']}")
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"❌ {vm_id}: Ошибка в тесте {test_name}: {e}")
        
        return result
    
    async def run_all_tests(self, test_suite) -> Dict:
        """Запуск всех тестов на всех ВМ"""
        results = {}
        
        for vm_id in self.vm_manager.get_enabled_vm_ids():
            vm_results = []
            for test_name, test_func in test_suite.get_tests_for_vm(vm_id):
                result = await self.run_test_on_vm(vm_id, test_name, test_func)
                vm_results.append(result)
            results[vm_id] = vm_results
        
        self.results = results
        return results
    
    def save_results(self, output_path: str = "logs/test_results.json") -> None:
        """Сохранение результатов в файл"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': self.results
            }, f, indent=2)
        logger.info(f"📊 Результаты сохранены в {output_path}")
