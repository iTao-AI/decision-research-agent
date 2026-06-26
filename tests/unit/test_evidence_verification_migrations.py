import json
import sqlite3

import pytest

from agent.research import EvidenceEntry
from api.evidence_verification_repository import (
    VERIFICATION_MIGRATION_VERSION,
    init_evidence_verification_schema,
)
from tests.legacy_db import init_legacy_db
from api.run_migrations import (
    backup_database,
    restore_database,
    verify_run_schema,
)
from api.run_repository import create_run, finalize_run_transaction


VERIFICATION_TABLES = {
    "evidence_verification_preflights_v2",
    "evidence_verification_decisions_v2",
    "evidence_verification_snapshots_v2",
}


def _tables(path: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()


def test_verification_schema_is_idempotent_and_optionally_verified(tmp_path):
    path = str(tmp_path / "tasks.db")
    init_legacy_db(path).close()

    init_evidence_verification_schema(path)
    init_evidence_verification_schema(path)
    result = verify_run_schema(
        db_path=path,
        include_evidence_verification=True,
    )

    assert VERIFICATION_TABLES <= _tables(path)
    assert VERIFICATION_MIGRATION_VERSION in result["migration_versions"]
    connection = sqlite3.connect(path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (VERIFICATION_MIGRATION_VERSION,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_verification_schema_backup_restore_removes_additive_state(tmp_path):
    path = str(tmp_path / "tasks.db")
    backup = str(tmp_path / "tasks.pre-verification.db")
    init_legacy_db(path).close()
    before = _tables(path)

    backup_database(db_path=path, backup_path=backup)
    init_evidence_verification_schema(path)
    assert VERIFICATION_TABLES <= _tables(path)

    restore_database(backup_path=backup, db_path=path)
    assert _tables(path) == before


def test_legacy_fixture_backfill_requires_aggregate_only_talent_scope_and_verified_status(
    tmp_path,
):
    path = str(tmp_path / "tasks.db")
    talent = create_run(
        db_path=path,
        thread_id="thread-talent",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [
                {
                    "sample_id": "aggregate-v1",
                    "source_type": "provided_aggregate",
                    "reference": "aggregate-v1",
                }
            ],
            "allowed_source_types": ["provided_aggregate"],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    ordinary = create_run(
        db_path=path,
        thread_id="thread-generic",
        query="query",
        profile_id="generic",
    )
    talent_entry = EvidenceEntry(
        thread_id="thread-talent",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/talent",
        snippet="talent",
        verification_status="verified",
    )
    ordinary_entry = EvidenceEntry(
        thread_id="thread-generic",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/generic",
        snippet="generic",
        verification_status="verified",
    )
    for created, entry in (
        (talent, talent_entry),
        (ordinary, ordinary_entry),
    ):
        assert finalize_run_transaction(
            db_path=path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=0,
            allowed_previous_statuses={"pending"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[entry],
        )

    init_evidence_verification_schema(path)

    connection = sqlite3.connect(path)
    try:
        rows = dict(
            connection.execute(
                """
                SELECT run_id, baseline_verification_origin
                FROM evidence_entries_v2
                """
            ).fetchall()
        )
    finally:
        connection.close()
    assert rows[talent["run_id"]] == "declared_fixture"
    assert rows[ordinary["run_id"]] == "none"


def test_mixed_source_talent_run_is_not_backfilled(tmp_path):
    path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=path,
        thread_id="thread-mixed",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [
                {
                    "sample_id": "aggregate-v1",
                    "source_type": "provided_aggregate",
                    "reference": "aggregate-v1",
                },
                {
                    "sample_id": "job-1",
                    "source_type": "public_job_posting",
                    "reference": "https://jobs.example.com/role",
                },
            ],
            "allowed_source_types": [
                "provided_aggregate",
                "public_job_posting",
            ],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    entry = EvidenceEntry(
        thread_id="thread-mixed",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://jobs.example.com/role",
        snippet="mixed source evidence",
        verification_status="verified",
    )
    assert finalize_run_transaction(
        db_path=path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[entry],
    )

    init_evidence_verification_schema(path)

    connection = sqlite3.connect(path)
    try:
        origin = connection.execute(
            """
            SELECT baseline_verification_origin
            FROM evidence_entries_v2
            WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    assert origin == "none"


def test_legacy_unverified_talent_evidence_is_not_backfilled(tmp_path):
    path = str(tmp_path / "tasks.db")
    created = create_run(
        db_path=path,
        thread_id="thread-talent",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [
                {
                    "sample_id": "aggregate-v1",
                    "source_type": "provided_aggregate",
                    "reference": "aggregate-v1",
                }
            ],
            "allowed_source_types": ["provided_aggregate"],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    entry = EvidenceEntry(
        thread_id="thread-talent",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/source",
        snippet="source",
    )
    assert finalize_run_transaction(
        db_path=path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[entry],
    )

    init_evidence_verification_schema(path)

    connection = sqlite3.connect(path)
    try:
        origin = connection.execute(
            """
            SELECT baseline_verification_origin
            FROM evidence_entries_v2
            WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    assert origin == "none"


def test_completed_migration_does_not_backfill_new_verified_evidence(tmp_path):
    path = str(tmp_path / "tasks.db")
    init_evidence_verification_schema(path)
    created = create_run(
        db_path=path,
        thread_id="thread-post-migration",
        query="query",
        profile_id="talent-hiring-signal",
        scope={
            "target_roles": ["AI Agent Engineer"],
            "target_companies": [],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [
                {
                    "sample_id": "aggregate-v1",
                    "source_type": "provided_aggregate",
                    "reference": "aggregate-v1",
                }
            ],
            "allowed_source_types": ["provided_aggregate"],
            "research_questions": ["question-1"],
            "requested_outputs": ["decision_brief"],
        },
    )
    entry = EvidenceEntry(
        thread_id="thread-post-migration",
        query_text="query",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url="https://example.com/post-migration",
        snippet="post-migration evidence",
        verification_status="verified",
    )
    assert finalize_run_transaction(
        db_path=path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[entry],
    )

    init_evidence_verification_schema(path)

    connection = sqlite3.connect(path)
    try:
        origin = connection.execute(
            """
            SELECT baseline_verification_origin
            FROM evidence_entries_v2
            WHERE run_id = ?
            """,
            (created["run_id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    assert origin == "none"


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("evidence_entries_v2", "baseline_verification_origin"),
        ("evidence_verification_preflights_v2", "checks_json"),
        ("evidence_verification_decisions_v2", "actor_fingerprint"),
        ("evidence_verification_snapshots_v2", "snapshot_json"),
    ],
)
def test_verification_schema_checks_required_columns(
    tmp_path,
    table,
    column,
):
    path = str(tmp_path / f"{table}.db")
    init_evidence_verification_schema(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        RuntimeError,
        match=rf"run_schema_verification_failed:.*{table}.*{column}",
    ):
        verify_run_schema(
            db_path=path,
            include_evidence_verification=True,
        )
