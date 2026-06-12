"""Canonical DecisionBrief hashing and deterministic Markdown rendering."""
from __future__ import annotations

import hashlib
import json

from agent.talent_contracts import DecisionBrief


def _canonical_payload(brief: DecisionBrief) -> bytes:
    payload = brief.model_dump(
        mode="json",
        exclude={"generated_at", "content_hash"},
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def with_content_hash(brief: DecisionBrief) -> DecisionBrief:
    content_hash = hashlib.sha256(_canonical_payload(brief)).hexdigest()
    return brief.model_copy(update={"content_hash": content_hash})


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None declared"


def render_markdown(brief: DecisionBrief) -> str:
    """Render stable Markdown from canonical JSON; no model calls or file tools."""
    return (
        "# Talent Hiring Signal Decision Brief\n\n"
        f"- Run ID: `{brief.run_id}`\n"
        f"- Profile: `{brief.profile_id}@{brief.profile_version}`\n"
        f"- Content hash: `{brief.content_hash}`\n"
        f"- Generated at: `{brief.generated_at.isoformat()}`\n\n"
        "## Executive Summary\n\n"
        f"{brief.executive_summary}\n\n"
        "## Target Roles\n\n"
        f"{_bullets(list(brief.scope.target_roles))}\n\n"
        "## Limitations\n\n"
        f"{_bullets(brief.limitations)}\n\n"
        "## Recommendations\n\n"
        f"{_bullets(brief.recommendations)}\n"
    )
