"""Unit tests for repeated benchmark summary helpers."""
import importlib.util
from pathlib import Path


def _load_benchmark_module():
    path = Path("scripts/benchmark_runner.py").resolve()
    spec = importlib.util.spec_from_file_location("benchmark_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_summarize_benchmark_runs_reports_median_p95_and_fallbacks():
    benchmark = _load_benchmark_module()

    summary = benchmark.summarize_benchmark_runs(
        [
            {
                "status": "completed",
                "elapsed_seconds": 10,
                "fallback_used": False,
                "token_usage": {"total_tokens": 100},
            },
            {
                "status": "completed_with_fallback",
                "elapsed_seconds": 20,
                "fallback_used": True,
                "token_usage": {"total_tokens": 200},
            },
            {
                "status": "failed",
                "elapsed_seconds": 30,
                "fallback_used": False,
                "token_usage": {"total_tokens": 300},
            },
        ]
    )

    assert summary["run_count"] == 3
    assert summary["completed_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["elapsed_seconds_median"] == 20
    assert summary["elapsed_seconds_p95"] == 30
    assert summary["total_tokens_median"] == 200
