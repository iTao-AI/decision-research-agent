from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.research import EvidenceEntry, evidence_id_for
from agent.talent_contracts import ResearchPacket
from api.review_models import (
    checkpoint_thread_id,
    post_review_segment_id,
    review_workflow_id,
)
from api.run_repository import create_run, finalize_run_transaction
from api.talent_artifacts import build_talent_artifacts


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


def assert_complete_proof_report(report: dict) -> None:
    required = {
        "manifest_id",
        "manifest_hash",
        "run_id",
        "source_count",
        "decision_mode",
        "verification_summary",
        "publication",
        "review",
        "artifact_hashes",
        "limits",
    }
    missing = required - set(report)
    if missing:
        raise ValueError(f"proof_report_missing:{','.join(sorted(missing))}")
    if report["decision_mode"] != "human_operator":
        raise ValueError("proof_decision_mode_not_human")
    if report["verification_summary"].get("unresolved_count") != 0:
        raise ValueError("proof_unresolved_verifications")
    if report["publication"].get("status") != "ready":
        raise ValueError("proof_publication_not_ready")
    encoded = json.dumps(report, ensure_ascii=False)
    disallowed = ("API_SECRET", "actor_fingerprint", "request_hash", "/Users/")
    for token in disallowed:
        if token in encoded:
            raise ValueError(f"proof_report_leaks:{token}")


def write_atomic_report(path: Path, report: dict) -> None:
    assert_complete_proof_report(report)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def evidence_entries_for_manifest(
    manifest: RealSourceManifest,
    *,
    thread_id: str,
    query_text: str,
) -> tuple[EvidenceEntry, ...]:
    created_at = datetime.now(timezone.utc).isoformat()
    return tuple(
        EvidenceEntry(
            thread_id=thread_id,
            query_text=query_text,
            subagent_name="operator_manifest",
            tool_name="real_source_manifest",
            source_url=record.source_url,
            source_identity=record.source_url,
            snippet=record.observation,
            citation_status="cited",
            verification_status="unverified",
            baseline_verification_origin="none",
            created_at=created_at,
        )
        for record in manifest.records
    )


def build_research_packet_for_manifest(
    *,
    manifest: RealSourceManifest,
    run_id: str,
    evidence_entries: tuple[EvidenceEntry, ...],
) -> ResearchPacket:
    findings = []
    claims = []
    for index, (record, entry) in enumerate(
        zip(manifest.records, evidence_entries), start=1
    ):
        evidence_id = evidence_id_for(entry.source_url, entry.snippet, run_id=run_id)
        finding_id = f"finding-{index}"
        findings.append(
            {
                "finding_id": finding_id,
                "research_question_id": "real_source_question",
                "statement": record.observation,
                "evidence_refs": [evidence_id],
                "sample_scope": "real_source_manifest",
                "confidence": 0.8,
            }
        )
        claims.append(
            {
                "claim_id": f"claim-{index}",
                "text": record.observation,
                "claim_type": "signal",
                "finding_refs": [finding_id],
                "evidence_refs": [evidence_id],
                "confidence": 0.8,
                "citation_status": "cited",
                "verification_status": "unverified",
                "review_status": "pending",
                "conflict_status": "none",
            }
        )
    return ResearchPacket.model_validate(
        {
            "packet_id": "real-source-proof-packet",
            "scope_id": manifest.manifest_id,
            "findings": findings,
            "candidate_claims": claims,
        }
    )


def manifest_scope(manifest: RealSourceManifest) -> dict:
    return {
        "target_roles": ["AI Agent Engineer", "Applied AI Engineer"],
        "target_companies": sorted({record.organization for record in manifest.records}),
        "time_window": {"start": "2026-06-01", "end": "2026-06-23"},
        "declared_samples": [
            {
                "sample_id": record.sample_id,
                "source_type": record.source_type,
                "reference": record.source_url,
            }
            for record in manifest.records
        ],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["real_source_question"],
        "requested_outputs": ["decision_brief"],
    }


def seed_real_source_run(*, manifest_path: Path, db_path: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    created = create_run(
        db_path=db_path,
        thread_id=f"thread-{manifest.manifest_id}",
        query=manifest.question,
        profile_id="talent-hiring-signal",
        profile_version="1",
        scope=manifest_scope(manifest),
    )
    entries = evidence_entries_for_manifest(
        manifest,
        thread_id=created["thread_id"],
        query_text=manifest.question,
    )
    packet = build_research_packet_for_manifest(
        manifest=manifest,
        run_id=created["run_id"],
        evidence_entries=entries,
    )
    scope = manifest_scope(manifest)
    review, _brief, artifacts = build_talent_artifacts(
        run_id=created["run_id"],
        scope=scope,
        packets=[packet],
        evidence_entries=list(entries),
        generated_at=datetime.now(timezone.utc),
    )
    workflow_id = review_workflow_id(
        created["run_id"],
        review.review_id,
        review.revision,
    )
    accepted = finalize_run_transaction(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=list(entries),
        research_packets=[packet],
        review_bundle=review,
        artifacts=artifacts,
        review_workflow={
            "workflow_id": workflow_id,
            "checkpoint_thread_id": checkpoint_thread_id(workflow_id),
            "post_review_segment_id": post_review_segment_id(
                created["run_id"],
                review.review_id,
                review.revision,
            ),
        },
    )
    if not accepted:
        raise RuntimeError("seed_run_finalization_failed")
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_hash": canonical_manifest_hash(manifest),
        "run_id": created["run_id"],
        "segment_id": created["segment_id"],
        "review_id": review.review_id,
        "evidence_count": len(entries),
    }


def _print_json(payload: dict, *, stream=None) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        file=stream,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="real_source_proof")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_hash_parser = subparsers.add_parser("manifest-hash")
    manifest_hash_parser.add_argument("--manifest", type=Path, required=True)

    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--manifest", type=Path, required=True)
    seed_parser.add_argument("--db-path", required=True)

    check_report_parser = subparsers.add_parser("check-report")
    check_report_parser.add_argument("--report", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "manifest-hash":
            manifest = load_manifest(args.manifest)
            _print_json(
                {
                    "manifest_id": manifest.manifest_id,
                    "manifest_hash": canonical_manifest_hash(manifest),
                    "source_count": len(manifest.records),
                }
            )
        elif args.command == "seed":
            _print_json(
                seed_real_source_run(
                    manifest_path=args.manifest,
                    db_path=args.db_path,
                )
            )
        else:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            assert_complete_proof_report(report)
            _print_json(
                {
                    "manifest_id": report["manifest_id"],
                    "run_id": report["run_id"],
                    "status": "valid",
                }
            )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        _print_json({"error": str(exc)}, stream=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
