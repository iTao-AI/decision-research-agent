from agent.sub_agents.base import BaseAgent, AgentConfig
from agent.prompts import sub_agents_config
from tools.mysql_tools import list_sql_tables, get_table_data, execute_sql_query
from tools.shared_context_tools import publish_fact, query_facts


class DatabaseQueryAgent(BaseAgent):
    """数据库查询子 Agent"""

    def __init__(self):
        config = AgentConfig(
            name=sub_agents_config["db"].get("name", ""),
            description=sub_agents_config["db"].get("description", ""),
            system_prompt=sub_agents_config["db"].get("system_prompt", ""),
            tools=[list_sql_tables, get_table_data, execute_sql_query, publish_fact, query_facts],
        )
        super().__init__(config)


# Backward compatibility
database_query_agent = DatabaseQueryAgent()
