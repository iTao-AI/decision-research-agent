"""Replay transport cancellations through the recorded-live CLI."""
import asyncio

import httpx
import pytest

from scripts.findings_quality import main
from scripts.findings_quality_io import json_bytes, read_json
from scripts.findings_quality_live import (
    MODEL,
    RUBRIC_VERSION,
    _calibration_inputs,
    capture_experiment,
    record_judgment,
)
from scripts.findings_quality_transport import BoundedChat, ChatBudget


def _cancelled_capture(output, kind):
    budget = ChatBudget(12, 480_000, 24_576, 40_000, 2_048, 120, 480_000)
    approval = "a" * 64
    calibration = _calibration_inputs()
    calls = []

    async def capture():
        in_transport = asyncio.Event()

        async def wait_for_cancel(request):
            calls.append(request)
            in_transport.set()
            await asyncio.Future()

        async with BoundedChat(
            opt_in=True, approval_id=approval, proposal_sha256=approval, budget=budget,
            receipt_dir=output / "receipts", transport=httpx.MockTransport(wait_for_cancel),
            key_loader=lambda: "scripted",
        ) as chat:
            if kind == "generation":
                attempt = capture_experiment(chat, output)
            else:
                (output / "manifest.json").write_bytes(json_bytes({
                    "schema_version": "dra.findings-quality.captured-live.v1",
                    "proposal_sha256": approval, "execution_mode": "scripted", "model": MODEL,
                    "rubric_version": RUBRIC_VERSION, "calibration_inputs": sorted(calibration),
                    "planned_arms": ["A", "B"],
                }))
                identity = min(calibration)
                attempt = record_judgment(
                    chat, calibration[identity], output / f"judge-{identity}.json",
                    request_id=f"judge.{identity}", basis="scripted_fixture",
                )
            task = asyncio.create_task(attempt)
            await asyncio.wait_for(in_transport.wait(), timeout=3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(capture())
    assert len(calls) == 1
    assert not (output / "generation-A.json").exists()
    assert not (output / "generation-B.json").exists()
    assert not list(output.glob("judge-*.json"))
    return read_json(output / "receipts/0001-result.json")


@pytest.mark.parametrize("kind", ["generation", "judge"])
def test_replay_counts_cancelled_transport_without_stop_record(tmp_path, kind):
    captured = _cancelled_capture(tmp_path, kind)
    assert captured["status"] == "cancelled"
    output = tmp_path / "replay"
    assert main(["replay", "--recorded-live", str(tmp_path), "--output-dir", str(output)]) == 0
    report = read_json(output / "report.json")

    if kind == "generation":
        arm = report["generation"]["pairs"][0]["A"]
        assert arm["started"] is True
        assert arm["outcome"] == "cancelled"
        assert report["generation"]["pairs"][0]["B"]["outcome"] == "not_started"
        resources = arm["resources"]
        aggregate = report["generation"]["resources"]
    else:
        case, = [row for row in report["cases"] if row["outcome"] == "judge_cancelled"]
        assert case["verdict"] is None
        assert case["judge"]["judgment"] is None
        resources = case["judge"]["resources"]
        aggregate = report["evaluator_resources"]

    assert resources == {
        "calls": 1, "input_tokens": None, "output_tokens": None,
        "estimated_microusd": None, "elapsed_seconds": captured["elapsed_ms"] / 1000,
    }
    assert aggregate["calls"]["total"] == 1
    assert aggregate["calls"]["observed"] == 1
    assert aggregate["input_tokens"]["total"] is None
    assert aggregate["output_tokens"]["total"] is None
    assert aggregate["estimated_microusd"]["total"] is None


def test_replay_rejects_cancelled_result_from_another_attempt(tmp_path):
    _cancelled_capture(tmp_path, "generation")
    (tmp_path / "receipts/0001-result.json").rename(tmp_path / "receipts/0002-result.json")

    output = tmp_path / "replay"
    assert main(["replay", "--recorded-live", str(tmp_path), "--output-dir", str(output)]) == 1
    assert not (output / "report.json").exists()


def test_replay_does_not_infer_cancellation_from_start_marker(tmp_path):
    _cancelled_capture(tmp_path, "generation")
    (tmp_path / "receipts/0001-result.json").unlink()

    output = tmp_path / "replay"
    assert main(["replay", "--recorded-live", str(tmp_path), "--output-dir", str(output)]) == 0
    report = read_json(output / "report.json")
    arm = report["generation"]["pairs"][0]["A"]
    assert arm["started"] is True
    assert arm["outcome"] == "report_absent"
    assert arm["resources"]["calls"] == 1
    assert arm["resources"]["elapsed_seconds"] is None
