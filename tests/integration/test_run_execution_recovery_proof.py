from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_execution_recovery_proof.py"
CASE_IDS = [
    "exclusive_writer_fail_closed",
    "migration_backfill_restore",
    "execution_phase_sigkill",
    "finalization_phase_sigkill",
    "stale_generation_fenced",
    "explicit_replacement_replay",
    "old_revision_rollback",
    "retained_contracts",
]
BOUNDARIES = {
    "process_lifetime_single_writer_gate": "proven",
    "single_node_startup_convergence": "proven",
    "execution_phase_interruption_classification": "proven",
    "finalization_phase_interruption_classification": "proven",
    "explicit_one_hop_replacement": "proven",
    "provider_free_contract": "proven",
    "exact_resume": "not_claimed",
    "exactly_once_execution": "not_claimed",
    "external_side_effect_deduplication": "not_claimed",
    "multi_instance_high_availability": "not_claimed",
    "live_provider_result": "not_observed",
    "automatic_release_or_rollback": "not_claimed",
}
LIMITS = [
    "Provider-free contract proof, not a production reliability measurement.",
    "Startup convergence is single-node and startup-only.",
    "Replacement creation does not deduplicate provider or tool side effects.",
    "No exact resume, automatic release, or business impact is observed.",
]
STAGE_CODES = {
    "writer": "run_execution_recovery_proof_writer_lock_failed",
    "migration": "run_execution_recovery_proof_migration_failed",
    "execution": "run_execution_recovery_proof_execution_sigkill_failed",
    "finalization": "run_execution_recovery_proof_finalization_sigkill_failed",
    "stale": "run_execution_recovery_proof_stale_generation_failed",
    "replacement": "run_execution_recovery_proof_replacement_failed",
    "rollback_revision": (
        "run_execution_recovery_proof_rollback_revision_unavailable"
    ),
    "rollback_import": "run_execution_recovery_proof_rollback_import_mismatch",
    "rollback_restore": "run_execution_recovery_proof_rollback_restore_failed",
    "rollback_verify": (
        "run_execution_recovery_proof_rollback_old_revision_verify_failed"
    ),
    "retained": "run_execution_recovery_proof_retained_contract_failed",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("recovery_proof", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str, inject: str | None = None):
    environment = os.environ.copy()
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    if inject is not None:
        environment["DRA_RECOVERY_PROOF_INJECT_FAILURE"] = inject
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="module")
def report():
    return _load_module().build_report()


def test_report_has_exact_ordered_cases_boundaries_and_limits(report):
    assert report["schema_version"] == "dra.run-execution-recovery-proof.v1"
    assert report["status"] == "valid"
    assert report["source"] == "provider_free_real_process"
    assert [case["case_id"] for case in report["cases"]] == CASE_IDS
    assert all(case["status"] == "passed" for case in report["cases"])
    assert report["boundaries"] == BOUNDARIES
    assert report["limits"] == LIMITS


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "reordered", "false"],
)
def test_report_validation_rejects_missing_extra_reordered_or_false_values(
    report,
    mutation,
):
    candidate = copy.deepcopy(report)
    if mutation == "missing":
        candidate["cases"].pop()
    elif mutation == "extra":
        candidate["extra"] = True
    elif mutation == "reordered":
        candidate["cases"][0], candidate["cases"][1] = (
            candidate["cases"][1],
            candidate["cases"][0],
        )
    else:
        candidate["cases"][0]["observations"]["overlap_rejected"] = False
    with pytest.raises(ValueError, match="report_invalid"):
        _load_module().validate_report(candidate)


def test_report_bytes_are_deterministic_across_two_isolated_runs():
    first = _run("check")
    second = _run("check")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


def test_report_contains_no_private_identity_path_pid_key_hash_or_query(report):
    encoded = json.dumps(report, sort_keys=True)
    for forbidden in (
        str(ROOT),
        "/tmp/",
        "run_",
        "boot_",
        "owner_",
        "thread_",
        "segment_",
        "key_hash",
        "idempotency_key",
        "query",
        '"pid"',
    ):
        assert forbidden not in encoded


def test_check_has_one_json_stdout_line_and_empty_stderr():
    completed = _run("check")
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout.endswith("\n")
    assert len(completed.stdout.splitlines()) == 1
    assert json.loads(completed.stdout)["status"] == "valid"


def test_invalid_arguments_and_injected_failures_have_stable_stderr():
    invalid = _run("build")
    assert invalid.returncode != 0
    assert invalid.stdout == ""
    assert "usage:" in invalid.stderr.lower()
    failed = _run("check", inject="writer")
    assert failed.returncode == 1
    assert failed.stdout == ""
    assert failed.stderr == STAGE_CODES["writer"] + "\n"


@pytest.mark.parametrize(("stage", "code"), list(STAGE_CODES.items()))
def test_each_proof_stage_maps_to_one_exact_safe_error_code(stage, code):
    completed = _run("check", inject=stage)
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == code + "\n"


@pytest.mark.parametrize(
    "stage",
    [
        "stale_start",
        "stale_phase",
        "stale_finalization_fence",
        "stale_normal",
        "stale_timeout",
        "stale_cancellation",
        "stale_fallback",
    ],
)
def test_stale_generation_stage_maps_every_fence_failure_to_one_safe_code(stage):
    completed = _run("check", inject=stage)
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == STAGE_CODES["stale"] + "\n"


def test_module_import_is_silent_and_help_succeeds():
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util;"
                f"s=importlib.util.spec_from_file_location('p',{str(SCRIPT)!r});"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0
    assert imported.stdout == imported.stderr == ""
    helped = _run("--help")
    assert helped.returncode == 0
    assert helped.stdout
    assert helped.stderr == ""
