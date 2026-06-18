"""Runtime limits for the Talent Hiring Signal profile."""
from __future__ import annotations

from agent.runtime_env import resolve_env


DEFAULT_TALENT_RECURSION_LIMIT = 160


def talent_recursion_limit() -> int:
    configured = resolve_env(
        "DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT",
        "DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT",
    )
    if configured is None or not configured.strip():
        return DEFAULT_TALENT_RECURSION_LIMIT
    try:
        limit = int(configured)
    except ValueError:
        return DEFAULT_TALENT_RECURSION_LIMIT
    if limit < 1:
        return DEFAULT_TALENT_RECURSION_LIMIT
    return limit
