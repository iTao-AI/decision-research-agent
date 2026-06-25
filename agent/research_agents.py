"""Compile the bounded synchronous researchers used by the generic harness."""
from __future__ import annotations

from typing import Any

from deepagents.middleware.subagents import CompiledSubAgent
from langchain.agents import create_agent

from agent.profile_middleware import build_profile_middleware
from agent.prompts import sub_agents_config
from agent.runtime_context import ResearchRuntimeContext
from tools.mysql_tools import execute_sql_query, get_table_data, list_sql_tables
from tools.ragflow_tools import create_ask_delete, get_assistant_list
from tools.tavily_tools import internet_search


_RESEARCHER_CONFIG = {
    "network_search": {
        "prompt_key": "tavily",
        "description": "Research public web sources with the approved search tool.",
        "tools": [internet_search],
    },
    "database_query": {
        "prompt_key": "db",
        "description": "Query approved business database tools.",
        "tools": [list_sql_tables, get_table_data, execute_sql_query],
    },
    "knowledge_base": {
        "prompt_key": "ragflow",
        "description": "Query the approved knowledge-base tools.",
        "tools": [get_assistant_list, create_ask_delete],
    },
}


def compile_generic_researchers(
    *,
    model: Any,
) -> dict[str, CompiledSubAgent]:
    """Compile three role-limited LangChain researchers."""
    compiled: dict[str, CompiledSubAgent] = {}
    for name, config in _RESEARCHER_CONFIG.items():
        runnable = create_agent(
            model=model,
            tools=config["tools"],
            system_prompt=sub_agents_config[config["prompt_key"]]["system_prompt"],
            middleware=build_profile_middleware("generic", role=name),
            context_schema=ResearchRuntimeContext,
            name=name,
        )
        compiled[name] = {
            "name": name,
            "description": config["description"],
            "runnable": runnable,
        }
    return compiled
