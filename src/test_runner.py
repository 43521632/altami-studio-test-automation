import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

from .vm_manager import VMManager
from .qmp_client import QMPClientWrapper
from config.settings import LOGS_DIR, TEST_TIMEOUT

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
            'error': None,
            'steps': []
        }
        
        try:
            # Шаг 1: Проверка статуса ВМ
            logger.info(f"🔍 {vm_id}: Шаг 1 - Проверка статуса ВМ")
            if not self.vm_manager.check_vm_running(vm_id):
                result['status'] = 'skipped'
                result['error'] = 'ВМ не запущена'
                result['steps'].append({'step': 1, 'status': 'failed', 'message': 'ВМ не запущена'})
                logger.warning(f"⚠️ {vm_id}: ВМ не запущена, тест пропущен")
                return result
            result['steps'].append({'step': 1, 'status': 'passed', 'message': 'ВМ запущена'})
            
            # Шаг 2: Подключение к ВМ
            logger.info(f"🔗 {vm_id}: Шаг 2 - Подключение к QMP")
            client = await self.vm_manager.connect_to_vm(vm_id)
            result['steps'].append({'step': 2, 'status': 'passed', 'message': 'Подключение установлено'})
            
            # Шаг 3: Запуск теста
            logger.info(f"▶️ {vm_id}: Шаг 3 - Запуск теста {test_name}")
            try:
                test_result = await asyncio.wait_for(
                    test_func(client),
                    timeout=TEST_TIMEOUT
                )
                result['steps'].append({'step': 3, 'status': 'passed', 'message': 'Тест выполнен'})
            except asyncio.TimeoutError:
                result['steps'].append({'step': 3, 'status': 'failed', 'message': f'Таймаут {TEST_TIMEOUT}с'})
                raise Exception(f"Таймаут выполнения теста {TEST_TIMEOUT}с")
            
            result['status'] = 'passed' if test_result.get('success', False) else 'failed'
            result['output'] = test_result.get('output')
            
            logger.info(f"✅ {vm_id}: Тест {test_name} - {result['status']}")
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['steps'].append({'step': 3, 'status': 'error', 'message': str(e)})
            logger.error(f"❌ {vm_id}: Ошибка в тесте {test_name}: {e}")
        
        finally:
            # Шаг 4: Отключение от ВМ
            logger.info(f"🔌 {vm_id}: Шаг 4 - Отключение от QMP")
            try:
                await self.vm_manager.disconnect_from_vm(vm_id)
                result['steps'].append({'step': 4, 'status': 'passed', 'message': 'Отключено'})
            except Exception as e:
                result['steps'].append({'step': 4, 'status': 'error', 'message': str(e)})
        
        return result
    
    async def run_all_tests(self, test_suite, vm_ids: Optional[List[str]] = None) -> Dict:
        """Запуск всех тестов на всех ВМ"""
        results = {}
        
        if vm_ids is None:
            vm_ids = self.vm_manager.get_enabled_vm_ids()
        elif isinstance(vm_ids, str):
            vm_ids = [vm_ids]
        
        for vm_id in vm_ids:
            vm_results = []
            for test_name, test_func in test_suite.get_tests_for_vm(vm_id):
                result = await self.run_test_on_vm(vm_id, test_name, test_func)
                vm_results.append(result)
            results[vm_id] = vm_results
        
        self.results = results
        return results
    
    def save_results(self, output_path: Optional[str] = None) -> None:
        """Сохранение результатов в файл"""
        if output_path is None:
            output_path = LOGS_DIR / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': self.results
            }, f, indent=2)
        logger.info(f"📊 Результаты сохранены в {output_path}")
    
    def get_test_summary(self) -> Dict:
        """Получение сводки по тестам"""
        summary = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'error': 0,
            'by_vm': {}
        }
        
        for vm_id, vm_results in self.results.items():
            vm_summary = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'error': 0}
            for result in vm_results:
                vm_summary['total'] += 1
                summary['total'] += 1
                status = result['status']
                if status == 'passed':
                    vm_summary['passed'] += 1
                    summary['passed'] += 1
                elif status == 'failed':
                    vm_summary['failed'] += 1
                    summary['failed'] += 1
                elif status == 'skipped':
                    vm_summary['skipped'] += 1
                    summary['skipped'] += 1
                else:
                    vm_summary['error'] += 1
                    summary['error'] += 1
            summary['by_vm'][vm_id] = vm_summary
        
        return summary
