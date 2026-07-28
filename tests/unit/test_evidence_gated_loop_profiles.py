from __future__ import annotations

import json
import subprocess

import pytest

import scripts.evidence_gated_loop_profiles as profiles
from scripts.evidence_gated_loop_contracts import (
    REGISTRY_PATH,
    LoopContractError,
    VerificationProfileRef,
    load_registry,
    validate_registry,
)
from scripts.evidence_gated_loop_profiles import (
    CONTEXT_ARGV,
    CONTEXT_EPISODE_BINDINGS,
    EVALUATION_ARGV,
    EVALUATION_EPISODE_BINDINGS,
    PROFILE_REGISTRY,
    STRICT_ARGV,
    STRICT_EPISODE_BINDINGS,
    TOTAL_VERIFICATION_TIMEOUT_SECONDS,
    LoopProfileError,
    VerificationResult,
    run_required_profiles,
    run_verification_profile,
)


def test_profile_registry_owns_exact_commands_timeout_and_coverage() -> None:
    assert list(PROFILE_REGISTRY) == [
        ("context-resolver-coherence", "1"),
        ("evaluation-sensitivity", "1"),
        ("strict-citation-consumer", "1"),
    ]
    assert PROFILE_REGISTRY[("context-resolver-coherence", "1")].argv == CONTEXT_ARGV
    assert PROFILE_REGISTRY[("evaluation-sensitivity", "1")].argv == EVALUATION_ARGV
    assert PROFILE_REGISTRY[("strict-citation-consumer", "1")].argv == STRICT_ARGV
    assert [profile.episode_bindings for profile in PROFILE_REGISTRY.values()] == [
        CONTEXT_EPISODE_BINDINGS,
        EVALUATION_EPISODE_BINDINGS,
        STRICT_EPISODE_BINDINGS,
    ]
    assert [profile.timeout_seconds for profile in PROFILE_REGISTRY.values()] == [
        120,
        300,
        180,
    ]
    assert TOTAL_VERIFICATION_TIMEOUT_SECONDS == 420
    assert all(
        profile.coverage
        == ("fail_to_pass", "retained", "safety_compatibility")
        for profile in PROFILE_REGISTRY.values()
    )


def test_manifest_bytes_cannot_override_profile_command() -> None:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    value["verification_profiles"][0]["argv"] = ["python", "-c", "pass"]
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        validate_registry(value)


def test_unknown_profile_fails_closed_without_subprocess(monkeypatch) -> None:
    calls = []

    def unexpected_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    with pytest.raises(
        LoopProfileError, match="loop_verification_profile_invalid"
    ):
        run_verification_profile(
            VerificationProfileRef(profile_id="unknown", profile_version="1")
        )
    assert calls == []


def test_runner_uses_shell_false_fixed_cwd_devnull_and_minimal_env(
    monkeypatch, tmp_path
) -> None:
    observed = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read-or-copied")

    def fake_run(argv, **kwargs):
        observed.update(argv=tuple(argv), **kwargs)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_verification_profile(
        VerificationProfileRef(
            profile_id="context-resolver-coherence", profile_version="1"
        ),
        project_root=tmp_path,
    )
    assert result.status == "passed"
    assert observed["shell"] is False
    assert observed["cwd"] == tmp_path
    assert observed["stdout"] is subprocess.DEVNULL
    assert observed["stderr"] is subprocess.DEVNULL
    assert observed["env"]["PYTHON_DOTENV_DISABLED"] == "1"
    assert observed["env"]["LANGCHAIN_TRACING_V2"] == "false"
    assert observed["env"]["PYTHONHASHSEED"] == "0"
    assert "OPENAI_API_KEY" not in observed["env"]


def test_required_profiles_run_once_in_registry_order(monkeypatch) -> None:
    calls = []

    def fake_run(ref, **kwargs):
        calls.append((ref.profile_id, ref.profile_version))
        return VerificationResult(
            profile_id=ref.profile_id,
            profile_version=ref.profile_version,
            provider_free=True,
            status="passed",
            coverage=["fail_to_pass", "retained", "safety_compatibility"],
            diagnostic_code="loop_verification_passed",
        )

    monkeypatch.setattr(profiles, "run_verification_profile", fake_run)
    results = run_required_profiles(load_registry())
    assert calls == [
        ("context-resolver-coherence", "1"),
        ("evaluation-sensitivity", "1"),
        ("strict-citation-consumer", "1"),
    ]
    assert [result.profile_id for result in results] == [
        "context-resolver-coherence",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess(("python",), 1),
        subprocess.TimeoutExpired(("python",), 1),
        OSError("private host detail"),
    ],
)
def test_runner_maps_all_failures_without_raw_output(
    monkeypatch, capsys, outcome
) -> None:
    def fail(*args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(LoopProfileError, match="loop_verification_failed"):
        run_verification_profile(
            VerificationProfileRef(
                profile_id="context-resolver-coherence", profile_version="1"
            )
        )
    assert capsys.readouterr() == ("", "")
