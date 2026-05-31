"""TTL-based in-memory cache with decorator support for tool functions."""
import functools
import hashlib
import json
import time
import asyncio


class TTLCache:
    """Thread-safe in-memory cache with TTL-based expiration."""

    def __init__(self, max_size: int = 1000):
        self._store: dict[str, tuple[object, float]] = {}  # key -> (value, expiry)
        self._max_size = max_size

    def set(self, key: str, value: object, ttl: float = 300) -> None:
        """Store value with TTL in seconds."""
        self._store[key] = (value, time.time() + ttl)

        # Evict oldest expired entry first, then oldest if still over capacity
        if len(self._store) > self._max_size:
            self._evict_oldest()

    def _evict_oldest(self) -> None:
        """Remove the oldest (earliest expiry) entry."""
        if not self._store:
            return
        oldest_key = min(self._store.keys(), key=lambda k: self._store[k][1])
        del self._store[oldest_key]

    def get(self, key: str) -> object | None:
        """Get value if not expired, return None otherwise."""
        if key not in self._store:
            return None

        value, expiry = self._store[key]
        if time.time() > expiry:
            del self._store[key]
            return None

        return value

    def size(self) -> int:
        """Return count of non-expired entries, cleaning up expired ones."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(self._store)

    def clear(self) -> None:
        """Clear all entries."""
        self._store.clear()


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate SHA256 cache key from function name and arguments."""
    key_input = json.dumps({
        "func": func_name,
        "args": args,
        "kwargs": kwargs,
    }, sort_keys=True, default=str)
    return hashlib.sha256(key_input.encode()).hexdigest()


def cached_tool(ttl: float = 300, tool_name: str = "unknown", cache: TTLCache = None):
    """Decorator that caches function results with TTL.

    Supports both sync and async functions.
    On cache miss, executes the function and stores result.
    On cache hit, returns cached value without execution and reports to monitor.
    """
    _cache = cache or TTLCache()

    def decorator(func):
        cache_key_base = _make_cache_key(func.__name__, (), {})

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            from api.monitor import monitor
            key = _make_cache_key(func.__name__, args, kwargs)
            result = _cache.get(key)
            if result is not None:
                monitor.report_cache_hit(tool_name, cached=True)
                return result

            result = func(*args, **kwargs)
            _cache.set(key, result, ttl)
            return result

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            from api.monitor import monitor
            key = _make_cache_key(func.__name__, args, kwargs)
            result = _cache.get(key)
            if result is not None:
                monitor.report_cache_hit(tool_name, cached=True)
                return result

            result = await func(*args, **kwargs)
            _cache.set(key, result, ttl)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
