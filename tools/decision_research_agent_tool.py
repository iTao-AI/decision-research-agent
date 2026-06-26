from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import RLock
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request
import uuid
import warnings


_MISSING = object()
_WARNED_LEGACY_KEYS: set[str] = set()
_WARNING_LOCK = RLock()


class ToolClientError(RuntimeError):
    """Raised when the Decision Research Agent client cannot complete a request."""


class ToolClientHTTPError(ToolClientError):
    """Raised when the server returns a structured non-success response."""

    def __init__(self, status: int, payload: dict[str, Any]):
        self.status = status
        self.payload = payload
        super().__init__(payload.get("code") or f"http_{status}")


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
    except Exception as exc:
        raise ToolClientError(f"invalid JSON response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolClientError("JSON response must be an object")
    return parsed


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
                "retryable": False,
            }
        raise ToolClientHTTPError(exc.code, parsed) from exc
    except ToolClientError:
        raise
    except (OSError, error.URLError, TimeoutError) as exc:
        raise ToolClientError(str(exc)) from exc
    if status < 200 or status >= 300:
        raise ToolClientError(f"HTTP {status} from {url}: {parsed.get('detail') or parsed.get('error') or 'request failed'}")
    return parsed


def healthcheck(config: ToolConfig) -> dict[str, Any]:
    return _request_json("GET", _join_url(config.base_url, "/health"), config=config)


def start_task(query: str, thread_id: str | None, config: ToolConfig) -> dict[str, Any]:
    payload = {"query": query}
    if thread_id:
        payload["thread_id"] = thread_id
    return _request_json("POST", _join_url(config.base_url, "/api/task"), config=config, payload=payload)


def get_task(thread_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_thread_id = parse.quote(thread_id, safe="")
    return _request_json("GET", _join_url(config.base_url, f"/api/tasks/{encoded_thread_id}"), config=config)


def token_usage(thread_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_thread_id = parse.quote(thread_id, safe="")
    return _request_json("GET", _join_url(config.base_url, f"/api/token-usage/{encoded_thread_id}"), config=config)


def research_run(thread_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded_thread_id = parse.quote(thread_id, safe="")
    return _request_json("GET", _join_url(config.base_url, f"/api/research/runs/{encoded_thread_id}"), config=config)


def research_runs(config: ToolConfig, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    return _request_json("GET", _join_url(config.base_url, f"/api/research/runs?limit={safe_limit}"), config=config)


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
) -> dict[str, Any]:
    while True:
        result = get_run(run_id, config)
        if result.get("execution_status") in {
            "completed",
            "completed_with_fallback",
            "failed",
        }:
            return result
        time.sleep(poll_seconds)


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
            code = result["workflow"].get("last_error_code") or "unknown"
            raise ToolClientError(f"manual_recovery:{code}")
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(poll_seconds, remaining))
    raise ToolClientError("review_wait_timeout")


def _resolve_env(
    canonical_key: str,
    legacy_key: str,
    *,
    default: str | None = None,
) -> str | None:
    """Resolve Tool Client settings without repository package imports."""
    canonical = os.environ.get(canonical_key, _MISSING)
    if canonical is not _MISSING:
        if legacy_key in os.environ:
            _warn_once(
                legacy_key,
                f"{legacy_key} is deprecated and ignored because {canonical_key} is set",
            )
        return canonical

    legacy = os.environ.get(legacy_key, _MISSING)
    if legacy is _MISSING:
        return default

    _warn_once(legacy_key, f"{legacy_key} is deprecated; use {canonical_key}")
    return legacy


def _warn_once(legacy_key: str, message: str) -> None:
    # Keep these semantics aligned with agent.runtime_env.
    with _WARNING_LOCK:
        if legacy_key in _WARNED_LEGACY_KEYS:
            return
        try:
            warnings.warn(message, FutureWarning, stacklevel=3)
        except FutureWarning:
            # Warning policy must not turn legacy configuration into an outage.
            pass
        finally:
            _WARNED_LEGACY_KEYS.add(legacy_key)


def _reset_warning_state_for_tests() -> None:
    """Reset warning deduplication for tests; production code must not call it."""
    with _WARNING_LOCK:
        _WARNED_LEGACY_KEYS.clear()


def config_from_env(args: argparse.Namespace) -> ToolConfig:
    timeout_raw = args.timeout or _resolve_env(
        "DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS",
        "DEEP_SEARCH_AGENT_TIMEOUT_SECONDS",
        default="",
    )
    try:
        timeout = float(timeout_raw) if timeout_raw else ToolConfig.timeout_seconds
    except (TypeError, ValueError):
        timeout = ToolConfig.timeout_seconds
    if timeout <= 0:
        timeout = ToolConfig.timeout_seconds
    base_url_raw = args.base_url or _resolve_env(
        "DECISION_RESEARCH_AGENT_URL",
        "DEEP_SEARCH_AGENT_URL",
        default="",
    )
    base_url = (base_url_raw or "").strip() or ToolConfig.base_url
    return ToolConfig(
        base_url=base_url,
        api_key=_resolve_env(
            "DECISION_RESEARCH_AGENT_API_KEY",
            "DEEP_SEARCH_AGENT_API_KEY",
        ),
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

    start = subparsers.add_parser("start-task")
    start.add_argument("--query", required=True)
    start.add_argument("--thread-id")

    get = subparsers.add_parser("get-task")
    get.add_argument("--thread-id", required=True)

    usage = subparsers.add_parser("token-usage")
    usage.add_argument("--thread-id", required=True)

    research = subparsers.add_parser("research-run")
    research.add_argument("--thread-id", required=True)

    research_list = subparsers.add_parser("research-runs")
    research_list.add_argument("--limit", type=int, default=50)

    run = subparsers.add_parser("run")
    run.add_argument("--query", required=True)
    run.add_argument("--thread-id")
    run.add_argument("--profile", default="generic")
    run.add_argument("--scope-file")
    run.add_argument("--wait", action="store_true")

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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = config_from_env(args)
    try:
        if args.command == "healthcheck":
            result = healthcheck(config)
        elif args.command == "doctor":
            result = doctor(config)
        elif args.command == "start-task":
            result = start_task(args.query, args.thread_id, config)
        elif args.command == "get-task":
            result = get_task(args.thread_id, config)
        elif args.command == "token-usage":
            result = token_usage(args.thread_id, config)
        elif args.command == "research-run":
            result = research_run(args.thread_id, config)
        elif args.command == "research-runs":
            result = research_runs(config, args.limit)
        elif args.command == "run":
            scope = {}
            if args.scope_file:
                scope = json.loads(Path(args.scope_file).read_text(encoding="utf-8"))
            result = start_run(
                query=args.query,
                thread_id=args.thread_id,
                profile_id=args.profile,
                scope=scope,
                config=config,
            )
            if args.wait:
                result = wait_for_run(result["run_id"], config)
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
    except ToolClientHTTPError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2))
        return 1
    except ToolClientError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
