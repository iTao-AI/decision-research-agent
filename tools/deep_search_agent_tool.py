from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class ToolClientError(RuntimeError):
    """Raised when the Deep Search Agent tool client cannot complete a request."""


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
    parser = argparse.ArgumentParser(description="Deep Search Agent integration tool")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("healthcheck")

    start = subparsers.add_parser("start-task")
    start.add_argument("--query", required=True)
    start.add_argument("--thread-id")

    get = subparsers.add_parser("get-task")
    get.add_argument("--thread-id", required=True)

    usage = subparsers.add_parser("token-usage")
    usage.add_argument("--thread-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = config_from_env(args)
    try:
        if args.command == "healthcheck":
            result = healthcheck(config)
        elif args.command == "start-task":
            result = start_task(args.query, args.thread_id, config)
        elif args.command == "get-task":
            result = get_task(args.thread_id, config)
        elif args.command == "token-usage":
            result = token_usage(args.thread_id, config)
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
