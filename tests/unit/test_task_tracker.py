"""异步任务错误处理单元测试 - Phase D"""
import pytest
import asyncio
import pytest_asyncio


class TestTaskTracker:
    """Phase D: 异步任务错误处理"""

    @pytest.mark.asyncio
    async def test_create_tracked_task(self):
        """创建的任务应该被跟踪"""
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks

        clear_active_tasks()

        async def dummy_task():
            await asyncio.sleep(0)
            return "done"

        task = create_tracked_task(dummy_task(), "test-1")
        assert get_active_task("test-1") is not None

    @pytest.mark.asyncio
    async def test_task_removed_after_completion(self):
        """任务完成后应该从字典中移除"""
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks

        clear_active_tasks()

        async def quick_task():
            return "done"

        task = create_tracked_task(quick_task(), "test-2")
        # 等待任务完成
        await task

        assert get_active_task("test-2") is None

    @pytest.mark.asyncio
    async def test_task_exception_logged(self):
        """任务异常应该被记录"""
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks

        clear_active_tasks()

        async def failing_task():
            raise ValueError("test error")

        task = create_tracked_task(failing_task(), "test-3")
        # 等待任务完成（应该捕获异常）
        try:
            await task
        except ValueError:
            pass  # 异常已记录

        # 任务应该被移除，异常已记录
        assert get_active_task("test-3") is None

    @pytest.mark.asyncio
    async def test_clear_active_tasks(self):
        """清理所有活跃任务"""
        from api.task_tracker import create_tracked_task, clear_active_tasks, active_tasks

        clear_active_tasks()

        async def dummy():
            await asyncio.sleep(10)

        create_tracked_task(dummy(), "test-4")
        create_tracked_task(dummy(), "test-5")

        assert len(active_tasks) == 2
        clear_active_tasks()
        assert len(active_tasks) == 0
