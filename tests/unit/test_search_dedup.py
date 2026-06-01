"""Test search query deduplication within a single task."""
import pytest
from unittest.mock import MagicMock


class TestSearchDedup:
    """Test that identical queries are not re-executed within same task."""

    def test_dedup_same_query_uses_cache(self):
        """Same query within a task returns cached result without calling again."""
        from tools.tavily_tools import search_with_dedup, clear_search_cache

        clear_search_cache()
        mock_fn = MagicMock(return_value={"results": "data"})

        results_1 = search_with_dedup("AI trends", search_fn=mock_fn, thread_id="test-dedup")
        results_2 = search_with_dedup("AI trends", search_fn=mock_fn, thread_id="test-dedup")

        assert results_1 == results_2
        # mock_fn should only have been called once (second call hit cache)
        assert mock_fn.call_count == 1
        clear_search_cache("test-dedup")

    def test_different_query_not_deduped(self):
        """Different queries should NOT be deduped."""
        from tools.tavily_tools import search_with_dedup, clear_search_cache

        clear_search_cache()
        mock_fn = MagicMock(side_effect=lambda q, **kw: {"results": q})

        results_1 = search_with_dedup("AI trends", search_fn=mock_fn, thread_id="test-dedup-2")
        results_2 = search_with_dedup("quantum computing", search_fn=mock_fn, thread_id="test-dedup-2")

        assert results_1 != results_2
        assert mock_fn.call_count == 2
        clear_search_cache("test-dedup-2")

    def test_same_query_different_options_not_deduped(self):
        """Different Tavily options must not reuse same-query cached results."""
        from tools.tavily_tools import search_with_dedup, clear_search_cache

        clear_search_cache()
        mock_fn = MagicMock(side_effect=lambda q, **kw: {"max_results": kw["max_results"]})

        results_1 = search_with_dedup(
            "AI trends",
            search_fn=mock_fn,
            thread_id="test-dedup-options",
            max_results=3,
        )
        results_2 = search_with_dedup(
            "AI trends",
            search_fn=mock_fn,
            thread_id="test-dedup-options",
            max_results=5,
        )

        assert results_1 != results_2
        assert mock_fn.call_count == 2
        clear_search_cache("test-dedup-options")

    def test_dedup_scoped_per_thread(self):
        """Dedup cache is isolated per thread_id."""
        from tools.tavily_tools import search_with_dedup, clear_search_cache

        clear_search_cache()
        mock_fn = MagicMock(return_value={"results": "data"})

        results_a = search_with_dedup("AI trends", search_fn=mock_fn, thread_id="thread-a")
        results_b = search_with_dedup("AI trends", search_fn=mock_fn, thread_id="thread-b")

        # Different threads should have separate caches — two calls
        assert mock_fn.call_count == 2
        clear_search_cache("thread-a")
        clear_search_cache("thread-b")

    def test_internet_search_uses_dedup_for_current_thread(self):
        """The registered LangChain tool should use the per-thread dedup path."""
        from api.context import set_thread_context, _thread_id_ctx
        from tools.tavily_tools import internet_search, clear_search_cache

        clear_search_cache()
        token = set_thread_context("tool-thread")
        try:
            with pytest.MonkeyPatch.context() as monkeypatch:
                mock_impl = MagicMock(return_value={"results": "data"})
                monkeypatch.setattr("tools.tavily_tools._internet_search_impl", mock_impl)

                result_1 = internet_search.invoke({"query": "AI trends"})
                result_2 = internet_search.invoke({"query": "AI trends"})

                assert result_1 == result_2
                assert mock_impl.call_count == 1
        finally:
            _thread_id_ctx.reset(token)
            clear_search_cache("tool-thread")
