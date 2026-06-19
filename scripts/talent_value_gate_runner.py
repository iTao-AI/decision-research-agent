#!/usr/bin/env python3
"""Run a fair, offline Generic-vs-Talent value-gate comparison."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.run_result import AgentRunResult
from agent.talent_contracts import DecisionBrief, ResearchScope
from api.decision_brief import render_markdown, with_content_hash


_TALENT_PROFILE_ID = "talent-hiring-signal"
_BENCHMARK_FIXTURE_ENV = "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"
_DISALLOWED_TALENT_TOOL_DIAGNOSTICS = frozenset(
    {
        "tool:convert_md_to_pdf",
        "tool:edit_file",
        "tool:generate_markdown",
        "tool:glob",
        "tool:ls",
        "tool:read_file",
        "tool:read_file_content",
        "tool:write_todos",
        "tool:write_file",
    }
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
)


@dataclass(frozen=True)
class BenchmarkInputs:
    """Validated immutable inputs shared by both benchmark profiles."""

    aggregate_id: str
    scope: ResearchScope
    samples: tuple[dict[str, str], ...]

    @property
    def source_urls(self) -> frozenset[str]:
        return frozenset(sample["source_url"] for sample in self.samples)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load benchmark JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Benchmark JSON must be an object: {path}")
    return value


def load_benchmark_inputs(scope_path: Path, fixture_path: Path) -> BenchmarkInputs:
    """Load and validate one declared aggregate plus its bounded source snapshots."""
    scope = ResearchScope.model_validate(_load_json_object(scope_path))
    fixture = _load_json_object(fixture_path)
    aggregate_refs = {
        sample.reference
        for sample in scope.declared_samples
        if sample.source_type == "provided_aggregate"
    }
    aggregate_id = fixture.get("aggregate_id")
    if not isinstance(aggregate_id, str) or aggregate_id not in aggregate_refs:
        raise ValueError("Fixture aggregate ID must match the declared ResearchScope")

    raw_samples = fixture.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("Fixture must contain at least one sample")

    samples: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for index, sample in enumerate(raw_samples):
        if not isinstance(sample, dict):
            raise ValueError(f"Fixture sample {index} must be an object")
        sample_id = sample.get("sample_id")
        source_url = sample.get("source_url")
        content = sample.get("content")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"Fixture sample {index} must have a sample ID")
        parsed = urlparse(source_url) if isinstance(source_url, str) else None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"Fixture sample {sample_id} must have an HTTP(S) source URL")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Fixture sample {sample_id} must have non-empty content")
        if sample_id in seen_ids or source_url in seen_urls:
            raise ValueError("Fixture sample IDs and source URLs must be unique")
        seen_ids.add(sample_id)
        seen_urls.add(source_url)
        samples.append(
            {
                "sample_id": sample_id.strip(),
                "source_url": source_url,
                "content": content.strip(),
            }
        )

    return BenchmarkInputs(
        aggregate_id=aggregate_id,
        scope=scope,
        samples=tuple(samples),
    )


def build_prompt_envelope(inputs: BenchmarkInputs) -> tuple[str, str]:
    """Return byte-stable shared prompt text and its SHA-256 hash."""
    payload = {
        "aggregate_id": inputs.aggregate_id,
        "allowed_evidence_refs": [
            {
                "sample_id": sample["sample_id"],
                "source_url": sample["source_url"],
            }
            for sample in inputs.samples
        ],
        "research_questions": list(inputs.scope.research_questions),
        "source_snapshots": list(inputs.samples),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    prompt = (
        "Analyze only the bounded source snapshot below. Do not use or infer "
        "sources outside this envelope. Distinguish repeated signals from "
        "sample-specific signals and state limitations explicitly. Every "
        "finding.evidence_refs and claim.evidence_refs entry must be copied "
        "verbatim from allowed_evidence_refs.sample_id or "
        "allowed_evidence_refs.source_url; any other evidence label is invalid.\n"
        f"{encoded}"
    )
    return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def serialize_outcome(
    outcome: AgentRunResult,
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """Serialize only reviewable fields from one execution outcome."""
    evidence_identity = outcome.run_id or outcome.thread_id
    bundle = {
        "profile_id": outcome.profile_id,
        "thread_id": outcome.thread_id,
        "run_id": outcome.run_id,
        "segment_id": outcome.segment_id,
        "status": (
            "failed"
            if outcome.failure_kind is not None or outcome.error_message is not None
            else "completed"
        ),
        "failure_kind": outcome.failure_kind,
        "error_message": outcome.error_message,
        "cancellation_state": outcome.cancellation_state,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "final_text": outcome.last_agent_text,
        "assistant_calls": outcome.assistant_calls,
        "tool_starts": outcome.tool_starts,
        "diagnostics": list(outcome.diagnostics),
        "evidence": [
            {
                "evidence_id": f"ev_{evidence_identity}_{entry.evidence_fingerprint}",
                "source_url": entry.source_url,
                "snippet": entry.snippet,
                "source_identity": entry.source_identity,
                "evidence_fingerprint": entry.evidence_fingerprint,
                "subagent_name": entry.subagent_name,
                "tool_name": entry.tool_name,
                "citation_status": entry.citation_status,
                "verification_status": entry.verification_status,
                "retrieved_at": entry.retrieved_at,
            }
            for entry in outcome.evidence_entries
        ],
        "research_packets": [
            packet.model_dump(mode="json") for packet in outcome.research_packets
        ],
    }
    return _sanitize_export_value(bundle)


def _is_talent_run(run: dict[str, Any]) -> bool:
    return run.get("profile_id") == _TALENT_PROFILE_ID


def _evidence_ids_for_run(run: dict[str, Any]) -> set[str]:
    run_identity = run.get("run_id") or run.get("thread_id") or ""
    evidence_ids: set[str] = set()
    for evidence in run.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        evidence_id = evidence.get("evidence_id")
        if isinstance(evidence_id, str) and evidence_id:
            evidence_ids.add(evidence_id)
            continue
        fingerprint = evidence.get("evidence_fingerprint")
        if isinstance(fingerprint, str) and fingerprint and run_identity:
            evidence_ids.add(f"ev_{run_identity}_{fingerprint}")
    return evidence_ids


def _run_has_unresolved_talent_evidence_refs(run: dict[str, Any]) -> bool:
    if not _is_talent_run(run):
        return False
    evidence_ids = _evidence_ids_for_run(run)
    for packet in run.get("research_packets", []):
        if not isinstance(packet, dict):
            return True
        findings = packet.get("findings", [])
        claims = packet.get("candidate_claims", [])
        if not isinstance(findings, list) or not findings:
            return True
        if not isinstance(claims, list) or not claims:
            return True
        for collection_name in ("findings", "candidate_claims"):
            collection = packet.get(collection_name, [])
            if not isinstance(collection, list):
                return True
            for item in collection:
                if not isinstance(item, dict):
                    return True
                refs = item.get("evidence_refs")
                if not isinstance(refs, list) or not refs:
                    return True
                if any(ref not in evidence_ids for ref in refs):
                    return True
    return False


def _run_has_disallowed_talent_tool(run: dict[str, Any]) -> bool:
    if not _is_talent_run(run):
        return False
    return any(
        diagnostic in _DISALLOWED_TALENT_TOOL_DIAGNOSTICS
        for diagnostic in run.get("diagnostics", [])
    )


def _run_has_valid_renderer_contract(run: dict[str, Any]) -> bool:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    expected = {
        "decision-brief.json": ("decision_brief_json", "application/json"),
        "decision-brief.md": ("decision_brief_markdown", "text/markdown"),
    }
    selected: dict[str, dict[str, Any]] = {}
    for artifact_id, (kind, media_type) in expected.items():
        matches = [
            artifact
            for artifact in artifacts
            if isinstance(artifact, dict)
            and artifact.get("artifact_id") == artifact_id
        ]
        if len(matches) != 1:
            return False
        artifact = matches[0]
        if artifact.get("kind") != kind or artifact.get("media_type") != media_type:
            return False
        if not isinstance(artifact.get("content"), str) or not artifact["content"]:
            return False
        if (
            not isinstance(artifact.get("content_hash"), str)
            or not artifact["content_hash"]
        ):
            return False
        selected[artifact_id] = artifact

    try:
        brief = DecisionBrief.model_validate_json(
            selected["decision-brief.json"]["content"]
        )
        if brief.renderer_version != "2":
            return False
        expected_hash = with_content_hash(brief).content_hash
        if brief.content_hash != expected_hash:
            return False
        if any(
            artifact["content_hash"] != expected_hash
            for artifact in selected.values()
        ):
            return False
        return selected["decision-brief.md"]["content"] == render_markdown(brief)
    except (TypeError, ValueError):
        return False


def build_benchmark_bundle(
    *,
    inputs: BenchmarkInputs,
    repetitions: int,
    paired_results: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """Build a fail-closed review bundle without making a value judgment."""
    runs = [
        run
        for pair in paired_results
        for run in pair.get("runs", {}).values()
        if isinstance(run, dict)
    ]
    completed_run_count = sum(run.get("status") == "completed" for run in runs)
    schema_failure_count = sum(
        _is_talent_run(run)
        and (
            run.get("status") != "completed"
            or not run.get("research_packets")
        )
        for run in runs
    )
    evidence_failure_count = sum(
        _is_talent_run(run)
        and run.get("status") == "completed"
        and not run.get("evidence")
        for run in runs
    )
    evidence_ref_failure_count = sum(
        _run_has_unresolved_talent_evidence_refs(run) for run in runs
    )
    out_of_scope_evidence_by_profile = {
        "generic": 0,
        _TALENT_PROFILE_ID: 0,
    }
    for run in runs:
        profile_id = run.get("profile_id")
        if profile_id not in out_of_scope_evidence_by_profile:
            continue
        out_of_scope_evidence_by_profile[profile_id] += sum(
            evidence.get("source_url") not in inputs.source_urls
            for evidence in run.get("evidence", [])
        )
    out_of_scope_evidence_count = sum(out_of_scope_evidence_by_profile.values())
    expected_input_hash = build_prompt_envelope(inputs)[1]
    input_mismatch_count = sum(
        pair.get("input_hash") != expected_input_hash for pair in paired_results
    )
    required_artifact_ids = {"decision-brief.json", "decision-brief.md"}
    artifact_failure_count = sum(
        _is_talent_run(run)
        and (
            not run.get("review_bundle")
            or not required_artifact_ids.issubset(
                {
                    artifact.get("artifact_id")
                    for artifact in run.get("artifacts", [])
                    if isinstance(artifact, dict)
                }
            )
        )
        for run in runs
    )
    renderer_contract_failure_count = sum(
        _is_talent_run(run) and not _run_has_valid_renderer_contract(run)
        for run in runs
    )
    disallowed_tool_failure_count = sum(
        _run_has_disallowed_talent_tool(run) for run in runs
    )
    timeout_failure_count = sum(
        run.get("failure_kind") == "runner_timeout" for run in runs
    )
    recursion_limit_failure_count = sum(
        run.get("failure_kind") == "recursion_limit_exceeded" for run in runs
    )
    expected_profiles = {"generic", _TALENT_PROFILE_ID}
    profile_mismatch_count = sum(
        set(pair.get("runs", {})) != expected_profiles
        or any(
            run.get("profile_id") != profile_id
            for profile_id, run in pair.get("runs", {}).items()
            if isinstance(run, dict)
        )
        for pair in paired_results
    )
    identity_collision_count = 0
    for field in ("thread_id", "run_id", "segment_id"):
        values = [run.get(field) for run in runs]
        present = [value for value in values if value]
        identity_collision_count += len(present) - len(set(present))
    expected_run_count = repetitions * 2
    ready = (
        len(paired_results) == repetitions
        and len(runs) == expected_run_count
        and completed_run_count == expected_run_count
        and schema_failure_count == 0
        and evidence_failure_count == 0
        and evidence_ref_failure_count == 0
        and input_mismatch_count == 0
        and artifact_failure_count == 0
        and renderer_contract_failure_count == 0
        and disallowed_tool_failure_count == 0
        and timeout_failure_count == 0
        and recursion_limit_failure_count == 0
        and profile_mismatch_count == 0
        and identity_collision_count == 0
    )
    bundle = {
        "benchmark_id": inputs.aggregate_id,
        "benchmark_status": "ready_for_human_review" if ready else "incomplete",
        "generated_at": generated_at.isoformat(),
        "repetitions": repetitions,
        "input_hash": expected_input_hash,
        "scope_hash": _canonical_hash(inputs.scope.model_dump(mode="json")),
        "fixture_hash": _canonical_hash(
            {
                "aggregate_id": inputs.aggregate_id,
                "samples": list(inputs.samples),
            }
        ),
        "model_configuration": {
            "primary_model": os.getenv("LLM_MODEL")
            or os.getenv("LLM_QWEN_MAX")
            or "deepseek-v4-pro",
            "fallback_model": os.getenv("LLM_FALLBACK_MODEL")
            or "deepseek-v4-flash",
        },
        "paired_results": paired_results,
        "completion": {
            "expected_run_count": expected_run_count,
            "completed_run_count": completed_run_count,
            "schema_failure_count": schema_failure_count,
            "evidence_failure_count": evidence_failure_count,
            "evidence_ref_failure_count": evidence_ref_failure_count,
            "out_of_scope_evidence_count": out_of_scope_evidence_count,
            "out_of_scope_evidence_by_profile": out_of_scope_evidence_by_profile,
            "input_mismatch_count": input_mismatch_count,
            "artifact_failure_count": artifact_failure_count,
            "renderer_contract_failure_count": renderer_contract_failure_count,
            "disallowed_tool_failure_count": disallowed_tool_failure_count,
            "timeout_failure_count": timeout_failure_count,
            "recursion_limit_failure_count": recursion_limit_failure_count,
            "profile_mismatch_count": profile_mismatch_count,
            "identity_collision_count": identity_collision_count,
            "ready_for_human_review": ready,
        },
        "value_gate": {
            "human_scores": {},
            "required_improved_dimensions": 3,
            "passed": False,
        },
    }
    return _sanitize_export_value(bundle)


def _sanitize_error_message(value: str) -> str:
    sanitized = value
    for pattern in _SECRET_PATTERNS:
        replacement = r"\1[REDACTED]" if pattern.groups else "[REDACTED]"
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _sanitize_export_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_error_message(value)
    if isinstance(value, list):
        return [_sanitize_export_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_export_value(item) for key, item in value.items()}
    return value


def _failed_run_record(
    *,
    profile_id: str,
    thread_id: str,
    run_id: str,
    segment_id: str,
    elapsed_seconds: float,
    exc: Exception | None = None,
    failure_kind: str = "runner_exception",
    error_message: str | None = None,
) -> dict[str, Any]:
    message = error_message if error_message is not None else str(exc or "")
    diagnostic_type = type(exc).__name__ if exc is not None else failure_kind
    return {
        "profile_id": profile_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "segment_id": segment_id,
        "status": "failed",
        "failure_kind": failure_kind,
        "error_message": _sanitize_error_message(message),
        "cancellation_state": None,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "final_text": "",
        "assistant_calls": 0,
        "tool_starts": 0,
        "diagnostics": [f"{failure_kind}:{diagnostic_type}"],
        "evidence": [],
        "research_packets": [],
    }


def _enrich_with_talent_artifacts(
    serialized: dict[str, Any],
    *,
    outcome: AgentRunResult,
    scope: dict[str, Any],
) -> dict[str, Any]:
    if outcome.failure_kind is not None or not outcome.research_packets:
        return serialized
    from api.talent_artifacts import build_talent_artifacts

    review, _, artifacts = build_talent_artifacts(
        run_id=outcome.run_id or outcome.thread_id,
        scope=scope,
        packets=outcome.research_packets,
        evidence_entries=outcome.evidence_entries,
        generated_at=outcome.started_at or datetime.now(timezone.utc),
    )
    serialized["review_bundle"] = review.model_dump(mode="json")
    serialized["artifacts"] = artifacts
    return serialized


async def run_value_gate(
    *,
    inputs: BenchmarkInputs,
    repetitions: int,
    agent_runner=None,
    generated_at: datetime | None = None,
    per_run_timeout_seconds: float | None = 600.0,
) -> dict[str, Any]:
    """Run sequential Generic/Talent pairs against one shared prompt envelope.

    This runner temporarily mutates process-global environment state and must
    not be invoked concurrently within the same process.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    if agent_runner is None:
        from agent.main_agent import run_deep_agent

        agent_runner = run_deep_agent

    prompt, input_hash = build_prompt_envelope(inputs)
    scope = inputs.scope.model_dump(mode="json")
    paired_results: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        runs: dict[str, dict[str, Any]] = {}
        for profile_id in ("generic", _TALENT_PROFILE_ID):
            identity = uuid.uuid4().hex
            thread_id = f"benchmark-{profile_id}-{identity}"
            run_id = f"run_{identity}"
            segment_id = f"{run_id}_seg_000"
            started = time.monotonic()
            try:
                previous_fixture_setting = os.environ.get(_BENCHMARK_FIXTURE_ENV)
                if profile_id == _TALENT_PROFILE_ID:
                    os.environ[_BENCHMARK_FIXTURE_ENV] = "true"
                try:
                    run_coro = agent_runner(
                        task_query=prompt,
                        thread_id=thread_id,
                        run_id=run_id,
                        segment_id=segment_id,
                        profile_id=profile_id,
                        scope=scope if profile_id == _TALENT_PROFILE_ID else None,
                    )
                    if per_run_timeout_seconds is None:
                        outcome = await run_coro
                    else:
                        outcome = await asyncio.wait_for(
                            run_coro,
                            timeout=per_run_timeout_seconds,
                        )
                finally:
                    if profile_id == _TALENT_PROFILE_ID:
                        if previous_fixture_setting is None:
                            os.environ.pop(_BENCHMARK_FIXTURE_ENV, None)
                        else:
                            os.environ[_BENCHMARK_FIXTURE_ENV] = (
                                previous_fixture_setting
                            )
                serialized = serialize_outcome(
                    outcome,
                    elapsed_seconds=time.monotonic() - started,
                )
                if profile_id == _TALENT_PROFILE_ID:
                    serialized = _enrich_with_talent_artifacts(
                        serialized,
                        outcome=outcome,
                        scope=scope,
                    )
                runs[profile_id] = serialized
            except asyncio.TimeoutError:
                runs[profile_id] = _failed_run_record(
                    profile_id=profile_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    segment_id=segment_id,
                    elapsed_seconds=time.monotonic() - started,
                    failure_kind="runner_timeout",
                    error_message=(
                        f"run exceeded {per_run_timeout_seconds:g}s timeout"
                    ),
                )
            except Exception as exc:
                runs[profile_id] = _failed_run_record(
                    profile_id=profile_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    segment_id=segment_id,
                    elapsed_seconds=time.monotonic() - started,
                    exc=exc,
                )
        paired_results.append(
            {
                "repetition": repetition,
                "input_hash": input_hash,
                "runs": runs,
            }
        )
    return build_benchmark_bundle(
        inputs=inputs,
        repetitions=repetitions,
        paired_results=paired_results,
        generated_at=generated_at or datetime.now(timezone.utc),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an offline fair Generic-vs-Talent value-gate comparison."
    )
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path("benchmarks/talent-hiring-signal-v1/research-scope.json"),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("benchmarks/fixtures/talent-hiring-signal-v1.json"),
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--per-run-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inputs = load_benchmark_inputs(args.scope, args.fixture)
    bundle = asyncio.run(
        run_value_gate(
            inputs=inputs,
            repetitions=args.repetitions,
            per_run_timeout_seconds=args.per_run_timeout_seconds,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Output: {args.output}")
    print(json.dumps(bundle["completion"], ensure_ascii=False, indent=2))
    if bundle["benchmark_status"] != "ready_for_human_review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
