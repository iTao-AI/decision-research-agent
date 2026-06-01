"""Tests for tools/cache.py — TTLCache, cached_tool decorator"""
import time
import pytest
from tools.cache import TTLCache, cached_tool


class TestTTLCache:
    def test_set_and_get(self):
        """存入后应能获取"""
        cache = TTLCache()
        cache.set("key1", "value1", ttl=300)
        assert cache.get("key1") == "value1"

    def test_expired_key_returns_none(self):
        """过期后应返回 None 并清除"""
        cache = TTLCache()
        cache.set("key1", "value1", ttl=0.1)
        time.sleep(0.2)
        result = cache.get("key1")
        assert result is None

    def test_nonexistent_key_returns_none(self):
        """不存在的 key 应返回 None"""
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_capacity_evicts_oldest(self):
        """超过容量应淘汰最早过期的 key"""
        cache = TTLCache(max_size=3)
        cache.set("a", 1, ttl=300)
        cache.set("b", 2, ttl=300)
        cache.set("c", 3, ttl=300)
        cache.set("d", 4, ttl=300)  # 超过容量

        summary = cache.size()
        assert summary == 3

    def test_different_values_same_key(self):
        """同 key 不同值应覆盖"""
        cache = TTLCache()
        cache.set("key1", "old", ttl=300)
        cache.set("key1", "new", ttl=300)
        assert cache.get("key1") == "new"

    def test_size(self):
        """size 应返回有效 key 数量"""
        cache = TTLCache()
        cache.set("a", 1, ttl=300)
        cache.set("b", 2, ttl=0.1)
        time.sleep(0.2)
        cache.get("b")  # 触发清除
        assert cache.size() == 1


class TestCachedToolDecorator:
    def test_first_call_executes_function(self):
        """首次调用应执行原函数"""
        call_count = [0]

        @cached_tool(ttl=300, tool_name="test_tool")
        def my_func(x):
            call_count[0] += 1
            return x * 2

        assert my_func(5) == 10
        assert call_count[0] == 1

    def test_cached_call_skips_execution(self):
        """缓存命中应跳过执行"""
        call_count = [0]

        @cached_tool(ttl=300, tool_name="test_tool")
        def my_func(x):
            call_count[0] += 1
            return x * 2

        my_func(5)  # 首次
        my_func(5)  # 缓存命中
        assert call_count[0] == 1

    def test_different_args_independent_cache(self):
        """不同参数应独立缓存"""
        call_count = [0]

        @cached_tool(ttl=300, tool_name="test_tool")
        def my_func(x):
            call_count[0] += 1
            return x * 2

        my_func(5)
        my_func(10)
        assert call_count[0] == 2

    def test_cache_expiry_re_executes(self):
        """缓存过期后应重新执行"""
        call_count = [0]

        @cached_tool(ttl=0.1, tool_name="test_tool")
        def my_func(x):
            call_count[0] += 1
            return x * 2

        my_func(5)
        time.sleep(0.2)
        my_func(5)
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_async_function(self):
        """应支持异步函数"""
        call_count = [0]

        @cached_tool(ttl=300, tool_name="test_tool")
        async def async_func(x):
            call_count[0] += 1
            return x * 2

        result = await async_func(5)
        assert result == 10
        assert call_count[0] == 1
