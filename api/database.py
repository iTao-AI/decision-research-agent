"""Canonical application database path resolution."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APPLICATION_DB_PATH = PROJECT_ROOT / "data" / "decision_research_agent.db"
APPLICATION_DB_ENV = "DECISION_RESEARCH_AGENT_DB_PATH"


def application_db_path(db_path: str | Path | None = None) -> Path:
    """Return the persistent application database path.

    Runtime resolution reads only the canonical environment variable. Explicit
    ``db_path`` arguments remain available for tests and migration tooling.
    """
    raw = str(db_path) if db_path is not None else os.getenv(APPLICATION_DB_ENV)
    path = Path(raw).expanduser() if raw else DEFAULT_APPLICATION_DB_PATH
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def sqlite_db_path(db_path: str | Path | None = None) -> str:
    """Return a value suitable for ``sqlite3.connect``.

    ``:memory:`` is accepted only when explicitly supplied by tests or tooling,
    never through runtime environment resolution.
    """
    if db_path is not None and str(db_path) == ":memory:":
        return ":memory:"
    return str(application_db_path(db_path))


def backup_database(*, db_path: str, backup_path: str) -> None:
    """Create a transactionally consistent SQLite backup."""
    Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(sqlite_db_path(db_path))
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def restore_database(*, backup_path: str, db_path: str) -> None:
    """Restore a SQLite backup without copying WAL sidecar files."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(backup_path)
    destination = sqlite3.connect(sqlite_db_path(db_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
