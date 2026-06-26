"""Talent-profile public search tool with structured failure output."""
from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from langchain_core.tools import tool

from api.context import get_allowed_source_domains_context, get_run_context
from agent.research import evidence_id_for
from tools.tavily_tools import (
    _internet_search_impl,
    search_with_dedup,
)


@tool("internet_search")
def talent_public_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Search declared public sources and return a structured success or failure."""
    allowed_domains = get_allowed_source_domains_context()
    if not allowed_domains:
        return {
            "status": "error",
            "error": {
                "code": "missing_declared_public_sources",
                "message": "No declared public source domains are available for this run.",
            },
        }
    execution_id = get_run_context() or "default"
    result = search_with_dedup(
        query,
        search_fn=_internet_search_impl,
        thread_id=execution_id,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
        include_domains=allowed_domains,
    )
    if isinstance(result, str) and result.startswith("Error:"):
        return {
            "status": "error",
            "error": {"code": "public_search_failed", "message": result},
        }
    if not isinstance(result, dict):
        return {
            "status": "error",
            "error": {
                "code": "invalid_public_search_response",
                "message": "Public search returned an unsupported response.",
            },
        }
    results = [
        item
        for item in result.get("results", [])
        if isinstance(item, dict)
        and (urlparse(item.get("url", "")).hostname or "").lower() in allowed_domains
    ]
    results = [
        {
            **item,
            "evidence_id": evidence_id_for(
                item.get("url"),
                item.get("content") or item.get("title") or "",
                run_id=execution_id,
            ),
        }
        for item in results
    ]
    return {"status": "ok", "results": results}
