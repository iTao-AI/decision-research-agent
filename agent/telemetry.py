from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    error: str | None = None
    token_usage: "TokenUsageData | None" = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryCollector:
    def __init__(self):
        self._records: dict[str, list[TelemetryRecord]] = {}

    def record(self, record: TelemetryRecord) -> None:
        thread_id = record.thread_id
        if thread_id not in self._records:
            self._records[thread_id] = []
        self._records[thread_id].append(record)

        # Evict oldest if > 500
        if len(self._records[thread_id]) > 500:
            self._records[thread_id].pop(0)

    def get_by_thread(self, thread_id: str) -> list[TelemetryRecord]:
        return list(self._records.get(thread_id, []))

    def clear_thread(self, thread_id: str) -> None:
        self._records.pop(thread_id, None)


# Global singleton
collector = TelemetryCollector()
