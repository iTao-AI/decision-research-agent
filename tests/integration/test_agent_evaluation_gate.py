from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import downstream_consumer_contract
from scripts.agent_evaluation_contracts import (
    CASE_IDS,
    MAX_REPORT_BYTES,
    load_manifest,
    serialize_json,
    validate_comparison,
    validate_report,
)
from scripts.agent_evaluation_gate import (
    BASELINE_JSON_PATH,
    BASELINE_MARKDOWN_PATH,
    build_deterministic_observations,
    build_deterministic_report,
    compare_artifacts,
    main,
    render_markdown,
)


MANIFEST_PATH = Path("benchmarks/agent-evaluation-v1/scenarios.json")


def _manifest() -> dict:
    return load_manifest(MANIFEST_PATH)


def _write_coherent_drift(tmp_path: Path) -> tuple[Path, Path]:
    drifted = build_deterministic_report(_manifest())
    drifted["cases"][0]["status"] = "regression"
    drifted["cases"][0]["expectation_match"] = False
    drifted["summary"]["expectation_mismatch_count"] = 1
    drifted["summary"]["release_gate_passed"] = False
    json_path = tmp_path / "drift.json"
    markdown_path = tmp_path / "drift.md"
    json_path.write_bytes(serialize_json(drifted, validator=validate_report))
    markdown_path.write_text(render_markdown(drifted), encoding="utf-8")
    return json_path, markdown_path


def test_deterministic_builder_uses_fresh_downstream_bundle_not_committed_copy(monkeypatch):
    calls = []
    original = downstream_consumer_contract.build_fixture_bundle

    def tracked_build():
        calls.append("build")
        return original()

    monkeypatch.setattr(downstream_consumer_contract, "build_fixture_bundle", tracked_build)
    report = build_deterministic_report(_manifest())
    assert calls == ["build"]
    assert report["source"] == "deterministic"


def test_observations_have_exact_order_resolved_run_refs_and_do_not_mutate_inputs():
    manifest = _manifest()
    original = copy.deepcopy(manifest)
    observations = build_deterministic_observations(manifest)
    assert [item["case_id"] for item in observations] == list(CASE_IDS)
    assert manifest == original
    canonical = observations[0]
    assert all("run_ref" not in event for event in canonical["trajectory"])
    assert all(
        event["run_id"] == canonical["run"]["run_id"]
        for event in canonical["trajectory"]
    )
    cross_run = observations[-1]
    assert any(
        event["run_id"] == "run_evaluation_foreign"
        for event in cross_run["trajectory"]
    )


def test_report_has_exact_contract_expected_cases_and_deterministic_bytes():
    report = build_deterministic_report(_manifest())
    assert validate_report(report) == report
    assert report["summary"] == {
        "blocking_regression_count": 0,
        "expectation_mismatch_count": 0,
        "observational_change_count": 2,
        "not_observed_count": 9,
        "release_gate_passed": True,
    }
    assert [case["case_id"] for case in report["cases"]] == list(CASE_IDS)
    assert serialize_json(report, validator=validate_report) == serialize_json(
        build_deterministic_report(_manifest()), validator=validate_report
    )
    markdown = render_markdown(report)
    assert "dra.agent-evaluation-report.v1" in markdown
    assert "canonical_success" in markdown
    assert all(limit in markdown for limit in report["limits"])
    assert "Public-safe contract proof" not in markdown


def test_compare_artifacts_reports_exact_match_and_coherent_drift():
    report = build_deterministic_report(_manifest())
    markdown = render_markdown(report)
    baseline_json = serialize_json(report, validator=validate_report)
    baseline_markdown = markdown.encode("utf-8")
    matched = compare_artifacts(report, markdown, baseline_json, baseline_markdown)
    assert validate_comparison(matched) == matched
    assert matched["match"] is True
    assert matched["changed_case_ids"] == []

    drifted = copy.deepcopy(report)
    drifted["cases"][0]["status"] = "regression"
    drifted["cases"][0]["expectation_match"] = False
    drifted["summary"]["expectation_mismatch_count"] = 1
    drifted["summary"]["release_gate_passed"] = False
    drift_markdown = render_markdown(drifted)
    comparison = compare_artifacts(
        report,
        markdown,
        serialize_json(drifted, validator=validate_report),
        drift_markdown.encode("utf-8"),
    )
    assert comparison["match"] is False
    assert comparison["changed_case_ids"] == ["canonical_success"]


def test_committed_baselines_match_fresh_build():
    report = build_deterministic_report(_manifest())
    markdown = render_markdown(report)
    comparison = compare_artifacts(
        report,
        markdown,
        BASELINE_JSON_PATH.read_bytes(),
        BASELINE_MARKDOWN_PATH.read_bytes(),
    )
    assert comparison["match"] is True


def test_cli_build_writes_distinct_candidates_and_check_matches(tmp_path, capsys):
    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"
    assert main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 0
    assert capsys.readouterr() == (json.dumps({"status": "built"}, separators=(",", ":")) + "\n", "")
    assert validate_report(json.loads(json_output.read_text(encoding="utf-8")))
    assert markdown_output.read_text(encoding="utf-8").startswith("# Agent Evaluation")

    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["match"] is True
    assert captured.err == ""


@pytest.mark.parametrize("same_path", [True, False])
def test_cli_refuses_same_path_and_committed_baseline_alias(tmp_path, capsys, same_path):
    json_output = tmp_path / "candidate.json"
    markdown_output = json_output if same_path else tmp_path / "baseline-link.md"
    if not same_path:
        markdown_output.symlink_to(BASELINE_MARKDOWN_PATH.resolve())
    assert main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid",
        "code": "evaluation_output_invalid",
    }
    assert not json_output.exists()


def test_cli_rejects_missing_parent_and_cleans_sibling_temps(tmp_path, capsys):
    missing = tmp_path / "missing"
    assert main(
        [
            "build",
            "--json-output",
            str(missing / "candidate.json"),
            "--markdown-output",
            str(tmp_path / "candidate.md"),
        ]
    ) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "evaluation_output_invalid"
    assert not missing.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_cli_invalid_manifest_hides_pydantic_details_and_writes_no_report(
    tmp_path, monkeypatch, capsys
):
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps({"schema_version": "dra.agent-evaluation-cases.v1", "cases": "bad"}),
        encoding="utf-8",
    )
    output = tmp_path / "candidate.json"
    from scripts import agent_evaluation_gate as module

    monkeypatch.setattr(module, "MANIFEST_PATH", invalid)
    assert main(
        [
            "build",
            "--json-output",
            str(output),
            "--markdown-output",
            str(tmp_path / "candidate.md"),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "status": "invalid",
        "code": "evaluation_manifest_invalid",
    }
    assert all(
        marker not in captured.err
        for marker in ("ValidationError", "cases", "input_value", str(invalid), "Traceback")
    )
    assert not output.exists()


def test_cli_maps_invalid_baseline_and_comparison_output_failure(tmp_path, monkeypatch, capsys):
    from scripts import agent_evaluation_gate as module

    missing = tmp_path / "missing.json"
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", missing)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_baseline_invalid"

    monkeypatch.setattr(module, "BASELINE_JSON_PATH", BASELINE_JSON_PATH)
    drifted = json.loads(BASELINE_JSON_PATH.read_text(encoding="utf-8"))
    drifted["cases"][0]["status"] = "regression"
    drifted["cases"][0]["expectation_match"] = False
    drifted["summary"]["expectation_mismatch_count"] = 1
    drifted["summary"]["release_gate_passed"] = False
    drift_json = tmp_path / "drift.json"
    drift_md = tmp_path / "drift.md"
    drift_json.write_bytes(serialize_json(drifted, validator=validate_report))
    drift_md.write_text(render_markdown(drifted), encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", drift_json)
    monkeypatch.setattr(module, "BASELINE_MARKDOWN_PATH", drift_md)
    assert main(["check", "--comparison-output", str(tmp_path / "missing" / "out.json")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_output_invalid"


def test_real_check_cli_emits_comparison_only_for_coherent_drift(tmp_path):
    drift_json, drift_markdown = _write_coherent_drift(tmp_path)
    code = f"""
from pathlib import Path
from scripts import agent_evaluation_gate as module
module.BASELINE_JSON_PATH = Path({str(drift_json)!r})
module.BASELINE_MARKDOWN_PATH = Path({str(drift_markdown)!r})
raise SystemExit(module.main(['check']))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 1
    assert completed.stderr == ""
    comparison = json.loads(completed.stdout)
    assert comparison["match"] is False
    assert comparison["changed_case_ids"] == ["canonical_success"]


def test_valid_comparison_output_is_written_for_coherent_drift(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    drift_json, drift_markdown = _write_coherent_drift(tmp_path)
    comparison_output = tmp_path / "comparison.json"
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", drift_json)
    monkeypatch.setattr(module, "BASELINE_MARKDOWN_PATH", drift_markdown)
    assert main(["check", "--comparison-output", str(comparison_output)]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["match"] is False
    assert validate_comparison(
        json.loads(comparison_output.read_text(encoding="utf-8"))
    )["match"] is False


def test_cli_rejects_malformed_json_wrong_schema_and_incoherent_baselines(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    valid_markdown = BASELINE_MARKDOWN_PATH
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", malformed)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"evaluation_baseline_invalid"}\n'
    )

    wrong_schema = tmp_path / "wrong-schema.json"
    payload = json.loads(BASELINE_JSON_PATH.read_text(encoding="utf-8"))
    payload["schema_version"] = "dra.agent-evaluation-report.v999"
    wrong_schema.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", wrong_schema)
    monkeypatch.setattr(module, "BASELINE_MARKDOWN_PATH", valid_markdown)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_baseline_invalid"

    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_text(json.dumps({"schema_version": "dra.agent-evaluation-report.v1"}), encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", wrong_shape)
    monkeypatch.setattr(module, "BASELINE_MARKDOWN_PATH", valid_markdown)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_baseline_invalid"

    monkeypatch.setattr(module, "BASELINE_JSON_PATH", BASELINE_JSON_PATH)
    incoherent = tmp_path / "incoherent.md"
    incoherent.write_text("# Stale report\n", encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE_MARKDOWN_PATH", incoherent)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_baseline_invalid"


def test_cli_maps_unreadable_baseline_without_exposing_path(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_bytes(BASELINE_JSON_PATH.read_bytes())
    original_open = Path.open

    def denied_open(path, *args, **kwargs):
        if path == unreadable:
            raise PermissionError("private path detail")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", unreadable)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"evaluation_baseline_invalid"}\n'
    )
    assert str(unreadable) not in captured.err


@pytest.mark.parametrize("baseline", [BASELINE_JSON_PATH, BASELINE_MARKDOWN_PATH])
def test_cli_refuses_alias_to_either_committed_baseline(
    baseline, tmp_path, capsys
):
    alias = tmp_path / baseline.name
    alias.symlink_to(baseline.resolve())
    other = tmp_path / "other-output.md"
    arguments = [
        "build",
        "--json-output",
        str(alias if baseline == BASELINE_JSON_PATH else tmp_path / "candidate.json"),
        "--markdown-output",
        str(alias if baseline == BASELINE_MARKDOWN_PATH else other),
    ]
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_output_invalid"
    assert not other.exists()


def test_cli_rejects_directory_and_deterministically_unwritable_targets(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    directory = tmp_path / "directory"
    directory.mkdir()
    assert main(
        [
            "build",
            "--json-output",
            str(directory),
            "--markdown-output",
            str(tmp_path / "candidate.md"),
        ]
    ) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "evaluation_output_invalid"

    candidate = tmp_path / "candidate.json"
    original_access = module.os.access

    def denied_access(path, mode):
        if Path(path) == tmp_path:
            return False
        return original_access(path, mode)

    monkeypatch.setattr(module.os, "access", denied_access)
    assert main(
        [
            "build",
            "--json-output",
            str(candidate),
            "--markdown-output",
            str(tmp_path / "candidate.md"),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_output_invalid"
    assert not candidate.exists()


def test_second_output_replace_failure_preserves_target_and_cleans_temps(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"
    markdown_output.write_text("preserved\n", encoding="utf-8")
    original_replace = module.os.replace
    calls = []

    def fail_second(source, destination):
        calls.append(Path(destination))
        if len(calls) == 2:
            raise OSError("replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_second)
    assert main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_output_invalid"
    assert validate_report(json.loads(json_output.read_text(encoding="utf-8")))
    assert markdown_output.read_text(encoding="utf-8") == "preserved\n"
    assert not list(tmp_path.glob(".*.tmp"))


def test_one_output_write_failure_does_not_damage_other_target(
    tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"
    markdown_output.write_text("preserved\n", encoding="utf-8")
    original_write = module._write_bytes

    def fail_markdown(path, raw):
        if path == markdown_output:
            raise OSError("write failure")
        return original_write(path, raw)

    monkeypatch.setattr(module, "_write_bytes", fail_markdown)
    assert main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "evaluation_output_invalid"
    assert validate_report(json.loads(json_output.read_text(encoding="utf-8")))
    assert markdown_output.read_text(encoding="utf-8") == "preserved\n"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("boundary", ["report", "comparison"])
def test_generated_schema_failures_map_to_output_invalid_and_leave_no_temp(
    boundary, tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    output = tmp_path / "candidate.json"
    markdown = tmp_path / "candidate.md"
    if boundary == "report":
        monkeypatch.setattr(module, "build_deterministic_report", lambda manifest: {})
        arguments = [
            "build",
            "--json-output",
            str(output),
            "--markdown-output",
            str(markdown),
        ]
    else:
        monkeypatch.setattr(module, "compare_artifacts", lambda *args: {})
        arguments = ["check", "--comparison-output", str(output)]
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"evaluation_output_invalid"}\n'
    )
    assert not output.exists()
    assert not markdown.exists()
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("candidate_kind", ["expectation_mismatch", "blocking_regression"])
def test_candidate_failures_keep_report_authority_and_emit_comparison_only(
    candidate_kind, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    candidate = build_deterministic_report(_manifest())
    case = candidate["cases"][0]
    case["status"] = "regression"
    case["expectation_match"] = False
    candidate["summary"]["expectation_mismatch_count"] = 1
    candidate["summary"]["release_gate_passed"] = False
    if candidate_kind == "blocking_regression":
        finding = {
            "evaluator_id": "result_contract",
            "code": "result.contract_invalid",
            "severity": "blocking",
        }
        case["evaluators"][0].update(
            status="regression", finding_codes=["result.contract_invalid"]
        )
        case["blocking_finding_codes"] = ["result.contract_invalid"]
        case["findings"] = [finding]
        candidate["summary"]["blocking_regression_count"] = 1
    candidate = validate_report(candidate)
    monkeypatch.setattr(module, "build_deterministic_report", lambda manifest: candidate)

    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    comparison = json.loads(captured.out)
    assert comparison["match"] is False
    assert comparison["changed_case_ids"] == ["canonical_success"]
    expected_codes = (
        ["result.contract_invalid"]
        if candidate_kind == "blocking_regression"
        else []
    )
    assert comparison["blocking_regression_codes"] == expected_codes


def test_oversized_baseline_is_bounded(tmp_path, monkeypatch, capsys):
    from scripts import agent_evaluation_gate as module

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_REPORT_BYTES + b"}")
    monkeypatch.setattr(module, "BASELINE_JSON_PATH", oversized)
    assert main(["check"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "evaluation_baseline_invalid"


def test_import_isolation_and_forbidden_imports():
    code = """
import sys
from scripts.agent_evaluation_gate import main
raise SystemExit(0 if main(['check']) == 0 and not any(name in sys.modules for name in (
    'agent.main_agent', 'agent.llm', 'tools.tavily_tools', 'tools.talent_search',
    'tools.ragflow_tools', 'deepagents', 'langchain', 'langgraph', 'langsmith'
)) else 1)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    source = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "scripts/agent_evaluation_contracts.py",
            "scripts/agent_evaluation_evaluators.py",
            "scripts/agent_evaluation_gate.py",
        )
    ).lower()
    for forbidden in ("import agentevals", "import deepagents", "import langchain", "import langgraph", "import langsmith"):
        assert forbidden not in source


def test_file_entrypoint_help_resolves_project_imports():
    completed = subprocess.run(
        [sys.executable, "scripts/agent_evaluation_gate.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "build" in completed.stdout
    assert "check" in completed.stdout
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["unknown"],
        ["build"],
        ["build", "--json-output", "candidate.json"],
        ["check", "--unknown-option"],
    ],
)
def test_file_entrypoint_parse_failures_use_bounded_public_error(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/agent_evaluation_gate.py", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        '{"status":"invalid","code":"evaluation_output_invalid"}\n'
    )


@pytest.mark.parametrize("arguments", [["--help"], ["build", "--help"], ["check", "--help"]])
def test_file_entrypoint_help_paths_remain_successful(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/agent_evaluation_gate.py", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.startswith("usage:")
    assert completed.stderr == ""


@pytest.mark.parametrize("source_case_id", ["missing_source", "fallback_ready"])
def test_cli_rejects_unknown_or_cross_case_source_before_fixture_lookup(
    source_case_id, tmp_path, monkeypatch, capsys
):
    from scripts import agent_evaluation_gate as module

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["cases"][0]["source_case_id"] = source_case_id
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest_path)

    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"evaluation_case_invalid"}\n'
    )
    assert "evaluation_internal_error" not in captured.err


def test_unexpected_exception_maps_to_bounded_internal_error():
    code = """
from scripts import agent_evaluation_gate as module
module.build_deterministic_report = lambda manifest: (_ for _ in ()).throw(RuntimeError('private detail'))
raise SystemExit(module.main(['check']))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "status": "invalid",
        "code": "evaluation_internal_error",
    }
    assert "private detail" not in completed.stderr
    assert "Traceback" not in completed.stderr
