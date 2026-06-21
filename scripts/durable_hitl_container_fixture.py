from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import uuid


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api.review_gate import ReviewGate
from api.review_models import checkpoint_thread_id
from api.review_repository import get_decision
from api.run_repository import get_run
from scripts.durable_hitl_fixture import create_required_review_fixture


def seed() -> dict:
    fixture_suffix = uuid.uuid4().hex[:12]
    fixture = create_required_review_fixture(
        db_path=os.environ["TASKS_DB_PATH"],
        checkpoint_path=os.environ[
            "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH"
        ],
        fixture_suffix=fixture_suffix,
    )

    async def ensure_waiting():
        for _ in range(20):
            run = fixture.get_run()
            if run["review_workflow"]["status"] == "waiting_decision":
                return
            await fixture.worker.run_once()
            await asyncio.sleep(0.05)
        raise RuntimeError("container_checkpoint_creation_timeout")

    asyncio.run(ensure_waiting())
    return {
        "run_id": fixture.run_id,
        "review_id": fixture.review_id,
    }


def recover(*, run_id: str, timeout_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = get_run(run_id=run_id)
        if run and run["delivery_status"] == "ready":
            checkpoint = ReviewGate(
                os.environ["DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH"],
                lambda decision_id: get_decision(decision_id=decision_id),
            ).inspect(
                checkpoint_thread_id(run["review_workflow"]["workflow_id"])
            )
            artifact_ids = {item["artifact_id"] for item in run["artifacts"]}
            return {
                "application_db_preserved": True,
                "checkpoint_db_preserved": checkpoint.status == "completed",
                "decision_preserved": run["review_decision"] is not None,
                "reviewed_artifact_preserved": (
                    "decision-brief.reviewed.json" in artifact_ids
                ),
            }
        time.sleep(0.25)
    raise RuntimeError("container_review_recovery_timeout")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    recover_parser = subparsers.add_parser("recover")
    recover_parser.add_argument("--run-id", required=True)
    recover_parser.add_argument("--timeout-seconds", type=float, default=20)
    args = parser.parse_args()

    if args.command == "seed":
        result = seed()
    else:
        result = recover(
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
