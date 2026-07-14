import json
import os
import re
import subprocess
import sys
from copy import deepcopy

import pytest

from scripts.run_creation_idempotency_proof import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    BOUNDARIES,
    LIMITS,
    MAX_REPORT_BYTES,
    _bounded_read,
    _case,
    build_report,
    main,
    render_markdown,
    serialize_report,
    validate_report,
)


EXPECTED_CASE_IDS = [
    "lost_response_replay",
    "request_conflict",
    "concurrent_duplicate_serialization",
    "durable_restart_lookup",
    "unkeyed_independence",
    "raw_key_non_persistence",
    "tool_client_key_recovery",
]


def test_report_uses_exact_cases_and_honest_boundary():
    report = build_report()
    assert report["schema_version"] == "dra.run-creation-idempotency-proof.v1"
    assert report["status"] == "valid"
    assert [case["case_id"] for case in report["cases"]] == EXPECTED_CASE_IDS
    assert all(case["status"] == "passed" for case in report["cases"])
    assert report["boundaries"] == {
        "client_response_loss_after_scheduling": "proven",
        "durable_identity_lookup_after_restart": "proven",
        "crash_before_schedule_recovery": "not_proven",
        "exactly_once_execution": "not_claimed",
    }


def test_case_rejects_false_or_wrong_semantic_observations():
    with pytest.raises(ValueError, match="run_idempotency_proof_report_invalid"):
        _case("lost_response_replay", same_identity=False)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report["cases"][0]["observations"].__setitem__(
            "same_identity", False
        ),
        lambda report: report["cases"][2]["observations"].__setitem__(
            "new_count", 2
        ),
        lambda report: report["cases"][0]["observations"].__setitem__(
            "unexpected", True
        ),
        lambda report: report["cases"].pop(),
        lambda report: report["cases"].append(deepcopy(report["cases"][0])),
        lambda report: report["cases"].reverse(),
        lambda report: report.__setitem__("schema_version", "unsupported"),
        lambda report: report["boundaries"].__setitem__(
            "crash_before_schedule_recovery", "proven"
        ),
        lambda report: report.__setitem__("limits", [*LIMITS, "/private/path"]),
        lambda report: report.__setitem__("extra", "not public"),
    ],
)
def test_report_validation_rejects_contract_and_semantic_drift(mutate):
    report = build_report()
    mutate(report)
    with pytest.raises(ValueError, match="run_idempotency_proof_report_invalid"):
        validate_report(report)
    with pytest.raises(ValueError, match="run_idempotency_proof_report_invalid"):
        serialize_report(report)


def test_report_validator_accepts_only_exact_boundaries_and_limits():
    report = build_report()
    assert report["boundaries"] == BOUNDARIES
    assert report["limits"] == LIMITS
    assert validate_report(report) is report


def test_report_bytes_are_deterministic_and_match_committed_evidence():
    first = build_report()
    second = build_report()
    assert serialize_report(first) == serialize_report(second)
    assert render_markdown(first) == render_markdown(second)
    assert BASELINE_JSON_PATH.read_bytes() == serialize_report(first)
    assert BASELINE_MARKDOWN_PATH.read_text(encoding="utf-8") == render_markdown(first)


def test_check_entrypoint_is_stable_json_and_network_free():
    completed = subprocess.run(
        [sys.executable, "scripts/run_creation_idempotency_proof.py", "check"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"status": "valid", "match": True}
    assert completed.stderr == ""


@pytest.mark.parametrize("arguments", [[], ["unknown"], ["check", "extra"]])
def test_invalid_cli_arguments_use_stable_error_boundary(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/run_creation_idempotency_proof.py", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "status": "invalid",
        "code": "run_idempotency_proof_baseline_invalid",
    }
    assert len(completed.stderr.splitlines()) == 1


def test_help_remains_successful_and_import_is_silent():
    help_result = subprocess.run(
        [sys.executable, "scripts/run_creation_idempotency_proof.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert help_result.returncode == 0
    assert "usage:" in help_result.stdout
    assert help_result.stderr == ""
    imported = subprocess.run(
        [sys.executable, "-c", "import scripts.run_creation_idempotency_proof"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert imported.returncode == 0
    assert imported.stdout == imported.stderr == ""


@pytest.mark.parametrize("mode", ["missing", "corrupt", "oversized"])
def test_check_fails_stably_for_invalid_committed_baseline(
    tmp_path, monkeypatch, capsys, mode
):
    import scripts.run_creation_idempotency_proof as proof

    json_path = tmp_path / "baseline.json"
    markdown_path = tmp_path / "baseline.md"
    markdown_path.write_text("invalid", encoding="utf-8")
    if mode == "corrupt":
        json_path.write_bytes(b"{not-json")
    elif mode == "oversized":
        json_path.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
    monkeypatch.setattr(proof, "BASELINE_JSON_PATH", json_path)
    monkeypatch.setattr(proof, "BASELINE_MARKDOWN_PATH", markdown_path)

    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid",
        "code": "run_idempotency_proof_baseline_invalid",
    }


def test_bounded_read_rejects_oversized_input(tmp_path):
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
    with pytest.raises(ValueError, match="run_idempotency_proof_baseline_invalid"):
        _bounded_read(oversized)


def test_render_entrypoints_match_exact_bytes():
    report = build_report()
    for command, expected in (
        ("json", serialize_report(report).decode("utf-8")),
        ("markdown", render_markdown(report)),
    ):
        completed = subprocess.run(
            [sys.executable, "scripts/run_creation_idempotency_proof.py", command],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
        )
        assert completed.returncode == 0
        assert completed.stdout == expected
        assert completed.stderr == ""


def test_public_report_contains_no_runtime_identity_or_private_marker():
    rendered = serialize_report(build_report()).decode("utf-8")
    assert re.search(r'"run_[0-9a-f]{16,}"', rendered) is None
    for marker in (
        "raw-key",
        "/Users/",
        "API_SECRET",
        "Career",
        "Night Voyager",
    ):
        assert marker not in rendered
