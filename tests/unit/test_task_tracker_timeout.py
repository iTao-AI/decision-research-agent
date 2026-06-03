"""任务超时管理单元测试 — Phase 7b"""
import asyncio
import os
import sys

import pytest


class TestTaskTrackerTimeout:
    """测试任务超时功能"""

    @pytest.mark.asyncio
    async def test_task_tracked_with_timeout(self):
        """创建的任务应被跟踪，完成后自动移除"""
        from api.task_tracker import (
            clear_active_tasks,
            create_tracked_task,
            get_active_task,
        )

        clear_active_tasks()

        async def dummy():
            await asyncio.sleep(0.1)
            return "done"

        task = create_tracked_task(dummy(), "timeout-test-1", timeout_seconds=1800)
        assert get_active_task("timeout-test-1") is not None

        await asyncio.sleep(0.2)
        assert get_active_task("timeout-test-1") is None

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

    @pytest.mark.asyncio
    async def test_default_timeout_from_env(self):
        """默认超时应从环境变量读取"""
        # 清除已缓存的模块
        sys.modules.pop("api.task_tracker", None)
        sys.modules.pop("api", None)

        old_val = os.environ.get("AGENT_TASK_TIMEOUT_SECONDS")
        os.environ["AGENT_TASK_TIMEOUT_SECONDS"] = "600"

        from api import task_tracker
        import importlib

        importlib.reload(task_tracker)

        assert task_tracker.DEFAULT_TASK_TIMEOUT == 600

        if old_val is None:
            os.environ.pop("AGENT_TASK_TIMEOUT_SECONDS", None)
        else:
            os.environ["AGENT_TASK_TIMEOUT_SECONDS"] = old_val
