from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

from scripts.report_runtime_versions import RUNTIME_PACKAGES


ROOT = Path(__file__).resolve().parents[2]


def _applicable_constraints() -> dict[str, str]:
    constraints: dict[str, str] = {}
    environment = default_environment()
    for raw_line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        pinned_versions = [
            specifier.version
            for specifier in requirement.specifier
            if specifier.operator == "=="
        ]
        if pinned_versions:
            constraints[canonicalize_name(requirement.name)] = pinned_versions[-1]
    return constraints


def test_report_runtime_versions_outputs_stable_json():
    completed = subprocess.run(
        [sys.executable, "scripts/report_runtime_versions.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    report = json.loads(completed.stdout)

    assert set(report) == {"python", *RUNTIME_PACKAGES}
    assert report["python"].count(".") >= 1


def test_runtime_packages_match_constraints():
    constraints = _applicable_constraints()

    missing = [
        package_name
        for package_name in RUNTIME_PACKAGES
        if canonicalize_name(package_name) not in constraints
    ]

    assert missing == []
    for package_name in RUNTIME_PACKAGES:
        assert version(package_name) == constraints[canonicalize_name(package_name)]


def test_constraints_pin_runtime_packages_exactly():
    constraints = _applicable_constraints()

    for package_name in RUNTIME_PACKAGES:
        specifier = SpecifierSet(f"=={constraints[canonicalize_name(package_name)]}")
        assert version(package_name) in specifier
