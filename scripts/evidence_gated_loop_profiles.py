from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

from pydantic import Field

from scripts.evidence_gated_loop_contracts import (
    PROJECT_ROOT,
    LoopRegistry,
    VerificationProfileRef,
    _StrictModel,
)


TOTAL_VERIFICATION_TIMEOUT_SECONDS = 420
_COVERAGE = ("fail_to_pass", "retained", "safety_compatibility")

CONTEXT_ARGV = (
    sys.executable,
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projects_production_coherent_resolver_errors",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projection_rejects_unknown_persisted_terminal_status",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projection_rejects_resolver_error_incompatible_with_persisted_state",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projects_resolver_error_without_problem_or_fix",
)
EVALUATION_ARGV = (
    sys.executable,
    "scripts/agent_evaluation_v2_gate.py",
    "check",
)
STRICT_ARGV = (
    sys.executable,
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_initial_success_uses_zero_correction_calls",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_correction_success_calls_once_and_persists_exact_url",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_failures_are_closed_and_retain_only_safe_state",
    "tests/integration/test_strict_citation_profile.py::"
    "test_post_insertion_zero_citation_fails_once_without_retry",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_profile_uses_existing_identity_and_manifest_surfaces",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_resolver_rejects_nonexact_persisted_profile_version",
    "tests/integration/test_strict_citation_profile.py::"
    "test_literal_generic_zero_citation_remains_ready_without_correction",
    "tests/integration/test_downstream_consumer_contract.py::"
    "test_committed_fixture_matches_fresh_build",
    "tests/integration/test_evidence_gated_loop_gate.py::"
    "test_frozen_generic_downstream_fixture_rejects_strict_profile",
    "tests/unit/test_v0_1_6_release_metadata.py::"
    "test_v0_1_6_version_identity_is_consistent",
)
CONTEXT_EPISODE_BINDINGS = (
    ("context-resolver-projection", "context-projection-episode-1"),
)
EVALUATION_EPISODE_BINDINGS = (
    ("evaluation-sensitivity", "evaluation-sensitivity-episode-1"),
)
STRICT_EPISODE_BINDINGS = (
    ("strict-citation-consumer", "strict-citation-change-episode-1"),
    ("strict-citation-consumer", "strict-citation-consumer-close-episode-2"),
)


class LoopProfileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerificationProfile:
    profile_id: str
    profile_version: str
    episode_bindings: Sequence[tuple[str, str]]
    argv: Sequence[str]
    timeout_seconds: int
    coverage: Sequence[
        Literal["fail_to_pass", "retained", "safety_compatibility"]
    ]
    failure_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_bindings", tuple(self.episode_bindings))
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "coverage", tuple(self.coverage))


class VerificationResult(_StrictModel):
    profile_id: str
    profile_version: str
    provider_free: Literal[True]
    status: Literal["passed"]
    coverage: list[
        Literal["fail_to_pass", "retained", "safety_compatibility"]
    ] = Field(min_length=3, max_length=3)
    diagnostic_code: Literal["loop_verification_passed"]


PROFILE_REGISTRY: Mapping[tuple[str, str], VerificationProfile] = {
    ("context-resolver-coherence", "1"): VerificationProfile(
        "context-resolver-coherence",
        "1",
        CONTEXT_EPISODE_BINDINGS,
        CONTEXT_ARGV,
        120,
        _COVERAGE,
        "loop_verification_failed",
    ),
    ("evaluation-sensitivity", "1"): VerificationProfile(
        "evaluation-sensitivity",
        "1",
        EVALUATION_EPISODE_BINDINGS,
        EVALUATION_ARGV,
        300,
        _COVERAGE,
        "loop_verification_failed",
    ),
    ("strict-citation-consumer", "1"): VerificationProfile(
        "strict-citation-consumer",
        "1",
        STRICT_EPISODE_BINDINGS,
        STRICT_ARGV,
        180,
        _COVERAGE,
        "loop_verification_failed",
    ),
}


def _subprocess_environment() -> dict[str, str]:
    value = {
        "PYTHON_DOTENV_DISABLED": "1",
        "LANGCHAIN_TRACING_V2": "false",
        "PYTHONHASHSEED": "0",
    }
    for key in ("PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR"):
        if key in os.environ:
            value[key] = os.environ[key]
    return value


def run_verification_profile(
    ref: VerificationProfileRef,
    *,
    project_root: Path = PROJECT_ROOT,
    timeout_seconds: float | None = None,
) -> VerificationResult:
    profile = PROFILE_REGISTRY.get((ref.profile_id, ref.profile_version))
    if profile is None:
        raise LoopProfileError("loop_verification_profile_invalid")
    timeout = float(profile.timeout_seconds)
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            raise LoopProfileError("loop_verification_failed")
        timeout = min(timeout, timeout_seconds)
    try:
        completed = subprocess.run(
            profile.argv,
            shell=False,
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
            env=_subprocess_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        raise LoopProfileError("loop_verification_failed") from None
    if completed.returncode != 0:
        raise LoopProfileError("loop_verification_failed")
    return VerificationResult(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        provider_free=True,
        status="passed",
        coverage=list(profile.coverage),
        diagnostic_code="loop_verification_passed",
    )


def run_required_profiles(
    registry: LoopRegistry,
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[VerificationResult, ...]:
    started = time.monotonic()
    results: list[VerificationResult] = []
    seen: set[tuple[str, str]] = set()
    for ref in registry.verification_profiles:
        identity = (ref.profile_id, ref.profile_version)
        if identity in seen:
            raise LoopProfileError("loop_verification_profile_invalid")
        seen.add(identity)
        profile = PROFILE_REGISTRY.get(identity)
        if profile is None:
            raise LoopProfileError("loop_verification_profile_invalid")
        remaining = TOTAL_VERIFICATION_TIMEOUT_SECONDS - (
            time.monotonic() - started
        )
        if remaining <= 0:
            raise LoopProfileError("loop_verification_failed")
        results.append(
            run_verification_profile(
                ref,
                project_root=project_root,
                timeout_seconds=min(float(profile.timeout_seconds), remaining),
            )
        )
    return tuple(results)
