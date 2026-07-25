from __future__ import annotations

from copy import deepcopy

import pytest

from api.run_result_service import ResolvedRunResult, RunResultUnavailable
from scripts.agent_evaluation_context import (
    CONTEXT_RELIABILITY_FINDING_CODES,
    ContextProjectionError,
    compare_context_reliability_outcomes,
    project_context_reliability_outcome,
)


RUN_ID = "run_control"
FINGERPRINT = "a" * 64


def _persisted_run(run_id: str = RUN_ID) -> dict:
    return {
        "run_id": run_id,
        "thread_id": f"thread_{run_id}",
        "query": "Compare the fixed synthetic context scenario.",
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "evidence": [
            {
                "evidence_id": f"ev_{run_id}_{FINGERPRINT}",
                "run_id": run_id,
                "segment_id": f"{run_id}_seg_000",
                "query_text": "Compare the fixed synthetic context scenario.",
                "subagent_name": "network_search",
                "tool_name": "internet_search",
                "source_url": "https://example.com/context-source",
                "source_identity": "https://example.com/context-source",
                "snippet": "Bounded synthetic source content.",
                "evidence_fingerprint": FINGERPRINT,
                "retrieved_at": "2026-07-25T00:00:00+00:00",
                "tool_call_id": "call-search",
                "citation_status": "cited",
                "verification_status": "unverified",
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        ],
        "artifacts": [
            {
                "artifact_id": "research-report.md",
                "kind": "research_report_markdown",
                "media_type": "text/markdown",
                "content_hash": "b" * 64,
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        ],
    }


def _resolved(run_id: str = RUN_ID) -> ResolvedRunResult:
    return ResolvedRunResult(
        run_id=run_id,
        execution_status="completed",
        delivery_status="ready",
        artifact={
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": "# Context report\n",
            "content_hash": "b" * 64,
        },
    )


def test_projects_public_safe_application_owned_outcome() -> None:
    projection = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )

    assert list(projection) == [
        "query_sha256",
        "evidence",
        "citation_states",
        "verification_states",
        "artifacts",
        "terminal",
        "resolver",
    ]
    assert projection["evidence"] == [
        {
            "evidence_fingerprint": FINGERPRINT,
            "source_identity_sha256": (
                "8cdc94c2e55df45f640d870fe7bd4a3e4d1371da4fe6f1bdeede230a6aef4a9d"
            ),
            "snippet_sha256": (
                "205037cf11e5846fa027bbb64c6c18cfb980a34f3cdcb00792dca5b8ba40e96a"
            ),
            "query_text_sha256": projection["query_sha256"],
            "subagent_name": "network_search",
            "tool_name": "internet_search",
        }
    ]
    assert projection["citation_states"] == [
        {
            "evidence_fingerprint": FINGERPRINT,
            "citation_status": "cited",
        }
    ]
    assert projection["verification_states"] == [
        {
            "evidence_fingerprint": FINGERPRINT,
            "verification_status": "unverified",
        }
    ]
    assert projection["artifacts"] == [
        {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content_hash": "b" * 64,
        }
    ]
    assert projection["terminal"] == {
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
    }
    assert projection["resolver"] == {
        "kind": "success",
        "execution_status": "completed",
        "delivery_status": "ready",
        "artifact_id": "research-report.md",
        "artifact_kind": "research_report_markdown",
        "artifact_media_type": "text/markdown",
        "artifact_content_hash": "b" * 64,
    }
    serialized = repr(projection)
    for excluded in (
        RUN_ID,
        "thread_run_control",
        "Compare the fixed synthetic context scenario.",
        "Bounded synthetic source content.",
        "https://example.com/context-source",
        "2026-07-25",
    ):
        assert excluded not in serialized


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda run: run["evidence"][0].__setitem__(
                "evidence_id",
                "ev_foreign",
            ),
            id="foreign-evidence-id",
        ),
        pytest.param(
            lambda run: run["evidence"][0].__setitem__(
                "evidence_fingerprint",
                "bad",
            ),
            id="invalid-fingerprint",
        ),
        pytest.param(
            lambda run: run["evidence"][0].__setitem__(
                "query_text",
                "different",
            ),
            id="query-mismatch",
        ),
        pytest.param(
            lambda run: run.__setitem__("artifacts", "not-a-list"),
            id="invalid-artifacts",
        ),
    ],
)
def test_projection_fails_closed_without_raw_details(mutate) -> None:
    run = _persisted_run()
    mutate(run)

    with pytest.raises(ContextProjectionError) as raised:
        project_context_reliability_outcome(run=run, resolution=_resolved())

    assert raised.value.code == "context.projection_invalid"
    assert str(raised.value) == "context.projection_invalid"


def test_projects_resolver_error_without_problem_or_fix() -> None:
    error = RunResultUnavailable(
        status_code=409,
        code="run_not_terminal",
        problem="private diagnostic",
        fix="private recovery",
    )

    projection = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=error,
    )

    assert projection["resolver"] == {
        "kind": "error",
        "status_code": 409,
        "code": "run_not_terminal",
        "retryable": True,
    }
    assert "private diagnostic" not in repr(projection)
    assert "private recovery" not in repr(projection)


def test_projection_rejects_mismatched_resolver_run_id() -> None:
    with pytest.raises(ContextProjectionError, match="context.projection_invalid"):
        project_context_reliability_outcome(
            run=_persisted_run("run_control"),
            resolution=_resolved("run_foreign"),
        )


def test_projection_rejects_raw_mapping_as_resolution() -> None:
    with pytest.raises(ContextProjectionError, match="context.projection_invalid"):
        project_context_reliability_outcome(
            run=_persisted_run(),
            resolution={
                "run_id": RUN_ID,
                "execution_status": "completed",
                "delivery_status": "ready",
            },
        )


def test_run_local_identities_are_validated_then_excluded_from_equality() -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run("run_control"),
        resolution=_resolved("run_control"),
    )
    forced = project_context_reliability_outcome(
        run=_persisted_run("run_forced"),
        resolution=_resolved("run_forced"),
    )

    assert control == forced
    assert compare_context_reliability_outcomes(control, forced) == []


def _set_nested(projection: dict, path: tuple, value) -> None:
    target = projection
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        pytest.param(
            ("query_sha256",),
            "c" * 64,
            "context.query_changed",
            id="query-hash",
        ),
        pytest.param(
            ("evidence", 0, "evidence_fingerprint"),
            "c" * 64,
            "context.evidence_changed",
            id="evidence-fingerprint",
        ),
        pytest.param(
            ("citation_states", 0, "citation_status"),
            "uncited",
            "context.citation_state_changed",
            id="citation-status",
        ),
        pytest.param(
            ("verification_states", 0, "verification_status"),
            "verified",
            "context.verification_state_changed",
            id="verification-status",
        ),
        pytest.param(
            ("artifacts", 0, "content_hash"),
            "c" * 64,
            "context.artifact_changed",
            id="artifact-content-hash",
        ),
        pytest.param(
            ("terminal", "delivery_status"),
            "blocked",
            "context.terminal_state_changed",
            id="delivery-status",
        ),
        pytest.param(
            ("resolver", "artifact_content_hash"),
            "c" * 64,
            "context.result_resolution_changed",
            id="resolver-artifact-hash",
        ),
    ],
)
def test_comparison_emits_dimension_specific_finding(
    path,
    value,
    expected,
) -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )
    forced = deepcopy(control)
    _set_nested(forced, path, value)

    assert compare_context_reliability_outcomes(control, forced) == [expected]


def test_comparison_uses_stable_finding_order() -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )
    forced = deepcopy(control)
    forced["query_sha256"] = "c" * 64
    forced["terminal"]["delivery_status"] = "blocked"
    forced["resolver"]["artifact_content_hash"] = "d" * 64

    assert compare_context_reliability_outcomes(control, forced) == [
        "context.query_changed",
        "context.terminal_state_changed",
        "context.result_resolution_changed",
    ]
    assert CONTEXT_RELIABILITY_FINDING_CODES == (
        "context.query_changed",
        "context.evidence_changed",
        "context.citation_state_changed",
        "context.verification_state_changed",
        "context.artifact_changed",
        "context.terminal_state_changed",
        "context.result_resolution_changed",
    )


def test_comparison_rejects_missing_projected_dimension() -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )
    forced = deepcopy(control)
    del forced["verification_states"]

    with pytest.raises(ContextProjectionError, match="context.projection_invalid"):
        compare_context_reliability_outcomes(control, forced)
