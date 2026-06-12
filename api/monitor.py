import datetime
import asyncio
import time
from threading import RLock
from typing import Any, Dict, Optional
from fastapi import WebSocket
from api.context import get_run_context, get_segment_context, get_thread_context
from agent.telemetry import collector, TelemetryRecord

# Exact match for known sensitive field names (case-insensitive)
# Includes common variants: api_key, secret_key, access_token, auth_token, etc.
_SENSITIVE_FIELDS = {
    "api_key", "secret_key", "access_key", "secret", "password", "passwd",
    "token", "access_token", "refresh_token", "auth_token", "jwt",
    "api_secret", "client_secret", "private_key",
    "authorization", "auth", "credential",
}
# Suffix patterns for fields that end with these (e.g. "my_api_key")
_SENSITIVE_SUFFIXES = ["_key", "_secret", "_token", "_password", "_auth"]
_MAX_VALUE_LENGTH = 200
_REDACTED = "***REDACTED***"


def sanitize_args(args: dict | None) -> dict | None:
    """Sanitize tool arguments before logging. Redact sensitive fields, truncate long strings."""
    if args is None:
        return None
    result = {}
    for k, v in args.items():
        k_lower = k.lower()
        # Exact match or ends-with sensitive suffix
        if k_lower in _SENSITIVE_FIELDS or any(k_lower.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES):
            result[k] = _REDACTED
        elif isinstance(v, str) and len(v) > _MAX_VALUE_LENGTH:
            result[k] = v[:_MAX_VALUE_LENGTH] + f"... (truncated, {len(v)} chars total)"
        else:
            result[k] = v
    return result


# 尝试导入全局运行时（用于脚本模式下的流式输出）
try:
    import builtins
except ImportError:
    builtins = None


class ToolMonitor:
    """
    工具监控类，用于在工具执行过程中上报进度和状态。
    设计为单例模式，可在任何工具中直接导入使用。
    兼容 FastAPI WebSocket 和 脚本运行时的 stream_writer。

    使用示例:
    from api.monitor import monitor

    def my_tool(arg1):
        monitor.report_start("my_tool", {"arg1": arg1})
        ...
        monitor.report_running("my_tool", "正在处理数据...", progress=0.5)
        ...
        monitor.report_end("my_tool", result)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None or not isinstance(cls._instance, cls):
            instance = super(ToolMonitor, cls).__new__(cls)
            instance.websocket_manager = None
            instance._start_times: dict[tuple[str, str], list[float]] = {}
            instance._start_times_lock = RLock()
            cls._instance = instance
        return cls._instance

    def set_websocket_manager(self, manager):
        """设置 FastAPI 的 WebSocket 管理器"""
        self.websocket_manager = manager

    def _schedule_websocket_send(self, payload: dict, run_id: str | None, thread_id: str | None):
        """Schedule one WebSocket send without leaking a coroutine on loop failure."""
        manager_loop = self.websocket_manager.get_loop()
        if not manager_loop or not manager_loop.is_running():
            return

        send = (
            self.websocket_manager.send_to_run(payload, run_id)
            if run_id
            else self.websocket_manager.send_to_thread(payload, thread_id)
        )
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        try:
            if current_loop is manager_loop:
                current_loop.create_task(send)
            else:
                asyncio.run_coroutine_threadsafe(send, manager_loop)
        except Exception:
            send.close()
            raise

    def _emit(
        self,
        event_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        segment_id: str | None = None,
    ):
        """内部发送方法"""
        target_thread_id = thread_id or get_thread_context()
        target_run_id = run_id or get_run_context()
        target_segment_id = segment_id or get_segment_context()
        payload = {
            "type": "monitor_event",
            "event": event_type,
            "message": message,
            "data": data or {},
            "thread_id": target_thread_id,
            "run_id": target_run_id,
            "segment_id": target_segment_id,
            "timestamp": datetime.datetime.now().isoformat()
        }

        # 1. 优先尝试通过 FastAPI WebSocket 发送 (定向推送)
        if self.websocket_manager:
            try:
                if target_run_id or target_thread_id:
                    self._schedule_websocket_send(payload, target_run_id, target_thread_id)
            except Exception as e:
                print(f"[Monitor] WebSocket send failed: {e}")

        # 2. 尝试通过全局 runtime 输出 (DeepAgents 脚本模式)
        # 这使得 simple_agents.py 中的 MockRuntime 能接收到数据
        if builtins and hasattr(builtins, 'runtime') and hasattr(builtins.runtime, 'stream_writer'):
            try:
                builtins.runtime.stream_writer(payload)
            except Exception:
                pass

        # 3. 控制台保底输出 (方便调试)
        # 加上特殊前缀，方便肉眼识别
        print(f"\n[Monitor:{event_type}] {message}")

    def report_start(self, tool_name: str, args: Dict[str, Any] = None):
        """报告工具开始执行"""
        execution_id = get_run_context() or get_thread_context() or "default"
        with self._start_times_lock:
            self._start_times.setdefault((execution_id, tool_name), []).append(
                time.monotonic()
            )
        sanitized = sanitize_args(args)
        self._emit("tool_start", f"开始执行工具: {tool_name}", {"tool_name": tool_name, "args": sanitized})

    def report_tool(self, tool_name: str, args: Dict[str, Any] = None):
        """Backward-compatible alias for report_start."""
        self.report_start(tool_name, args)

    def report_end(self, tool_name: str, result: Any = None, error: str | None = None):
        """报告工具执行结束，生成 TelemetryRecord。"""
        thread_id = get_thread_context() or "default"
        run_id = get_run_context()
        segment_id = get_segment_context()
        execution_id = run_id or thread_id
        with self._start_times_lock:
            starts = self._start_times.get((execution_id, tool_name), [])
            start = starts.pop() if starts else None
            if not starts:
                self._start_times.pop((execution_id, tool_name), None)
        duration_ms = 0.0
        if start is not None:
            duration_ms = (time.monotonic() - start) * 1000.0

        status = "error" if error else "success"

        collector.record(TelemetryRecord(
            thread_id=thread_id,
            run_id=run_id,
            segment_id=segment_id,
            agent_name="main",
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            error=error,
        ))

        self._emit("tool_end", f"工具执行完成: {tool_name}", {
            "tool_name": tool_name,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
        })

    def report_assistant(self, assistant_name: str, args: Dict[str, Any] = None):
        """报告正在调用的子智能体进度"""
        sanitized = sanitize_args(args)
        self._emit("assistant_call", f"正在调用助手: {assistant_name}",
                   {"assistant_name": assistant_name, "args": sanitized})

    def report_task_result(self, result: str):
        """报告任务最终结果"""
        if isinstance(result, dict):
            sanitized = sanitize_args(result)
            self._emit("task_result", "任务执行完成", {"result": sanitized})
        elif isinstance(result, str) and len(result) > _MAX_VALUE_LENGTH:
            truncated = result[:_MAX_VALUE_LENGTH] + f"... (truncated, {len(result)} chars total)"
            self._emit("task_result", "任务执行完成", {"result": truncated})
        else:
            self._emit("task_result", "任务执行完成", {"result": result})

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
            thread_id=thread_id,
        )

    def report_session_dir(self, path: str):
        """报告任务工作目录"""
        self._emit("session_created", f"工作目录已创建: {path}", {"path": path})

    def report_retry(self, service_name: str, attempt: int, max_retries: int, error: str = ""):
        """报告服务调用重试事件（供 @retry 装饰器使用）"""
        message = f"Retry {attempt}/{max_retries} for {service_name}"
        if error:
            message += f": {error}"
        self._emit("retry_event", message, {
            "service_name": service_name,
            "attempt": attempt,
            "max_retries": max_retries,
            "error": error,
        })

    def report_cache_hit(self, tool_name: str, cached: bool = True):
        """报告缓存命中/未命中事件（供 @cached_tool 装饰器使用）"""
        event = "cache_hit" if cached else "cache_miss"
        self._emit(event, f"Cache {event} for {tool_name}", {
            "tool_name": tool_name,
            "cached": cached,
        })


# 全局单例实例
monitor = ToolMonitor()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.active_run_connections: Dict[str, WebSocket] = {}
        self.run_threads: Dict[str, str] = {}
        # 延迟绑定 loop，防止初始化时 loop 不一致
        self.loop = None

    def get_loop(self):
        """懒加载获取当前运行的事件循环"""
        try:
            current_loop = asyncio.get_running_loop()
            if self.loop is None or self.loop.is_closed() or not self.loop.is_running():
                self.loop = current_loop
                # 同时设置 monitor 的 manager (确保双向绑定)
                monitor.set_websocket_manager(self)
                print(f"[Monitor] ConnectionManager auto-bound to loop: {id(self.loop)}")
        except RuntimeError:
            print("[Monitor] Warning: No running event loop found yet.")
        return self.loop

    async def connect(self, websocket: WebSocket, thread_id: str):
        # 每次连接时尝试获取/更新 loop
        self.get_loop()

        await websocket.accept()
        self.active_connections[thread_id] = websocket
        print(f"Client connected: {thread_id}")

    async def connect_run(self, websocket: WebSocket, run_id: str, thread_id: str):
        self.get_loop()
        await websocket.accept()
        self.active_run_connections[run_id] = websocket
        self.run_threads[run_id] = thread_id
        print(f"Client connected: {thread_id}/{run_id}")

    def disconnect(self, websocket: WebSocket, thread_id: str):
        if thread_id in self.active_connections:
            del self.active_connections[thread_id]
        print(f"Client disconnected: {thread_id}")

    def disconnect_run(self, websocket: WebSocket, run_id: str):
        if self.active_run_connections.get(run_id) is websocket:
            del self.active_run_connections[run_id]
            self.run_threads.pop(run_id, None)
        print(f"Client disconnected: {run_id}")

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
