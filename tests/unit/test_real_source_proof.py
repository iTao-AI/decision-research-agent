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
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _record(sample_id: str, url: str = "https://example.com/careers/agent"):
    return {
        "sample_id": sample_id,
        "source_url": url,
        "source_title": "Agent infrastructure role",
        "organization": "Example",
        "observed_at": "2026-06-23T00:00:00Z",
        "observation": "The role asks for agent infrastructure reliability work.",
        "source_type": "public_job_posting",
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
            _record("real_source_001", "https://example.com/careers/other"),
            _record("real_source_003"),
            _record("real_source_004"),
            _record("real_source_005"),
        ],
    )

    with pytest.raises(ValueError, match="duplicate_sample_id"):
        load_manifest(path)


def test_manifest_hash_is_ordered_and_stable(tmp_path):
    records = [
        _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
        for i in range(1, 6)
    ]
    path = _write_manifest(tmp_path, records)

    manifest = load_manifest(path)

    assert isinstance(manifest, RealSourceManifest)
    assert canonical_manifest_hash(manifest) == canonical_manifest_hash(manifest)


def test_manifest_evidence_starts_as_ordinary_unverified(tmp_path):
    manifest = load_manifest(
        _write_manifest(
            tmp_path,
            [
                _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
                for i in range(1, 6)
            ],
        )
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
        _write_manifest(
            tmp_path,
            [
                _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
                for i in range(1, 6)
            ],
        )
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

    with pytest.raises(ValueError, match="proof_report_leaks"):
        write_atomic_report(
            tmp_path / "proof.json",
            {
                "manifest_id": "x",
                "manifest_hash": "h",
                "run_id": "run",
                "source_count": 5,
                "decision_mode": "human_operator",
                "verification_summary": {"unresolved_count": 0},
                "publication": {"status": "ready"},
                "review": {"status": "approved"},
                "artifact_hashes": {},
                "limits": ["sample only"],
                "actor_fingerprint": "secret",
            },
        )


def test_main_manifest_hash_outputs_bounded_json(tmp_path, capsys):
    manifest_path = _write_manifest(
        tmp_path,
        [
            _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
            for i in range(1, 6)
        ],
    )
    from scripts.real_source_proof import main

    assert main(["manifest-hash", "--manifest", str(manifest_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manifest_id"] == "talent-agent-hiring-signals-v1"
    assert re.fullmatch(r"[0-9a-f]{64}", payload["manifest_hash"])


def test_script_entrypoint_runs_from_repository_root(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [
            _record(f"real_source_00{i}", f"https://example.com/careers/{i}")
            for i in range(1, 6)
        ],
    )
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
