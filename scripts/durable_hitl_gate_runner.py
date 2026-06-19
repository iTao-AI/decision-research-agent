from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


GATE_TESTS = {
    "gate_01_restart_recovery":
        "tests/integration/test_durable_review_restart.py::"
        "test_restart_recovers_checkpoint_pending",
    "gate_02_container_persistence":
        "tests/integration/test_durable_review_container.py::"
        "test_backend_container_restart_preserves_review_state",
    "gate_03_duplicate_idempotency":
        "tests/integration/test_durable_review_api.py::"
        "test_decision_api_accepts_and_replays_same_request",
    "gate_04_decision_before_resume":
        "tests/integration/test_durable_review_restart.py::"
        "test_restart_recovers_decision_committed_before_resume",
    "gate_05_replay_safety":
        "tests/unit/test_review_repository.py::"
        "test_approval_resolution_is_exactly_once",
    "gate_06_conflicting_decision":
        "tests/integration/test_durable_review_api.py::"
        "test_conflicting_decision_returns_actionable_409",
    "gate_07_checkpoint_failure":
        "tests/integration/test_durable_review_restart.py::"
        "test_corrupt_checkpoint_after_resume_attempt_is_manual_recovery",
    "gate_08_migration_restore":
        "tests/unit/test_review_migrations.py::"
        "test_review_schema_backup_restore_removes_additive_tables",
    "gate_09_auth_fail_closed":
        "tests/integration/test_durable_review_api.py::"
        "test_enabled_decision_api_fails_closed_without_api_secret",
    "gate_10_unresolved_not_deliverable":
        "tests/integration/test_durable_review_lifecycle.py::"
        "test_required_review_remains_not_deliverable_before_resolution",
    "gate_11_lease_reclaim":
        "tests/unit/test_review_repository.py::"
        "test_expired_lease_is_reclaimed_without_new_segment",
    "gate_12_sync_durability":
        "tests/integration/test_review_checkpoint_compatibility.py::"
        "test_sqlite_checkpoint_reopens_and_resumes_with_sync_durability",
    "gate_13_sigkill_windows":
        "tests/integration/test_durable_review_kill9.py::"
        "test_sigkill_window_converges_without_duplicate_state",
}


def build_report(results: dict[str, bool]) -> dict:
    failed = [name for name, passed in sorted(results.items()) if not passed]
    return {
        "status": "PASS" if not failed and len(results) == 13 else "NO_GO",
        "expected": 13,
        "passed": sum(results.values()),
        "failed": failed,
        "results": results,
    }


def _pytest_gate_passed(
    completed: subprocess.CompletedProcess[str],
) -> bool:
    output = f"{completed.stdout}\n{completed.stderr}"
    skipped = re.search(r"\b\d+\s+skipped\b", output, flags=re.IGNORECASE)
    return completed.returncode == 0 and skipped is None


def run_gate_tests() -> dict[str, bool]:
    results = {}
    for gate_name, node_id in GATE_TESTS.items():
        command = [sys.executable, "-m", "pytest", node_id, "-q"]
        env = os.environ.copy()
        if gate_name == "gate_02_container_persistence":
            env["DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS"] = "true"
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        results[gate_name] = _pytest_gate_passed(completed)
        if not results[gate_name]:
            print(completed.stdout, file=sys.stderr)
            print(completed.stderr, file=sys.stderr)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_report(run_gate_tests())
    encoded = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
