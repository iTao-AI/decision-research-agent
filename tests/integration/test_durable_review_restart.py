import subprocess
import sys

from api.review_repository import get_review_projection
from api.run_repository import get_run
from scripts.durable_hitl_fixture import (
    seed_checkpoint_pending,
    seed_resume_pending,
    seed_resuming_with_corrupt_checkpoint,
)


def _run_worker_subprocess(root):
    subprocess.run(
        [
            sys.executable,
            "scripts/durable_hitl_fixture.py",
            "recover",
            "--root",
            str(root),
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def test_restart_recovers_checkpoint_pending(tmp_path):
    fixture = seed_checkpoint_pending(tmp_path)

    _run_worker_subprocess(tmp_path)

    projection = get_review_projection(
        db_path=fixture.db_path,
        run_id=fixture.run_id,
    )
    assert projection["workflow"]["status"] == "waiting_decision"


def test_restart_recovers_decision_committed_before_resume(tmp_path):
    fixture = seed_resume_pending(tmp_path, action="approve")

    _run_worker_subprocess(tmp_path)

    run = get_run(db_path=fixture.db_path, run_id=fixture.run_id)
    assert run["delivery_status"] == "ready"
    assert run["review_resolution"]["action"] == "approve"


def test_corrupt_checkpoint_after_resume_attempt_is_manual_recovery(tmp_path):
    fixture = seed_resuming_with_corrupt_checkpoint(tmp_path)

    _run_worker_subprocess(tmp_path)

    projection = get_review_projection(
        db_path=fixture.db_path,
        run_id=fixture.run_id,
    )
    assert projection["workflow"]["status"] == "manual_recovery"
    assert projection["workflow"]["last_error_code"] == "checkpoint_corrupt"
