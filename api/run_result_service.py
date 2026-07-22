"""Canonical run result construction and resolution.

This module is application-owned: it builds and resolves deliverable result
artifacts from persisted ResearchRun state without giving framework harnesses
delivery authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

from agent.run_result import ExecutionOutcome
from api.run_repository import (
    RunDeliverySnapshotConflict,
    get_run_delivery_snapshot,
)


CANONICAL_RESULT_ARTIFACT_ID = "research-report.md"
CANONICAL_RESULT_PATH = PurePosixPath("/workspace/research-report.md")
MAX_RESULT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ResolvedRunResult:
    run_id: str
    execution_status: str
    delivery_status: str
    artifact: dict[str, str]


class RunResultUnavailable(RuntimeError):
    """Stable application error for canonical result resolution."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        problem: str,
        fix: str,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.problem = problem
        self.fix = fix

    def payload(self, *, run_id: str | None = None) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "problem": self.problem,
            "fix": self.fix,
            "retryable": self.status_code == 409,
        }
        if run_id:
            payload["run_id"] = run_id
        return payload


def build_generic_result_artifact(
    outcome: ExecutionOutcome,
    *,
    generated_at: datetime | None = None,
) -> dict[str, str]:
    """Build the immutable generic result artifact for one completed run."""
    candidate = outcome.report_candidate
    if (
        candidate is not None
        and getattr(candidate, "path", None) == CANONICAL_RESULT_PATH
        and _is_non_empty_bounded_text(getattr(candidate, "content", ""))
    ):
        content = _sanitize_result_content(candidate.content)
        if not _is_non_empty_bounded_text(content):
            return _artifact(
                kind="research_report_fallback_markdown",
                content=_fallback_report(outcome, generated_at=generated_at),
            )
        return _artifact(
            kind="research_report_markdown",
            content=content,
        )

    return _artifact(
        kind="research_report_fallback_markdown",
        content=_fallback_report(outcome, generated_at=generated_at),
    )


def _artifact(*, kind: str, content: str) -> dict[str, str]:
    return {
        "artifact_id": CANONICAL_RESULT_ARTIFACT_ID,
        "kind": kind,
        "media_type": "text/markdown",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _is_non_empty_bounded_text(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return len(value.encode("utf-8")) <= MAX_RESULT_BYTES


def _fallback_report(
    outcome: ExecutionOutcome,
    *,
    generated_at: datetime | None,
) -> str:
    timestamp = (generated_at or datetime.now(timezone.utc)).isoformat()
    bounded_text = _safe_excerpt(outcome.last_agent_text)
    if not bounded_text:
        bounded_text = "No canonical report was produced by the agent."
    lines = [
        "# Fallback Report",
        "",
        "A canonical `/workspace/research-report.md` artifact was not available.",
        "",
        f"- Run ID: {outcome.run_id or 'unknown'}",
        f"- Generated at: {timestamp}",
        "",
        "## Last Agent Text",
        "",
        bounded_text,
        "",
    ]
    return "\n".join(lines)


_HOST_ABSOLUTE_PATH_RE = re.compile(
    r"(?:(?:/Users|/private|/var|/tmp|/Volumes|/home|/opt)/[^\s)\"']+)"
)
_CHECKPOINT_OR_TRACEBACK_RE = re.compile(r"(?:checkpoint|traceback)", re.IGNORECASE)


def _sanitize_result_content(value: str, *, limit: int | None = None) -> str:
    if not value:
        return ""
    sanitized_lines = []
    for line in value.splitlines():
        if _CHECKPOINT_OR_TRACEBACK_RE.search(line):
            continue
        sanitized_lines.append(_HOST_ABSOLUTE_PATH_RE.sub("[redacted-path]", line))
    text = "\n".join(sanitized_lines).strip()
    if limit is not None and len(text) > limit:
        text = f"{text[:limit]}…"
    return text


def _safe_excerpt(value: str, *, limit: int = 4000) -> str:
    return _sanitize_result_content(value, limit=limit)


def _contains_unsafe_result_content(value: str) -> bool:
    return bool(
        _HOST_ABSOLUTE_PATH_RE.search(value)
        or _CHECKPOINT_OR_TRACEBACK_RE.search(value)
    )


def resolve_run_result(
    *,
    run_id: str,
    db_path: str | None = None,
) -> ResolvedRunResult:
    """Resolve the current deliverable result for a persisted run."""
    try:
        run = get_run_delivery_snapshot(run_id=run_id, db_path=db_path)
    except RunDeliverySnapshotConflict as exc:
        raise _unavailable() from exc
    if run is None:
        raise RunResultUnavailable(
            status_code=404,
            code="run_not_found",
            problem="The requested ResearchRun does not exist.",
            fix="Check the run_id returned by POST /api/runs.",
        )

    execution_status = run["execution_status"]
    delivery_status = run["delivery_status"]
    if execution_status in {"pending", "running"}:
        raise RunResultUnavailable(
            status_code=409,
            code="run_not_terminal",
            problem="The ResearchRun has not reached a terminal state.",
            fix="Poll GET /api/runs/{run_id} until execution_status is terminal.",
        )
    if execution_status == "failed":
        raise RunResultUnavailable(
            status_code=409,
            code="run_failed",
            problem="The ResearchRun failed and has no deliverable result.",
            fix="Inspect the bounded run projection and start a new run if needed.",
        )
    if delivery_status == "review_required":
        raise RunResultUnavailable(
            status_code=409,
            code="run_review_required",
            problem="The ResearchRun requires review before delivery.",
            fix="Complete the review workflow, then retry the result request.",
        )
    if delivery_status == "blocked":
        raise RunResultUnavailable(
            status_code=409,
            code="run_delivery_blocked",
            problem="Delivery is blocked for this ResearchRun.",
            fix="Start a corrected run if a deliverable result is still needed.",
        )
    if delivery_status != "ready":
        raise RunResultUnavailable(
            status_code=409,
            code="run_result_unavailable",
            problem="No deliverable result is available for this ResearchRun.",
            fix="Retry after the run reaches ready delivery state.",
        )

    artifact_id = _select_artifact_id(run)
    by_id = {row["artifact_id"]: row for row in run["artifacts"]}
    artifact = by_id.get(artifact_id) if artifact_id is not None else None
    if not _valid_artifact(artifact):
        raise _unavailable()

    return ResolvedRunResult(
        run_id=run_id,
        execution_status=execution_status,
        delivery_status=delivery_status,
        artifact={
            "artifact_id": artifact["artifact_id"],
            "kind": artifact["kind"],
            "media_type": artifact["media_type"],
            "content": artifact["content"],
            "content_hash": artifact["content_hash"],
        },
    )


def _select_artifact_id(run: dict[str, Any]) -> str | None:
    if run.get("profile_id") == "generic":
        return CANONICAL_RESULT_ARTIFACT_ID

    artifact_ids = {
        item["artifact_id"]: item
        for item in run.get("artifacts", [])
    }
    current_ids = run.get("current_artifact_ids", ())
    if current_ids:
        for artifact_id in current_ids:
            artifact = artifact_ids.get(artifact_id)
            if artifact is not None and artifact.get("media_type") == "text/markdown":
                return artifact_id
        return None

    if "decision-brief.md" in artifact_ids:
        return "decision-brief.md"
    if CANONICAL_RESULT_ARTIFACT_ID in artifact_ids:
        return CANONICAL_RESULT_ARTIFACT_ID
    return None


def _valid_artifact(artifact: dict[str, Any] | None) -> bool:
    if artifact is None:
        return False
    content = artifact.get("content")
    content_hash = artifact.get("content_hash")
    if not _is_non_empty_bounded_text(content):
        return False
    if not isinstance(content_hash, str):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        return False
    if str(artifact.get("kind", "")).startswith("research_report_"):
        if _contains_unsafe_result_content(content):
            return False
        return hashlib.sha256(content.encode("utf-8")).hexdigest() == content_hash
    return True


def _unavailable() -> RunResultUnavailable:
    return RunResultUnavailable(
        status_code=409,
        code="run_result_unavailable",
        problem="The persisted result artifact is missing or invalid.",
        fix="Retry later or start a new run if the artifact cannot be recovered.",
    )
