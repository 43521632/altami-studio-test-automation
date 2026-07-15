#!/bin/bash
# Скрипт для проверки статуса ВМ

echo "=== Статус виртуальных машин ==="
echo

# Проверка QMP сокетов
echo "QMP сокеты:"
ls -la /tmp/qmp-*.sock 2>/dev/null || echo "  Нет активных QMP сокетов"
echo

# Проверка процессов QEMU
echo "Процессы QEMU:"
ps aux | grep -E "qemu-system|qemu" | grep -v grep || echo "  Нет процессов QEMU"
echo

# Проверка через Python скрипт
echo "Проверка через Python:"
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
from src.vm_manager import VMManager
import asyncio

async def check():
    manager = VMManager()
    for vm_id in manager.get_all_vm_ids():
        status = manager.get_vm_status(vm_id)
        symbol = '✅' if status['running'] else '❌'
        print(f'{symbol} {status[\"name\"]}: {\"Запущена\" if status[\"running\"] else \"Остановлена\"}')

asyncio.run(check())
"
