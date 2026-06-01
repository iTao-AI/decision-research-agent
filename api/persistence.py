"""SQLite persistence for task state.

Provides functions to save, update, and query task metadata using
Python's built-in sqlite3 with WAL mode for concurrent access.
"""
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict


DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"


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
             created_at = excluded.created_at,
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
    When status is 'completed' or 'failed', sets completed_at automatically.
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
        elif status in ("completed", "failed"):
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
