"""异步任务跟踪、终止来源和 shield-and-settle 契约测试。"""

import asyncio

import pytest


class TestTaskTracker:
    @pytest.mark.asyncio
    async def test_create_tracked_task(self):
        """创建的任务在运行期间可查询，完成后返回原始结果。"""
        from api.task_tracker import (
            clear_active_tasks,
            create_tracked_task,
            get_active_task,
        )

        clear_active_tasks()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def dummy_task():
            started.set()
            await finish.wait()
            return "done"

        task = create_tracked_task(dummy_task(), "test-1")
        await started.wait()

        assert get_active_task("test-1") is task

        finish.set()
        assert await task == "done"

    @pytest.mark.asyncio
    async def test_task_removed_after_completion(self):
        """任务完成后应该从字典中移除。"""
        from api.task_tracker import (
            clear_active_tasks,
            create_tracked_task,
            get_active_task,
        )

        clear_active_tasks()

        async def quick_task():
            return "done"

        task = create_tracked_task(quick_task(), "test-2")
        assert await task == "done"
        assert get_active_task("test-2") is None

    @pytest.mark.asyncio
    async def test_task_exception_logged_and_removed(self, caplog):
        """任务异常应该被记录，且任务条目仍被移除。"""
        from api.task_tracker import (
            clear_active_tasks,
            create_tracked_task,
            get_active_task,
        )

        clear_active_tasks()

        async def failing_task():
            raise ValueError("test error")

        task = create_tracked_task(failing_task(), "test-3")
        with pytest.raises(ValueError, match="test error"):
            await task

        assert get_active_task("test-3") is None
        assert "Task test-3 failed with exception: test error" in caplog.text

    @pytest.mark.asyncio
    async def test_clear_active_tasks(self):
        """显式清理只移除跟踪条目，不遗留本测试创建的运行任务。"""
        from api.task_tracker import active_tasks, clear_active_tasks, create_tracked_task

        clear_active_tasks()
        started = [asyncio.Event(), asyncio.Event()]
        finish = asyncio.Event()

        async def dummy(index: int):
            started[index].set()
            await finish.wait()

        tasks = [
            create_tracked_task(dummy(0), "test-4"),
            create_tracked_task(dummy(1), "test-5"),
        ]
        await asyncio.gather(*(event.wait() for event in started))

        assert len(active_tasks) == 2
        clear_active_tasks()
        assert active_tasks == {}

        finish.set()
        await asyncio.gather(*tasks)


def test_termination_origin_first_claim_wins():
    from api.task_tracker import TerminationOrigin

    timeout_origin = TerminationOrigin()
    assert timeout_origin.value == "unset"
    assert timeout_origin.claim_timeout() is True
    assert timeout_origin.value == "timeout"
    assert timeout_origin.claim_timeout() is False
    assert timeout_origin.claim_cancelled() is False
    assert timeout_origin.value == "timeout"

    cancelled_origin = TerminationOrigin()
    assert cancelled_origin.claim_cancelled() is True
    assert cancelled_origin.value == "cancelled"
    assert cancelled_origin.claim_timeout() is False


@pytest.mark.asyncio
async def test_finalization_checkpoint_is_one_shot_and_rejects_misuse():
    from api.task_tracker import FinalizationCheckpoint

    checkpoint = FinalizationCheckpoint()
    request = asyncio.create_task(checkpoint.request_and_wait())
    await checkpoint.wait_requested()

    with pytest.raises(RuntimeError, match="already requested"):
        await checkpoint.request_and_wait()

    checkpoint.release()
    await request

    with pytest.raises(RuntimeError, match="already released"):
        checkpoint.release()

    never_requested = FinalizationCheckpoint()
    with pytest.raises(RuntimeError, match="before request"):
        never_requested.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_target_error", [False, True])
async def test_settle_shielded_task_returns_result_or_exception_after_cancellation(
    raise_target_error: bool,
):
    from api.task_tracker import settle_shielded_task

    target_started = asyncio.Event()
    target_release = asyncio.Event()
    owner_started = asyncio.Event()

    async def target_coroutine():
        target_started.set()
        await target_release.wait()
        if raise_target_error:
            raise ValueError("target failed")
        return "settled"

    target = asyncio.create_task(target_coroutine())

    async def owner_coroutine():
        owner_started.set()
        return await settle_shielded_task(target)

    owner = asyncio.create_task(owner_coroutine())
    await target_started.wait()
    await owner_started.wait()

    owner.cancel()
    target_release.set()

    result, target_exception, cancellation_requests = await owner
    assert cancellation_requests >= 1
    assert owner.cancelled() is False
    if raise_target_error:
        assert result is None
        assert isinstance(target_exception, ValueError)
        assert str(target_exception) == "target failed"
    else:
        assert result == "settled"
        assert target_exception is None


@pytest.mark.asyncio
async def test_settle_shielded_task_returns_target_self_cancel_without_outer_cancel():
    from api.task_tracker import settle_shielded_task

    async def self_cancel():
        raise asyncio.CancelledError

    target = asyncio.create_task(self_cancel())
    result, target_exception, cancellation_requests = await settle_shielded_task(target)

    assert result is None
    assert isinstance(target_exception, asyncio.CancelledError)
    assert cancellation_requests == 0


@pytest.mark.asyncio
async def test_caller_propagates_outer_cancel_only_after_settlement_and_classification():
    from api.task_tracker import settle_shielded_task

    target_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    cleanup_finished = asyncio.Event()
    settlement_started = asyncio.Event()
    classified = asyncio.Event()

    async def target_coroutine():
        target_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await cleanup_release.wait()
            cleanup_finished.set()

    target = asyncio.create_task(target_coroutine())
    await target_started.wait()
    target.cancel()

    async def caller():
        settlement_started.set()
        result, target_exception, cancellation_requests = await settle_shielded_task(
            target
        )
        assert result is None
        assert isinstance(target_exception, asyncio.CancelledError)
        classified.set()
        if cancellation_requests:
            raise asyncio.CancelledError

    caller_task = asyncio.create_task(caller())
    await settlement_started.wait()
    await cleanup_started.wait()
    caller_task.cancel()

    assert classified.is_set() is False
    assert caller_task.done() is False

    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller_task

    assert cleanup_finished.is_set()
    assert classified.is_set()
