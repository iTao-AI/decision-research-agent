from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class ToolClientError(RuntimeError):
    """Raised when the Decision Research Agent client cannot complete a request."""


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
    return {
        "status": "ok"
        if all(check["status"] == "ok" for check in checks.values())
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


def config_from_env(args: argparse.Namespace) -> ToolConfig:
    timeout_raw = args.timeout or os.environ.get("DEEP_SEARCH_AGENT_TIMEOUT_SECONDS", "")
    try:
        timeout = float(timeout_raw) if timeout_raw else ToolConfig.timeout_seconds
    except ValueError:
        timeout = ToolConfig.timeout_seconds
    if timeout <= 0:
        timeout = ToolConfig.timeout_seconds
    return ToolConfig(
        base_url=(args.base_url or os.environ.get("DEEP_SEARCH_AGENT_URL") or ToolConfig.base_url).strip(),
        api_key=os.environ.get("DEEP_SEARCH_AGENT_API_KEY"),
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
            result = get_run(args.run_id, config)
        else:
            parser.error(f"unknown command: {args.command}")
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ToolClientError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
