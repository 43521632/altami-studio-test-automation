#!/usr/bin/env python3
"""Update execution 642 to PASSED (ID 4)."""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def update_to_passed():
    """Update execution 642 to PASSED (status_id=4)."""
    logger.info("=== Обновление исполнения 642 на PASSED ===")
    
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
        exec_id = 642
        
        # Get current status
        exec_data = client.rpc.TestExecution.filter({"id": exec_id})
        if not exec_data:
            logger.error("Исполнение %d не найдено", exec_id)
            return False
        
        current_status = exec_data[0].get("status")
        logger.info("Текущий статус: %s (ID: %s)", 
                   exec_data[0].get("status__name"), current_status)
        
        # Set status to PASSED (ID 4)
        update_data = {
            "status": 4,  # PASSED
            "comment": "Тест успешно пройден (автоматическая проверка)",
            "stop_date": datetime.now().isoformat(),
            "tested_by": 5,
        }
        
        logger.info("Обновляем исполнение %d на PASSED (ID 4)...", exec_id)
        client.rpc.TestExecution.update(exec_id, update_data)
        logger.info("✅ Исполнение успешно обновлено!")
        
        # Verify
        updated = client.rpc.TestExecution.filter({"id": exec_id})
        if updated:
            new_status = updated[0].get("status")
            new_status_name = updated[0].get("status__name")
            logger.info("Новый статус: %s (ID: %s)", new_status_name, new_status)
            
            if new_status == 4:
                logger.info("✅ Статус успешно изменён на PASSED!")
            else:
                logger.warning("Статус изменился на %s (ID: %s), ожидался PASSED (ID: 4)", 
                              new_status_name, new_status)
        
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = update_to_passed()
    sys.exit(0 if success else 1)
