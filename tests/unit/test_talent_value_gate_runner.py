"""Unit tests for the fair Talent Hiring Signal value-gate runner."""
from __future__ import annotations

import asyncio
from dataclasses import replace
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


def _packet() -> ResearchPacket:
    return ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "talent-hiring-signal-v1",
            "findings": [],
            "candidate_claims": [],
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
    return ExecutionOutcome(
        thread_id=f"{profile_id}-thread",
        query="bounded query",
        session_dir=Path("/private/runtime/session"),
        profile_id=profile_id,
        run_id=f"run-{profile_id}",
        segment_id=f"seg-{profile_id}",
        started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        last_agent_text="final answer",
        diagnostics=["tool:provided_aggregate"],
        evidence_entries=evidence,
        research_packets=[_packet()]
        if profile_id == "talent-hiring-signal" and include_packet
        else [],
        error_message="failed" if failed else None,
        failure_kind="execution_error" if failed else None,
    )


def _paired_results(inputs, *, talent_outcome=None, generic_outcome=None):
    source_url = next(iter(inputs.source_urls))
    talent = runner.serialize_outcome(
        talent_outcome
        or _outcome("talent-hiring-signal", source_url=source_url),
        elapsed_seconds=2.5,
    )
    talent["review_bundle"] = {"run_id": talent["run_id"]}
    talent["artifacts"] = [
        {"artifact_id": "decision-brief.json"},
        {"artifact_id": "decision-brief.md"},
    ]
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
        "out_of_scope_evidence_count": 0,
        "out_of_scope_evidence_by_profile": {
            "generic": 0,
            "talent-hiring-signal": 0,
        },
        "input_mismatch_count": 0,
        "artifact_failure_count": 0,
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


def test_run_value_gate_enables_fixture_provider_only_for_talent(monkeypatch):
    inputs = runner.load_benchmark_inputs(SCOPE_PATH, FIXTURE_PATH)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "false")
    observed = []

    async def fake_agent_runner(**kwargs):
        observed.append(
            (
                kwargs["profile_id"],
                os.getenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"),
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
    assert os.getenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES") == "false"


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
