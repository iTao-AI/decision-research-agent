from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.token_tracking import TokenUsageData


@dataclass
class TelemetryRecord:
    thread_id: str
    agent_name: str
    tool_name: str
    duration_ms: float
    status: str
    run_id: str | None = None
    segment_id: str | None = None
    error: str | None = None
    token_usage: "TokenUsageData | None" = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryCollector:
    def __init__(self):
        self._records: dict[str, list[TelemetryRecord]] = {}
        self._lock = RLock()

    def record(self, record: TelemetryRecord) -> None:
        execution_id = record.run_id or record.thread_id
        with self._lock:
            if execution_id not in self._records:
                self._records[execution_id] = []
            self._records[execution_id].append(record)

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
