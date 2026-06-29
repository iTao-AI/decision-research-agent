from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request
import uuid


_LOCAL_ERROR_DETAILS: dict[str, tuple[str, str, str, bool]] = {
    "connection_failed": (
        "Cannot reach Decision Research Agent.",
        "The configured service endpoint is unavailable.",
        "Start the backend or verify DECISION_RESEARCH_AGENT_URL.",
        True,
    ),
    "request_timeout": (
        "The service request timed out.",
        "The backend did not respond within the configured request timeout.",
        "Retry the command or increase DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS.",
        True,
    ),
    "invalid_json_response": (
        "The service returned invalid JSON.",
        "The response could not be decoded as a JSON document.",
        "Check backend health and retry after the service is stable.",
        False,
    ),
    "json_response_not_object": (
        "The service returned an unsupported JSON value.",
        "The Tool Client requires a JSON object response.",
        "Check the backend and Tool Client versions before retrying.",
        False,
    ),
    "scope_file_unreadable": (
        "The scope file cannot be read.",
        "The file is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 JSON file.",
        False,
    ),
    "scope_file_invalid": (
        "The scope file is invalid.",
        "Research scope must be a JSON object.",
        "Correct the scope document and retry the command.",
        False,
    ),
    "run_response_invalid": (
        "The run creation response is invalid.",
        "The service did not return a non-empty string run_id.",
        "Check backend compatibility before creating another run.",
        False,
    ),
    "result_requires_wait": (
        "Canonical result retrieval requires --wait.",
        "The --result flag composes run creation, bounded waiting, and delivery.",
        "Use --wait --result, or call result --run-id separately.",
        False,
    ),
    "run_poll_seconds_must_be_positive": (
        "Run polling interval must be positive.",
        "The provided --poll-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "run_wait_timeout_seconds_must_be_positive": (
        "Run wait timeout must be positive.",
        "The provided --wait-timeout-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "run_wait_timeout": (
        "The run did not finish before the wait deadline.",
        "Client polling stopped while the server-side run may still be active.",
        "Inspect the run by ID or retry result --run-id later.",
        True,
    ),
    "run_has_no_durable_review": (
        "The run has no durable review workflow.",
        "No review identifier is attached to the run.",
        "Inspect the run state before requesting review details.",
        False,
    ),
    "confirm_source_match_required": (
        "Source confirmation is required.",
        "Evidence verification requires explicit source matching confirmation.",
        "Retry with --confirm-source-match after checking the source.",
        False,
    ),
    "exactly_one_reason_source_required": (
        "Exactly one reason source is required.",
        "The command requires either a reason file or standard input.",
        "Choose one reason input method and retry.",
        False,
    ),
    "rejection_reason_must_be_1_to_1000_characters": (
        "The rejection reason length is invalid.",
        "The reason must contain between 1 and 1000 characters.",
        "Provide a complete reason within the allowed limit.",
        False,
    ),
    "rejection_reason_unreadable": (
        "The rejection reason cannot be read.",
        "The selected input is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 reason and retry.",
        False,
    ),
    "verification_reason_must_be_1_to_1000_characters": (
        "The verification reason length is invalid.",
        "The reason must contain between 1 and 1000 characters.",
        "Provide a complete reason within the allowed limit.",
        False,
    ),
    "verification_reason_unreadable": (
        "The verification reason cannot be read.",
        "The selected input is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 reason and retry.",
        False,
    ),
    "review_poll_seconds_must_be_positive": (
        "Review polling interval must be positive.",
        "The provided --poll-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "review_wait_timeout_seconds_must_be_positive": (
        "Review wait timeout must be positive.",
        "The provided --wait-timeout-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "review_wait_timeout": (
        "The review did not finish before the wait deadline.",
        "Client polling stopped before the workflow reached a terminal state.",
        "Inspect the review by run ID and retry later.",
        True,
    ),
    "manual_recovery": (
        "The review requires manual recovery.",
        "The durable workflow cannot resume automatically.",
        "Follow the controlled review recovery runbook.",
        False,
    ),
}


def _local_error_payload(
    code: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    problem, cause, fix, retryable = _LOCAL_ERROR_DETAILS[code]
    return {
        "code": code,
        "problem": problem,
        "cause": cause,
        "fix": fix,
        "retryable": retryable,
        **(context or {}),
    }


def _normalize_service_error(
    payload: dict[str, Any],
    *,
    status: int,
) -> dict[str, Any]:
    normalized = dict(payload)
    defaults = {
        "code": f"http_{status}",
        "problem": "The service rejected the request.",
        "cause": "The request could not be completed.",
        "fix": "Inspect the error code and retry when safe.",
    }
    for field, default in defaults.items():
        if not isinstance(normalized.get(field), str) or not normalized[field]:
            normalized[field] = default
    if not isinstance(normalized.get("retryable"), bool):
        normalized["retryable"] = status >= 500
    return normalized


class ToolClientError(RuntimeError):
    """Bounded client error safe for JSON serialization."""

    def __init__(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ):
        self.payload = payload or _local_error_payload(code, context=context)
        super().__init__(self.payload["code"])


class ToolClientHTTPError(ToolClientError):
    """Bounded service error retaining its HTTP status."""

    def __init__(self, status: int, payload: dict[str, Any]):
        self.status = status
        super().__init__(
            str(payload.get("code") or f"http_{status}"),
            payload=_normalize_service_error(payload, status=status),
        )


@dataclass(frozen=True)
class ToolConfig:
    base_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    timeout_seconds: float = 10.0


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _headers(config: ToolConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    return headers


def _read_json(response: Any) -> dict[str, Any]:
    raw = response.read()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ToolClientError("invalid_json_response") from exc
    if not isinstance(parsed, dict):
        raise ToolClientError("json_response_not_object")
    return parsed


def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or isinstance(
        getattr(exc, "reason", None),
        TimeoutError,
    )


def _request_json(
    method: str,
    url: str,
    *,
    config: ToolConfig,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=body, method=method, headers=_headers(config))
    try:
        with request.urlopen(req, timeout=config.timeout_seconds) as response:
            status = response.getcode()
            parsed = _read_json(response)
    except error.HTTPError as exc:
        try:
            parsed = _read_json(exc)
        except ToolClientError:
            parsed = {
                "code": f"http_{exc.code}",
                "problem": "The server returned a non-JSON error.",
            }
        raise ToolClientHTTPError(exc.code, parsed) from exc
    except ToolClientError:
        raise
    except (OSError, error.URLError, TimeoutError) as exc:
        code = "request_timeout" if _is_timeout_error(exc) else "connection_failed"
        raise ToolClientError(code) from exc
    if status < 200 or status >= 300:
        raise ToolClientHTTPError(status, parsed)
    return parsed


def healthcheck(config: ToolConfig) -> dict[str, Any]:
    return _request_json("GET", _join_url(config.base_url, "/health"), config=config)


def profile_manifest(profile_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_profile_id = parse.quote(profile_id, safe="")
    return _request_json(
        "GET",
        _join_url(config.base_url, f"/api/profiles/{encoded_profile_id}"),
        config=config,
    )


def review_health(config: ToolConfig) -> dict[str, Any]:
    return _request_json(
        "GET",
        _join_url(config.base_url, "/api/reviews/health"),
        config=config,
    )


def evidence_verification_health(config: ToolConfig) -> dict[str, Any]:
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            "/api/evidence-verifications/health",
        ),
        config=config,
    )


def doctor(config: ToolConfig) -> dict[str, Any]:
    """Check the backend and the compiled Talent profile contract."""
    checks: dict[str, dict[str, Any]] = {}
    health = healthcheck(config)
    checks["server"] = {
        "status": "ok" if health.get("status") == "ok" else "failed",
        "service": health.get("service"),
    }
    manifest = profile_manifest("talent-hiring-signal", config)
    checks["talent_profile"] = {
        "status": (
            "ok"
            if manifest.get("profile", {}).get("profile_id") == "talent-hiring-signal"
            else "failed"
        ),
        "allowed_tools": manifest.get("harness_policy", {}).get("allowed_tools", []),
    }
    try:
        review = review_health(config)
    except ToolClientHTTPError as exc:
        if (
            exc.status == 404
            and exc.payload.get("code") == "durable_hitl_disabled"
        ):
            checks["durable_review"] = {"status": "disabled"}
        else:
            raise
    else:
        checks["durable_review"] = {
            "status": "ok" if review.get("status") == "ok" else "failed",
            "worker_running": review.get("worker_running"),
            "gate_report_status": review.get("gate_report_status"),
        }
    try:
        verification = evidence_verification_health(config)
    except ToolClientHTTPError as exc:
        if (
            exc.status == 404
            and exc.payload.get("code")
            == "evidence_verification_disabled"
        ):
            checks["evidence_verification"] = {"status": "disabled"}
        else:
            checks["evidence_verification"] = {
                "status": "failed",
                "code": exc.payload.get("code"),
            }
    else:
        checks["evidence_verification"] = {
            "status": (
                "ok"
                if verification.get("status") == "ok"
                else "failed"
            ),
            "worker_running": verification.get("worker_running"),
        }
    return {
        "status": "ok"
        if all(
            check["status"] in {"ok", "disabled"}
            for check in checks.values()
        )
        else "failed",
        "checks": checks,
    }


def read_scope_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ToolClientError("scope_file_unreadable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolClientError("scope_file_invalid") from exc
    if not isinstance(parsed, dict):
        raise ToolClientError("scope_file_invalid")
    return parsed


def start_run(
    *,
    query: str,
    thread_id: str | None,
    profile_id: str,
    scope: dict[str, Any],
    config: ToolConfig,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "profile_id": profile_id,
        "scope": scope,
    }
    if thread_id:
        payload["thread_id"] = thread_id
    return _request_json(
        "POST", _join_url(config.base_url, "/api/runs"), config=config, payload=payload
    )


def get_run(run_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_run_id = parse.quote(run_id, safe="")
    return _request_json(
        "GET", _join_url(config.base_url, f"/api/runs/{encoded_run_id}"), config=config
    )


def result(run_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_run_id = parse.quote(run_id, safe="")
    return _request_json(
        "GET",
        _join_url(config.base_url, f"/api/runs/{encoded_run_id}/result"),
        config=config,
    )


def list_reviews(
    config: ToolConfig,
    *,
    status: str = "waiting_decision",
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    query = {"status": status, "limit": str(limit)}
    if cursor:
        query["cursor"] = cursor
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            f"/api/reviews?{parse.urlencode(query)}",
        ),
        config=config,
    )


def show_review(
    *,
    run_id: str,
    review_id: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    resolved_review_id = review_id
    if resolved_review_id is None:
        run = get_run(run_id, config)
        workflow = run.get("review_workflow") or {}
        resolved_review_id = workflow.get("review_id")
        if not resolved_review_id:
            raise ToolClientError("run_has_no_durable_review")
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/reviews/{parse.quote(resolved_review_id, safe='')}"
            ),
        ),
        config=config,
    )


def list_evidence_verifications(
    *,
    run_id: str,
    limit: int,
    cursor: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    query = {"limit": str(limit)}
    if cursor:
        query["cursor"] = cursor
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/evidence/verifications?{parse.urlencode(query)}"
            ),
        ),
        config=config,
    )


def show_evidence_verification(
    *,
    run_id: str,
    evidence_id: str,
    config: ToolConfig,
) -> dict[str, Any]:
    return _request_json(
        "GET",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/evidence/{parse.quote(evidence_id, safe='')}"
                "/verification"
            ),
        ),
        config=config,
    )


def stable_verification_id(
    *,
    run_id: str,
    evidence_id: str,
    evidence_fingerprint: str,
    expected_revision: int,
    action: str,
    reason_code: str | None,
    reason_note: str | None,
) -> str:
    note_hash = hashlib.sha256(
        (reason_note or "").encode("utf-8")
    ).hexdigest()
    semantic = "\n".join(
        [
            run_id,
            evidence_id,
            evidence_fingerprint,
            str(expected_revision),
            action,
            reason_code or "",
            note_hash,
        ]
    )
    return f"verification_{uuid.uuid5(uuid.NAMESPACE_URL, semantic).hex}"


def submit_evidence_verification_decision(
    *,
    run_id: str,
    evidence_id: str,
    action: str,
    confirm_source_match: bool,
    reason_code: str | None,
    reason_note: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    if action == "verify" and not confirm_source_match:
        raise ToolClientError("confirm_source_match_required")
    detail = show_evidence_verification(
        run_id=run_id,
        evidence_id=evidence_id,
        config=config,
    )
    effective = detail["effective"]
    expected_revision = effective["verification_revision"]
    fingerprint = effective["evidence_fingerprint"]
    payload = {
        "verification_id": stable_verification_id(
            run_id=run_id,
            evidence_id=evidence_id,
            evidence_fingerprint=fingerprint,
            expected_revision=expected_revision,
            action=action,
            reason_code=reason_code,
            reason_note=reason_note,
        ),
        "evidence_fingerprint": fingerprint,
        "expected_revision": expected_revision,
        "action": action,
        "confirm_source_match": confirm_source_match,
        "reason_code": reason_code,
        "reason_note": reason_note,
    }
    return _request_json(
        "POST",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/evidence/{parse.quote(evidence_id, safe='')}"
                "/verification-decisions"
            ),
        ),
        config=config,
        payload=payload,
    )


def finalize_evidence_verification(
    *,
    run_id: str,
    config: ToolConfig,
) -> dict[str, Any]:
    run = get_run(run_id, config)
    return _request_json(
        "POST",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                "/evidence/verification-snapshots"
            ),
        ),
        config=config,
        payload={"expected_state_version": run["state_version"]},
    )


def stable_decision_id(
    *,
    run_id: str,
    review_id: str,
    revision: int,
    action: str,
    reason: str | None,
) -> str:
    reason_hash = hashlib.sha256((reason or "").encode("utf-8")).hexdigest()
    semantic = "\n".join(
        [run_id, review_id, str(revision), action, reason_hash]
    )
    return f"decision_{uuid.uuid5(uuid.NAMESPACE_URL, semantic).hex}"


def _read_bounded_text(stream, *, error_code: str) -> str:
    value = stream.read(1002)
    if len(value) > 1001:
        raise ToolClientError(error_code)
    value = value.strip()
    if not 1 <= len(value) <= 1000:
        raise ToolClientError(error_code)
    return value


def _read_bounded_rejection_reason(stream) -> str:
    return _read_bounded_text(
        stream,
        error_code="rejection_reason_must_be_1_to_1000_characters",
    )


def read_rejection_reason(
    *,
    reason_file: Path | None,
    reason_stdin: bool,
    stdin,
) -> str:
    if (reason_file is None) == (not reason_stdin):
        raise ToolClientError("exactly_one_reason_source_required")
    try:
        if reason_file is not None:
            with reason_file.open("r", encoding="utf-8") as handle:
                return _read_bounded_rejection_reason(handle)
        else:
            return _read_bounded_rejection_reason(stdin)
    except (OSError, UnicodeError) as exc:
        raise ToolClientError("rejection_reason_unreadable") from exc


def read_verification_reason(
    *,
    reason_file: Path | None,
    reason_stdin: bool,
    stdin,
) -> str:
    if (reason_file is None) == (not reason_stdin):
        raise ToolClientError("exactly_one_reason_source_required")
    try:
        if reason_file is not None:
            with reason_file.open("r", encoding="utf-8") as handle:
                return _read_bounded_text(
                    handle,
                    error_code=(
                        "verification_reason_must_be_1_to_1000_characters"
                    ),
                )
        return _read_bounded_text(
            stdin,
            error_code="verification_reason_must_be_1_to_1000_characters",
        )
    except (OSError, UnicodeError) as exc:
        raise ToolClientError("verification_reason_unreadable") from exc


def submit_review_decision(
    *,
    run_id: str,
    review_id: str | None,
    decision_id: str | None,
    action: str,
    reason: str | None,
    config: ToolConfig,
) -> dict[str, Any]:
    detail = show_review(
        run_id=run_id,
        review_id=review_id,
        config=config,
    )
    resolved_review_id = detail["review_id"]
    resolved_decision_id = decision_id or stable_decision_id(
        run_id=run_id,
        review_id=resolved_review_id,
        revision=detail["review_revision"],
        action=action,
        reason=reason,
    )
    payload = {
        "decision_id": resolved_decision_id,
        "review_revision": detail["review_revision"],
        "action": action,
        "reason": reason,
        "expected_state_version": detail["state_version"],
    }
    result = _request_json(
        "POST",
        _join_url(
            config.base_url,
            (
                f"/api/runs/{parse.quote(run_id, safe='')}"
                f"/reviews/{parse.quote(resolved_review_id, safe='')}"
                "/decisions"
            ),
        ),
        config=config,
        payload=payload,
    )
    return {key: value for key, value in result.items() if key != "reason"}


def wait_for_run(
    run_id: str,
    config: ToolConfig,
    *,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    if poll_seconds <= 0:
        raise ToolClientError("run_poll_seconds_must_be_positive")
    if timeout_seconds <= 0:
        raise ToolClientError("run_wait_timeout_seconds_must_be_positive")
    deadline = time.monotonic() + timeout_seconds
    first_poll = True
    while first_poll or time.monotonic() < deadline:
        first_poll = False
        result = get_run(run_id, config)
        if result.get("execution_status") in {
            "completed",
            "completed_with_fallback",
            "failed",
        }:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ToolClientError("run_wait_timeout")
        time.sleep(min(poll_seconds, remaining))
    raise ToolClientError("run_wait_timeout")


def _bounded_error_code(value: Any) -> str:
    rendered = str(value)
    if not 1 <= len(rendered) <= 128:
        return "unknown"
    if not all(character.isalnum() or character in "._-" for character in rendered):
        return "unknown"
    return rendered


def wait_for_review(
    *,
    run_id: str,
    review_id: str | None,
    config: ToolConfig,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if poll_seconds <= 0:
        raise ToolClientError("review_poll_seconds_must_be_positive")
    if timeout_seconds <= 0:
        raise ToolClientError(
            "review_wait_timeout_seconds_must_be_positive"
        )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = show_review(
            run_id=run_id,
            review_id=review_id,
            config=config,
        )
        status = result["workflow"]["status"]
        if status in {"approved", "rejected"}:
            return result
        if status == "manual_recovery":
            recovery_code = _bounded_error_code(
                result["workflow"].get("last_error_code") or "unknown"
            )
            raise ToolClientError(
                "manual_recovery",
                context={"recovery_code": recovery_code},
            )
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(poll_seconds, remaining))
    raise ToolClientError("review_wait_timeout")


def config_from_env(args: argparse.Namespace) -> ToolConfig:
    timeout_raw = args.timeout or os.environ.get(
        "DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS",
        "",
    )
    try:
        timeout = float(timeout_raw) if timeout_raw else ToolConfig.timeout_seconds
    except (TypeError, ValueError):
        timeout = ToolConfig.timeout_seconds
    if timeout <= 0:
        timeout = ToolConfig.timeout_seconds
    base_url_raw = args.base_url or os.environ.get(
        "DECISION_RESEARCH_AGENT_URL",
        "",
    )
    base_url = (base_url_raw or "").strip() or ToolConfig.base_url
    return ToolConfig(
        base_url=base_url,
        api_key=os.environ.get("DECISION_RESEARCH_AGENT_API_KEY"),
        timeout_seconds=timeout,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decision Research Agent integration tool"
    )
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("healthcheck")
    subparsers.add_parser("doctor")

    run = subparsers.add_parser("run")
    run.add_argument("--query", required=True)
    run.add_argument("--thread-id")
    run.add_argument("--profile", default="generic")
    run.add_argument("--scope-file")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--result", action="store_true")
    run.add_argument("--poll-seconds", type=float, default=1)
    run.add_argument("--wait-timeout-seconds", type=float, default=600)

    result = subparsers.add_parser("result")
    result.add_argument("--run-id", required=True)

    review = subparsers.add_parser("review")
    review_subparsers = review.add_subparsers(
        dest="review_command",
        required=True,
    )
    review_list = review_subparsers.add_parser("list")
    review_list.add_argument("--status", default="waiting_decision")
    review_list.add_argument("--limit", type=int, default=20)
    review_list.add_argument("--cursor")

    review_show = review_subparsers.add_parser("show")
    review_show.add_argument("--run-id", required=True)
    review_show.add_argument("--review-id")

    review_approve = review_subparsers.add_parser("approve")
    review_approve.add_argument("--run-id", required=True)
    review_approve.add_argument("--review-id")
    review_approve.add_argument("--decision-id")
    review_approve.add_argument("--wait", action="store_true")

    review_reject = review_subparsers.add_parser("reject")
    review_reject.add_argument("--run-id", required=True)
    review_reject.add_argument("--review-id")
    review_reject.add_argument("--decision-id")
    reason = review_reject.add_mutually_exclusive_group(required=True)
    reason.add_argument("--reason-file", type=Path)
    reason.add_argument("--reason-stdin", action="store_true")
    review_reject.add_argument("--wait", action="store_true")

    review_wait = review_subparsers.add_parser("wait")
    review_wait.add_argument("--run-id", required=True)
    review_wait.add_argument("--review-id")
    review_wait.add_argument("--poll-seconds", type=float, default=1)
    review_wait.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=120,
    )

    evidence = subparsers.add_parser("evidence")
    evidence_subparsers = evidence.add_subparsers(
        dest="evidence_command",
        required=True,
    )
    evidence_list = evidence_subparsers.add_parser("list")
    evidence_list.add_argument("--run-id", required=True)
    evidence_list.add_argument("--limit", type=int, default=20)
    evidence_list.add_argument("--cursor")

    evidence_show = evidence_subparsers.add_parser("show")
    evidence_show.add_argument("--run-id", required=True)
    evidence_show.add_argument("--evidence-id", required=True)

    evidence_verify = evidence_subparsers.add_parser("verify")
    evidence_verify.add_argument("--run-id", required=True)
    evidence_verify.add_argument("--evidence-id", required=True)
    evidence_verify.add_argument(
        "--confirm-source-match",
        action="store_true",
    )

    evidence_reject = evidence_subparsers.add_parser("reject")
    evidence_reject.add_argument("--run-id", required=True)
    evidence_reject.add_argument("--evidence-id", required=True)
    evidence_reject.add_argument("--reason-code", required=True)
    verification_reason = evidence_reject.add_mutually_exclusive_group(
        required=True
    )
    verification_reason.add_argument("--reason-file", type=Path)
    verification_reason.add_argument(
        "--reason-stdin",
        action="store_true",
    )

    evidence_finalize = evidence_subparsers.add_parser("finalize")
    evidence_finalize.add_argument("--run-id", required=True)
    return parser


def _with_error_context(
    exc: ToolClientError,
    *,
    context: dict[str, Any],
) -> ToolClientError:
    payload = {**exc.payload, **context}
    if isinstance(exc, ToolClientHTTPError):
        return ToolClientHTTPError(exc.status, payload)
    return ToolClientError(str(payload["code"]), payload=payload)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = config_from_env(args)
    try:
        if args.command == "healthcheck":
            result = healthcheck(config)
        elif args.command == "doctor":
            result = doctor(config)
        elif args.command == "run":
            if args.result and not args.wait:
                raise ToolClientError("result_requires_wait")
            scope = read_scope_file(Path(args.scope_file)) if args.scope_file else {}
            created = start_run(
                query=args.query,
                thread_id=args.thread_id,
                profile_id=args.profile,
                scope=scope,
                config=config,
            )
            if not args.wait:
                result = created
            else:
                run_id = created.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ToolClientError("run_response_invalid")
                try:
                    terminal = wait_for_run(
                        run_id,
                        config,
                        poll_seconds=args.poll_seconds,
                        timeout_seconds=args.wait_timeout_seconds,
                    )
                    result = (
                        globals()["result"](run_id, config)
                        if args.result
                        else terminal
                    )
                except ToolClientError as exc:
                    raise _with_error_context(
                        exc,
                        context={"run_id": run_id},
                    ) from exc
        elif args.command == "result":
            result = globals()["result"](args.run_id, config)
        elif args.command == "review" and args.review_command == "list":
            result = list_reviews(
                config,
                status=args.status,
                limit=args.limit,
                cursor=args.cursor,
            )
        elif args.command == "review" and args.review_command == "show":
            result = show_review(
                run_id=args.run_id,
                review_id=args.review_id,
                config=config,
            )
        elif args.command == "review" and args.review_command == "approve":
            result = submit_review_decision(
                run_id=args.run_id,
                review_id=args.review_id,
                decision_id=args.decision_id,
                action="approve",
                reason=None,
                config=config,
            )
            if args.wait:
                result = wait_for_review(
                    run_id=args.run_id,
                    review_id=result["review_id"],
                    config=config,
                )
        elif args.command == "review" and args.review_command == "reject":
            reason = read_rejection_reason(
                reason_file=args.reason_file,
                reason_stdin=args.reason_stdin,
                stdin=sys.stdin,
            )
            result = submit_review_decision(
                run_id=args.run_id,
                review_id=args.review_id,
                decision_id=args.decision_id,
                action="reject",
                reason=reason,
                config=config,
            )
            if args.wait:
                result = wait_for_review(
                    run_id=args.run_id,
                    review_id=result["review_id"],
                    config=config,
                )
        elif args.command == "review" and args.review_command == "wait":
            result = wait_for_review(
                run_id=args.run_id,
                review_id=args.review_id,
                config=config,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.wait_timeout_seconds,
            )
        elif args.command == "evidence" and args.evidence_command == "list":
            result = list_evidence_verifications(
                run_id=args.run_id,
                limit=args.limit,
                cursor=args.cursor,
                config=config,
            )
        elif args.command == "evidence" and args.evidence_command == "show":
            result = show_evidence_verification(
                run_id=args.run_id,
                evidence_id=args.evidence_id,
                config=config,
            )
        elif args.command == "evidence" and args.evidence_command == "verify":
            result = submit_evidence_verification_decision(
                run_id=args.run_id,
                evidence_id=args.evidence_id,
                action="verify",
                confirm_source_match=args.confirm_source_match,
                reason_code=None,
                reason_note=None,
                config=config,
            )
        elif args.command == "evidence" and args.evidence_command == "reject":
            reason_note = read_verification_reason(
                reason_file=args.reason_file,
                reason_stdin=args.reason_stdin,
                stdin=sys.stdin,
            )
            result = submit_evidence_verification_decision(
                run_id=args.run_id,
                evidence_id=args.evidence_id,
                action="reject",
                confirm_source_match=False,
                reason_code=args.reason_code,
                reason_note=reason_note,
                config=config,
            )
        elif args.command == "evidence" and args.evidence_command == "finalize":
            result = finalize_evidence_verification(
                run_id=args.run_id,
                config=config,
            )
        else:
            parser.error(f"unknown command: {args.command}")
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ToolClientError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
