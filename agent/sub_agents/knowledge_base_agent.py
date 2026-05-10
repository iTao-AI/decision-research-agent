from agent.sub_agents.base import BaseAgent, AgentConfig
from agent.prompts import sub_agents_config
from tools.ragflow_tools import get_assistant_list, create_ask_delete


class KnowledgeBaseAgent(BaseAgent):
    """知识库子 Agent"""

    def __init__(self):
        config = AgentConfig(
            name=sub_agents_config["ragflow"].get("name", ""),
            description=sub_agents_config["ragflow"].get("description", ""),
            system_prompt=sub_agents_config["ragflow"].get("system_prompt", ""),
            tools=[get_assistant_list, create_ask_delete],
        )
        super().__init__(config)


# Backward compatibility
knowledge_base_agent = KnowledgeBaseAgent()
