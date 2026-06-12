"""Phase A: AgentContext + AgentConfig + BaseAgent tests"""
import pytest
from pathlib import Path


class TestAgentContext:
    """Test AgentContext creation and state management"""

    def test_create_context_with_thread_id(self):
        """Creating AgentContext should accept thread_id and workspace_dir"""
        from agent.sub_agents.base import AgentContext

        ctx = AgentContext(thread_id="test-123", workspace_dir=Path("/tmp/test"))

        assert ctx.thread_id == "test-123"
        assert ctx.workspace_dir == Path("/tmp/test")
        assert ctx.memory == {}
        assert ctx.metadata == {}

    def test_memory_read_write(self):
        """AgentContext should support cross-tool-call memory sharing"""
        from agent.sub_agents.base import AgentContext

        ctx = AgentContext(thread_id="test-1", workspace_dir=Path("/tmp/test"))

        ctx.memory["search_results"] = ["result1", "result2"]
        assert ctx.memory["search_results"] == ["result1", "result2"]

    def test_metadata_tracking(self):
        """AgentContext should track metadata"""
        from agent.sub_agents.base import AgentContext

        ctx = AgentContext(thread_id="test-1", workspace_dir=Path("/tmp/test"))

        ctx.metadata["call_count"] = 3
        ctx.metadata["execution_time"] = 1.5

        assert ctx.metadata["call_count"] == 3
        assert ctx.metadata["execution_time"] == 1.5

    def test_run_context_is_independent_from_langgraph_thread_context(self):
        from api.context import (
            get_run_context,
            get_thread_context,
            reset_execution_context,
            set_run_context,
            set_thread_context,
        )

        thread_token = set_thread_context("thread-1")
        run_token = set_run_context("run-1")

        assert get_thread_context() == "thread-1"
        assert get_run_context() == "run-1"

        reset_execution_context(run_token, thread_token)
        assert get_thread_context() is None
        assert get_run_context() is None


class TestAgentConfig:
    """Test AgentConfig creation and to_dict compatibility"""

    def test_create_config(self):
        """AgentConfig should accept name, description, system_prompt, tools"""
        from agent.sub_agents.base import AgentConfig

        def dummy_tool():
            pass

        config = AgentConfig(
            name="test_agent",
            description="A test agent",
            system_prompt="You are a test agent",
            tools=[dummy_tool]
        )

        assert config.name == "test_agent"
        assert config.description == "A test agent"
        assert config.system_prompt == "You are a test agent"
        assert dummy_tool in config.tools

    def test_to_dict_output(self):
        """AgentConfig.to_dict() should output deepagents compatible format"""
        from agent.sub_agents.base import AgentConfig

        def dummy_tool():
            pass

        config = AgentConfig(
            name="test_agent",
            description="A test agent",
            system_prompt="You are a test agent",
            tools=[dummy_tool]
        )

        result = config.to_dict()

        assert result["name"] == "test_agent"
        assert result["description"] == "A test agent"
        assert result["system_prompt"] == "You are a test agent"
        assert dummy_tool in result["tools"]
