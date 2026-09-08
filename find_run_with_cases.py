#!/usr/bin/env python3
"""Find test runs with executions and test update."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_runs_with_cases():
    """Find test runs that have executions."""
    logger.info("=== Поиск тест-ранов с исполнениями ===")
    
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
        
        # Try to get runs where user is manager or default_tester
        # First, try to get user ID
        user_result = client.rpc.User.filter({"username": "autotest-local"})
        if not user_result:
            logger.error("Пользователь autotest-local не найден")
            return False
        user_id = user_result[0]["id"]
        logger.info("User ID: %d", user_id)
        
        # Try to find runs where this user is manager or default_tester
        # Filter by manager or default_tester
        testruns = client.rpc.TestRun.filter({"manager": user_id})
        logger.info("Найдено тест-ранов где manager=%d: %d", user_id, len(testruns))
        
        if not testruns:
            testruns = client.rpc.TestRun.filter({"default_tester": user_id})
            logger.info("Найдено тест-ранов где default_tester=%d: %d", user_id, len(testruns))
        
        # If still none, try to get any runs (without filter)
        if not testruns:
            logger.info("Попытка получить все тест-раны (без фильтра)")
            testruns = client.rpc.TestRun.filter({})
            logger.info("Всего тест-ранов: %d", len(testruns))
        
        # Check each run for executions
        runs_with_cases = []
        for tr in testruns[:10]:  # Check first 10
            run_id = tr["id"]
            try:
                executions = client.rpc.TestExecution.filter({"run": run_id})
                if executions:
                    runs_with_cases.append({
                        "id": run_id,
                        "summary": tr.get("summary", ""),
                        "executions_count": len(executions),
                        "first_exec": executions[0]
                    })
                    logger.info("Тест-ран %d: %s (исполнений: %d)", 
                               run_id, tr.get("summary", "")[:50], len(executions))
            except Exception as e:
                logger.warning("Ошибка при получении исполнений для рана %d: %s", run_id, e)
        
        if not runs_with_cases:
            logger.warning("Не найдено тест-ранов с исполнениями")
            return False
        
        # Take first run with executions
        run = runs_with_cases[0]
        run_id = run["id"]
        exec_data = run["first_exec"]
        
        logger.info("\n=== Тестируем обновление в тест-ране %d ===", run_id)
        logger.info("Исполнение: %s", exec_data)
        
        # Try to update first execution
        exec_id = exec_data["id"]
        
        # Get current status
        current_status = exec_data.get("status")
        logger.info("Текущий статус: %s", current_status)
        
        # Update to PASS (status_id = 1)
        update_data = {
            "status": 1,
            "comment": "Обновлено автоматически (тест интеграции)",
            "stop_date": "2026-09-08T12:00:00",
            "tested_by": user_id,
        }
        
        logger.info("Обновляем исполнение %d статусом PASS...", exec_id)
        client.rpc.TestExecution.update(exec_id, update_data)
        logger.info("✅ Исполнение успешно обновлено!")
        
        # Verify
        updated = client.rpc.TestExecution.filter({"id": exec_id})
        if updated:
            new_status = updated[0].get("status")
            logger.info("Новый статус: %s", new_status)
            
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = find_runs_with_cases()
    sys.exit(0 if success else 1)
