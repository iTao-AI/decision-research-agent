"""Public-safe paired projections for context-reliability evaluation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from api.run_result_service import ResolvedRunResult, RunResultUnavailable


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
CONTEXT_RELIABILITY_FINDING_CODES = (
    "context.query_changed",
    "context.evidence_changed",
    "context.citation_state_changed",
    "context.verification_state_changed",
    "context.artifact_changed",
    "context.terminal_state_changed",
    "context.result_resolution_changed",
)


class ContextProjectionError(ValueError):
    """Stable fail-closed error for malformed evaluation projections."""

    def __init__(self) -> None:
        self.code = "context.projection_invalid"
        super().__init__(self.code)


def _fail() -> None:
    raise ContextProjectionError()


def _text(value: Any) -> str:
    if type(value) is not str or not value:
        _fail()
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_value(value: Any) -> str:
    return _sha256(_text(value))


def _hash64(value: Any) -> str:
    text = _text(value)
    if _SHA256_RE.fullmatch(text) is None:
        _fail()
    return text


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if type(value) is not list or any(
        not isinstance(item, Mapping) for item in value
    ):
        _fail()
    return value


def _project_evidence(
    run_id: str,
    rows: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    projected = []
    seen: set[str] = set()
    for row in rows:
        fingerprint = _hash64(row.get("evidence_fingerprint"))
        if fingerprint in seen:
            _fail()
        seen.add(fingerprint)
        if row.get("evidence_id") != f"ev_{run_id}_{fingerprint}":
            _fail()
        projected.append(
            {
                "evidence_fingerprint": fingerprint,
                "source_identity_sha256": _hash_value(
                    row.get("source_identity")
                ),
                "snippet_sha256": _hash_value(row.get("snippet")),
                "query_text_sha256": _hash_value(row.get("query_text")),
                "subagent_name": _text(row.get("subagent_name")),
                "tool_name": _text(row.get("tool_name")),
            }
        )
    return sorted(projected, key=lambda item: item["evidence_fingerprint"])


def _project_states(
    rows: list[Mapping[str, Any]],
    field: str,
) -> list[dict[str, str]]:
    key = (
        "citation_status"
        if field == "citation_status"
        else "verification_status"
    )
    return sorted(
        (
            {
                "evidence_fingerprint": _hash64(
                    row.get("evidence_fingerprint")
                ),
                key: _text(row.get(field)),
            }
            for row in rows
        ),
        key=lambda item: item["evidence_fingerprint"],
    )


def _project_artifacts(
    rows: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    projected = [
        {
            "artifact_id": _text(row.get("artifact_id")),
            "kind": _text(row.get("kind")),
            "media_type": _text(row.get("media_type")),
            "content_hash": _hash64(row.get("content_hash")),
        }
        for row in rows
    ]
    if len({row["artifact_id"] for row in projected}) != len(projected):
        _fail()
    return sorted(projected, key=lambda item: item["artifact_id"])


def _project_resolver(
    resolution: ResolvedRunResult | RunResultUnavailable,
    *,
    run_id: str,
) -> dict[str, Any]:
    if type(resolution) is ResolvedRunResult:
        if resolution.run_id != run_id:
            _fail()
        artifact = resolution.artifact
        if not isinstance(artifact, Mapping):
            _fail()
        return {
            "kind": "success",
            "execution_status": _text(resolution.execution_status),
            "delivery_status": _text(resolution.delivery_status),
            "artifact_id": _text(artifact.get("artifact_id")),
            "artifact_kind": _text(artifact.get("kind")),
            "artifact_media_type": _text(artifact.get("media_type")),
            "artifact_content_hash": _hash64(
                artifact.get("content_hash")
            ),
        }
    if type(resolution) is RunResultUnavailable:
        if (
            type(resolution.status_code) is not int
            or type(resolution.code) is not str
            or not resolution.code
        ):
            _fail()
        return {
            "kind": "error",
            "status_code": resolution.status_code,
            "code": resolution.code,
            "retryable": resolution.status_code == 409,
        }
    _fail()


def project_context_reliability_outcome(
    *,
    run: Mapping[str, Any],
    resolution: ResolvedRunResult | RunResultUnavailable,
) -> dict[str, Any]:
    """Validate and project one persisted application-owned run outcome."""

    if not isinstance(run, Mapping):
        _fail()
    run_id = _text(run.get("run_id"))
    query_sha256 = _hash_value(run.get("query"))
    evidence = _rows(run.get("evidence"))
    projection = {
        "query_sha256": query_sha256,
        "evidence": _project_evidence(run_id, evidence),
        "citation_states": _project_states(evidence, "citation_status"),
        "verification_states": _project_states(
            evidence,
            "verification_status",
        ),
        "artifacts": _project_artifacts(_rows(run.get("artifacts"))),
        "terminal": {
            "execution_status": _text(run.get("execution_status")),
            "review_status": _text(run.get("review_status")),
            "delivery_status": _text(run.get("delivery_status")),
        },
        "resolver": _project_resolver(resolution, run_id=run_id),
    }
    if any(
        row["query_text_sha256"] != query_sha256
        for row in projection["evidence"]
    ):
        _fail()
    return projection


def compare_context_reliability_outcomes(
    control: Mapping[str, Any],
    forced: Mapping[str, Any],
) -> list[str]:
    """Return stable finding codes for paired application projection drift."""

    if not isinstance(control, Mapping) or not isinstance(forced, Mapping):
        _fail()
    comparisons = (
        ("query_sha256", "context.query_changed"),
        ("evidence", "context.evidence_changed"),
        ("citation_states", "context.citation_state_changed"),
        ("verification_states", "context.verification_state_changed"),
        ("artifacts", "context.artifact_changed"),
        ("terminal", "context.terminal_state_changed"),
        ("resolver", "context.result_resolution_changed"),
    )
    expected_fields = {item[0] for item in comparisons}
    if set(control) != expected_fields or set(forced) != expected_fields:
        _fail()
    return [
        code
        for field, code in comparisons
        if control[field] != forced[field]
    ]
