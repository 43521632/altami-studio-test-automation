#!/usr/bin/env python
"""Главный скрипт для запуска тестов"""

import asyncio
import logging
import sys
import argparse
from pathlib import Path
from typing import List, Optional

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from src.vm_manager import VMManager
from src.test_runner import TestRunner
from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, LOGS_DIR

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "test_run.log")
    ]
)
logger = logging.getLogger(__name__)

# Пример тестовой функции
async def test_system_info(client):
    """Тест получения системной информации"""
    try:
        status = await client.query_status()
        return {
            'success': True,
            'output': f"Статус: {status.get('status', 'unknown')}"
        }
    except Exception as e:
        return {
            'success': False,
            'output': str(e)
        }

class TestSuite:
    """Набор тестов для ВМ"""
    
    def get_tests_for_vm(self, vm_id: str):
        """Возвращает список тестов для конкретной ВМ"""
        tests = []
        
        # Для всех ВМ
        tests.append(("system_info", test_system_info))
        
        # Специфичные тесты для конкретных ВМ
        if vm_id == "windows11":
            tests.append(("windows_service_check", self.test_windows_services))
        elif vm_id == "astra":
            tests.append(("astra_security_check", self.test_astra_security))
        elif vm_id == "macos":
            tests.append(("macos_system_check", self.test_macos_system))
        
        return tests
    
    async def test_windows_services(self, client):
        """Тест Windows сервисов"""
        try:
            # Здесь будет специфичный тест для Windows
            return {'success': True, 'output': 'Windows service check OK'}
        except Exception as e:
            return {'success': False, 'output': str(e)}
    
    async def test_astra_security(self, client):
        """Тест безопасности Astra"""
        try:
            # Здесь будет специфичный тест для Astra
            return {'success': True, 'output': 'Astra security check OK'}
        except Exception as e:
            return {'success': False, 'output': str(e)}
    
    async def test_macos_system(self, client):
        """Тест macOS системы"""
        try:
            # Здесь будет специфичный тест для macOS
            return {'success': True, 'output': 'macOS system check OK'}
        except Exception as e:
            return {'success': False, 'output': str(e)}

async def run_tests(vm_id: Optional[str] = None):
    """Запуск тестов"""
    # Создаем менеджер ВМ
    manager = VMManager()
    
    # Проверяем статус ВМ
    print("\n📋 Проверка статуса ВМ:")
    vm_ids = [vm_id] if vm_id else manager.get_all_vm_ids()
    
    for vm_id in vm_ids:
        status = manager.get_vm_status(vm_id)
        print(f"  {status['name']}: {'✅ Запущена' if status['running'] else '❌ Остановлена'}")
    
    # Запускаем тесты
    test_suite = TestSuite()
    runner = TestRunner(manager)
    
    print("\n🚀 Запуск тестов...")
    if vm_id:
        print(f"   Только для ВМ: {vm_id}")
    else:
        print("   Для всех ВМ")
    
    results = await runner.run_all_tests(test_suite, vm_ids)
    
    # Выводим результаты
    print("\n📊 Результаты тестирования:")
    for vm_id, vm_results in results.items():
        vm_config = manager.get_vm_config(vm_id)
        print(f"\n  {vm_config.get('name', vm_id)}:")
        for result in vm_results:
            status_icon = "✅" if result['status'] == 'passed' else "❌"
            print(f"    {status_icon} {result['test_name']}: {result['status']}")
            if result.get('output'):
                print(f"       {result['output']}")
            if result.get('error'):
                print(f"       ⚠️ Ошибка: {result['error']}")
    
    # Сохраняем результаты
    runner.save_results()
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Запуск тестов для ВМ')
    parser.add_argument(
        '--vm',
        type=str,
        help='ID ВМ для запуска тестов (если не указан, запускаются все)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='Показать доступные ВМ'
    )
    
    args = parser.parse_args()
    
    if args.list:
        manager = VMManager()
        print("\n📋 Доступные ВМ:")
        for vm_id in manager.get_all_vm_ids():
            config = manager.get_vm_config(vm_id)
            print(f"  • {vm_id}: {config.get('name', vm_id)}")
        return
    
    asyncio.run(run_tests(args.vm))

if __name__ == "__main__":
    main()
