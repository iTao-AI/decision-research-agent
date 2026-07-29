from __future__ import annotations

import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

import pytest

from api.database import application_db_path, prepare_application_db_parent
from api.run_execution_models import RunExecutionConflict
from api.run_execution_writer_lock import acquire_run_execution_writer


_CHILD = """
import sys
from api.run_execution_writer_lock import acquire_run_execution_writer
from api.run_execution_models import RunExecutionConflict
try:
    writer = acquire_run_execution_writer(db_path=sys.argv[1])
except RunExecutionConflict as exc:
    print(exc.code, flush=True)
    raise SystemExit(23)
print("acquired", flush=True)
sys.stdin.buffer.read(1)
writer.release()
"""


def _holder(db: Path) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(db)],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "acquired"
    return child


def test_pure_database_path_resolution_does_not_create_missing_parent(tmp_path):
    db = tmp_path / "missing" / "nested" / "runs.db"
    assert application_db_path(db) == db.resolve()
    assert not db.parent.exists()


def test_writer_bootstrap_creates_missing_nested_parent_without_database(tmp_path):
    db = tmp_path / "missing" / "nested" / "runs.db"
    assert prepare_application_db_parent(db) == db.resolve()
    assert db.parent.is_dir() and not db.exists()


def test_first_writer_acquires_canonical_db_scoped_lock(tmp_path):
    db = tmp_path / "runs.db"
    capability = acquire_run_execution_writer(db_path=db)
    try:
        assert capability.held
        assert not db.exists()
    finally:
        capability.release()


def test_two_processes_bootstrap_missing_parent_and_only_one_acquires(tmp_path):
    db = tmp_path / "missing" / "nested" / "runs.db"
    first = _holder(db)
    try:
        second = subprocess.run(
            [sys.executable, "-c", _CHILD, str(db)],
            cwd=Path(__file__).resolve().parents[2],
            input="",
            capture_output=True,
            text=True,
            check=False,
        )
        assert second.returncode == 23
        assert second.stdout.strip() == "run_execution_writer_already_active"
        assert not db.exists()
    finally:
        assert first.stdin is not None
        first.stdin.write("x")
        first.stdin.flush()
        assert first.wait(timeout=3) == 0


def test_second_process_writer_fails_nonblocking_with_bounded_code(tmp_path):
    db = tmp_path / "runs.db"
    first = _holder(db)
    try:
        with pytest.raises(RunExecutionConflict, match="run_execution_writer_already_active"):
            acquire_run_execution_writer(db_path=db)
    finally:
        assert first.stdin is not None
        first.stdin.write("x")
        first.stdin.flush()
        assert first.wait(timeout=3) == 0


def test_contention_does_not_open_or_mutate_the_application_database(tmp_path):
    db = tmp_path / "runs.db"
    first = acquire_run_execution_writer(db_path=db)
    try:
        with pytest.raises(RunExecutionConflict):
            acquire_run_execution_writer(db_path=db)
        assert not db.exists()
    finally:
        first.release()


def test_lock_descriptor_is_noninheritable_nofollow_and_private(tmp_path):
    capability = acquire_run_execution_writer(db_path=tmp_path / "runs.db")
    try:
        assert not os.get_inheritable(capability.descriptor)
        mode = stat.S_IMODE(os.fstat(capability.descriptor).st_mode)
        assert mode == 0o600
    finally:
        capability.release()


def test_lock_file_contains_no_path_pid_boot_or_owner_identity(tmp_path):
    capability = acquire_run_execution_writer(db_path=tmp_path / "runs.db")
    try:
        assert Path(capability.lock_path).read_bytes() == b""
    finally:
        capability.release()


def test_unsupported_advisory_lock_platform_fails_closed(tmp_path, monkeypatch):
    import api.run_execution_writer_lock as module

    monkeypatch.setattr(module, "fcntl", None)
    with pytest.raises(RunExecutionConflict, match="run_execution_writer_unavailable"):
        acquire_run_execution_writer(db_path=tmp_path / "missing" / "runs.db")


def test_unsupported_platform_does_not_create_database_or_runtime_directories(tmp_path, monkeypatch):
    import api.run_execution_writer_lock as module

    db = tmp_path / "missing" / "runs.db"
    monkeypatch.setattr(module, "fcntl", None)
    with pytest.raises(RunExecutionConflict):
        acquire_run_execution_writer(db_path=db)
    assert not db.parent.exists()


def test_real_sigkill_releases_writer_lock_for_a_fresh_process(tmp_path):
    db = tmp_path / "runs.db"
    first = _holder(db)
    os.kill(first.pid, signal.SIGKILL)
    assert first.wait(timeout=3) == -signal.SIGKILL
    second = acquire_run_execution_writer(db_path=db)
    second.release()
