"""Retry decorator and timeout configuration for external service calls.

Provides:
- @retry: Async decorator with exponential backoff for retrying failed calls
- retry_async(): Standalone async retry function
- TIMEOUTS: Centralized timeout configuration dictionary
"""
import asyncio
import functools
from typing import Callable, Optional, Tuple, Type

from api.monitor import monitor

# Centralized timeout configuration (in seconds)
TIMEOUTS = {
    "tavily": 15,          # HTTP search, typically 1-3s
    "ragflow": 60,         # Streaming Q&A, may need longer
    "mysql_connect": 10,   # Database connection
    "mysql_query": 30,     # SQL query
    "llm": 120,            # DeepSeek generation
    "pdf_convert": 60,     # weasyprint / word conversion
}

# Default retryable exceptions
_DEFAULT_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)


def retry_async(
    coro_factory: Callable,
    *args,
    max_retries: int = 3,
    backoff_factor: float = 2,
    max_wait: float = 30,
    retryable_exceptions: Tuple[Type[Exception], ...] = _DEFAULT_RETRYABLE_EXCEPTIONS,
    service_name: str = "unknown",
    **kwargs,
):
    """Standalone async retry function with exponential backoff.

    Args:
        coro_factory: Async callable to retry (can be a coroutine function or
            a callable that returns a coroutine when invoked with args/kwargs).
        *args: Positional arguments passed to coro_factory.
        max_retries: Maximum number of retry attempts (default 3).
        backoff_factor: Multiplier for exponential backoff (default 2).
        max_wait: Maximum seconds to wait between retries (default 30).
        retryable_exceptions: Tuple of exception types that should trigger retry.
        service_name: Human-readable service name for monitor logging.
        **kwargs: Keyword arguments passed to coro_factory.

    Returns:
        The result of the first successful call.

    Raises:
        The last exception if all retries are exhausted.
        Non-retryable exceptions are raised immediately.
    """
    if not asyncio.iscoroutinefunction(coro_factory):
        raise ValueError(
            "retry_async requires an async function, not a pre-created coroutine object. "
            "Pass the function itself, not the result of calling it."
        )
    async def _inner():
        last_exception = None

        # Initial attempt (attempt 0)
        try:
            return await coro_factory(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
        except Exception:
            raise

        # Retry loop (max_retries - 1 more attempts after initial = max_retries total)
        for attempt in range(max_retries - 1):
            wait_time = min((2 ** attempt) * backoff_factor, max_wait)
            monitor.report_retry(
                service_name,
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(last_exception) if last_exception else "",
            )
            await asyncio.sleep(wait_time)

            try:
                return await coro_factory(*args, **kwargs)
            except retryable_exceptions as e:
                last_exception = e
            except Exception:
                raise

        raise last_exception

    return _inner()


def retry(
    max_retries: int = 3,
    backoff_factor: float = 2,
    max_wait: float = 30,
    retryable_exceptions: Tuple[Type[Exception], ...] = _DEFAULT_RETRYABLE_EXCEPTIONS,
    service_name: str = "unknown",
):
    """Async decorator with exponential backoff retry.

    Usage:
        @retry(max_retries=3, backoff_factor=2, max_wait=30, service_name="tavily")
        async def search(query: str) -> dict:
            ...

    Args:
        max_retries: Maximum number of retry attempts (default 3).
        backoff_factor: Multiplier for exponential backoff (default 2).
        max_wait: Maximum seconds to wait between retries (default 30).
        retryable_exceptions: Tuple of exception types that should trigger retry.
        service_name: Human-readable service name for monitor logging.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                max_wait=max_wait,
                retryable_exceptions=retryable_exceptions,
                service_name=service_name,
                *args,
                **kwargs,
            )
        return wrapper
    return decorator
