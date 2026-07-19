from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

import pytest

from scripts.bounded_live_producer_contracts import (
    BOUNDARIES,
    LIMITS,
    CleanupReceipt,
    CleanupStatus,
    EvaluationError,
    LiveReportModel,
)
from scripts.bounded_live_producer_http import CreateAmbiguous
from scripts.bounded_live_producer_proof import (
    TerminalSnapshot,
    compare_restart,
    main,
    observe_terminal,
    observe_usage,
    project_live_observation,
    publish_paired_output,
    reconcile_create,
    run_cleanup_guarded,
    run_provider_free_check,
    validate_replay,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    PROJECT_ROOT / "benchmarks" / "bounded-live-producer-v1" / "manifest.json"
)
ARTIFACT_TEXT = "# Free-threaded CPython pilot\n\nBounded public-source brief.\n"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT_TEXT.encode("utf-8")).hexdigest()


def _evidence(
    evidence_id: str,
    source_url: str,
    *,
    citation_status: str = "cited",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "run_id": "run-proof-1",
        "segment_id": "segment-proof-1",
        "query_text": "must-not-be-published",
        "subagent_name": "researcher",
        "tool_name": "search",
        "source_url": source_url,
        "source_identity": source_url,
        "snippet": "must-not-be-published",
        "evidence_fingerprint": "a" * 64,
        "retrieved_at": "2026-07-18T00:00:00+00:00",
        "tool_call_id": "tool-1",
        "citation_status": citation_status,
        "verification_status": "unverified",
        "created_at": "2026-07-18T00:00:00+00:00",
    }


def _status(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-proof-1",
        "thread_id": "thread-proof-1",
        "profile_id": "generic",
        "query": "must-not-be-published",
        "scope": {},
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "state_version": 2,
        "failure_cause": None,
        "segments": [
            {
                "segment_id": "segment-proof-1",
                "run_id": "run-proof-1",
                "kind": "initial",
                "sequence": 0,
                "attempt": 1,
                "status": "completed",
                "created_at": "2026-07-18T00:00:00+00:00",
                "updated_at": "2026-07-18T00:01:00+00:00",
            }
        ],
        "evidence": [
            _evidence("ev-python-docs", "https://docs.python.org/3/howto/free-threading-python.html"),
            _evidence("ev-pep-703", "https://peps.python.org/pep-0703/"),
        ],
    }
    payload.update(overrides)
    return payload


def _result(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-proof-1",
        "execution_status": "completed",
        "delivery_status": "ready",
        "artifact": {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": ARTIFACT_TEXT,
            "content_hash": ARTIFACT_HASH,
        },
    }
    payload.update(overrides)
    return payload


def _snapshot(
    *,
    status: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> TerminalSnapshot:
    return project_live_observation(
        status_payload=status or _status(),
        result_payload=result or _result(),
        expected_run_id="run-proof-1",
        expected_thread_id="thread-proof-1",
        expected_segment_id="segment-proof-1",
        required_cited_domains=("docs.python.org", "peps.python.org"),
    )


def _report() -> LiveReportModel:
    observation = _snapshot()
    return LiveReportModel.model_validate(
        {
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
                "docker_version": "Docker version 28",
                "compose_version": "Docker Compose version v2",
                "source_clean": True,
                "build_context": "tracked_archive",
            },
            "scenario": {
                "scenario_id": "cpython-313-free-threaded-pilot",
                "manifest_sha256": "d" * 64,
                "request_sha256": "1" * 64,
                "profile_id": "generic",
                "required_cited_domains": ["docs.python.org", "peps.python.org"],
                "provider_id": "approved-provider",
                "primary_model_id": "approved-model",
                "fallback_model_id": "approved-model",
            },
            "lifecycle": {
                "docker_probe_ms": 1,
                "build_start_ms": 1,
                "research_ms": 1,
                "restart_replay_ms": 1,
                "active_ms": 3,
                "cleanup_ms": 1,
                "total_ms": 5,
                "loopback_binding_observed": True,
                "health_identity_observed": True,
            },
            "run": observation.run.model_dump(mode="python"),
            "result": observation.result.model_dump(mode="python"),
            "evidence": [row.model_dump(mode="python") for row in observation.evidence],
            "usage": {
                "status": "not_observed",
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
            "boundaries": BOUNDARIES,
            "limits": list(LIMITS),
        },
        strict=True,
    )


def test_import_is_silent_and_does_not_initialize_runtime_or_docker() -> None:
    command = (
        "import json,sys; "
        "import scripts.bounded_live_producer_proof; "
        "print(json.dumps({'server': 'api.server' in sys.modules, "
        "'agent': 'agent.main_agent' in sys.modules, 'docker': 'docker' in sys.modules}, "
        "sort_keys=True, separators=(',', ':')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHON_DOTENV_DISABLED": "1"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stderr == ""
    assert result.stdout == '{"agent":false,"docker":false,"server":false}\n'


def test_provider_free_check_is_exact_and_deterministic() -> None:
    first = run_provider_free_check(manifest_path=MANIFEST_PATH)
    second = run_provider_free_check(manifest_path=MANIFEST_PATH)
    expected = {
        "mode": "provider_free",
        "schema_version": "dra.bounded-live-producer-manifest.v1",
        "status": "valid",
    }
    assert first == second == expected
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == (
        '{"mode":"provider_free","schema_version":'
        '"dra.bounded-live-producer-manifest.v1","status":"valid"}'
    )


def test_cli_check_has_exact_stdout_and_help_is_non_mutating(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        '{"mode":"provider_free","schema_version":'
        '"dra.bounded-live-producer-manifest.v1","status":"valid"}\n'
    )
    assert captured.err == ""
    for arguments in (["--help"], ["check", "--help"], ["observe-live", "--help"]):
        assert main(list(arguments)) == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert captured.err == ""


@pytest.mark.parametrize("arguments", [[], ["unknown"], ["check", "--extra"]])
def test_cli_invalid_arguments_emit_one_canonical_error_line(
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "manifest_invalid",
        "phase": "input",
        "retryable": False,
        "cleanup_status": "not_started",
    }
    assert captured.err.count("\n") == 1


class FakeCreateClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[bytes, str]] = []

    def create(self, *, request_bytes: bytes, idempotency_key: str) -> dict[str, Any]:
        self.calls.append((request_bytes, idempotency_key))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, dict)
        return outcome


def _create_ack(*, replay: bool) -> dict[str, Any]:
    return {
        "status": "started",
        "run_id": "run-proof-1",
        "thread_id": "thread-proof-1",
        "segment_id": "segment-proof-1",
        "idempotent_replay": replay,
    }


def _request_bytes() -> bytes:
    return json.dumps(
        {
            "profile_id": "generic",
            "query": "bounded query",
            "scope": {},
            "thread_id": "thread-proof-1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_new_request_uses_contract_hash_and_128_bit_thread_and_key_entropy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    manifest = module.load_manifest(MANIFEST_PATH)
    values = iter(("a" * 32, "b" * 32))
    monkeypatch.setattr(module.secrets, "token_hex", lambda size: next(values))
    request_bytes, request_hash, thread_id, key = module._new_request(manifest)
    request = json.loads(request_bytes)
    assert thread_id == "proof-thread-" + "a" * 32
    assert key == "proof-key-" + "b" * 32
    assert request == {
        "query": manifest.query,
        "thread_id": thread_id,
        "profile_id": "generic",
        "scope": {},
    }
    from api.run_creation_models import run_create_request_hash

    assert request_hash == run_create_request_hash(
        query=manifest.query,
        thread_id=thread_id,
        profile_id="generic",
        scope={},
    )
    assert request_hash != hashlib.sha256(request_bytes).hexdigest()


def test_reconcile_create_accepts_first_ack_and_preserves_object_identity() -> None:
    request_bytes = _request_bytes()
    key = "proof-key-0123456789abcdef0123456789abcdef"
    client = FakeCreateClient([_create_ack(replay=False)])
    accepted = reconcile_create(client, request_bytes=request_bytes, key=key)
    assert accepted == _create_ack(replay=False)
    assert client.calls == [(request_bytes, key)]
    assert client.calls[0][0] is request_bytes
    assert client.calls[0][1] is key


def test_reconcile_create_replays_exact_request_only_after_one_ambiguity() -> None:
    request_bytes = _request_bytes()
    key = "proof-key-0123456789abcdef0123456789abcdef"
    client = FakeCreateClient([CreateAmbiguous(), _create_ack(replay=True)])
    accepted = reconcile_create(client, request_bytes=request_bytes, key=key)
    assert accepted["idempotent_replay"] is True
    assert client.calls == [(request_bytes, key), (request_bytes, key)]
    assert all(call[0] is request_bytes and call[1] is key for call in client.calls)


def test_reconcile_create_stops_after_second_ambiguity() -> None:
    client = FakeCreateClient([CreateAmbiguous(), CreateAmbiguous()])
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            client,
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert (caught.value.code.value, caught.value.phase.value) == (
        "create_reconciliation_unresolved",
        "create",
    )
    assert len(client.calls) == 2


def test_reconcile_create_never_retries_complete_http_error() -> None:
    failure = EvaluationError("create_rejected", "create", False)
    client = FakeCreateClient([failure, _create_ack(replay=True)])
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            client,
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert caught.value is failure
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("ack", "expected_code"),
    [
        ({**_create_ack(replay=False), "thread_id": "other-thread"}, "create_identity_mismatch"),
        ({**_create_ack(replay=False), "idempotent_replay": True}, "create_response_invalid"),
        ({**_create_ack(replay=False), "extra": "field"}, "create_response_invalid"),
    ],
)
def test_reconcile_create_rejects_malformed_or_mismatched_ack(
    ack: dict[str, Any],
    expected_code: str,
) -> None:
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            FakeCreateClient([ack]),
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert caught.value.code.value == expected_code


def test_project_live_observation_accepts_only_canonical_consumer_and_six_field_evidence() -> None:
    projected = _snapshot()
    assert projected.run.run_id == "run-proof-1"
    assert projected.run.segment_id == "segment-proof-1"
    assert projected.result.sha256 == ARTIFACT_HASH
    assert [row.evidence_id for row in projected.evidence] == [
        "ev-python-docs",
        "ev-pep-703",
    ]
    assert set(projected.evidence[0].model_dump()) == {
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    }
    assert "query_text" not in repr(projected)
    with pytest.raises(FrozenInstanceError):
        projected.state_version = 3  # type: ignore[misc]


def test_observe_terminal_uses_one_remaining_deadline_and_never_cancels() -> None:
    class Client:
        def __init__(self) -> None:
            self.statuses = [
                _status(execution_status="pending", delivery_status="pending"),
                _status(execution_status="running", delivery_status="pending"),
                _status(),
            ]
            self.status_calls: list[str] = []
            self.result_calls: list[str] = []

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            assert timeout_seconds == 30.0
            self.status_calls.append(run_id)
            return self.statuses.pop(0)

        def result(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            assert timeout_seconds == 30.0
            self.result_calls.append(run_id)
            return _result()

    client = Client()
    remaining_calls: list[float] = []
    sleeps: list[float] = []

    def remaining(requested: float) -> float:
        remaining_calls.append(requested)
        return min(requested, 0.25)

    projected, status, result = observe_terminal(
        client,  # type: ignore[arg-type]
        accepted=_create_ack(replay=False),
        required_cited_domains=("docs.python.org", "peps.python.org"),
        remaining_seconds=remaining,
        sleep=sleeps.append,
    )
    assert projected.run.run_id == "run-proof-1"
    assert status["execution_status"] == "completed"
    assert result["artifact"]["content_hash"] == ARTIFACT_HASH
    assert client.status_calls == ["run-proof-1"] * 3
    assert client.result_calls == ["run-proof-1"]
    assert remaining_calls == [30.0, 1.0, 30.0, 1.0, 30.0]
    assert sleeps == [0.25, 0.25]
    assert not hasattr(client, "cancel")


def test_restart_backend_transport_reinspects_loopback_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    events: list[tuple[object, ...]] = []

    class Deadline:
        def remaining(self, requested: float) -> float:
            return requested

    class Project:
        def restart_backend(self, deadline: object) -> None:
            events.append(("restart", deadline))

    class Client:
        def __init__(
            self,
            *,
            port: int,
            api_key: str,
            remaining_seconds: object,
        ) -> None:
            events.append(("client", port, api_key, remaining_seconds))

        def health(self, *, timeout_seconds: float) -> dict[str, str]:
            events.append(("health", timeout_seconds))
            return {"status": "ok", "service": "decision-research-agent"}

    deadline = Deadline()
    project = Project()

    def inspect_port(
        inspected_project: object,
        service: str,
        target: int,
        inspected_deadline: object,
    ) -> int:
        events.append(
            ("port", inspected_project, service, target, inspected_deadline)
        )
        return 48001

    monkeypatch.setattr(module, "_loopback_port", inspect_port)
    monkeypatch.setattr(module, "ProofHttpClient", Client)

    client = module.restart_backend_transport(
        project,
        api_key="test-api-secret",
        deadline=deadline,
    )

    assert isinstance(client, Client)
    assert events[0] == ("restart", deadline)
    assert events[1] == ("port", project, "backend", 8000, deadline)
    assert events[2][:3] == ("client", 48001, "test-api-secret")
    assert getattr(events[2][3], "__self__", None) is deadline
    assert events[3] == ("health", 30.0)


@pytest.mark.parametrize(
    ("status", "result", "expected_code"),
    [
        (_status(execution_status="failed"), _result(), "run_failed"),
        (_status(execution_status="completed_with_fallback"), _result(), "run_fallback_rejected"),
        (_status(delivery_status="blocked"), _result(), "run_delivery_not_ready"),
        (_status(failure_cause={"code": "execution_error"}), _result(), "run_state_invalid"),
        (_status(thread_id="other-thread"), _result(), "run_state_invalid"),
        (_status(segments=[]), _result(), "run_state_invalid"),
        (_status(evidence=[]), _result(), "evidence_missing"),
        (_status(), _result(run_id="other-run"), "consumer_projection_invalid"),
        (
            _status(),
            _result(
                artifact={
                    **_result()["artifact"],
                    "kind": "research_report_fallback_markdown",
                }
            ),
            "consumer_projection_invalid",
        ),
    ],
)
def test_project_live_observation_rejects_terminal_consumer_and_identity_mutations(
    status: dict[str, Any],
    result: dict[str, Any],
    expected_code: str,
) -> None:
    with pytest.raises(EvaluationError) as caught:
        project_live_observation(
            status_payload=status,
            result_payload=result,
            expected_run_id="run-proof-1",
            expected_thread_id="thread-proof-1",
            expected_segment_id="segment-proof-1",
            required_cited_domains=("docs.python.org", "peps.python.org"),
        )
    assert caught.value.code.value == expected_code


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda rows: [rows[0], rows[0]], "evidence_invalid"),
        (
            lambda rows: [
                {**rows[0], "source_url": "https://127.0.0.1/private"},
                rows[1],
            ],
            "evidence_invalid",
        ),
        (
            lambda rows: [
                {**rows[0], "citation_status": "uncited"},
                rows[1],
            ],
            "required_cited_domain_missing",
        ),
    ],
)
def test_project_live_observation_rejects_evidence_mutations(mutator, expected_code: str) -> None:
    status = _status()
    status["evidence"] = mutator(status["evidence"])
    with pytest.raises(EvaluationError) as caught:
        _snapshot(status=status)
    assert caught.value.code.value == expected_code


def test_observe_usage_maps_absence_and_positive_consistent_usage() -> None:
    absent = observe_usage(
        {
            "total_prompt": 0,
            "total_completion": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "call_count": 0,
        },
        primary_model_id="model-a",
        fallback_model_id="model-a",
    )
    assert absent.model_dump(mode="json") == {
        "status": "not_observed",
        "cost_estimate": {"status": "not_observed"},
        "search_cost": {"status": "not_observed"},
    }
    observed = observe_usage(
        {
            "total_prompt": 10,
            "total_completion": 5,
            "total_tokens": 15,
            "total_cost": 0.125,
            "call_count": 2,
        },
        primary_model_id="model-a",
        fallback_model_id="model-a",
        pricing_basis="operator-v1",
        currency="USD",
        pricing_identity_matches=True,
    )
    assert observed.model_dump(mode="json") == {
        "status": "observed",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "call_count": 2,
        "cost_estimate": {
            "status": "observed",
            "amount": "0.12500000",
            "currency": "USD",
            "pricing_basis": "operator-v1",
            "estimate": True,
        },
        "search_cost": {"status": "not_observed"},
    }


def test_observe_usage_keeps_cost_unobserved_for_model_ambiguity_or_missing_declaration() -> None:
    payload = {
        "total_prompt": 10,
        "total_completion": 5,
        "total_tokens": 15,
        "total_cost": 0.125,
        "call_count": 1,
    }
    for options in (
        {"primary_model_id": "model-a", "fallback_model_id": "model-b"},
        {"primary_model_id": "model-a", "fallback_model_id": "model-a"},
        {
            "primary_model_id": "model-a",
            "fallback_model_id": "model-a",
            "pricing_basis": "operator-v1",
            "currency": "USD",
            "pricing_identity_matches": False,
        },
    ):
        usage = observe_usage(payload, **options)
        assert usage.status == "observed"
        assert usage.cost_estimate.status == "not_observed"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_prompt": 1, "total_completion": 1, "total_tokens": 3, "total_cost": 0, "call_count": 1},
        {"total_prompt": -1, "total_completion": 1, "total_tokens": 0, "total_cost": 0, "call_count": 1},
        {"total_prompt": 0, "total_completion": 0, "total_tokens": 0, "total_cost": 0, "call_count": 1},
        {"total_prompt": 1, "total_completion": 1, "total_tokens": 2, "total_cost": float("nan"), "call_count": 1},
    ],
)
def test_observe_usage_rejects_malformed_or_inconsistent_payload(payload: dict[str, Any]) -> None:
    with pytest.raises(EvaluationError, match="usage_invalid"):
        observe_usage(
            payload,
            primary_model_id="model-a",
            fallback_model_id="model-a",
        )


def test_compare_restart_requires_identity_state_evidence_artifact_and_disposition() -> None:
    before = _snapshot()
    after = _snapshot(status=_status(state_version=3))
    receipt = compare_restart(before, after)
    assert receipt.model_dump(mode="json") == {
        "same_run_identity": True,
        "same_thread_identity": True,
        "same_segment_identity": True,
        "state_version_non_regressing": True,
        "same_terminal_state": True,
        "same_evidence": True,
        "same_artifact": True,
        "same_consumer_disposition": True,
    }


@pytest.mark.parametrize(
    ("after", "expected_code"),
    [
        (
            lambda before: replace(
                before,
                run=before.run.model_copy(update={"run_id": "run-other"}),
            ),
            "restart_identity_drift",
        ),
        (lambda _before: _snapshot(status=_status(state_version=1)), "restart_identity_drift"),
        (
            lambda _before: _snapshot(
                status=_status(
                    evidence=list(reversed(_status()["evidence"])),
                )
            ),
            "restart_evidence_drift",
        ),
        (
            lambda _before: _snapshot(
                result=_result(
                    artifact={
                        **_result()["artifact"],
                        "content": ARTIFACT_TEXT + "changed",
                        "content_hash": hashlib.sha256(
                            (ARTIFACT_TEXT + "changed").encode("utf-8")
                        ).hexdigest(),
                    }
                )
            ),
            "restart_artifact_drift",
        ),
    ],
)
def test_compare_restart_maps_drift_to_stable_codes(after, expected_code: str) -> None:
    before = _snapshot()
    with pytest.raises(EvaluationError) as caught:
        compare_restart(before, after(before))
    assert caught.value.code.value == expected_code


def test_validate_replay_requires_exact_identity_flag_and_unchanged_projection() -> None:
    before = _snapshot()
    receipt = validate_replay(_create_ack(replay=True), before=before, after=before)
    assert receipt.idempotent_replay is True
    assert receipt.unchanged_terminal_projection is True


@pytest.mark.parametrize(
    ("ack", "expected_code"),
    [
        ({**_create_ack(replay=True), "run_id": "run-other"}, "duplicate_run_observed"),
        ({**_create_ack(replay=True), "idempotent_replay": False}, "idempotent_replay_invalid"),
        ({**_create_ack(replay=True), "extra": "field"}, "idempotent_replay_invalid"),
    ],
)
def test_validate_replay_rejects_new_identity_or_malformed_ack(
    ack: dict[str, Any],
    expected_code: str,
) -> None:
    before = _snapshot()
    with pytest.raises(EvaluationError) as caught:
        validate_replay(ack, before=before, after=before)
    assert caught.value.code.value == expected_code


def _output_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "evidence").mkdir(parents=True)
    return root


def test_publish_paired_output_uses_exact_paths_and_never_overwrites(tmp_path: Path) -> None:
    root = _output_root(tmp_path)
    json_path, markdown_path = publish_paired_output(root, _report())
    assert json_path == root / "docs/evidence/bounded-live-producer-v1.json"
    assert markdown_path == root / "docs/evidence/bounded-live-producer-v1.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "valid"
    assert markdown_path.read_text(encoding="utf-8").startswith(
        "# Bounded Live Producer Evaluation v1\n"
    )
    assert not list((root / "docs/evidence").glob(".bounded-live-producer-*"))
    with pytest.raises(EvaluationError, match="output_exists"):
        publish_paired_output(root, _report())


def test_publish_paired_output_rejects_symlinked_parent_and_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs/evidence").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EvaluationError, match="output_invalid"):
        publish_paired_output(root, _report())

    root = _output_root(tmp_path / "second")
    target = root / "docs/evidence/bounded-live-producer-v1.json"
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(EvaluationError, match="output_exists"):
        publish_paired_output(root, _report())


def test_publish_paired_output_rolls_back_first_target_when_second_link_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _output_root(tmp_path)
    real_link = os.link
    calls = 0

    def fail_second_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", fail_second_link)
    with pytest.raises(EvaluationError, match="output_write_failed"):
        publish_paired_output(root, _report())
    assert list((root / "docs/evidence").iterdir()) == []


def test_run_cleanup_guarded_preserves_primary_and_cleanup_causes() -> None:
    primary = EvaluationError("run_failed", "observe", False)
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail_primary():
        raise primary

    def fail_cleanup():
        raise cleanup

    with pytest.raises(ExceptionGroup) as caught:
        run_cleanup_guarded(fail_primary, fail_cleanup)
    assert caught.value.exceptions == (primary, cleanup)


def test_run_cleanup_guarded_returns_cleanup_receipt_after_success() -> None:
    receipt = CleanupReceipt(
        attempted=True,
        succeeded=True,
        zero_container_residue=True,
        zero_volume_residue=True,
        zero_network_residue=True,
        zero_temp_residue=True,
    )
    assert run_cleanup_guarded(lambda: "result", lambda: receipt) == ("result", receipt)


def test_main_projects_unknown_exception_without_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    def fail(**_kwargs):
        raise RuntimeError("credential-value-must-not-appear")

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "credential-value-must-not-appear" not in captured.err
    assert json.loads(captured.err)["code"] == "evaluation_internal_error"


def test_main_projects_dual_failure_as_primary_with_failed_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    primary = EvaluationError("run_failed", "observe", False)
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail(**_kwargs):
        raise ExceptionGroup("local-only", [primary, cleanup])

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "run_failed",
        "phase": "observe",
        "retryable": False,
        "cleanup_status": "failed",
    }


def test_live_cli_accepts_only_public_declarations_and_fixed_output_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    captured_arguments: dict[str, Any] = {}

    def fake_observe_live(**kwargs):
        captured_arguments.update(kwargs)
        return _report()

    monkeypatch.setattr(module, "observe_live", fake_observe_live)
    env_file = tmp_path / "live.env"
    arguments = [
        "observe-live",
        "--env-file",
        str(env_file),
        "--provider-id",
        "approved-provider",
        "--provider-base-url",
        "https://provider.example/v1",
        "--primary-model-id",
        "approved-model",
        "--fallback-model-id",
        "approved-model",
        "--pricing-basis",
        "operator-v1",
        "--currency",
        "USD",
        "--retain-task-images",
    ]
    assert module.main(arguments) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "mode": "live",
        "schema_version": "dra.bounded-live-producer-evaluation.v1",
        "status": "valid",
    }
    assert output.err == ""
    assert captured_arguments == {
        "env_file": env_file,
        "provider_id": "approved-provider",
        "provider_base_url": "https://provider.example/v1",
        "primary_model_id": "approved-model",
        "fallback_model_id": "approved-model",
        "pricing_basis": "operator-v1",
        "currency": "USD",
        "retain_task_images": True,
    }
    assert not any(
        name in captured_arguments
        for name in ("query", "scope", "output", "project_name", "api_key", "retry")
    )


@pytest.mark.parametrize(
    "extra",
    [
        ["--query", "private"],
        ["--output", "report.json"],
        ["--provider-i", "abbreviated"],
        ["--pricing-basis", "operator-v1"],
        ["--currency", "USD"],
    ],
)
def test_live_cli_rejects_unapproved_or_partial_arguments(
    extra: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "observe-live",
        "--env-file",
        "live.env",
        "--provider-id",
        "approved-provider",
        "--provider-base-url",
        "https://provider.example/v1",
        "--primary-model-id",
        "model-a",
        "--fallback-model-id",
        "model-a",
        *extra,
    ]
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["phase"] == "input"


def test_container_fixture_uses_production_dispatch_fence_and_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_path = PROJECT_ROOT / "scripts/bounded_live_producer_container_fixture.py"
    assert fixture_path.is_file()
    source = fixture_path.read_text(encoding="utf-8")
    assert "start_run_dispatch" in source
    assert "finalize_run_transaction" in source
    assert "build_generic_result_artifact" in source
    assert "create_run_dispatch_worker" in source
    assert "run_deep_agent" in source
    assert "sqlite3" not in source
    assert "live evidence" not in source.lower()

    guard = subprocess.run(
        [sys.executable, str(fixture_path), "serve"],
        cwd=PROJECT_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHON_DOTENV_DISABLED": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert guard.returncode == 1
    assert guard.stdout == ""
    assert guard.stderr == '{"code":"fixture_disabled"}\n'

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE", "true")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION", "false")
    server_was_loaded = "api.server" in sys.modules
    module = importlib.import_module(
        "scripts.bounded_live_producer_container_fixture"
    )
    assert ("api.server" in sys.modules) is server_was_loaded

    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_or_replay_run, get_run
    from api.run_result_service import resolve_run_result

    db_path = str(tmp_path / "fixture.db")
    accepted = create_or_replay_run(
        db_path=db_path,
        idempotency_key="fixture-key-0123456789abcdef0123456789abcdef",
        thread_id="fixture-thread-0123456789abcdef0123456789abcdef",
        query="bounded fixture query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_" + "a" * 32,
        lease_seconds=30,
        run_id=accepted.run_id,
    )
    assert claim is not None
    worker = module.create_fixture_worker(db_path)
    worker.scheduler(claim)

    status = get_run(db_path=db_path, run_id=accepted.run_id)
    resolved = resolve_run_result(db_path=db_path, run_id=accepted.run_id)
    assert status is not None
    assert status["state_version"] == 2
    assert status["segments"][0]["status"] == "completed"
    result = {
        "run_id": resolved.run_id,
        "execution_status": resolved.execution_status,
        "delivery_status": resolved.delivery_status,
        "artifact": resolved.artifact,
    }
    projected = project_live_observation(
        status_payload=status,
        result_payload=result,
        expected_run_id=accepted.run_id,
        expected_thread_id=accepted.thread_id,
        expected_segment_id=accepted.segment_id,
        required_cited_domains=("docs.python.org", "peps.python.org"),
    )
    assert projected.result.consumer_support == "supported"
    assert [urlsplit(row.source_url).hostname for row in projected.evidence] == [
        "docs.python.org",
        "peps.python.org",
    ]
    assert "live evidence" not in resolved.artifact["content"].lower()
