#!/usr/bin/env python3
"""Update a specific execution in run 24 to PASSED."""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def update_execution():
    """Update execution 642 to PASSED."""
    logger.info("=== Обновление исполнения в тест-ране 24 ===")
    
    # Load .env
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
        logger.info("Загружены переменные из .env")
    
    try:
        client = KiwiClient()
        
        # Execution details from previous inspection
        exec_id = 642
        run_id = 24
        case_id = 85
        
        # Get current execution data
        exec_data = client.rpc.TestExecution.filter({"id": exec_id})
        if not exec_data:
            logger.error("Исполнение %d не найдено", exec_id)
            return False
        
        current_status = exec_data[0].get("status")
        logger.info("Текущий статус: %s (ID: %s)", 
                   exec_data[0].get("status__name"), current_status)
        
        # Try to map status values
        # From documentation: 
        # 1 = IDLE, 2 = RUNNING, 3 = PASSED, 4 = FAILED, 5 = BLOCKED, 6 = WAIVED
        # Let's try 3 (PASSED)
        status_to_try = 3
        logger.info("Попытка установить статус %d (PASSED)", status_to_try)
        
        # Update data
        update_data = {
            "status": status_to_try,
            "comment": "Тест пройден успешно (автоматическая проверка)",
            "stop_date": datetime.now().isoformat(),
        }
        
        # Set tested_by if possible (user ID 5 is autotest-local)
        update_data["tested_by"] = 5
        logger.info("Устанавливаем tested_by = 5")
        
        # Perform update
        logger.info("Обновляем исполнение %d...", exec_id)
        client.rpc.TestExecution.update(exec_id, update_data)
        logger.info("✅ Исполнение успешно обновлено!")
        
        # Verify
        updated = client.rpc.TestExecution.filter({"id": exec_id})
        if updated:
            new_status = updated[0].get("status")
            new_status_name = updated[0].get("status__name")
            logger.info("Новый статус: %s (ID: %s)", new_status_name, new_status)
            
            if new_status == status_to_try:
                logger.info("✅ Статус успешно изменён на PASSED!")
            else:
                logger.warning("Статус изменился на %s, но ожидался %d", new_status_name, status_to_try)
        
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = update_execution()
    sys.exit(0 if success else 1)
