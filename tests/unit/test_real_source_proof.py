from pathlib import Path
import json
import re
import subprocess
import sys

import pytest

from agent.research import evidence_id_for
from scripts.real_source_proof import (
    RealSourceManifest,
    build_research_packet_for_manifest,
    canonical_manifest_hash,
    evidence_entries_for_manifest,
    load_manifest,
)


def _write_manifest(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "talent-agent-hiring-signals-v1",
                "manifest_version": 1,
                "question": "What hiring signals appear in AI Agent roles?",
                "allowed_hosts": [
                    "jobs.ashbyhq.com",
                    "openai.com",
                    "www.google.com",
                ],
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _record(
    sample_id: str,
    url: str = "https://openai.com/careers/agent",
    organization: str = "OpenAI",
):
    return {
        "sample_id": sample_id,
        "source_url": url,
        "source_title": "Agent infrastructure role",
        "organization": organization,
        "observed_at": "2026-06-23T00:00:00Z",
        "observation": "The role asks for agent infrastructure reliability work.",
        "source_type": "public_job_posting",
    }


def _records(count: int = 5) -> list[dict]:
    sources = (
        ("OpenAI", "https://openai.com/careers"),
        ("LangChain", "https://jobs.ashbyhq.com/langchain"),
        ("Google", "https://www.google.com/about/careers"),
    )
    return [
        _record(
            f"real_source_{index:03d}",
            f"{sources[(index - 1) % len(sources)][1]}/{index}",
            sources[(index - 1) % len(sources)][0],
        )
        for index in range(1, count + 1)
    ]


def _valid_report() -> dict:
    source_decisions = []
    for index, record in enumerate(_records(), start=1):
        source_decisions.append(
            {
                "sample_id": record["sample_id"],
                "organization": record["organization"],
                "source_type": record["source_type"],
                "source_url": record["source_url"],
                "evidence_id": f"evidence-{index}",
                "evidence_fingerprint": f"{index:064x}",
                "verification_id": f"verification-{index}",
                "action": "verify",
                "reason_code": None,
                "revision": 1,
                "verification_state": "verified",
                "verification_origin": "human",
            }
        )
    logical_hash = "a" * 64
    json_byte_hash = "b" * 64
    markdown_byte_hash = "c" * 64
    return {
        "schema_version": 1,
        "manifest_id": "talent-agent-hiring-signals-v1",
        "manifest_version": 1,
        "manifest_hash": "d" * 64,
        "run_id": "run-proof",
        "source_count": 5,
        "organization_counts": {"Google": 1, "LangChain": 2, "OpenAI": 2},
        "source_type_counts": {"public_job_posting": 5},
        "decision_mode": "human_operator",
        "source_decisions": source_decisions,
        "verification_summary": {
            "state_counts": {"verified": 5},
            "origin_counts": {"human": 5},
            "unresolved_count": 0,
            "snapshot_id": "snapshot-proof",
            "snapshot_hash": "e" * 64,
        },
        "publication": {
            "publication_id": "publication-proof",
            "revision": 2,
            "verification_snapshot_id": "snapshot-proof",
            "review_id": "review-proof",
            "status": "ready",
            "is_current": True,
            "content_hash": logical_hash,
        },
        "review": {
            "review_id": "review-proof",
            "revision": 2,
            "status": "approved",
            "action": "approve",
            "decision_id": "decision-proof",
            "resolution_id": "resolution-proof",
            "delivery_status": "ready",
        },
        "artifact_hashes": {
            "decision-brief.r2.reviewed.json": {
                "media_type": "application/json",
                "logical_content_hash": logical_hash,
                "byte_sha256": json_byte_hash,
                "byte_size": 100,
            },
            "decision-brief.r2.reviewed.md": {
                "media_type": "text/markdown",
                "logical_content_hash": logical_hash,
                "byte_sha256": markdown_byte_hash,
                "byte_size": 200,
            },
        },
        "idempotency": {
            "finalize_replay": True,
            "publication_id": "publication-proof",
            "snapshot_id": "snapshot-proof",
        },
        "byte_stability": {
            "stable": True,
            "rebuilt_byte_sha256": {
                "decision-brief.r2.reviewed.json": json_byte_hash,
                "decision-brief.r2.reviewed.md": markdown_byte_hash,
            },
        },
        "limits": ["bounded sample"],
    }


def test_manifest_requires_five_to_eight_records(tmp_path):
    path = _write_manifest(tmp_path, [_record("real_source_001")])

    with pytest.raises(ValueError, match="manifest_record_count"):
        load_manifest(path)


def test_manifest_rejects_duplicate_sample_id_and_url(tmp_path):
    path = _write_manifest(
        tmp_path,
        [
            _record("real_source_001"),
            _record(
                "real_source_001",
                "https://jobs.ashbyhq.com/langchain/other",
                "LangChain",
            ),
            _record(
                "real_source_003",
                "https://www.google.com/about/careers/3",
                "Google",
            ),
            _record("real_source_004", "https://openai.com/careers/4"),
            _record(
                "real_source_005",
                "https://jobs.ashbyhq.com/langchain/5",
                "LangChain",
            ),
        ],
    )

    with pytest.raises(ValueError, match="duplicate_sample_id"):
        load_manifest(path)


def test_manifest_hash_is_ordered_and_stable(tmp_path):
    records = _records()
    path = _write_manifest(tmp_path, records)

    manifest = load_manifest(path)

    assert isinstance(manifest, RealSourceManifest)
    assert canonical_manifest_hash(manifest) == canonical_manifest_hash(manifest)


def test_manifest_evidence_starts_as_ordinary_unverified(tmp_path):
    manifest = load_manifest(
        _write_manifest(tmp_path, _records())
    )

    entries = evidence_entries_for_manifest(
        manifest,
        thread_id="thread-real-proof",
        query_text=manifest.question,
    )

    assert len(entries) == 5
    assert {entry.baseline_verification_origin for entry in entries} == {"none"}
    assert {entry.verification_status for entry in entries} == {"unverified"}
    assert all(entry.tool_name == "real_source_manifest" for entry in entries)


def test_research_packet_references_real_evidence_ids(tmp_path):
    manifest = load_manifest(
        _write_manifest(tmp_path, _records())
    )
    run_id = "run_real_source"
    entries = evidence_entries_for_manifest(
        manifest,
        thread_id="thread-real-proof",
        query_text=manifest.question,
    )

    packet = build_research_packet_for_manifest(
        manifest=manifest,
        run_id=run_id,
        evidence_entries=entries,
    )

    expected_ids = {
        evidence_id_for(entry.source_url, entry.snippet, run_id=run_id)
        for entry in entries
    }
    actual_ids = {
        evidence_ref
        for finding in packet.findings
        for evidence_ref in finding.evidence_refs
    }
    assert actual_ids == expected_ids


def test_report_writer_rejects_private_fields(tmp_path):
    from scripts.real_source_proof import write_atomic_report

    report = _valid_report()
    report["actor_fingerprint"] = "secret"
    with pytest.raises(ValueError, match="proof_report_leaks"):
        write_atomic_report(tmp_path / "proof.json", report)


def test_main_manifest_hash_outputs_bounded_json(tmp_path, capsys):
    manifest_path = _write_manifest(tmp_path, _records())
    from scripts.real_source_proof import main

    assert main(["manifest-hash", "--manifest", str(manifest_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manifest_id"] == "talent-agent-hiring-signals-v1"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["manifest_hash"])


def test_script_entrypoint_runs_from_repository_root(tmp_path):
    manifest_path = _write_manifest(tmp_path, _records())
    repository_root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/real_source_proof.py",
            "manifest-hash",
            "--manifest",
            str(manifest_path),
        ],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["manifest_id"] == (
        "talent-agent-hiring-signals-v1"
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("manifest_version", 2, "manifest_version_unsupported"),
        ("manifest_version", "1", "manifest_version_unsupported"),
    ],
)
def test_manifest_rejects_unsupported_version(tmp_path, field, value, error):
    path = _write_manifest(tmp_path, _records())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_manifest(path)


def test_manifest_requires_three_organizations(tmp_path):
    records = [
        _record(f"real_source_{index:03d}", f"https://openai.com/careers/{index}")
        for index in range(1, 6)
    ]

    with pytest.raises(ValueError, match="manifest_organization_count"):
        load_manifest(_write_manifest(tmp_path, records))


def test_manifest_rejects_unsupported_source_type(tmp_path):
    records = _records()
    records[0]["source_type"] = "blog_post"

    with pytest.raises(ValueError, match="source_type_unsupported"):
        load_manifest(_write_manifest(tmp_path, records))


@pytest.mark.parametrize(
    "observed_at",
    ["not-a-time", "2026-06-23T00:00:00"],
)
def test_manifest_requires_timezone_aware_observed_at(tmp_path, observed_at):
    records = _records()
    records[0]["observed_at"] = observed_at

    with pytest.raises(ValueError, match="observed_at_invalid"):
        load_manifest(_write_manifest(tmp_path, records))


def test_manifest_rejects_undeclared_or_unapproved_host(tmp_path):
    records = _records()
    records[0]["source_url"] = "https://careers.example.org/agent"

    with pytest.raises(ValueError, match="source_host_not_allowed"):
        load_manifest(_write_manifest(tmp_path, records))


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda report: report.pop("source_decisions"),
            "proof_report_missing:source_decisions",
        ),
        (
            lambda report: report["source_decisions"][0].pop(
                "evidence_fingerprint"
            ),
            "proof_decision_schema",
        ),
        (
            lambda report: report["review"].update(
                {"status": "rejected", "action": "reject"}
            ),
            "proof_review_not_approved",
        ),
        (
            lambda report: report.update({"manifest_hash": "not-a-hash"}),
            "proof_hash_invalid",
        ),
        (
            lambda report: report.update({"source_count": 6}),
            "proof_source_count_mismatch",
        ),
        (
            lambda report: report["source_decisions"][0].update(
                {"revision": "1"}
            ),
            "proof_decision_schema",
        ),
        (
            lambda report: report.update({"run_id": ""}),
            "proof_identifier_invalid",
        ),
    ],
)
def test_report_checker_rejects_incomplete_or_inconsistent_report(mutate, error):
    from scripts.real_source_proof import assert_complete_proof_report

    report = _valid_report()
    mutate(report)

    with pytest.raises(ValueError, match=error):
        assert_complete_proof_report(report)


def test_main_redacts_absolute_path_from_error(tmp_path, capsys):
    from scripts.real_source_proof import main

    missing = tmp_path / "private" / "missing.json"

    assert main(["check-report", "--report", str(missing)]) == 1
    error = capsys.readouterr().err
    assert str(missing) not in error
    assert json.loads(error) == {"error": "input_unavailable"}


def test_main_rejects_non_object_manifest_with_bounded_json(tmp_path, capsys):
    from scripts.real_source_proof import main

    manifest_path = tmp_path / "private" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text("[]", encoding="utf-8")

    assert main(["manifest-hash", "--manifest", str(manifest_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(manifest_path) not in captured.err
    assert "Traceback" not in captured.err
    assert json.loads(captured.err) == {"error": "manifest_root_invalid"}
