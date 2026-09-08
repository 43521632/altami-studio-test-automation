#!/usr/bin/env python3
"""Inspect test run 24 in detail."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def inspect_run():
    """Get all details of run 24."""
    logger.info("=== Детальный просмотр тест-рана 24 ===")
    
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
        
        run_id = 24
        
        # Get run data
        run_data = client.get_testrun(run_id)
        logger.info("Все ключи тест-рана:")
        for key, value in run_data.items():
            logger.info("  %s: %s (тип: %s)", key, value, type(value).__name__)
        
        # Check if there are any executions
        executions = client.rpc.TestExecution.filter({"run": run_id})
        logger.info("Найдено исполнений: %d", len(executions))
        
        if executions:
            logger.info("Первое исполнение:")
            for key, value in executions[0].items():
                logger.info("  %s: %s", key, value)
        else:
            logger.warning("Исполнений нет.")
            
            # Try to get cases from the plan? Or maybe we need to add cases?
            # Let's try to get the plan details to see what cases are in the plan
            plan_id = run_data.get("plan")
            if isinstance(plan_id, dict):
                plan_id = plan_id.get("id")
            if plan_id:
                logger.info("План ID: %s", plan_id)
                try:
                    plan_data = client.rpc.TestPlan.filter({"pk": plan_id})
                    if plan_data:
                        logger.info("Данные плана:")
                        for key, value in plan_data[0].items():
                            logger.info("  %s: %s", key, value)
                        # Try to get cases from plan
                        # There's no direct method, but we can get all cases in plan?
                        # Maybe there is TestPlan.get_cases? Not sure.
                        # Alternatively, we can try to add a case to the run.
                except Exception as e:
                    logger.error("Ошибка получения плана: %s", e)
            
            # Try to get cases from test run through another way
            # Maybe there is a method to list cases in a run?
            # According to Kiwi XML-RPC, there is TestRun.get_cases? Not sure.
            # Let's try to see if we can call TestRun.get_cases
            try:
                cases = client.rpc.TestRun.get_cases(run_id)
                logger.info("TestRun.get_cases вернул: %s", cases)
            except Exception as e:
                logger.warning("TestRun.get_cases не работает: %s", e)
        
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = inspect_run()
    sys.exit(0 if success else 1)
