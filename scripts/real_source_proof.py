from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class RealSourceRecord:
    sample_id: str
    source_url: str
    source_title: str
    organization: str
    observed_at: str
    observation: str
    source_type: str


@dataclass(frozen=True)
class RealSourceManifest:
    manifest_id: str
    manifest_version: int
    question: str
    records: tuple[RealSourceRecord, ...]


def _require_text(value: object, *, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_required")
    normalized = " ".join(value.split())
    if len(normalized) > max_length:
        raise ValueError(f"{field}_too_long")
    return normalized


def _validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("source_url_https_required")
    return value


def load_manifest(path: Path) -> RealSourceManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not 5 <= len(records) <= 8:
        raise ValueError("manifest_record_count")
    sample_ids: set[str] = set()
    urls: set[str] = set()
    parsed_records: list[RealSourceRecord] = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("manifest_record_invalid")
        sample_id = _require_text(
            item.get("sample_id"), field="sample_id", max_length=128
        )
        source_url = _validate_url(
            _require_text(item.get("source_url"), field="source_url", max_length=500)
        )
        if sample_id in sample_ids:
            raise ValueError("duplicate_sample_id")
        if source_url in urls:
            raise ValueError("duplicate_source_url")
        sample_ids.add(sample_id)
        urls.add(source_url)
        parsed_records.append(
            RealSourceRecord(
                sample_id=sample_id,
                source_url=source_url,
                source_title=_require_text(
                    item.get("source_title"), field="source_title", max_length=200
                ),
                organization=_require_text(
                    item.get("organization"), field="organization", max_length=100
                ),
                observed_at=_require_text(
                    item.get("observed_at"), field="observed_at", max_length=40
                ),
                observation=_require_text(
                    item.get("observation"), field="observation", max_length=500
                ),
                source_type=_require_text(
                    item.get("source_type"), field="source_type", max_length=80
                ),
            )
        )
    return RealSourceManifest(
        manifest_id=_require_text(
            payload.get("manifest_id"), field="manifest_id", max_length=128
        ),
        manifest_version=int(payload.get("manifest_version")),
        question=_require_text(payload.get("question"), field="question", max_length=300),
        records=tuple(parsed_records),
    )


def canonical_manifest_json(manifest: RealSourceManifest) -> str:
    return json.dumps(
        {
            "manifest_id": manifest.manifest_id,
            "manifest_version": manifest.manifest_version,
            "question": manifest.question,
            "records": [record.__dict__ for record in manifest.records],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_manifest_hash(manifest: RealSourceManifest) -> str:
    return hashlib.sha256(canonical_manifest_json(manifest).encode("utf-8")).hexdigest()
