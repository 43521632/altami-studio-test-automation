#!/usr/bin/env python
"""Скрипт для проверки статуса существующих ВМ"""

import asyncio
import logging
from pathlib import Path
import sys

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vm_manager import VMManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def main():
    manager = VMManager()
    
    print("\n🔍 Статус виртуальных машин:")
    print("-" * 50)
    
    for vm_id in manager.get_all_vm_ids():
        status = manager.get_vm_status(vm_id)
        status_symbol = "✅" if status['running'] else "❌"
        print(f"{status_symbol} {status['name']}")
        print(f"   ID: {vm_id}")
        print(f"   QMP Socket: {status['qmp_socket']}")
        if status.get('pid'):
            print(f"   PID: {status['pid']}")
        print(f"   Статус: {'Запущена' if status['running'] else 'Остановлена'}")
        
        # Проверяем доступность QMP
        if status['running']:
            try:
                client = await manager.connect_to_vm(vm_id)
                qmp_status = await client.query_status()
                print(f"   QMP Статус: {qmp_status.get('status', 'unknown')}")
                await manager.disconnect_from_vm(vm_id)
            except Exception as e:
                print(f"   ⚠️ QMP недоступен: {e}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
