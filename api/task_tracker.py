"""异步任务错误处理"""
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# 活跃任务字典
active_tasks: Dict[str, asyncio.Task] = {}


def create_tracked_task(coroutine, task_id: str) -> asyncio.Task:
    """
    创建并跟踪异步任务。

    Args:
        coroutine: 要执行的协程
        task_id: 任务标识

    Returns:
        asyncio.Task: 创建的任务对象
    """
    task = asyncio.create_task(coroutine)
    active_tasks[task_id] = task
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
            logger.error(f"Task {task_id} failed with exception: {exc}")
    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was cancelled")
    except Exception:
        pass


def get_active_task(task_id: str) -> asyncio.Task | None:
    """获取指定任务"""
    return active_tasks.get(task_id)


def clear_active_tasks():
    """清理所有活跃任务（测试用）"""
    active_tasks.clear()
