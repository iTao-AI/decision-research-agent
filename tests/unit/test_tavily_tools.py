"""Phase B: Tavily 工具重构测试 — 重试、超时、错误返回"""
import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture(autouse=True)
def _mock_dependencies():
    """Mock tavily and dependencies before importing tavily_tools"""
    for mod in ["tavily", "dotenv", "api.monitor", "tools.tavily_tools"]:
        sys.modules.pop(mod, None)

    # Mock tavily client
    mock_tavily_mod = MagicMock()
    mock_client = MagicMock()
    mock_tavily_mod.TavilyClient = MagicMock(return_value=mock_client)
    sys.modules["tavily"] = mock_tavily_mod
    sys.modules["api.monitor"] = MagicMock()
    sys.modules["api.monitor"].monitor = MagicMock()

    # Set env
    import os
    os.environ["TAVILY_API_KEY"] = "test_key"

    yield

    for mod in ["tavily", "dotenv", "api.monitor", "tools.tavily_tools"]:
        sys.modules.pop(mod, None)


class TestTavilyTools:
    """测试 Tavily 工具的重试、超时、错误返回"""

    def test_internet_search_returns_results(self):
        """正常搜索应返回结果"""
        from tools.tavily_tools import internet_search
        with patch("tools.tavily_tools._tavily_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"title": "Test", "url": "http://test.com"}]
            result = internet_search.invoke({"query": "test"})
            assert result == [{"title": "Test", "url": "http://test.com"}]

    def test_search_timeout_passed_to_sdk(self):
        """验证 timeout 参数被正确传递给 Tavily SDK"""
        from tools.tavily_tools import _tavily_search
        import asyncio

        mock_client = MagicMock()
        mock_client.search.return_value = [{"title": "Test", "url": "http://test.com"}]

        with patch("tavily.TavilyClient", return_value=mock_client):
            result = asyncio.run(_tavily_search(
                query="test", max_results=5, topic="general",
                include_raw_content=False, timeout=15,
            ))
            mock_client.search.assert_called_once()
            call_args = mock_client.search.call_args
            call_kwargs = call_args[1]
            assert call_kwargs["timeout"] == 15
            assert call_kwargs["max_results"] == 5
            assert call_kwargs["topic"] == "general"
            assert call_kwargs["include_raw_content"] is False
            # query is passed as positional arg
            assert call_args[0][0] == "test"
            assert result == [{"title": "Test", "url": "http://test.com"}]

    def test_search_retries_on_connection_error(self):
        """连接错误应触发重试，重试耗尽后返回错误字符串"""
        from tools.tavily_tools import internet_search
        import asyncio

        mock_client = MagicMock()
        mock_client.search.side_effect = ConnectionError("Connection refused")

        with patch("tavily.TavilyClient", return_value=mock_client):
            result = internet_search.invoke({"query": "test"})
            # Should have been called 3 times (max_retries=3)
            assert mock_client.search.call_count == 3
            assert isinstance(result, str)
            assert "Error" in result

    def test_internet_search_no_api_key_returns_error(self):
        """无 API Key 应返回错误字符串"""
        import os
        os.environ.pop("TAVILY_API_KEY", None)
        from tools.tavily_tools import internet_search
        result = internet_search.invoke({"query": "test"})
        assert "Error" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_search_with_resilience_end_to_end(self):
        """_cached_search_with_resilience should retry on failure and respect timeout."""
        from tools.tavily_tools import _cached_search_with_resilience
        import os
        os.environ["TAVILY_API_KEY"] = "test_key"

        call_count = {"n": 0}

        # Mock at the TavilyClient level to verify retry actually fires
        with patch("tavily.TavilyClient") as mock_cls:
            mock_client = MagicMock()
            # Fail twice, succeed on third call
            def side_effect(*args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] <= 2:
                    raise ConnectionError("transient error")
                return {"results": [{"title": "Found"}]}
            mock_client.search = MagicMock(side_effect=side_effect)
            mock_cls.return_value = mock_client

            result = await _cached_search_with_resilience("test query", 5, "general", False)

            assert call_count["n"] == 3  # 2 failures + 1 success
            assert result == {"results": [{"title": "Found"}]}
