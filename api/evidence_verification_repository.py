from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

from api.evidence_verification_models import (
    EffectiveEvidenceVerification,
    EvidencePreflightResult,
    VerificationDecisionRecord,
    VerificationDecisionRequest,
    VerificationSnapshotRecord,
    canonical_hash,
    snapshot_id_for,
    verification_request_hash,
)
from api.evidence_verification_service import evaluate_evidence_preflight
from api.review_repository import init_review_schema
from api.run_repository import _connect, _now


VERIFICATION_MIGRATION_VERSION = "005_evidence_verification_authority"
VERIFICATION_MIGRATION_CHECKSUM = "evidence-verification-authority-v1"
DECISION_HISTORY_LIMIT = 100


@dataclass(frozen=True)
class VerificationDecisionAcceptance:
    decision: VerificationDecisionRecord
    preflight: EvidencePreflightResult
    idempotent_replay: bool


@dataclass(frozen=True)
class VerificationSnapshotAcceptance:
    snapshot: VerificationSnapshotRecord
    idempotent_replay: bool


class VerificationConflict(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _is_aggregate_only_scope(scope_json: str) -> bool:
    try:
        scope = json.loads(scope_json)
    except (TypeError, ValueError):
        return False
    allowed = scope.get("allowed_source_types")
    samples = scope.get("declared_samples", [])
    return (
        allowed == ["provided_aggregate"]
        and bool(samples)
        and all(
            isinstance(sample, dict)
            and sample.get("source_type") == "provided_aggregate"
            and isinstance(sample.get("reference"), str)
            and bool(sample["reference"])
            for sample in samples
        )
    )


def _backfill_declared_fixture_origin(
    connection: sqlite3.Connection,
) -> None:
    runs = connection.execute(
        """
        SELECT run_id, scope_json
        FROM research_runs_v2
        WHERE profile_id = 'talent-hiring-signal'
        """
    ).fetchall()
    fixture_run_ids = [
        row["run_id"]
        for row in runs
        if _is_aggregate_only_scope(row["scope_json"])
    ]
    connection.executemany(
        """
        UPDATE evidence_entries_v2
        SET baseline_verification_origin = 'declared_fixture'
        WHERE run_id = ?
          AND verification_status = 'verified'
          AND baseline_verification_origin = 'none'
        """,
        [(run_id,) for run_id in fixture_run_ids],
    )


def init_evidence_verification_schema(
    db_path: str | None = None,
) -> None:
    init_review_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS
                evidence_verification_preflights_v2 (
                    preflight_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    evidence_id TEXT NOT NULL
                        REFERENCES evidence_entries_v2(evidence_id)
                        ON DELETE CASCADE,
                    evidence_fingerprint TEXT NOT NULL,
                    preflight_version TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('eligible', 'blocked')),
                    checks_json TEXT NOT NULL,
                    preflight_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(
                        run_id,
                        evidence_id,
                        evidence_fingerprint,
                        preflight_version,
                        preflight_hash
                    )
                );

                CREATE TABLE IF NOT EXISTS
                evidence_verification_decisions_v2 (
                    verification_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    evidence_id TEXT NOT NULL
                        REFERENCES evidence_entries_v2(evidence_id)
                        ON DELETE CASCADE,
                    evidence_fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    action TEXT NOT NULL
                        CHECK(action IN ('verify', 'reject')),
                    reason_code TEXT,
                    reason_note TEXT,
                    preflight_id TEXT NOT NULL
                        REFERENCES evidence_verification_preflights_v2(
                            preflight_id
                        ),
                    actor_fingerprint TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(
                        run_id,
                        evidence_id,
                        evidence_fingerprint,
                        revision
                    )
                );

                CREATE TABLE IF NOT EXISTS
                evidence_verification_snapshots_v2 (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL
                        REFERENCES research_runs_v2(run_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    snapshot_json TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, revision),
                    UNIQUE(run_id, snapshot_hash)
                );

                CREATE INDEX IF NOT EXISTS
                idx_evidence_preflights_evidence
                ON evidence_verification_preflights_v2(
                    run_id,
                    evidence_id,
                    created_at
                );

                CREATE INDEX IF NOT EXISTS
                idx_evidence_decisions_current
                ON evidence_verification_decisions_v2(
                    run_id,
                    evidence_id,
                    evidence_fingerprint,
                    revision DESC
                );
                """
            )
            migration_applied = connection.execute(
                """
                SELECT 1
                FROM schema_migrations
                WHERE version = ?
                """,
                (VERIFICATION_MIGRATION_VERSION,),
            ).fetchone()
            if migration_applied is None:
                _backfill_declared_fixture_origin(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(
                    version,
                    applied_at,
                    checksum
                ) VALUES (?, ?, ?)
                """,
                (
                    VERIFICATION_MIGRATION_VERSION,
                    _now(),
                    VERIFICATION_MIGRATION_CHECKSUM,
                ),
            )
    finally:
        connection.close()


def _decision_record(row: sqlite3.Row) -> VerificationDecisionRecord:
    return VerificationDecisionRecord.model_validate(
        {
            "verification_id": row["verification_id"],
            "run_id": row["run_id"],
            "evidence_id": row["evidence_id"],
            "evidence_fingerprint": row["evidence_fingerprint"],
            "revision": row["revision"],
            "action": row["action"],
            "reason_code": row["reason_code"],
            "reason_note": row["reason_note"],
            "preflight_id": row["preflight_id"],
            "created_at": row["created_at"],
        }
    )


def _preflight_record(row: sqlite3.Row) -> EvidencePreflightResult:
    return EvidencePreflightResult.model_validate(
        {
            "preflight_id": row["preflight_id"],
            "run_id": row["run_id"],
            "evidence_id": row["evidence_id"],
            "evidence_fingerprint": row["evidence_fingerprint"],
            "preflight_version": row["preflight_version"],
            "status": row["status"],
            "checks": json.loads(row["checks_json"]),
            "preflight_hash": row["preflight_hash"],
        }
    )


def _snapshot_record(row: sqlite3.Row) -> VerificationSnapshotRecord:
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
        raise VerificationConflict("verification_snapshot_invalid") from exc


def _target_rows(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    evidence_id: str,
) -> tuple[sqlite3.Row, sqlite3.Row]:
    run = connection.execute(
        """
        SELECT run_id, profile_id, scope_json
        FROM research_runs_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    evidence = connection.execute(
        """
        SELECT *
        FROM evidence_entries_v2
        WHERE run_id = ? AND evidence_id = ?
        """,
        (run_id, evidence_id),
    ).fetchone()
    if run is None or evidence is None:
        raise VerificationConflict("evidence_not_found")
    return run, evidence


def _persist_preflight(
    connection: sqlite3.Connection,
    *,
    preflight: EvidencePreflightResult,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO evidence_verification_preflights_v2 (
            preflight_id,
            run_id,
            evidence_id,
            evidence_fingerprint,
            preflight_version,
            status,
            checks_json,
            preflight_hash,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            preflight.preflight_id,
            preflight.run_id,
            preflight.evidence_id,
            preflight.evidence_fingerprint,
            preflight.preflight_version,
            preflight.status,
            json.dumps(
                [item.model_dump(mode="json") for item in preflight.checks],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            preflight.preflight_hash,
            _now(),
        ),
    )
    stored = connection.execute(
        """
        SELECT preflight_hash
        FROM evidence_verification_preflights_v2
        WHERE preflight_id = ?
        """,
        (preflight.preflight_id,),
    ).fetchone()
    if stored is None or stored["preflight_hash"] != preflight.preflight_hash:
        raise VerificationConflict("verification_persistence_conflict")


def get_or_create_evidence_preflight(
    *,
    db_path: str,
    run_id: str,
    evidence_id: str,
) -> EvidencePreflightResult:
    init_evidence_verification_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            run, evidence = _target_rows(
                connection,
                run_id=run_id,
                evidence_id=evidence_id,
            )
            preflight = evaluate_evidence_preflight(
                run=dict(run),
                evidence=dict(evidence),
            )
            _persist_preflight(connection, preflight=preflight)
            row = connection.execute(
                """
                SELECT *
                FROM evidence_verification_preflights_v2
                WHERE preflight_id = ?
                """,
                (preflight.preflight_id,),
            ).fetchone()
            return _preflight_record(row)
    finally:
        connection.close()


def accept_verification_decision(
    *,
    db_path: str,
    run_id: str,
    evidence_id: str,
    request: VerificationDecisionRequest,
    actor_fingerprint: str,
) -> VerificationDecisionAcceptance:
    init_evidence_verification_schema(db_path)
    if not actor_fingerprint or len(actor_fingerprint) > 128:
        raise VerificationConflict("verification_persistence_conflict")
    request_hash = verification_request_hash(
        run_id=run_id,
        evidence_id=evidence_id,
        request=request,
    )
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT *
                FROM evidence_verification_decisions_v2
                WHERE verification_id = ?
                """,
                (request.verification_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise VerificationConflict("verification_id_conflict")
                preflight_row = connection.execute(
                    """
                    SELECT *
                    FROM evidence_verification_preflights_v2
                    WHERE preflight_id = ?
                    """,
                    (existing["preflight_id"],),
                ).fetchone()
                if preflight_row is None:
                    raise VerificationConflict(
                        "verification_persistence_conflict"
                    )
                return VerificationDecisionAcceptance(
                    decision=_decision_record(existing),
                    preflight=_preflight_record(preflight_row),
                    idempotent_replay=True,
                )

            run, evidence = _target_rows(
                connection,
                run_id=run_id,
                evidence_id=evidence_id,
            )
            from api.publication_repository import (
                adopt_baseline_publication,
                publication_schema_exists,
            )

            publication_enabled = publication_schema_exists(connection)
            if publication_enabled:
                adopt_baseline_publication(
                    connection,
                    run_id=run_id,
                )
            if (
                evidence["evidence_fingerprint"]
                != request.evidence_fingerprint
            ):
                raise VerificationConflict(
                    "evidence_fingerprint_mismatch"
                )
            preflight = evaluate_evidence_preflight(
                run=dict(run),
                evidence=dict(evidence),
            )
            _persist_preflight(connection, preflight=preflight)
            if request.action == "verify" and preflight.status != "eligible":
                raise VerificationConflict("evidence_preflight_blocked")

            current_revision = connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0)
                FROM evidence_verification_decisions_v2
                WHERE run_id = ?
                  AND evidence_id = ?
                  AND evidence_fingerprint = ?
                """,
                (
                    run_id,
                    evidence_id,
                    request.evidence_fingerprint,
                ),
            ).fetchone()[0]
            if current_revision != request.expected_revision:
                raise VerificationConflict(
                    "verification_revision_conflict"
                )

            revision = current_revision + 1
            now = _now()
            connection.execute(
                """
                INSERT INTO evidence_verification_decisions_v2 (
                    verification_id,
                    run_id,
                    evidence_id,
                    evidence_fingerprint,
                    revision,
                    action,
                    reason_code,
                    reason_note,
                    preflight_id,
                    actor_fingerprint,
                    request_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.verification_id,
                    run_id,
                    evidence_id,
                    request.evidence_fingerprint,
                    revision,
                    request.action,
                    request.reason_code,
                    request.reason_note,
                    preflight.preflight_id,
                    actor_fingerprint,
                    request_hash,
                    now,
                ),
            )
            if publication_enabled:
                from api.publication_repository import (
                    stale_current_publication,
                )

                stale_current_publication(
                    connection,
                    run_id=run_id,
                    now=now,
                )
            row = connection.execute(
                """
                SELECT *
                FROM evidence_verification_decisions_v2
                WHERE verification_id = ?
                """,
                (request.verification_id,),
            ).fetchone()
            return VerificationDecisionAcceptance(
                decision=_decision_record(row),
                preflight=preflight,
                idempotent_replay=False,
            )
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if "verification_id" in message:
            raise VerificationConflict("verification_id_conflict") from exc
        if "revision" in message:
            raise VerificationConflict(
                "verification_revision_conflict"
            ) from exc
        raise VerificationConflict(
            "verification_persistence_conflict"
        ) from exc
    finally:
        connection.close()


def _effective_projection(
    *,
    evidence: sqlite3.Row,
    decision: sqlite3.Row | None,
) -> EffectiveEvidenceVerification:
    if decision is not None:
        verified = decision["action"] == "verify"
        return EffectiveEvidenceVerification(
            run_id=evidence["run_id"],
            evidence_id=evidence["evidence_id"],
            evidence_fingerprint=evidence["evidence_fingerprint"],
            verification_status="verified" if verified else "unverified",
            verification_state="verified" if verified else "rejected",
            verification_origin="human",
            verification_revision=decision["revision"],
            decision_id=decision["verification_id"],
        )
    if evidence["baseline_verification_origin"] == "declared_fixture":
        return EffectiveEvidenceVerification(
            run_id=evidence["run_id"],
            evidence_id=evidence["evidence_id"],
            evidence_fingerprint=evidence["evidence_fingerprint"],
            verification_status="verified",
            verification_state="verified",
            verification_origin="declared_fixture",
            verification_revision=0,
        )
    return EffectiveEvidenceVerification(
        run_id=evidence["run_id"],
        evidence_id=evidence["evidence_id"],
        evidence_fingerprint=evidence["evidence_fingerprint"],
        verification_status="unverified",
        verification_state="unverified",
        verification_origin="none",
        verification_revision=0,
    )


def get_effective_verification(
    *,
    db_path: str,
    run_id: str,
    evidence_id: str,
) -> EffectiveEvidenceVerification | None:
    init_evidence_verification_schema(db_path)
    connection = _connect(db_path)
    try:
        evidence = connection.execute(
            """
            SELECT *
            FROM evidence_entries_v2
            WHERE run_id = ? AND evidence_id = ?
            """,
            (run_id, evidence_id),
        ).fetchone()
        if evidence is None:
            return None
        decision = connection.execute(
            """
            SELECT *
            FROM evidence_verification_decisions_v2
            WHERE run_id = ?
              AND evidence_id = ?
              AND evidence_fingerprint = ?
            ORDER BY revision DESC
            LIMIT 1
            """,
            (
                run_id,
                evidence_id,
                evidence["evidence_fingerprint"],
            ),
        ).fetchone()
        return _effective_projection(
            evidence=evidence,
            decision=decision,
        )
    finally:
        connection.close()


def list_effective_verifications(
    *,
    db_path: str,
    run_id: str,
    after: str | None = None,
    limit: int | None = None,
) -> list[EffectiveEvidenceVerification]:
    init_evidence_verification_schema(db_path)
    connection = _connect(db_path)
    try:
        params: list = [run_id]
        after_sql = ""
        if after is not None:
            after_sql = "AND evidence_id > ?"
            params.append(after)
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT ?"
            params.append(limit)
        evidence_rows = connection.execute(
            f"""
            SELECT *
            FROM evidence_entries_v2
            WHERE run_id = ?
              {after_sql}
            ORDER BY evidence_id
            {limit_sql}
            """,
            params,
        ).fetchall()
        if not evidence_rows:
            return []
        evidence_ids = [row["evidence_id"] for row in evidence_rows]
        placeholders = ", ".join("?" for _ in evidence_ids)
        decision_rows = connection.execute(
            f"""
            WITH ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY evidence_id, evidence_fingerprint
                           ORDER BY revision DESC
                       ) AS decision_rank
                FROM evidence_verification_decisions_v2
                WHERE run_id = ?
                  AND evidence_id IN ({placeholders})
            )
            SELECT * FROM ranked WHERE decision_rank = 1
            """,
            [run_id, *evidence_ids],
        ).fetchall()
        decision_by_evidence = {
            row["evidence_id"]: row
            for row in decision_rows
        }
        result = []
        for evidence in evidence_rows:
            decision = decision_by_evidence.get(evidence["evidence_id"])
            if (
                decision is not None
                and decision["evidence_fingerprint"]
                != evidence["evidence_fingerprint"]
            ):
                decision = None
            result.append(
                _effective_projection(
                    evidence=evidence,
                    decision=decision,
                )
            )
        return result
    finally:
        connection.close()


def get_evidence_verification_detail(
    *,
    db_path: str,
    run_id: str,
    evidence_id: str,
) -> dict | None:
    init_evidence_verification_schema(db_path)
    connection = _connect(db_path)
    try:
        evidence = connection.execute(
            """
            SELECT *
            FROM evidence_entries_v2
            WHERE run_id = ? AND evidence_id = ?
            """,
            (run_id, evidence_id),
        ).fetchone()
        if evidence is None:
            return None
        preflight = connection.execute(
            """
            SELECT *
            FROM evidence_verification_preflights_v2
            WHERE run_id = ?
              AND evidence_id = ?
              AND evidence_fingerprint = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                run_id,
                evidence_id,
                evidence["evidence_fingerprint"],
            ),
        ).fetchone()
        decision_rows = connection.execute(
            """
            SELECT *
            FROM evidence_verification_decisions_v2
            WHERE run_id = ?
              AND evidence_id = ?
              AND evidence_fingerprint = ?
            ORDER BY revision DESC
            LIMIT ?
            """,
            (
                run_id,
                evidence_id,
                evidence["evidence_fingerprint"],
                DECISION_HISTORY_LIMIT + 1,
            ),
        ).fetchall()
        truncated = len(decision_rows) > DECISION_HISTORY_LIMIT
        selected_rows = list(
            reversed(decision_rows[:DECISION_HISTORY_LIMIT])
        )
        decision = decision_rows[0] if decision_rows else None
        projected_decisions = [
            _decision_record(row).model_dump(mode="json")
            for row in selected_rows
        ]
        return {
            "effective": _effective_projection(
                evidence=evidence,
                decision=decision,
            ).model_dump(mode="json"),
            "preflight": (
                _preflight_record(preflight).model_dump(mode="json")
                if preflight is not None
                else None
            ),
            "decisions": projected_decisions,
            "decision_history": {
                "limit": DECISION_HISTORY_LIMIT,
                "returned": len(projected_decisions),
                "truncated": truncated,
                "oldest_returned_revision": (
                    projected_decisions[0]["revision"]
                    if projected_decisions
                    else None
                ),
                "newest_returned_revision": (
                    projected_decisions[-1]["revision"]
                    if projected_decisions
                    else None
                ),
            },
        }
    finally:
        connection.close()


def finalize_verification_snapshot(
    *,
    db_path: str,
    run_id: str,
) -> VerificationSnapshotAcceptance:
    init_evidence_verification_schema(db_path)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            return finalize_verification_snapshot_in_transaction(
                connection,
                run_id=run_id,
            )
    except sqlite3.IntegrityError as exc:
        raise VerificationConflict(
            "verification_persistence_conflict"
        ) from exc
    finally:
        connection.close()


def finalize_verification_snapshot_in_transaction(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> VerificationSnapshotAcceptance:
    run = connection.execute(
        """
        SELECT run_id
        FROM research_runs_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if run is None:
        raise VerificationConflict("evidence_not_found")

    evidence_rows = connection.execute(
        """
        SELECT *
        FROM evidence_entries_v2
        WHERE run_id = ?
        ORDER BY evidence_id
        """,
        (run_id,),
    ).fetchall()
    projections = []
    for evidence in evidence_rows:
        decision = connection.execute(
            """
            SELECT *
            FROM evidence_verification_decisions_v2
            WHERE run_id = ?
              AND evidence_id = ?
              AND evidence_fingerprint = ?
            ORDER BY revision DESC
            LIMIT 1
            """,
            (
                run_id,
                evidence["evidence_id"],
                evidence["evidence_fingerprint"],
            ),
        ).fetchone()
        projections.append(
            _effective_projection(
                evidence=evidence,
                decision=decision,
            )
        )

    snapshot_payload = [
        item.model_dump(mode="json")
        for item in projections
    ]
    snapshot_hash = canonical_hash(snapshot_payload)
    existing = connection.execute(
        """
        SELECT *
        FROM evidence_verification_snapshots_v2
        WHERE run_id = ? AND snapshot_hash = ?
        """,
        (run_id, snapshot_hash),
    ).fetchone()
    if existing is not None:
        return VerificationSnapshotAcceptance(
            snapshot=_snapshot_record(existing),
            idempotent_replay=True,
        )

    revision = connection.execute(
        """
        SELECT COALESCE(MAX(revision), 0) + 1
        FROM evidence_verification_snapshots_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()[0]
    snapshot_id = snapshot_id_for(
        run_id=run_id,
        snapshot_hash=snapshot_hash,
    )
    now = _now()
    connection.execute(
        """
        INSERT INTO evidence_verification_snapshots_v2 (
            snapshot_id,
            run_id,
            revision,
            snapshot_json,
            snapshot_hash,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            run_id,
            revision,
            json.dumps(
                snapshot_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            snapshot_hash,
            now,
        ),
    )
    row = connection.execute(
        """
        SELECT *
        FROM evidence_verification_snapshots_v2
        WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    return VerificationSnapshotAcceptance(
        snapshot=_snapshot_record(row),
        idempotent_replay=False,
    )
