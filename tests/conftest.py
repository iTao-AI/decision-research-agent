"""Shared fixtures for all tests (unit + integration)."""
import sys

# Stub heavy imports before any test module imports them.
# This prevents LLM initialization during test collection.


class _MockMainAgent:
    """Mock module for agent.main_agent with async-compatible run_deep_agent."""
    @staticmethod
    async def run_deep_agent(*args, **kwargs):
        return "Done"


sys.modules.setdefault("agent.main_agent", _MockMainAgent())

import pytest

from api.context import (
    set_session_context,
    set_thread_context,
    reset_session_context,
)
from agent.telemetry import collector


@pytest.fixture
def session_dir():
    """Create a temporary session directory, set context, and clean up."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="test_session_") as tmpdir:
        session_token = set_session_context(tmpdir)
        try:
            yield tmpdir
        finally:
            reset_session_context(session_token)


@pytest.fixture
def clean_collector():
    """Ensure telemetry collector is clean before and after tests."""
    test_threads = [
        "test-thread-1",
        "test-thread-2",
        "test-thread-integration",
        "nonexistent-thread",
    ]
    for tid in test_threads:
        collector.clear_thread(tid)
    yield collector
    for tid in test_threads:
        collector.clear_thread(tid)
