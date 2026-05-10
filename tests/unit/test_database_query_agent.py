"""Phase C: DatabaseQueryAgent 重构测试"""
import sys
from unittest.mock import MagicMock

# Mock mysql_tools before importing the agent
_mock_mysql = MagicMock()
sys.modules.setdefault("tools.mysql_tools", _mock_mysql)


class TestDatabaseQueryAgent:
    """测试 DatabaseQueryAgent 配置正确性和 to_dict 兼容性"""

    def test_create_agent(self):
        """DatabaseQueryAgent 应该可以正常创建"""
        from agent.sub_agents.database_query_agent import DatabaseQueryAgent
        from agent.sub_agents.base import BaseAgent
        from agent.prompts import sub_agents_config

        agent = DatabaseQueryAgent()
        assert isinstance(agent, BaseAgent)
        assert agent.config.name == sub_agents_config["db"].get("name", "")

    def test_to_dict_has_required_fields(self):
        """to_dict() 输出应该包含 name, description, system_prompt, tools"""
        from agent.sub_agents.database_query_agent import DatabaseQueryAgent

        agent = DatabaseQueryAgent()
        result = agent.to_dict()

        assert "name" in result
        assert "description" in result
        assert "system_prompt" in result
        assert "tools" in result
        assert isinstance(result["tools"], list)

    def test_to_dict_matches_original_format(self):
        """to_dict() 输出应该与原始 dict 格式一致"""
        from agent.prompts import sub_agents_config
        from agent.sub_agents.database_query_agent import DatabaseQueryAgent

        expected_name = sub_agents_config["db"].get("name", "")
        expected_desc = sub_agents_config["db"].get("description", "")
        expected_prompt = sub_agents_config["db"].get("system_prompt", "")

        agent = DatabaseQueryAgent()
        result = agent.to_dict()

        assert result["name"] == expected_name
        assert result["description"] == expected_desc
        assert result["system_prompt"] == expected_prompt
