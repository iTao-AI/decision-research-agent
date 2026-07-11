from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


def _canonical_status() -> dict:
    return {
        "run_id": "run_fixture_canonical",
        "profile_id": "generic",
        "profile_version": "1",
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "state_version": 1,
        "query": "must not be projected",
        "evidence": [
            {
                "evidence_id": "ev_run_fixture_canonical_01",
                "run_id": "run_fixture_canonical",
                "segment_id": "run_fixture_canonical_seg_000",
                "query_text": "must not be projected",
                "subagent_name": "network_search",
                "tool_name": "internet_search",
                "source_url": "https://example.com/public-source",
                "source_identity": "https://example.com/public-source",
                "snippet": "must not be projected",
                "evidence_fingerprint": "f" * 64,
                "retrieved_at": "2026-07-11T00:00:00+00:00",
                "tool_call_id": "tool-private",
                "citation_status": "cited",
                "verification_status": "unverified",
                "created_at": "2026-07-11T00:00:00+00:00",
            }
        ],
    }


def _canonical_result() -> dict:
    content = "# Synthetic Research Report\n\nPublic-safe contract proof."
    return {
        "run_id": "run_fixture_canonical",
        "execution_status": "completed",
        "delivery_status": "ready",
        "artifact": {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    }


def _project(status: dict | None = None, result: dict | None = None) -> dict:
    from scripts.downstream_consumer_contract import project_consumer_case

    return project_consumer_case(
        case_id="canonical_ready",
        status_payload=status or _canonical_status(),
        result_http_status=200,
        result_payload=result or _canonical_result(),
    )


def _bundle(case: dict | None = None) -> dict:
    return {
        "schema_version": "dra.downstream-consumer.v1",
        "service": {
            "name": "decision-research-agent",
            "health": {"status": "ok", "service": "decision-research-agent"},
            "status_endpoint": "/api/runs/{run_id}",
            "result_endpoint": "/api/runs/{run_id}/result",
        },
        "capabilities": {
            "supported": [
                "run_state",
                "run_level_evidence",
                "generic_canonical_artifact",
                "fallback_distinction",
                "review_and_delivery_gates",
                "stable_result_errors",
            ],
            "partial": [
                "retrieved_at_is_not_source_as_of",
                "fallback_content_is_not_canonical",
                "completed_with_fallback_is_compatibility_only",
            ],
            "unknown": [
                "claim_level_evidence_refs",
                "typed_limitations",
                "typed_conflicts_and_gaps",
                "source_title_publisher_and_effective_date",
                "persistent_failure_cause",
                "persistent_usage_cost",
            ],
        },
        "cases": [case or _project()],
    }


def test_canonical_projection_is_strict_and_public_safe():
    projected = _project()

    assert projected["expected"] == {
        "support": "supported",
        "disposition": "accept_draft",
    }
    assert set(projected["evidence"][0]) == {
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    }
    serialized = json.dumps(projected, ensure_ascii=False)
    for forbidden in ("query_text", "snippet", "tool-private", "network_search"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_status", "mystery"),
        ("review_status", "mystery"),
        ("delivery_status", "mystery"),
        ("state_version", -1),
        ("state_version", "1"),
        ("run_id", ""),
        ("profile_id", "bad profile"),
    ],
)
def test_projection_rejects_invalid_run_state(field: str, value: object):
    from scripts.downstream_consumer_contract import ContractValidationError

    status = _canonical_status()
    status[field] = value
    with pytest.raises(ContractValidationError):
        _project(status=status)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "other.md"),
        ("kind", "decision_brief_markdown"),
        ("kind", "unknown"),
        ("media_type", "text/plain"),
        ("content", ""),
        ("content_hash", "not-a-hash"),
        ("content_hash", "0" * 64),
    ],
)
def test_projection_rejects_invalid_generic_artifact(field: str, value: str):
    from scripts.downstream_consumer_contract import ContractValidationError

    result = _canonical_result()
    result["artifact"][field] = value
    with pytest.raises(ContractValidationError):
        _project(result=result)


def test_projection_rejects_impossible_state_and_wrong_result():
    from scripts.downstream_consumer_contract import ContractValidationError

    status = _canonical_status()
    status["delivery_status"] = "pending"
    with pytest.raises(ContractValidationError):
        _project(status=status)

    with pytest.raises(ContractValidationError):
        from scripts.downstream_consumer_contract import project_consumer_case

        project_consumer_case(
            case_id="canonical_ready",
            status_payload=_canonical_status(),
            result_http_status=409,
            result_payload={
                "detail": {
                    "code": "run_not_terminal",
                    "run_id": "run_fixture_canonical",
                    "retryable": True,
                }
            },
        )


def test_projection_handles_fallback_but_never_accepts_it():
    result = _canonical_result()
    result["artifact"]["kind"] = "research_report_fallback_markdown"
    projected = _project(result=result)
    assert projected["expected"] == {
        "support": "partial",
        "disposition": "block_fallback",
    }


def test_projection_enforces_evidence_identity_url_and_duplicates():
    from scripts.downstream_consumer_contract import ContractValidationError

    status = _canonical_status()
    status["evidence"][0]["source_url"] = "http://example.com/private"
    with pytest.raises(ContractValidationError):
        _project(status=status)

    status = _canonical_status()
    status["evidence"].append(copy.deepcopy(status["evidence"][0]))
    with pytest.raises(ContractValidationError):
        _project(status=status)

    status = _canonical_status()
    status["evidence"] = []
    assert _project(status=status)["evidence"] == []


def test_fixture_schema_is_exact_and_deterministic():
    from scripts.downstream_consumer_contract import (
        ContractValidationError,
        serialize_fixture,
        validate_fixture_bundle,
    )

    payload = _bundle()
    assert validate_fixture_bundle(payload) is payload
    assert serialize_fixture(payload).endswith(b"\n")

    mutations = []
    wrong_schema = copy.deepcopy(payload)
    wrong_schema["schema_version"] = "v2"
    mutations.append(wrong_schema)
    extra_root = copy.deepcopy(payload)
    extra_root["extra"] = True
    mutations.append(extra_root)
    extra_case = copy.deepcopy(payload)
    extra_case["cases"][0]["extra"] = True
    mutations.append(extra_case)
    extra_evidence = copy.deepcopy(payload)
    extra_evidence["cases"][0]["evidence"][0]["snippet"] = "private"
    mutations.append(extra_evidence)
    duplicate_case = copy.deepcopy(payload)
    duplicate_case["cases"].append(copy.deepcopy(duplicate_case["cases"][0]))
    mutations.append(duplicate_case)
    bad_disposition = copy.deepcopy(payload)
    bad_disposition["cases"][0]["expected"]["disposition"] = "approve"
    mutations.append(bad_disposition)

    for mutation in mutations:
        with pytest.raises(ContractValidationError):
            validate_fixture_bundle(mutation)


def test_build_fixture_bundle_covers_required_states_and_is_deterministic():
    from scripts.downstream_consumer_contract import (
        build_fixture_bundle,
        serialize_fixture,
    )

    first = build_fixture_bundle()
    second = build_fixture_bundle()

    assert serialize_fixture(first) == serialize_fixture(second)
    assert [case["case_id"] for case in first["cases"]] == [
        "pending",
        "running",
        "canonical_ready",
        "fallback_ready",
        "compatibility_fallback",
        "review_required",
        "blocked",
        "failed",
        "result_unavailable",
    ]


def test_fixture_capabilities_keep_untyped_semantics_unknown():
    from scripts.downstream_consumer_contract import build_fixture_bundle

    capabilities = build_fixture_bundle()["capabilities"]
    assert "run_level_evidence" in capabilities["supported"]
    assert "retrieved_at_is_not_source_as_of" in capabilities["partial"]
    assert "typed_limitations" in capabilities["unknown"]
    assert "claim_level_evidence_refs" in capabilities["unknown"]
    assert "persistent_failure_cause" in capabilities["unknown"]
    assert "persistent_usage_cost" in capabilities["unknown"]


def test_build_fixture_uses_expected_results_evidence_and_public_values():
    from scripts.downstream_consumer_contract import build_fixture_bundle

    bundle = build_fixture_bundle()
    by_id = {case["case_id"]: case for case in bundle["cases"]}
    for case_id in ("canonical_ready", "fallback_ready", "compatibility_fallback"):
        assert len(by_id[case_id]["evidence"]) == 1
    assert by_id["fallback_ready"]["expected"]["disposition"] == "block_fallback"
    assert by_id["compatibility_fallback"]["expected"]["disposition"] == "block_fallback"
    assert by_id["pending"]["result"]["body"]["code"] == "run_not_terminal"
    assert by_id["running"]["result"]["body"]["code"] == "run_not_terminal"
    assert by_id["review_required"]["result"]["body"]["code"] == "run_review_required"
    assert by_id["blocked"]["result"]["body"]["code"] == "run_delivery_blocked"
    assert by_id["failed"]["result"]["body"]["code"] == "run_failed"
    assert by_id["result_unavailable"]["result"]["body"]["code"] == "run_result_unavailable"

    serialized = json.dumps(bundle, ensure_ascii=False)
    for forbidden in (
        "/Users/",
        "/private/",
        "Traceback",
        "checkpoint",
        "api_key",
        "secret",
        "Synthetic private query",
        "Synthetic private snippet",
        "tool-private",
    ):
        assert forbidden not in serialized
    assert "2026-07-11T00:00:00+00:00" in serialized


def test_committed_fixture_matches_fresh_build():
    from scripts.downstream_consumer_contract import (
        build_fixture_bundle,
        serialize_fixture,
    )

    committed = Path("docs/evidence/downstream-consumer-contract-v1.json").read_bytes()
    assert committed == serialize_fixture(build_fixture_bundle())


def test_cli_build_and_check_are_deterministic(tmp_path, capsys):
    from scripts.downstream_consumer_contract import (
        build_fixture_bundle,
        main,
        serialize_fixture,
    )

    output = tmp_path / "fixture.json"
    assert main(["build", "--output", str(output)]) == 0
    assert output.read_bytes() == serialize_fixture(build_fixture_bundle())
    assert json.loads(capsys.readouterr().out) == {
        "status": "built",
        "schema_version": "dra.downstream-consumer.v1",
    }

    assert main(["check", "--input", str(output)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "valid",
        "schema_version": "dra.downstream-consumer.v1",
    }


def test_cli_file_entrypoint_can_import_application_modules(tmp_path):
    output = tmp_path / "fixture.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/downstream_consumer_contract.py",
            "build",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "built"


def test_cli_reports_drift_with_bounded_error(tmp_path, capsys):
    from scripts.downstream_consumer_contract import build_fixture_bundle, main

    payload = build_fixture_bundle()
    payload["cases"][0]["run"]["state_version"] += 1
    fixture = tmp_path / "modified.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["check", "--input", str(fixture)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid",
        "code": "contract_fixture_drift",
    }
    assert str(fixture) not in captured.err


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"not-json", "contract_file_invalid"),
        (b"[]", "contract_file_invalid"),
        (b'{"schema_version":"unsupported"}', "contract_schema_unsupported"),
    ],
)
def test_cli_maps_invalid_input_to_bounded_codes(tmp_path, capsys, body: bytes, code: str):
    from scripts.downstream_consumer_contract import main

    fixture = tmp_path / "invalid.json"
    fixture.write_bytes(body)
    assert main(["check", "--input", str(fixture)]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {"status": "invalid", "code": code}
    assert str(fixture) not in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_oversized_unreadable_and_unwritable_files(tmp_path, capsys):
    from scripts.downstream_consumer_contract import MAX_FIXTURE_BYTES, main

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_FIXTURE_BYTES + 1))
    assert main(["check", "--input", str(oversized)]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "contract_file_invalid"

    assert main(["check", "--input", str(tmp_path)]) == 1
    unreadable_error = capsys.readouterr().err
    assert json.loads(unreadable_error)["code"] == "contract_file_invalid"
    assert str(tmp_path) not in unreadable_error

    assert main(["build", "--output", str(tmp_path)]) == 1
    unwritable_error = capsys.readouterr().err
    assert json.loads(unwritable_error)["code"] == "contract_file_invalid"
    assert str(tmp_path) not in unwritable_error
