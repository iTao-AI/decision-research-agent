"""异步任务错误处理和超时管理"""
import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 默认任务超时（秒）— 30 分钟
DEFAULT_TASK_TIMEOUT = int(os.getenv("AGENT_TASK_TIMEOUT_SECONDS", "1800"))

# 活跃任务字典: task_id -> (asyncio.Task, timeout_seconds, start_time)
active_tasks: Dict[str, tuple] = {}
TimeoutCallback = Callable[[str, int], Awaitable[Any] | Any]


def create_tracked_task(
    coroutine,
    task_id: str,
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT,
    on_timeout: TimeoutCallback | None = None,
) -> asyncio.Task:
    """创建并跟踪异步任务，带超时保护。

    使用 asyncio.wait_for 包裹协程，超时后自动取消任务。

    Args:
        coroutine: 要执行的协程
        task_id: 任务标识
        timeout_seconds: 超时时间（秒），默认从环境变量 AGENT_TASK_TIMEOUT_SECONDS 读取

    Returns:
        asyncio.Task: 创建的任务对象
    """
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


def _on_task_done(task: asyncio.Task, task_id: str):
    """任务完成回调"""
    # 从活跃字典中移除
    active_tasks.pop(task_id, None)

    # 检查异常
    try:
        exc = task.exception()
        if exc:
            if isinstance(exc, asyncio.CancelledError):
                logger.info(f"Task {task_id} was cancelled (possibly due to timeout)")
            else:
                logger.error(f"Task {task_id} failed with exception: {exc}")
    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was cancelled")
    except Exception:
        pass


def check_timeouts() -> list:
    """检查所有活跃任务是否超时，超时则取消。

    Returns:
        被取消的任务 ID 列表
    """
    cancelled = []
    now = asyncio.get_event_loop().time()
    timed_out_ids = []

    for task_id, (task, timeout_seconds, start_time) in active_tasks.items():
        elapsed = now - start_time
        if elapsed > timeout_seconds:
            timed_out_ids.append(task_id)

    for task_id in timed_out_ids:
        if task_id in active_tasks:
            task, timeout_seconds, _ = active_tasks[task_id]
            logger.warning(
                f"Task {task_id} timed out after {timeout_seconds}s, cancelling"
            )
            task.cancel()
            cancelled.append(task_id)

    return cancelled


def get_active_task(task_id: str) -> asyncio.Task | None:
    """获取指定任务"""
    entry = active_tasks.get(task_id)
    return entry[0] if entry else None


def clear_active_tasks():
    """清理所有活跃任务（测试用）"""
    active_tasks.clear()
