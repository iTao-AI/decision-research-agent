import json
import os
import re
import subprocess
import sys

from scripts.run_creation_idempotency_proof import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    build_report,
    render_markdown,
    serialize_report,
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
