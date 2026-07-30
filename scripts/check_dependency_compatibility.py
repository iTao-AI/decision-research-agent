#!/usr/bin/env python3
"""Fail-closed compatibility gate for the exact no-deps release lock."""

from __future__ import annotations

import json
import re
import subprocess
import sys


MAX_CAPTURE_BYTES = 8_192
APPROVED_RAGFLOW_DIAGNOSTIC = (
    "ragflow-sdk",
    "0.13.0",
    frozenset({"pytest<9.0.0", "pytest>=8.0.0"}),
    "pytest",
    "9.0.3",
)
_DIAGNOSTIC = re.compile(
    r"^(?P<owner>ragflow-sdk) (?P<owner_version>0\.13\.0) has requirement "
    r"pytest(?P<first><9\.0\.0|>=8\.0\.0),(?P<second><9\.0\.0|>=8\.0\.0), "
    r"but you have (?P<installed>pytest) (?P<installed_version>9\.0\.3)\.$"
)


class DependencyCompatibilityError(RuntimeError):
    """The pip diagnostic was not one of the two approved closed outcomes."""


def decode_output(value: bytes) -> str:
    if len(value) > MAX_CAPTURE_BYTES:
        raise DependencyCompatibilityError("dependency diagnostic is invalid")
    try:
        return value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DependencyCompatibilityError("dependency diagnostic is invalid") from exc


def parse_pip_check(stdout: str, stderr: str, returncode: int) -> tuple[str, ...]:
    if stderr or len(stdout.encode("utf-8")) > MAX_CAPTURE_BYTES:
        raise DependencyCompatibilityError("dependency diagnostic is invalid")
    lines = stdout.splitlines()
    if returncode == 0 and lines == ["No broken requirements found."]:
        return ("clean",)
    if returncode != 1 or len(lines) != 1:
        raise DependencyCompatibilityError("dependency diagnostic is invalid")
    match = _DIAGNOSTIC.fullmatch(lines[0])
    if match is None:
        raise DependencyCompatibilityError("dependency diagnostic is invalid")
    requirements = frozenset(
        {f"pytest{match.group('first')}", f"pytest{match.group('second')}"}
    )
    actual = (
        match.group("owner"),
        match.group("owner_version"),
        requirements,
        match.group("installed"),
        match.group("installed_version"),
    )
    if actual != APPROVED_RAGFLOW_DIAGNOSTIC:
        raise DependencyCompatibilityError("dependency diagnostic is invalid")
    return (
        "approved_diagnostic",
        actual[0],
        actual[1],
        actual[3],
        actual[4],
    )


def main() -> int:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        result = parse_pip_check(
            decode_output(completed.stdout),
            decode_output(completed.stderr),
            completed.returncode,
        )
    except (DependencyCompatibilityError, subprocess.SubprocessError):
        print(json.dumps({"status": "rejected"}, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps({"status": result[0]}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
