#!/usr/bin/env python3
"""Private child process used by the provider-free execution recovery proof."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.run_dispatch_repository import claim_run_dispatch, start_run_dispatch
from api.run_execution_models import RunExecutionConflict, new_boot_id
from api.run_execution_repository import (
    activate_run_execution_boot,
    advance_run_execution_phase,
)
from api.run_execution_writer_lock import acquire_run_execution_writer
from api.run_repository import create_run, init_run_schema


def _publish_marker(path: Path, token: str) -> None:
    temporary = path.with_name(path.name + ".ready")
    temporary.write_text(token, encoding="ascii")
    os.replace(temporary, path)


def _pause() -> None:
    if hasattr(signal, "pause"):
        while True:
            signal.pause()
    signal.sigwait({signal.SIGTERM})


def _verify_started(db_path: str, *, phase: str) -> None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT run.execution_status, run.state_version, segment.status,
                   owner.status, owner.phase, boot.boot_scope
            FROM research_runs_v2 AS run
            JOIN run_segments AS segment ON segment.run_id=run.run_id
            JOIN run_execution_owners_v1 AS owner ON owner.run_id=run.run_id
            JOIN run_execution_boot_v1 AS boot ON boot.boot_id=owner.boot_id
            WHERE owner.status='active'
            """
        ).fetchone()
    if row != ("running", 1, "running", "active", phase, "application"):
        raise RuntimeError("worker_readback_failed")


def _run(args: argparse.Namespace) -> None:
    writer = acquire_run_execution_writer(db_path=args.db)
    if not writer.held or os.get_inheritable(writer.descriptor):
        raise RuntimeError("writer_readback_failed")
    if args.mode == "writer":
        _publish_marker(Path(args.marker), "writer")
        _pause()

    init_run_schema(args.db)
    boot_id = new_boot_id()
    activate_run_execution_boot(db_path=args.db, boot_id=boot_id)
    created = create_run(
        db_path=args.db,
        thread_id="proof-thread",
        query="provider-free crash proof",
    )
    claim = claim_run_dispatch(
        db_path=args.db,
        worker_id="dispatch_worker_" + "d" * 32,
        boot_id=boot_id,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    if claim is None:
        raise RuntimeError("worker_claim_failed")
    handle = start_run_dispatch(db_path=args.db, claim=claim)
    if handle is None:
        raise RuntimeError("worker_start_failed")
    if args.mode == "finalization" and not advance_run_execution_phase(
        db_path=args.db,
        handle=handle,
    ):
        raise RuntimeError("worker_phase_failed")
    _verify_started(args.db, phase=args.mode)
    _publish_marker(Path(args.marker), args.mode)
    _pause()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("writer", "execution", "finalization"),
    )
    return parser


def main() -> int:
    try:
        _run(_parser().parse_args())
        return 0
    except RunExecutionConflict as exc:
        if exc.code == "run_execution_writer_already_active":
            print(exc.code, file=sys.stderr)
            return 3
        raise


if __name__ == "__main__":
    raise SystemExit(main())
