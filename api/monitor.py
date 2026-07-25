"""Best-effort delivery for the closed application observation contract."""

from __future__ import annotations

import asyncio
import builtins
from concurrent.futures import Future
from datetime import datetime, timezone
from threading import RLock
import time
from typing import Callable

from fastapi import WebSocket

from agent.telemetry import TelemetryRecord, collector
from api.context import get_run_context, get_segment_context, get_thread_context
from api.observation_contract import projector


def _safe_console(fixed_message: str) -> None:
    """Emit only a caller-owned fixed message and never affect execution."""
    try:
        print(f"\n[Monitor] {fixed_message}")
    except Exception:
        pass


def sanitize_args(args: object) -> dict[str, object]:
    """Return the closed descriptor used by compatibility monitor callers."""
    return projector.descriptor(args)


def _explicit_or_context(
    explicit: object,
    getter: Callable[[], object],
) -> str | None:
    """Select an explicit built-in string or a built-in-string context value."""
    if explicit is not None:
        return explicit if type(explicit) is str else None
    try:
        contextual = getter()
    except Exception:
        return None
    return contextual if type(contextual) is str else None


def _copy_event_payload(payload: dict[str, object]) -> dict[str, object]:
    """Make one independent fixed-depth built-in copy for an observation sink."""
    source_data = payload["data"]
    copied_data = {
        key: dict(value) if type(value) is dict else value
        for key, value in source_data.items()
    }
    return {
        "type": payload["type"],
        "schema": payload["schema"],
        "event": payload["event"],
        "message": payload["message"],
        "data": copied_data,
        "thread_id": payload["thread_id"],
        "run_id": payload["run_id"],
        "segment_id": payload["segment_id"],
        "timestamp": payload["timestamp"],
    }


async def _protected_websocket_send(
    manager: object,
    payload: dict[str, object],
    run_id: str | None,
    thread_id: str | None,
) -> None:
    """Create and await the manager send inside one exception-consuming task."""
    try:
        if run_id is not None:
            await manager.send_to_run(payload, run_id)
        elif thread_id is not None:
            await manager.send_to_thread(payload, thread_id)
    except asyncio.CancelledError:
        pass
    except Exception:
        _safe_console("WebSocket delivery failed")


class ToolMonitor:
    """Deliver safe tool observations without changing tool execution.

    Reporter inputs are untrusted. Registered aliases such as ``tavily_search``
    remain exact; other labels become closed sentinels. ``args`` and ``result``
    keep their compatibility field positions but contain descriptors only.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None or not isinstance(cls._instance, cls):
            instance = super().__new__(cls)
            instance.websocket_manager = None
            instance._start_times: dict[tuple[str, str], list[float]] = {}
            instance._start_times_lock = RLock()
            instance._pending_lock = RLock()
            instance._pending_tasks: set[asyncio.Task[None]] = set()
            instance._pending_futures: set[Future[None]] = set()
            cls._instance = instance
        return cls._instance

    def set_websocket_manager(self, manager: object) -> None:
        """Set the FastAPI WebSocket manager."""
        self.websocket_manager = manager

    def _pending_snapshot(
        self,
    ) -> tuple[tuple[asyncio.Task[None], ...], tuple[Future[None], ...]]:
        """Return a thread-safe immutable snapshot for deterministic settlement."""
        with self._pending_lock:
            return tuple(self._pending_tasks), tuple(self._pending_futures)

    def _consume_done(
        self,
        kind: str,
        completed: asyncio.Task[None] | Future[None],
    ) -> None:
        try:
            if not completed.cancelled():
                completed.exception()
        except Exception:
            _safe_console("WebSocket delivery failed")
        finally:
            with self._pending_lock:
                if kind == "task":
                    self._pending_tasks.discard(completed)
                else:
                    self._pending_futures.discard(completed)

    def _register_pending(
        self,
        kind: str,
        scheduled: asyncio.Task[None] | Future[None],
    ) -> None:
        pending = (
            self._pending_tasks
            if kind == "task"
            else self._pending_futures
        )
        try:
            with self._pending_lock:
                pending.add(scheduled)
                try:
                    scheduled.add_done_callback(
                        lambda completed: self._consume_done(kind, completed)
                    )
                except Exception:
                    pending.discard(scheduled)
                    raise
        except Exception:
            _safe_console("WebSocket delivery failed")

    def _schedule_websocket_send(
        self,
        payload: dict[str, object],
        run_id: str | None,
        thread_id: str | None,
    ) -> None:
        """Schedule one protected send and retain it until completion."""
        manager = self.websocket_manager
        if manager is None:
            return
        try:
            manager_loop = manager.get_loop()
        except Exception:
            _safe_console("WebSocket delivery failed")
            return
        if (
            manager_loop is None
            or manager_loop.is_closed()
            or not manager_loop.is_running()
        ):
            return

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        except Exception:
            current_loop = None

        protected = _protected_websocket_send(
            manager,
            payload,
            run_id,
            thread_id,
        )
        if current_loop is manager_loop:
            try:
                task = current_loop.create_task(protected)
            except Exception:
                protected.close()
                _safe_console("WebSocket delivery failed")
                return
            self._register_pending("task", task)
            return

        try:
            future = asyncio.run_coroutine_threadsafe(protected, manager_loop)
        except Exception:
            protected.close()
            _safe_console("WebSocket delivery failed")
            return
        self._register_pending("future", future)

    def _emit(
        self,
        event_type: object,
        message: object,
        data: object = None,
        thread_id: object = None,
        run_id: object = None,
        segment_id: object = None,
    ) -> None:
        """Project once, then independently deliver closed built-in copies."""
        del message
        target_thread_id = _explicit_or_context(thread_id, get_thread_context)
        target_run_id = _explicit_or_context(run_id, get_run_context)
        target_segment_id = _explicit_or_context(
            segment_id,
            get_segment_context,
        )
        try:
            payload = projector.monitor_event(
                event_type=event_type,
                data=data,
                thread_id=target_thread_id,
                run_id=target_run_id,
                segment_id=target_segment_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            _safe_console("Observation projection rejected")
            return
        if payload is None:
            _safe_console("Observation projection rejected")
            return

        projected_run_id = payload["run_id"]
        projected_thread_id = payload["thread_id"]
        if (
            self.websocket_manager is not None
            and (
                projected_run_id is not None
                or projected_thread_id is not None
            )
        ):
            self._schedule_websocket_send(
                _copy_event_payload(payload),
                projected_run_id,
                projected_thread_id,
            )

        try:
            runtime = getattr(builtins, "runtime", None)
            writer = getattr(runtime, "stream_writer", None)
            if callable(writer):
                writer(_copy_event_payload(payload))
        except Exception:
            _safe_console("stream_writer delivery failed")

        _safe_console(payload["message"])

    @staticmethod
    def _context_string(getter: Callable[[], object], fallback: str | None) -> str | None:
        try:
            value = getter()
        except Exception:
            return fallback
        return value if type(value) is str else fallback

    def _timing_key(self, tool_name: object) -> tuple[str, str]:
        run_id = self._context_string(get_run_context, None)
        thread_id = self._context_string(get_thread_context, "default")
        execution_id = run_id if run_id is not None else thread_id
        safe_tool_name = tool_name if type(tool_name) is str else "unknown_tool"
        return execution_id or "default", safe_tool_name

    def report_start(self, tool_name: str, args: object = None) -> None:
        """Report tool start without retaining argument content."""
        timing_key = self._timing_key(tool_name)
        with self._start_times_lock:
            self._start_times.setdefault(timing_key, []).append(time.monotonic())
        self._emit(
            "tool_start",
            "Tool execution started",
            {"tool_name": tool_name, "args": args},
        )

    def report_tool(self, tool_name: str, args: object = None) -> None:
        """Backward-compatible alias for report_start."""
        self.report_start(tool_name, args)

    def report_end(
        self,
        tool_name: str,
        result: object = None,
        error: object = None,
        error_type: object = None,
    ) -> None:
        """Report tool completion without retaining result or exception content."""
        timing_key = self._timing_key(tool_name)
        with self._start_times_lock:
            starts = self._start_times.get(timing_key, [])
            start = starts.pop() if starts else None
            if not starts:
                self._start_times.pop(timing_key, None)
        duration_ms = (
            (time.monotonic() - start) * 1000.0
            if start is not None
            else 0.0
        )
        status = (
            "success"
            if error is None or (type(error) is str and error == "")
            else "error"
        )
        thread_id = self._context_string(get_thread_context, "default")
        run_id = self._context_string(get_run_context, None)
        segment_id = self._context_string(get_segment_context, None)
        try:
            collector.record(
                TelemetryRecord(
                    thread_id=thread_id,
                    run_id=run_id,
                    segment_id=segment_id,
                    agent_name="main",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    status=status,
                    error=error,
                    error_type=error_type,
                )
            )
        except Exception:
            _safe_console("Telemetry delivery failed")
        self._emit(
            "tool_end",
            "Tool execution completed",
            {
                "tool_name": tool_name,
                "status": status,
                "result": result,
                "error": error,
                "error_type": error_type,
                "duration_ms": duration_ms,
            },
        )

    def report_assistant(self, assistant_name: str, args: object = None) -> None:
        """Report an assistant call using only registered observation aliases."""
        self._emit(
            "assistant_call",
            "Assistant call started",
            {"assistant_name": assistant_name, "args": args},
        )

    def report_task_result(self, result: object) -> None:
        """Report only that the canonical task result is available."""
        self._emit(
            "task_result",
            "Task result available",
            {"result": result},
        )

    def report_task_finalized(
        self,
        thread_id: str,
        status: str,
        fallback_used: bool = False,
        output_path: str | None = None,
        error_message: object = None,
    ) -> None:
        """Report closed terminal task persistence state."""
        self._emit(
            "task_finalized",
            "Task finalized",
            {
                "status": status,
                "fallback_used": fallback_used,
                "output_path": output_path,
                "error": error_message,
            },
            thread_id=thread_id,
        )

    def report_session_dir(self, path: str) -> None:
        """Report workspace presence without exposing its path."""
        self._emit(
            "session_created",
            "Workspace created",
            {"path": path},
        )

    def report_retry(
        self,
        service_name: str,
        attempt: int,
        max_retries: int,
        error: object = None,
        error_type: object = None,
    ) -> None:
        """Report a retry while discarding legacy raw error input."""
        del error
        self._emit(
            "retry_event",
            "Retry scheduled",
            {
                "service_name": service_name,
                "attempt": attempt,
                "max_retries": max_retries,
                "error": "retryable_failure",
                "error_type": error_type,
            },
        )

    def report_cache_hit(self, tool_name: str, cached: bool = True) -> None:
        """Report cache presence for a registered tool alias."""
        event = "cache_hit" if cached else "cache_miss"
        self._emit(
            event,
            "Tool cache result",
            {"tool_name": tool_name, "cached": cached},
        )


monitor = ToolMonitor()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.active_run_connections: dict[str, WebSocket] = {}
        self.run_threads: dict[str, str] = {}
        self.loop = None

    def get_loop(self):
        """Lazily bind the current running event loop."""
        try:
            current_loop = asyncio.get_running_loop()
            if (
                self.loop is None
                or self.loop.is_closed()
                or not self.loop.is_running()
            ):
                self.loop = current_loop
                monitor.set_websocket_manager(self)
                _safe_console("Connection manager bound")
        except RuntimeError:
            _safe_console("No running event loop")
        except Exception:
            _safe_console("Event loop lookup failed")
        return self.loop

    async def connect(self, websocket: WebSocket, thread_id: str):
        self.get_loop()
        await websocket.accept()
        self.active_connections[thread_id] = websocket
        _safe_console("Client connected")

    async def connect_run(
        self,
        websocket: WebSocket,
        run_id: str,
        thread_id: str,
    ):
        self.get_loop()
        await websocket.accept()
        self.active_run_connections[run_id] = websocket
        self.run_threads[run_id] = thread_id
        _safe_console("Run client connected")

    def disconnect(self, websocket: WebSocket, thread_id: str):
        del websocket
        if thread_id in self.active_connections:
            del self.active_connections[thread_id]
        _safe_console("Client disconnected")

    def disconnect_run(self, websocket: WebSocket, run_id: str):
        if self.active_run_connections.get(run_id) is websocket:
            del self.active_run_connections[run_id]
            self.run_threads.pop(run_id, None)
        _safe_console("Run client disconnected")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def send_to_thread(self, message: dict, thread_id: str):
        if thread_id in self.active_connections:
            websocket = self.active_connections[thread_id]
            await websocket.send_json(message)

    async def send_to_run(self, message: dict, run_id: str):
        if run_id in self.active_run_connections:
            websocket = self.active_run_connections[run_id]
            await websocket.send_json(message)


manager = ConnectionManager()
