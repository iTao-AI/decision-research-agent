"""Integration tests for ContextVar isolation.

Verifies that concurrent run_deep_agent calls maintain strict session isolation.
This is the critical test for multi-request safety in the async event loop.
"""
import asyncio
import tempfile
import shutil
import pytest

from api.context import (
    _session_dir_ctx,
    _thread_id_ctx,
    set_session_context,
    get_session_context,
    set_thread_context,
    get_thread_context,
    reset_session_context,
)


class TestContextVarIsolation:
    """ContextVar isolation under concurrent execution."""

    def test_concurrent_sessions_do_not_cross_contaminate(self):
        """Two async tasks setting different session dirs never read each other's."""
        results = {}
        errors = []

        dir_a = tempfile.mkdtemp(prefix="ctx_iso_a_")
        dir_b = tempfile.mkdtemp(prefix="ctx_iso_b_")

        async def task_a():
            """Simulates run_deep_agent's context setup/teardown for session A."""
            token = set_session_context(dir_a)
            thread_tok = set_thread_context("thread-a")
            try:
                # Simulate work: read context
                await asyncio.sleep(0.01)  # yield control
                ctx = get_session_context()
                if ctx != dir_a:
                    errors.append(f"Task A saw wrong session: {ctx} (expected {dir_a})")
                results["a"] = ctx
            finally:
                reset_session_context(token, thread_tok)

        async def task_b():
            """Simulates run_deep_agent's context setup/teardown for session B."""
            token = set_session_context(dir_b)
            thread_tok = set_thread_context("thread-b")
            try:
                await asyncio.sleep(0.01)  # yield control
                ctx = get_session_context()
                if ctx != dir_b:
                    errors.append(f"Task B saw wrong session: {ctx} (expected {dir_b})")
                results["b"] = ctx
            finally:
                reset_session_context(token, thread_tok)

        async def main():
            await asyncio.gather(task_a(), task_b())

        asyncio.run(main())

        assert not errors, f"Cross-contamination detected: {errors}"
        assert results["a"] == dir_a
        assert results["b"] == dir_b

        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)

    def test_context_cleanup_restores_previous_state(self):
        """After reset_session_context, the previous context is restored."""
        outer_dir = tempfile.mkdtemp(prefix="ctx_outer_")
        inner_dir = tempfile.mkdtemp(prefix="ctx_inner_")

        outer_token = set_session_context(outer_dir)
        assert get_session_context() == outer_dir

        inner_token = set_session_context(inner_dir)
        assert get_session_context() == inner_dir

        reset_session_context(inner_token)
        assert get_session_context() == outer_dir

        reset_session_context(outer_token)
        assert get_session_context() is None

        shutil.rmtree(outer_dir, ignore_errors=True)
        shutil.rmtree(inner_dir, ignore_errors=True)

    def test_rapid_context_switches_no_leak(self):
        """Rapid context switches don't leak state between operations."""
        dirs = [tempfile.mkdtemp(prefix=f"ctx_rapid_{i}_") for i in range(5)]
        seen = []

        for d in dirs:
            token = set_session_context(d)
            ctx = get_session_context()
            seen.append(ctx)
            reset_session_context(token)

        # Every read should have returned its own dir
        assert seen == dirs

        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_context_reset_restores_default_none(self):
        """After setting and resetting context, value returns to None (the default)."""
        # This test verifies the default state
        token = set_session_context("test-default")
        reset_session_context(token)
        assert get_session_context() is None


class TestContextVarThreadIsolation:
    """Thread ID context isolation."""

    def test_thread_id_isolation(self):
        """Thread ID context is isolated between tasks."""
        results = {}

        async def task_a():
            tok = set_thread_context("thread-a")
            try:
                await asyncio.sleep(0.01)
                results["a"] = get_thread_context()
            finally:
                _thread_id_ctx.reset(tok)

        async def task_b():
            tok = set_thread_context("thread-b")
            try:
                await asyncio.sleep(0.01)
                results["b"] = get_thread_context()
            finally:
                _thread_id_ctx.reset(tok)

        async def main():
            await asyncio.gather(task_a(), task_b())

        asyncio.run(main())

        assert results["a"] == "thread-a"
        assert results["b"] == "thread-b"

    def test_thread_context_cleanup(self):
        """Thread context is properly cleaned up after reset."""
        token = set_thread_context("cleanup-test")
        assert get_thread_context() == "cleanup-test"
        _thread_id_ctx.reset(token)
        assert get_thread_context() is None
