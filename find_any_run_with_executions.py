#!/usr/bin/env python3
"""Find any test run with executions and update one."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_and_update():
    """Find a test run with executions and update first execution."""
    logger.info("=== Поиск тест-рана с исполнениями ===")
    
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
        
        # Try to get all test runs (limit to 50)
        logger.info("Получаем список тест-ранов...")
        all_runs = client.rpc.TestRun.filter({})
        logger.info("Всего тест-ранов: %d", len(all_runs))
        
        # Take first 20
        runs_to_check = all_runs[:20]
        
        found_run = None
        found_exec = None
        
        for tr in runs_to_check:
            run_id = tr["id"]
            try:
                executions = client.rpc.TestExecution.filter({"run": run_id})
                if executions:
                    logger.info("Тест-ран %d: %s (исполнений: %d)", 
                               run_id, tr.get("summary", "")[:50], len(executions))
                    found_run = tr
                    found_exec = executions[0]
                    break
            except Exception as e:
                logger.warning("Ошибка при получении исполнений для рана %d: %s", run_id, e)
        
        if not found_run:
            logger.error("Не найдено тест-ранов с исполнениями в первых 20.")
            logger.info("Попробуем получить больше...")
            # Try to get more runs
            for tr in all_runs[20:50]:
                run_id = tr["id"]
                try:
                    executions = client.rpc.TestExecution.filter({"run": run_id})
                    if executions:
                        logger.info("Тест-ран %d: %s (исполнений: %d)", 
                                   run_id, tr.get("summary", "")[:50], len(executions))
                        found_run = tr
                        found_exec = executions[0]
                        break
                except Exception:
                    pass
        
        if not found_run:
            logger.error("Не найдено тест-ранов с исполнениями.")
            return False
        
        run_id = found_run["id"]
        exec_data = found_exec
        exec_id = exec_data["id"]
        
        logger.info("\n=== Обновляем исполнение в тест-ране %d ===", run_id)
        logger.info("Исполнение ID: %d", exec_id)
        logger.info("Текущий статус: %s", exec_data.get("status"))
        
        # Get current user ID (try to find it)
        user_id = None
        try:
            # Try to get user by username using a different approach? 
            # Actually we might not need tested_by if we skip it
            pass
        except Exception:
            pass
        
        # Update to PASS (status_id = 1)
        update_data = {
            "status": 1,
            "comment": "Обновлено автоматически (тест интеграции) - PASS",
            "stop_date": "2026-09-08T12:00:00",
        }
        
        # Try to set tested_by if we can get user ID
        try:
            # Maybe we can get user ID from the run's manager or default_tester
            manager = found_run.get("manager")
            if isinstance(manager, dict):
                user_id = manager.get("id")
            elif isinstance(manager, int):
                user_id = manager
            if user_id:
                update_data["tested_by"] = user_id
                logger.info("Устанавливаем tested_by = %d", user_id)
        except Exception:
            pass
        
        logger.info("Обновляем исполнение %d статусом PASS...", exec_id)
        client.rpc.TestExecution.update(exec_id, update_data)
        logger.info("✅ Исполнение успешно обновлено!")
        
        # Verify
        updated = client.rpc.TestExecution.filter({"id": exec_id})
        if updated:
            new_status = updated[0].get("status")
            logger.info("Новый статус исполнения: %s", new_status)
        
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = find_and_update()
    sys.exit(0 if success else 1)
