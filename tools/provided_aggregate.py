"""Read a declared, versioned benchmark aggregate without exposing file paths."""
from __future__ import annotations

import json
from pathlib import Path
import re

from langchain_core.tools import tool

from agent.research import evidence_id_for
from agent.runtime_env import resolve_env
from api.context import get_allowed_aggregate_ids_context, get_run_context
from tools.tavily_tools import _publish_search_evidence


FIXTURE_ROOT = Path(__file__).parents[1] / "benchmarks" / "fixtures"
_AGGREGATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _error(code: str, message: str) -> dict:
    return {"status": "error", "error": {"code": code, "message": message}}


@tool("provided_aggregate")
def provided_aggregate(aggregate_id: str) -> dict:
    """Read one scope-declared, server-bundled aggregate in benchmark mode."""
    fixtures_enabled = resolve_env(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        default="",
    )
    if (fixtures_enabled or "").lower() != "true":
        return _error(
            "provided_aggregate_disabled",
            "The server-side benchmark fixture provider is disabled.",
        )
    if not _AGGREGATE_ID_RE.fullmatch(aggregate_id):
        return _error(
            "invalid_provided_aggregate_id",
            "The aggregate ID must be a simple versioned identifier.",
        )
    if aggregate_id not in get_allowed_aggregate_ids_context():
        return _error(
            "undeclared_provided_aggregate",
            "The aggregate ID was not declared in the validated ResearchScope.",
        )

    fixture_path = FIXTURE_ROOT / f"{aggregate_id}.json"
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _error("provided_aggregate_not_found", "The declared aggregate was not found.")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _error(
            "invalid_provided_aggregate_fixture",
            "The declared aggregate fixture could not be validated.",
        )
    if payload.get("aggregate_id") != aggregate_id or not isinstance(
        payload.get("samples"), list
    ):
        return _error(
            "invalid_provided_aggregate_fixture",
            "The declared aggregate fixture could not be validated.",
        )

    execution_id = get_run_context() or "default"
    results = []
    for sample in payload["samples"]:
        if not isinstance(sample, dict):
            continue
        source_url = sample.get("source_url")
        content = sample.get("content")
        if not isinstance(source_url, str) or not source_url.startswith(
            ("http://", "https://")
        ):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        results.append(
            {
                "sample_id": sample.get("sample_id"),
                "url": source_url,
                "content": content.strip(),
                "evidence_id": evidence_id_for(
                    source_url, content, run_id=execution_id
                ),
            }
        )
    if not results:
        return _error(
            "invalid_provided_aggregate_fixture",
            "The declared aggregate fixture contains no valid samples.",
        )
    _publish_search_evidence({"results": results}, thread_id=execution_id)
    return {"status": "ok", "aggregate_id": aggregate_id, "results": results}
