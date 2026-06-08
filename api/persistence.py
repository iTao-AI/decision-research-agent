"""SQLite persistence for task state.

Provides functions to save, update, and query task metadata using
Python's built-in sqlite3 with WAL mode for concurrent access.
"""
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Any, Optional, Dict


DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"
TERMINAL_STATUSES = {"completed", "completed_with_fallback", "failed"}


def _get_db_path(db_path: str = None) -> str:
    path = db_path or os.environ.get("TASKS_DB_PATH", str(DEFAULT_DB_PATH))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: str = None) -> sqlite3.Connection:
    """Initialize the tasks database and return a connection.

    Creates the tasks table if it doesn't exist. Idempotent.
    """
    path = _get_db_path(db_path)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
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
    """)
    conn.execute("""
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
    """)
    conn.execute("""
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
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_entries_thread_id "
        "ON evidence_entries(thread_id)"
    )
    conn.commit()
    return conn


def save_task(
    db_path: str = None,
    thread_id: str = "",
    query: str = "",
    status: str = "pending",
) -> None:
    """Insert or reset a task record for a thread."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO tasks (thread_id, query, status, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(thread_id) DO UPDATE SET
             query = excluded.query,
             status = excluded.status,
             started_at = NULL,
             completed_at = NULL,
             output_path = NULL,
             token_usage_json = NULL,
             error_message = NULL""",
        (thread_id, query, status, now),
    )
    conn.commit()
    conn.close()


def update_task(
    db_path: str = None,
    thread_id: str = "",
    status: str = None,
    output_path: str = None,
    token_usage_json: str = None,
    error_message: str = None,
) -> None:
    """Update a task record. Only provided fields are updated.

    When status is 'running', sets started_at automatically.
    When status is a terminal status, sets completed_at automatically.
    """
    path = _get_db_path(db_path)
    conn = init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    sets = []
    params = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
        if status == "running":
            sets.append("started_at = ?")
            params.append(now)
        elif status in TERMINAL_STATUSES:
            sets.append("completed_at = ?")
            params.append(now)
    if output_path is not None:
        sets.append("output_path = ?")
        params.append(output_path)
    if token_usage_json is not None:
        sets.append("token_usage_json = ?")
        params.append(token_usage_json)
    if error_message is not None:
        sets.append("error_message = ?")
        params.append(error_message)
    if not sets:
        return
    params.append(thread_id)
    conn.execute(
        f"UPDATE tasks SET {', '.join(sets)} WHERE thread_id = ?",
        params,
    )
    conn.commit()
    conn.close()


def get_task(db_path: str = None, thread_id: str = "") -> Optional[Dict]:
    """Retrieve a task by thread_id. Returns None if not found."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM tasks WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def save_research_run(
    db_path: str = None,
    thread_id: str = "",
    query: str = "",
    status: str = "",
    started_at: str | None = None,
    completed_at: str | None = None,
    output_path: str | None = None,
    fallback_used: bool = False,
    assistant_calls: int = 0,
    tool_starts: int = 0,
    diagnostics_json: str = "[]",
    token_usage_json: str = "{}",
    quality_report_json: str = "{}",
) -> None:
    """Insert or replace one auditable research run record."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO research_runs (
             thread_id, query, status, started_at, completed_at, output_path,
             fallback_used, assistant_calls, tool_starts, diagnostics_json,
             token_usage_json, quality_report_json, created_at
           )
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(thread_id) DO UPDATE SET
             query = excluded.query,
             status = excluded.status,
             started_at = excluded.started_at,
             completed_at = excluded.completed_at,
             output_path = excluded.output_path,
             fallback_used = excluded.fallback_used,
             assistant_calls = excluded.assistant_calls,
             tool_starts = excluded.tool_starts,
             diagnostics_json = excluded.diagnostics_json,
             token_usage_json = excluded.token_usage_json,
             quality_report_json = excluded.quality_report_json""",
        (
            thread_id,
            query,
            status,
            started_at,
            completed_at,
            output_path,
            1 if fallback_used else 0,
            assistant_calls,
            tool_starts,
            diagnostics_json,
            token_usage_json,
            quality_report_json,
            now,
        ),
    )
    conn.commit()
    conn.close()


def replace_evidence_entries(
    db_path: str = None, thread_id: str = "", entries: list[Any] | None = None
) -> None:
    """Replace the evidence ledger for one thread."""
    entries = entries or []
    path = _get_db_path(db_path)
    conn = init_db(path)
    try:
        with conn:
            conn.execute("DELETE FROM evidence_entries WHERE thread_id = ?", (thread_id,))
            conn.executemany(
                """INSERT INTO evidence_entries (
                     thread_id, query_text, subagent_name, tool_name, source_url, snippet,
                     citation_status, verification_status, created_at
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item.thread_id,
                        item.query_text,
                        item.subagent_name,
                        item.tool_name,
                        item.source_url,
                        item.snippet,
                        item.citation_status,
                        item.verification_status,
                        item.created_at,
                    )
                    for item in entries
                ],
            )
    finally:
        conn.close()


def _research_run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["fallback_used"] = bool(data["fallback_used"])
    data["diagnostics"] = _json_loads(data.pop("diagnostics_json", None), [])
    data["token_usage"] = _json_loads(data.pop("token_usage_json", None), {})
    data["quality_report"] = _json_loads(data.pop("quality_report_json", None), {})
    return data


def list_research_runs(db_path: str = None, limit: int = 50) -> list[dict[str, Any]]:
    """List recent research runs without evidence entries."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM research_runs ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    ).fetchall()
    conn.close()
    return [_research_run_row_to_dict(row) for row in rows]


def get_research_run_with_evidence(
    db_path: str = None, thread_id: str = ""
) -> Optional[dict[str, Any]]:
    """Retrieve one research run and its evidence ledger."""
    path = _get_db_path(db_path)
    conn = init_db(path)
    conn.row_factory = sqlite3.Row
    run_row = conn.execute(
        "SELECT * FROM research_runs WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if run_row is None:
        conn.close()
        return None

    evidence_rows = conn.execute(
        """SELECT thread_id, query_text, subagent_name, tool_name, source_url,
                  snippet, citation_status, verification_status, created_at
           FROM evidence_entries
           WHERE thread_id = ?
           ORDER BY id ASC""",
        (thread_id,),
    ).fetchall()
    conn.close()

    run = _research_run_row_to_dict(run_row)
    run["evidence"] = [dict(row) for row in evidence_rows]
    return run
