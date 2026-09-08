"""Kiwi TCMS API client using official tcms-api library."""

import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any

from tcms_api import TCMS

logger = logging.getLogger(__name__)


class KiwiClient:
    """Client for Kiwi TCMS API using tcms-api."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = (base_url or os.environ.get("KIWI_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError("KIWI_URL не задан")

        self.username = username or os.environ.get("KIWI_USER")
        self.password = password or os.environ.get("KIWI_PASSWORD")
        if not self.username or not self.password:
            raise ValueError("KIWI_USER и KIWI_PASSWORD должны быть заданы")

        # Initialize RPC client
        # TCMS expects full URL to XML-RPC endpoint
        # For Kiwi TCMS, the endpoint is usually /xml-rpc/
        xmlrpc_url = f"{self.base_url}/xml-rpc/"
        # TCMS() returns a proxy object that has .exec for XML-RPC calls
        self.rpc: Any = TCMS(xmlrpc_url, self.username, self.password).exec
        
        # Explicitly login to authenticate the session
        try:
            self.rpc.Auth.login(self.username, self.password)
            logger.info("Аутентификация в Kiwi TCMS успешна")
        except Exception as e:
            logger.warning("Ошибка при явной аутентификации: %s", e)
        
        logger.info("Подключение к Kiwi TCMS: %s", self.base_url)

    def get_testrun(self, testrun_id: int) -> dict:
        """Get test run details by ID."""
        try:
            # TestRun.filter returns list of dicts
            result = self.rpc.TestRun.filter({"pk": testrun_id})
            if not result:
                raise ValueError(f"Тест-ран с ID {testrun_id} не найден")
            return result[0]
        except Exception as e:
            logger.error("Не удалось получить тест-ран %d: %s", testrun_id, e)
            raise

    def _get_field_value(self, data: dict, field: str, default=None):
        """Get field value, handling both dict and int/string cases."""
        value = data.get(field)
        if isinstance(value, dict):
            # Try common name fields
            return value.get("name") or value.get("username") or value
        return value if value is not None else default

    def is_assigned_to_user(self, testrun_id: int, username: str) -> bool:
        """Check if the test run is assigned to the given user."""
        data = self.get_testrun(testrun_id)
        assignee = data.get("assignee")
        if not assignee:
            logger.warning("В тест-ране %d нет поля 'assignee'", testrun_id)
            return False
        # assignee can be a dict with 'username' or a string
        if isinstance(assignee, dict):
            assignee = assignee.get("username")
        return assignee == username

    def get_build_revision(self, testrun_id: int) -> Optional[str]:
        """Extract build revision from a test run."""
        if not self.is_assigned_to_user(testrun_id, self.username):
            logger.warning(
                "Тест-ран %d назначен не на пользователя %s — пропускаем",
                testrun_id, self.username
            )
            return None

        data = self.get_testrun(testrun_id)
        build = data.get("build")
        if not build:
            logger.warning("В тест-ране %d нет поля 'build'", testrun_id)
            return None

        # build can be a dict with 'name' or a string
        if isinstance(build, dict):
            return build.get("name")
        if isinstance(build, str):
            return build

        logger.warning("Неизвестный формат поля 'build' в тест-ране %d", testrun_id)
        return None

    def get_test_executions_for_case(self, testrun_id: int, case_id: str) -> List[dict]:
        """Get test executions for a specific case in a test run."""
        try:
            # Get the case PK by its ID
            case_pk = self._get_case_pk_by_id(case_id)
            if not case_pk:
                logger.error("Кейс с ID %s не найден", case_id)
                return []

            executions = self.rpc.TestExecution.filter({
                "run": testrun_id,
                "case": case_pk,
            })
            return executions
        except Exception as e:
            logger.error("Ошибка при получении TestExecution для кейса %s: %s", case_id, e)
            return []

    def _get_case_pk_by_id(self, case_id: str) -> Optional[int]:
        """Get the numeric PK of a test case by its ID (e.g., 'TC-85')."""
        try:
            # Try to parse numeric part
            if case_id.startswith("TC-"):
                numeric_id = case_id.split("-")[1]
            else:
                numeric_id = case_id

            # Search for case by ID (which is stored in the 'case_id' field in Kiwi)
            # Note: The API might use different field names. Let's try both.
            result = self.rpc.TestCase.filter({"case_id": numeric_id})
            if not result:
                # Try with the full string
                result = self.rpc.TestCase.filter({"case_id": case_id})
            if result:
                return result[0]["id"]

            logger.warning("Кейс с ID %s не найден", case_id)
            return None
        except Exception as e:
            logger.error("Ошибка при поиске кейса %s: %s", case_id, e)
            return None

    def add_case_result(
        self,
        testrun_id: int,
        case_id: str,
        status: str,
        comment: str = "",
        attachments: Optional[List[Path]] = None,
    ) -> bool:
        """Add a result for a specific test case in a test run.

        Args:
            testrun_id: ID of the test run in Kiwi
            case_id: Case ID (e.g., "TC-85")
            status: "PASS", "FAIL", "SKIP", "ERROR"
            comment: Optional comment or error message
            attachments: List of file paths to attach

        Returns:
            True if successful, False otherwise
        """
        try:
            # Map status to Kiwi status IDs (based on actual Kiwi statuses)
            # 4=PASSED, 5=FAILED, 6=BLOCKED, 7=ERROR, 8=WAIVED
            status_map = {
                "PASS": 4,   # PASSED
                "FAIL": 5,   # FAILED
                "ERROR": 7,  # ERROR
                "SKIP": 6,   # BLOCKED (or 8 WAIVED depending on interpretation)
            }
            status_id = status_map.get(status, 5)  # default to FAILED

            # Find executions for this case in the test run
            executions = self.get_test_executions_for_case(testrun_id, case_id)
            if not executions:
                logger.warning(
                    "Не найдено исполнений для кейса %s в тест-ране %d. Пропускаем.",
                    case_id, testrun_id
                )
                return False

            # Update the first execution (there should be only one per case per run)
            execution = executions[0]
            execution_id = execution["id"]

            # Prepare update data
            update_data = {
                "status": status_id,
                "comment": comment,
                "stop_date": datetime.now().isoformat(),
            }

            # If we have a tester, set tested_by (optional)
            # We need to get the user ID
            try:
                user_result = self.rpc.User.filter({"username": self.username})
                if user_result:
                    update_data["tested_by"] = user_result[0]["id"]
            except Exception:
                pass  # Ignore if we can't set tested_by

            # Update the execution
            self.rpc.TestExecution.update(execution_id, update_data)
            logger.info(
                "Обновлён результат для кейса %s в тест-ране %d: %s",
                case_id, testrun_id, status
            )

            # Upload attachments if any
            if attachments:
                for attach_path in attachments:
                    if attach_path.exists():
                        self.upload_attachment(testrun_id, case_id, attach_path)

            return True

        except Exception as e:
            logger.error("Ошибка при добавлении результата для кейса %s: %s", case_id, e)
            return False

    def close_testrun(self, testrun_id: int) -> bool:
        """Close the test run by setting stop_date."""
        try:
            self.rpc.TestRun.update(testrun_id, {
                "stop_date": datetime.now().isoformat()
            })
            logger.info("Тест-ран %d закрыт", testrun_id)
            return True
        except Exception as e:
            logger.error("Ошибка при закрытии тест-рана %d: %s", testrun_id, e)
            return False

    def upload_attachment(
        self,
        testrun_id: int,
        case_id: str,
        file_path: Path,
        description: str = "",
    ) -> bool:
        """Upload an attachment for a test case result."""
        try:
            if not file_path.exists():
                logger.warning("Файл для аттачмента не найден: %s", file_path)
                return False

            with open(file_path, "rb") as f:
                file_content = f.read()

            # Encode to Base64
            b64_content = base64.b64encode(file_content).decode("utf-8")

            # Upload attachment to the test run
            self.rpc.TestRun.add_attachment(
                testrun_id,
                file_path.name,
                b64_content
            )
            logger.info("Загружен аттачмент для кейса %s: %s", case_id, file_path.name)
            return True

        except Exception as e:
            logger.error("Ошибка при загрузке аттачмента %s: %s", file_path, e)
            return False


# Helper functions for backward compatibility with existing code

def get_revision_from_kiwi(testrun_id: int) -> Optional[str]:
    """Helper to get revision from Kiwi by test run ID."""
    try:
        client = KiwiClient()
        return client.get_build_revision(testrun_id)
    except Exception as e:
        logger.error("Ошибка при получении ревизии из Kiwi: %s", e)
        return None


class KiwiReporter:
    """Report test results to Kiwi TCMS."""

    def __init__(self, client: Optional[KiwiClient] = None):
        self.client = client or KiwiClient()
        self.testrun_id = os.environ.get("KIWI_TESTRUN_ID")
        self.results: List[dict] = []
        self.enabled = os.environ.get("KIWI_REPORTING_ENABLED", "true").lower() == "true"
        self.skip_if_unavailable = os.environ.get("KIWI_SKIP_IF_UNAVAILABLE", "true").lower() == "true"

    def add_result(self, test_name: str, status: str, duration: float, message: str = "") -> None:
        """Add a single test result."""
        self.results.append({
            "test_name": test_name,
            "status": status,  # PASS, FAIL, ERROR, SKIP
            "duration": duration,
            "message": message,
        })

    def submit(self) -> bool:
        """Submit all results to Kiwi TCMS."""
        if not self.enabled:
            logger.info("Отправка в Kiwi отключена (KIWI_REPORTING_ENABLED=false)")
            return True

        if not self.results:
            logger.info("Нет результатов для отправки")
            return True

        try:
            # If we have a testrun_id, update it
            if self.testrun_id:
                self._update_testrun()
            else:
                # No testrun_id provided — we can't create one automatically
                logger.warning("KIWI_TESTRUN_ID не задан, создание тест-рана не поддерживается")
                self._save_local()
                return True
            return True
        except Exception as e:
            logger.error("Ошибка при отправке результатов в Kiwi: %s", e)
            if self.skip_if_unavailable:
                self._save_local()
                return True
            else:
                raise

    def _update_testrun(self) -> None:
        """Update existing test run with results."""
        testrun_id = int(self.testrun_id)
        for result in self.results:
            # Here we need to map test_name to case_id
            # This is a simplified version — the actual plugin (pytest_kiwi_plugin) will call
            # add_case_result directly, so this method is just a fallback.
            logger.info(
                "[Kiwi] Результат для теста %s: %s (run %d)",
                result["test_name"], result["status"], testrun_id
            )

        # Close the test run after all results
        self.client.close_testrun(testrun_id)

    def _save_local(self) -> None:
        """Save results to a local JSON file as fallback."""
        import json
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kiwi_results_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump({
                "testrun_id": self.testrun_id,
                "results": self.results,
                "timestamp": timestamp,
            }, f, indent=2)
        logger.info("Результаты сохранены локально: %s", filename)

    def add_case_result(
        self,
        testrun_id: int,
        case_id: str,
        status: str,
        comment: str = "",
        attachments: Optional[List[Path]] = None,
    ) -> bool:
        """Add a result for a specific test case in a test run."""
        if not self.enabled:
            logger.info("Отправка в Kiwi отключена, результат для кейса %s не отправлен", case_id)
            return True

        try:
            return self.client.add_case_result(testrun_id, case_id, status, comment, attachments)
        except Exception as e:
            logger.error("Ошибка при добавлении результата для кейса %s: %s", case_id, e)
            if self.skip_if_unavailable:
                return True
            raise

    def close_testrun(self, testrun_id: int) -> bool:
        """Close the test run in Kiwi."""
        if not self.enabled:
            logger.info("Отправка в Kiwi отключена, тест-ран %d не закрыт", testrun_id)
            return True

        try:
            return self.client.close_testrun(testrun_id)
        except Exception as e:
            logger.error("Ошибка при закрытии тест-рана %d: %s", testrun_id, e)
            if self.skip_if_unavailable:
                return True
            raise

    def upload_attachment(
        self,
        testrun_id: int,
        case_id: str,
        file_path: Path,
        description: str = "",
    ) -> bool:
        """Upload an attachment for a test case result."""
        if not self.enabled:
            logger.info("Отправка в Kiwi отключена, аттачмент %s не загружен", file_path.name)
            return True

        try:
            return self.client.upload_attachment(testrun_id, case_id, file_path, description)
        except Exception as e:
            logger.error("Ошибка при загрузке аттачмента %s: %s", file_path, e)
            if self.skip_if_unavailable:
                return True
            raise
