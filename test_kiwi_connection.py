#!/usr/bin/env python3
"""Тестовый скрипт для проверки подключения к Kiwi TCMS."""

import os
import sys
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from utils.kiwi_client import KiwiClient, KiwiReporter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_connection():
    """Test Kiwi connection and basic operations."""
    logger.info("=== Тест подключения к Kiwi TCMS ===")
    
    # Проверяем наличие переменных окружения
    url = os.environ.get("KIWI_URL")
    user = os.environ.get("KIWI_USER")
    password = os.environ.get("KIWI_PASSWORD")
    testrun_id = os.environ.get("KIWI_TESTRUN_ID")
    
    # Если нет переменных, пробуем загрузить из .env
    if not all([url, user, password]):
        logger.info("Подгружаем из .env файла, если есть...")
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
            url = os.environ.get("KIWI_URL")
            user = os.environ.get("KIWI_USER")
            password = os.environ.get("KIWI_PASSWORD")
            testrun_id = os.environ.get("KIWI_TESTRUN_ID")
            logger.info("Загружены переменные из .env")
    
    # Если всё ещё нет, запрашиваем у пользователя
    if not all([url, user, password]):
        logger.error("Не заданы KIWI_URL, KIWI_USER или KIWI_PASSWORD")
        url = input("Введите KIWI_URL (например, https://kiwitcms.altami.ru): ").strip()
        user = input("Введите KIWI_USER: ").strip()
        password = input("Введите KIWI_PASSWORD: ").strip()
        os.environ["KIWI_URL"] = url
        os.environ["KIWI_USER"] = user
        os.environ["KIWI_PASSWORD"] = password
    
    # If no testrun_id is set, we'll just test connection without it
    if not testrun_id:
        logger.info("KIWI_TESTRUN_ID не задан, пропускаем проверку тест-рана")
    else:
        os.environ["KIWI_TESTRUN_ID"] = testrun_id
    
    if not all([url, user, password]):
        logger.error("Не заданы KIWI_URL, KIWI_USER или KIWI_PASSWORD")
        logger.info("Подгружаем из .env файла, если есть...")
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
            # Обновляем переменные
            url = os.environ.get("KIWI_URL")
            user = os.environ.get("KIWI_USER")
            password = os.environ.get("KIWI_PASSWORD")
            testrun_id = os.environ.get("KIWI_TESTRUN_ID")
            logger.info("Загружены переменные из .env")
    
    if not all([url, user, password]):
        logger.error("Не заданы KIWI_URL, KIWI_USER или KIWI_PASSWORD")
        return False
    
    logger.info("URL: %s", url)
    logger.info("User: %s", user)
    logger.info("TestRun ID: %s", testrun_id or "(не задан)")
    
    try:
        # Создаём клиент
        client = KiwiClient(url, user, password)
        logger.info("✅ Клиент создан успешно")
        
        # Проверяем, что RPC работает
        # Попробуем получить список пользователей (простая операция)
        try:
            users = client.rpc.User.filter({})
            logger.info("✅ RPC работает, найдено пользователей: %d", len(users[:5]))
        except Exception as e:
            logger.warning("Не удалось получить список пользователей: %s", e)
        
        # Если задан testrun_id, пробуем получить его
        if testrun_id:
            try:
                testrun_id_int = int(testrun_id)
                testrun = client.get_testrun(testrun_id_int)
                logger.info("✅ Получен тест-ран %d: %s", testrun_id_int, testrun.get("summary", "без названия"))
                
                # Проверяем назначение
                is_assigned = client.is_assigned_to_user(testrun_id_int, user)
                logger.info("Назначен на пользователя %s: %s", user, is_assigned)
                
                # Пробуем получить ревизию
                revision = client.get_build_revision(testrun_id_int)
                logger.info("Ревизия из тест-рана: %s", revision or "(не найдена)")
                
                # Пробуем получить исполнения для какого-нибудь кейса
                # Сначала получим список кейсов в тест-ране
                try:
                    # TestRun.get_cases не работает напрямую через RPC, используем filter
                    # Получаем все исполнения для этого рана
                    executions = client.rpc.TestExecution.filter({"run": testrun_id_int})
                    logger.info("Найдено исполнений в тест-ране: %d", len(executions))
                    if executions:
                        case_id = executions[0].get("case_id")
                        if case_id:
                            logger.info("Пример кейса: case_id=%s", case_id)
                            # Пробуем получить исполнения для этого кейса
                            case_execs = client.get_test_executions_for_case(testrun_id_int, case_id)
                            logger.info("Исполнений для кейса %s: %d", case_id, len(case_execs))
                except Exception as e:
                    logger.warning("Не удалось получить исполнения: %s", e)
                    
            except ValueError as e:
                logger.error("KIWI_TESTRUN_ID должен быть числом: %s", e)
            except Exception as e:
                logger.error("Ошибка при получении тест-рана: %s", e)
        else:
            # Пробуем получить список последних тест-ранов
            try:
                # Получаем тест-раны, назначенные на этого пользователя
                testruns = client.rpc.TestRun.filter({"assignee__username": user})
                logger.info("Найдено тест-ранов для пользователя %s: %d", user, len(testruns))
                if testruns:
                    logger.info("Последние 3 тест-рана:")
                    for tr in testruns[:3]:
                        logger.info("  - ID %d: %s", tr.get("id"), tr.get("summary", "без названия"))
            except Exception as e:
                logger.warning("Не удалось получить список тест-ранов: %s", e)
        
        logger.info("=== Тест успешно завершён ===")
        return True
        
    except Exception as e:
        logger.error("❌ Ошибка при тестировании подключения: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
