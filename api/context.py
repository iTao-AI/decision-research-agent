from contextvars import ContextVar
from typing import Optional

# ContextVar is used to isolate per-request state in async contexts.
# Using a global variable or threading.local would cause data races
# when multiple requests run concurrently in the same event loop.

_session_dir_ctx: ContextVar[Optional[str]] = ContextVar("session_dir", default=None)
_thread_id_ctx: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)
_run_id_ctx: ContextVar[Optional[str]] = ContextVar("run_id", default=None)
_segment_id_ctx: ContextVar[Optional[str]] = ContextVar("segment_id", default=None)
_allowed_source_domains_ctx: ContextVar[tuple[str, ...]] = ContextVar(
    "allowed_source_domains", default=()
)


def set_session_context(path: str):
    """
    设置当前请求链路的会话目录。
    通常在 Agent 开始执行任务前调用。
    
    Returns:
        Token: 返回一个 Token 对象，后续可用它来恢复(reset)变量状态。
    """
    return _session_dir_ctx.set(path)

def get_session_context() -> Optional[str]:
    """
    获取当前请求链路的会话目录。
    可以在任何深层调用的工具函数中直接使用，无需层层传递参数。
    """
    return _session_dir_ctx.get()

def set_thread_context(thread_id: str):
    """
    设置当前请求链路的 Thread ID。
    """
    return _thread_id_ctx.set(thread_id)

def get_thread_context() -> Optional[str]:
    """
    获取当前请求链路的 Thread ID。
    """
    return _thread_id_ctx.get()

def set_run_context(run_id: str):
    """Set the application ResearchRun identity for the current execution."""
    return _run_id_ctx.set(run_id)

def get_run_context() -> Optional[str]:
    """Get the application ResearchRun identity without changing LangGraph thread state."""
    return _run_id_ctx.get()

def set_segment_context(segment_id: str | None):
    """Set the current business segment identity."""
    return _segment_id_ctx.set(segment_id)

def get_segment_context() -> Optional[str]:
    """Get the current business segment identity."""
    return _segment_id_ctx.get()

def set_allowed_source_domains_context(domains: tuple[str, ...]):
    """Set server-validated public source domains for a restricted research run."""
    return _allowed_source_domains_ctx.set(domains)

def get_allowed_source_domains_context() -> tuple[str, ...]:
    """Get the public source allowlist for the current restricted research run."""
    return _allowed_source_domains_ctx.get()

def reset_execution_context(
    run_token, thread_token=None, segment_token=None, allowed_source_domains_token=None
):
    """Reset run and thread identities after one execution."""
    if segment_token is not None:
        _segment_id_ctx.reset(segment_token)
    if allowed_source_domains_token is not None:
        _allowed_source_domains_ctx.reset(allowed_source_domains_token)
    _run_id_ctx.reset(run_token)
    if thread_token:
        _thread_id_ctx.reset(thread_token)

def reset_session_context(session_token, thread_token=None):
    """
    清理/重置上下文。
    通常在请求处理结束 (finally 块) 中调用，防止内存泄漏或污染后续请求。
    """
    _session_dir_ctx.reset(session_token)
    if thread_token:
        _thread_id_ctx.reset(thread_token)


if __name__ == "__main__":
    import asyncio

    async def demo():
        token1 = set_session_context("/data/user1")
        print(f"Context: {get_session_context()}")
        reset_session_context(token1)

    asyncio.run(demo())
