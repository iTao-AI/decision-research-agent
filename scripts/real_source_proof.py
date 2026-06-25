from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
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
from api.evidence_verification_repository import get_evidence_verification_detail
from api.publication_repository import (
    finalize_verification_publication,
    get_current_publication,
)
from api.publication_service import build_publication_artifacts
from api.review_artifacts import build_reviewed_artifacts
from api.review_repository import (
    get_decision,
    get_review_detail,
)
from api.run_repository import create_run, finalize_run_transaction, get_run
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
    allowed_hosts: tuple[str, ...]
    records: tuple[RealSourceRecord, ...]


OFFICIAL_SOURCE_HOSTS = {
    "jobs.ashbyhq.com": "LangChain",
    "openai.com": "OpenAI",
    "www.google.com": "Google",
}
SUPPORTED_SOURCE_TYPE = "public_job_posting"


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


def _validate_observed_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at_invalid")
    return value


def load_manifest(path: Path) -> RealSourceManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest_root_invalid")
    if payload.get("manifest_version") != 1 or isinstance(
        payload.get("manifest_version"), bool
    ):
        raise ValueError("manifest_version_unsupported")
    allowed_hosts_payload = payload.get("allowed_hosts")
    if not isinstance(allowed_hosts_payload, list) or not allowed_hosts_payload:
        raise ValueError("manifest_allowed_hosts_required")
    allowed_hosts = tuple(sorted(set(allowed_hosts_payload)))
    if (
        len(allowed_hosts) != len(allowed_hosts_payload)
        or any(
            not isinstance(host, str) or host not in OFFICIAL_SOURCE_HOSTS
            for host in allowed_hosts
        )
    ):
        raise ValueError("manifest_allowed_hosts_invalid")
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
        source_host = urlparse(source_url).hostname
        if source_host not in allowed_hosts:
            raise ValueError("source_host_not_allowed")
        if sample_id in sample_ids:
            raise ValueError("duplicate_sample_id")
        if source_url in urls:
            raise ValueError("duplicate_source_url")
        sample_ids.add(sample_id)
        urls.add(source_url)
        organization = _require_text(
            item.get("organization"), field="organization", max_length=100
        )
        if OFFICIAL_SOURCE_HOSTS[source_host] != organization:
            raise ValueError("source_organization_mismatch")
        source_type = _require_text(
            item.get("source_type"), field="source_type", max_length=80
        )
        if source_type != SUPPORTED_SOURCE_TYPE:
            raise ValueError("source_type_unsupported")
        parsed_records.append(
            RealSourceRecord(
                sample_id=sample_id,
                source_url=source_url,
                source_title=_require_text(
                    item.get("source_title"), field="source_title", max_length=200
                ),
                organization=organization,
                observed_at=_validate_observed_at(
                    _require_text(
                        item.get("observed_at"),
                        field="observed_at",
                        max_length=40,
                    )
                ),
                observation=_require_text(
                    item.get("observation"), field="observation", max_length=500
                ),
                source_type=source_type,
            )
        )
    if len({record.organization for record in parsed_records}) < 3:
        raise ValueError("manifest_organization_count")
    return RealSourceManifest(
        manifest_id=_require_text(
            payload.get("manifest_id"), field="manifest_id", max_length=128
        ),
        manifest_version=payload["manifest_version"],
        question=_require_text(payload.get("question"), field="question", max_length=300),
        allowed_hosts=allowed_hosts,
        records=tuple(parsed_records),
    )


def canonical_manifest_json(manifest: RealSourceManifest) -> str:
    return json.dumps(
        {
            "manifest_id": manifest.manifest_id,
            "manifest_version": manifest.manifest_version,
            "question": manifest.question,
            "allowed_hosts": list(manifest.allowed_hosts),
            "records": [record.__dict__ for record in manifest.records],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_manifest_hash(manifest: RealSourceManifest) -> str:
    return hashlib.sha256(canonical_manifest_json(manifest).encode("utf-8")).hexdigest()


def _require_schema(value: object, fields: set[str], *, error: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(error)
    return value


def _require_hash(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("proof_hash_invalid")
    return value


def _require_identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None
    ):
        raise ValueError("proof_identifier_invalid")
    return value


def _require_positive_int(value: object, *, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(error)
    return value


def assert_complete_proof_report(report: dict) -> None:
    encoded = json.dumps(report, ensure_ascii=False)
    disallowed = (
        "API_SECRET",
        "actor_fingerprint",
        "request_hash",
        "/Users/",
        "/private/",
        "/var/",
        "/tmp/",
    )
    for token in disallowed:
        if token in encoded:
            raise ValueError(f"proof_report_leaks:{token}")
    required = {
        "schema_version",
        "manifest_id",
        "manifest_version",
        "manifest_hash",
        "run_id",
        "source_count",
        "organization_counts",
        "source_type_counts",
        "decision_mode",
        "source_decisions",
        "verification_summary",
        "publication",
        "review",
        "artifact_hashes",
        "idempotency",
        "byte_stability",
        "limits",
    }
    missing = required - set(report)
    if missing:
        raise ValueError(f"proof_report_missing:{','.join(sorted(missing))}")
    if set(report) != required:
        raise ValueError("proof_report_schema")
    if report["schema_version"] != 1 or report["manifest_version"] != 1:
        raise ValueError("proof_report_version")
    _require_identifier(report["manifest_id"])
    _require_identifier(report["run_id"])
    _require_hash(report["manifest_hash"])
    if report["decision_mode"] != "human_operator":
        raise ValueError("proof_decision_mode_not_human")
    source_count = _require_positive_int(
        report["source_count"],
        error="proof_source_count_invalid",
    )
    if not 5 <= source_count <= 8:
        raise ValueError("proof_source_count_invalid")
    decisions = report["source_decisions"]
    if not isinstance(decisions, list) or len(decisions) != source_count:
        raise ValueError("proof_source_count_mismatch")
    decision_fields = {
        "sample_id",
        "organization",
        "source_type",
        "source_url",
        "evidence_id",
        "evidence_fingerprint",
        "verification_id",
        "action",
        "reason_code",
        "revision",
        "verification_state",
        "verification_origin",
    }
    unique_fields = (
        "sample_id",
        "source_url",
        "evidence_id",
        "evidence_fingerprint",
        "verification_id",
    )
    seen = {field: set() for field in unique_fields}
    action_counts: Counter[str] = Counter()
    organization_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    for decision in decisions:
        _require_schema(decision, decision_fields, error="proof_decision_schema")
        if any(
            not isinstance(decision[field], str) or not decision[field]
            for field in (
                "sample_id",
                "organization",
                "source_type",
                "source_url",
                "evidence_id",
                "evidence_fingerprint",
                "verification_id",
            )
        ):
            raise ValueError("proof_decision_schema")
        _require_hash(decision["evidence_fingerprint"])
        if (
            urlparse(decision["source_url"]).scheme != "https"
            or decision["action"] not in {"verify", "reject"}
            or decision["verification_origin"] != "human"
        ):
            raise ValueError("proof_decision_schema")
        _require_positive_int(
            decision["revision"],
            error="proof_decision_schema",
        )
        expected_state = (
            "verified" if decision["action"] == "verify" else "rejected"
        )
        if decision["verification_state"] != expected_state:
            raise ValueError("proof_decision_state_mismatch")
        if (
            decision["action"] == "verify"
            and decision["reason_code"] is not None
        ) or (
            decision["action"] == "reject"
            and (
                not isinstance(decision["reason_code"], str)
                or not decision["reason_code"]
            )
        ):
            raise ValueError("proof_decision_reason_mismatch")
        for field in unique_fields:
            if decision[field] in seen[field]:
                raise ValueError("proof_decision_duplicate")
            seen[field].add(decision[field])
        action_counts[decision["action"]] += 1
        organization_counts[decision["organization"]] += 1
        source_type_counts[decision["source_type"]] += 1
    if dict(sorted(organization_counts.items())) != report["organization_counts"]:
        raise ValueError("proof_organization_counts_mismatch")
    if dict(sorted(source_type_counts.items())) != report["source_type_counts"]:
        raise ValueError("proof_source_type_counts_mismatch")

    summary = _require_schema(
        report["verification_summary"],
        {
            "state_counts",
            "origin_counts",
            "unresolved_count",
            "snapshot_id",
            "snapshot_hash",
        },
        error="proof_verification_summary_schema",
    )
    if summary["unresolved_count"] != 0:
        raise ValueError("proof_unresolved_verifications")
    _require_identifier(summary["snapshot_id"])
    expected_states = {
        state: count
        for state, count in {
            "verified": action_counts["verify"],
            "rejected": action_counts["reject"],
        }.items()
        if count
    }
    if (
        summary["state_counts"] != expected_states
        or summary["origin_counts"] != {"human": source_count}
    ):
        raise ValueError("proof_verification_counts_mismatch")
    _require_hash(summary["snapshot_hash"])

    publication = _require_schema(
        report["publication"],
        {
            "publication_id",
            "revision",
            "verification_snapshot_id",
            "review_id",
            "status",
            "is_current",
            "content_hash",
        },
        error="proof_publication_schema",
    )
    if publication["status"] != "ready" or publication["is_current"] is not True:
        raise ValueError("proof_publication_not_ready")
    for field in (
        "publication_id",
        "verification_snapshot_id",
        "review_id",
    ):
        _require_identifier(publication[field])
    _require_positive_int(
        publication["revision"],
        error="proof_publication_revision_invalid",
    )
    _require_hash(publication["content_hash"])
    if publication["verification_snapshot_id"] != summary["snapshot_id"]:
        raise ValueError("proof_snapshot_mismatch")

    review = _require_schema(
        report["review"],
        {
            "review_id",
            "revision",
            "status",
            "action",
            "decision_id",
            "resolution_id",
            "delivery_status",
        },
        error="proof_review_schema",
    )
    if (
        review["status"] != "approved"
        or review["action"] != "approve"
        or review["delivery_status"] != "ready"
    ):
        raise ValueError("proof_review_not_approved")
    for field in ("review_id", "decision_id", "resolution_id"):
        _require_identifier(review[field])
    if (
        review["review_id"] != publication["review_id"]
        or review["revision"] != publication["revision"]
    ):
        raise ValueError("proof_review_publication_mismatch")

    artifact_hashes = report["artifact_hashes"]
    if not isinstance(artifact_hashes, dict) or len(artifact_hashes) != 2:
        raise ValueError("proof_artifact_schema")
    artifact_fields = {
        "media_type",
        "logical_content_hash",
        "byte_sha256",
        "byte_size",
    }
    media_types = set()
    byte_hashes = {}
    for artifact_id, artifact in artifact_hashes.items():
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ValueError("proof_artifact_schema")
        _require_schema(artifact, artifact_fields, error="proof_artifact_schema")
        media_types.add(artifact["media_type"])
        if artifact["logical_content_hash"] != publication["content_hash"]:
            raise ValueError("proof_artifact_content_hash_mismatch")
        byte_hashes[artifact_id] = _require_hash(artifact["byte_sha256"])
        _require_positive_int(
            artifact["byte_size"],
            error="proof_artifact_size_invalid",
        )
    if media_types != {"application/json", "text/markdown"}:
        raise ValueError("proof_artifact_schema")

    idempotency = _require_schema(
        report["idempotency"],
        {"finalize_replay", "publication_id", "snapshot_id"},
        error="proof_idempotency_schema",
    )
    if (
        idempotency["finalize_replay"] is not True
        or idempotency["publication_id"] != publication["publication_id"]
        or idempotency["snapshot_id"] != summary["snapshot_id"]
    ):
        raise ValueError("proof_idempotency_mismatch")
    _require_identifier(idempotency["publication_id"])
    _require_identifier(idempotency["snapshot_id"])
    byte_stability = _require_schema(
        report["byte_stability"],
        {"stable", "rebuilt_byte_sha256"},
        error="proof_byte_stability_schema",
    )
    if (
        byte_stability["stable"] is not True
        or byte_stability["rebuilt_byte_sha256"] != byte_hashes
    ):
        raise ValueError("proof_byte_stability_mismatch")
    if (
        not isinstance(report["limits"], list)
        or not report["limits"]
        or any(not isinstance(item, str) or not item for item in report["limits"])
    ):
        raise ValueError("proof_limits_invalid")


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


def _artifact_rows(
    *,
    db_path: str,
    run_id: str,
    artifact_ids: tuple[str, ...],
) -> dict[str, dict]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ", ".join("?" for _ in artifact_ids)
        rows = connection.execute(
            f"""
            SELECT artifact_id, media_type, content, content_hash
            FROM run_artifacts_v2
            WHERE run_id = ? AND artifact_id IN ({placeholders})
            """,
            (run_id, *artifact_ids),
        ).fetchall()
        return {row["artifact_id"]: dict(row) for row in rows}
    finally:
        connection.close()


def build_proof_report(
    *,
    manifest_path: Path,
    db_path: str,
    run_id: str,
) -> dict:
    manifest = load_manifest(manifest_path)
    run = get_run(db_path=db_path, run_id=run_id)
    if (
        run["profile_id"] != "talent-hiring-signal"
        or run["query"] != manifest.question
    ):
        raise ValueError("proof_run_manifest_mismatch")
    publication = get_current_publication(db_path=db_path, run_id=run_id)
    if publication is None:
        raise ValueError("proof_publication_missing")
    replay = finalize_verification_publication(
        db_path=db_path,
        run_id=run_id,
        expected_state_version=run["state_version"],
    )
    if not replay.idempotent_replay:
        raise ValueError("proof_finalize_not_idempotent")
    review = get_review_detail(
        db_path=db_path,
        run_id=run_id,
        review_id=publication.review_id,
    )
    if review["decision"] is None or review["resolution"] is None:
        raise ValueError("proof_review_incomplete")

    evidence_by_url = {
        evidence["source_url"]: evidence for evidence in run["evidence"]
    }
    if set(evidence_by_url) != {
        record.source_url for record in manifest.records
    }:
        raise ValueError("proof_manifest_evidence_mismatch")
    source_decisions = []
    for record in manifest.records:
        evidence = evidence_by_url[record.source_url]
        if evidence["snippet"] != record.observation:
            raise ValueError("proof_manifest_evidence_mismatch")
        detail = get_evidence_verification_detail(
            db_path=db_path,
            run_id=run_id,
            evidence_id=evidence["evidence_id"],
        )
        if detail is None or not detail["decisions"]:
            raise ValueError("proof_decision_missing")
        decision = detail["decisions"][-1]
        effective = detail["effective"]
        if (
            decision["evidence_fingerprint"]
            != evidence["evidence_fingerprint"]
            or effective["evidence_fingerprint"]
            != evidence["evidence_fingerprint"]
        ):
            raise ValueError("proof_decision_fingerprint_mismatch")
        source_decisions.append(
            {
                "sample_id": record.sample_id,
                "organization": record.organization,
                "source_type": record.source_type,
                "source_url": record.source_url,
                "evidence_id": evidence["evidence_id"],
                "evidence_fingerprint": evidence["evidence_fingerprint"],
                "verification_id": decision["verification_id"],
                "action": decision["action"],
                "reason_code": decision["reason_code"],
                "revision": decision["revision"],
                "verification_state": effective["verification_state"],
                "verification_origin": effective["verification_origin"],
            }
        )

    stored_artifacts = _artifact_rows(
        db_path=db_path,
        run_id=run_id,
        artifact_ids=publication.artifact_ids,
    )
    if set(stored_artifacts) != set(publication.artifact_ids):
        raise ValueError("proof_artifact_missing")
    decision_record = get_decision(
        db_path=db_path,
        decision_id=review["decision"]["decision_id"],
    )
    if decision_record is None:
        raise ValueError("proof_review_incomplete")
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        original = build_publication_artifacts(
            connection=connection,
            run_id=run_id,
            snapshot_id=publication.verification_snapshot_id,
            revision=publication.revision,
        )
    finally:
        connection.close()
    rebuilt = build_reviewed_artifacts(
        original_brief_json=original.brief_json,
        decision=decision_record,
        revision=publication.revision,
    )
    rebuilt_by_id = {
        artifact["artifact_id"]: artifact for artifact in rebuilt.artifacts
    }
    if set(rebuilt_by_id) != set(stored_artifacts):
        raise ValueError("proof_artifact_rebuild_mismatch")
    artifact_hashes = {}
    rebuilt_byte_hashes = {}
    stable = True
    for artifact_id in publication.artifact_ids:
        stored = stored_artifacts[artifact_id]
        rebuilt_artifact = rebuilt_by_id[artifact_id]
        stored_bytes = stored["content"].encode("utf-8")
        rebuilt_bytes = rebuilt_artifact["content"].encode("utf-8")
        stored_byte_hash = hashlib.sha256(stored_bytes).hexdigest()
        rebuilt_byte_hash = hashlib.sha256(rebuilt_bytes).hexdigest()
        stable = stable and stored_bytes == rebuilt_bytes
        artifact_hashes[artifact_id] = {
            "media_type": stored["media_type"],
            "logical_content_hash": stored["content_hash"],
            "byte_sha256": stored_byte_hash,
            "byte_size": len(stored_bytes),
        }
        rebuilt_byte_hashes[artifact_id] = rebuilt_byte_hash

    organization_counts = Counter(
        record.organization for record in manifest.records
    )
    source_type_counts = Counter(record.source_type for record in manifest.records)
    report = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "manifest_version": manifest.manifest_version,
        "manifest_hash": canonical_manifest_hash(manifest),
        "run_id": run_id,
        "source_count": len(manifest.records),
        "organization_counts": dict(sorted(organization_counts.items())),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "decision_mode": "human_operator",
        "source_decisions": source_decisions,
        "verification_summary": {
            "state_counts": run["verification_summary"]["state_counts"],
            "origin_counts": run["verification_summary"]["origin_counts"],
            "unresolved_count": sum(
                1
                for decision in source_decisions
                if decision["verification_state"] == "unverified"
            ),
            "snapshot_id": publication.verification_snapshot_id,
            "snapshot_hash": run["verification_summary"]["snapshot_hash"],
        },
        "publication": {
            "publication_id": publication.publication_id,
            "revision": publication.revision,
            "verification_snapshot_id": publication.verification_snapshot_id,
            "review_id": publication.review_id,
            "status": publication.status,
            "is_current": publication.is_current,
            "content_hash": publication.content_hash,
        },
        "review": {
            "review_id": publication.review_id,
            "revision": review["review_revision"],
            "status": review["workflow"]["status"],
            "action": review["decision"]["action"],
            "decision_id": review["decision"]["decision_id"],
            "resolution_id": review["resolution"]["resolution_id"],
            "delivery_status": run["delivery_status"],
        },
        "artifact_hashes": artifact_hashes,
        "idempotency": {
            "finalize_replay": replay.idempotent_replay,
            "publication_id": replay.publication.publication_id,
            "snapshot_id": replay.publication.verification_snapshot_id,
        },
        "byte_stability": {
            "stable": stable,
            "rebuilt_byte_sha256": rebuilt_byte_hashes,
        },
        "limits": [
            "This proves one fixed public-source sample workflow only.",
            "Verification means the persisted observation matched the source at decision time.",
            "It is not a crawler, source archive, or market-coverage benchmark.",
            "It does not prove future source availability, hiring outcomes, or production readiness.",
        ],
    }
    assert_complete_proof_report(report)
    return report


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

    build_report_parser = subparsers.add_parser("build-report")
    build_report_parser.add_argument("--manifest", type=Path, required=True)
    build_report_parser.add_argument("--db-path", required=True)
    build_report_parser.add_argument("--run-id", required=True)
    build_report_parser.add_argument("--output", type=Path, required=True)

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
        elif args.command == "check-report":
            report = json.loads(args.report.read_text(encoding="utf-8"))
            assert_complete_proof_report(report)
            _print_json(
                {
                    "manifest_id": report["manifest_id"],
                    "run_id": report["run_id"],
                    "status": "valid",
                }
            )
        else:
            report = build_proof_report(
                manifest_path=args.manifest,
                db_path=args.db_path,
                run_id=args.run_id,
            )
            write_atomic_report(args.output, report)
            _print_json(
                {
                    "manifest_id": report["manifest_id"],
                    "run_id": report["run_id"],
                    "report": args.output.name,
                    "status": "written",
                }
            )
    except OSError:
        _print_json({"error": "input_unavailable"}, stream=sys.stderr)
        return 1
    except json.JSONDecodeError:
        _print_json({"error": "invalid_json"}, stream=sys.stderr)
        return 1
    except (TypeError, ValueError, RuntimeError) as exc:
        message = str(exc)
        if "/" in message or "\\" in message:
            message = "operation_failed"
        _print_json({"error": message}, stream=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
