"""Phase D: KnowledgeBaseAgent 重构测试"""
import sys
from unittest.mock import MagicMock

_mock_ragflow = MagicMock()
sys.modules.setdefault("tools.ragflow_tools", _mock_ragflow)


class TestKnowledgeBaseAgent:
    """测试 KnowledgeBaseAgent 配置正确性和 to_dict 兼容性"""

    def test_create_agent(self):
        from agent.sub_agents.knowledge_base_agent import KnowledgeBaseAgent
        from agent.sub_agents.base import BaseAgent
        from agent.prompts import sub_agents_config

        agent = KnowledgeBaseAgent()
        assert isinstance(agent, BaseAgent)
        assert agent.config.name == sub_agents_config["ragflow"].get("name", "")

    def test_to_dict_has_required_fields(self):
        from agent.sub_agents.knowledge_base_agent import KnowledgeBaseAgent

        agent = KnowledgeBaseAgent()
        result = agent.to_dict()

        assert "name" in result
        assert "description" in result
        assert "system_prompt" in result
        assert "tools" in result
        assert isinstance(result["tools"], list)

    def test_to_dict_matches_original_format(self):
        from agent.prompts import sub_agents_config
        from agent.sub_agents.knowledge_base_agent import KnowledgeBaseAgent

        expected_name = sub_agents_config["ragflow"].get("name", "")
        expected_desc = sub_agents_config["ragflow"].get("description", "")
        expected_prompt = sub_agents_config["ragflow"].get("system_prompt", "")

        agent = KnowledgeBaseAgent()
        result = agent.to_dict()

        assert result["name"] == expected_name
        assert result["description"] == expected_desc
        assert result["system_prompt"] == expected_prompt
