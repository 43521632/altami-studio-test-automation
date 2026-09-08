#!/usr/bin/env python3
"""Test specific test run 24."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_run_24():
    """Test operations on run 24."""
    logger.info("=== Проверка тест-рана 24 ===")
    
    # Load .env if exists
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
        
        # Get test run details
        testrun_id = 24
        testrun = client.get_testrun(testrun_id)
        logger.info("Тест-ран %d:", testrun_id)
        logger.info("  Summary: %s", testrun.get("summary"))
        
        # Plan can be int or dict
        plan = testrun.get("plan")
        if isinstance(plan, dict):
            plan_name = plan.get("name")
        else:
            plan_name = plan  # int ID
        logger.info("  Plan: %s", plan_name)
        
        # Build can be int or dict
        build = testrun.get("build")
        if isinstance(build, dict):
            build_name = build.get("name")
        else:
            build_name = build  # int ID
        logger.info("  Build: %s", build_name)
        
        # Check assignment
        assignee = testrun.get("assignee")
        if isinstance(assignee, dict):
            assignee_name = assignee.get("username")
        else:
            assignee_name = assignee  # int ID
        logger.info("  Assignee: %s", assignee_name)
        
        # Check if assigned to autotest-local
        if assignee_name != "autotest-local":
            logger.warning("Тест-ран назначен на %s, а не на autotest-local", assignee_name)
            # Try to update assignment? For now just warn
        else:
            logger.info("✅ Тест-ран назначен на autotest-local")
        
        # Get executions for this run
        try:
            executions = client.rpc.TestExecution.filter({"run": testrun_id})
            logger.info("Найдено исполнений в тест-ране: %d", len(executions))
            
            if executions:
                # Take first execution
                first_exec = executions[0]
                case = first_exec.get("case")
                case_id = case.get("case_id") if isinstance(case, dict) else case
                case_pk = first_exec.get("case")
                if isinstance(case_pk, dict):
                    case_pk = case_pk.get("id")
                
                logger.info("Первый кейс: case_id=%s, pk=%s", case_id, case_pk)
                
                # Try to update this execution to PASS
                status_map = {"PASS": 1, "FAIL": 2, "SKIP": 3}
                status_id = 1  # PASS
                
                exec_id = first_exec["id"]
                update_data = {
                    "status": status_id,
                    "comment": "Тест пройден автоматически (проверка интеграции)",
                    "stop_date": "2026-09-08T12:00:00",
                }
                
                # Get user ID for tested_by
                try:
                    user_result = client.rpc.User.filter({"username": "autotest-local"})
                    if user_result:
                        update_data["tested_by"] = user_result[0]["id"]
                except Exception:
                    pass
                
                logger.info("Обновляем исполнение %d статусом PASS...", exec_id)
                client.rpc.TestExecution.update(exec_id, update_data)
                logger.info("✅ Исполнение успешно обновлено!")
                
                # Verify update
                updated = client.rpc.TestExecution.filter({"id": exec_id})
                if updated:
                    status = updated[0].get("status")
                    logger.info("Новый статус исполнения: %s", status)
                    
            else:
                logger.warning("В тест-ране нет исполнений")
                
        except Exception as e:
            logger.error("Ошибка при работе с исполнениями: %s", e)
            
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False
    
    logger.info("=== Проверка завершена ===")
    return True


if __name__ == "__main__":
    success = test_run_24()
    sys.exit(0 if success else 1)
