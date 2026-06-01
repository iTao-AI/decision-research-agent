"""Test SQLite persistence module."""
import pytest
import sqlite3
from pathlib import Path


@pytest.fixture
def db_path(tmp_path):
    """Create a temp SQLite database."""
    db = tmp_path / "test_tasks.db"
    yield str(db)
    if db.exists():
        db.unlink()


class TestPersistence:
    """Test api/persistence.py operations."""

    def test_init_db_creates_table(self, db_path):
        """init_db creates the tasks table if it doesn't exist."""
        from api.persistence import init_db
        conn = init_db(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_db_idempotent(self, db_path):
        """Calling init_db twice doesn't error."""
        from api.persistence import init_db
        conn1 = init_db(db_path)
        conn1.close()
        conn2 = init_db(db_path)
        conn2.close()

    def test_save_and_get_task(self, db_path):
        """Save a task and retrieve it by thread_id."""
        from api.persistence import init_db, save_task, get_task
        init_db(db_path)
        save_task(db_path, thread_id="test-001", query="测试查询")
        task = get_task(db_path, "test-001")
        assert task is not None
        assert task["thread_id"] == "test-001"
        assert task["query"] == "测试查询"
        assert task["status"] == "pending"

    def test_save_task_same_thread_resets_existing_record(self, db_path):
        """Starting another task in the same frontend thread resets status."""
        from api.persistence import init_db, save_task, update_task, get_task
        init_db(db_path)
        save_task(db_path, thread_id="test-001", query="first")
        update_task(
            db_path,
            "test-001",
            status="failed",
            output_path="/output/old.md",
            token_usage_json='{"total": 1000}',
            error_message="old error",
        )

        save_task(db_path, thread_id="test-001", query="second")

        task = get_task(db_path, "test-001")
        assert task["query"] == "second"
        assert task["status"] == "pending"
        assert task["completed_at"] is None
        assert task["output_path"] is None
        assert task["token_usage_json"] is None
        assert task["error_message"] is None

    def test_update_task_status(self, db_path):
        """Update task status from pending to completed."""
        from api.persistence import init_db, save_task, update_task
        init_db(db_path)
        save_task(db_path, thread_id="test-002", query="test")
        update_task(
            db_path,
            "test-002",
            status="completed",
            output_path="/output/report.md",
            token_usage_json='{"total": 1000}',
        )
        from api.persistence import get_task as gt
        task = gt(db_path, "test-002")
        assert task["status"] == "completed"
        assert task["output_path"] == "/output/report.md"

    def test_get_nonexistent_task(self, db_path):
        """Querying a nonexistent thread returns None."""
        from api.persistence import init_db, get_task
        init_db(db_path)
        assert get_task(db_path, "nonexistent") is None
