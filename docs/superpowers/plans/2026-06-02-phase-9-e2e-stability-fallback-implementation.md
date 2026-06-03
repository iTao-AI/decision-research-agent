# Phase 9 E2E Stability Fallback Implementation Plan

> **For Claude Code workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every agent task end with a deterministic persisted terminal state and a downloadable Markdown artifact when the agent finishes without producing one.

**Architecture:** Add a lightweight agent run result module that can be tested without importing the LLM-heavy main agent. Add a synchronous task finalizer that selects an existing report or writes a transparent fallback report, then wire FastAPI task persistence and timeout handling through that finalizer. Keep frontend and E2E runner changes minimal: `task_finalized` is the terminal UI event, while the runner treats `GET /api/tasks/{thread_id}` as the source of truth.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (`sqlite3`), pytest, LangChain message types, Vue 3 + TypeScript + Vite, `requests`, optional `websockets` from `uvicorn[standard]`.

**Source Spec:** `docs/superpowers/plans/2026-06-02-phase-9-e2e-stability-fallback.md`

**Execution note:** This plan contains commit steps because Superpowers execution plans are designed for frequent commits. If the user has not explicitly authorized commits in the execution session, stop before the first commit step and ask for commit authorization.

**Workflow priority:** user instruction and project safety boundaries > activated Superpowers skill procedure > project default workflow > optional OpenSpec mode. `SUPERPOWERS_GATE` and `TDD_EVIDENCE` are evidence gates; they do not replace the execution steps required by the activated skill.

**Subagent execution rule:** if `subagent-driven-development` is loaded, dispatch fresh implementation subagents for plan tasks instead of manually executing the plan. Provide the full task text, allowed files, RED/GREEN commands, expected evidence, and stop conditions in each implementer prompt.

**Tool failure stop condition:** if 3 consecutive tool calls fail with missing/empty parameters or malformed invocation, stop manual execution, record the deviation, and switch to a fresh subagent or new session.

---

## File Structure

- Create `agent/run_result.py`: testable dataclasses plus stream chunk processing that records final AI text and emits existing monitor events.
- Modify `agent/main_agent.py`: use `AgentRunAccumulator`, return `AgentRunResult`, and re-raise stream exceptions.
- Create `api/task_finalizer.py`: select existing report, write fallback report, persist terminal task state, and emit terminal monitor events.
- Modify `api/persistence.py`: define terminal status constants and stamp `completed_at` for `completed_with_fallback`.
- Modify `api/task_tracker.py`: support timeout callback and stop returning timeout error strings.
- Modify `api/monitor.py`: add `report_task_finalized(...)`.
- Modify `api/server.py`: extract `_run_task_with_persistence(...)` and `_mark_task_timeout(...)`, pass timeout callback to tracker.
- Modify `frontend/src/App.vue`: handle `task_finalized`.
- Create `scripts/e2e_runner.py`: WebSocket evidence collection plus REST polling to terminal state.
- Update docs: `spec/api-contract.md`, `README.md`, `README_CN.md`, `CLAUDE.md`, `docs/evidence/run-log.md`.

---

### Task 1: Persistence Terminal Status and Monitor Event

**Files:**
- Modify: `api/persistence.py`
- Modify: `api/monitor.py`
- Modify: `tests/unit/test_persistence.py`
- Modify: `tests/unit/test_monitor_sanitization.py`

- [ ] **Step 1: Add persistence tests for `completed_with_fallback`**

Append this test method to `TestPersistence` in `tests/unit/test_persistence.py`:

```python
    def test_completed_with_fallback_sets_completed_at(self, db_path):
        """completed_with_fallback is a terminal status."""
        from api.persistence import init_db, save_task, update_task, get_task

        init_db(db_path)
        save_task(db_path, thread_id="fallback-001", query="test")
        update_task(
            db_path,
            "fallback-001",
            status="completed_with_fallback",
            output_path="/output/session_fallback-001/fallback_report.md",
        )

        task = get_task(db_path, "fallback-001")
        assert task["status"] == "completed_with_fallback"
        assert task["completed_at"] is not None
        assert task["output_path"].endswith("fallback_report.md")
```

- [ ] **Step 2: Add monitor test for `task_finalized`**

Append this test method to `TestMonitorSanitization` in `tests/unit/test_monitor_sanitization.py`:

```python
    def test_report_task_finalized_emits_terminal_payload(self):
        """task_finalized includes status and fallback metadata."""
        mon, captured = self._make_monitor_with_captured_emit()

        mon.report_task_finalized(
            thread_id="thread-001",
            status="completed_with_fallback",
            fallback_used=True,
            output_path="/tmp/output/session_thread-001/fallback_report.md",
            error_message=None,
        )

        assert captured["event_type"] == "task_finalized"
        assert captured["message"] == "任务状态已完成: completed_with_fallback"
        assert captured["data"] == {
            "thread_id": "thread-001",
            "status": "completed_with_fallback",
            "fallback_used": True,
            "output_path": "/tmp/output/session_thread-001/fallback_report.md",
            "error_message": None,
        }
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_persistence.py::TestPersistence::test_completed_with_fallback_sets_completed_at tests/unit/test_monitor_sanitization.py::TestMonitorSanitization::test_report_task_finalized_emits_terminal_payload -v
```

Expected: both tests fail. Persistence should fail because `completed_at` is `None`; monitor should fail because `report_task_finalized` is missing.

- [ ] **Step 4: Implement terminal status constant**

In `api/persistence.py`, add this constant after `DEFAULT_DB_PATH`:

```python
TERMINAL_STATUSES = {"completed", "completed_with_fallback", "failed"}
```

Replace this block in `update_task(...)`:

```python
        elif status in ("completed", "failed"):
            sets.append("completed_at = ?")
            params.append(now)
```

with:

```python
        elif status in TERMINAL_STATUSES:
            sets.append("completed_at = ?")
            params.append(now)
```

- [ ] **Step 5: Implement monitor terminal helper**

In `api/monitor.py`, add this method after `report_task_result(...)`:

```python
    def report_task_finalized(
        self,
        thread_id: str,
        status: str,
        fallback_used: bool = False,
        output_path: str | None = None,
        error_message: str | None = None,
    ):
        """Report terminal task persistence state."""
        self._emit(
            "task_finalized",
            f"任务状态已完成: {status}",
            {
                "thread_id": thread_id,
                "status": status,
                "fallback_used": fallback_used,
                "output_path": output_path,
                "error_message": error_message,
            },
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/unit/test_persistence.py::TestPersistence::test_completed_with_fallback_sets_completed_at tests/unit/test_monitor_sanitization.py::TestMonitorSanitization::test_report_task_finalized_emits_terminal_payload -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add api/persistence.py api/monitor.py tests/unit/test_persistence.py tests/unit/test_monitor_sanitization.py
git commit -m "feat: add fallback terminal task status"
```

---

### Task 2: Agent Run Result and Stream Accumulator

**Files:**
- Create: `agent/run_result.py`
- Create: `tests/unit/test_agent_run_result.py`

- [ ] **Step 1: Write failing tests for stream accumulation**

Create `tests/unit/test_agent_run_result.py`:

```python
"""Tests for agent run result accumulation."""
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage


class CapturingMonitor:
    def __init__(self):
        self.assistant_calls = []
        self.task_results = []

    def report_assistant(self, assistant_name, args=None):
        self.assistant_calls.append((assistant_name, args))

    def report_task_result(self, result):
        self.task_results.append(result)


class TestAgentRunAccumulator:
    def test_records_task_tool_calls_and_emits_existing_monitor_event(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-001",
            query="研究问题",
            session_dir=tmp_path,
        )
        chunk = {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "subagent_type": "network_search",
                                    "description": "搜索公开资料",
                                },
                                "id": "call-1",
                            }
                        ],
                    )
                ]
            }
        }

        process_stream_chunk(chunk, accumulator, monitor)

        assert accumulator.assistant_calls == 1
        assert monitor.assistant_calls == [
            ("network_search", {"desc": "搜索公开资料"})
        ]

    def test_records_last_non_empty_ai_text(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-002",
            query="研究问题",
            session_dir=tmp_path,
        )

        process_stream_chunk(
            {"agent": {"messages": [AIMessage(content="第一段结果")]}},
            accumulator,
            monitor,
        )
        process_stream_chunk(
            {"agent": {"messages": [AIMessage(content="最终结果")]}},
            accumulator,
            monitor,
        )

        assert accumulator.last_agent_text == "最终结果"
        assert monitor.task_results == ["第一段结果", "最终结果"]

    def test_records_tool_messages_as_tool_events(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-003",
            query="研究问题",
            session_dir=tmp_path,
        )

        process_stream_chunk(
            {"tools": {"messages": [ToolMessage(content="工具输出", tool_call_id="call-1", name="tavily_search")]}},
            accumulator,
            monitor,
        )

        assert accumulator.tool_starts == 1
        assert accumulator.diagnostics == ["tool:tavily_search"]

    def test_to_result_copies_accumulator_state(self, tmp_path):
        from agent.run_result import AgentRunAccumulator

        accumulator = AgentRunAccumulator(
            thread_id="thread-004",
            query="研究问题",
            session_dir=tmp_path,
        )
        accumulator.last_agent_text = "最终结果"
        accumulator.assistant_calls = 2
        accumulator.tool_starts = 3
        accumulator.diagnostics.append("tool:tavily_search")

        result = accumulator.to_result()

        assert result.thread_id == "thread-004"
        assert result.query == "研究问题"
        assert result.session_dir == tmp_path
        assert result.last_agent_text == "最终结果"
        assert result.assistant_calls == 2
        assert result.tool_starts == 3
        assert result.diagnostics == ["tool:tavily_search"]
        assert result.error_message is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_agent_run_result.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.run_result'`.

- [ ] **Step 3: Implement `agent/run_result.py`**

Create `agent/run_result.py`:

```python
"""Lightweight agent run result contracts.

This module intentionally avoids importing agent.main_agent so tests can cover
stream processing without initializing the LLM-backed DeepAgent.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


@dataclass(frozen=True)
class AgentRunResult:
    """Summary of one main-agent execution."""

    thread_id: str
    query: str
    session_dir: Path
    last_agent_text: str = ""
    assistant_calls: int = 0
    tool_starts: int = 0
    diagnostics: list[str] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class AgentRunAccumulator:
    """Mutable state collected while streaming LangGraph chunks."""

    thread_id: str
    query: str
    session_dir: Path
    last_agent_text: str = ""
    assistant_calls: int = 0
    tool_starts: int = 0
    diagnostics: list[str] = field(default_factory=list)

    def to_result(self, error_message: str | None = None) -> AgentRunResult:
        return AgentRunResult(
            thread_id=self.thread_id,
            query=self.query,
            session_dir=self.session_dir,
            last_agent_text=self.last_agent_text,
            assistant_calls=self.assistant_calls,
            tool_starts=self.tool_starts,
            diagnostics=list(self.diagnostics),
            error_message=error_message,
        )


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _tool_value(tool: Any, key: str, default: Any = None) -> Any:
    if isinstance(tool, dict):
        return tool.get(key, default)
    return getattr(tool, key, default)


def process_stream_chunk(chunk: dict[str, Any], accumulator: AgentRunAccumulator, monitor) -> None:
    """Process LangGraph stream output and report events to frontend."""
    for node_name, state in chunk.items():
        if not state or "messages" not in state:
            continue

        messages = state["messages"]
        if not isinstance(messages, list) or not messages:
            continue

        last_msg = messages[-1]

        if isinstance(last_msg, AIMessage):
            if last_msg.tool_calls:
                for tool in last_msg.tool_calls:
                    if _tool_value(tool, "name") != "task":
                        continue

                    args = _tool_value(tool, "args", {}) or {}
                    accumulator.assistant_calls += 1
                    monitor.report_assistant(
                        args.get("subagent_type", "Agent"),
                        {"desc": args.get("description")},
                    )
            elif last_msg.content:
                text = _text_from_content(last_msg.content).strip()
                if text:
                    accumulator.last_agent_text = text
                    monitor.report_task_result(text)

        elif isinstance(last_msg, ToolMessage):
            accumulator.tool_starts += 1
            tool_name = getattr(last_msg, "name", None) or node_name
            accumulator.diagnostics.append(f"tool:{tool_name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/unit/test_agent_run_result.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add agent/run_result.py tests/unit/test_agent_run_result.py
git commit -m "feat: add agent run result accumulator"
```

---

### Task 3: Task Finalizer

**Files:**
- Create: `api/task_finalizer.py`
- Create: `tests/unit/test_task_finalizer.py`

- [ ] **Step 1: Write failing finalizer tests**

Create `tests/unit/test_task_finalizer.py`:

```python
"""Tests for task finalization and fallback reports."""
import json

import pytest

from agent.run_result import AgentRunResult


@pytest.fixture
def task_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(db_path))
    return str(db_path)


def _save_task(thread_id: str, query: str):
    from api.persistence import save_task

    save_task(thread_id=thread_id, query=query, status="running")


class TestTaskFinalizer:
    def test_selects_newest_existing_markdown_report(self, tmp_path, task_db):
        from api.persistence import get_task
        from api.task_finalizer import finalize_task_run

        thread_id = "finalizer-existing"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        old_report = session_dir / "old.md"
        new_report = session_dir / "new.md"
        fallback = session_dir / "fallback_report.md"
        old_report.write_text("old", encoding="utf-8")
        new_report.write_text("new", encoding="utf-8")
        fallback.write_text("fallback must be ignored", encoding="utf-8")
        old_time = 1_700_000_000
        new_time = 1_700_000_100
        old_report.touch()
        new_report.touch()
        fallback.touch()
        import os
        os.utime(old_report, (old_time, old_time))
        os.utime(new_report, (new_time, new_time))
        os.utime(fallback, (new_time + 100, new_time + 100))
        _save_task(thread_id, "query")

        result = AgentRunResult(
            thread_id=thread_id,
            query="query",
            session_dir=session_dir,
            last_agent_text="agent text",
        )
        finalization = finalize_task_run(result)

        task = get_task(thread_id=thread_id)
        assert finalization.status == "completed"
        assert finalization.fallback_used is False
        assert finalization.output_path == str(new_report)
        assert task["status"] == "completed"
        assert task["output_path"] == str(new_report)
        assert json.loads(task["token_usage_json"])["total_tokens"] == 0

    def test_writes_fallback_report_when_no_markdown_exists(self, tmp_path, task_db):
        from api.persistence import get_task
        from api.task_finalizer import finalize_task_run

        thread_id = "finalizer-fallback"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        _save_task(thread_id, "query")

        result = AgentRunResult(
            thread_id=thread_id,
            query="query",
            session_dir=session_dir,
            last_agent_text="last visible agent text",
            assistant_calls=2,
            tool_starts=1,
            diagnostics=["tool:tavily_search"],
        )
        finalization = finalize_task_run(result)

        fallback_path = session_dir / "fallback_report.md"
        task = get_task(thread_id=thread_id)
        content = fallback_path.read_text(encoding="utf-8")
        assert finalization.status == "completed_with_fallback"
        assert finalization.fallback_used is True
        assert finalization.output_path == str(fallback_path)
        assert task["status"] == "completed_with_fallback"
        assert task["output_path"] == str(fallback_path)
        assert "# Fallback Report" in content
        assert "query" in content
        assert "last visible agent text" in content
        assert "tool:tavily_search" in content

    def test_ignores_empty_markdown_report(self, tmp_path, task_db):
        from api.task_finalizer import finalize_task_run

        thread_id = "finalizer-empty"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        (session_dir / "empty.md").write_text("", encoding="utf-8")
        _save_task(thread_id, "query")

        result = AgentRunResult(
            thread_id=thread_id,
            query="query",
            session_dir=session_dir,
            last_agent_text="agent text",
        )
        finalization = finalize_task_run(result)

        assert finalization.status == "completed_with_fallback"
        assert finalization.output_path.endswith("fallback_report.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_task_finalizer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api.task_finalizer'`.

- [ ] **Step 3: Implement `api/task_finalizer.py`**

Create `api/task_finalizer.py`:

```python
"""Task finalization: report selection, fallback report, and persistence."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from agent.run_result import AgentRunResult
from agent.token_tracking import token_collector
from api.monitor import monitor
from api.persistence import update_task


@dataclass(frozen=True)
class TaskFinalization:
    thread_id: str
    status: str
    output_path: str | None
    fallback_used: bool
    error_message: str | None = None


def _find_latest_markdown_report(session_dir: Path) -> Path | None:
    candidates = [
        path
        for path in session_dir.glob("*.md")
        if path.name != "fallback_report.md" and path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _fallback_report_content(run_result: AgentRunResult) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    diagnostics = "\n".join(f"- {item}" for item in run_result.diagnostics) or "- No diagnostic events captured"
    last_agent_text = run_result.last_agent_text.strip() or "No final agent text was captured."

    return (
        "# Fallback Report\n\n"
        "This fallback report was generated because the agent task finished without a non-empty Markdown report.\n\n"
        f"- Thread ID: `{run_result.thread_id}`\n"
        f"- Generated at: `{generated_at}`\n"
        f"- Assistant calls observed: `{run_result.assistant_calls}`\n"
        f"- Tool messages observed: `{run_result.tool_starts}`\n\n"
        "## Original Query\n\n"
        f"{run_result.query}\n\n"
        "## Last Agent Output\n\n"
        f"{last_agent_text}\n\n"
        "## Diagnostics\n\n"
        f"{diagnostics}\n"
    )


def _write_fallback_report(run_result: AgentRunResult) -> Path:
    run_result.session_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = run_result.session_dir / "fallback_report.md"
    fallback_path.write_text(_fallback_report_content(run_result), encoding="utf-8")
    return fallback_path


def _token_usage_json(thread_id: str) -> str:
    return json.dumps(token_collector.get_summary(thread_id), ensure_ascii=False)


def finalize_task_run(run_result: AgentRunResult) -> TaskFinalization:
    """Persist a successful agent run as completed or completed_with_fallback."""
    report_path = _find_latest_markdown_report(run_result.session_dir)
    fallback_used = False
    status = "completed"

    if report_path is None:
        report_path = _write_fallback_report(run_result)
        fallback_used = True
        status = "completed_with_fallback"

    output_path = str(report_path)
    update_task(
        thread_id=run_result.thread_id,
        status=status,
        output_path=output_path,
        token_usage_json=_token_usage_json(run_result.thread_id),
    )
    monitor.report_task_finalized(
        thread_id=run_result.thread_id,
        status=status,
        fallback_used=fallback_used,
        output_path=output_path,
        error_message=None,
    )
    if fallback_used:
        monitor.report_task_result(
            {
                "result": "任务已完成但未生成正式报告，系统已创建兜底报告。",
                "output_path": output_path,
                "fallback_used": True,
            }
        )

    return TaskFinalization(
        thread_id=run_result.thread_id,
        status=status,
        output_path=output_path,
        fallback_used=fallback_used,
        error_message=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/unit/test_task_finalizer.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/task_finalizer.py tests/unit/test_task_finalizer.py
git commit -m "feat: add task finalizer with fallback reports"
```

---

### Task 4: Timeout Callback Semantics

**Files:**
- Modify: `api/task_tracker.py`
- Modify: `tests/unit/test_task_tracker_timeout.py`

- [ ] **Step 1: Replace the timeout test expectation**

In `tests/unit/test_task_tracker_timeout.py`, replace `test_timeout_wraps_wait_for` with:

```python
    @pytest.mark.asyncio
    async def test_timeout_calls_callback_and_does_not_return_error_string(self):
        """Timed out tasks call on_timeout and return None instead of a success-like string."""
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks

        clear_active_tasks()
        calls = []

        async def slow():
            await asyncio.sleep(100)
            return "done"

        async def on_timeout(task_id: str, timeout_seconds: int):
            calls.append((task_id, timeout_seconds))

        task = create_tracked_task(
            slow(),
            "timeout-test-2",
            timeout_seconds=1,
            on_timeout=on_timeout,
        )

        result = await asyncio.wait_for(task, timeout=3)
        assert result is None
        assert calls == [("timeout-test-2", 1)]
        assert get_active_task("timeout-test-2") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/unit/test_task_tracker_timeout.py::TestTaskTrackerTimeout::test_timeout_calls_callback_and_does_not_return_error_string -v
```

Expected: FAIL because `create_tracked_task` does not accept `on_timeout`.

- [ ] **Step 3: Implement timeout callback support**

In `api/task_tracker.py`, replace imports:

```python
from typing import Dict
```

with:

```python
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Dict
```

Add this type alias after `active_tasks`:

```python
TimeoutCallback = Callable[[str, int], Awaitable[Any] | Any]
```

Replace `create_tracked_task(...)` with:

```python
def create_tracked_task(
    coroutine,
    task_id: str,
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT,
    on_timeout: TimeoutCallback | None = None,
) -> asyncio.Task:
    """Create and track an async task with timeout protection."""
    async def _with_timeout():
        try:
            return await asyncio.wait_for(coroutine, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_id} timed out after {timeout_seconds}s")
            if on_timeout is not None:
                callback_result = on_timeout(task_id, timeout_seconds)
                if inspect.isawaitable(callback_result):
                    await callback_result
            return None

    task = asyncio.create_task(_with_timeout())
    start_time = asyncio.get_event_loop().time()
    active_tasks[task_id] = (task, timeout_seconds, start_time)
    task.add_done_callback(lambda t: _on_task_done(t, task_id))
    return task
```

- [ ] **Step 4: Run task tracker tests**

Run:

```bash
python -m pytest tests/unit/test_task_tracker.py tests/unit/test_task_tracker_timeout.py -v
```

Expected: all task tracker tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/task_tracker.py tests/unit/test_task_tracker_timeout.py
git commit -m "fix: persist timeout through callback path"
```

---

### Task 5: Main Agent Returns `AgentRunResult`

**Files:**
- Modify: `agent/main_agent.py`

- [ ] **Step 1: Update imports**

In `agent/main_agent.py`, remove:

```python
from langchain_core.messages import AIMessage
```

Add:

```python
from agent.run_result import AgentRunAccumulator, AgentRunResult, process_stream_chunk
```

- [ ] **Step 2: Replace `_process_stream_chunk(...)`**

Replace the current `_process_stream_chunk(chunk)` function with:

```python
def _process_stream_chunk(chunk, accumulator: AgentRunAccumulator):
    """Process LangGraph stream output and report events to frontend."""
    process_stream_chunk(chunk, accumulator, monitor)
```

- [ ] **Step 3: Update `run_deep_agent(...)` return contract**

In `run_deep_agent(...)`, after `monitor.report_session_dir(session_dir_str)`, add:

```python
    accumulator = AgentRunAccumulator(
        thread_id=thread_id,
        query=task_query,
        session_dir=Path(session_dir_str),
    )
```

Replace the streaming block:

```python
    try:
        async for chunk in main_agent.astream(
                {"messages": [{"role": "user", "content": task_query + path_instruction}]},
                config=config
        ):
            _process_stream_chunk(chunk)
        return "Done"
    except Exception as e:
        print(f"Error: {e}")
        monitor._emit("error", f"Execution failed: {e}")
        return f"Error: {e}"
```

with:

```python
    try:
        async for chunk in main_agent.astream(
                {"messages": [{"role": "user", "content": task_query + path_instruction}]},
                config=config
        ):
            _process_stream_chunk(chunk, accumulator)
        return accumulator.to_result()
    except Exception as e:
        print(f"Error: {e}")
        monitor._emit("error", f"Execution failed: {e}")
        raise
```

Also update the function signature:

```python
async def run_deep_agent(task_query: str, thread_id: str = None) -> AgentRunResult:
```

- [ ] **Step 4: Run import and accumulator tests**

Run:

```bash
python -m pytest tests/unit/test_agent_run_result.py -v
```

Expected: 4 passed.

Run:

```bash
python - <<'PY'
import importlib
module = importlib.import_module("agent.run_result")
print(module.AgentRunResult.__name__)
PY
```

Expected output:

```text
AgentRunResult
```

- [ ] **Step 5: Commit**

```bash
git add agent/main_agent.py
git commit -m "feat: return structured agent run results"
```

---

### Task 6: Server Persistence Wiring

**Files:**
- Modify: `api/server.py`
- Create: `tests/integration/test_task_finalization_flow.py`

- [ ] **Step 1: Write integration tests for server task finalization**

Create `tests/integration/test_task_finalization_flow.py`:

```python
"""Integration tests for server-side task finalization."""
import asyncio

import pytest

from agent.run_result import AgentRunResult


@pytest.fixture
def task_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(db_path))
    return str(db_path)


def _save_task(thread_id: str, query: str):
    from api.persistence import save_task

    save_task(thread_id=thread_id, query=query, status="pending")


class TestServerTaskFinalization:
    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_completed_when_report_exists(
        self,
        tmp_path,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-completed"
        query = "query"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        report = session_dir / "report.md"
        report.write_text("report", encoding="utf-8")
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            assert task_query == query
            assert task_thread_id == thread_id
            return AgentRunResult(
                thread_id=thread_id,
                query=query,
                session_dir=session_dir,
                last_agent_text="agent text",
            )

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        finalization = await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert finalization.status == "completed"
        assert task["status"] == "completed"
        assert task["output_path"] == str(report)

    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_completed_with_fallback(
        self,
        tmp_path,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-fallback"
        query = "query"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            return AgentRunResult(
                thread_id=thread_id,
                query=query,
                session_dir=session_dir,
                last_agent_text="agent text",
            )

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        finalization = await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert finalization.status == "completed_with_fallback"
        assert task["status"] == "completed_with_fallback"
        assert task["output_path"].endswith("fallback_report.md")

    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_failed_on_exception(
        self,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-failed"
        query = "query"
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            raise RuntimeError("agent failed")

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        with pytest.raises(RuntimeError):
            await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert task["status"] == "failed"
        assert task["error_message"] == "agent failed"

    @pytest.mark.asyncio
    async def test_mark_task_timeout_persists_failed_status(self, task_db):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-timeout"
        _save_task(thread_id, "query")

        await server._mark_task_timeout(thread_id, 7)

        task = get_task(thread_id=thread_id)
        assert task["status"] == "failed"
        assert task["error_message"] == "Agent task timed out after 7s"
```

- [ ] **Step 2: Run integration tests to verify they fail**

Run:

```bash
python -m pytest tests/integration/test_task_finalization_flow.py -v
```

Expected: FAIL because `_run_task_with_persistence` and `_mark_task_timeout` are missing.

- [ ] **Step 3: Update server imports**

In `api/server.py`, add:

```python
from agent.run_result import AgentRunResult
from api.task_finalizer import finalize_task_run, TaskFinalization
```

- [ ] **Step 4: Add top-level persistence helpers**

In `api/server.py`, add these functions above `@app.post("/api/task")`:

```python
async def _mark_task_timeout(thread_id: str, timeout_seconds: int) -> None:
    error_message = f"Agent task timed out after {timeout_seconds}s"
    await asyncio.to_thread(
        update_task,
        thread_id=thread_id,
        status="failed",
        error_message=error_message,
    )
    monitor.report_task_finalized(
        thread_id=thread_id,
        status="failed",
        fallback_used=False,
        output_path=None,
        error_message=error_message,
    )
    monitor._emit("error", error_message)


async def _run_task_with_persistence(query: str, thread_id: str) -> TaskFinalization:
    try:
        await asyncio.to_thread(update_task, thread_id=thread_id, status="running")
        result = await run_deep_agent(query, thread_id)
        if not isinstance(result, AgentRunResult):
            raise RuntimeError(
                f"run_deep_agent returned unsupported result type: {type(result).__name__}"
            )
        return await asyncio.to_thread(finalize_task_run, result)
    except Exception as e:
        await asyncio.to_thread(
            update_task,
            thread_id=thread_id,
            status="failed",
            error_message=str(e),
        )
        monitor.report_task_finalized(
            thread_id=thread_id,
            status="failed",
            fallback_used=False,
            output_path=None,
            error_message=str(e),
        )
        raise
```

- [ ] **Step 5: Simplify `/api/task` to use helpers**

Replace the nested `_run_with_persistence()` block inside `run_task(...)` with:

```python
    create_tracked_task(
        _run_task_with_persistence(request.query, thread_id),
        thread_id,
        on_timeout=_mark_task_timeout,
    )
```

The final `run_task(...)` body should still save `pending` before scheduling and return:

```python
    return {"status": "started", "thread_id": thread_id}
```

- [ ] **Step 6: Run integration tests**

Run:

```bash
python -m pytest tests/integration/test_task_finalization_flow.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Run endpoint smoke test**

Run:

```bash
python -m pytest tests/integration/test_api_endpoints.py::TestTaskEndpoint::test_run_task_returns_thread_id -v
```

Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add api/server.py tests/integration/test_task_finalization_flow.py
git commit -m "feat: finalize persisted agent task states"
```

---

### Task 7: Frontend `task_finalized` Handling

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add terminal event handling**

In `frontend/src/App.vue`, inside `handleSocketMessage(...)`, add this branch before the existing `task_result` branch:

```ts
  } else if (event === 'task_finalized') {
    const finalizedStatus = eventData.status
    if (finalizedStatus === 'completed' || finalizedStatus === 'completed_with_fallback' || finalizedStatus === 'failed') {
      status.value = 'idle'
    }

    if (finalizedStatus === 'completed_with_fallback') {
      const fallbackMessage = '任务已完成但未生成正式报告，系统已创建兜底报告。'
      if (lastAiMsg) {
        lastAiMsg.content = fallbackMessage
      } else {
        messages.value.push({
          role: 'ai',
          content: fallbackMessage,
          timestamp: Date.now()
        })
      }
    }

    if (finalizedStatus === 'failed') {
      messages.value.push({
        role: 'system',
        content: `Error: ${eventData.error_message || message}`,
        timestamp: Date.now()
      })
    }

    fetchFiles()
```

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds with `vue-tsc` and `vite build`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: handle finalized task websocket event"
```

---

### Task 8: Manual E2E Runner

**Files:**
- Create: `scripts/e2e_runner.py`
- Create: `tests/unit/test_e2e_runner.py`

- [ ] **Step 1: Write unit tests for runner helpers**

Create `tests/unit/test_e2e_runner.py`:

```python
"""Unit tests for the manual E2E runner helpers."""
import importlib.util
from pathlib import Path


def _load_runner_module():
    path = Path("scripts/e2e_runner.py").resolve()
    spec = importlib.util.spec_from_file_location("e2e_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestE2ERunnerHelpers:
    def test_is_terminal_status(self):
        runner = _load_runner_module()

        assert runner.is_terminal_status("completed") is True
        assert runner.is_terminal_status("completed_with_fallback") is True
        assert runner.is_terminal_status("failed") is True
        assert runner.is_terminal_status("running") is False

    def test_ws_url_for_http_api_base(self):
        runner = _load_runner_module()

        assert runner.default_ws_base("http://127.0.0.1:8000") == "ws://127.0.0.1:8000"
        assert runner.default_ws_base("https://example.com") == "wss://example.com"

    def test_count_websocket_events(self):
        runner = _load_runner_module()
        events = [
            {"type": "monitor_event", "event": "assistant_call"},
            {"type": "monitor_event", "event": "tool_start"},
            {"type": "monitor_event", "event": "tool_start"},
            {"type": "pong"},
        ]

        summary = runner.summarize_ws_events(events)

        assert summary["websocket_events"] == 3
        assert summary["assistant_calls"] == 1
        assert summary["tool_starts"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_e2e_runner.py -v
```

Expected: FAIL because `scripts/e2e_runner.py` does not exist.

- [ ] **Step 3: Implement `scripts/e2e_runner.py`**

Create directory and file:

```bash
mkdir -p scripts
```

Create `scripts/e2e_runner.py`:

```python
#!/usr/bin/env python3
"""Manual E2E runner for Deep Search Agent.

Connects WebSocket before submitting a task, records monitor events, then polls
the persisted task endpoint until a terminal status is reached.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import requests


TERMINAL_STATUSES = {"completed", "completed_with_fallback", "failed"}


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def default_ws_base(api_base: str) -> str:
    parsed = urlparse(api_base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


def summarize_ws_events(events: list[dict[str, Any]]) -> dict[str, int]:
    monitor_events = [event for event in events if event.get("type") == "monitor_event"]
    return {
        "websocket_events": len(monitor_events),
        "assistant_calls": sum(1 for event in monitor_events if event.get("event") == "assistant_call"),
        "tool_starts": sum(1 for event in monitor_events if event.get("event") == "tool_start"),
    }


def _headers(api_key: str | None) -> dict[str, str]:
    return {"X-API-Key": api_key} if api_key else {}


async def collect_websocket_events(
    ws_base: str,
    thread_id: str,
    api_key: str | None,
    events: list[dict[str, Any]],
    stop_event: asyncio.Event,
) -> None:
    import websockets

    query = f"?api_key={quote(api_key)}" if api_key else ""
    url = f"{ws_base.rstrip('/')}/ws/{thread_id}{query}"
    try:
        async with websockets.connect(url) as websocket:
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                events.append(json.loads(raw))
    except Exception as exc:
        events.append(
            {
                "type": "runner_error",
                "event": "websocket_error",
                "message": str(exc),
            }
        )


def submit_task(api_base: str, query: str, thread_id: str, api_key: str | None) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}/api/task",
        json={"query": query, "thread_id": thread_id},
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_task(api_base: str, thread_id: str, api_key: str | None) -> dict[str, Any]:
    response = requests.get(
        f"{api_base.rstrip('/')}/api/tasks/{thread_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_token_usage(api_base: str, thread_id: str, api_key: str | None) -> dict[str, Any]:
    response = requests.get(
        f"{api_base.rstrip('/')}/api/token-usage/{thread_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def report_size(output_path: str | None) -> int:
    if not output_path:
        return 0
    path = Path(output_path)
    return path.stat().st_size if path.exists() else 0


async def run(args: argparse.Namespace) -> dict[str, Any]:
    ws_base = args.ws_base or default_ws_base(args.api_base)
    events: list[dict[str, Any]] = []
    stop_event = asyncio.Event()
    started_at = time.monotonic()

    ws_task = asyncio.create_task(
        collect_websocket_events(ws_base, args.thread_id, args.api_key, events, stop_event)
    )
    await asyncio.sleep(0.25)

    submit_task(args.api_base, args.query, args.thread_id, args.api_key)

    task_state: dict[str, Any] = {}
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        task_state = fetch_task(args.api_base, args.thread_id, args.api_key)
        if is_terminal_status(task_state.get("status", "")):
            break
        await asyncio.sleep(args.poll_interval)
    else:
        task_state = {
            "thread_id": args.thread_id,
            "query": args.query,
            "status": "runner_timeout",
            "output_path": None,
        }

    stop_event.set()
    await asyncio.sleep(0)
    ws_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass

    token_usage = fetch_token_usage(args.api_base, args.thread_id, args.api_key)
    event_summary = summarize_ws_events(events)
    output_path = task_state.get("output_path")

    return {
        "thread_id": args.thread_id,
        "query": args.query,
        "status": task_state.get("status"),
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        **event_summary,
        "token_usage": token_usage,
        "output_path": output_path,
        "report_size_bytes": report_size(output_path),
        "fallback_used": task_state.get("status") == "completed_with_fallback",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one manual Deep Search Agent E2E task.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-base", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
python -m pytest tests/unit/test_e2e_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Verify WebSocket dependency availability**

Run:

```bash
python - <<'PY'
import websockets
print(websockets.__name__)
PY
```

Expected output:

```text
websockets
```

If this import fails, add this line to `requirements.txt` under the Web service section:

```text
websockets>=12.0              # Manual E2E runner WebSocket client
```

Then run:

```bash
python -m pytest tests/unit/test_e2e_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/e2e_runner.py tests/unit/test_e2e_runner.py requirements.txt
git commit -m "feat: add manual e2e runner"
```

---

### Task 9: Docs and API Contract

**Files:**
- Modify: `spec/api-contract.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CLAUDE.md`
- Modify: `docs/evidence/run-log.md`

- [ ] **Step 1: Update API contract for task status and WebSocket event**

In `spec/api-contract.md`, add this section after `POST /api/task`:

````markdown
### GET /api/tasks/{thread_id}

查询异步 Agent 任务的持久化状态。

**响应：**
```json
{
  "thread_id": "唯一的会话线程ID",
  "query": "用户提交的原始问题",
  "status": "pending | running | completed | completed_with_fallback | failed",
  "created_at": "ISO 8601 时间戳",
  "started_at": "ISO 8601 时间戳或 null",
  "completed_at": "ISO 8601 时间戳或 null",
  "output_path": "完成状态下可下载的 Markdown 文件绝对路径或 null",
  "token_usage_json": "JSON 字符串或 null",
  "error_message": "失败原因或 null"
}
```
````

Replace the WebSocket event list with:

```markdown
WebSocket events: `session_created`, `tool_start`, `assistant_call`, `task_result`, `task_finalized`, `error`
```

Add this event description:

```markdown
`task_finalized` 表示后端已写入持久化终态。`data.status` 可能为 `completed`、`completed_with_fallback` 或 `failed`；`data.output_path` 在成功和兜底成功时指向可下载 Markdown 文件。
```

- [ ] **Step 2: Update README endpoint lists**

In `README.md`, add:

```markdown
- **GET /api/tasks/{thread_id}** — View persisted task status and output path
```

Update the WebSocket event line to:

```markdown
WebSocket events: `session_created`, `tool_start`, `assistant_call`, `task_result`, `task_finalized`, `error`
```

In `README_CN.md`, add:

```markdown
- **GET /api/tasks/{thread_id}** — 查看任务持久化状态和输出路径
```

Update the WebSocket event line to:

```markdown
WebSocket 事件: `session_created`, `tool_start`, `assistant_call`, `task_result`, `task_finalized`, `error`
```

- [ ] **Step 3: Fix CLAUDE Node version**

In `CLAUDE.md`, replace:

```markdown
### Frontend (Node.js 18+)
```

with:

```markdown
### Frontend (Node.js 20.19+ or 22.12+)
```

- [ ] **Step 4: Update run log**

Append this section to `docs/evidence/run-log.md`:

```markdown
## Phase 9 Plan

- **状态**: PLANNED
- **目标**: 将 Phase 8 的 E2E 不稳定报告生成问题收敛为确定性后端终态：`completed`、`completed_with_fallback` 或 `failed`。
- **验证策略**: 后端单元测试覆盖 persistence、timeout、agent run accumulator 和 task finalizer；集成测试覆盖 completed、fallback、exception、timeout；真实 E2E 使用 `scripts/e2e_runner.py` 手动记录。
- **非目标**: 本阶段不做 5 问 benchmark，不做 prompt 调优，不把真实 LLM E2E 放入 CI。
```

- [ ] **Step 5: Run docs grep checks**

Run:

```bash
rg -n "completed_with_fallback|task_finalized|Node.js 18\\+" spec/api-contract.md README.md README_CN.md CLAUDE.md docs/evidence/run-log.md
```

Expected:
- `completed_with_fallback` appears in `spec/api-contract.md` and `docs/evidence/run-log.md`.
- `task_finalized` appears in `spec/api-contract.md`, `README.md`, and `README_CN.md`.
- No result contains `Node.js 18+`.

- [ ] **Step 6: Commit**

```bash
git add spec/api-contract.md README.md README_CN.md CLAUDE.md docs/evidence/run-log.md
git commit -m "docs: document task finalization contract"
```

---

### Task 10: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
python -m pytest tests/unit/test_persistence.py tests/unit/test_monitor_sanitization.py tests/unit/test_agent_run_result.py tests/unit/test_task_finalizer.py tests/unit/test_task_tracker.py tests/unit/test_task_tracker_timeout.py tests/integration/test_task_finalization_flow.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only Phase 9 implementation, runner, tests, and docs files are changed.

- [ ] **Step 5: Optional manual E2E**

Run only when backend is running with valid API keys:

```bash
python scripts/e2e_runner.py \
  --query "2024年AI发展趋势" \
  --thread-id "phase9-manual-001" \
  --timeout-seconds 900 \
  --output docs/evidence/phase9-manual-001.json
```

Expected:
- JSON `status` is `completed`, `completed_with_fallback`, or `failed`.
- `completed` and `completed_with_fallback` include a non-empty `output_path`.
- `completed_with_fallback` has `"fallback_used": true`.

- [ ] **Step 6: Final commit if manual E2E evidence was added**

If `docs/evidence/phase9-manual-001.json` was created and should be kept:

```bash
git add docs/evidence/phase9-manual-001.json
git commit -m "test: record phase 9 manual e2e evidence"
```

If the manual E2E file was not created, no commit is needed for this task.

---

## Self-Review

- Spec coverage: timeout failure, swallowed agent exceptions, last agent text capture, deterministic report selection, `completed_with_fallback`, frontend terminal event, E2E runner, and docs are all mapped to tasks.
- Placeholder scan: this plan contains no placeholder implementation steps.
- Type consistency: `AgentRunResult`, `AgentRunAccumulator`, `TaskFinalization`, `finalize_task_run`, `_run_task_with_persistence`, `_mark_task_timeout`, and `task_finalized` are defined before later tasks use them.
