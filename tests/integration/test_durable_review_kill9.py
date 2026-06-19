import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

from scripts.durable_hitl_fixture import run_recovery


CRASH_STAGES = [
    "application_finalized",
    "checkpoint_interrupted",
    "decision_committed",
    "lease_acquired",
    "graph_resumed",
]

EXPECTED_OUTCOMES = {
    "application_finalized": {
        "workflow_status": "waiting_decision",
        "decision_count": 0,
        "resolution_count": 0,
        "reviewed_artifact_count": 0,
    },
    "checkpoint_interrupted": {
        "workflow_status": "waiting_decision",
        "decision_count": 0,
        "resolution_count": 0,
        "reviewed_artifact_count": 0,
    },
    "decision_committed": {
        "workflow_status": "approved",
        "decision_count": 1,
        "resolution_count": 1,
        "reviewed_artifact_count": 1,
    },
    "lease_acquired": {
        "workflow_status": "approved",
        "decision_count": 1,
        "resolution_count": 1,
        "reviewed_artifact_count": 1,
    },
    "graph_resumed": {
        "workflow_status": "approved",
        "decision_count": 1,
        "resolution_count": 1,
        "reviewed_artifact_count": 1,
    },
}


def _wait_for_marker(marker: Path, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8"):
            return
        time.sleep(0.05)
    raise AssertionError(f"marker_timeout:{marker.name}")


def _scalar(root: Path, query: str, params=()):
    connection = sqlite3.connect(root / "tasks.db")
    try:
        return connection.execute(query, params).fetchone()[0]
    finally:
        connection.close()


def _assert_converged_exactly_once(root: Path, *, expected: dict) -> None:
    assert _scalar(
        root,
        "SELECT COUNT(*) FROM run_segments WHERE kind = 'post_review'",
    ) == 1
    assert _scalar(root, "SELECT COUNT(*) FROM review_decisions_v2") == (
        expected["decision_count"]
    )
    assert _scalar(root, "SELECT COUNT(*) FROM review_resolutions_v2") == (
        expected["resolution_count"]
    )
    assert _scalar(
        root,
        """
        SELECT COUNT(*) FROM run_artifacts_v2
        WHERE artifact_id = 'decision-brief.reviewed.json'
        """,
    ) == expected["reviewed_artifact_count"]
    assert _scalar(
        root,
        "SELECT status FROM review_workflows_v2 LIMIT 1",
    ) == expected["workflow_status"]


@pytest.mark.parametrize("stage", CRASH_STAGES)
def test_sigkill_window_converges_without_duplicate_state(tmp_path, stage):
    marker = tmp_path / f"{stage}.marker"
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/durable_hitl_crash_worker.py",
            "--stage",
            stage,
            "--marker",
            str(marker),
            "--root",
            str(tmp_path),
        ]
    )
    try:
        _wait_for_marker(marker, timeout=10)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    run_recovery(tmp_path)
    _assert_converged_exactly_once(
        tmp_path,
        expected=EXPECTED_OUTCOMES[stage],
    )
