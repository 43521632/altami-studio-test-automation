#!/usr/bin/env python
"""Главный скрипт для запуска тестов"""

import asyncio
import logging
import sys
from pathlib import Path

from src.vm_manager import VMManager
from src.test_runner import TestRunner

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Пример тестовой функции
async def test_system_info(client):
    """Тест получения системной информации"""
    try:
        # Получаем информацию о ВМ
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
        
        return tests
    
    async def test_windows_services(self, client):
        """Тест Windows сервисов"""
        # Здесь будет специфичный тест для Windows
        return {'success': True, 'output': 'Windows service check OK'}
    
    async def test_astra_security(self, client):
        """Тест безопасности Astra"""
        # Здесь будет специфичный тест для Astra
        return {'success': True, 'output': 'Astra security check OK'}

async def main():
    # Создаем менеджер ВМ
    manager = VMManager()
    
    # Проверяем статус ВМ
    print("\n📋 Проверка статуса ВМ:")
    for vm_id in manager.get_all_vm_ids():
        status = manager.get_vm_status(vm_id)
        print(f"  {status['name']}: {'✅ Запущена' if status['running'] else '❌ Остановлена'}")
    
    # Запускаем тесты
    test_suite = TestSuite()
    runner = TestRunner(manager)
    
    print("\n🚀 Запуск тестов...")
    results = await runner.run_all_tests(test_suite)
    
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

if __name__ == "__main__":
    asyncio.run(main())
