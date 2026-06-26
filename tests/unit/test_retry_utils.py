"""Phase 7b Task 1: Retry decorator and TIMEOUTS config tests."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

from tools.retry_utils import retry, retry_async, TIMEOUTS


@pytest.fixture
def _reset_monitor():
    """Patch monitor at the usage site so each test gets an isolated mock."""
    with patch("tools.retry_utils.monitor") as mock_monitor:
        yield mock_monitor


# ============================================================
# TIMEOUTS Config Tests
# ============================================================

class TestTimeoutsConfig:
    """Test the TIMEOUTS configuration dictionary."""

    def test_has_all_required_keys(self):
        """TIMEOUTS should contain all expected service keys."""
        required_keys = {"tavily", "ragflow", "mysql_connect", "mysql_query", "llm"}
        assert required_keys.issubset(TIMEOUTS.keys())

    def test_tavily_timeout(self):
        assert TIMEOUTS["tavily"] == 15

    def test_ragflow_timeout(self):
        assert TIMEOUTS["ragflow"] == 60

    def test_mysql_connect_timeout(self):
        assert TIMEOUTS["mysql_connect"] == 10

    def test_mysql_query_timeout(self):
        assert TIMEOUTS["mysql_query"] == 30

    def test_llm_timeout(self):
        assert TIMEOUTS["llm"] == 120

    def test_all_values_positive(self):
        """All timeout values should be positive integers."""
        for key, value in TIMEOUTS.items():
            assert isinstance(value, (int, float)), f"{key} should be numeric"
            assert value > 0, f"{key} should be positive"


# ============================================================
# Retry Decorator Tests
# ============================================================

class TestRetryDecorator:
    """Test the @retry async decorator."""

    @pytest.mark.asyncio
    async def test_first_attempt_success(self, _reset_monitor):
        """Successful on first call — no retries needed."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(max_retries=3, service_name="test_svc")
        async def successful_fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await successful_fn()
        assert result == "ok"
        assert call_count == 1
        # No retries needed — monitor should record 0 retry events
        assert mock_monitor.report_retry.call_count == 0

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, _reset_monitor):
        """TimeoutError should trigger retry, then succeed."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(max_retries=3, backoff_factor=0.001, max_wait=0.01, service_name="test_svc")
        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("connection timeout")
            return "recovered"

        result = await flaky_fn()
        assert result == "recovered"
        assert call_count == 2
        # 1 retry event recorded (attempt 1/3)
        assert mock_monitor.report_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, _reset_monitor):
        """After max_retries failures, the last exception should be raised."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(max_retries=3, backoff_factor=0.001, max_wait=0.01, service_name="test_svc")
        async def always_failing():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("always fails")

        with pytest.raises(TimeoutError, match="always fails"):
            await always_failing()

        # 1 initial + 2 retries = 3 total calls (max_retries=3 means 3 total)
        assert call_count == 3
        # Monitor should record max_retries - 1 = 2 retry events
        assert mock_monitor.report_retry.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self, _reset_monitor):
        """Non-retryable exceptions should not trigger any retry."""
        call_count = 0

        @retry(max_retries=3, service_name="test_svc")
        async def bad_fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await bad_fn()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_custom_retry_parameters(self, _reset_monitor):
        """Custom max_retries, backoff_factor, max_wait should be respected."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(max_retries=5, backoff_factor=0.001, max_wait=0.005, service_name="test_svc")
        async def custom_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise TimeoutError("transient")
            return "done"

        result = await custom_fn()
        assert result == "done"
        assert call_count == 5
        # 4 retry events recorded (5 total calls - 1 initial = 4 retries = max_retries - 1)
        assert mock_monitor.report_retry.call_count == 4

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self, _reset_monitor):
        """Only specified exceptions should be retried."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(
            max_retries=3,
            backoff_factor=0.001,
            max_wait=0.01,
            retryable_exceptions=(ConnectionError,),
            service_name="test_svc",
        )
        async def connection_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("reset")
            return "connected"

        result = await connection_fn()
        assert result == "connected"
        assert call_count == 2
        # 1 retry event recorded
        assert mock_monitor.report_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_1_no_retries(self, _reset_monitor):
        """max_retries=1 means exactly 1 attempt, 0 retries — failure propagates immediately."""
        mock_monitor = _reset_monitor
        call_count = 0

        @retry(max_retries=1, service_name="test_svc")
        async def failing_fn():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("one shot")

        with pytest.raises(TimeoutError, match="one shot"):
            await failing_fn()

        assert call_count == 1
        assert mock_monitor.report_retry.call_count == 0

    @pytest.mark.asyncio
    async def test_unlisted_exception_not_retried(self, _reset_monitor):
        """Exception not in retryable_exceptions should not be retried."""
        call_count = 0

        @retry(
            max_retries=3,
            backoff_factor=0.001,
            max_wait=0.01,
            retryable_exceptions=(ConnectionError,),
            service_name="test_svc",
        )
        async def timeout_fn():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("not in list")

        with pytest.raises(TimeoutError):
            await timeout_fn()

        assert call_count == 1


# ============================================================
# retry_async Standalone Function Tests
# ============================================================

class TestRetryAsyncFunction:
    """Test the retry_async() standalone function."""

    @pytest.mark.asyncio
    async def test_first_try_success(self, _reset_monitor):
        """First attempt succeeds — no retries."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def success_fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(success_fn, max_retries=3, backoff_factor=0.001, max_wait=0.01)
        assert result == "ok"
        assert call_count == 1
        assert mock_monitor.report_retry.call_count == 0

    @pytest.mark.asyncio
    async def test_retries_succeed(self, _reset_monitor):
        """Retries eventually succeed."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("transient")
            return "recovered"

        result = await retry_async(flaky_fn, max_retries=3, backoff_factor=0.001, max_wait=0.01)
        assert result == "recovered"
        assert call_count == 3
        # 2 retry events recorded (max_retries=3, 2 retries)
        assert mock_monitor.report_retry.call_count == 2

    @pytest.mark.asyncio
    async def test_custom_exceptions(self, _reset_monitor):
        """Should only retry on specified exceptions."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def custom_exc_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("io error")
            return "ok"

        result = await retry_async(
            custom_exc_fn,
            max_retries=3,
            backoff_factor=0.001,
            max_wait=0.01,
            retryable_exceptions=(OSError,),
        )
        assert result == "ok"
        assert call_count == 2
        assert mock_monitor.report_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_rejects_pre_created_coroutine(self, _reset_monitor):
        """Passing a pre-created coroutine object (not a function) should raise ValueError."""
        async def some_fn():
            return "result"

        coro = some_fn()  # Pre-created coroutine, not a function
        with pytest.raises(ValueError, match="requires an async function"):
            await retry_async(coro, max_retries=3)

        # Clean up the unawaited coroutine to avoid RuntimeWarning
        coro.close()

    @pytest.mark.asyncio
    async def test_max_retries_1_no_retries_standalone(self, _reset_monitor):
        """max_retries=1 means exactly 1 attempt, 0 retries."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def failing_fn():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("one shot")

        with pytest.raises(TimeoutError, match="one shot"):
            await retry_async(failing_fn, max_retries=1, backoff_factor=0.001, max_wait=0.01)

        assert call_count == 1
        assert mock_monitor.report_retry.call_count == 0


# ============================================================
# retry_async + asyncio.wait_for Combo Tests
# ============================================================

class TestRetryWithAsyncioWaitFor:
    """Test retry_async combined with asyncio.wait_for for timeout enforcement.

    Correct pattern: each individual attempt is wrapped in wait_for,
    and retry_async wraps that. NOT wait_for(retry_async(...)) which
    cancels the entire retry loop on the first timeout.
    """

    @pytest.mark.asyncio
    async def test_wait_for_each_attempt(self, _reset_monitor):
        """Each attempt wrapped in wait_for — timeout triggers retry."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def slow_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                await asyncio.sleep(10)  # Will be killed by wait_for
            return "done"

        # Correct pattern: wrap each attempt in wait_for, then retry
        async def attempt_with_timeout():
            return await asyncio.wait_for(slow_fn(), timeout=0.05)

        result = await retry_async(
            attempt_with_timeout,
            max_retries=5,
            backoff_factor=0.001,
            max_wait=0.01,
        )
        assert result == "done"
        assert call_count == 3
        # 2 retry events (3rd call succeeds, so 2 retries)
        assert mock_monitor.report_retry.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_for_all_attempts_timeout(self, _reset_monitor):
        """If all attempts also timeout, TimeoutError should propagate."""
        mock_monitor = _reset_monitor
        call_count = 0

        async def always_slow():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)  # Always too slow

        async def attempt_with_timeout():
            return await asyncio.wait_for(always_slow(), timeout=0.05)

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await retry_async(
                attempt_with_timeout,
                max_retries=2,
                backoff_factor=0.001,
                max_wait=0.01,
            )

        # Should have attempted initial + 1 retry = 2 total (max_retries=2 means 2 total)
        assert call_count == 2
        # 1 retry event recorded
        assert mock_monitor.report_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_fast_function_not_affected_by_wait_for(self, _reset_monitor):
        """Fast function should complete within wait_for timeout."""
        async def fast_fn():
            return "instant"

        result = await asyncio.wait_for(
            retry_async(fast_fn, max_retries=3),
            timeout=5.0,
        )
        assert result == "instant"
