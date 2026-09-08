#!/usr/bin/env python3
"""List all available statuses in Kiwi TCMS."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def list_statuses():
    """List all test execution statuses."""
    logger.info("=== Список статусов Kiwi TCMS ===")
    
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
        
        # Get all statuses
        statuses = client.rpc.TestExecutionStatus.filter({})
        logger.info("Найдено статусов: %d", len(statuses))
        
        logger.info("\nДоступные статусы:")
        logger.info("%-10s %-20s %-10s" % ("ID", "Name", "Weight"))
        logger.info("-" * 45)
        for st in statuses:
            logger.info("%-10d %-20s %-10d" % (st.get("id"), st.get("name"), st.get("weight")))
        
        return True
        
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = list_statuses()
    sys.exit(0 if success else 1)
