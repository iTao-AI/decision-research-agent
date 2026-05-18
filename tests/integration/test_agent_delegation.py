"""Integration tests for Agent delegation链路.

Verifies that sub-agents are properly structured, tools are registered,
and the delegation configuration is correct.
"""
import pytest

from agent.sub_agents.base import AgentConfig
from agent.sub_agents.network_search_agent import NetworkSearchAgent
from agent.sub_agents.database_query_agent import DatabaseQueryAgent
from agent.sub_agents.knowledge_base_agent import KnowledgeBaseAgent


class TestSubAgentStructure:
    """Verify sub-agent class structure and to_dict() output."""

    def test_network_search_agent_to_dict(self):
        """NetworkSearchAgent.to_dict() produces the expected format."""
        agent = NetworkSearchAgent()
        result = agent.to_dict()

        assert isinstance(result, dict)
        assert "name" in result
        assert "description" in result
        assert "system_prompt" in result
        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0

    def test_database_query_agent_to_dict(self):
        """DatabaseQueryAgent.to_dict() produces the expected format."""
        agent = DatabaseQueryAgent()
        result = agent.to_dict()

        assert isinstance(result, dict)
        assert "name" in result
        assert "description" in result
        assert "system_prompt" in result
        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0

    def test_knowledge_base_agent_to_dict(self):
        """KnowledgeBaseAgent.to_dict() produces the expected format."""
        agent = KnowledgeBaseAgent()
        result = agent.to_dict()

        assert isinstance(result, dict)
        assert "name" in result
        assert "description" in result
        assert "system_prompt" in result
        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0

    def test_all_agents_have_non_empty_names(self):
        """All sub-agents have non-empty names."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        for agent in agents:
            d = agent.to_dict()
            assert d["name"], f"Agent has empty name: {agent.__class__.__name__}"

    def test_all_agents_have_non_empty_descriptions(self):
        """All sub-agents have non-empty descriptions."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        for agent in agents:
            d = agent.to_dict()
            assert d["description"], f"Agent has empty description: {agent.__class__.__name__}"

    def test_all_agents_have_non_empty_system_prompts(self):
        """All sub-agents have non-empty system prompts."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        for agent in agents:
            d = agent.to_dict()
            assert d["system_prompt"], f"Agent has empty system_prompt: {agent.__class__.__name__}"


class TestToolRegistration:
    """Verify tool registration completeness."""

    def test_network_search_agent_has_search_tool(self):
        """NetworkSearchAgent has internet_search tool registered."""
        agent = NetworkSearchAgent()
        tool_names = [t.name for t in agent.to_dict()["tools"]]
        assert any("search" in name.lower() or "tavily" in name.lower() for name in tool_names), \
            f"Expected search tool, got: {tool_names}"

    def test_database_query_agent_has_query_tools(self):
        """DatabaseQueryAgent has database query tools registered."""
        agent = DatabaseQueryAgent()
        tool_names = [t.name for t in agent.to_dict()["tools"]]
        assert any("mysql" in name.lower() or "query" in name.lower() or "sql" in name.lower() for name in tool_names), \
            f"Expected database tools, got: {tool_names}"

    def test_knowledge_base_agent_has_rag_tools(self):
        """KnowledgeBaseAgent has RAG/knowledge base tools registered."""
        agent = KnowledgeBaseAgent()
        tool_names = [t.name for t in agent.to_dict()["tools"]]
        assert any("rag" in name.lower() or "knowledge" in name.lower() or "assistant" in name.lower() for name in tool_names), \
            f"Expected RAG tools, got: {tool_names}"

    def test_all_tools_are_callable(self):
        """All registered tools have invoke capability (StructuredTool or callable)."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        for agent in agents:
            for tool in agent.to_dict()["tools"]:
                # StructuredTool has .invoke; plain functions are callable
                has_invoke = hasattr(tool, "invoke") or callable(tool)
                assert has_invoke, f"Tool {tool} in {agent.__class__.__name__} is not invocable"


class TestAgentConfig:
    """Verify AgentConfig TypedDict structure."""

    def test_agent_config_has_required_fields(self):
        """AgentConfig requires name, description, system_prompt, tools."""
        config = AgentConfig(
            name="test_agent",
            description="A test agent",
            system_prompt="You are a test agent",
            tools=[],
        )
        assert config.name == "test_agent"
        assert config.description == "A test agent"
        assert config.system_prompt == "You are a test agent"
        assert config.tools == []

    def test_agent_config_rejects_missing_fields(self):
        """AgentConfig raises error when required fields are missing."""
        with pytest.raises(TypeError):
            AgentConfig(
                name="test_agent",
                # missing description, system_prompt, tools
            )


class TestDelegationStructure:
    """Verify the overall delegation structure matches deepagents expectations."""

    def test_subagents_list_format(self):
        """All sub-agents produce dicts compatible with create_deep_agent."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        subagents_list = [a.to_dict() for a in agents]

        assert len(subagents_list) == 3
        for subagent in subagents_list:
            assert isinstance(subagent, dict)
            required_keys = {"name", "description", "system_prompt", "tools"}
            assert required_keys.issubset(set(subagent.keys())), \
                f"Missing keys: {required_keys - set(subagent.keys())}"

    def test_no_duplicate_agent_names(self):
        """All sub-agent names are unique."""
        agents = [
            NetworkSearchAgent(),
            DatabaseQueryAgent(),
            KnowledgeBaseAgent(),
        ]
        names = [a.to_dict()["name"] for a in agents]
        assert len(names) == len(set(names)), f"Duplicate agent names: {names}"
