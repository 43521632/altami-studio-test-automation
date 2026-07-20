"""Kiwi TCMS result reporting — currently a stub with local JSON/CSV export.

Kiwi access is not available yet, so every result is written locally in a
shape that maps cleanly onto Kiwi's TestExecution model. When credentials
arrive, only :meth:`KiwiReporter._send_to_kiwi` needs a real implementation —
callers and the local export stay unchanged.
"""

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import (
    KIWI_ENABLED,
    KIWI_EXPORT_CSV,
    KIWI_EXPORT_ENABLED,
    KIWI_EXPORT_JSON,
    KIWI_PROJECT_ID,
    KIWI_TEST_RUN_NAME,
    KIWI_URL,
)

logger = logging.getLogger(__name__)

# Статусы совпадают с моделью TestExecution в Kiwi TCMS
STATUS_PASS = "PASSED"
STATUS_FAIL = "FAILED"
STATUS_ERROR = "ERROR"
STATUS_SKIP = "SKIPPED"
VALID_STATUSES = {STATUS_PASS, STATUS_FAIL, STATUS_ERROR, STATUS_SKIP}


@dataclass
class TestResult:
    """One test execution, in a Kiwi-compatible shape."""

    test_name: str
    vm_id: str
    status: str
    started_at: str
    finished_at: str
    duration_s: float = 0.0
    log_file: Optional[str] = None
    screenshot: Optional[str] = None
    baseline: Optional[str] = None
    diff_image: Optional[str] = None
    ssim_score: Optional[float] = None
    error: Optional[str] = None
    attempt: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Недопустимый статус {self.status!r}. Допустимы: {sorted(VALID_STATUSES)}"
            )

    @property
    def passed(self) -> bool:
        """True if this execution passed."""
        return self.status == STATUS_PASS

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for JSON export."""
        return asdict(self)


class KiwiReporter:
    """Collects results, exports them locally, and (later) pushes to Kiwi TCMS.

    Args:
        enabled: send results to a real Kiwi instance. Requires KIWI_URL and
            KIWI_API_KEY; raises at construction time if they are missing.

    Example:
        reporter = KiwiReporter(enabled=False)
        reporter.report_result(result)
        reporter.finalize()
    """

    def __init__(self, enabled: bool = KIWI_ENABLED, run_name: str = KIWI_TEST_RUN_NAME) -> None:
        self.enabled = enabled
        self.run_name = f"{run_name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.results: List[TestResult] = []
        self._run_id: Optional[int] = None

        if self.enabled:
            # Падаем сразу, а не после часового прогона тестов
            if not KIWI_URL:
                raise ValueError(
                    "Интеграция с Kiwi включена (--kiwi), но не задан url.\n"
                    "Укажите его в config/vms_config.yaml (kiwi.url) или в KIWI_URL."
                )
            logger.warning(
                "Интеграция с Kiwi TCMS запрошена, но ЕЩЁ НЕ РЕАЛИЗОВАНА. "
                "Результаты сохраняются только локально."
            )

    # --- Приём результатов -------------------------------------------------

    def report_result(self, result: TestResult) -> None:
        """Record one test execution (and forward it to Kiwi when enabled)."""
        self.results.append(result)
        logger.info(
            "Результат: %s / %s -> %s%s",
            result.vm_id,
            result.test_name,
            result.status,
            f" (SSIM {result.ssim_score:.4f})" if result.ssim_score is not None else "",
        )
        if self.enabled:
            try:
                self._send_to_kiwi(result)
            except Exception as e:
                # Сбой отправки не должен ронять прогон — результат уже локально
                logger.error("Не удалось отправить результат в Kiwi: %s", e)

    def _send_to_kiwi(self, result: TestResult) -> None:
        """Push a single result to Kiwi TCMS.

        TODO: реализовать, когда появится доступ к Kiwi TCMS.

        План интеграции (Kiwi использует JSON-RPC, а не REST):
            1. pip install tcms-api
            2. from tcms_api import TCMS; rpc = TCMS().exec
            3. Один раз за прогон создать TestRun:
                 run = rpc.TestRun.create({
                     'summary': self.run_name,
                     'plan': <plan_id>,
                     'build': <build_id>,
                     'manager': <user_id>,
                 })
                 self._run_id = run['id']
            4. На каждый результат:
                 case = rpc.TestCase.filter({'summary': result.test_name})[0]
                 ex = rpc.TestExecution.filter(
                          {'run_id': self._run_id, 'case_id': case['id']})[0]
                 rpc.TestExecution.update(ex['id'], {
                     'status': <id статуса из TestExecutionStatus.filter({})>,
                     'tested_by': <user_id>,
                 })
            5. Прикрепить логи и скриншоты:
                 rpc.TestExecution.add_comment(ex['id'], <текст>)
                 # вложения загружаются через User.add_attachment (base64)
            6. Аутентификация: KIWI_URL + KIWI_API_KEY из окружения.

        Текущие настройки-заглушки: url=%s, project_id=%s
        """
        logger.debug(
            "ЗАГЛУШКА: результат '%s' не отправлен (url=%s, project=%s)",
            result.test_name, KIWI_URL or "не задан", KIWI_PROJECT_ID,
        )

    # --- Локальный экспорт --------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Aggregate counts overall and per VM."""
        totals = {"total": len(self.results), "passed": 0, "failed": 0,
                  "error": 0, "skipped": 0}
        by_vm: Dict[str, Dict[str, int]] = {}
        key = {STATUS_PASS: "passed", STATUS_FAIL: "failed",
               STATUS_ERROR: "error", STATUS_SKIP: "skipped"}

        for result in self.results:
            bucket = key[result.status]
            totals[bucket] += 1
            vm_stats = by_vm.setdefault(
                result.vm_id,
                {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0},
            )
            vm_stats["total"] += 1
            vm_stats[bucket] += 1

        return {"run_name": self.run_name, "totals": totals, "by_vm": by_vm}

    def export_json(self, path: Path = KIWI_EXPORT_JSON) -> Path:
        """Write all results plus the summary as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_name": self.run_name,
            "exported_at": datetime.now().isoformat(),
            "kiwi_enabled": self.enabled,
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info("JSON-отчёт сохранён: %s", path)
        return path

    def export_csv(self, path: Path = KIWI_EXPORT_CSV) -> Path:
        """Write a flat CSV suitable for manual import into Kiwi."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "test_name", "vm_id", "status", "started_at", "finished_at",
            "duration_s", "attempt", "ssim_score", "log_file", "screenshot",
            "baseline", "diff_image", "error",
        ]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for result in self.results:
                writer.writerow(result.to_dict())
        logger.info("CSV-отчёт сохранён: %s", path)
        return path

    def finalize(self) -> Dict[str, Any]:
        """Export local reports and return the run summary."""
        if KIWI_EXPORT_ENABLED:
            self.export_json()
            self.export_csv()
        return self.summary()
