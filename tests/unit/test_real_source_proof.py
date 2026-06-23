from pathlib import Path
import json

import pytest

from scripts.real_source_proof import (
    RealSourceManifest,
    canonical_manifest_hash,
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
