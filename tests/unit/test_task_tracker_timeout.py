"""任务超时、取消竞态和有序清理契约测试。"""

import asyncio
import importlib
import logging
import os

import pytest


@pytest.mark.asyncio
async def test_normal_completion_invokes_neither_callback():
    from api.task_tracker import (
        TerminationOrigin,
        clear_active_tasks,
        create_tracked_task,
        get_active_task,
    )

    clear_active_tasks()
    origin = TerminationOrigin()
    calls = []

    async def complete():
        return "done"

    task = create_tracked_task(
        complete(),
        "normal-completion",
        on_timeout=lambda *_: calls.append("timeout"),
        on_cancel=lambda *_: calls.append("cancelled"),
        termination_origin=origin,
    )

    assert await task == "done"
    assert calls == []
    assert origin.value == "unset"
    assert get_active_task("normal-completion") is None


@pytest.mark.asyncio
async def test_timeout_claims_origin_before_inner_cancel_and_calls_timeout_once():
    from api.task_tracker import (
        TerminationOrigin,
        clear_active_tasks,
        create_tracked_task,
        get_active_task,
    )

    clear_active_tasks()
    origin = TerminationOrigin()
    inner_started = asyncio.Event()
    observations = []

    async def inner():
        inner_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            observations.append(("inner-cancelled", origin.value))
            raise

    async def on_timeout(task_id: str, timeout_seconds: int):
        observations.append(("timeout-callback", origin.value, task_id, timeout_seconds))

    task = create_tracked_task(
        inner(),
        "timeout-order",
        timeout_seconds=0,
        on_timeout=on_timeout,
        termination_origin=origin,
    )

    assert await task is None
    assert inner_started.is_set()
    assert observations == [
        ("inner-cancelled", "timeout"),
        ("timeout-callback", "timeout", "timeout-order", 0),
    ]
    assert origin.value == "timeout"
    assert get_active_task("timeout-order") is None


@pytest.mark.asyncio
async def test_external_cancel_waits_for_inner_cleanup_calls_cancel_once_and_reraises():
    from api.task_tracker import (
        TerminationOrigin,
        clear_active_tasks,
        create_tracked_task,
        get_active_task,
    )

    clear_active_tasks()
    origin = TerminationOrigin()
    inner_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    cleanup_finished = asyncio.Event()
    cancel_calls = []

    async def inner():
        inner_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await cleanup_release.wait()
            cleanup_finished.set()

    async def on_cancel(task_id: str):
        cancel_calls.append((task_id, cleanup_finished.is_set()))

    task = create_tracked_task(
        inner(),
        "external-cancel",
        on_cancel=on_cancel,
        termination_origin=origin,
    )
    await inner_started.wait()

    task.cancel()
    await cleanup_started.wait()
    assert cancel_calls == []

    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cleanup_finished.is_set()
    assert cancel_calls == [("external-cancel", True)]
    assert origin.value == "cancelled"
    assert get_active_task("external-cancel") is None


@pytest.mark.asyncio
async def test_inner_self_cancel_does_not_claim_application_cancel():
    from api.task_tracker import (
        TerminationOrigin,
        clear_active_tasks,
        create_tracked_task,
        get_active_task,
    )

    clear_active_tasks()
    origin = TerminationOrigin()
    calls = []

    async def self_cancel():
        raise asyncio.CancelledError

    task = create_tracked_task(
        self_cancel(),
        "self-cancel",
        timeout_seconds=100,
        on_timeout=lambda *_: calls.append("timeout"),
        on_cancel=lambda *_: calls.append("cancelled"),
        termination_origin=origin,
    )

    with pytest.raises(asyncio.CancelledError):
        await task

    assert origin.value == "unset"
    assert calls == []
    assert get_active_task("self-cancel") is None


@pytest.mark.asyncio
async def test_timeout_and_external_cancel_race_has_one_matching_origin_callback():
    from api.task_tracker import TerminationOrigin, create_tracked_task

    origin = TerminationOrigin()
    inner_started = asyncio.Event()
    calls = []

    async def inner():
        inner_started.set()
        await asyncio.Event().wait()

    task = create_tracked_task(
        inner(),
        "timeout-cancel-race",
        timeout_seconds=0,
        on_timeout=lambda *_: calls.append("timeout"),
        on_cancel=lambda *_: calls.append("cancelled"),
        termination_origin=origin,
    )
    await inner_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert origin.value in {"timeout", "cancelled"}
    assert calls == [origin.value]


@pytest.mark.asyncio
async def test_inner_completion_wins_same_turn_deadline_tie_without_outer_cancel():
    from api.task_tracker import TerminationOrigin, create_tracked_task

    origin = TerminationOrigin()
    calls = []

    async def complete_without_suspending():
        return "inner-result"

    task = create_tracked_task(
        complete_without_suspending(),
        "inner-deadline-tie",
        timeout_seconds=0,
        on_timeout=lambda *_: calls.append("timeout"),
        on_cancel=lambda *_: calls.append("cancelled"),
        termination_origin=origin,
    )

    assert await task == "inner-result"
    assert origin.value == "unset"
    assert calls == []


@pytest.mark.asyncio
async def test_target_self_cancel_and_outer_cancel_same_turn_preserve_outer_cancel():
    from api.task_tracker import TerminationOrigin, create_tracked_task

    origin = TerminationOrigin()
    inner_started = asyncio.Event()
    self_cancel = asyncio.Event()
    calls = []

    async def inner():
        inner_started.set()
        await self_cancel.wait()
        raise asyncio.CancelledError

    task = create_tracked_task(
        inner(),
        "same-turn-self-outer-cancel",
        timeout_seconds=100,
        on_cancel=lambda task_id: calls.append(task_id),
        termination_origin=origin,
    )
    await inner_started.wait()

    self_cancel.set()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert origin.value == "cancelled"
    assert calls == ["same-turn-self-outer-cancel"]


@pytest.mark.asyncio
async def test_expired_checkpoint_claims_timeout_when_deadline_task_was_not_scheduled(
    monkeypatch,
):
    from api.task_tracker import (
        FinalizationCheckpoint,
        TerminationOrigin,
        create_tracked_task,
    )

    loop = asyncio.get_running_loop()
    clock = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: clock[0])

    checkpoint = FinalizationCheckpoint()
    origin = TerminationOrigin()
    observed = []

    async def inner():
        clock[0] += 20
        try:
            await checkpoint.request_and_wait()
        except asyncio.CancelledError:
            observed.append(("inner-cancelled", origin.value))
            raise

    task = create_tracked_task(
        inner(),
        "expired-checkpoint",
        timeout_seconds=10,
        on_timeout=lambda *_: observed.append(("timeout-callback", origin.value)),
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await task is None
    assert observed == [
        ("inner-cancelled", "timeout"),
        ("timeout-callback", "timeout"),
    ]
    assert origin.value == "timeout"


@pytest.mark.asyncio
async def test_live_checkpoint_is_released_exactly_once():
    from api.task_tracker import FinalizationCheckpoint, TerminationOrigin, create_tracked_task

    class CountingCheckpoint(FinalizationCheckpoint):
        def __init__(self):
            super().__init__()
            self.release_count = 0

        def release(self):
            self.release_count += 1
            super().release()

    checkpoint = CountingCheckpoint()
    origin = TerminationOrigin()

    async def inner():
        await checkpoint.request_and_wait()
        return "finalized"

    task = create_tracked_task(
        inner(),
        "live-checkpoint",
        timeout_seconds=100,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )

    assert await task == "finalized"
    assert checkpoint.release_count == 1
    assert origin.value == "unset"


@pytest.mark.asyncio
async def test_second_outer_cancel_during_cancel_callback_waits_for_settlement():
    from api.task_tracker import TerminationOrigin, create_tracked_task

    origin = TerminationOrigin()
    inner_started = asyncio.Event()
    callback_started = asyncio.Event()
    callback_advance = asyncio.Event()
    callback_advanced = asyncio.Event()
    callback_release = asyncio.Event()
    calls = []

    async def inner():
        inner_started.set()
        await asyncio.Event().wait()

    async def on_cancel(task_id: str):
        calls.append(task_id)
        callback_started.set()
        await callback_advance.wait()
        callback_advanced.set()
        await callback_release.wait()

    task = create_tracked_task(
        inner(),
        "double-cancel",
        on_cancel=on_cancel,
        termination_origin=origin,
    )
    await inner_started.wait()

    task.cancel()
    await callback_started.wait()
    task.cancel()
    callback_advance.set()
    await callback_advanced.wait()

    assert task.done() is False
    assert calls == ["double-cancel"]
    assert origin.value == "cancelled"

    callback_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_outer_cancel_during_timeout_callback_preserves_timeout_and_settles():
    from api.task_tracker import TerminationOrigin, create_tracked_task

    origin = TerminationOrigin()
    callback_started = asyncio.Event()
    callback_release = asyncio.Event()
    calls = []

    async def inner():
        await asyncio.Event().wait()

    async def on_timeout(task_id: str, timeout_seconds: int):
        calls.append(("timeout", task_id, timeout_seconds))
        callback_started.set()
        await callback_release.wait()

    task = create_tracked_task(
        inner(),
        "cancel-during-timeout-callback",
        timeout_seconds=0,
        on_timeout=on_timeout,
        on_cancel=lambda *_: calls.append(("cancelled",)),
        termination_origin=origin,
    )
    await callback_started.wait()

    task.cancel()
    assert task.done() is False
    callback_release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert origin.value == "timeout"
    assert calls == [("timeout", "cancel-during-timeout-callback", 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_kind", ["sync", "async", "sync-raising"])
async def test_callback_shapes_share_task_settlement_boundary(callback_kind, caplog):
    from api.task_tracker import create_tracked_task

    calls = []
    callback_tasks = []

    if callback_kind == "async":

        async def callback(task_id: str, timeout_seconds: int):
            calls.append((task_id, timeout_seconds))
            callback_tasks.append(asyncio.current_task())

    elif callback_kind == "sync-raising":

        def callback(task_id: str, timeout_seconds: int):
            calls.append((task_id, timeout_seconds))
            callback_tasks.append(asyncio.current_task())
            raise ValueError("callback failed")

    else:

        def callback(task_id: str, timeout_seconds: int):
            calls.append((task_id, timeout_seconds))
            callback_tasks.append(asyncio.current_task())

    async def inner():
        await asyncio.Event().wait()

    with caplog.at_level(logging.ERROR, logger="api.task_tracker"):
        task = create_tracked_task(
            inner(),
            f"callback-{callback_kind}",
            timeout_seconds=0,
            on_timeout=callback,
        )
        assert await task is None

    assert calls == [(f"callback-{callback_kind}", 0)]
    assert len(callback_tasks) == 1
    assert callback_tasks[0] is not task
    assert callback_tasks[0].done()
    if callback_kind == "sync-raising":
        assert "Task termination callback failed" in caplog.text
        assert "callback failed" in caplog.text
    else:
        assert "Task termination callback failed" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_path", ["normal", "timeout", "cancel", "self-cancel"])
async def test_control_tasks_settle_on_every_terminal_path(terminal_path, monkeypatch):
    import api.task_tracker as task_tracker

    task_tracker.clear_active_tasks()
    deadline_fire = asyncio.Event()
    deadline_settled = asyncio.Event()
    checkpoint_waiter_settled = asyncio.Event()
    inner_started = asyncio.Event()
    inner_finish = asyncio.Event()
    control_tasks = {}

    async def controlled_deadline(_delay):
        control_tasks["deadline"] = asyncio.current_task()
        try:
            await deadline_fire.wait()
        finally:
            deadline_settled.set()

    monkeypatch.setattr(task_tracker.asyncio, "sleep", controlled_deadline)

    class ObservableCheckpoint(task_tracker.FinalizationCheckpoint):
        async def wait_requested(self):
            control_tasks["checkpoint"] = asyncio.current_task()
            try:
                await super().wait_requested()
            finally:
                checkpoint_waiter_settled.set()

    checkpoint = ObservableCheckpoint()

    async def inner():
        inner_started.set()
        await inner_finish.wait()
        if terminal_path == "self-cancel":
            raise asyncio.CancelledError
        return "done"

    task_id = f"controls-{terminal_path}"
    task = task_tracker.create_tracked_task(
        inner(),
        task_id,
        timeout_seconds=100,
        finalization_checkpoint=checkpoint,
    )
    await inner_started.wait()

    if terminal_path == "normal":
        inner_finish.set()
        assert await task == "done"
    elif terminal_path == "timeout":
        deadline_fire.set()
        assert await task is None
    elif terminal_path == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        inner_finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert deadline_settled.is_set()
    assert checkpoint_waiter_settled.is_set()
    assert set(control_tasks) == {"deadline", "checkpoint"}
    assert all(control_task.done() for control_task in control_tasks.values())
    assert all(
        control_task not in asyncio.all_tasks()
        for control_task in control_tasks.values()
    )
    assert task_tracker.get_active_task(task_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("inner_outcome", ["result", "self-cancel", "exception"])
async def test_first_outer_cancel_during_control_cleanup_claims_and_calls_cancel(
    inner_outcome,
    monkeypatch,
):
    import api.task_tracker as task_tracker

    task_tracker.clear_active_tasks()
    inner_started = asyncio.Event()
    inner_finish = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    cleanup_finished = asyncio.Event()
    origin = task_tracker.TerminationOrigin()
    cancel_calls = []

    async def controlled_deadline(_delay):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup_started.set()
            await cleanup_release.wait()
            cleanup_finished.set()
            raise

    monkeypatch.setattr(task_tracker.asyncio, "sleep", controlled_deadline)

    async def inner():
        inner_started.set()
        await inner_finish.wait()
        if inner_outcome == "self-cancel":
            raise asyncio.CancelledError
        if inner_outcome == "exception":
            raise ValueError("inner failed")
        return "done"

    async def on_cancel(task_id: str):
        cancel_calls.append((task_id, cleanup_finished.is_set()))

    task_id = f"cleanup-cancel-{inner_outcome}"
    task = task_tracker.create_tracked_task(
        inner(),
        task_id,
        timeout_seconds=100,
        on_cancel=on_cancel,
        termination_origin=origin,
    )
    await inner_started.wait()
    inner_finish.set()
    await cleanup_started.wait()

    task.cancel()
    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cleanup_finished.is_set()
    assert (origin.value, cancel_calls) == (
        "cancelled",
        [(task_id, True)],
    )
    assert task_tracker.get_active_task(task_id) is None


@pytest.mark.asyncio
async def test_outer_cancel_during_timeout_control_cleanup_does_not_call_cancel(
    monkeypatch,
):
    import api.task_tracker as task_tracker

    task_tracker.clear_active_tasks()
    checkpoint_cleanup_started = asyncio.Event()
    checkpoint_cleanup_release = asyncio.Event()
    checkpoint_cleanup_finished = asyncio.Event()
    origin = task_tracker.TerminationOrigin()
    calls = []

    class BlockingCheckpoint(task_tracker.FinalizationCheckpoint):
        async def wait_requested(self):
            try:
                await super().wait_requested()
            except asyncio.CancelledError:
                checkpoint_cleanup_started.set()
                await checkpoint_cleanup_release.wait()
                checkpoint_cleanup_finished.set()
                raise

    async def inner():
        await asyncio.Event().wait()

    task = task_tracker.create_tracked_task(
        inner(),
        "timeout-cleanup-cancel",
        timeout_seconds=0,
        on_timeout=lambda *_: calls.append("timeout"),
        on_cancel=lambda *_: calls.append("cancelled"),
        termination_origin=origin,
        finalization_checkpoint=BlockingCheckpoint(),
    )
    await checkpoint_cleanup_started.wait()

    assert origin.value == "timeout"
    assert calls == ["timeout"]
    task.cancel()
    checkpoint_cleanup_release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert checkpoint_cleanup_finished.is_set()
    assert origin.value == "timeout"
    assert calls == ["timeout"]


@pytest.mark.asyncio
async def test_timeout_callback_observes_outcome_published_during_inner_cleanup(tmp_path):
    from agent.run_result import AgentRunAccumulator, OutcomeBox
    from api.task_tracker import clear_active_tasks, create_tracked_task

    clear_active_tasks()
    box = OutcomeBox()
    observed = []
    accumulator = AgentRunAccumulator(
        thread_id="timeout-closure",
        query="query",
        session_dir=tmp_path,
    )

    async def inner():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            box.publish(
                accumulator.to_outcome(
                    failure_kind="cancelled",
                    cancellation_state="cancelled",
                )
            )
            raise

    async def on_timeout(task_id: str, timeout_seconds: int):
        observed.append(box.latest())

    task = create_tracked_task(
        inner(),
        "timeout-closure",
        timeout_seconds=0,
        on_timeout=on_timeout,
    )

    assert await task is None
    assert observed[0].failure_kind == "cancelled"
    assert observed[0].cancellation_state == "cancelled"


def test_default_timeout_from_env():
    from api import task_tracker

    old_value = os.environ.get("AGENT_TASK_TIMEOUT_SECONDS")
    try:
        os.environ["AGENT_TASK_TIMEOUT_SECONDS"] = "600"
        importlib.reload(task_tracker)
        assert task_tracker.DEFAULT_TASK_TIMEOUT == 600
    finally:
        if old_value is None:
            os.environ.pop("AGENT_TASK_TIMEOUT_SECONDS", None)
        else:
            os.environ["AGENT_TASK_TIMEOUT_SECONDS"] = old_value
        importlib.reload(task_tracker)
