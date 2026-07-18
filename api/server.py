import sys
import os
import asyncio
import logging
import sqlite3
from functools import partial
import uvicorn
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, ValidationError, field_validator
from contextlib import asynccontextmanager
import uuid
from typing import Annotated, Literal

# Load env once at startup — tools read from os.environ
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from agent.main_agent import run_deep_agent
from agent.run_result import OutcomeBox
from agent.telemetry import collector
from api.monitor import monitor, manager
from api.cors_config import load_cors_configuration
from api.runtime_access import (
    AccessDecision,
    build_http_access_context,
    build_websocket_access_context,
    credentials_match,
    decide_runtime_access,
    load_runtime_access_policy,
)
from api.task_tracker import (
    FinalizationCheckpoint,
    TerminationOrigin,
    create_tracked_task,
    settle_shielded_task,
)
from api.database import sqlite_db_path
from api.thread_ids import validate_thread_id
from api.run_repository import (
    RunCreationConflict,
    create_or_replay_run,
    create_run,
    finalize_run_transaction,
    get_artifact,
    get_run,
)
from api.run_failure_cause_models import (
    RunFailureCauseConflict,
    RunFailureCauseWrite,
    RunStatusFailureCauseOpenAPI,
)
from api.run_dispatch_models import RunDispatchClaim
from api.run_dispatch_repository import (
    reconcile_run_dispatch_cancellation,
    reconcile_run_dispatch_timeout,
    release_run_dispatch_for_retry,
    start_run_dispatch,
)
from api.run_dispatch_worker import RunDispatchWorker
from api.run_creation_models import validate_idempotency_key
from api.run_result_service import (
    RunResultUnavailable,
    build_generic_result_artifact,
    resolve_run_result,
)
from agent.profile_registry import profile_registry
from agent.talent_contracts import ResearchScope
from api.talent_artifacts import build_talent_artifacts
from api.review_api import router as review_router
from api.evidence_verification_api import (
    router as evidence_verification_router,
)
from api.review_models import (
    checkpoint_thread_id,
    durable_hitl_enabled,
    post_review_segment_id,
    review_workflow_id,
)
from api.review_config import (
    ReviewConfigurationError,
    check_evidence_verification_readiness,
    check_review_readiness,
    validate_evidence_verification_runtime,
    validate_review_runtime,
)
from api.review_worker import ReviewWorker
from api.run_migrations import migrate_with_backup


def _is_review_api_path(path: str) -> bool:
    return (
        path == "/api/reviews"
        or path.startswith("/api/reviews/")
        or path == "/api/evidence-verifications/health"
        or (
            path.startswith("/api/runs/")
            and "/evidence/" in path
        )
        or (
        path.startswith("/api/runs/")
        and "/reviews/" in path
        )
    )


_RUNTIME_ACCESS_ERRORS = {
    "api_key_invalid": (
        401,
        "The service credential is invalid.",
        "X-API-Key did not match the configured service credential.",
        "Provide the configured X-API-Key.",
    ),
    "api_auth_not_configured": (
        503,
        "The service is not configured for remote unauthenticated access.",
        "The direct client is not an explicit loopback peer.",
        "Use the loopback source runtime or configure X-API-Key.",
    ),
    "local_authority_required": (
        503,
        "An explicit loopback authority is required.",
        "The request authority is not an explicit loopback literal.",
        "Use 127.0.0.1 or [::1], or configure X-API-Key.",
    ),
    "forwarded_request_rejected": (
        503,
        "Forwarded unauthenticated requests are not supported.",
        "Forwarding identity metadata is present in loopback-only mode.",
        "Connect directly over loopback or configure X-API-Key.",
    ),
    "origin_not_allowed": (
        403,
        "The browser Origin is not allowed.",
        "Origin did not match the configured browser Origin.",
        "Use the configured browser Origin.",
    ),
}


def _runtime_access_error(decision: AccessDecision) -> JSONResponse:
    status, problem, cause, fix = _RUNTIME_ACCESS_ERRORS[decision.code]
    return JSONResponse(
        status_code=status,
        content={
            "code": decision.code,
            "problem": problem,
            "cause": cause,
            "fix": fix,
            "retryable": False,
        },
    )


class RuntimeAccessMiddleware(BaseHTTPMiddleware):
    """Enforce the frozen general HTTP runtime access policy."""

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if _is_review_api_path(path):
            return await call_next(request)

        # Skip auth for docs and health endpoints
        if path in ("/docs", "/openapi.json", "/redoc", "/health"):
            return await call_next(request)

        context = build_http_access_context(request)
        decision = decide_runtime_access(
            request.app.state.runtime_access_policy,
            context,
            allowed_origin=request.app.state.cors_configuration.allowed_origin,
        )
        return await call_next(request) if decision.allowed else _runtime_access_error(decision)


def _emit_runtime_access_warning_once(application: FastAPI) -> None:
    if (
        application.state.runtime_access_policy.secret_value is None
        and not application.state.runtime_access_warning_emitted
    ):
        logging.warning("runtime access mode: loopback_only")
        application.state.runtime_access_warning_emitted = True


def create_review_worker(
    *,
    application_db_path: Path,
    checkpoint_db_path: Path,
) -> ReviewWorker:
    return ReviewWorker(
        db_path=str(application_db_path),
        checkpoint_path=str(checkpoint_db_path),
    )


def create_run_dispatch_worker(application_db_path: str | Path) -> RunDispatchWorker:
    return RunDispatchWorker(
        db_path=str(application_db_path),
        scheduler=partial(
            _schedule_run_dispatch,
            db_path=str(application_db_path),
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    worker = None
    run_dispatch_task = None
    run_dispatch_worker = None
    app.state.review_worker_task = None
    app.state.run_dispatch_worker = None
    app.state.run_dispatch_worker_task = None
    app.state.review_runtime_readiness = None
    app.state.evidence_verification_runtime_readiness = None
    _emit_runtime_access_warning_once(app)
    try:
        application_db_path = sqlite_db_path()
        runtime = validate_review_runtime(output_dir=output_dir)
        verification_runtime = validate_evidence_verification_runtime(
            review_runtime=runtime,
            output_dir=output_dir,
        )
        try:
            migrate_with_backup(
                db_path=application_db_path,
                backup_path=f"{application_db_path}.pre-run-dispatch.bak",
            )
        except sqlite3.DatabaseError as exc:
            if runtime.enabled:
                raise ReviewConfigurationError(
                    "review_runtime_not_ready"
                ) from exc
            raise
        run_dispatch_worker = create_run_dispatch_worker(application_db_path)
        run_dispatch_task = asyncio.create_task(run_dispatch_worker.run_forever())
        await asyncio.sleep(0)
        if run_dispatch_task.done():
            run_dispatch_task.result()
        app.state.run_dispatch_worker = run_dispatch_worker
        app.state.run_dispatch_worker_task = run_dispatch_task

        if runtime.enabled:
            readiness = check_review_readiness(
                runtime=runtime,
                gate_report_path=(
                    project_root
                    / "docs"
                    / "evidence"
                    / "durable-hitl-gate-report.json"
                ),
            )
            if not readiness.ready:
                raise ReviewConfigurationError("review_runtime_not_ready")
            app.state.review_runtime_readiness = readiness
            verification_readiness = (
                check_evidence_verification_readiness(
                    runtime=verification_runtime,
                    review_readiness=readiness,
                )
            )
            if (
                verification_runtime.enabled
                and not verification_readiness.ready
            ):
                raise ReviewConfigurationError(
                    "verification_runtime_not_ready"
                )
            app.state.evidence_verification_runtime_readiness = (
                verification_readiness
                if verification_runtime.enabled
                else None
            )
            worker = create_review_worker(
                application_db_path=runtime.application_db_path,
                checkpoint_db_path=runtime.checkpoint_db_path,
            )
            task = asyncio.create_task(worker.run_forever())
            await asyncio.sleep(0)
            if task.done():
                task.result()
            app.state.review_worker_task = task
        yield
    finally:
        app.state.review_worker_task = None
        app.state.run_dispatch_worker = None
        app.state.run_dispatch_worker_task = None
        app.state.review_runtime_readiness = None
        app.state.evidence_verification_runtime_readiness = None
        if worker is not None:
            worker.stop()
        if task is not None:
            if task.done():
                if not task.cancelled():
                    task.exception()
            else:
                await task
        if run_dispatch_worker is not None:
            run_dispatch_worker.stop()
        if run_dispatch_task is not None:
            if run_dispatch_task.done():
                if not run_dispatch_task.cancelled():
                    run_dispatch_task.exception()
            else:
                await run_dispatch_task


app = FastAPI(
    title="Decision Research Agent API",
    description="Source-backed research runs that produce decision-ready briefs.",
    lifespan=lifespan,
)

runtime_access_policy = load_runtime_access_policy()
cors_configuration = load_cors_configuration(
    access_policy=runtime_access_policy,
)
app.state.runtime_access_policy = runtime_access_policy
app.state.cors_configuration = cors_configuration
app.state.runtime_access_warning_emitted = False

output_dir = project_root / "output"
output_dir.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_configuration.allowed_origins,
    allow_credentials=False,
    allow_methods=list(cors_configuration.allow_methods),
    allow_headers=list(cors_configuration.allow_headers),
)

app.add_middleware(RuntimeAccessMiddleware)
app.include_router(review_router)
app.include_router(evidence_verification_router)


@app.get("/health")
async def health():
    """Lightweight service health endpoint for agent-tool integrations."""
    return {"status": "ok", "service": "decision-research-agent"}


class RunRequest(BaseModel):
    query: str
    thread_id: str | None = None
    profile_id: str = "generic"
    scope: dict = Field(default_factory=dict)

    @field_validator("thread_id")
    @classmethod
    def validate_optional_thread_id(cls, value):
        return validate_thread_id(value) if value is not None else value


def _validated_thread_id(thread_id: str) -> str:
    try:
        return validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_DIRECT_EXECUTION_FAILURES = frozenset(
    {
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
    }
)


def _execution_failure_cause(failure_kind: str | None) -> RunFailureCauseWrite:
    code = (
        failure_kind
        if failure_kind in _DIRECT_EXECUTION_FAILURES
        else "execution_error"
    )
    return RunFailureCauseWrite(phase="execution", code=code)


_RunStageValue = Literal["dispatch", "execution", "finalization"]


class _RunStage:
    """Monotonic application stage shared by one exact dispatch attempt."""

    def __init__(self) -> None:
        self._value: _RunStageValue = "dispatch"

    @property
    def value(self) -> _RunStageValue:
        return self._value

    def advance_to_execution(self) -> None:
        if self._value == "dispatch":
            self._value = "execution"
        elif self._value != "execution":
            raise RuntimeError("run_stage_cannot_move_backward")

    def advance_to_finalization(self) -> None:
        if self._value == "execution":
            self._value = "finalization"
        elif self._value != "finalization":
            raise RuntimeError("run_stage_transition_invalid")


def _stage_failure_cause(stage: _RunStage) -> RunFailureCauseWrite:
    if stage.value == "finalization":
        return RunFailureCauseWrite(
            phase="finalization",
            code="run_finalization_failed",
        )
    return RunFailureCauseWrite(
        phase="execution",
        code="execution_error",
    )


def _termination_failure_cause(
    stage: _RunStage,
    termination_origin: TerminationOrigin,
) -> RunFailureCauseWrite:
    if termination_origin.value == "timeout":
        code = "run_timeout"
    elif termination_origin.value == "cancelled":
        code = "cancelled"
    else:
        return _stage_failure_cause(stage)
    phase = "finalization" if stage.value == "finalization" else "execution"
    return RunFailureCauseWrite(phase=phase, code=code)


async def _run_started_v2_with_persistence(
    *,
    query: str,
    thread_id: str,
    run_id: str,
    segment_id: str,
    outcome_box: OutcomeBox,
    db_path: str,
    stage: _RunStage,
    termination_origin: TerminationOrigin,
    finalization_checkpoint: FinalizationCheckpoint,
    profile_id: str = "generic",
    scope: dict | None = None,
) -> None:
    """Execute one run-scoped request while preserving LangGraph thread identity."""
    state_version = 1
    allowed_previous_statuses = {"running"}
    result = None
    try:
        result = await run_deep_agent(
            query,
            thread_id,
            run_id=run_id,
            segment_id=segment_id,
            outcome_box=outcome_box,
            profile_id=profile_id,
            scope=scope,
        )
        stage.advance_to_finalization()
        execution_status = (
            "failed" if result.failure_kind is not None else "completed"
        )
        failure_cause = (
            _execution_failure_cause(result.failure_kind)
            if execution_status == "failed"
            else None
        )
        delivery_status = "failed" if execution_status == "failed" else "ready"
        review_status = "not_required"
        review_bundle = None
        review_workflow = None
        artifacts = []
        if execution_status == "completed" and profile_id == "generic":
            artifacts = [build_generic_result_artifact(result)]
        if execution_status == "completed" and profile_id == "talent-hiring-signal":
            review_bundle, _, artifacts = build_talent_artifacts(
                run_id=run_id,
                scope=scope or {},
                packets=result.research_packets,
                evidence_entries=result.evidence_entries,
                generated_at=result.started_at or datetime.now(timezone.utc),
            )
            review_status = review_bundle.status
            if review_bundle.required_before_delivery:
                delivery_status = "review_required"
                if durable_hitl_enabled():
                    workflow_id = review_workflow_id(
                        run_id,
                        review_bundle.review_id,
                        review_bundle.revision,
                    )
                    review_workflow = {
                        "workflow_id": workflow_id,
                        "checkpoint_thread_id": checkpoint_thread_id(
                            workflow_id
                        ),
                        "post_review_segment_id": post_review_segment_id(
                            run_id,
                            review_bundle.review_id,
                            review_bundle.revision,
                        ),
                    }
        await finalization_checkpoint.request_and_wait()
    except asyncio.CancelledError:
        outcome = result or outcome_box.latest()
        await _finalize_failed_run_v2(
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=state_version,
            allowed_previous_statuses=allowed_previous_statuses,
            evidence_entries=outcome.evidence_entries if outcome is not None else [],
            failure_cause=_termination_failure_cause(stage, termination_origin),
            db_path=db_path,
        )
        raise
    except Exception:
        outcome = result or outcome_box.latest()
        await _finalize_failed_run_v2(
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=state_version,
            allowed_previous_statuses=allowed_previous_statuses,
            evidence_entries=outcome.evidence_entries if outcome is not None else [],
            failure_cause=_stage_failure_cause(stage),
            db_path=db_path,
        )
        raise

    terminal_failure_cause = failure_cause
    terminal_execution_status = execution_status
    terminal_delivery_status = delivery_status
    terminal_review_status = review_status
    terminal_evidence_entries = result.evidence_entries
    terminal_research_packets = result.research_packets
    terminal_review_bundle = review_bundle
    terminal_artifacts = artifacts
    terminal_review_workflow = review_workflow
    if termination_origin.value != "unset":
        terminal_failure_cause = _termination_failure_cause(
            stage,
            termination_origin,
        )
        terminal_execution_status = "failed"
        terminal_delivery_status = "failed"
        terminal_review_status = "not_required"
        terminal_research_packets = []
        terminal_review_bundle = None
        terminal_artifacts = []
        terminal_review_workflow = None

    terminal_task = asyncio.create_task(
        asyncio.to_thread(
            finalize_run_transaction,
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=state_version,
            allowed_previous_statuses=allowed_previous_statuses,
            execution_status=terminal_execution_status,
            delivery_status=terminal_delivery_status,
            review_status=terminal_review_status,
            evidence_entries=terminal_evidence_entries,
            research_packets=terminal_research_packets,
            review_bundle=terminal_review_bundle,
            artifacts=terminal_artifacts,
            review_workflow=terminal_review_workflow,
            failure_cause=terminal_failure_cause,
            db_path=db_path,
        )
    )
    terminal_result, terminal_exception, cancellation_requests = (
        await settle_shielded_task(terminal_task)
    )
    if terminal_exception is not None:
        fallback_cause = (
            _termination_failure_cause(stage, termination_origin)
            if termination_origin.value != "unset"
            else RunFailureCauseWrite(
                phase="finalization",
                code="run_finalization_failed",
            )
        )
        await _finalize_failed_run_v2(
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=state_version,
            allowed_previous_statuses=allowed_previous_statuses,
            evidence_entries=result.evidence_entries,
            failure_cause=fallback_cause,
            db_path=db_path,
        )
        current_task = asyncio.current_task()
        if cancellation_requests or (
            current_task is not None and current_task.cancelling()
        ):
            raise asyncio.CancelledError
        raise terminal_exception
    if cancellation_requests:
        raise asyncio.CancelledError
    if terminal_result is False:
        return


async def _run_dispatched_with_persistence(
    claim: RunDispatchClaim,
    *,
    db_path: str,
    outcome_box: OutcomeBox,
    stage: _RunStage,
    termination_origin: TerminationOrigin,
    finalization_checkpoint: FinalizationCheckpoint,
) -> None:
    """Cross the application-owned start fence before invoking the Agent."""
    start_task = asyncio.create_task(
        asyncio.to_thread(
            start_run_dispatch,
            db_path=db_path,
            claim=claim,
        )
    )
    started, start_exception, cancellation_requests = await settle_shielded_task(
        start_task
    )
    if start_exception is not None:
        if cancellation_requests or termination_origin.value != "unset":
            raise asyncio.CancelledError
        recovery_task = asyncio.create_task(
            asyncio.to_thread(
                release_run_dispatch_for_retry,
                db_path=db_path,
                claim=claim,
                error_code="run_dispatch_start_failed",
            )
        )
        _, recovery_exception, recovery_cancellations = await settle_shielded_task(
            recovery_task
        )
        if recovery_exception is not None:
            logging.error("Run dispatch start recovery failed")
        if recovery_cancellations:
            raise asyncio.CancelledError
        return
    if not started:
        if cancellation_requests:
            raise asyncio.CancelledError
        return
    stage.advance_to_execution()
    if cancellation_requests or termination_origin.value != "unset":
        outcome = outcome_box.latest()
        await _finalize_failed_run_v2(
            run_id=claim.run_id,
            segment_id=claim.segment_id,
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            evidence_entries=outcome.evidence_entries if outcome is not None else [],
            failure_cause=_termination_failure_cause(stage, termination_origin),
            db_path=db_path,
        )
        raise asyncio.CancelledError
    await _run_started_v2_with_persistence(
        query=claim.query,
        thread_id=claim.thread_id,
        run_id=claim.run_id,
        segment_id=claim.segment_id,
        outcome_box=outcome_box,
        db_path=db_path,
        stage=stage,
        termination_origin=termination_origin,
        finalization_checkpoint=finalization_checkpoint,
        profile_id=claim.profile_id,
        scope=claim.scope,
    )


async def _finalize_failed_run_v2(
    *,
    run_id: str,
    segment_id: str,
    expected_state_version: int,
    allowed_previous_statuses: set[str],
    evidence_entries: list,
    failure_cause: RunFailureCauseWrite,
    db_path: str | None = None,
) -> bool:
    """Best-effort failure finalization that never masks the original error."""
    terminal_task = asyncio.create_task(
        asyncio.to_thread(
            finalize_run_transaction,
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=expected_state_version,
            allowed_previous_statuses=allowed_previous_statuses,
            execution_status="failed",
            delivery_status="failed",
            evidence_entries=evidence_entries,
            failure_cause=failure_cause,
            db_path=db_path,
        )
    )
    result, terminal_exception, cancellation_requests = await settle_shielded_task(
        terminal_task
    )
    if terminal_exception is not None:
        logging.error("Failed to finalize ResearchRun %s", run_id)
    if cancellation_requests:
        raise asyncio.CancelledError
    if terminal_exception is not None:
        return False
    return result is True


async def _mark_run_timeout(
    run_id: str,
    timeout_seconds: int,
    *,
    segment_id: str,
    outcome_box: OutcomeBox,
    db_path: str | None = None,
    stage: _RunStage | None = None,
) -> None:
    """Fail-close a nonterminal ResearchRun after task tracker timeout."""
    run_task = asyncio.create_task(
        asyncio.to_thread(get_run, run_id=run_id, db_path=db_path)
    )
    run, run_exception, _ = await settle_shielded_task(run_task)
    if run_exception is not None:
        logging.error("Timed out ResearchRun %s could not be read", run_id)
        return
    if run is None:
        logging.error("Timed out ResearchRun %s no longer exists", run_id)
        return

    outcome = outcome_box.latest()
    previous_status = run["execution_status"]
    finalized_by_callback = False
    if previous_status in {"pending", "running"}:
        finalized_by_callback = await _finalize_failed_run_v2(
            run_id=run_id,
            segment_id=segment_id,
            expected_state_version=run["state_version"],
            allowed_previous_statuses={previous_status},
            evidence_entries=outcome.evidence_entries if outcome is not None else [],
            failure_cause=RunFailureCauseWrite(
                phase=(
                    "finalization"
                    if stage is not None and stage.value == "finalization"
                    else "execution"
                ),
                code="run_timeout",
            ),
            db_path=db_path,
        )

    monitor._emit(
        "run_timeout",
        f"ResearchRun timed out after {timeout_seconds}s",
        {
            "timeout_seconds": timeout_seconds,
            "previous_status": previous_status,
            "finalized_by_callback": finalized_by_callback,
        },
        thread_id=run["thread_id"],
        run_id=run_id,
        segment_id=segment_id,
    )


async def _mark_dispatched_timeout(
    claim: RunDispatchClaim,
    *,
    db_path: str,
    outcome_box: OutcomeBox,
    timeout_seconds: int,
    stage: _RunStage | None = None,
    termination_origin: TerminationOrigin | None = None,
) -> None:
    """Fence timeout handling to the exact dispatch attempt."""
    if (
        termination_origin is not None
        and termination_origin.value != "timeout"
    ):
        return
    reconcile_task = asyncio.create_task(
        asyncio.to_thread(
            reconcile_run_dispatch_timeout,
            db_path=db_path,
            claim=claim,
        )
    )
    timeout_outcome, reconcile_exception, _ = await settle_shielded_task(
        reconcile_task
    )
    if reconcile_exception is not None:
        logging.error("Run dispatch timeout inspection failed")
        return
    if timeout_outcome != "started":
        return
    await _mark_run_timeout(
        claim.run_id,
        timeout_seconds,
        segment_id=claim.segment_id,
        outcome_box=outcome_box,
        db_path=db_path,
        stage=stage,
    )


async def _mark_dispatched_cancellation(
    claim: RunDispatchClaim,
    *,
    db_path: str,
    outcome_box: OutcomeBox,
    stage: _RunStage,
    termination_origin: TerminationOrigin,
) -> None:
    """Fence cancellation handling to the exact dispatch attempt."""
    if termination_origin.value != "cancelled":
        return
    reconcile_task = asyncio.create_task(
        asyncio.to_thread(
            reconcile_run_dispatch_cancellation,
            db_path=db_path,
            claim=claim,
        )
    )
    cancellation_outcome, reconcile_exception, _ = await settle_shielded_task(
        reconcile_task
    )
    if reconcile_exception is not None:
        logging.error("Run dispatch cancellation inspection failed")
        return
    if cancellation_outcome != "started":
        return

    run_task = asyncio.create_task(
        asyncio.to_thread(get_run, run_id=claim.run_id, db_path=db_path)
    )
    run, run_exception, _ = await settle_shielded_task(run_task)
    if run_exception is not None or run is None:
        logging.error("Cancelled ResearchRun %s could not be read", claim.run_id)
        return
    previous_status = run["execution_status"]
    if previous_status not in {"pending", "running"}:
        return
    outcome = outcome_box.latest()
    await _finalize_failed_run_v2(
        run_id=claim.run_id,
        segment_id=claim.segment_id,
        expected_state_version=run["state_version"],
        allowed_previous_statuses={previous_status},
        evidence_entries=outcome.evidence_entries if outcome is not None else [],
        failure_cause=RunFailureCauseWrite(
            phase=(
                "finalization" if stage.value == "finalization" else "execution"
            ),
            code="cancelled",
        ),
        db_path=db_path,
    )


def _schedule_run_dispatch(claim: RunDispatchClaim, *, db_path: str) -> None:
    outcome_box = OutcomeBox()
    stage = _RunStage()
    termination_origin = TerminationOrigin()
    finalization_checkpoint = FinalizationCheckpoint()
    coroutine = _run_dispatched_with_persistence(
        claim,
        db_path=db_path,
        outcome_box=outcome_box,
        stage=stage,
        termination_origin=termination_origin,
        finalization_checkpoint=finalization_checkpoint,
    )
    task_id = f"{claim.run_id}:dispatch:{claim.attempt_count}"
    try:
        create_tracked_task(
            coroutine,
            task_id,
            on_timeout=lambda _task_id, timeout_seconds: _mark_dispatched_timeout(
                claim,
                db_path=db_path,
                outcome_box=outcome_box,
                timeout_seconds=timeout_seconds,
                stage=stage,
                termination_origin=termination_origin,
            ),
            on_cancel=lambda _task_id: _mark_dispatched_cancellation(
                claim,
                db_path=db_path,
                outcome_box=outcome_box,
                stage=stage,
                termination_origin=termination_origin,
            ),
            termination_origin=termination_origin,
            finalization_checkpoint=finalization_checkpoint,
        )
    except Exception:
        coroutine.close()
        raise


def _run_creation_error(
    status_code: int,
    *,
    code: str,
    problem: str,
    cause: str,
    fix: str,
    retryable: bool,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "problem": problem,
            "cause": cause,
            "fix": fix,
            "retryable": retryable,
            "run_id": None,
            "request_id": f"request_{uuid.uuid4().hex}",
        },
    )


def _run_creation_conflict_response(code: str) -> JSONResponse:
    if code == "run_idempotency_conflict":
        return _run_creation_error(
            409,
            code=code,
            problem="The run idempotency key is already bound to another request.",
            cause="The canonical request does not match the first accepted request.",
            fix="Retry the original request or use a new high-entropy key.",
            retryable=False,
        )
    return _run_creation_error(
        503,
        code="run_idempotency_unavailable",
        problem="Run idempotency persistence is unavailable.",
        cause="The durable run-creation ledger could not be used safely.",
        fix="Retry the same request and key after the service is ready.",
        retryable=True,
    )


@app.post("/api/runs")
async def create_research_run(
    request: RunRequest,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    """Create one run-scoped research execution."""
    try:
        profile = profile_registry.get(request.profile_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unknown_profile",
                "problem": str(exc),
                "fix": "Use a profile returned by the server profile manifest.",
            },
        ) from exc
    validated_scope = request.scope
    if request.profile_id == "talent-hiring-signal":
        try:
            validated_scope = ResearchScope.model_validate(request.scope).model_dump(
                mode="json"
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_research_scope",
                    "problem": "Talent Hiring Signal scope failed validation.",
                    "cause": exc.errors(include_url=False),
                    "fix": "Provide a bounded ResearchScope with declared public samples.",
                },
            ) from exc
    if idempotency_key is None:
        thread_id = request.thread_id or str(uuid.uuid4())
        created = await asyncio.to_thread(
            create_run,
            thread_id=thread_id,
            query=request.query,
            profile_id=request.profile_id,
            profile_version=profile.version,
            scope=validated_scope,
        )
        replay = False
    else:
        try:
            validated_key = validate_idempotency_key(idempotency_key)
        except ValueError:
            return _run_creation_error(
                422,
                code="run_idempotency_key_invalid",
                problem="The run idempotency key is invalid.",
                cause="Idempotency-Key failed the bounded public contract.",
                fix="Use 8-128 high-entropy ASCII characters from the documented set.",
                retryable=False,
            )
        try:
            acceptance = await asyncio.to_thread(
                create_or_replay_run,
                idempotency_key=validated_key,
                thread_id=request.thread_id,
                query=request.query,
                profile_id=request.profile_id,
                profile_version=profile.version,
                scope=validated_scope,
            )
        except RunCreationConflict as exc:
            return _run_creation_conflict_response(exc.code)
        created = acceptance.model_dump(mode="json")
        thread_id = acceptance.thread_id
        replay = acceptance.idempotent_replay

    response = {"status": "started", **created}
    if idempotency_key is not None:
        response["idempotent_replay"] = replay
    worker = app.state.run_dispatch_worker
    await worker.dispatch_run(created["run_id"])
    worker.wake()
    return response


@app.get(
    "/api/runs/{run_id}",
    responses={
        200: {
            "model": RunStatusFailureCauseOpenAPI,
            "description": "ResearchRun status with additive failure cause",
        }
    },
)
async def get_research_run_v2(run_id: str):
    try:
        run = await asyncio.to_thread(get_run, run_id=run_id)
    except RunFailureCauseConflict:
        return JSONResponse(
            status_code=500,
            content={"detail": "ResearchRun state is unavailable"},
        )
    if run is None:
        return JSONResponse(status_code=404, content={"detail": "ResearchRun 不存在"})
    return run


@app.get("/api/runs/{run_id}/result")
async def get_research_run_result(run_id: str):
    try:
        result = await asyncio.to_thread(resolve_run_result, run_id=run_id)
    except RunResultUnavailable as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.payload(run_id=run_id),
        )
    return {
        "run_id": result.run_id,
        "execution_status": result.execution_status,
        "delivery_status": result.delivery_status,
        "artifact": result.artifact,
    }


@app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
async def get_run_artifact(run_id: str, artifact_id: str):
    artifact = await asyncio.to_thread(
        get_artifact, run_id=run_id, artifact_id=artifact_id
    )
    if artifact is None:
        return JSONResponse(status_code=404, content={"detail": "Artifact 不存在"})
    return Response(content=artifact["content"], media_type=artifact["media_type"])


@app.get("/api/profiles/{profile_id}")
async def get_profile_manifest(profile_id: str):
    try:
        return profile_registry.manifest(profile_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_profile",
                "problem": str(exc),
                "fix": "Use a configured server profile.",
            },
        ) from exc


def _serialize_telemetry(records):
    return [
        {
            "thread_id": r.thread_id,
            "run_id": r.run_id,
            "segment_id": r.segment_id,
            "agent_name": r.agent_name,
            "tool_name": r.tool_name,
            "duration_ms": r.duration_ms,
            "status": r.status,
            "error": r.error,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in records
    ]


@app.get("/api/telemetry/runs/{run_id}")
async def get_run_telemetry(run_id: str):
    """Get telemetry records for one ResearchRun."""
    run_id = _validated_thread_id(run_id)
    return _serialize_telemetry(collector.get_by_run(run_id))


@app.get("/api/token-usage/runs/{run_id}")
async def get_run_token_usage(run_id: str):
    """Get token usage summary for one ResearchRun."""
    run_id = _validated_thread_id(run_id)
    from agent.token_tracking import token_collector
    return token_collector.get_summary(run_id)


@app.websocket("/ws/runs/{run_id}")
async def run_websocket_endpoint(websocket: WebSocket, run_id: str):
    """Run-scoped WebSocket endpoint that permits same-thread concurrent runs."""
    context = build_websocket_access_context(websocket)
    decision = decide_runtime_access(
        websocket.app.state.runtime_access_policy,
        context,
        allowed_origin=websocket.app.state.cors_configuration.allowed_origin,
    )
    if not decision.allowed:
        await websocket.close(
            code=4001 if decision.code == "api_key_invalid" else 1008,
            reason=decision.code,
        )
        return

    try:
        run_id = validate_thread_id(run_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid run_id")
        return

    run = await asyncio.to_thread(get_run, run_id=run_id)
    if run is None:
        await websocket.close(code=1008, reason="ResearchRun not found")
        return

    await manager.connect_run(websocket, run_id=run_id, thread_id=run["thread_id"])
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json(
                {"type": "pong", "run_id": run_id, "message": f"服务端已收到: {data}"}
            )
    except WebSocketDisconnect:
        manager.disconnect_run(websocket, run_id)
    except Exception:
        manager.disconnect_run(websocket, run_id)


def run_source_server() -> None:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="warning",
    )


if __name__ == "__main__":
    run_source_server()
