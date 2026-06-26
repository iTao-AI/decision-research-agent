"""Test-only helpers for seeding pre-v0.1.0 legacy SQLite tables."""
from __future__ import annotations

import sqlite3


def init_legacy_db(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            thread_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            output_path TEXT,
            token_usage_json TEXT,
            error_message TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_runs (
            thread_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            output_path TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            assistant_calls INTEGER NOT NULL DEFAULT 0,
            tool_starts INTEGER NOT NULL DEFAULT 0,
            diagnostics_json TEXT NOT NULL DEFAULT '[]',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            quality_report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            query_text TEXT NOT NULL,
            subagent_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            source_url TEXT,
            snippet TEXT NOT NULL,
            citation_status TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_entries_thread_id "
        "ON evidence_entries(thread_id)"
    )
    connection.commit()
    return connection
