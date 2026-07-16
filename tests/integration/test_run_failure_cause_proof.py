from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from scripts import run_failure_cause_proof as proof
from scripts.run_failure_cause_proof import (
    BOUNDARIES,
    EXPECTED_CASE_IDS,
    EXPECTED_INVARIANT_IDS,
    FIXED_TIME,
    LIMITS,
    REPORT_SCHEMA_VERSION,
    build_report,
    render_markdown,
    serialize_report,
    validate_report,
)


def test_report_contract_freezes_exact_case_order():
    assert EXPECTED_CASE_IDS == (
        "completed_null",
        "historical_not_observed",
        "dispatch_schedule_failed",
        "dispatch_start_failed",
        "dispatch_start_timeout",
        "dispatch_lease_expired",
        "execution_call_budget_exceeded",
        "execution_recursion_limit_exceeded",
        "execution_invalid_research_packet",
        "execution_missing_research_packet",
        "execution_timeout",
        "finalization_timeout",
        "execution_cancelled",
        "finalization_cancelled",
        "execution_error",
        "finalization_failed",
    )


EXPECTED_PHASE_CODES = (
    (None, None),
    (None, None),
    ("dispatch", "run_dispatch_schedule_failed"),
    ("dispatch", "run_dispatch_start_failed"),
    ("dispatch", "run_dispatch_start_timeout"),
    ("dispatch", "run_dispatch_lease_expired"),
    ("execution", "call_budget_exceeded"),
    ("execution", "recursion_limit_exceeded"),
    ("execution", "invalid_research_packet"),
    ("execution", "missing_research_packet"),
    ("execution", "run_timeout"),
    ("finalization", "run_timeout"),
    ("execution", "cancelled"),
    ("finalization", "cancelled"),
    ("execution", "execution_error"),
    ("finalization", "run_finalization_failed"),
)


def test_report_contract_freezes_top_level_cases_and_invariant_order():
    report = build_report()

    assert set(report) == {
        "schema_version",
        "status",
        "source",
        "fixed_time",
        "cases",
        "invariants",
        "boundaries",
        "limits",
    }
    assert report["schema_version"] == "dra.run-failure-cause-proof.v1"
    assert report["status"] == "valid"
    assert report["source"] == "production_path_deterministic_local"
    assert report["fixed_time"] == "2026-07-16T00:00:00+00:00"
    assert [item["case_id"] for item in report["cases"]] == list(
        EXPECTED_CASE_IDS
    )
    assert [
        (
            item["observations"]["phase"],
            item["observations"]["code"],
        )
        for item in report["cases"]
    ] == list(EXPECTED_PHASE_CODES)
    assert [item["invariant_id"] for item in report["invariants"]] == [
        "retry_attempts_have_no_cause",
        "dispatch_codes_match",
        "terminal_insert_fault_rolls_back",
        "terminal_guards_fail_closed",
        "first_cause_is_immutable",
        "restart_projection_is_identical",
        "termination_ownership_is_distinct",
        "prestart_cancellation_is_infrastructure_only",
        "inner_self_cancel_is_bounded",
        "launched_terminal_task_settles",
        "public_failure_surface_is_redacted",
        "bounded_cli_inputs_fail_closed",
        "fresh_outputs_are_byte_identical",
    ]
    assert all(item["status"] == "passed" for item in report["cases"])
    assert all(item["status"] == "passed" for item in report["invariants"])
    assert report["boundaries"] == BOUNDARIES
    assert report["limits"] == LIMITS
    assert validate_report(report) is report


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("schema_version", "unsupported"),
        lambda value: value.__setitem__("fixed_time", "dynamic"),
        lambda value: value["cases"].reverse(),
        lambda value: value["cases"][2]["observations"].__setitem__(
            "code", "execution_error"
        ),
        lambda value: value["cases"][0]["observations"].__setitem__(
            "extra", True
        ),
        lambda value: value["cases"][0]["observations"].__setitem__(
            "state_version", 2.0
        ),
        lambda value: value["cases"][0]["observations"].__setitem__(
            "timestamp_aligned", 1
        ),
        lambda value: value["cases"][0]["observations"].__setitem__(
            "evidence_count", False
        ),
        lambda value: value["invariants"].pop(),
        lambda value: value["invariants"].reverse(),
        lambda value: value["boundaries"].__setitem__(
            "live_provider_result", "proven"
        ),
        lambda value: value.__setitem__("limits", [*LIMITS, "/private/path"]),
        lambda value: value.__setitem__("extra", "invalid"),
    ],
)
def test_validator_and_serializers_reject_contract_drift(mutate):
    report = deepcopy(build_report())
    mutate(report)

    with pytest.raises(ValueError, match="run_failure_cause_proof_report_invalid"):
        validate_report(report)
    with pytest.raises(ValueError, match="run_failure_cause_proof_report_invalid"):
        serialize_report(report)


def test_serializers_are_stable_and_markdown_carries_exact_contract():
    first = build_report()
    second = build_report()

    assert REPORT_SCHEMA_VERSION == "dra.run-failure-cause-proof.v1"
    assert FIXED_TIME == "2026-07-16T00:00:00+00:00"
    assert serialize_report(first) == serialize_report(second)
    markdown = render_markdown(first)
    assert markdown == render_markdown(second)
    assert markdown.startswith("# Durable Run Failure Cause v1 Proof\n")
    assert all(case_id in markdown for case_id in EXPECTED_CASE_IDS)
    assert all(invariant_id in markdown for invariant_id in EXPECTED_INVARIANT_IDS)


@pytest.mark.parametrize(
    "boundary",
    (
        "repository_create",
        "historical_migration",
        "worker_dispatch",
        "server_scheduler",
    ),
)
def test_first_six_cases_fail_closed_when_real_production_boundary_breaks(
    boundary,
    monkeypatch,
):
    modules = proof._load_production_modules()

    def broken_sync(*_args, **_kwargs):
        raise RuntimeError("injected production boundary failure")

    async def broken_async(*_args, **_kwargs):
        raise RuntimeError("injected production boundary failure")

    if boundary == "repository_create":
        monkeypatch.setattr(modules.repository, "create_run", broken_sync)
    elif boundary == "historical_migration":
        monkeypatch.setattr(modules.migrations, "migrate_with_backup", broken_sync)
    elif boundary == "worker_dispatch":
        monkeypatch.setattr(
            modules.worker.RunDispatchWorker,
            "dispatch_run",
            broken_async,
        )
    else:
        monkeypatch.setattr(modules.server, "_schedule_run_dispatch", broken_sync)

    with pytest.raises((RuntimeError, ValueError)):
        build_report()


@pytest.mark.parametrize(
    "boundary",
    ("native_harness", "execution_service", "packet_resolver"),
)
def test_framework_and_packet_cases_fail_closed_at_real_adapter_boundaries(
    boundary,
    monkeypatch,
):
    proof._load_production_modules()
    import agent.deepagents_harness as harness_module
    import agent.run_result as run_result_module
    import api.research_execution_service as service_module

    async def broken_async(*_args, **_kwargs):
        raise RuntimeError("injected adapter boundary failure")

    def broken_sync(*_args, **_kwargs):
        raise RuntimeError("injected packet resolution failure")

    if boundary == "native_harness":
        monkeypatch.setattr(
            harness_module.DeepAgentsHarness,
            "execute",
            broken_async,
        )
    elif boundary == "execution_service":
        monkeypatch.setattr(
            service_module.ResearchExecutionService,
            "execute",
            broken_async,
        )
    else:
        monkeypatch.setattr(
            run_result_module,
            "_resolve_talent_packets",
            broken_sync,
        )

    with pytest.raises((RuntimeError, ValueError)):
        build_report()


@pytest.mark.parametrize(
    "boundary",
    ("checkpoint_request", "cancellation_callback", "failure_finalizer"),
)
def test_timeout_cancellation_and_error_cases_require_real_server_owners(
    boundary,
    monkeypatch,
):
    modules = proof._load_production_modules()

    async def no_checkpoint(self):
        return None

    async def no_cancel_callback(*_args, **_kwargs):
        return None

    async def broken_finalizer(*_args, **_kwargs):
        raise RuntimeError("injected typed finalizer failure")

    if boundary == "checkpoint_request":
        monkeypatch.setattr(
            modules.tracker.FinalizationCheckpoint,
            "request_and_wait",
            no_checkpoint,
        )
    elif boundary == "cancellation_callback":
        monkeypatch.setattr(
            modules.server,
            "_mark_dispatched_cancellation",
            no_cancel_callback,
        )
    else:
        monkeypatch.setattr(
            modules.server,
            "_finalize_failed_run_v2",
            broken_finalizer,
        )

    with pytest.raises((RuntimeError, ValueError, TimeoutError)):
        build_report()


@pytest.mark.parametrize("boundary", ("repository_finalizer", "restart_reader"))
def test_invariant_observations_require_real_transaction_and_restart_paths(
    boundary,
    monkeypatch,
):
    modules = proof._load_production_modules()

    def broken(*_args, **_kwargs):
        raise RuntimeError("injected invariant boundary failure")

    if boundary == "repository_finalizer":
        monkeypatch.setattr(
            modules.repository,
            "finalize_run_transaction",
            broken,
        )
    else:
        monkeypatch.setattr(proof.subprocess, "run", broken)

    with pytest.raises((RuntimeError, ValueError)):
        build_report()


def test_cli_build_and_check_use_exact_stable_output(tmp_path, capsys):
    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"

    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"status":"built"}\n'
    assert captured.err == ""
    report = validate_report(json.loads(json_output.read_text(encoding="utf-8")))
    assert markdown_output.read_text(encoding="utf-8") == render_markdown(report)

    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_output),
            "--markdown-baseline",
            str(markdown_output),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"status":"valid","match":true}\n'
    assert captured.err == ""


@pytest.mark.parametrize(
    "arguments",
    (
        [],
        ["unknown"],
        ["build"],
        ["build", "--json-output", "candidate.json"],
        ["check", "extra"],
        ["check", "--unknown-option"],
    ),
)
def test_file_entrypoint_invalid_arguments_are_one_stable_error_line(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/run_failure_cause_proof.py", *arguments],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        '{"status":"invalid","code":"run_failure_cause_proof_invalid"}\n'
    )


@pytest.mark.parametrize("arguments", (["--help"], ["build", "--help"], ["check", "--help"]))
def test_help_paths_succeed_and_import_is_silent(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/run_failure_cause_proof.py", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 0
    assert completed.stdout.startswith("usage:")
    assert completed.stderr == ""

    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import scripts.run_failure_cause_proof; "
                "raise SystemExit(1 if any(name in sys.modules for name in "
                "('api.server','agent.main_agent','agent.llm')) else 0)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "API_SECRET"}
        }
        | {"PYTHON_DOTENV_DISABLED": "1"},
    )
    assert imported.returncode == 0
    assert imported.stdout == imported.stderr == ""


@pytest.mark.parametrize(
    "mode",
    ("missing", "corrupt", "oversized", "symlink", "directory", "incoherent"),
)
def test_check_rejects_invalid_baselines_with_bounded_stable_error(
    mode,
    tmp_path,
    capsys,
):
    valid_report = build_report()
    json_path = tmp_path / "baseline.json"
    markdown_path = tmp_path / "baseline.md"
    json_path.write_bytes(serialize_report(valid_report))
    markdown_path.write_text(render_markdown(valid_report), encoding="utf-8")
    if mode == "missing":
        json_path.unlink()
    elif mode == "corrupt":
        json_path.write_bytes(b"{not-json")
    elif mode == "oversized":
        json_path.write_bytes(b"x" * (proof.MAX_BASELINE_BYTES + 1))
    elif mode == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(serialize_report(valid_report))
        json_path.unlink()
        json_path.symlink_to(target)
    elif mode == "directory":
        json_path.unlink()
        json_path.mkdir()
    else:
        markdown_path.write_text("# stale\n", encoding="utf-8")

    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_path),
            "--markdown-baseline",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"run_failure_cause_proof_invalid"}\n'
    )
    assert str(json_path) not in captured.err


def _assert_invalid_cli(capsys):
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"run_failure_cause_proof_invalid"}\n'
    )


@pytest.mark.parametrize(
    "mode",
    (
        "same",
        "hardlink",
        "symlink",
        "directory",
        "missing_parent",
        "unwritable_parent",
    ),
)
def test_build_validates_both_output_paths_before_building(
    mode,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    restore_mode = None
    if mode == "same":
        markdown_path = json_path
    elif mode == "hardlink":
        json_path.write_text("old", encoding="utf-8")
        os.link(json_path, markdown_path)
    elif mode == "symlink":
        target = tmp_path / "target.md"
        target.write_text("old", encoding="utf-8")
        markdown_path.symlink_to(target)
    elif mode == "directory":
        markdown_path.mkdir()
    elif mode == "missing_parent":
        markdown_path = tmp_path / "missing" / "candidate.md"
    else:
        output_dir = tmp_path / "locked"
        output_dir.mkdir()
        restore_mode = output_dir.stat().st_mode
        output_dir.chmod(0o500)
        json_path = output_dir / "candidate.json"
        markdown_path = output_dir / "candidate.md"

    def unexpected_build():
        pytest.fail("invalid output paths must fail before report construction")

    monkeypatch.setattr(proof, "build_report", unexpected_build)
    try:
        assert proof.main(
            [
                "build",
                "--json-output",
                str(json_path),
                "--markdown-output",
                str(markdown_path),
            ]
        ) == 1
    finally:
        if restore_mode is not None:
            json_path.parent.chmod(restore_mode)
    _assert_invalid_cli(capsys)


@pytest.mark.parametrize("failure_index", (1, 2))
def test_build_write_failure_preserves_targets_and_cleans_sibling_temps(
    failure_index,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    json_path.write_bytes(b"old-json")
    markdown_path.write_bytes(b"old-markdown")
    report = build_report()
    monkeypatch.setattr(proof, "build_report", lambda: report)
    real_stage = proof._stage_output
    calls = 0

    def fail_selected_write(target, content):
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected write failure")
        return real_stage(target, content)

    monkeypatch.setattr(proof, "_stage_output", fail_selected_write)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    _assert_invalid_cli(capsys)
    assert json_path.read_bytes() == b"old-json"
    assert markdown_path.read_bytes() == b"old-markdown"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "candidate.json",
        "candidate.md",
    ]


@pytest.mark.parametrize("failure_index", (1, 2))
def test_build_replace_failure_leaves_only_whole_files_and_cleans_temps(
    failure_index,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    json_path.write_bytes(b"old-json")
    markdown_path.write_bytes(b"old-markdown")
    report = build_report()
    expected_json = serialize_report(report)
    monkeypatch.setattr(proof, "build_report", lambda: report)
    real_replace = proof.os.replace
    calls = 0

    def fail_selected_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(proof.os, "replace", fail_selected_replace)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    _assert_invalid_cli(capsys)
    assert json_path.read_bytes() == (
        b"old-json" if failure_index == 1 else expected_json
    )
    assert markdown_path.read_bytes() == b"old-markdown"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "candidate.json",
        "candidate.md",
    ]


def test_stage_output_cleans_temp_on_non_os_write_exception(
    tmp_path,
    monkeypatch,
):
    real_named_temporary_file = proof.tempfile.NamedTemporaryFile

    class FailingWriteProxy:
        def __init__(self, handle):
            self._handle = handle
            self.name = handle.name

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def write(self, _content):
            self._handle.write(b"partial")
            raise RuntimeError("injected non-os write failure")

    def failing_named_temporary_file(*args, **kwargs):
        return FailingWriteProxy(real_named_temporary_file(*args, **kwargs))

    monkeypatch.setattr(
        proof.tempfile,
        "NamedTemporaryFile",
        failing_named_temporary_file,
    )
    with pytest.raises(proof._ProofError):
        proof._stage_output(tmp_path / "candidate.json", b"content")
    assert list(tmp_path.iterdir()) == []


def test_cli_maps_unexpected_database_error_to_stable_fail_closed_output(
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    json_path.write_bytes(b"old-json")
    markdown_path.write_bytes(b"old-markdown")

    def unavailable_database():
        raise sqlite3.DatabaseError("private database diagnostic")

    monkeypatch.setattr(proof, "build_report", unavailable_database)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    _assert_invalid_cli(capsys)
    assert json_path.read_bytes() == b"old-json"
    assert markdown_path.read_bytes() == b"old-markdown"


@pytest.fixture(scope="module")
def mutation_baselines(tmp_path_factory):
    root = tmp_path_factory.mktemp("run-failure-cause-mutation-baseline")
    json_path = root / "baseline.json"
    markdown_path = root / "baseline.md"
    report = build_report()
    json_path.write_bytes(serialize_report(report))
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


@pytest.mark.parametrize(
    "mutation",
    (
        "failure_mapper",
        "dispatch_cause_insert",
        "terminal_cause_insert",
        "status_projection",
        "timeout_callback",
        "tracked_task",
        "shield_settlement",
        "finalization_checkpoint",
        "timeout_origin_ordering",
    ),
)
def test_check_fails_when_real_production_authority_is_mutated(
    mutation,
    mutation_baselines,
    monkeypatch,
    capsys,
):
    modules = proof._load_production_modules()
    if mutation == "failure_mapper":
        from api.run_failure_cause_models import RunFailureCauseWrite

        real_mapper = modules.server._execution_failure_cause

        def wrong_mapper(failure_kind):
            if failure_kind == "call_budget_exceeded":
                return RunFailureCauseWrite(
                    phase="execution",
                    code="execution_error",
                )
            return real_mapper(failure_kind)

        monkeypatch.setattr(modules.server, "_execution_failure_cause", wrong_mapper)
    elif mutation == "dispatch_cause_insert":
        real_terminalize = modules.dispatch._terminalize_leased_dispatch

        def drop_dispatch_cause(connection, *, row, failure_cause, now):
            won = real_terminalize(
                connection,
                row=row,
                failure_cause=failure_cause,
                now=now,
            )
            if won:
                connection.execute(
                    "DELETE FROM run_failure_causes_v1 WHERE run_id = ?",
                    (row["run_id"],),
                )
            return won

        monkeypatch.setattr(
            modules.dispatch,
            "_terminalize_leased_dispatch",
            drop_dispatch_cause,
        )
    elif mutation == "terminal_cause_insert":
        real_finalize = modules.server.finalize_run_transaction

        def drop_terminal_cause(**kwargs):
            if kwargs.get("execution_status") == "failed":
                kwargs["failure_cause"] = None
            return real_finalize(**kwargs)

        monkeypatch.setattr(
            modules.server,
            "finalize_run_transaction",
            drop_terminal_cause,
        )
    elif mutation == "status_projection":
        monkeypatch.setattr(
            modules.repository,
            "_failure_cause_projection",
            lambda _row: None,
        )
    elif mutation == "timeout_callback":

        async def omit_timeout_callback(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            modules.server,
            "_mark_dispatched_timeout",
            omit_timeout_callback,
        )
    elif mutation == "tracked_task":

        def create_untracked(coroutine, _task_id, **_kwargs):
            return proof.asyncio.create_task(coroutine)

        monkeypatch.setattr(
            modules.server,
            "create_tracked_task",
            create_untracked,
        )
    elif mutation == "shield_settlement":

        async def abandon_shield(task):
            try:
                return await task, None, 0
            except BaseException as error:
                return None, error, 0

        monkeypatch.setattr(
            modules.server,
            "settle_shielded_task",
            abandon_shield,
        )
    elif mutation == "finalization_checkpoint":

        async def omit_checkpoint_request(self):
            del self

        monkeypatch.setattr(
            modules.tracker.FinalizationCheckpoint,
            "request_and_wait",
            omit_checkpoint_request,
        )
    else:

        def timeout_claims_cancelled(self):
            return self.claim_cancelled()

        monkeypatch.setattr(
            modules.tracker.TerminationOrigin,
            "claim_timeout",
            timeout_claims_cancelled,
        )

    json_path, markdown_path = mutation_baselines
    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_path),
            "--markdown-baseline",
            str(markdown_path),
        ]
    ) == 1
    _assert_invalid_cli(capsys)


@pytest.mark.parametrize("removed_target", proof.CLOCK_PATCH_TARGETS)
def test_check_fails_when_any_serialized_clock_patch_alias_is_removed(
    removed_target,
    mutation_baselines,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        proof,
        "CLOCK_PATCH_TARGETS",
        tuple(
            target
            for target in proof.CLOCK_PATCH_TARGETS
            if target != removed_target
        ),
    )
    json_path, markdown_path = mutation_baselines
    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_path),
            "--markdown-baseline",
            str(markdown_path),
        ]
    ) == 1
    _assert_invalid_cli(capsys)


def test_two_fresh_cli_builds_are_byte_identical_and_public_safe(
    tmp_path,
    capsys,
):
    output_pairs = [
        (tmp_path / f"fresh-{index}.json", tmp_path / f"fresh-{index}.md")
        for index in (1, 2)
    ]
    for json_path, markdown_path in output_pairs:
        assert proof.main(
            [
                "build",
                "--json-output",
                str(json_path),
                "--markdown-output",
                str(markdown_path),
            ]
        ) == 0
        captured = capsys.readouterr()
        assert captured.out == '{"status":"built"}\n'
        assert captured.err == ""

    first_json = output_pairs[0][0].read_bytes()
    first_markdown = output_pairs[0][1].read_bytes()
    assert first_json == output_pairs[1][0].read_bytes()
    assert first_markdown == output_pairs[1][1].read_bytes()
    public_bytes = first_json + b"\n" + first_markdown
    forbidden_markers = (
        proof._RAW_EXCEPTION_MARKER,
        proof._RAW_CREDENTIAL_MARKER,
        proof._RAW_UNIX_PATH_MARKER,
        proof._RAW_WINDOWS_PATH_MARKER,
        proof._RAW_HOST_MARKER,
        proof._RAW_PROVIDER_MARKER,
        proof._RAW_QUERY_MARKER,
        "Traceback (most recent call last)",
        "/Users/",
        "/private/tmp/",
        "C:\\Users\\",
        "api.openai.com",
        "ModelCallLimitExceededError",
        "ToolCallLimitExceededError",
        "GraphRecursionError",
        "dra-failure-cause-proof-",
    )
    assert all(marker.encode("utf-8") not in public_bytes for marker in forbidden_markers)


def test_ci_runs_failure_cause_proof_after_dispatch_proof_before_broad_pytest():
    workflow = (Path.cwd() / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    dispatch_index = workflow.index(
        "- name: Run deterministic run dispatch reconciliation proof"
    )
    proof_index = workflow.index("- name: Run failure cause proof")
    pytest_index = workflow.index("- name: Run tests")
    assert dispatch_index < proof_index < pytest_index
    assert workflow.count("- name: Run failure cause proof") == 1
    step = workflow[proof_index:pytest_index]
    assert step == (
        "- name: Run failure cause proof\n"
        "        run: python scripts/run_failure_cause_proof.py check\n"
        "      "
    )
    assert all(
        marker not in step.lower()
        for marker in ("env:", "credential", "service", "provider", "network")
    )
