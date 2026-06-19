"""Unit tests for the fair Talent Hiring Signal value-gate runner."""
from __future__ import annotations

import asyncio
import argparse
from dataclasses import replace
from copy import deepcopy
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

import pytest

from agent.research import EvidenceEntry
from agent.run_result import ExecutionOutcome
from agent.talent_contracts import ResearchPacket
from scripts import talent_value_gate_runner as runner


SCOPE_PATH = Path("benchmarks/talent-hiring-signal-v1/research-scope.json")
FIXTURE_PATH = Path("benchmarks/fixtures/talent-hiring-signal-v1.json")


def test_cli_help_runs_from_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/talent_value_gate_runner.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--repetitions" in result.stdout
    assert "--per-run-timeout-seconds" in result.stdout


def test_load_benchmark_inputs_builds_byte_stable_shared_envelope():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)

    first_prompt, first_hash = runner.build_prompt_envelope(inputs)
    second_prompt, second_hash = runner.build_prompt_envelope(inputs)

    assert inputs.aggregate_id == "talent-hiring-signal-v1"
    assert len(inputs.samples) == 5
    assert first_prompt == second_prompt
    assert first_hash == second_hash
    assert len(first_hash) == 64
    assert all(sample["content"] in first_prompt for sample in inputs.samples)
    assert all(sample["source_url"] in first_prompt for sample in inputs.samples)
    assert "allowed_evidence_refs" in first_prompt
    assert "any other evidence label is invalid" in first_prompt


def test_load_benchmark_inputs_rejects_mismatched_aggregate_id(tmp_path):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["aggregate_id"] = "different-aggregate"
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError, match="aggregate ID"):
        runner.load_benchmark_inputs(SCOPE_PATH, fixture_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_url", "file:///tmp/private", "HTTP"),
        ("content", "   ", "content"),
    ],
)
def test_load_benchmark_inputs_rejects_invalid_sample(
    tmp_path, field, value, message
):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["samples"][0][field] = value
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        runner.load_benchmark_inputs(SCOPE_PATH, fixture_path)


def _packet(evidence_refs: list[str] | None = None) -> ResearchPacket:
    evidence_refs = list(evidence_refs) if evidence_refs is not None else ["ev_default"]
    return ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "talent-hiring-signal-v1",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Declared sample contains a bounded hiring signal.",
                    "evidence_refs": evidence_refs,
                    "sample_scope": "declared samples",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Declared sample contains a bounded hiring signal.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": evidence_refs,
                    "confidence": 0.8,
                    "citation_status": "cited" if evidence_refs else "uncited",
                    "verification_status": "unverified",
                    "review_status": "pending",
                    "conflict_status": "none",
                }
            ],
            "limitations": ["Five declared snapshots only."],
        }
    )


def _outcome(
    profile_id: str,
    *,
    source_url: str | None = None,
    failed: bool = False,
    include_packet: bool = True,
) -> ExecutionOutcome:
    run_id = f"run-{profile_id}"
    evidence = (
        [
            EvidenceEntry(
                thread_id=f"{profile_id}-thread",
                query_text="bounded query",
                subagent_name="researcher",
                tool_name="provided_aggregate",
                source_url=source_url,
                snippet="bounded evidence",
            )
        ]
        if source_url
        else []
    )
    evidence_refs = [
        f"ev_{run_id}_{entry.evidence_fingerprint}" for entry in evidence
    ]
    return ExecutionOutcome(
        thread_id=f"{profile_id}-thread",
        query="bounded query",
        session_dir=Path("/private/runtime/session"),
        profile_id=profile_id,
        run_id=run_id,
        segment_id=f"seg-{profile_id}",
        started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        last_agent_text="final answer",
        diagnostics=["tool:provided_aggregate"],
        evidence_entries=evidence,
        research_packets=[_packet(evidence_refs or None)]
        if profile_id == "talent-hiring-signal" and include_packet
        else [],
        error_message="failed" if failed else None,
        failure_kind="execution_error" if failed else None,
    )


def _paired_results(inputs, *, talent_outcome=None, generic_outcome=None):
    source_url = next(iter(inputs.source_urls))
    talent_outcome = talent_outcome or _outcome(
        "talent-hiring-signal", source_url=source_url
    )
    talent = runner.serialize_outcome(
        talent_outcome,
        elapsed_seconds=2.5,
    )
    if talent_outcome.research_packets and talent_outcome.failure_kind is None:
        talent = runner._enrich_with_talent_artifacts(
            talent,
            outcome=talent_outcome,
            scope=inputs.scope.model_dump(mode="json"),
        )
    return [
        {
            "repetition": 1,
            "input_hash": runner.build_prompt_envelope(inputs)[1],
            "runs": {
                "generic": runner.serialize_outcome(
                    generic_outcome or _outcome("generic", source_url=source_url),
                    elapsed_seconds=1.25,
                ),
                "talent-hiring-signal": talent,
            },
        }
    ]


def test_serialize_outcome_allowlists_reviewable_fields():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    outcome = _outcome("talent-hiring-signal", source_url=next(iter(inputs.source_urls)))

    serialized = runner.serialize_outcome(outcome, elapsed_seconds=2.5)

    assert serialized["status"] == "completed"
    assert serialized["final_text"] == "final answer"
    assert serialized["elapsed_seconds"] == 2.5
    assert serialized["evidence"][0]["source_url"] in inputs.source_urls
    assert serialized["research_packets"][0]["packet_id"] == "packet-1"
    assert "session_dir" not in serialized
    assert "/private/runtime/session" not in json.dumps(serialized)


@pytest.mark.parametrize(
    "talent_outcome",
    [
        _outcome("talent-hiring-signal", failed=True),
        _outcome("talent-hiring-signal", include_packet=False),
    ],
)
def test_build_benchmark_bundle_fails_closed_for_invalid_runs(talent_outcome):
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=_paired_results(inputs, talent_outcome=talent_outcome),
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["ready_for_human_review"] is False
    assert bundle["value_gate"]["passed"] is False
    assert bundle["value_gate"]["human_scores"] == {}


def test_build_benchmark_bundle_records_out_of_scope_evidence_for_human_scoring():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    generic = _outcome("generic", source_url="https://outside.example/source")

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=_paired_results(inputs, generic_outcome=generic),
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "ready_for_human_review"
    assert bundle["completion"]["out_of_scope_evidence_count"] == 1
    assert bundle["completion"]["out_of_scope_evidence_by_profile"] == {
        "generic": 1,
        "talent-hiring-signal": 0,
    }


def test_build_benchmark_bundle_marks_complete_pairs_ready_for_human_review():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=_paired_results(inputs),
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "ready_for_human_review"
    assert bundle["completion"] == {
        "expected_run_count": 2,
        "completed_run_count": 2,
        "schema_failure_count": 0,
        "evidence_failure_count": 0,
        "evidence_ref_failure_count": 0,
        "out_of_scope_evidence_count": 0,
        "out_of_scope_evidence_by_profile": {
            "generic": 0,
            "talent-hiring-signal": 0,
        },
        "input_mismatch_count": 0,
        "artifact_failure_count": 0,
        "renderer_contract_failure_count": 0,
        "disallowed_tool_failure_count": 0,
        "timeout_failure_count": 0,
        "recursion_limit_failure_count": 0,
        "profile_mismatch_count": 0,
        "identity_collision_count": 0,
        "ready_for_human_review": True,
    }
    assert bundle["value_gate"]["passed"] is False


def test_run_value_gate_pairs_identical_inputs_with_unique_run_identities():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    calls = []

    async def fake_agent_runner(**kwargs):
        calls.append(kwargs)
        source_url = next(iter(inputs.source_urls))
        return replace(
            _outcome(kwargs["profile_id"], source_url=source_url),
            thread_id=kwargs["thread_id"],
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            query=kwargs["task_query"],
        )

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=2,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    assert [call["profile_id"] for call in calls] == [
        "generic",
        "talent-hiring-signal",
        "generic",
        "talent-hiring-signal",
    ]
    assert len({call["task_query"] for call in calls}) == 1
    assert len({call["thread_id"] for call in calls}) == 4
    assert len({call["run_id"] for call in calls}) == 4
    assert len({call["segment_id"] for call in calls}) == 4
    assert all(call["scope"] is None for call in calls if call["profile_id"] == "generic")
    assert all(
        call["scope"] == inputs.scope.model_dump(mode="json")
        for call in calls
        if call["profile_id"] == "talent-hiring-signal"
    )
    assert {
        pair["input_hash"] for pair in bundle["paired_results"]
    } == {bundle["input_hash"]}


def test_run_value_gate_captures_exception_and_continues_pair():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    calls = []

    async def fake_agent_runner(**kwargs):
        calls.append(kwargs)
        if kwargs["profile_id"] == "generic":
            raise RuntimeError("model unavailable")
        return replace(
            _outcome("talent-hiring-signal"),
            thread_id=kwargs["thread_id"],
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
        )

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    assert len(calls) == 2
    generic = bundle["paired_results"][0]["runs"]["generic"]
    assert generic["status"] == "failed"
    assert generic["failure_kind"] == "runner_exception"
    assert generic["error_message"] == "model unavailable"
    assert bundle["benchmark_status"] == "incomplete"


def test_build_benchmark_bundle_rejects_mismatched_pair_input_hash():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["input_hash"] = "different-input"

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["input_mismatch_count"] == 1


def test_build_benchmark_bundle_requires_talent_review_artifacts():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    del pairs[0]["runs"]["talent-hiring-signal"]["artifacts"]

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["artifact_failure_count"] == 1


def test_build_benchmark_bundle_allows_required_review_bundle_for_human_scoring():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["talent-hiring-signal"]["review_bundle"] = {
        "run_id": pairs[0]["runs"]["talent-hiring-signal"]["run_id"],
        "status": "required",
        "required_before_delivery": True,
        "triggers": ["conflicting_sources:claim-1"],
    }

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "ready_for_human_review"
    assert bundle["completion"]["artifact_failure_count"] == 0


def test_build_benchmark_bundle_requires_talent_evidence_even_with_artifacts():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["talent-hiring-signal"]["evidence"] = []

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["evidence_failure_count"] == 1
    assert bundle["completion"]["evidence_ref_failure_count"] == 1


def test_build_benchmark_bundle_rejects_unresolved_talent_evidence_refs():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    packet = pairs[0]["runs"]["talent-hiring-signal"]["research_packets"][0]
    packet["findings"][0]["evidence_refs"] = ["ev_missing"]
    packet["candidate_claims"][0]["evidence_refs"] = ["ev_missing"]

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["evidence_failure_count"] == 0
    assert bundle["completion"]["evidence_ref_failure_count"] == 1


def test_build_benchmark_bundle_rejects_empty_talent_findings_and_claims():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    packet = pairs[0]["runs"]["talent-hiring-signal"]["research_packets"][0]
    packet["findings"] = []
    packet["candidate_claims"] = []

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["evidence_ref_failure_count"] == 1


def test_build_benchmark_bundle_rejects_talent_filesystem_tool_diagnostics():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["talent-hiring-signal"]["diagnostics"].append("tool:write_file")

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["disallowed_tool_failure_count"] == 1


def test_build_benchmark_bundle_rejects_talent_todo_tool_diagnostics():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["talent-hiring-signal"]["diagnostics"].append("tool:write_todos")

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["disallowed_tool_failure_count"] == 1


def test_build_benchmark_bundle_allows_additional_talent_artifacts():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["talent-hiring-signal"]["artifacts"].append(
        {"artifact_id": "future-review.json"}
    )

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["completion"]["artifact_failure_count"] == 0
    assert bundle["benchmark_status"] == "ready_for_human_review"


def _talent_artifacts(pairs):
    return pairs[0]["runs"]["talent-hiring-signal"]["artifacts"]


def _artifact(artifacts, artifact_id):
    return next(item for item in artifacts if item["artifact_id"] == artifact_id)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda artifacts: artifacts.pop(0),
        lambda artifacts: artifacts.pop(1),
        lambda artifacts: artifacts.append(deepcopy(artifacts[0])),
        lambda artifacts: _artifact(artifacts, "decision-brief.json").update(
            kind="wrong"
        ),
        lambda artifacts: _artifact(artifacts, "decision-brief.md").update(
            media_type="text/plain"
        ),
        lambda artifacts: _artifact(artifacts, "decision-brief.md").update(
            content=""
        ),
        lambda artifacts: _artifact(artifacts, "decision-brief.json").update(
            content="{not-json"
        ),
        lambda artifacts: _mutate_brief_json(
            artifacts, renderer_version="1"
        ),
        lambda artifacts: _mutate_brief_json(
            artifacts, content_hash="wrong-hash"
        ),
        lambda artifacts: _mutate_open_status_with_valid_hash(artifacts),
        lambda artifacts: _artifact(artifacts, "decision-brief.md").update(
            content="# mismatched markdown\n"
        ),
    ],
    ids=(
        "missing-json",
        "missing-markdown",
        "duplicate-json",
        "wrong-kind",
        "wrong-media-type",
        "empty-content",
        "malformed-json",
        "renderer-v1",
        "wrong-semantic-hash",
        "unhashable-open-status",
        "markdown-mismatch",
    ),
)
def test_build_benchmark_bundle_fails_closed_for_renderer_contract(mutate):
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    mutate(_talent_artifacts(pairs))

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["renderer_contract_failure_count"] == 1
    assert bundle["completion"]["ready_for_human_review"] is False


def _mutate_brief_json(artifacts, **updates):
    artifact = _artifact(artifacts, "decision-brief.json")
    payload = json.loads(artifact["content"])
    payload.update(updates)
    artifact["content"] = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mutate_open_status_with_valid_hash(artifacts):
    from agent.talent_contracts import DecisionBrief
    from api.decision_brief import with_content_hash

    json_artifact = _artifact(artifacts, "decision-brief.json")
    payload = json.loads(json_artifact["content"])
    payload["evidence_summary"][0]["verification_status"] = []
    brief = with_content_hash(DecisionBrief.model_validate(payload))
    json_artifact["content"] = json.dumps(
        brief.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for artifact in artifacts:
        artifact["content_hash"] = brief.content_hash


@pytest.mark.parametrize(
    ("benchmark_status", "expected_exit"),
    [("ready_for_human_review", 0), ("incomplete", 1)],
)
def test_cli_writes_bundle_prints_path_and_uses_status_exit_code(
    tmp_path,
    monkeypatch,
    capsys,
    benchmark_status,
    expected_exit,
):
    output = tmp_path / "bundle.json"
    monkeypatch.setattr(
        runner,
        "parse_args",
        lambda: argparse.Namespace(
            scope=SCOPE_PATH,
            fixture=FIXTURE_PATH,
            repetitions=1,
            per_run_timeout_seconds=600.0,
            output=output,
        ),
    )

    async def fake_run_value_gate(**kwargs):
        return {
            "benchmark_status": benchmark_status,
            "completion": {"ready_for_human_review": expected_exit == 0},
        }

    monkeypatch.setattr(runner, "run_value_gate", fake_run_value_gate)

    if expected_exit:
        with pytest.raises(SystemExit) as exc_info:
            runner.main()
        assert exc_info.value.code == expected_exit
    else:
        assert runner.main() is None

    assert json.loads(output.read_text(encoding="utf-8"))["benchmark_status"] == (
        benchmark_status
    )
    assert str(output) in capsys.readouterr().out


def test_build_benchmark_bundle_rejects_profile_mismatch_and_identity_collision():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    generic = pairs[0]["runs"]["generic"]
    talent = pairs[0]["runs"]["talent-hiring-signal"]
    talent["profile_id"] = "generic"
    talent["run_id"] = generic["run_id"]

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["profile_mismatch_count"] == 1
    assert bundle["completion"]["identity_collision_count"] == 1


def test_build_benchmark_bundle_counts_recursion_limit_failures():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    talent = pairs[0]["runs"]["talent-hiring-signal"]
    talent["status"] = "failed"
    talent["failure_kind"] = "recursion_limit_exceeded"
    talent["error_message"] = "recursion limit reached"
    talent["research_packets"] = []
    talent.pop("review_bundle", None)
    talent.pop("artifacts", None)

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["recursion_limit_failure_count"] == 1


def test_build_benchmark_bundle_does_not_count_missing_legacy_identity_as_collision():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    pairs = _paired_results(inputs)
    pairs[0]["runs"]["generic"]["segment_id"] = None
    pairs[0]["runs"]["talent-hiring-signal"]["segment_id"] = None

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=pairs,
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert bundle["completion"]["identity_collision_count"] == 0


def test_run_value_gate_redacts_secret_like_exception_text():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)

    async def fake_agent_runner(**kwargs):
        raise RuntimeError("request failed api_key=secret-value Bearer sk-private-token")

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    encoded = json.dumps(bundle)
    assert "secret-value" not in encoded
    assert "sk-private-token" not in encoded
    assert "[REDACTED]" in encoded


def test_run_value_gate_times_out_one_run_and_continues_pair():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    calls = []

    async def fake_agent_runner(**kwargs):
        calls.append(kwargs)
        if kwargs["profile_id"] == "generic":
            await asyncio.sleep(0.05)
        source_url = next(iter(inputs.source_urls))
        return replace(
            _outcome(kwargs["profile_id"], source_url=source_url),
            thread_id=kwargs["thread_id"],
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            query=kwargs["task_query"],
        )

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            per_run_timeout_seconds=0.01,
        )
    )

    assert [call["profile_id"] for call in calls] == [
        "generic",
        "talent-hiring-signal",
    ]
    generic = bundle["paired_results"][0]["runs"]["generic"]
    talent = bundle["paired_results"][0]["runs"]["talent-hiring-signal"]
    assert generic["status"] == "failed"
    assert generic["failure_kind"] == "runner_timeout"
    assert talent["status"] == "completed"
    assert bundle["benchmark_status"] == "incomplete"
    assert bundle["completion"]["timeout_failure_count"] == 1


def test_run_value_gate_attaches_talent_review_and_decision_brief_artifacts():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)

    async def fake_agent_runner(**kwargs):
        source_url = next(iter(inputs.source_urls))
        return replace(
            _outcome(kwargs["profile_id"], source_url=source_url),
            thread_id=kwargs["thread_id"],
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
        )

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    generic = bundle["paired_results"][0]["runs"]["generic"]
    talent = bundle["paired_results"][0]["runs"]["talent-hiring-signal"]
    assert "artifacts" not in generic
    assert talent["review_bundle"]["run_id"] == talent["run_id"]
    assert {artifact["artifact_id"] for artifact in talent["artifacts"]} == {
        "decision-brief.json",
        "decision-brief.md",
    }


def test_run_value_gate_restores_canonical_fixture_setting_after_success(monkeypatch):
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "false",
    )
    observed = []

    async def fake_agent_runner(**kwargs):
        observed.append(
            (
                kwargs["profile_id"],
                os.getenv(
                    "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"
                ),
            )
        )
        return _outcome(kwargs["profile_id"])

    asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    assert observed == [
        ("generic", "false"),
        ("talent-hiring-signal", "true"),
    ]
    assert (
        os.getenv("DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES")
        == "false"
    )


def test_run_value_gate_removes_temporary_canonical_fixture_setting_after_failure(
    monkeypatch,
):
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        raising=False,
    )
    observed = []

    async def fake_agent_runner(**kwargs):
        observed.append(
            (
                kwargs["profile_id"],
                os.getenv(
                    "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"
                ),
            )
        )
        if kwargs["profile_id"] == "talent-hiring-signal":
            raise RuntimeError("talent failed")
        return _outcome(kwargs["profile_id"])

    bundle = asyncio.run(
        runner.run_value_gate(
            inputs=inputs,
            repetitions=1,
            agent_runner=fake_agent_runner,
            generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
    )

    talent = bundle["paired_results"][0]["runs"]["talent-hiring-signal"]
    assert observed == [
        ("generic", None),
        ("talent-hiring-signal", "true"),
    ]
    assert talent["failure_kind"] == "runner_exception"
    assert "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES" not in os.environ


def test_build_benchmark_bundle_recursively_redacts_secret_like_text():
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    generic = replace(
        _outcome("generic", source_url=next(iter(inputs.source_urls))),
        last_agent_text="accidentally echoed sk-private-token",
    )

    bundle = runner.build_benchmark_bundle(
        inputs=inputs,
        repetitions=1,
        paired_results=_paired_results(inputs, generic_outcome=generic),
        generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    encoded = json.dumps(bundle)
    assert "sk-private-token" not in encoded
    assert "[REDACTED]" in encoded
