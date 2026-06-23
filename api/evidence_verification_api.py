from __future__ import annotations

import asyncio
from email.message import Message
import hashlib
import hmac
import os
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from starlette.requests import ClientDisconnect

from api.evidence_verification_models import VerificationDecisionRequest
from api.evidence_verification_repository import (
    VerificationConflict,
    accept_verification_decision,
    get_evidence_verification_detail,
    list_effective_verifications,
)
from api.publication_models import (
    VerificationFinalizationRequest,
    decode_evidence_cursor,
    encode_evidence_cursor,
)
from api.publication_repository import (
    PublicationConflict,
    evidence_verification_enabled,
    finalize_verification_publication,
)
from api.publication_service import PublicationBuildConflict
from api.review_models import BoundedId
from api.run_repository import get_run


router = APIRouter()
_BOUNDED_ID_ADAPTER = TypeAdapter(BoundedId)


class EvidenceListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)


def _error(
    status: int,
    *,
    code: str,
    problem: str,
    cause: str,
    fix: str,
    retryable: bool,
    run_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "problem": problem,
            "cause": cause,
            "fix": fix,
            "retryable": retryable,
            "run_id": run_id,
            "request_id": f"request_{uuid.uuid4().hex}",
        },
    )


def authenticate_evidence_verification_request(
    request: Request,
    *,
    run_id: str | None = None,
):
    if not evidence_verification_enabled():
        return None, _error(
            404,
            code="evidence_verification_disabled",
            problem="Evidence verification is disabled.",
            cause="The canonical feature flag is false.",
            fix="Enable the controlled verification runtime first.",
            retryable=False,
            run_id=run_id,
        )
    secret = os.getenv("API_SECRET", "")
    if not secret:
        return None, _error(
            503,
            code="evidence_verification_auth_not_configured",
            problem="Evidence verification authentication is not configured.",
            cause="API_SECRET is empty after startup.",
            fix="Disable the feature and restart with API_SECRET configured.",
            retryable=False,
            run_id=run_id,
        )
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied, secret):
        return None, _error(
            401,
            code="invalid_api_key",
            problem="The verification credential is invalid.",
            cause="X-API-Key did not match the configured service credential.",
            fix="Provide the configured X-API-Key.",
            retryable=False,
            run_id=run_id,
        )
    fingerprint = hashlib.sha256(
        f"decision-research-agent-evidence-verification:{secret}".encode()
    ).hexdigest()
    return fingerprint, None


def _validate_identity(*values: str):
    try:
        return tuple(
            _BOUNDED_ID_ADAPTER.validate_python(value)
            for value in values
        ), None
    except ValidationError:
        return None, _error(
            422,
            code="invalid_evidence_verification_identity",
            problem="The Evidence verification identity is invalid.",
            cause="A run or Evidence ID failed the bounded contract.",
            fix="Use IDs returned by the run and verification APIs.",
            retryable=False,
        )


def _runtime_error(request: Request, *, run_id: str | None = None):
    readiness = getattr(
        request.app.state,
        "evidence_verification_runtime_readiness",
        None,
    )
    if readiness is None or not readiness.ready:
        return _error(
            503,
            code="verification_runtime_not_ready",
            problem="The Evidence verification runtime is not ready.",
            cause="The application schema or durable review runtime is unavailable.",
            fix="Disable the feature, run doctor, and repair readiness.",
            retryable=True,
            run_id=run_id,
        )
    return None


def _is_json_content_type(value: str | None) -> bool:
    if value is None:
        return True
    if not value:
        return False
    message = Message()
    message["content-type"] = value
    if message.get_content_maintype() != "application":
        return False
    subtype = message.get_content_subtype()
    return subtype == "json" or subtype.endswith("+json")


def _conflict_response(code: str, *, run_id: str) -> JSONResponse:
    if code == "stale_state_version":
        return _error(
            409,
            code=code,
            problem="The run changed before verification finalization.",
            cause="expected_state_version is stale.",
            fix="Fetch the run and retry with its current state version.",
            retryable=True,
            run_id=run_id,
        )
    if code in {
        "evidence_not_found",
        "publication_run_not_found",
        "verification_snapshot_not_found",
    }:
        return _error(
            404,
            code="evidence_not_found",
            problem="The requested Evidence verification target was not found.",
            cause="The run or Evidence identity did not resolve.",
            fix="Fetch the run and use its exact Evidence IDs.",
            retryable=False,
            run_id=run_id,
        )
    if code in {
        "verification_schema_not_ready",
        "verification_runtime_not_ready",
    }:
        return _error(
            503,
            code=code,
            problem="The verification runtime is not ready.",
            cause="Required schema or runtime state is unavailable.",
            fix="Disable the feature and repair runtime readiness.",
            retryable=True,
            run_id=run_id,
        )
    retryable = code == "verification_revision_conflict"
    return _error(
        409,
        code=code,
        problem="The Evidence verification transition was rejected.",
        cause="The authoritative ledger rejected the requested transition.",
        fix="Fetch current Evidence state and retry with exact identities.",
        retryable=retryable,
        run_id=run_id,
    )


@router.get("/api/evidence-verifications/health")
async def evidence_verification_health(request: Request):
    _, error = authenticate_evidence_verification_request(request)
    if error is not None:
        return error
    error = _runtime_error(request)
    if error is not None:
        return error
    task = getattr(request.app.state, "review_worker_task", None)
    worker_running = task is not None and not task.done()
    if not worker_running:
        return _conflict_response(
            "verification_runtime_not_ready",
            run_id="",
        )
    readiness = request.app.state.evidence_verification_runtime_readiness
    return {
        "status": "ok",
        "feature_enabled": True,
        "worker_running": True,
        "application_schema_ready": readiness.application_schema_ready,
        "review_runtime_ready": readiness.review_runtime_ready,
    }


@router.get("/api/runs/{run_id}/evidence/verifications")
async def list_evidence_verifications(run_id: str, request: Request):
    _, error = authenticate_evidence_verification_request(
        request,
        run_id=run_id,
    )
    if error is not None:
        return error
    identity, error = _validate_identity(run_id)
    if error is not None:
        return error
    run_id = identity[0]
    error = _runtime_error(request, run_id=run_id)
    if error is not None:
        return error
    try:
        query = EvidenceListQuery.model_validate(dict(request.query_params))
        after = (
            decode_evidence_cursor(query.cursor)
            if query.cursor is not None
            else None
        )
    except (ValidationError, ValueError):
        return _error(
            422,
            code="invalid_evidence_verification_query",
            problem="The Evidence verification query is invalid.",
            cause="limit or cursor failed the bounded contract.",
            fix="Use limit 1-100 and a cursor returned by this endpoint.",
            retryable=False,
            run_id=run_id,
        )
    run = await asyncio.to_thread(get_run, run_id=run_id)
    if run is None:
        return _conflict_response("evidence_not_found", run_id=run_id)
    items = await asyncio.to_thread(
        list_effective_verifications,
        db_path=os.getenv("TASKS_DB_PATH", ""),
        run_id=run_id,
        after=after,
        limit=query.limit + 1,
    )
    page = items[: query.limit]
    next_cursor = (
        encode_evidence_cursor(evidence_id=page[-1].evidence_id)
        if len(items) > query.limit
        else None
    )
    return {
        "items": [
            {
                "run_id": item.run_id,
                "evidence_id": item.evidence_id,
                "evidence_fingerprint": item.evidence_fingerprint,
                "verification_status": item.verification_status,
                "verification_state": item.verification_state,
                "verification_origin": item.verification_origin,
                "verification_revision": item.verification_revision,
            }
            for item in page
        ],
        "next_cursor": next_cursor,
    }


@router.get(
    "/api/runs/{run_id}/evidence/{evidence_id}/verification"
)
async def show_evidence_verification(
    run_id: str,
    evidence_id: str,
    request: Request,
):
    _, error = authenticate_evidence_verification_request(
        request,
        run_id=run_id,
    )
    if error is not None:
        return error
    identity, error = _validate_identity(run_id, evidence_id)
    if error is not None:
        return error
    run_id, evidence_id = identity
    error = _runtime_error(request, run_id=run_id)
    if error is not None:
        return error
    detail = await asyncio.to_thread(
        get_evidence_verification_detail,
        db_path=os.getenv("TASKS_DB_PATH", ""),
        run_id=run_id,
        evidence_id=evidence_id,
    )
    if detail is None:
        return _conflict_response("evidence_not_found", run_id=run_id)
    return detail


@router.post(
    "/api/runs/{run_id}/evidence/{evidence_id}/verification-decisions"
)
async def submit_evidence_verification_decision(
    run_id: str,
    evidence_id: str,
    request: Request,
):
    actor, error = authenticate_evidence_verification_request(
        request,
        run_id=run_id,
    )
    if error is not None:
        return error
    identity, error = _validate_identity(run_id, evidence_id)
    if error is not None:
        return error
    run_id, evidence_id = identity
    error = _runtime_error(request, run_id=run_id)
    if error is not None:
        return error
    try:
        if not _is_json_content_type(request.headers.get("content-type")):
            raise ValueError
        body = await request.json()
        validated = VerificationDecisionRequest.model_validate(body)
    except (ClientDisconnect, RuntimeError, ValueError):
        return _error(
            422,
            code="invalid_evidence_verification_decision",
            problem="The verification decision request is invalid.",
            cause="The body failed the bounded verification contract.",
            fix="Provide exact identity, revision, action, and confirmation fields.",
            retryable=False,
            run_id=run_id,
        )
    try:
        accepted = await asyncio.to_thread(
            accept_verification_decision,
            db_path=os.getenv("TASKS_DB_PATH", ""),
            run_id=run_id,
            evidence_id=evidence_id,
            request=validated,
            actor_fingerprint=actor,
        )
    except VerificationConflict as exc:
        return _conflict_response(exc.code, run_id=run_id)
    return {
        "run_id": run_id,
        "evidence_id": evidence_id,
        "verification_id": accepted.decision.verification_id,
        "revision": accepted.decision.revision,
        "action": accepted.decision.action,
        "idempotent_replay": accepted.idempotent_replay,
    }


@router.post(
    "/api/runs/{run_id}/evidence/verification-snapshots"
)
async def finalize_evidence_verification(
    run_id: str,
    request: Request,
):
    _, error = authenticate_evidence_verification_request(
        request,
        run_id=run_id,
    )
    if error is not None:
        return error
    identity, error = _validate_identity(run_id)
    if error is not None:
        return error
    run_id = identity[0]
    error = _runtime_error(request, run_id=run_id)
    if error is not None:
        return error
    try:
        if not _is_json_content_type(request.headers.get("content-type")):
            raise ValueError
        body = await request.json()
        validated = VerificationFinalizationRequest.model_validate(body)
    except (ClientDisconnect, RuntimeError, ValueError):
        return _error(
            422,
            code="invalid_verification_finalization",
            problem="The verification finalization request is invalid.",
            cause="The body failed the state-version contract.",
            fix="Provide the current non-negative expected_state_version.",
            retryable=False,
            run_id=run_id,
        )
    try:
        result = await asyncio.to_thread(
            finalize_verification_publication,
            db_path=os.getenv("TASKS_DB_PATH", ""),
            run_id=run_id,
            expected_state_version=validated.expected_state_version,
        )
    except (
        PublicationBuildConflict,
        PublicationConflict,
        VerificationConflict,
    ) as exc:
        return _conflict_response(exc.code, run_id=run_id)
    return {
        "run_id": run_id,
        "snapshot_id": result.snapshot.snapshot_id,
        "publication_id": result.publication.publication_id,
        "revision": result.publication.revision,
        "review_id": result.publication.review_id,
        "workflow_id": (
            result.workflow["workflow_id"]
            if result.workflow is not None
            else None
        ),
        "idempotent_replay": result.idempotent_replay,
    }
