"""Offline downstream-consumer compatibility proof."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "dra.downstream-consumer.v1"
FIXTURE_TIMESTAMP = "2026-07-11T00:00:00+00:00"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_FIXTURE_BYTES = 2 * 1024 * 1024

EXECUTION_STATUSES = {
    "pending",
    "running",
    "completed",
    "completed_with_fallback",
    "failed",
}
REVIEW_STATUSES = {"not_required", "required", "resolved"}
DELIVERY_STATUSES = {
    "pending",
    "ready",
    "review_required",
    "blocked",
    "failed",
}
EVIDENCE_KEYS = {
    "evidence_id",
    "source_url",
    "source_identity",
    "retrieved_at",
    "citation_status",
    "verification_status",
}
CANONICAL_KIND = "research_report_markdown"
FALLBACK_KIND = "research_report_fallback_markdown"

STATE_DISPOSITIONS = {
    ("pending", "not_required", "pending"): ("supported", "wait"),
    ("running", "not_required", "pending"): ("supported", "wait"),
    ("completed", "not_required", "ready"): ("supported", "accept_draft"),
    ("completed_with_fallback", "not_required", "ready"): (
        "partial",
        "block_fallback",
    ),
    ("completed", "required", "review_required"): (
        "supported",
        "await_review",
    ),
    ("completed", "resolved", "blocked"): ("supported", "block"),
    ("failed", "not_required", "failed"): ("supported", "block"),
}

SUPPORTED_CAPABILITIES = [
    "run_state",
    "run_level_evidence",
    "generic_canonical_artifact",
    "fallback_distinction",
    "review_and_delivery_gates",
    "stable_result_errors",
]
PARTIAL_CAPABILITIES = [
    "retrieved_at_is_not_source_as_of",
    "fallback_content_is_not_canonical",
    "completed_with_fallback_is_compatibility_only",
]
UNKNOWN_CAPABILITIES = [
    "claim_level_evidence_refs",
    "typed_limitations",
    "typed_conflicts_and_gaps",
    "source_title_publisher_and_effective_date",
    "persistent_failure_cause",
    "persistent_usage_cost",
]

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_CASE_KEYS = {"case_id", "profile_id", "run", "evidence", "result", "expected"}
_RUN_KEYS = {
    "run_id",
    "execution_status",
    "review_status",
    "delivery_status",
    "state_version",
}
_RESULT_KEYS = {"http_status", "body"}
_EXPECTED_KEYS = {"support", "disposition"}
_ARTIFACT_KEYS = {"artifact_id", "kind", "media_type", "content", "content_hash"}


class ContractValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise ContractValidationError(code)


def _require_exact_keys(value: object, expected: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        _fail(code)
    return value


def _identifier(value: object, code: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        _fail(code)
    return value


def _state(status: dict[str, Any]) -> tuple[str, str, str]:
    execution = status.get("execution_status")
    review = status.get("review_status")
    delivery = status.get("delivery_status")
    if execution not in EXECUTION_STATUSES:
        _fail("contract_state_invalid")
    if review not in REVIEW_STATUSES or delivery not in DELIVERY_STATUSES:
        _fail("contract_state_invalid")
    state = (execution, review, delivery)
    if state not in STATE_DISPOSITIONS:
        _fail("contract_state_invalid")
    return state


def _validate_artifact(value: object) -> dict[str, Any]:
    artifact = _require_exact_keys(value, _ARTIFACT_KEYS, "contract_artifact_invalid")
    if artifact["artifact_id"] != "research-report.md":
        _fail("contract_artifact_invalid")
    if artifact["kind"] not in {CANONICAL_KIND, FALLBACK_KIND}:
        _fail("contract_artifact_invalid")
    if artifact["media_type"] != "text/markdown":
        _fail("contract_artifact_invalid")
    content = artifact["content"]
    if (
        not isinstance(content, str)
        or not content.strip()
        or len(content.encode("utf-8")) > MAX_ARTIFACT_BYTES
    ):
        _fail("contract_artifact_invalid")
    content_hash = artifact["content_hash"]
    if (
        not isinstance(content_hash, str)
        or not _SHA256_RE.fullmatch(content_hash)
        or hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash
    ):
        _fail("contract_artifact_invalid")
    return artifact


def _validate_evidence_rows(value: object, *, exact: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail("contract_evidence_invalid")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            _fail("contract_evidence_invalid")
        if exact and set(raw) != EVIDENCE_KEYS:
            _fail("contract_evidence_invalid")
        if not EVIDENCE_KEYS.issubset(raw):
            _fail("contract_evidence_invalid")
        evidence_id = _identifier(raw["evidence_id"], "contract_evidence_invalid")
        if evidence_id in seen:
            _fail("contract_evidence_invalid")
        seen.add(evidence_id)
        source_identity = raw["source_identity"]
        if not isinstance(source_identity, str) or not source_identity.strip():
            _fail("contract_evidence_invalid")
        source_url = raw["source_url"]
        if source_url is not None:
            if not isinstance(source_url, str):
                _fail("contract_evidence_invalid")
            parsed = urlsplit(source_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username:
                _fail("contract_evidence_invalid")
        for key in ("retrieved_at", "citation_status", "verification_status"):
            if not isinstance(raw[key], str) or not raw[key]:
                _fail("contract_evidence_invalid")
        rows.append({key: raw[key] for key in sorted(EVIDENCE_KEYS)})
    return rows


def _expected_error(state: tuple[str, str, str]) -> tuple[int, str]:
    execution, _, delivery = state
    if execution in {"pending", "running"}:
        return 409, "run_not_terminal"
    if execution == "failed":
        return 409, "run_failed"
    if delivery == "review_required":
        return 409, "run_review_required"
    if delivery == "blocked":
        return 409, "run_delivery_blocked"
    return 409, "run_result_unavailable"


def _validate_result(
    *,
    state: tuple[str, str, str],
    run_id: str,
    http_status: object,
    body: object,
) -> tuple[dict[str, Any], tuple[str, str]]:
    if not isinstance(body, dict) or not isinstance(http_status, int):
        _fail("contract_result_invalid")
    support, disposition = STATE_DISPOSITIONS[state]
    if http_status == 200:
        if state not in {
            ("completed", "not_required", "ready"),
            ("completed_with_fallback", "not_required", "ready"),
        }:
            _fail("contract_result_invalid")
        result = _require_exact_keys(
            body,
            {"run_id", "execution_status", "delivery_status", "artifact"},
            "contract_result_invalid",
        )
        if (
            result["run_id"] != run_id
            or result["execution_status"] != state[0]
            or result["delivery_status"] != state[2]
        ):
            _fail("contract_result_invalid")
        artifact = _validate_artifact(result["artifact"])
        if state[0] == "completed_with_fallback" and artifact["kind"] != FALLBACK_KIND:
            _fail("contract_artifact_invalid")
        if artifact["kind"] == FALLBACK_KIND:
            support, disposition = "partial", "block_fallback"
        return dict(result), (support, disposition)

    expected_status, expected_code = _expected_error(state)
    if http_status != expected_status or body.get("code") != expected_code:
        _fail("contract_result_invalid")
    if body.get("run_id") != run_id:
        _fail("contract_result_invalid")
    return dict(body), (support, disposition)


def project_consumer_case(
    *,
    case_id: str,
    status_payload: dict[str, Any],
    result_http_status: int,
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    case_id = _identifier(case_id, "contract_schema_invalid")
    if not isinstance(status_payload, dict):
        _fail("contract_state_invalid")
    run_id = _identifier(status_payload.get("run_id"), "contract_state_invalid")
    profile_id = _identifier(status_payload.get("profile_id"), "contract_state_invalid")
    state_version = status_payload.get("state_version")
    if isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 0:
        _fail("contract_state_invalid")
    state = _state(status_payload)
    result, expected = _validate_result(
        state=state,
        run_id=run_id,
        http_status=result_http_status,
        body=result_payload,
    )
    evidence = _validate_evidence_rows(status_payload.get("evidence"), exact=False)
    return {
        "case_id": case_id,
        "profile_id": profile_id,
        "run": {
            "run_id": run_id,
            "execution_status": state[0],
            "review_status": state[1],
            "delivery_status": state[2],
            "state_version": state_version,
        },
        "evidence": evidence,
        "result": {"http_status": result_http_status, "body": result},
        "expected": {"support": expected[0], "disposition": expected[1]},
    }


def _assert_public_safe(payload: object) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    lowered = serialized.lower()
    forbidden = ("/users/", "/private/", "traceback", "checkpoint", "api_key=", "secret=")
    if any(marker in lowered for marker in forbidden):
        _fail("contract_file_invalid")


def validate_fixture_bundle(payload: Any) -> dict[str, Any]:
    root = _require_exact_keys(
        payload,
        {"schema_version", "service", "capabilities", "cases"},
        "contract_schema_invalid",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        _fail("contract_schema_unsupported")
    service = _require_exact_keys(
        root["service"],
        {"name", "health", "status_endpoint", "result_endpoint"},
        "contract_schema_invalid",
    )
    if service != {
        "name": "decision-research-agent",
        "health": {"status": "ok", "service": "decision-research-agent"},
        "status_endpoint": "/api/runs/{run_id}",
        "result_endpoint": "/api/runs/{run_id}/result",
    }:
        _fail("contract_schema_invalid")
    capabilities = _require_exact_keys(
        root["capabilities"], {"supported", "partial", "unknown"}, "contract_schema_invalid"
    )
    if capabilities != {
        "supported": SUPPORTED_CAPABILITIES,
        "partial": PARTIAL_CAPABILITIES,
        "unknown": UNKNOWN_CAPABILITIES,
    }:
        _fail("contract_schema_invalid")
    if not isinstance(root["cases"], list) or not root["cases"]:
        _fail("contract_schema_invalid")
    seen: set[str] = set()
    for raw_case in root["cases"]:
        case = _require_exact_keys(raw_case, _CASE_KEYS, "contract_schema_invalid")
        case_id = _identifier(case["case_id"], "contract_schema_invalid")
        if case_id in seen:
            _fail("contract_schema_invalid")
        seen.add(case_id)
        _identifier(case["profile_id"], "contract_schema_invalid")
        run = _require_exact_keys(case["run"], _RUN_KEYS, "contract_schema_invalid")
        if case["profile_id"] == "":
            _fail("contract_schema_invalid")
        state_version = run["state_version"]
        if isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 0:
            _fail("contract_state_invalid")
        run_id = _identifier(run["run_id"], "contract_state_invalid")
        state = _state(run)
        evidence = _validate_evidence_rows(case["evidence"], exact=True)
        result = _require_exact_keys(case["result"], _RESULT_KEYS, "contract_result_invalid")
        _, expected = _validate_result(
            state=state,
            run_id=run_id,
            http_status=result["http_status"],
            body=result["body"],
        )
        expected_payload = _require_exact_keys(
            case["expected"], _EXPECTED_KEYS, "contract_schema_invalid"
        )
        if expected_payload != {"support": expected[0], "disposition": expected[1]}:
            _fail("contract_state_invalid")
        if evidence != case["evidence"]:
            _fail("contract_evidence_invalid")
    _assert_public_safe(root)
    return root


def serialize_fixture(payload: dict[str, object]) -> bytes:
    validate_fixture_bundle(payload)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
