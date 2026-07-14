"""Single-node worker that reconciles durable pre-execution run dispatch."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Callable
import uuid

from pydantic import ValidationError

from api.run_dispatch_models import RunDispatchClaim, RunDispatchConflict
from api.run_dispatch_repository import (
    claim_run_dispatch,
    release_run_dispatch_for_retry,
)


def bounded_dispatch_error_code(exc: Exception) -> str:
    """Map failures to stable codes without retaining exception text."""
    if isinstance(exc, (sqlite3.Error, OSError)):
        return "run_dispatch_unavailable"
    if isinstance(exc, (ValidationError, ValueError, RunDispatchConflict)):
        return "run_dispatch_invalid"
    return "run_dispatch_schedule_failed"


async def _claim_in_thread(**kwargs) -> RunDispatchClaim | None:
    return await asyncio.to_thread(claim_run_dispatch, **kwargs)


class RunDispatchWorker:
    def __init__(
        self,
        *,
        db_path: str | None,
        scheduler: Callable[[RunDispatchClaim], None],
        worker_id: str | None = None,
        lease_seconds: int = 30,
        poll_seconds: float = 1.0,
    ) -> None:
        self.db_path = db_path
        self.scheduler = scheduler
        self.worker_id = worker_id or f"dispatch_worker_{uuid.uuid4().hex}"
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()

    def wake(self) -> None:
        self._wake.set()

    async def dispatch_run(self, run_id: str) -> bool:
        try:
            return await self.run_once(run_id=run_id)
        except Exception as exc:
            logging.error(
                "Run dispatch targeted attempt failed: %s",
                bounded_dispatch_error_code(exc),
            )
            return False

    async def run_once(self, *, run_id: str | None = None) -> bool:
        self._wake.clear()
        claim = await _claim_in_thread(
            db_path=self.db_path,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            run_id=run_id,
        )
        if claim is None:
            return False
        try:
            self.scheduler(claim)
        except Exception:
            error_code = "run_dispatch_schedule_failed"
            logging.error("Run dispatch scheduling failed: %s", error_code)
            outcome = await asyncio.to_thread(
                release_run_dispatch_for_retry,
                db_path=self.db_path,
                claim=claim,
                error_code=error_code,
            )
            if outcome == "retry":
                self.wake()
        return True

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                did_work = await self.run_once()
            except Exception as exc:
                logging.error(
                    "Run dispatch worker loop failed: %s",
                    bounded_dispatch_error_code(exc),
                )
                did_work = False
            if did_work:
                continue
            if self._wake.is_set():
                continue
            stop_task = asyncio.create_task(self._stop.wait())
            wake_task = asyncio.create_task(self._wake.wait())
            try:
                done, pending = await asyncio.wait(
                    {stop_task, wake_task},
                    timeout=self.poll_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
            finally:
                for task in (stop_task, wake_task):
                    if not task.done():
                        task.cancel()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
