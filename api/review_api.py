from __future__ import annotations

import asyncio
from email.message import Message
import hashlib
import hmac
import os
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from starlette.requests import ClientDisconnect

from api.review_models import (
    BoundedId,
    ReviewDecisionRequest,
    ReviewListQuery,
    decode_review_cursor,
    durable_hitl_enabled,
)
from api.review_repository import (
    ReviewConflict,
    accept_review_decision,
    get_review_detail,
    list_review_workflows,
)


router = APIRouter()
_BOUNDED_ID_ADAPTER = TypeAdapter(BoundedId)


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


def authenticate_review_request(
    request: Request,
    *,
    run_id: str | None = None,
):
    if not durable_hitl_enabled():
        return None, _error(
            404,
            code="durable_hitl_disabled",
            problem="Durable review is disabled.",
            cause="The feature flag is false.",
            fix="Enable the controlled single-node review configuration first.",
            retryable=False,
            run_id=run_id,
        )
    secret = os.getenv("API_SECRET", "")
    if not secret:
        return None, _error(
            503,
            code="review_auth_not_configured",
            problem="Durable review authentication is not configured.",
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
            problem="The review credential is invalid.",
            cause="X-API-Key did not match the configured service credential.",
            fix="Provide the configured X-API-Key.",
            retryable=False,
            run_id=run_id,
        )
    fingerprint = hashlib.sha256(
        f"decision-research-agent-review:{secret}".encode()
    ).hexdigest()
    return fingerprint, None


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


def _validate_review_identity(
    *,
    run_id: str,
    review_id: str,
):
    try:
        return (
            _BOUNDED_ID_ADAPTER.validate_python(run_id),
            _BOUNDED_ID_ADAPTER.validate_python(review_id),
        ), None
    except ValidationError:
        return None, _error(
            422,
            code="invalid_review_identity",
            problem="The review identity is invalid.",
            cause="The run or review ID failed the bounded identity contract.",
            fix="Use bounded run and review IDs from the review API.",
            retryable=False,
        )


@router.get("/api/reviews")
async def list_reviews(request: Request):
    _, error = authenticate_review_request(request)
    if error is not None:
        return error
    try:
        query = ReviewListQuery.model_validate(dict(request.query_params))
        cursor = (
            decode_review_cursor(query.cursor)
            if query.cursor is not None
            else None
        )
    except (ValidationError, ValueError):
        return _error(
            422,
            code="invalid_review_query",
            problem="The review query is invalid.",
            cause="Status, limit, or cursor failed the bounded contract.",
            fix="Use a documented workflow status, limit 1-100, and returned cursor.",
            retryable=False,
        )
    return await asyncio.to_thread(
        list_review_workflows,
        status=query.status,
        limit=query.limit,
        cursor=cursor,
    )


@router.get("/api/reviews/health")
async def review_health(request: Request):
    _, error = authenticate_review_request(request)
    if error is not None:
        return error
    readiness = getattr(request.app.state, "review_runtime_readiness", None)
    task = getattr(request.app.state, "review_worker_task", None)
    worker_running = task is not None and not task.done()
    if readiness is None or not readiness.ready or not worker_running:
        return _error(
            503,
            code="review_runtime_not_ready",
            problem="The controlled review runtime is not ready.",
            cause="A required worker, schema, checkpoint, or release gate is unavailable.",
            fix="Disable the feature, run doctor, and correct the reported readiness check.",
            retryable=True,
        )
    return {
        "status": "ok",
        "feature_enabled": True,
        "worker_running": worker_running,
        "application_schema_ready": readiness.application_schema_ready,
        "checkpoint_compatible": readiness.checkpoint_compatible,
        "gate_report_status": readiness.gate_report_status,
    }


@router.get("/api/runs/{run_id}/reviews/{review_id}")
async def show_review(run_id: str, review_id: str, request: Request):
    _, error = authenticate_review_request(request, run_id=run_id)
    if error is not None:
        return error
    identity, error = _validate_review_identity(
        run_id=run_id,
        review_id=review_id,
    )
    if error is not None:
        return error
    run_id, review_id = identity
    detail = await asyncio.to_thread(
        get_review_detail,
        run_id=run_id,
        review_id=review_id,
    )
    if detail is None:
        return _conflict_response("review_not_found", run_id=run_id)
    if detail["workflow"]["status"] == "manual_recovery":
        detail["operator_guidance"] = {
            "code": detail["workflow"]["last_error_code"],
            "docs_url": (
                "/docs/operations/controlled-review-workflow#manual-recovery"
            ),
        }
    return detail


def _conflict_response(code: str, *, run_id: str) -> JSONResponse:
    if code == "review_already_decided":
        return _error(
            409,
            code=code,
            problem="This review revision already has an accepted decision.",
            cause="A conflicting decision was submitted.",
            fix="Fetch the run and use the persisted decision result.",
            retryable=False,
            run_id=run_id,
        )
    if code == "decision_id_conflict":
        return _error(
            409,
            code=code,
            problem="This decision ID is already bound to another request.",
            cause="The decision ID was reused with different content.",
            fix="Use the original request or submit a new decision ID.",
            retryable=False,
            run_id=run_id,
        )
    if code == "stale_state_version":
        return _error(
            409,
            code=code,
            problem="The run changed before this decision was accepted.",
            cause="expected_state_version is stale.",
            fix="Fetch the run and retry against its current state version.",
            retryable=True,
            run_id=run_id,
        )
    if code == "review_not_found":
        return _error(
            404,
            code=code,
            problem="The requested review workflow was not found.",
            cause="The run, review, or revision does not match.",
            fix="Fetch the run and use its current review identity.",
            retryable=False,
            run_id=run_id,
        )
    if code == "review_not_waiting":
        return _error(
            409,
            code=code,
            problem="The review is not accepting a decision.",
            cause="The workflow is not in waiting_decision state.",
            fix="Fetch the run and inspect the current review status.",
            retryable=False,
            run_id=run_id,
        )
    if code == "unsupported_review_profile":
        return _error(
            409,
            code=code,
            problem="This run profile does not support durable review.",
            cause="P1B is limited to the Talent Hiring Signal profile.",
            fix="Use the existing delivery path for this profile.",
            retryable=False,
            run_id=run_id,
        )
    return _error(
        409,
        code=code,
        problem="The review decision could not be accepted.",
        cause="The durable review ledger rejected the transition.",
        fix="Fetch the run and inspect its current review status.",
        retryable=False,
        run_id=run_id,
    )


@router.post(
    "/api/runs/{run_id}/reviews/{review_id}/decisions",
    status_code=202,
    include_in_schema=True,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"title": "Body"},
                },
            },
        },
    },
)
async def submit_review_decision(
    run_id: str,
    review_id: str,
    request: Request,
):
    actor, error = authenticate_review_request(request, run_id=run_id)
    if error is not None:
        return error
    identity, error = _validate_review_identity(
        run_id=run_id,
        review_id=review_id,
    )
    if error is not None:
        return error
    run_id, review_id = identity
    try:
        if not _is_json_content_type(request.headers.get("content-type")):
            raise ValueError("invalid_review_content_type")
        body = await request.json()
        validated = ReviewDecisionRequest.model_validate(body)
    except (ClientDisconnect, RuntimeError, ValueError):
        return _error(
            422,
            code="invalid_review_decision",
            problem="The review decision request is invalid.",
            cause="The request body failed the bounded decision contract.",
            fix="Provide a valid decision ID, revision, action, and state version.",
            retryable=False,
            run_id=run_id,
        )
    try:
        result = await asyncio.to_thread(
            accept_review_decision,
            run_id=run_id,
            review_id=review_id,
            request=validated,
            actor_fingerprint=actor,
        )
    except ReviewConflict as exc:
        return _conflict_response(exc.code, run_id=run_id)
    return {
        "status": result.workflow_status,
        "run_id": run_id,
        "review_id": review_id,
        "decision_id": result.decision.decision_id,
        "idempotent_replay": result.idempotent_replay,
    }
