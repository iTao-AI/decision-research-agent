#!/usr/bin/env python3
"""Repeated benchmark runner for Deep Search Agent.

Runs fixed queries through the existing manual E2E runner and summarizes
completion, fallback, latency, and token usage. This script is intended for
manual benchmark evidence collection; do not treat one run as a stable metric.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_runner


DEFAULT_QUERIES = [
    "调研 AI Agent 在企业知识管理中的应用趋势，输出结构化报告",
    "比较 LangGraph 与 AutoGen 在多 Agent 编排中的适用场景",
    "调研 RAG 评估体系中的引用正确性和低置信处理",
    "分析多模态 OCR 在合同审查中的落地风险",
    "总结 Deep Research 产品的工程架构共性",
]


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round((percentile / 100) * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _token_total(result: dict[str, Any]) -> int:
    token_usage = result.get("token_usage") or {}
    return int(token_usage.get("total_tokens") or 0)


def summarize_benchmark_runs(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize repeated run outputs from scripts/e2e_runner.py."""
    elapsed = [
        float(result["elapsed_seconds"])
        for result in results
        if result.get("elapsed_seconds") is not None
    ]
    token_totals = [_token_total(result) for result in results]
    completed_statuses = {"completed", "completed_with_fallback"}

    return {
        "run_count": len(results),
        "completed_count": sum(
            1 for result in results if result.get("status") in completed_statuses
        ),
        "failed_count": sum(1 for result in results if result.get("status") == "failed"),
        "timeout_count": sum(
            1 for result in results if result.get("status") == "runner_timeout"
        ),
        "fallback_count": sum(
            1
            for result in results
            if result.get("fallback_used")
            or result.get("status") == "completed_with_fallback"
        ),
        "elapsed_seconds_median": statistics.median(elapsed) if elapsed else None,
        "elapsed_seconds_p95": _percentile_nearest_rank(elapsed, 95),
        "total_tokens_median": statistics.median(token_totals) if token_totals else None,
        "total_tokens_p95": _percentile_nearest_rank(token_totals, 95),
    }


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for repetition in range(args.repetitions):
        for query_index, query in enumerate(args.queries, start=1):
            thread_id = f"{args.thread_prefix}-r{repetition + 1}-q{query_index}"
            runner_args = argparse.Namespace(
                api_base=args.api_base,
                ws_base=args.ws_base,
                query=query,
                thread_id=thread_id,
                api_key=args.api_key,
                timeout_seconds=args.timeout_seconds,
                poll_interval=args.poll_interval,
                output=None,
            )
            result = await e2e_runner.run(runner_args)
            result["repetition"] = repetition + 1
            result["query_index"] = query_index
            results.append(result)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repetitions": args.repetitions,
        "query_count": len(args.queries),
        "summary": summarize_benchmark_runs(results),
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repeated Deep Search Agent benchmark queries."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-base", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument(
        "--thread-prefix",
        default=f"benchmark-{int(time.time())}",
    )
    parser.add_argument("--query-file", default=None)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _load_queries(path: str | None) -> list[str]:
    if path is None:
        return DEFAULT_QUERIES
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def main() -> None:
    args = parse_args()
    args.queries = _load_queries(args.query_file)
    result = asyncio.run(run_benchmark(args))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
