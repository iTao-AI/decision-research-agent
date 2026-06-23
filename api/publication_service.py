from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3

from agent.profile_registry import profile_registry
from agent.research import EvidenceEntry
from agent.talent_contracts import DecisionBrief, ResearchPacket, ReviewBundle
from api.evidence_verification_models import (
    EffectiveEvidenceVerification,
    VerificationSnapshotRecord,
)
from api.talent_artifacts import build_talent_artifacts


@dataclass(frozen=True)
class PublicationArtifacts:
    review: ReviewBundle
    brief: DecisionBrief
    artifacts: tuple[dict, ...]
    artifact_ids: tuple[str, ...]
    brief_json: str
    brief_markdown: str


class PublicationBuildConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _load_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT run_id, thread_id, profile_id, profile_version, scope_json
        FROM research_runs_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise PublicationBuildConflict("publication_run_not_found")
    profile = profile_registry.get("talent-hiring-signal")
    if (
        row["profile_id"] != profile.profile_id
        or row["profile_version"] != profile.version
    ):
        raise PublicationBuildConflict("unsupported_publication_profile")
    return row


def _load_packets(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> list[ResearchPacket]:
    rows = connection.execute(
        """
        SELECT packet_json
        FROM research_packets_v2
        WHERE run_id = ?
        ORDER BY packet_id
        """,
        (run_id,),
    ).fetchall()
    if not rows:
        raise PublicationBuildConflict("publication_packet_state_missing")
    try:
        return [
            ResearchPacket.model_validate_json(row["packet_json"])
            for row in rows
        ]
    except ValueError as exc:
        raise PublicationBuildConflict(
            "publication_packet_state_invalid"
        ) from exc


def _load_evidence(
    connection: sqlite3.Connection,
    *,
    run: sqlite3.Row,
) -> tuple[list[EvidenceEntry], dict[str, sqlite3.Row]]:
    rows = connection.execute(
        """
        SELECT *
        FROM evidence_entries_v2
        WHERE run_id = ?
        ORDER BY evidence_id
        """,
        (run["run_id"],),
    ).fetchall()
    entries = [
        EvidenceEntry(
            thread_id=run["thread_id"],
            query_text=row["query_text"],
            subagent_name=row["subagent_name"],
            tool_name=row["tool_name"],
            source_url=row["source_url"],
            source_identity=row["source_identity"],
            snippet=row["snippet"],
            evidence_fingerprint=row["evidence_fingerprint"],
            retrieved_at=row["retrieved_at"],
            tool_call_id=row["tool_call_id"],
            citation_status=row["citation_status"],
            verification_status=row["verification_status"],
            baseline_verification_origin=row[
                "baseline_verification_origin"
            ],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return entries, {row["evidence_id"]: row for row in rows}


def _load_snapshot(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    snapshot_id: str,
) -> VerificationSnapshotRecord:
    row = connection.execute(
        """
        SELECT *
        FROM evidence_verification_snapshots_v2
        WHERE run_id = ? AND snapshot_id = ?
        """,
        (run_id, snapshot_id),
    ).fetchone()
    if row is None:
        raise PublicationBuildConflict("verification_snapshot_not_found")
    try:
        return VerificationSnapshotRecord.model_validate(
            {
                "snapshot_id": row["snapshot_id"],
                "run_id": row["run_id"],
                "revision": row["revision"],
                "snapshot": json.loads(row["snapshot_json"]),
                "snapshot_hash": row["snapshot_hash"],
                "created_at": row["created_at"],
            }
        )
    except ValueError as exc:
        raise PublicationBuildConflict(
            "verification_snapshot_invalid"
        ) from exc


def _verification_projection(
    *,
    snapshot: VerificationSnapshotRecord,
    evidence_by_id: dict[str, sqlite3.Row],
) -> dict[str, EffectiveEvidenceVerification]:
    projected: dict[str, EffectiveEvidenceVerification] = {}
    for item in snapshot.snapshot:
        evidence = evidence_by_id.get(item.evidence_id)
        if (
            evidence is None
            or evidence["evidence_fingerprint"]
            != item.evidence_fingerprint
        ):
            raise PublicationBuildConflict(
                "verification_snapshot_evidence_mismatch"
            )
        projected[item.evidence_id] = item
    if set(projected) != set(evidence_by_id):
        raise PublicationBuildConflict(
            "verification_snapshot_evidence_mismatch"
        )
    return projected


def build_publication_artifacts(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_id: str,
    revision: int,
) -> PublicationArtifacts:
    if revision < 1:
        raise PublicationBuildConflict("publication_revision_invalid")
    run = _load_run(connection, run_id=run_id)
    packets = _load_packets(connection, run_id=run_id)
    evidence, evidence_by_id = _load_evidence(connection, run=run)
    snapshot = _load_snapshot(
        connection,
        run_id=run_id,
        snapshot_id=snapshot_id,
    )
    verification = _verification_projection(
        snapshot=snapshot,
        evidence_by_id=evidence_by_id,
    )
    try:
        generated_at = datetime.fromisoformat(snapshot.created_at)
        review, brief, artifacts = build_talent_artifacts(
            run_id=run_id,
            scope=json.loads(run["scope_json"]),
            packets=packets,
            evidence_entries=evidence,
            generated_at=generated_at,
            revision=revision,
            verification_snapshot_id=snapshot.snapshot_id,
            verification_snapshot_hash=snapshot.snapshot_hash,
            verification_by_evidence_id=verification,
            mandatory_review_triggers=(
                "verification_snapshot_changed",
            ),
        )
    except PublicationBuildConflict:
        raise
    except (TypeError, ValueError) as exc:
        code = (
            "verification_snapshot_evidence_mismatch"
            if str(exc) == "verification_snapshot_evidence_mismatch"
            else "publication_artifact_build_invalid"
        )
        raise PublicationBuildConflict(code) from exc
    artifact_by_type = {
        artifact["media_type"]: artifact
        for artifact in artifacts
    }
    return PublicationArtifacts(
        review=review,
        brief=brief,
        artifacts=tuple(artifacts),
        artifact_ids=tuple(
            artifact["artifact_id"]
            for artifact in artifacts
        ),
        brief_json=artifact_by_type["application/json"]["content"],
        brief_markdown=artifact_by_type["text/markdown"]["content"],
    )
