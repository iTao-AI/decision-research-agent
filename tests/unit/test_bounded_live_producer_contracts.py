from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from api.run_failure_cause_models import RUN_FAILURE_CAUSE_CODES
from scripts.bounded_live_producer_contracts import (
    BOUNDARIES,
    LIMITS,
    MAX_DIAGNOSTIC_BYTES,
    CleanupStatus,
    CallBudgetDiagnosticReceipt,
    EvidenceBoundaryDiagnostic,
    EvidenceDiagnosticReason,
    EvidenceDiagnosticReceipt,
    EvidenceDiagnosticStage,
    ErrorEnvelope,
    EvaluationError,
    EvaluationValidationError,
    FailureCode,
    FailurePhase,
    LiveReportModel,
    ManifestModel,
    ObservedUsage,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticReceipt,
    ResultDiagnosticStage,
    RunFailureDiagnostic,
    RunFailureDiagnosticReceipt,
    load_manifest,
    render_markdown,
    serialize_error,
    serialize_call_budget_diagnostic,
    serialize_evidence_diagnostic,
    serialize_manifest,
    serialize_report,
    serialize_result_diagnostic,
    serialize_run_failure_diagnostic,
    validate_live_report,
)
from scripts.bounded_live_producer_runtime_diagnostics import parse_call_budget_sidecar


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    PROJECT_ROOT / "benchmarks" / "bounded-live-producer-v1" / "manifest.json"
)


def _safe_report() -> dict:
    return {
        "schema_version": "dra.bounded-live-producer-evaluation.v1",
        "status": "valid",
        "source": {
            "repository_name": "decision-research-agent",
            "service_name": "decision-research-agent",
            "version": "0.1.5",
            "source_commit": "a" * 40,
            "source_tree": "b" * 40,
            "archive_sha256": "c" * 64,
            "manifest_sha256": "d" * 64,
            "sanitized_compose_sha256": "e" * 64,
            "backend_image_id": "sha256:" + "f" * 64,
            "docker_version": "27.5.1",
            "compose_version": "2.32.4",
            "source_clean": True,
            "build_context": "tracked_archive",
        },
        "scenario": {
            "scenario_id": "cpython-313-free-threaded-pilot",
            "manifest_sha256": "d" * 64,
            "request_sha256": "1" * 64,
            "profile_id": "generic",
            "required_cited_domains": ["docs.python.org", "peps.python.org"],
            "provider_id": "operator-provider",
            "primary_model_id": "operator-primary",
            "fallback_model_id": "operator-primary",
        },
        "lifecycle": {
            "docker_probe_ms": 100,
            "build_start_ms": 200,
            "research_ms": 300,
            "restart_replay_ms": 400,
            "active_ms": 900,
            "cleanup_ms": 100,
            "total_ms": 1100,
            "loopback_binding_observed": True,
            "health_identity_observed": True,
        },
        "run": {
            "run_id": "run_" + "1" * 32,
            "thread_id": "bounded-live-thread-" + "2" * 32,
            "segment_id": "run_" + "1" * 32 + "_seg_000",
            "state_version": 2,
            "execution_status": "completed",
            "review_status": "not_required",
            "delivery_status": "ready",
            "failure_cause": None,
            "profile_id": "generic",
        },
        "result": {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "utf8_bytes": 128,
            "sha256": "3" * 64,
            "consumer_support": "supported",
            "consumer_disposition": "accept_draft",
        },
        "evidence": [
            {
                "evidence_id": "ev_docs",
                "source_url": "https://docs.python.org/3/whatsnew/3.13.html",
                "source_identity": "docs.python.org/cpython-313",
                "retrieved_at": "2026-07-18T00:00:00+00:00",
                "citation_status": "cited",
                "verification_status": "unverified",
            },
            {
                "evidence_id": "ev_pep",
                "source_url": "https://peps.python.org/pep-0703/",
                "source_identity": "peps.python.org/pep-0703",
                "retrieved_at": "2026-07-18T00:00:01+00:00",
                "citation_status": "cited",
                "verification_status": "unverified",
            },
        ],
        "usage": {
            "status": "observed",
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "call_count": 1,
            "cost_estimate": {"status": "not_observed"},
            "search_cost": {"status": "not_observed"},
        },
        "restart": {
            "same_run_identity": True,
            "same_thread_identity": True,
            "same_segment_identity": True,
            "state_version_non_regressing": True,
            "same_terminal_state": True,
            "same_evidence": True,
            "same_artifact": True,
            "same_consumer_disposition": True,
        },
        "replay": {
            "idempotent_replay": True,
            "same_run_identity": True,
            "same_thread_identity": True,
            "same_segment_identity": True,
            "unchanged_terminal_projection": True,
        },
        "cleanup": {
            "attempted": True,
            "succeeded": True,
            "zero_container_residue": True,
            "zero_volume_residue": True,
            "zero_network_residue": True,
            "zero_temp_residue": True,
        },
        "boundaries": dict(BOUNDARIES),
        "limits": list(LIMITS),
    }


def test_manifest_is_canonical_and_exact() -> None:
    raw = MANIFEST_PATH.read_bytes()
    manifest = load_manifest(MANIFEST_PATH)

    assert isinstance(manifest, ManifestModel)
    assert manifest.schema_version == "dra.bounded-live-producer-manifest.v1"
    assert manifest.profile_id == "generic"
    assert manifest.required_cited_domains == (
        "docs.python.org",
        "peps.python.org",
    )
    assert serialize_manifest(manifest) == raw


def test_manifest_is_frozen_and_strict() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    with pytest.raises(ValidationError):
        manifest.profile_id = "talent-hiring-signal"  # type: ignore[misc]

    payload = manifest.model_dump(mode="python")
    payload["bounds"]["query_utf8_bytes_min"] = True
    with pytest.raises(ValidationError):
        ManifestModel.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", ""),
        ("query", "line one\r\nline two"),
        ("required_cited_domains", ["Docs.Python.org"]),
        ("required_cited_domains", ["docs.python.org", "docs.python.org"]),
        ("required_cited_domains", ["127.0.0.1"]),
    ],
)
def test_manifest_rejects_invalid_query_or_domains(field: str, value: object) -> None:
    payload = load_manifest(MANIFEST_PATH).model_dump(mode="python")
    payload[field] = value
    with pytest.raises(ValidationError):
        ManifestModel.model_validate(payload, strict=True)


def test_manifest_rejects_scope_depth_and_node_overflow() -> None:
    payload = load_manifest(MANIFEST_PATH).model_dump(mode="python")
    payload["scope"] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}
    with pytest.raises(ValidationError):
        ManifestModel.model_validate(payload, strict=True)

    payload = load_manifest(MANIFEST_PATH).model_dump(mode="python")
    payload["scope"] = {str(index): index for index in range(257)}
    with pytest.raises(ValidationError):
        ManifestModel.model_validate(payload, strict=True)


def test_manifest_rejects_noncanonical_bytes(tmp_path: Path) -> None:
    candidate = tmp_path / "manifest.json"
    candidate.write_bytes(MANIFEST_PATH.read_bytes() + b"\n")
    with pytest.raises(EvaluationValidationError, match="manifest_invalid"):
        load_manifest(candidate)


def test_manifest_rejects_symlink(tmp_path: Path) -> None:
    candidate = tmp_path / "manifest.json"
    candidate.symlink_to(MANIFEST_PATH)
    with pytest.raises(EvaluationValidationError, match="manifest_invalid"):
        load_manifest(candidate)


def test_manifest_requires_change1_cost_to_remain_not_observed() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    assert manifest.usage_policy.cost_estimate == "not_observed"


def test_strict_usage_rejects_bool_as_integer() -> None:
    with pytest.raises(ValidationError):
        ObservedUsage.model_validate(
            {
                "status": "observed",
                "prompt_tokens": True,
                "completion_tokens": 1,
                "total_tokens": 2,
                "call_count": 1,
                "cost_estimate": {"status": "not_observed"},
                "search_cost": {"status": "not_observed"},
            },
            strict=True,
        )


def test_report_adapter_maps_usage_validation_to_stable_error() -> None:
    report = _safe_report()
    report["usage"]["prompt_tokens"] = True
    with pytest.raises(EvaluationValidationError, match="usage_invalid"):
        validate_live_report(report)


def test_live_report_is_strict_and_serializes_twice_identically() -> None:
    model = validate_live_report(_safe_report())
    assert isinstance(model, LiveReportModel)
    assert serialize_report(model) == serialize_report(model)
    assert render_markdown(model) == render_markdown(model)


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("result", "content"), "raw markdown", "report_invalid"),
        (("evidence", 0, "snippet"), "raw snippet", "evidence_invalid"),
        (("evidence", 0, "source_url"), "http://127.0.0.1/x", "evidence_invalid"),
        (("evidence", 0, "source_url"), "https://docs.python.org:444/x", "evidence_invalid"),
        (("source", "local_path"), "/tmp/archive", "report_invalid"),
        (("scenario", "query"), "raw query", "report_invalid"),
    ],
)
def test_report_rejects_unknown_or_unsafe_fields(
    path: tuple[object, ...], value: object, code: str
) -> None:
    report = deepcopy(_safe_report())
    target: object = report
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(EvaluationValidationError, match=code):
        validate_live_report(report)


@pytest.mark.parametrize(
    "amount",
    ["1", "1.0", "01.00000000", "NaN", "Infinity", "-1.00000000"],
)
def test_report_rejects_legacy_observed_cost_regardless_of_amount(amount: str) -> None:
    report = _safe_report()
    report["usage"]["cost_estimate"] = {
        "status": "observed",
        "amount": amount,
        "currency": "USD",
        "pricing_basis": "operator-pricing-v1",
        "estimate": True,
    }
    with pytest.raises(EvaluationValidationError, match="usage_invalid"):
        validate_live_report(report)


def test_report_rejects_observed_cost_in_change1() -> None:
    report = _safe_report()
    report["usage"]["cost_estimate"] = {
        "status": "observed",
        "amount": "0.01000000",
        "currency": "USD",
        "pricing_basis": "operator-pricing-v1",
        "estimate": True,
    }
    with pytest.raises(EvaluationValidationError, match="usage_invalid"):
        validate_live_report(report)


def test_report_requires_exact_boundaries_and_limits() -> None:
    report = _safe_report()
    report["boundaries"]["hosted_production_or_sla"] = "proven"
    with pytest.raises(EvaluationValidationError, match="report_invalid"):
        validate_live_report(report)

    report = _safe_report()
    report["limits"].reverse()
    with pytest.raises(EvaluationValidationError, match="report_invalid"):
        validate_live_report(report)


def test_error_registry_rejects_cross_phase_code() -> None:
    with pytest.raises(ValueError, match="evaluation_error_invalid"):
        EvaluationError(
            code=FailureCode.SOURCE_DIRTY,
            phase=FailurePhase.DOCKER,
            retryable=False,
        )


def test_error_serialization_is_exact_and_safe() -> None:
    error = EvaluationError(
        code=FailureCode.SOURCE_DIRTY,
        phase=FailurePhase.INPUT,
        retryable=False,
        cleanup_status=CleanupStatus.NOT_STARTED,
    )
    raw = serialize_error(error)
    assert raw.endswith(b"\n")
    envelope = ErrorEnvelope.model_validate_json(raw, strict=True)
    assert envelope.model_dump(mode="json") == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "source_dirty",
        "phase": "input",
        "retryable": False,
        "cleanup_status": "not_started",
    }
    assert b"Traceback" not in raw


VALID_DIAGNOSTIC_PAIRS = {
    "connection": {"connection_failed"},
    "response_status": {"response_status_invalid"},
    "response_body": {"response_read_failed", "response_size_exceeded"},
    "response_json": {
        "response_utf8_invalid",
        "response_json_invalid",
        "response_not_object",
    },
    "response_identity": {"run_identity_mismatch"},
    "consumer_contract": {"contract_result_invalid", "contract_schema_invalid"},
    "projection_disposition": {"projection_disposition_invalid"},
}

EVIDENCE_DIAGNOSTIC_PAIRS = (
    ("status_projection", "row_count_exceeded"),
    ("status_projection", "row_shape_invalid"),
    ("status_projection", "ownership_invalid"),
    ("consumer_contract", "required_fields_invalid"),
    ("consumer_contract", "evidence_id_invalid"),
    ("consumer_contract", "evidence_id_duplicate"),
    ("consumer_contract", "source_identity_invalid"),
    ("consumer_contract", "source_url_invalid"),
    ("consumer_contract", "retrieved_at_invalid"),
    ("consumer_contract", "citation_status_invalid"),
    ("consumer_contract", "verification_status_invalid"),
    ("receipt_contract", "source_url_required"),
    ("receipt_contract", "source_url_policy_invalid"),
    ("receipt_contract", "source_identity_too_long"),
    ("receipt_contract", "retrieved_at_too_long"),
)

_EVIDENCE_DIAGNOSTIC_REASON_STAGE = {
    reason: stage for stage, reason in EVIDENCE_DIAGNOSTIC_PAIRS
}


def _evidence_diagnostic() -> EvidenceBoundaryDiagnostic:
    return EvidenceBoundaryDiagnostic(
        stage=EvidenceDiagnosticStage.RECEIPT_CONTRACT,
        reason=EvidenceDiagnosticReason.SOURCE_URL_POLICY_INVALID,
    )


@pytest.mark.parametrize(("stage", "reason"), EVIDENCE_DIAGNOSTIC_PAIRS)
def test_evidence_diagnostic_accepts_only_registered_pairs(
    stage: str, reason: str
) -> None:
    diagnostic = EvidenceBoundaryDiagnostic(
        stage=EvidenceDiagnosticStage(stage),
        reason=EvidenceDiagnosticReason(reason),
    )

    assert diagnostic.model_dump(mode="json") == {"stage": stage, "reason": reason}


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        (stage, reason)
        for stage in ("status_projection", "consumer_contract", "receipt_contract")
        for reason in _EVIDENCE_DIAGNOSTIC_REASON_STAGE
        if _EVIDENCE_DIAGNOSTIC_REASON_STAGE[reason] != stage
    ],
)
def test_evidence_diagnostic_rejects_every_cross_stage_pair(
    stage: str, reason: str
) -> None:
    with pytest.raises(ValidationError, match="evidence_diagnostic_pair_invalid"):
        EvidenceBoundaryDiagnostic(
            stage=EvidenceDiagnosticStage(stage),
            reason=EvidenceDiagnosticReason(reason),
        )


def test_evidence_diagnostic_receipt_has_exact_canonical_bytes() -> None:
    error = EvaluationError(
        "evidence_invalid",
        "evidence",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_evidence_diagnostic(),
    )

    raw = serialize_evidence_diagnostic(error)

    assert raw == (
        b'{"evidence_boundary":{"reason":"source_url_policy_invalid",'
        b'"stage":"receipt_contract"},"primary":{"cleanup_status":"succeeded",'
        b'"code":"evidence_invalid","phase":"evidence","retryable":false},'
        b'"schema_version":"dra.bounded-live-producer-evidence-diagnostic.v1"}\n'
    )
    assert len(raw) <= MAX_DIAGNOSTIC_BYTES
    assert all(
        marker not in raw
        for marker in (
            b'"query"',
            b'"content"',
            b'"raw_error"',
            b'"traceback"',
            b'"local_path"',
            b'"api_key"',
            b"/Users/",
            b"/private/",
            b"Traceback",
            b"OPENAI_API_KEY",
        )
    )


@pytest.mark.parametrize(
    "cleanup_status", [CleanupStatus.SUCCEEDED, CleanupStatus.FAILED]
)
def test_evidence_diagnostic_accepts_only_final_cleanup_status(
    cleanup_status: CleanupStatus,
) -> None:
    error = EvaluationError(
        "evidence_invalid",
        "evidence",
        False,
        cleanup_status,
        diagnostic=_evidence_diagnostic(),
    )

    receipt = EvidenceDiagnosticReceipt.model_validate_json(
        serialize_evidence_diagnostic(error), strict=True
    )
    assert receipt.primary.cleanup_status is cleanup_status


def test_evidence_diagnostic_rejects_not_started_cleanup() -> None:
    error = EvaluationError(
        "evidence_invalid",
        "evidence",
        False,
        diagnostic=_evidence_diagnostic(),
    )

    with pytest.raises(ValidationError):
        serialize_evidence_diagnostic(error)


@pytest.mark.parametrize("missing_field", ["stage", "reason"])
def test_evidence_diagnostic_requires_every_boundary_field(
    missing_field: str,
) -> None:
    payload = _evidence_diagnostic().model_dump(mode="python")
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        EvidenceBoundaryDiagnostic.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "missing_field", ["schema_version", "primary", "evidence_boundary"]
)
def test_evidence_diagnostic_receipt_requires_every_top_level_field(
    missing_field: str,
) -> None:
    payload = {
        "schema_version": "dra.bounded-live-producer-evidence-diagnostic.v1",
        "primary": {
            "code": "evidence_invalid",
            "phase": "evidence",
            "retryable": False,
            "cleanup_status": "succeeded",
        },
        "evidence_boundary": {
            "stage": "receipt_contract",
            "reason": "source_url_policy_invalid",
        },
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        EvidenceDiagnosticReceipt.model_validate(payload)


@pytest.mark.parametrize(
    "missing_field", ["code", "phase", "retryable", "cleanup_status"]
)
def test_evidence_diagnostic_receipt_requires_every_primary_field(
    missing_field: str,
) -> None:
    payload = {
        "schema_version": "dra.bounded-live-producer-evidence-diagnostic.v1",
        "primary": {
            "code": "evidence_invalid",
            "phase": "evidence",
            "retryable": False,
            "cleanup_status": "succeeded",
        },
        "evidence_boundary": {
            "stage": "receipt_contract",
            "reason": "source_url_policy_invalid",
        },
    }
    payload["primary"].pop(missing_field)

    with pytest.raises(ValidationError):
        EvidenceDiagnosticReceipt.model_validate(payload)


def test_evidence_diagnostic_is_strict_frozen_and_forbids_extra_fields() -> None:
    diagnostic = _evidence_diagnostic()
    with pytest.raises(ValidationError):
        diagnostic.reason = EvidenceDiagnosticReason.SOURCE_URL_REQUIRED  # type: ignore[misc]

    payload = diagnostic.model_dump(mode="python")
    payload["raw_evidence"] = "private"
    with pytest.raises(ValidationError):
        EvidenceBoundaryDiagnostic.model_validate(payload, strict=True)

    payload = diagnostic.model_dump(mode="python")
    payload["stage"] = 1
    with pytest.raises(ValidationError):
        EvidenceBoundaryDiagnostic.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("code", "phase"),
    [
        ("evidence_invalid", "result"),
        ("consumer_projection_invalid", "evidence"),
        ("run_failed", "observe"),
    ],
)
def test_evidence_diagnostic_rejects_ineligible_primary(
    code: str, phase: str
) -> None:
    with pytest.raises(ValueError, match="evaluation_error_invalid"):
        EvaluationError(code, phase, False, diagnostic=_evidence_diagnostic())


def test_default_public_error_bytes_ignore_evidence_diagnostic() -> None:
    baseline = EvaluationError(
        "evidence_invalid", "evidence", False, CleanupStatus.SUCCEEDED
    )
    enriched = EvaluationError(
        "evidence_invalid",
        "evidence",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_evidence_diagnostic(),
    )

    assert serialize_error(enriched) == serialize_error(baseline)


def test_evidence_diagnostic_compatibility_preserves_existing_receipt_bytes() -> None:
    result_error = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )
    run_error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.FAILED,
        diagnostic=_run_failure_diagnostic(),
    )
    budget_error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_run_failure_diagnostic(code="call_budget_exceeded"),
    )
    limiter = parse_call_budget_sidecar(
        {
            "schema_version": "dra.call-budget-origin-sidecar.v1",
            "limiter": {
                "limiter_kind": "model",
                "tool_scope": "not_applicable",
                "run_count": 40,
                "run_limit": 40,
                "thread_count": 40,
                "thread_limit": None,
                "agent_role": "not_observed",
            },
        }
    ).limiter

    assert serialize_result_diagnostic(result_error) == (
        b'{"primary":{"cleanup_status":"succeeded","code":'
        b'"consumer_projection_invalid","phase":"result","retryable":false},'
        b'"result_boundary":{"http_status":200,"reason":'
        b'"contract_result_invalid","response_bytes":1234,"stage":'
        b'"consumer_contract"},"schema_version":'
        b'"dra.bounded-live-producer-result-diagnostic.v1"}\n'
    )
    assert serialize_run_failure_diagnostic(run_error) == (
        b'{"primary":{"cleanup_status":"failed","code":"run_failed",'
        b'"phase":"observe","retryable":false},"run_failure":'
        b'{"cause_schema_version":"dra.run-failure-cause.v1","code":'
        b'"execution_error","observation_status":"observed","phase":'
        b'"execution"},"schema_version":'
        b'"dra.bounded-live-producer-run-failure-diagnostic.v1"}\n'
    )
    assert serialize_call_budget_diagnostic(budget_error, limiter) == (
        b'{"limiter":{"agent_role":"not_observed","limiter_kind":"model",'
        b'"run_count":40,"run_limit":40,"thread_count":40,"thread_limit":null,'
        b'"tool_scope":"not_applicable"},"primary":{"cleanup_status":"succeeded",'
        b'"code":"run_failed","phase":"observe","retryable":false},"run_failure":'
        b'{"cause_schema_version":"dra.run-failure-cause.v1","code":'
        b'"call_budget_exceeded","observation_status":"observed","phase":"execution"},'
        b'"schema_version":"dra.bounded-live-producer-call-budget-diagnostic.v1"}\n'
    )


def _diagnostic() -> ResultBoundaryDiagnostic:
    return ResultBoundaryDiagnostic(
        stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
        reason=ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
        http_status=200,
        response_bytes=1234,
    )


def test_result_diagnostic_receipt_is_strict_exact_and_bounded() -> None:
    error = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )

    raw = serialize_result_diagnostic(error)
    receipt = ResultDiagnosticReceipt.model_validate_json(raw, strict=True)

    assert len(raw) <= MAX_DIAGNOSTIC_BYTES
    assert receipt.model_dump(mode="json") == {
        "schema_version": "dra.bounded-live-producer-result-diagnostic.v1",
        "primary": {
            "code": "consumer_projection_invalid",
            "phase": "result",
            "retryable": False,
            "cleanup_status": "succeeded",
        },
        "result_boundary": {
            "stage": "consumer_contract",
            "reason": "contract_result_invalid",
            "http_status": 200,
            "response_bytes": 1234,
        },
    }


def test_default_public_error_bytes_ignore_internal_diagnostic() -> None:
    baseline = EvaluationError(
        "consumer_projection_invalid", "result", False, CleanupStatus.SUCCEEDED
    )
    enriched = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )

    assert serialize_error(enriched) == serialize_error(baseline)


def _run_failure_diagnostic(
    *, phase: str = "execution", code: str = "execution_error"
) -> RunFailureDiagnostic:
    return RunFailureDiagnostic(
        cause_schema_version="dra.run-failure-cause.v1",
        observation_status="observed",
        phase=phase,
        code=code,
    )


@pytest.mark.parametrize(
    ("phase", "code"),
    [
        (phase, code)
        for phase, codes in RUN_FAILURE_CAUSE_CODES.items()
        for code in sorted(codes)
    ],
)
def test_run_failure_diagnostic_reuses_application_pairs(
    phase: str, code: str
) -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_run_failure_diagnostic(phase=phase, code=code),
    )

    raw = serialize_run_failure_diagnostic(error)
    receipt = RunFailureDiagnosticReceipt.model_validate_json(raw, strict=True)

    assert receipt.run_failure.phase == phase
    assert receipt.run_failure.code == code
    assert len(raw) <= MAX_DIAGNOSTIC_BYTES


def test_run_failure_diagnostic_has_exact_canonical_bytes() -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.FAILED,
        diagnostic=_run_failure_diagnostic(),
    )

    assert serialize_run_failure_diagnostic(error) == (
        b'{"primary":{"cleanup_status":"failed","code":"run_failed",'
        b'"phase":"observe","retryable":false},"run_failure":'
        b'{"cause_schema_version":"dra.run-failure-cause.v1","code":'
        b'"execution_error","observation_status":"observed","phase":'
        b'"execution"},"schema_version":'
        b'"dra.bounded-live-producer-run-failure-diagnostic.v1"}\n'
    )


def test_call_budget_receipt_has_exact_canonical_bytes_and_old_receipts_are_unchanged() -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_run_failure_diagnostic(code="call_budget_exceeded"),
    )
    limiter = parse_call_budget_sidecar(
        {
            "schema_version": "dra.call-budget-origin-sidecar.v1",
            "limiter": {
                "limiter_kind": "model",
                "tool_scope": "not_applicable",
                "run_count": 40,
                "run_limit": 40,
                "thread_count": 40,
                "thread_limit": None,
                "agent_role": "not_observed",
            },
        }
    ).limiter

    raw = serialize_call_budget_diagnostic(error, limiter)
    receipt = CallBudgetDiagnosticReceipt.model_validate_json(raw, strict=True)

    assert receipt.limiter == limiter
    assert raw == (
        b'{"limiter":{"agent_role":"not_observed","limiter_kind":"model",'
        b'"run_count":40,"run_limit":40,"thread_count":40,"thread_limit":null,'
        b'"tool_scope":"not_applicable"},"primary":{"cleanup_status":"succeeded",'
        b'"code":"run_failed","phase":"observe","retryable":false},"run_failure":'
        b'{"cause_schema_version":"dra.run-failure-cause.v1","code":'
        b'"call_budget_exceeded","observation_status":"observed","phase":"execution"},'
        b'"schema_version":"dra.bounded-live-producer-call-budget-diagnostic.v1"}\n'
    )

@pytest.mark.parametrize(
    "cleanup_status", [CleanupStatus.SUCCEEDED, CleanupStatus.FAILED]
)
def test_run_failure_diagnostic_accepts_only_final_cleanup_status(
    cleanup_status: CleanupStatus,
) -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        cleanup_status,
        diagnostic=_run_failure_diagnostic(),
    )

    receipt = RunFailureDiagnosticReceipt.model_validate_json(
        serialize_run_failure_diagnostic(error), strict=True
    )
    assert receipt.primary.cleanup_status is cleanup_status


def test_run_failure_diagnostic_rejects_not_started_cleanup() -> None:
    error = EvaluationError(
        "run_failed",
        "observe",
        False,
        diagnostic=_run_failure_diagnostic(),
    )

    with pytest.raises(ValidationError):
        serialize_run_failure_diagnostic(error)


def test_run_failure_diagnostic_is_strict_frozen_and_forbids_extra_fields() -> None:
    diagnostic = _run_failure_diagnostic()
    with pytest.raises(ValidationError):
        diagnostic.code = "run_timeout"  # type: ignore[misc]

    payload = diagnostic.model_dump(mode="python")
    payload["recorded_at"] = "2026-07-22T00:00:00Z"
    with pytest.raises(ValidationError):
        RunFailureDiagnostic.model_validate(payload, strict=True)

    payload = diagnostic.model_dump(mode="python")
    payload["phase"] = 1
    with pytest.raises(ValidationError):
        RunFailureDiagnostic.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "field", ["cause_schema_version", "observation_status", "phase", "code"]
)
def test_run_failure_diagnostic_requires_every_exact_field(field: str) -> None:
    payload = _run_failure_diagnostic().model_dump(mode="python")
    payload.pop(field)

    with pytest.raises(ValidationError):
        RunFailureDiagnostic.model_validate(payload, strict=True)


def test_run_failure_diagnostic_rejects_cross_phase_pair_and_unsafe_code() -> None:
    for code in ("run_finalization_failed", "execution_error\nraw"):
        with pytest.raises(ValidationError):
            RunFailureDiagnostic(
                cause_schema_version="dra.run-failure-cause.v1",
                observation_status="observed",
                phase="execution",
                code=code,
            )


@pytest.mark.parametrize(
    ("code", "phase"),
    [
        ("run_failed", "result"),
        ("run_state_invalid", "observe"),
        ("consumer_projection_invalid", "result"),
    ],
)
def test_run_failure_diagnostic_rejects_ineligible_primary(
    code: str, phase: str
) -> None:
    with pytest.raises(ValueError, match="evaluation_error_invalid"):
        EvaluationError(
            code,
            phase,
            False,
            diagnostic=_run_failure_diagnostic(),
        )


def test_default_public_error_bytes_ignore_run_failure_diagnostic() -> None:
    baseline = EvaluationError(
        "run_failed", "observe", False, CleanupStatus.SUCCEEDED
    )
    enriched = EvaluationError(
        "run_failed",
        "observe",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_run_failure_diagnostic(),
    )

    assert serialize_error(enriched) == serialize_error(baseline)


def test_result_diagnostic_compatibility_bytes_are_unchanged() -> None:
    error = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )

    assert serialize_result_diagnostic(error) == (
        b'{"primary":{"cleanup_status":"succeeded","code":'
        b'"consumer_projection_invalid","phase":"result","retryable":false},'
        b'"result_boundary":{"http_status":200,"reason":'
        b'"contract_result_invalid","response_bytes":1234,"stage":'
        b'"consumer_contract"},"schema_version":'
        b'"dra.bounded-live-producer-result-diagnostic.v1"}\n'
    )


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        (stage, reason)
        for stage, reasons in VALID_DIAGNOSTIC_PAIRS.items()
        for reason in reasons
    ],
)
def test_result_diagnostic_accepts_only_registered_pairs(stage: str, reason: str) -> None:
    diagnostic = ResultBoundaryDiagnostic(
        stage=ResultDiagnosticStage(stage),
        reason=ResultDiagnosticReason(reason),
        http_status=None,
        response_bytes=None,
    )

    assert diagnostic.stage.value == stage
    assert diagnostic.reason.value == reason


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        ("connection", "response_status_invalid"),
        ("response_status", "connection_failed"),
        ("response_body", "response_json_invalid"),
        ("consumer_contract", "projection_disposition_invalid"),
    ],
)
def test_result_diagnostic_rejects_cross_stage_pairs(stage: str, reason: str) -> None:
    with pytest.raises(ValidationError):
        ResultBoundaryDiagnostic(
            stage=ResultDiagnosticStage(stage),
            reason=ResultDiagnosticReason(reason),
            http_status=None,
            response_bytes=None,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("http_status", True),
        ("http_status", 99),
        ("http_status", 600),
        ("response_bytes", True),
        ("response_bytes", -1),
        ("response_bytes", 2_097_153),
    ],
)
def test_result_diagnostic_rejects_invalid_integer_bounds(
    field: str, value: object
) -> None:
    payload = {
        "stage": "connection",
        "reason": "connection_failed",
        "http_status": None,
        "response_bytes": None,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ResultBoundaryDiagnostic.model_validate(payload, strict=True)


def test_result_diagnostic_models_are_frozen_and_forbid_extra_or_raw_fields() -> None:
    diagnostic = _diagnostic()
    with pytest.raises(ValidationError):
        diagnostic.reason = ResultDiagnosticReason.CONTRACT_SCHEMA_INVALID  # type: ignore[misc]

    payload = diagnostic.model_dump(mode="python")
    payload["raw_response"] = "private payload"
    with pytest.raises(ValidationError):
        ResultBoundaryDiagnostic.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("code", "phase"),
    [
        ("artifact_invalid", "result"),
        ("consumer_projection_invalid", "observe"),
    ],
)
def test_result_diagnostic_rejects_ineligible_primary(code: str, phase: str) -> None:
    with pytest.raises(ValueError, match="evaluation_error_invalid"):
        EvaluationError(code, phase, False, diagnostic=_diagnostic())


def test_result_diagnostic_rejects_non_contract_metadata_and_missing_metadata() -> None:
    with pytest.raises(ValueError, match="evaluation_error_invalid"):
        EvaluationError(
            "consumer_projection_invalid",
            "result",
            False,
            diagnostic={"raw": "payload"},  # type: ignore[arg-type]
        )
    with pytest.raises(EvaluationValidationError, match="diagnostic_invalid"):
        serialize_result_diagnostic(
            EvaluationError("consumer_projection_invalid", "result", False)
        )


def test_result_diagnostic_contract_import_is_silent() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import scripts.bounded_live_producer_contracts"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_report_size_bound_is_enforced() -> None:
    report = _safe_report()
    report["source"]["docker_version"] = "x" * 1_048_576
    with pytest.raises(EvaluationValidationError, match="report_invalid"):
        validate_live_report(report)
