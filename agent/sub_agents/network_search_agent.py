from agent.sub_agents.base import BaseAgent, AgentConfig
from agent.prompts import sub_agents_config
from tools.tavily_tools import internet_search
from tools.shared_context_tools import publish_fact, query_facts


class NetworkSearchAgent(BaseAgent):
    """网络搜索子 Agent"""

    def __init__(self):
        config = AgentConfig(
            name=sub_agents_config["tavily"].get("name", ""),
            description=sub_agents_config["tavily"].get("description", ""),
            system_prompt=sub_agents_config["tavily"].get("system_prompt", ""),
            tools=[internet_search, publish_fact, query_facts],
        )
        super().__init__(config)


# Backward compatibility: module-level instance
network_search_agent = NetworkSearchAgent()
