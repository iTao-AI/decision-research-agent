"""异步任务错误处理和有序超时/取消管理。"""

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Literal

logger = logging.getLogger(__name__)

# 默认任务超时（秒）— 30 分钟
DEFAULT_TASK_TIMEOUT = int(os.getenv("AGENT_TASK_TIMEOUT_SECONDS", "1800"))

# 活跃任务字典: task_id -> (asyncio.Task, timeout_seconds, start_time)
active_tasks: Dict[str, tuple] = {}
TimeoutCallback = Callable[[str, int], Awaitable[Any] | Any]
CancelCallback = Callable[[str], Awaitable[Any] | Any]
TerminationKind = Literal["unset", "timeout", "cancelled"]


class TerminationOrigin:
    """记录第一个获得任务终止所有权的来源。"""

    def __init__(self) -> None:
        self._value: TerminationKind = "unset"

    def claim_timeout(self) -> bool:
        if self._value != "unset":
            return False
        self._value = "timeout"
        return True

    def claim_cancelled(self) -> bool:
        if self._value != "unset":
            return False
        self._value = "cancelled"
        return True

    @property
    def value(self) -> TerminationKind:
        return self._value


class FinalizationCheckpoint:
    """让 tracker 在一次 finalization 请求处决定继续或超时。"""

    def __init__(self) -> None:
        self._requested = asyncio.Event()
        self._released = asyncio.Event()
        self._request_started = False
        self._release_called = False

    async def request_and_wait(self) -> None:
        if self._request_started:
            raise RuntimeError("Finalization checkpoint already requested")
        self._request_started = True
        self._requested.set()
        await self._released.wait()

    async def wait_requested(self) -> None:
        await self._requested.wait()

    def release(self) -> None:
        if not self._request_started:
            raise RuntimeError("Finalization checkpoint released before request")
        if self._release_called:
            raise RuntimeError("Finalization checkpoint already released")
        self._release_called = True
        self._released.set()


def _cancellation_request_count(task: asyncio.Task[Any] | None) -> int:
    return task.cancelling() if task is not None else 0


async def settle_shielded_task(
    task: asyncio.Task,
) -> tuple[Any, BaseException | None, int]:
    """等待已启动任务完成，并把外层取消请求作为数据返回。"""

    owning_task = asyncio.current_task()
    cancellation_requests = _cancellation_request_count(owning_task)

    while not task.done():
        cancellation_requests = max(
            cancellation_requests,
            _cancellation_request_count(owning_task),
        )
        try:
            await asyncio.shield(task)
        except BaseException:
            # shield 可能因 target 结束或 owning task 被取消而抛出；两者都必须
            # 先等待 target 真正结束，再由调用者依据返回值分类。
            pass
        cancellation_requests = max(
            cancellation_requests,
            _cancellation_request_count(owning_task),
        )

    cancellation_requests = max(
        cancellation_requests,
        _cancellation_request_count(owning_task),
    )
    try:
        return task.result(), None, cancellation_requests
    except BaseException as exc:
        return None, exc, cancellation_requests


async def _invoke_callback(callback: Callable[..., Any], *args: Any) -> Any:
    callback_result = callback(*args)
    if inspect.isawaitable(callback_result):
        return await callback_result
    return callback_result


async def _settle_callback(
    callback: Callable[..., Any] | None,
    *args: Any,
) -> int:
    if callback is None:
        current_task = asyncio.current_task()
        return _cancellation_request_count(current_task)

    callback_task = asyncio.create_task(_invoke_callback(callback, *args))
    _, callback_exception, cancellation_requests = await settle_shielded_task(
        callback_task
    )
    if callback_exception is not None:
        logger.error(
            "Task termination callback failed",
            exc_info=(
                type(callback_exception),
                callback_exception,
                callback_exception.__traceback__,
            ),
        )
    return cancellation_requests


def create_tracked_task(
    coroutine,
    task_id: str,
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT,
    on_timeout: TimeoutCallback | None = None,
    on_cancel: CancelCallback | None = None,
    termination_origin: TerminationOrigin | None = None,
    finalization_checkpoint: FinalizationCheckpoint | None = None,
) -> asyncio.Task:
    """创建并跟踪任务，按单调终止来源完成有序清理。"""

    origin = termination_origin or TerminationOrigin()

    async def _with_timeout():
        loop = asyncio.get_running_loop()
        deadline_at = loop.time() + timeout_seconds
        owning_task = asyncio.current_task()
        outer_cancellation_requests = _cancellation_request_count(owning_task)

        inner_task = asyncio.create_task(coroutine)
        deadline_task = asyncio.create_task(asyncio.sleep(timeout_seconds))
        checkpoint_waiter_task = (
            asyncio.create_task(finalization_checkpoint.wait_requested())
            if finalization_checkpoint is not None
            else None
        )
        control_tasks = [deadline_task]
        if checkpoint_waiter_task is not None:
            control_tasks.append(checkpoint_waiter_task)

        terminal_mode: TerminationKind | None = None
        inner_result: Any = None
        inner_exception: BaseException | None = None

        try:
            while terminal_mode is None:
                live_control_tasks = [deadline_task]
                if checkpoint_waiter_task is not None:
                    live_control_tasks.append(checkpoint_waiter_task)
                try:
                    await asyncio.wait(
                        [inner_task, *live_control_tasks],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except asyncio.CancelledError:
                    outer_cancellation_requests = max(
                        outer_cancellation_requests,
                        _cancellation_request_count(owning_task),
                    )
                    origin.claim_cancelled()
                    terminal_mode = origin.value
                    break

                outer_cancellation_requests = max(
                    outer_cancellation_requests,
                    _cancellation_request_count(owning_task),
                )
                if outer_cancellation_requests:
                    origin.claim_cancelled()
                    terminal_mode = origin.value
                    break

                # 不依赖 asyncio.wait 返回 set 的迭代顺序：无外层取消时，inner
                # 在同一轮与 deadline 同时完成仍优先。
                if inner_task.done():
                    terminal_mode = "unset"
                    break

                if (
                    checkpoint_waiter_task is not None
                    and checkpoint_waiter_task.done()
                ):
                    if loop.time() >= deadline_at:
                        origin.claim_timeout()
                        terminal_mode = origin.value
                        break

                    finalization_checkpoint.release()
                    _, checkpoint_exception, checkpoint_cancellations = (
                        await settle_shielded_task(checkpoint_waiter_task)
                    )
                    outer_cancellation_requests = max(
                        outer_cancellation_requests,
                        checkpoint_cancellations,
                    )
                    if checkpoint_exception is not None:
                        raise checkpoint_exception
                    if outer_cancellation_requests:
                        origin.claim_cancelled()
                        terminal_mode = origin.value
                    checkpoint_waiter_task = None
                    continue

                if deadline_task.done():
                    origin.claim_timeout()
                    terminal_mode = origin.value

            if terminal_mode == "unset":
                inner_result, inner_exception, inner_cancellations = (
                    await settle_shielded_task(inner_task)
                )
                outer_cancellation_requests = max(
                    outer_cancellation_requests,
                    inner_cancellations,
                )
            else:
                if not inner_task.done():
                    inner_task.cancel()
                _, _, inner_cancellations = await settle_shielded_task(inner_task)
                outer_cancellation_requests = max(
                    outer_cancellation_requests,
                    inner_cancellations,
                )

                if terminal_mode == "timeout":
                    logger.warning(
                        "Task %s timed out after %ss", task_id, timeout_seconds
                    )
                    callback_cancellations = await _settle_callback(
                        on_timeout,
                        task_id,
                        timeout_seconds,
                    )
                else:
                    callback_cancellations = await _settle_callback(
                        on_cancel,
                        task_id,
                    )
                outer_cancellation_requests = max(
                    outer_cancellation_requests,
                    callback_cancellations,
                )
        finally:
            for control_task in control_tasks:
                if not control_task.done():
                    control_task.cancel()
            for control_task in control_tasks:
                _, _, control_cancellations = await settle_shielded_task(control_task)
                outer_cancellation_requests = max(
                    outer_cancellation_requests,
                    control_cancellations,
                )

        if outer_cancellation_requests and origin.value == "unset":
            origin.claim_cancelled()
            terminal_mode = origin.value
            callback_cancellations = await _settle_callback(on_cancel, task_id)
            outer_cancellation_requests = max(
                outer_cancellation_requests,
                callback_cancellations,
            )

        if outer_cancellation_requests or terminal_mode == "cancelled":
            raise asyncio.CancelledError
        if terminal_mode == "timeout":
            return None
        if inner_exception is not None:
            raise inner_exception
        return inner_result

    task = asyncio.create_task(_with_timeout())
    start_time = asyncio.get_event_loop().time()
    active_tasks[task_id] = (task, timeout_seconds, start_time)
    task.add_done_callback(lambda tracked_task: _on_task_done(tracked_task, task_id))
    return task


def _on_task_done(task: asyncio.Task, task_id: str):
    """任务完成回调。"""

    active_tasks.pop(task_id, None)

    try:
        exc = task.exception()
        if exc:
            if isinstance(exc, asyncio.CancelledError):
                logger.info("Task %s was cancelled (possibly due to timeout)", task_id)
            else:
                logger.error("Task %s failed with exception: %s", task_id, exc)
    except asyncio.CancelledError:
        logger.info("Task %s was cancelled", task_id)
    except Exception:
        pass


def get_active_task(task_id: str) -> asyncio.Task | None:
    """获取指定任务。"""

    entry = active_tasks.get(task_id)
    return entry[0] if entry else None


def clear_active_tasks():
    """清理所有活跃任务（测试用）。"""

    active_tasks.clear()
