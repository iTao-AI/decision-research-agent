from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import TYPE_CHECKING

from api.observation_contract import projector

if TYPE_CHECKING:
    from agent.token_tracking import TokenUsageData


def _safe_rejection_diagnostic() -> None:
    try:
        print("[Telemetry] Record rejected")
    except Exception:
        pass


@dataclass(frozen=True)
class TelemetryRecord:
    thread_id: str | None
    agent_name: str
    tool_name: str
    duration_ms: float
    status: str
    run_id: str | None = None
    segment_id: str | None = None
    error: str | None = None
    error_type: str | None = None
    token_usage: "TokenUsageData | None" = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema: str = field(init=False, default="dra.telemetry-record.v1")

    def __post_init__(self) -> None:
        safe = projector.telemetry_fields(
            thread_id=self.thread_id,
            run_id=self.run_id,
            segment_id=self.segment_id,
            agent_name=self.agent_name,
            tool_name=self.tool_name,
            duration_ms=self.duration_ms,
            status=self.status,
            error=self.error,
            error_type=self.error_type,
            timestamp=self.timestamp,
            token_usage=self.token_usage,
        )
        for name, value in safe.items():
            object.__setattr__(self, name, value)


class TelemetryCollector:
    def __init__(self):
        self._records: dict[str, list[TelemetryRecord]] = {}
        self._lock = RLock()

    def record(self, record: TelemetryRecord) -> None:
        if type(record) is not TelemetryRecord:
            return
        safe_record = TelemetryRecord(
            thread_id=record.thread_id,
            run_id=record.run_id,
            segment_id=record.segment_id,
            agent_name=record.agent_name,
            tool_name=record.tool_name,
            duration_ms=record.duration_ms,
            status=record.status,
            error=record.error,
            error_type=record.error_type,
            token_usage=record.token_usage,
            timestamp=record.timestamp,
        )
        execution_id = (
            safe_record.run_id
            if safe_record.run_id is not None
            else safe_record.thread_id
        )
        if execution_id is None:
            _safe_rejection_diagnostic()
            return
        with self._lock:
            if execution_id not in self._records:
                self._records[execution_id] = []
            self._records[execution_id].append(safe_record)

            if len(self._records[execution_id]) > 500:
                self._records[execution_id].pop(0)

    def get_by_run(self, run_id: str) -> list[TelemetryRecord]:
        with self._lock:
            return list(self._records.get(run_id, []))

    def get_by_thread(self, thread_id: str) -> list[TelemetryRecord]:
        with self._lock:
            return [
                record
                for records in self._records.values()
                for record in records
                if record.thread_id == thread_id
            ]

    def clear_run(self, run_id: str) -> None:
        with self._lock:
            self._records.pop(run_id, None)

    def clear_thread(self, thread_id: str) -> None:
        with self._lock:
            for execution_id in list(self._records):
                records = [
                    record
                    for record in self._records[execution_id]
                    if record.thread_id != thread_id
                ]
                if records:
                    self._records[execution_id] = records
                else:
                    self._records.pop(execution_id, None)


# Global singleton
collector = TelemetryCollector()
