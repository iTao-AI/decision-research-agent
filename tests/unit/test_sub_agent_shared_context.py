"""Phase 3: 子 Agent 接入 SharedContext 测试"""
import pytest
import sys
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _mock_dependencies():
    """Mock heavy dependencies before importing"""
    for mod in ["tavily", "dotenv", "api.monitor", "tools.tavily_tools",
                "tools.mysql_tools", "tools.shared_context_tools"]:
        sys.modules.pop(mod, None)

    mock_tavily_mod = MagicMock()
    mock_client = MagicMock()
    mock_tavily_mod.TavilyClient = MagicMock(return_value=mock_client)
    sys.modules["tavily"] = mock_tavily_mod
    sys.modules["api.monitor"] = MagicMock()
    sys.modules["api.monitor"].monitor = MagicMock()

    import os
    os.environ["TAVILY_API_KEY"] = "test_key"

    yield

    for mod in ["tavily", "dotenv", "api.monitor", "tools.tavily_tools",
                "tools.mysql_tools", "tools.shared_context_tools"]:
        sys.modules.pop(mod, None)


class TestNetworkSearchAgentIntegration:
    """测试 NetworkSearchAgent 接入事实发布"""

    def test_has_shared_context_tools(self):
        """NetworkSearchAgent 应包含 publish_fact 和 query_facts 工具"""
        from agent.sub_agents.network_search_agent import NetworkSearchAgent
        agent = NetworkSearchAgent()
        tool_names = [t.name if hasattr(t, "name") else t.__name__
                      for t in agent.config.tools]
        assert "publish_fact" in tool_names
        assert "query_facts" in tool_names

    def test_shared_context_tools_are_callable(self):
        """事实发布工具应可调用"""
        from agent.shared_context import SharedContext
        from tools.shared_context_tools import publish_fact, _context

        ctx = SharedContext()
        # Temporarily override the lazy-loaded context
        import tools.shared_context_tools as sc_mod
        sc_mod._context = ctx

        result = publish_fact.invoke({
            "fact": "test fact",
            "source": "network_search",
            "topic": "test",
            "thread_id": "t1",
        })
        assert "事实已发布" in result
        assert "test fact" in result


class TestDatabaseQueryAgentIntegration:
    """测试 DatabaseQueryAgent 接入事实发布"""

    def test_has_shared_context_tools(self):
        """DatabaseQueryAgent 应包含 publish_fact 和 query_facts 工具"""
        from agent.sub_agents.database_query_agent import DatabaseQueryAgent
        agent = DatabaseQueryAgent()
        tool_names = [t.name if hasattr(t, "name") else t.__name__
                      for t in agent.config.tools]
        assert "publish_fact" in tool_names
        assert "query_facts" in tool_names

    def test_query_facts_tool_returns_results(self):
        """事实查询工具应可返回结果"""
        from agent.shared_context import SharedContext
        from tools.shared_context_tools import query_facts

        ctx = SharedContext()
        ctx.publish_fact(thread_id="t1", fact="existing fact", source="db", topic="db_test")

        import tools.shared_context_tools as sc_mod
        sc_mod._context = ctx

        result = query_facts.invoke({
            "topic": "db_test",
            "thread_id": "t1",
        })
        assert "existing fact" in result
        assert "1 条事实" in result

    def test_query_facts_empty_topic(self):
        """查询空主题应返回空提示"""
        from agent.shared_context import SharedContext
        from tools.shared_context_tools import query_facts

        ctx = SharedContext()
        import tools.shared_context_tools as sc_mod
        sc_mod._context = ctx

        result = query_facts.invoke({
            "topic": "nonexistent",
            "thread_id": "t1",
        })
        assert "没有找到事实" in result
