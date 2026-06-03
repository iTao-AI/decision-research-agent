#!/usr/bin/env python3
"""Manual E2E runner for Deep Search Agent.

Connects WebSocket before submitting a task, records monitor events, then polls
the persisted task endpoint until a terminal status is reached.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import requests


TERMINAL_STATUSES = {"completed", "completed_with_fallback", "failed"}


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def default_ws_base(api_base: str) -> str:
    parsed = urlparse(api_base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


def summarize_ws_events(events: list[dict[str, Any]]) -> dict[str, int]:
    monitor_events = [
        event for event in events if event.get("type") == "monitor_event"
    ]
    return {
        "websocket_events": len(monitor_events),
        "assistant_calls": sum(
            1 for event in monitor_events if event.get("event") == "assistant_call"
        ),
        "tool_starts": sum(
            1 for event in monitor_events if event.get("event") == "tool_start"
        ),
    }


def _headers(api_key: str | None) -> dict[str, str]:
    return {"X-API-Key": api_key} if api_key else {}


async def collect_websocket_events(
    ws_base: str,
    thread_id: str,
    api_key: str | None,
    events: list[dict[str, Any]],
    stop_event: asyncio.Event,
) -> None:
    import websockets

    query = f"?api_key={quote(api_key)}" if api_key else ""
    url = f"{ws_base.rstrip('/')}/ws/{thread_id}{query}"
    try:
        async with websockets.connect(url) as websocket:
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                events.append(json.loads(raw))
    except Exception as exc:
        events.append(
            {
                "type": "runner_error",
                "event": "websocket_error",
                "message": str(exc),
            }
        )


def submit_task(
    api_base: str, query: str, thread_id: str, api_key: str | None
) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}/api/task",
        json={"query": query, "thread_id": thread_id},
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_task(api_base: str, thread_id: str, api_key: str | None) -> dict[str, Any]:
    response = requests.get(
        f"{api_base.rstrip('/')}/api/tasks/{thread_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_token_usage(
    api_base: str, thread_id: str, api_key: str | None
) -> dict[str, Any]:
    response = requests.get(
        f"{api_base.rstrip('/')}/api/token-usage/{thread_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def report_size(output_path: str | None) -> int:
    if not output_path:
        return 0
    path = Path(output_path)
    return path.stat().st_size if path.exists() else 0


async def run(args: argparse.Namespace) -> dict[str, Any]:
    ws_base = args.ws_base or default_ws_base(args.api_base)
    events: list[dict[str, Any]] = []
    stop_event = asyncio.Event()
    started_at = time.monotonic()

    ws_task = asyncio.create_task(
        collect_websocket_events(
            ws_base, args.thread_id, args.api_key, events, stop_event
        )
    )
    await asyncio.sleep(0.25)

    submit_task(args.api_base, args.query, args.thread_id, args.api_key)

    task_state: dict[str, Any] = {}
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        task_state = fetch_task(args.api_base, args.thread_id, args.api_key)
        if is_terminal_status(task_state.get("status", "")):
            break
        await asyncio.sleep(args.poll_interval)
    else:
        task_state = {
            "thread_id": args.thread_id,
            "query": args.query,
            "status": "runner_timeout",
            "output_path": None,
        }

    stop_event.set()
    await asyncio.sleep(0)
    ws_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass

    token_usage = fetch_token_usage(args.api_base, args.thread_id, args.api_key)
    event_summary = summarize_ws_events(events)
    output_path = task_state.get("output_path")

    return {
        "thread_id": args.thread_id,
        "query": args.query,
        "status": task_state.get("status"),
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        **event_summary,
        "token_usage": token_usage,
        "output_path": output_path,
        "report_size_bytes": report_size(output_path),
        "fallback_used": task_state.get("status") == "completed_with_fallback",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one manual Deep Search Agent E2E task."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-base", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
