import subprocess

from scripts.durable_hitl_gate_runner import (
    _pytest_gate_passed,
    build_report,
)


def test_gate_report_is_no_go_when_any_gate_fails():
    report = build_report(
        {f"gate_{number:02d}": number != 13 for number in range(1, 14)}
    )

    assert report["status"] == "NO_GO"
    assert report["passed"] == 12
    assert report["failed"] == ["gate_13"]


def test_gate_report_passes_only_all_thirteen():
    report = build_report(
        {f"gate_{number:02d}": True for number in range(1, 14)}
    )

    assert report["status"] == "PASS"
    assert report["passed"] == 13
    assert report["failed"] == []


def test_pytest_skip_never_counts_as_gate_pass():
    completed = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="1 skipped in 0.01s",
        stderr="",
    )

    assert _pytest_gate_passed(completed) is False
