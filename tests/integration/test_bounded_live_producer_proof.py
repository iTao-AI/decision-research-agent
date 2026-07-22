from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from api.run_failure_cause_models import RUN_FAILURE_CAUSE_CODES
from scripts.bounded_live_producer_contracts import (
    BOUNDARIES,
    LIMITS,
    CleanupReceipt,
    CleanupStatus,
    EvaluationError,
    LiveReportModel,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticStage,
    RunFailureDiagnostic,
)
from scripts.bounded_live_producer_diagnostics import DIAGNOSTIC_FILENAME
from scripts.bounded_live_producer_http import CreateAmbiguous, HttpObservation
from scripts.bounded_live_producer_proof import (
    TerminalSnapshot,
    compare_restart,
    main,
    observe_terminal,
    observe_usage,
    project_live_observation,
    publish_paired_output,
    reconcile_create,
    run_cleanup_guarded,
    run_provider_free_check,
    validate_replay,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    PROJECT_ROOT / "benchmarks" / "bounded-live-producer-v1" / "manifest.json"
)
ARTIFACT_TEXT = "# Free-threaded CPython pilot\n\nBounded public-source brief.\n"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT_TEXT.encode("utf-8")).hexdigest()


class _FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _install_provider_free_live_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_preclaim: bool = False,
    fail_cleanup_refresh: bool = False,
    publication_error: BaseException | None = None,
    clock: _FakeMonotonic | None = None,
    configuration_seconds: float = 0.0,
    snapshot_seconds: float = 0.0,
    cleanup_seconds: float = 0.0,
    publication_seconds: float = 0.0,
    pre_guard_failure: str | None = None,
    fail_pre_guard_cleanup: bool = False,
    secure_check_error: BaseException | None = None,
    terminal_error: EvaluationError | None = None,
    diagnostic_dir: Path | None = None,
    diagnostic_publication_error: BaseException | None = None,
    configuration_close_error: BaseException | None = None,
):
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    lifecycle = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    repository = tmp_path / "repository"
    manifest_path = (
        repository / "benchmarks/bounded-live-producer-v1/manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(MANIFEST_PATH.read_bytes())
    (repository / "docs/evidence").mkdir(parents=True)
    env_file = tmp_path / "external-live.env"
    env_file.write_text("fixture-only\n", encoding="utf-8")
    events: list[str] = []
    holder: dict[str, Any] = {}
    if fail_pre_guard_cleanup:
        real_rmtree = module.shutil.rmtree
        holder["real_rmtree"] = real_rmtree

        def fail_task_temp_cleanup(path: Path, *args: Any, **kwargs: Any) -> None:
            task_temp = holder.get("task_temp")
            if task_temp is not None and Path(path).resolve() == task_temp.resolve():
                raise OSError("private pre-guard cleanup failure")
            real_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(module.shutil, "rmtree", fail_task_temp_cleanup)
    if clock is not None:
        monkeypatch.setattr(module.time, "monotonic", clock)

    class FakeConfiguration(dict):
        def close(self) -> None:
            events.append("configuration_close")
            if configuration_close_error is not None:
                raise configuration_close_error

    def load_configuration(
        _env_file: Path,
        declaration: Any,
        *,
        process_api_key: str,
        repository_root: Path,
    ) -> FakeConfiguration:
        events.append("configuration")
        if clock is not None:
            clock.advance(configuration_seconds)
        assert declaration.provider_id == "approved-provider"
        assert process_api_key == ""
        assert repository_root == repository
        return FakeConfiguration()

    def run_subprocess(arguments, **_kwargs):
        events.append("probe:" + " ".join(arguments[1:3]))
        if pre_guard_failure == "probe":
            raise EvaluationError("docker_unavailable", "docker", False)
        value = "28.0.0\n" if arguments[1] == "version" else "2.39.0\n"
        return subprocess.CompletedProcess(arguments, 0, value, "")

    def prepare_snapshot(
        checkout_root: Path,
        task_temp_parent: Path,
        **_kwargs,
    ) -> Any:
        events.append("snapshot")
        assert checkout_root == repository
        assert _kwargs["verify_secure_runtime"] is False
        holder["required_paths"] = tuple(_kwargs["required_paths"])
        task_temp_parent.mkdir()
        holder["task_temp"] = task_temp_parent
        if clock is not None:
            clock.advance(snapshot_seconds)
        if pre_guard_failure == "snapshot":
            raise EvaluationError("source_archive_invalid", "docker", False)
        return SimpleNamespace(
            root=repository,
            commit="a" * 40,
            tree="b" * 40,
            version="0.1.5",
            archive_sha256="c" * 64,
        )

    class FakeProject:
        def __init__(self, **kwargs: Any) -> None:
            events.append("project")
            if pre_guard_failure == "project":
                raise RuntimeError("private project construction failure")
            self.project_name = kwargs["project_name"]
            self._temp_paths: tuple[Path, ...] = ()
            self._project_claimed = False
            holder["project"] = self

        def track_temp_paths(self, paths) -> None:
            events.append("track_temp")
            if pre_guard_failure == "track":
                raise RuntimeError("private ownership transition failure")
            self._temp_paths = tuple(Path(path).resolve() for path in paths)

        def assert_unclaimed(self, _deadline: Any) -> None:
            events.append("assert_unclaimed")
            if fail_preclaim:
                raise EvaluationError("compose_config_invalid", "docker", False)
            self._project_claimed = True

        def _invoke(self, arguments, _deadline, **_kwargs):
            events.append("invoke:" + " ".join(arguments[:3]))
            if tuple(arguments[:3]) == ("config", "--format", "json"):
                return subprocess.CompletedProcess(arguments, 0, "{}", "")
            if tuple(arguments[:3]) == ("docker", "image", "inspect"):
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    "sha256:" + "d" * 64 + "\n",
                    "",
                )
            return subprocess.CompletedProcess(arguments, 0, "", "")

        def build_backend(self, _deadline: Any) -> None:
            events.append("build")

        def verify_snapshot_secure_runtime(self, deadline: Any) -> None:
            events.append("secure_check")
            assert deadline.code.value == "source_archive_invalid"
            assert deadline.phase.value == "docker"
            if secure_check_error is not None:
                raise secure_check_error

        def start_mysql(self, _deadline: Any) -> None:
            events.append("start_mysql")

        def start_backend(self, _deadline: Any) -> None:
            events.append("start_backend")

    resource_refreshes = 0

    def refresh_resources(project: Any, _deadline: Any) -> None:
        nonlocal resource_refreshes
        resource_refreshes += 1
        events.append(f"resource_refresh:{resource_refreshes}")
        if fail_cleanup_refresh and resource_refreshes == 3:
            raise RuntimeError("private refresh failure")

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            events.append("client")

        def usage(self, **_kwargs: Any) -> dict[str, Any]:
            events.append("usage")
            return {
                "total_prompt": 10,
                "total_completion": 5,
                "total_tokens": 15,
                "total_cost": 0.125,
                "call_count": 1,
            }

        def create(self, **_kwargs: Any) -> dict[str, Any]:
            events.append("replay_create")
            return _create_ack(replay=True)

    client = FakeClient()

    def reconcile(_client: Any, *, request_bytes: bytes, key: str) -> dict[str, Any]:
        events.append("create")
        request = json.loads(request_bytes)
        assert key.startswith("proof-key-")
        return {
            "run_id": "run-proof-1",
            "thread_id": request["thread_id"],
            "segment_id": "segment-proof-1",
            "idempotent_replay": False,
        }

    def terminal(*_args, **_kwargs):
        events.append("terminal")
        if terminal_error is not None:
            raise terminal_error
        return _snapshot(), _status(), _result()

    def restart(*_args, **_kwargs):
        events.append("restart")
        return client

    def cleanup(project: Any, _deadline: Any) -> dict[str, bool]:
        events.append("cleanup_receipt")
        if clock is not None:
            clock.advance(cleanup_seconds)
        for path in project._temp_paths:
            shutil.rmtree(path)
        return {
            "attempted": True,
            "succeeded": True,
            "zero_unapproved_containers": True,
            "zero_unapproved_volumes": True,
            "zero_unapproved_networks": True,
            "zero_temp_residue": True,
        }

    monkeypatch.setattr(lifecycle, "load_live_configuration", load_configuration)
    monkeypatch.setattr(lifecycle, "run_bounded_subprocess", run_subprocess)
    monkeypatch.setattr(lifecycle, "prepare_source_snapshot", prepare_snapshot)
    monkeypatch.setattr(lifecycle, "ManagedComposeProject", FakeProject)
    monkeypatch.setattr(lifecycle, "sanitize_compose_projection", lambda _value: {})
    monkeypatch.setattr(lifecycle, "cleanup_receipt", cleanup)
    monkeypatch.setattr(module, "_project_resource_ids", refresh_resources)
    monkeypatch.setattr(module, "_loopback_port", lambda *_args, **_kwargs: 18000)
    monkeypatch.setattr(module, "_wait_for_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "ProofHttpClient", FakeClient)
    monkeypatch.setattr(module, "reconcile_create", reconcile)
    monkeypatch.setattr(module, "observe_terminal", terminal)
    monkeypatch.setattr(module, "restart_backend_transport", restart)
    real_diagnostic_publish = module.publish_result_diagnostic

    def diagnostic_publish(*args, **kwargs):
        events.append("diagnostic_publish")
        if diagnostic_publication_error is not None:
            raise diagnostic_publication_error
        return real_diagnostic_publish(*args, **kwargs)

    monkeypatch.setattr(module, "publish_result_diagnostic", diagnostic_publish)
    if publication_error is not None:
        def fail_publication(*_args, **_kwargs):
            raise publication_error

        monkeypatch.setattr(module, "publish_paired_output", fail_publication)
    elif clock is not None and publication_seconds:
        publish = module.publish_paired_output

        def advance_then_publish(*args, **kwargs):
            events.append("publication")
            clock.advance(publication_seconds)
            return publish(*args, **kwargs)

        monkeypatch.setattr(module, "publish_paired_output", advance_then_publish)

    def invoke() -> Any:
        return module.observe_live(
            env_file=env_file,
            provider_id="approved-provider",
            provider_base_url="https://provider.example/v1",
            primary_model_id="approved-model",
            fallback_model_id="approved-model",
            diagnostic_dir=diagnostic_dir,
            repository_root=repository,
        )

    return invoke, repository, events, holder


def _evidence(
    evidence_id: str,
    source_url: str,
    *,
    citation_status: str = "cited",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "run_id": "run-proof-1",
        "segment_id": "segment-proof-1",
        "query_text": "must-not-be-published",
        "subagent_name": "researcher",
        "tool_name": "search",
        "source_url": source_url,
        "source_identity": source_url,
        "snippet": "must-not-be-published",
        "evidence_fingerprint": "a" * 64,
        "retrieved_at": "2026-07-18T00:00:00+00:00",
        "tool_call_id": "tool-1",
        "citation_status": citation_status,
        "verification_status": "unverified",
        "created_at": "2026-07-18T00:00:00+00:00",
    }


def test_project_resource_ids_uses_full_docker_identity_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    calls: list[tuple[str, ...]] = []
    merged: dict[str, tuple[str, ...]] = {}

    class Project:
        project_name = "dra-proof-26262626262626262626262626262626"

        def _invoke(self, arguments, _deadline, **_kwargs):
            calls.append(tuple(arguments))
            resource = arguments[1]
            if resource == "container":
                output = "a" * 64 + "\n"
            elif resource == "volume":
                output = f"{self.project_name}_data\n"
            else:
                output = "b" * 64 + "\n"
            return subprocess.CompletedProcess(arguments, 0, output, "")

        def merge_resource_ownership(self, **values: tuple[str, ...]) -> None:
            merged.update(values)

    module._project_resource_ids(
        Project(),
        SimpleNamespace(code="service_identity_invalid", phase="docker"),
    )
    container_call = next(call for call in calls if call[1] == "container")
    network_call = next(call for call in calls if call[1] == "network")
    assert "--no-trunc" in container_call
    assert "--no-trunc" in network_call
    assert merged["container_ids"] == ("a" * 64,)
    assert merged["network_ids"] == ("b" * 64,)


@pytest.mark.parametrize("resource", ["container", "network"])
def test_project_resource_ids_rejects_short_docker_identity(
    monkeypatch: pytest.MonkeyPatch,
    resource: str,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    class Project:
        project_name = "dra-proof-27272727272727272727272727272727"

        def _invoke(self, arguments, _deadline, **_kwargs):
            current = arguments[1]
            if current == "volume":
                output = f"{self.project_name}_data\n"
            elif current == resource:
                output = "a" * 12 + "\n"
            else:
                output = "b" * 64 + "\n"
            return subprocess.CompletedProcess(arguments, 0, output, "")

        def merge_resource_ownership(self, **_values: tuple[str, ...]) -> None:
            pytest.fail("short Docker identity reached ownership receipt")

    with pytest.raises(EvaluationError) as raised:
        module._project_resource_ids(
            Project(),
            SimpleNamespace(code="service_identity_invalid", phase="docker"),
        )
    assert raised.value.code.value == "service_identity_invalid"


def _status(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-proof-1",
        "thread_id": "thread-proof-1",
        "profile_id": "generic",
        "query": "must-not-be-published",
        "scope": {},
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "state_version": 2,
        "failure_cause": None,
        "segments": [
            {
                "segment_id": "segment-proof-1",
                "run_id": "run-proof-1",
                "kind": "initial",
                "sequence": 0,
                "attempt": 1,
                "status": "completed",
                "created_at": "2026-07-18T00:00:00+00:00",
                "updated_at": "2026-07-18T00:01:00+00:00",
            }
        ],
        "evidence": [
            _evidence("ev-python-docs", "https://docs.python.org/3/howto/free-threading-python.html"),
            _evidence("ev-pep-703", "https://peps.python.org/pep-0703/"),
        ],
    }
    payload.update(overrides)
    return payload


def _observed_failure_cause(
    *, phase: str = "execution", code: str = "execution_error"
) -> dict[str, Any]:
    return {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "observed",
        "phase": phase,
        "code": code,
        "recorded_at": "2026-07-22T00:00:00Z",
    }


def _result(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-proof-1",
        "execution_status": "completed",
        "delivery_status": "ready",
        "artifact": {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": ARTIFACT_TEXT,
            "content_hash": ARTIFACT_HASH,
        },
    }
    payload.update(overrides)
    return payload


def _snapshot(
    *,
    status: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> TerminalSnapshot:
    return project_live_observation(
        status_payload=status or _status(),
        result_payload=result or _result(),
        result_response_bytes=len(
            json.dumps(result or _result(), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ),
        expected_run_id="run-proof-1",
        expected_thread_id="thread-proof-1",
        expected_segment_id="segment-proof-1",
        required_cited_domains=("docs.python.org", "peps.python.org"),
    )


def _result_diagnostic_error() -> EvaluationError:
    return EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        diagnostic=ResultBoundaryDiagnostic(
            stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
            reason=ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
            http_status=200,
            response_bytes=512,
        ),
    )


def _report() -> LiveReportModel:
    observation = _snapshot()
    return LiveReportModel.model_validate(
        {
            "schema_version": "dra.bounded-live-producer-evaluation.v1",
            "status": "valid",
            "source": {
                "repository_name": "decision-research-agent",
                "service_name": "decision-research-agent",
                "version": "0.1.5",
                "source_commit": "a" * 40,
                "source_tree": "b" * 40,
                "archive_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "sanitized_compose_sha256": "e" * 64,
                "backend_image_id": "sha256:" + "f" * 64,
                "docker_version": "Docker version 28",
                "compose_version": "Docker Compose version v2",
                "source_clean": True,
                "build_context": "tracked_archive",
            },
            "scenario": {
                "scenario_id": "cpython-313-free-threaded-pilot",
                "manifest_sha256": "d" * 64,
                "request_sha256": "1" * 64,
                "profile_id": "generic",
                "required_cited_domains": ["docs.python.org", "peps.python.org"],
                "provider_id": "approved-provider",
                "primary_model_id": "approved-model",
                "fallback_model_id": "approved-model",
            },
            "lifecycle": {
                "docker_probe_ms": 1,
                "build_start_ms": 1,
                "research_ms": 1,
                "restart_replay_ms": 1,
                "active_ms": 3,
                "cleanup_ms": 1,
                "total_ms": 5,
                "loopback_binding_observed": True,
                "health_identity_observed": True,
            },
            "run": observation.run.model_dump(mode="python"),
            "result": observation.result.model_dump(mode="python"),
            "evidence": [row.model_dump(mode="python") for row in observation.evidence],
            "usage": {
                "status": "not_observed",
                "cost_estimate": {"status": "not_observed"},
                "search_cost": {"status": "not_observed"},
            },
            "restart": {
                "same_run_identity": True,
                "same_thread_identity": True,
                "same_segment_identity": True,
                "state_version_non_regressing": True,
                "same_terminal_state": True,
                "same_evidence": True,
                "same_artifact": True,
                "same_consumer_disposition": True,
            },
            "replay": {
                "idempotent_replay": True,
                "same_run_identity": True,
                "same_thread_identity": True,
                "same_segment_identity": True,
                "unchanged_terminal_projection": True,
            },
            "cleanup": {
                "attempted": True,
                "succeeded": True,
                "zero_container_residue": True,
                "zero_volume_residue": True,
                "zero_network_residue": True,
                "zero_temp_residue": True,
            },
            "boundaries": BOUNDARIES,
            "limits": list(LIMITS),
        },
        strict=True,
    )


def test_import_is_silent_and_does_not_initialize_runtime_or_docker() -> None:
    command = (
        "import json,sys; "
        "import scripts.bounded_live_producer_proof; "
        "print(json.dumps({'server': 'api.server' in sys.modules, "
        "'agent': 'agent.main_agent' in sys.modules, 'docker': 'docker' in sys.modules}, "
        "sort_keys=True, separators=(',', ':')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHON_DOTENV_DISABLED": "1"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stderr == ""
    assert result.stdout == '{"agent":false,"docker":false,"server":false}\n'


def test_provider_free_check_is_exact_and_deterministic() -> None:
    first = run_provider_free_check(manifest_path=MANIFEST_PATH)
    second = run_provider_free_check(manifest_path=MANIFEST_PATH)
    expected = {
        "mode": "provider_free",
        "schema_version": "dra.bounded-live-producer-manifest.v1",
        "status": "valid",
    }
    assert first == second == expected
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == (
        '{"mode":"provider_free","schema_version":'
        '"dra.bounded-live-producer-manifest.v1","status":"valid"}'
    )


def test_cli_check_has_exact_stdout_and_help_is_non_mutating(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        '{"mode":"provider_free","schema_version":'
        '"dra.bounded-live-producer-manifest.v1","status":"valid"}\n'
    )
    assert captured.err == ""
    for arguments in (["--help"], ["check", "--help"], ["observe-live", "--help"]):
        assert main(list(arguments)) == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert captured.err == ""


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["unknown"],
        ["check", "--extra"],
        ["check", "--diagnostic-dir", "diagnostic"],
    ],
)
def test_cli_invalid_arguments_emit_one_canonical_error_line(
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "manifest_invalid",
        "phase": "input",
        "retryable": False,
        "cleanup_status": "not_started",
    }
    assert captured.err.count("\n") == 1


class FakeCreateClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[bytes, str]] = []

    def create(self, *, request_bytes: bytes, idempotency_key: str) -> dict[str, Any]:
        self.calls.append((request_bytes, idempotency_key))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, dict)
        return outcome


def _create_ack(*, replay: bool) -> dict[str, Any]:
    return {
        "status": "started",
        "run_id": "run-proof-1",
        "thread_id": "thread-proof-1",
        "segment_id": "segment-proof-1",
        "idempotent_replay": replay,
    }


def _request_bytes() -> bytes:
    return json.dumps(
        {
            "profile_id": "generic",
            "query": "bounded query",
            "scope": {},
            "thread_id": "thread-proof-1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_new_request_uses_contract_hash_and_128_bit_thread_and_key_entropy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    manifest = module.load_manifest(MANIFEST_PATH)
    values = iter(("a" * 32, "b" * 32))
    monkeypatch.setattr(module.secrets, "token_hex", lambda size: next(values))
    request_bytes, request_hash, thread_id, key = module._new_request(manifest)
    request = json.loads(request_bytes)
    assert thread_id == "proof-thread-" + "a" * 32
    assert key == "proof-key-" + "b" * 32
    assert request == {
        "query": manifest.query,
        "thread_id": thread_id,
        "profile_id": "generic",
        "scope": {},
    }
    from api.run_creation_models import run_create_request_hash

    assert request_hash == run_create_request_hash(
        query=manifest.query,
        thread_id=thread_id,
        profile_id="generic",
        scope={},
    )
    assert request_hash != hashlib.sha256(request_bytes).hexdigest()


def test_reconcile_create_accepts_first_ack_and_preserves_object_identity() -> None:
    request_bytes = _request_bytes()
    key = "proof-key-0123456789abcdef0123456789abcdef"
    client = FakeCreateClient([_create_ack(replay=False)])
    accepted = reconcile_create(client, request_bytes=request_bytes, key=key)
    assert accepted == _create_ack(replay=False)
    assert client.calls == [(request_bytes, key)]
    assert client.calls[0][0] is request_bytes
    assert client.calls[0][1] is key


def test_reconcile_create_replays_exact_request_only_after_one_ambiguity() -> None:
    request_bytes = _request_bytes()
    key = "proof-key-0123456789abcdef0123456789abcdef"
    client = FakeCreateClient([CreateAmbiguous(), _create_ack(replay=True)])
    accepted = reconcile_create(client, request_bytes=request_bytes, key=key)
    assert accepted["idempotent_replay"] is True
    assert client.calls == [(request_bytes, key), (request_bytes, key)]
    assert all(call[0] is request_bytes and call[1] is key for call in client.calls)


def test_reconcile_create_stops_after_second_ambiguity() -> None:
    client = FakeCreateClient([CreateAmbiguous(), CreateAmbiguous()])
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            client,
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert (caught.value.code.value, caught.value.phase.value) == (
        "create_reconciliation_unresolved",
        "create",
    )
    assert len(client.calls) == 2


def test_reconcile_create_never_retries_complete_http_error() -> None:
    failure = EvaluationError("create_rejected", "create", False)
    client = FakeCreateClient([failure, _create_ack(replay=True)])
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            client,
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert caught.value is failure
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("ack", "expected_code"),
    [
        ({**_create_ack(replay=False), "thread_id": "other-thread"}, "create_identity_mismatch"),
        ({**_create_ack(replay=False), "idempotent_replay": True}, "create_response_invalid"),
        ({**_create_ack(replay=False), "extra": "field"}, "create_response_invalid"),
    ],
)
def test_reconcile_create_rejects_malformed_or_mismatched_ack(
    ack: dict[str, Any],
    expected_code: str,
) -> None:
    with pytest.raises(EvaluationError) as caught:
        reconcile_create(
            FakeCreateClient([ack]),
            request_bytes=_request_bytes(),
            key="proof-key-0123456789abcdef0123456789abcdef",
        )
    assert caught.value.code.value == expected_code


def test_project_live_observation_accepts_only_canonical_consumer_and_six_field_evidence() -> None:
    projected = _snapshot()
    assert projected.run.run_id == "run-proof-1"
    assert projected.run.segment_id == "segment-proof-1"
    assert projected.result.sha256 == ARTIFACT_HASH
    assert [row.evidence_id for row in projected.evidence] == [
        "ev-python-docs",
        "ev-pep-703",
    ]
    assert set(projected.evidence[0].model_dump()) == {
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    }
    assert "query_text" not in repr(projected)
    with pytest.raises(FrozenInstanceError):
        projected.state_version = 3  # type: ignore[misc]


def test_observe_terminal_uses_one_remaining_deadline_and_never_cancels() -> None:
    class Client:
        def __init__(self) -> None:
            self.statuses = [
                _status(execution_status="pending", delivery_status="pending"),
                _status(execution_status="running", delivery_status="pending"),
                _status(),
            ]
            self.status_calls: list[str] = []
            self.result_calls: list[str] = []

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            assert timeout_seconds == 30.0
            self.status_calls.append(run_id)
            return self.statuses.pop(0)

        def result_observation(
            self, *, run_id: str, timeout_seconds: float
        ) -> HttpObservation:
            assert timeout_seconds == 30.0
            self.result_calls.append(run_id)
            result = _result()
            return HttpObservation(
                status_code=200,
                body=result,
                response_bytes=len(
                    json.dumps(result, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ),
            )

    client = Client()
    remaining_calls: list[float] = []
    sleeps: list[float] = []

    def remaining(requested: float) -> float:
        remaining_calls.append(requested)
        return min(requested, 0.25)

    projected, status, result = observe_terminal(
        client,  # type: ignore[arg-type]
        accepted=_create_ack(replay=False),
        required_cited_domains=("docs.python.org", "peps.python.org"),
        remaining_seconds=remaining,
        sleep=sleeps.append,
    )
    assert projected.run.run_id == "run-proof-1"
    assert status["execution_status"] == "completed"
    assert result["artifact"]["content_hash"] == ARTIFACT_HASH
    assert client.status_calls == ["run-proof-1"] * 3
    assert client.result_calls == ["run-proof-1"]
    assert remaining_calls == [30.0, 1.0, 30.0, 1.0, 30.0]
    assert sleeps == [0.25, 0.25]
    assert not hasattr(client, "cancel")


@pytest.mark.parametrize(
    ("phase", "code"),
    [
        (phase, code)
        for phase, codes in RUN_FAILURE_CAUSE_CODES.items()
        for code in sorted(codes)
    ],
)
def test_observe_terminal_failure_reuses_exact_application_cause_without_result(
    phase: str, code: str
) -> None:
    class Client:
        result_calls = 0

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            return _status(
                execution_status="failed",
                delivery_status="blocked",
                failure_cause=_observed_failure_cause(phase=phase, code=code),
            )

        def result_observation(self, **_kwargs: Any) -> HttpObservation:
            self.result_calls += 1
            raise AssertionError("failed terminal state must not request result")

    client = Client()
    with pytest.raises(EvaluationError) as raised:
        observe_terminal(
            client,  # type: ignore[arg-type]
            accepted=_create_ack(replay=False),
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=lambda requested: requested,
        )

    assert raised.value.code.value == "run_failed"
    assert raised.value.phase.value == "observe"
    assert isinstance(raised.value.diagnostic, RunFailureDiagnostic)
    assert raised.value.diagnostic.phase == phase
    assert raised.value.diagnostic.code == code
    assert client.result_calls == 0


@pytest.mark.parametrize(
    "cause",
    [
        None,
        {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "not_observed",
        },
        {**_observed_failure_cause(), "recorded_at": "not-a-timestamp"},
        {
            **_observed_failure_cause(),
            "phase": "execution",
            "code": "run_finalization_failed",
        },
        {**_observed_failure_cause(), "phase": 1},
        {**_observed_failure_cause(), "unexpected": True},
        {
            key: value
            for key, value in _observed_failure_cause().items()
            if key != "recorded_at"
        },
    ],
)
def test_observe_terminal_failure_rejects_invalid_cause_without_result(
    cause: object,
) -> None:
    class Client:
        result_calls = 0

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            return _status(
                execution_status="failed",
                delivery_status="blocked",
                failure_cause=cause,
            )

        def result_observation(self, **_kwargs: Any) -> HttpObservation:
            self.result_calls += 1
            raise AssertionError("invalid failed state must not request result")

    client = Client()
    with pytest.raises(EvaluationError) as raised:
        observe_terminal(
            client,  # type: ignore[arg-type]
            accepted=_create_ack(replay=False),
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=lambda requested: requested,
        )

    assert raised.value.code.value == "run_state_invalid"
    assert raised.value.phase.value == "observe"
    assert raised.value.diagnostic is None
    assert client.result_calls == 0


@pytest.mark.parametrize(
    "status",
    [
        _status(execution_status="completed_with_fallback", delivery_status="blocked"),
        _status(execution_status="completed", delivery_status="blocked"),
        _status(execution_status="unknown", delivery_status="blocked"),
    ],
)
def test_observe_terminal_fallback_delivery_and_unknown_skip_result(
    status: dict[str, Any],
) -> None:
    class Client:
        result_calls = 0

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            return status

        def result_observation(self, **_kwargs: Any) -> HttpObservation:
            self.result_calls += 1
            raise AssertionError("ineligible terminal state must not request result")

    client = Client()
    with pytest.raises(EvaluationError):
        observe_terminal(
            client,  # type: ignore[arg-type]
            accepted=_create_ack(replay=False),
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=lambda requested: requested,
        )

    assert client.result_calls == 0


def test_observe_terminal_failure_identity_precedes_cause_classification() -> None:
    class Client:
        result_calls = 0

        def status(self, *, run_id: str, timeout_seconds: float) -> dict[str, Any]:
            return _status(
                thread_id="other-thread",
                execution_status="failed",
                delivery_status="blocked",
                failure_cause=_observed_failure_cause(),
            )

        def result_observation(self, **_kwargs: Any) -> HttpObservation:
            self.result_calls += 1
            raise AssertionError("identity failure must not request result")

    client = Client()
    with pytest.raises(EvaluationError) as raised:
        observe_terminal(
            client,  # type: ignore[arg-type]
            accepted=_create_ack(replay=False),
            required_cited_domains=("docs.python.org", "peps.python.org"),
            remaining_seconds=lambda requested: requested,
        )

    assert raised.value.code.value == "run_state_invalid"
    assert raised.value.diagnostic is None
    assert client.result_calls == 0


def test_project_live_observation_failure_identity_precedes_cause_classification() -> None:
    with pytest.raises(EvaluationError) as raised:
        project_live_observation(
            status_payload=_status(
                thread_id="other-thread",
                execution_status="failed",
                delivery_status="blocked",
                failure_cause=_observed_failure_cause(),
            ),
            result_payload=_result(),
            result_response_bytes=1,
            expected_run_id="run-proof-1",
            expected_thread_id="thread-proof-1",
            expected_segment_id="segment-proof-1",
            required_cited_domains=("docs.python.org", "peps.python.org"),
        )

    assert raised.value.code.value == "run_state_invalid"
    assert raised.value.diagnostic is None


def test_restart_backend_transport_reinspects_loopback_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    events: list[tuple[object, ...]] = []

    class Deadline:
        def remaining(self, requested: float) -> float:
            return requested

    class Project:
        def restart_backend(self, deadline: object) -> None:
            events.append(("restart", deadline))

    class Client:
        def __init__(
            self,
            *,
            port: int,
            api_key: str,
            remaining_seconds: object,
        ) -> None:
            events.append(("client", port, api_key, remaining_seconds))

        def health(self, *, timeout_seconds: float) -> dict[str, str]:
            events.append(("health", timeout_seconds))
            return {"status": "ok", "service": "decision-research-agent"}

    deadline = Deadline()
    project = Project()

    def inspect_port(
        inspected_project: object,
        service: str,
        target: int,
        inspected_deadline: object,
    ) -> int:
        events.append(
            ("port", inspected_project, service, target, inspected_deadline)
        )
        return 48001

    monkeypatch.setattr(module, "_loopback_port", inspect_port)
    monkeypatch.setattr(module, "ProofHttpClient", Client)

    client = module.restart_backend_transport(
        project,
        api_key="test-api-secret",
        deadline=deadline,
    )

    assert isinstance(client, Client)
    assert events[0] == ("restart", deadline)
    assert events[1] == ("port", project, "backend", 8000, deadline)
    assert events[2][:3] == ("client", 48001, "test-api-secret")
    assert getattr(events[2][3], "__self__", None) is deadline
    assert events[3] == ("health", 30.0)


@pytest.mark.parametrize(
    ("status", "result", "expected_code", "expected_phase"),
    [
        (
            _status(
                execution_status="failed",
                failure_cause=_observed_failure_cause(),
            ),
            _result(),
            "run_failed",
            "observe",
        ),
        (
            _status(execution_status="completed_with_fallback"),
            _result(),
            "run_fallback_rejected",
            "observe",
        ),
        (
            _status(delivery_status="blocked"),
            _result(),
            "run_delivery_not_ready",
            "observe",
        ),
        (
            _status(failure_cause={"code": "execution_error"}),
            _result(),
            "run_state_invalid",
            "observe",
        ),
        (_status(thread_id="other-thread"), _result(), "run_state_invalid", "observe"),
        (_status(segments=[]), _result(), "run_state_invalid", "observe"),
        (_status(evidence=[]), _result(), "evidence_missing", "evidence"),
        (
            _status(),
            _result(run_id="other-run"),
            "consumer_projection_invalid",
            "result",
        ),
        (
            _status(),
            {**_result(), "unexpected": True},
            "consumer_projection_invalid",
            "result",
        ),
        (
            _status(),
            _result(
                artifact={
                    **_result()["artifact"],
                    "media_type": "text/plain",
                }
            ),
            "artifact_invalid",
            "result",
        ),
        (
            _status(),
            _result(
                artifact={
                    **_result()["artifact"],
                    "kind": "research_report_fallback_markdown",
                }
            ),
            "run_fallback_rejected",
            "result",
        ),
    ],
)
def test_project_live_observation_rejects_terminal_consumer_and_identity_mutations(
    status: dict[str, Any],
    result: dict[str, Any],
    expected_code: str,
    expected_phase: str,
) -> None:
    with pytest.raises(EvaluationError) as caught:
        project_live_observation(
            status_payload=status,
            result_payload=result,
            result_response_bytes=len(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ),
            expected_run_id="run-proof-1",
            expected_thread_id="thread-proof-1",
            expected_segment_id="segment-proof-1",
            required_cited_domains=("docs.python.org", "peps.python.org"),
        )
    assert caught.value.code.value == expected_code
    assert caught.value.phase.value == expected_phase


@pytest.mark.parametrize(
    ("contract_code", "expected_code", "expected_phase", "expected_reason"),
    [
        ("contract_artifact_invalid", "artifact_invalid", "result", None),
        ("contract_state_invalid", "run_state_invalid", "observe", None),
        ("contract_evidence_invalid", "evidence_invalid", "evidence", None),
        (
            "contract_result_invalid",
            "consumer_projection_invalid",
            "result",
            "contract_result_invalid",
        ),
        (
            "contract_schema_invalid",
            "consumer_projection_invalid",
            "result",
            "contract_schema_invalid",
        ),
    ],
)
def test_project_live_observation_preserves_precise_consumer_failure_class(
    monkeypatch: pytest.MonkeyPatch,
    contract_code: str,
    expected_code: str,
    expected_phase: str,
    expected_reason: str | None,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    def fail_projection(**_kwargs: Any) -> dict[str, Any]:
        raise module.ContractValidationError(contract_code)

    monkeypatch.setattr(module, "project_consumer_case", fail_projection)

    with pytest.raises(EvaluationError) as caught:
        _snapshot()

    assert caught.value.code.value == expected_code
    assert caught.value.phase.value == expected_phase
    if expected_reason is None:
        assert caught.value.diagnostic is None
    else:
        assert caught.value.diagnostic is not None
        assert caught.value.diagnostic.stage.value == "consumer_contract"
        assert caught.value.diagnostic.reason.value == expected_reason


def test_project_live_observation_classifies_unexpected_projection_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    monkeypatch.setattr(
        module,
        "project_consumer_case",
        lambda **_kwargs: {
            "expected": {"support": "unexpected", "disposition": "unexpected"}
        },
    )

    with pytest.raises(EvaluationError) as caught:
        _snapshot()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.diagnostic is not None
    assert caught.value.diagnostic.model_dump(mode="json") == {
        "stage": "projection_disposition",
        "reason": "projection_disposition_invalid",
        "http_status": 200,
        "response_bytes": len(
            json.dumps(_result(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
    }


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda rows: [rows[0], rows[0]], "evidence_invalid"),
        (
            lambda rows: [
                {**rows[0], "source_url": "https://127.0.0.1/private"},
                rows[1],
            ],
            "evidence_invalid",
        ),
        (
            lambda rows: [
                {**rows[0], "citation_status": "uncited"},
                rows[1],
            ],
            "required_cited_domain_missing",
        ),
    ],
)
def test_project_live_observation_rejects_evidence_mutations(mutator, expected_code: str) -> None:
    status = _status()
    status["evidence"] = mutator(status["evidence"])
    with pytest.raises(EvaluationError) as caught:
        _snapshot(status=status)
    assert caught.value.code.value == expected_code


@pytest.mark.parametrize(
    "mutation",
    [
        {"run_id": "foreign-run"},
        {"segment_id": "foreign-segment"},
        {"run_id": None},
        {"segment_id": None},
    ],
)
def test_project_live_observation_rejects_foreign_or_missing_evidence_ownership(
    mutation: dict[str, Any],
) -> None:
    status = _status()
    status["evidence"][0] = {**status["evidence"][0], **mutation}
    with pytest.raises(EvaluationError) as caught:
        _snapshot(status=status)
    assert caught.value.code.value == "evidence_invalid"


def test_observe_usage_maps_absence_and_keeps_cost_unobserved_without_model_identity() -> None:
    absent = observe_usage(
        {
            "total_prompt": 0,
            "total_completion": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "call_count": 0,
        },
        primary_model_id="model-a",
        fallback_model_id="model-a",
    )
    assert absent.model_dump(mode="json") == {
        "status": "not_observed",
        "cost_estimate": {"status": "not_observed"},
        "search_cost": {"status": "not_observed"},
    }
    observed = observe_usage(
        {
            "total_prompt": 10,
            "total_completion": 5,
            "total_tokens": 15,
            "total_cost": 0.125,
            "call_count": 2,
        },
        primary_model_id="model-a",
        fallback_model_id="model-a",
        pricing_basis="operator-v1",
        currency="USD",
        pricing_identity_matches=True,
    )
    assert observed.model_dump(mode="json") == {
        "status": "observed",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "call_count": 2,
        "cost_estimate": {"status": "not_observed"},
        "search_cost": {"status": "not_observed"},
    }


def test_observe_usage_rejects_runtime_default_fallback_as_observed_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_tracking = importlib.import_module("agent.token_tracking")
    monkeypatch.setattr(
        token_tracking,
        "PRICING",
        {
            "qwen-max": {"prompt": 0.04, "completion": 0.12},
            "model-a": {"prompt": 0.001, "completion": 0.002},
        },
    )
    fallback_cost = token_tracking._calculate_cost("unknown-response-model", 10, 5)
    usage = observe_usage(
        {
            "total_prompt": 10,
            "total_completion": 5,
            "total_tokens": 15,
            "total_cost": fallback_cost,
            "call_count": 1,
        },
        primary_model_id="model-a",
        fallback_model_id="model-a",
        pricing_basis="operator-v1",
        currency="USD",
        pricing_identity_matches=True,
    )
    assert usage.status == "observed"
    assert usage.cost_estimate.status == "not_observed"


def test_observe_usage_keeps_cost_unobserved_for_model_ambiguity_or_missing_declaration() -> None:
    payload = {
        "total_prompt": 10,
        "total_completion": 5,
        "total_tokens": 15,
        "total_cost": 0.125,
        "call_count": 1,
    }
    for options in (
        {"primary_model_id": "model-a", "fallback_model_id": "model-b"},
        {"primary_model_id": "model-a", "fallback_model_id": "model-a"},
        {
            "primary_model_id": "model-a",
            "fallback_model_id": "model-a",
            "pricing_basis": "operator-v1",
            "currency": "USD",
            "pricing_identity_matches": False,
        },
    ):
        usage = observe_usage(payload, **options)
        assert usage.status == "observed"
        assert usage.cost_estimate.status == "not_observed"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_prompt": 1, "total_completion": 1, "total_tokens": 3, "total_cost": 0, "call_count": 1},
        {"total_prompt": -1, "total_completion": 1, "total_tokens": 0, "total_cost": 0, "call_count": 1},
        {"total_prompt": 0, "total_completion": 0, "total_tokens": 0, "total_cost": 0, "call_count": 1},
        {"total_prompt": 1, "total_completion": 1, "total_tokens": 2, "total_cost": float("nan"), "call_count": 1},
    ],
)
def test_observe_usage_rejects_malformed_or_inconsistent_payload(payload: dict[str, Any]) -> None:
    with pytest.raises(EvaluationError, match="usage_invalid"):
        observe_usage(
            payload,
            primary_model_id="model-a",
            fallback_model_id="model-a",
        )


def test_compare_restart_requires_identity_state_evidence_artifact_and_disposition() -> None:
    before = _snapshot()
    after = _snapshot(status=_status(state_version=3))
    receipt = compare_restart(before, after)
    assert receipt.model_dump(mode="json") == {
        "same_run_identity": True,
        "same_thread_identity": True,
        "same_segment_identity": True,
        "state_version_non_regressing": True,
        "same_terminal_state": True,
        "same_evidence": True,
        "same_artifact": True,
        "same_consumer_disposition": True,
    }


@pytest.mark.parametrize(
    ("after", "expected_code"),
    [
        (
            lambda before: replace(
                before,
                run=before.run.model_copy(update={"run_id": "run-other"}),
            ),
            "restart_identity_drift",
        ),
        (lambda _before: _snapshot(status=_status(state_version=1)), "restart_identity_drift"),
        (
            lambda _before: _snapshot(
                status=_status(
                    evidence=list(reversed(_status()["evidence"])),
                )
            ),
            "restart_evidence_drift",
        ),
        (
            lambda _before: _snapshot(
                result=_result(
                    artifact={
                        **_result()["artifact"],
                        "content": ARTIFACT_TEXT + "changed",
                        "content_hash": hashlib.sha256(
                            (ARTIFACT_TEXT + "changed").encode("utf-8")
                        ).hexdigest(),
                    }
                )
            ),
            "restart_artifact_drift",
        ),
    ],
)
def test_compare_restart_maps_drift_to_stable_codes(after, expected_code: str) -> None:
    before = _snapshot()
    with pytest.raises(EvaluationError) as caught:
        compare_restart(before, after(before))
    assert caught.value.code.value == expected_code


def test_validate_replay_requires_exact_identity_flag_and_unchanged_projection() -> None:
    before = _snapshot()
    receipt = validate_replay(_create_ack(replay=True), before=before, after=before)
    assert receipt.idempotent_replay is True
    assert receipt.unchanged_terminal_projection is True


@pytest.mark.parametrize(
    ("ack", "expected_code"),
    [
        ({**_create_ack(replay=True), "run_id": "run-other"}, "duplicate_run_observed"),
        ({**_create_ack(replay=True), "idempotent_replay": False}, "idempotent_replay_invalid"),
        ({**_create_ack(replay=True), "extra": "field"}, "idempotent_replay_invalid"),
    ],
)
def test_validate_replay_rejects_new_identity_or_malformed_ack(
    ack: dict[str, Any],
    expected_code: str,
) -> None:
    before = _snapshot()
    with pytest.raises(EvaluationError) as caught:
        validate_replay(ack, before=before, after=before)
    assert caught.value.code.value == expected_code


def _output_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "evidence").mkdir(parents=True)
    return root


def test_publish_paired_output_uses_exact_paths_and_never_overwrites(tmp_path: Path) -> None:
    root = _output_root(tmp_path)
    json_path, markdown_path = publish_paired_output(root, _report())
    assert json_path == root / "docs/evidence/bounded-live-producer-v1.json"
    assert markdown_path == root / "docs/evidence/bounded-live-producer-v1.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "valid"
    assert markdown_path.read_text(encoding="utf-8").startswith(
        "# Bounded Live Producer Evaluation v1\n"
    )
    assert not list((root / "docs/evidence").glob(".bounded-live-producer-*"))
    with pytest.raises(EvaluationError, match="output_exists"):
        publish_paired_output(root, _report())


def test_publish_paired_output_rejects_symlinked_parent_and_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs/evidence").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EvaluationError, match="output_invalid"):
        publish_paired_output(root, _report())

    root = _output_root(tmp_path / "second")
    target = root / "docs/evidence/bounded-live-producer-v1.json"
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(EvaluationError, match="output_exists"):
        publish_paired_output(root, _report())


def test_publish_paired_output_rolls_back_first_target_when_second_link_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _output_root(tmp_path)
    real_link = os.link
    calls = 0

    def fail_second_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", fail_second_link)
    with pytest.raises(EvaluationError, match="output_write_failed"):
        publish_paired_output(root, _report())
    assert list((root / "docs/evidence").iterdir()) == []


def test_publish_paired_output_rolls_back_both_targets_when_commit_fsync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _output_root(tmp_path)
    real_fsync = os.fsync
    calls = 0

    def fail_commit_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected commit fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_commit_fsync)
    with pytest.raises(EvaluationError, match="output_write_failed"):
        publish_paired_output(root, _report())
    assert list((root / "docs/evidence").iterdir()) == []


def test_publish_paired_output_removes_projection_when_rollback_unlink_fails_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _output_root(tmp_path)
    real_link = os.link
    real_unlink = os.unlink
    link_calls = 0
    failed_unlink = False

    def fail_second_link(*args, **kwargs):
        nonlocal link_calls
        link_calls += 1
        if link_calls == 2:
            raise OSError("injected second link failure")
        return real_link(*args, **kwargs)

    def fail_first_target_unlink(path, *args, **kwargs):
        nonlocal failed_unlink
        if path == "bounded-live-producer-v1.md" and not failed_unlink:
            failed_unlink = True
            raise OSError("injected rollback unlink failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "link", fail_second_link)
    monkeypatch.setattr(os, "unlink", fail_first_target_unlink)
    with pytest.raises(EvaluationError, match="output_write_failed"):
        publish_paired_output(root, _report())
    assert not (root / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (root / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_publish_paired_output_never_links_json_before_fallible_pair_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _output_root(tmp_path)
    real_link = os.link
    real_unlink = os.unlink
    real_rename = os.rename
    link_calls = 0

    def fail_second_link(*args, **kwargs):
        nonlocal link_calls
        link_calls += 1
        if link_calls == 2:
            raise OSError("injected second link failure")
        return real_link(*args, **kwargs)

    def persistently_fail_json_unlink(path, *args, **kwargs):
        if path == "bounded-live-producer-v1.json":
            raise OSError("injected persistent JSON unlink failure")
        return real_unlink(path, *args, **kwargs)

    def persistently_fail_json_rename(source, *args, **kwargs):
        if source == "bounded-live-producer-v1.json":
            raise OSError("injected persistent JSON rename failure")
        return real_rename(source, *args, **kwargs)

    monkeypatch.setattr(os, "link", fail_second_link)
    monkeypatch.setattr(os, "unlink", persistently_fail_json_unlink)
    monkeypatch.setattr(os, "rename", persistently_fail_json_rename)
    with pytest.raises(EvaluationError, match="output_write_failed"):
        publish_paired_output(root, _report())
    assert not (root / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (root / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_run_cleanup_guarded_preserves_primary_and_cleanup_causes() -> None:
    primary = EvaluationError("run_failed", "observe", False)
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail_primary():
        raise primary

    def fail_cleanup():
        raise cleanup

    with pytest.raises(ExceptionGroup) as caught:
        run_cleanup_guarded(fail_primary, fail_cleanup)
    assert caught.value.exceptions == (primary, cleanup)


def test_group_error_preserves_result_diagnostic_and_cleanup_failure() -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    primary = _result_diagnostic_error()
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    projected = module._group_error(ExceptionGroup("local-only", [primary, cleanup]))

    assert projected.code.value == "consumer_projection_invalid"
    assert projected.cleanup_status is CleanupStatus.FAILED
    assert projected.diagnostic == primary.diagnostic


def test_run_cleanup_guarded_returns_cleanup_receipt_after_success() -> None:
    receipt = CleanupReceipt(
        attempted=True,
        succeeded=True,
        zero_container_residue=True,
        zero_volume_residue=True,
        zero_network_residue=True,
        zero_temp_residue=True,
    )
    assert run_cleanup_guarded(lambda: "result", lambda: receipt) == ("result", receipt)


@pytest.mark.parametrize("primary", [RuntimeError("private"), KeyboardInterrupt()])
def test_run_cleanup_guarded_preserves_unknown_or_interrupt_with_cleanup_failure(
    primary: BaseException,
) -> None:
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail_primary():
        raise primary

    def fail_cleanup():
        raise cleanup

    with pytest.raises(BaseExceptionGroup) as caught:
        run_cleanup_guarded(fail_primary, fail_cleanup)
    assert caught.value.exceptions == (primary, cleanup)


@pytest.mark.parametrize("primary", [RuntimeError("private"), KeyboardInterrupt()])
def test_run_cleanup_guarded_maps_unknown_or_interrupt_after_successful_cleanup(
    primary: BaseException,
) -> None:
    receipt = CleanupReceipt(
        attempted=True,
        succeeded=True,
        zero_container_residue=True,
        zero_volume_residue=True,
        zero_network_residue=True,
        zero_temp_residue=True,
    )

    def fail_primary():
        raise primary

    with pytest.raises(EvaluationError) as caught:
        run_cleanup_guarded(fail_primary, lambda: receipt)
    assert caught.value.code.value == "evaluation_internal_error"
    assert caught.value.phase.value == "internal"
    assert caught.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert caught.value.__cause__ is primary


def test_main_projects_unknown_exception_without_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    def fail(**_kwargs):
        raise RuntimeError("credential-value-must-not-appear")

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "credential-value-must-not-appear" not in captured.err
    assert json.loads(captured.err)["code"] == "evaluation_internal_error"


def test_main_projects_keyboard_interrupt_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    def fail(**_kwargs):
        raise KeyboardInterrupt("private-interrupt-text")

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    try:
        result = module.main(["check"])
    except KeyboardInterrupt:
        result = None
    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-interrupt-text" not in captured.err
    assert json.loads(captured.err) == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "evaluation_internal_error",
        "phase": "internal",
        "retryable": False,
        "cleanup_status": "not_started",
    }


def test_main_projects_unknown_primary_with_cleanup_failure_as_internal_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail(**_kwargs):
        raise BaseExceptionGroup(
            "local-only",
            [KeyboardInterrupt("private"), cleanup],
        )

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "evaluation_internal_error",
        "phase": "internal",
        "retryable": False,
        "cleanup_status": "failed",
    }


def test_main_maps_malformed_live_declaration_to_credential_input_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lifecycle = importlib.import_module("scripts.bounded_live_producer_lifecycle")

    def forbidden_probe(*_args, **_kwargs):
        raise AssertionError("Docker probe must not run")

    monkeypatch.setattr(lifecycle, "run_bounded_subprocess", forbidden_probe)
    result = main(
        [
            "observe-live",
            "--env-file",
            "missing.env",
            "--provider-id",
            "invalid provider",
            "--provider-base-url",
            "https://provider.example/v1",
            "--primary-model-id",
            "model-a",
            "--fallback-model-id",
            "model-a",
        ]
    )
    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "credential_source_invalid",
        "phase": "input",
        "retryable": False,
        "cleanup_status": "not_started",
    }


def test_observe_live_runs_real_orchestrator_through_provider_free_fake_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
    )
    report = invoke()
    assert report.status == "valid"
    assert report.usage.status == "observed"
    assert report.usage.cost_estimate.status == "not_observed"
    assert events.index("configuration") < events.index("snapshot")
    assert events.index("track_temp") < events.index("assert_unclaimed")
    assert events.index("assert_unclaimed") < events.index("build")
    assert events.index("build") < events.index("secure_check")
    assert events.index("secure_check") < events.index("start_mysql")
    assert events.index("secure_check") < events.index("start_backend")
    assert events.count("terminal") == 3
    assert events.index("cleanup_receipt") > events.index("replay_create")
    assert not holder["task_temp"].exists()
    json_path = repository / "docs/evidence/bounded-live-producer-v1.json"
    markdown_path = repository / "docs/evidence/bounded-live-producer-v1.md"
    assert json_path.is_file() and markdown_path.is_file()
    public_bytes = json_path.read_bytes() + markdown_path.read_bytes()
    for forbidden in (b"must-not-be-published", b"fixture-only", b"snippet"):
        assert forbidden not in public_bytes


def test_observe_live_publishes_diagnostic_only_after_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        terminal_error=_result_diagnostic_error(),
        diagnostic_dir=diagnostic_dir,
    )

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.cleanup_status is CleanupStatus.SUCCEEDED
    receipt = diagnostic_dir / DIAGNOSTIC_FILENAME
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "schema_version": "dra.bounded-live-producer-result-diagnostic.v1",
        "primary": {
            "code": "consumer_projection_invalid",
            "phase": "result",
            "retryable": False,
            "cleanup_status": "succeeded",
        },
        "result_boundary": {
            "stage": "consumer_contract",
            "reason": "contract_result_invalid",
            "http_status": 200,
            "response_bytes": 512,
        },
    }
    assert events.index("cleanup_receipt") < events.index("diagnostic_publish")
    assert not holder["task_temp"].exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_observe_live_rejects_invalid_diagnostic_dir_before_live_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_diagnostic = tmp_path / "repository" / "diagnostic"
    repository_diagnostic.mkdir(parents=True, mode=0o700)
    repository_diagnostic.chmod(0o700)
    invoke, repository, events, _holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        diagnostic_dir=repository_diagnostic,
    )
    events.clear()

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.code.value == "output_invalid"
    assert caught.value.phase.value == "input"
    assert events == []
    assert not (repository_diagnostic / DIAGNOSTIC_FILENAME).exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()


def test_observe_live_success_or_precise_failure_produces_no_generic_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, _repository, _events, _holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        diagnostic_dir=diagnostic_dir,
    )
    assert invoke().status == "valid"
    assert not (diagnostic_dir / DIAGNOSTIC_FILENAME).exists()

    second_root = tmp_path / "second"
    second_root.mkdir()
    second_diagnostic = second_root / "diagnostic"
    second_diagnostic.mkdir(mode=0o700)
    second_diagnostic.chmod(0o700)
    invoke, _repository, _events, _holder = _install_provider_free_live_boundaries(
        second_root,
        monkeypatch,
        diagnostic_dir=second_diagnostic,
        terminal_error=EvaluationError("artifact_invalid", "result", False),
    )
    with pytest.raises(EvaluationError, match="artifact_invalid"):
        invoke()
    assert not (second_diagnostic / DIAGNOSTIC_FILENAME).exists()


def test_diagnostic_publication_failure_preserves_primary_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        diagnostic_dir=diagnostic_dir,
        terminal_error=_result_diagnostic_error(),
        diagnostic_publication_error=RuntimeError("private publication detail"),
    )

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert caught.value.diagnostic is not None
    assert events.index("cleanup_receipt") < events.index("diagnostic_publish")
    assert not holder["task_temp"].exists()
    assert not (diagnostic_dir / DIAGNOSTIC_FILENAME).exists()


def test_primary_plus_cleanup_failure_publishes_failed_cleanup_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        diagnostic_dir=diagnostic_dir,
        terminal_error=_result_diagnostic_error(),
        fail_cleanup_refresh=True,
    )

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.cleanup_status is CleanupStatus.FAILED
    receipt = json.loads(
        (diagnostic_dir / DIAGNOSTIC_FILENAME).read_text(encoding="utf-8")
    )
    assert receipt["primary"]["cleanup_status"] == "failed"
    assert events.index("cleanup_receipt") < events.index("diagnostic_publish")
    assert not holder["task_temp"].exists()


@pytest.mark.parametrize("project_cleanup_fails", [False, True])
def test_configuration_close_failure_preserves_result_diagnostic_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_cleanup_fails: bool,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        diagnostic_dir=diagnostic_dir,
        terminal_error=_result_diagnostic_error(),
        fail_cleanup_refresh=project_cleanup_fails,
        configuration_close_error=EvaluationError(
            "credential_source_invalid",
            "input",
            False,
        ),
    )

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"
    assert caught.value.cleanup_status is CleanupStatus.FAILED
    assert caught.value.diagnostic == _result_diagnostic_error().diagnostic
    receipt = json.loads(
        (diagnostic_dir / DIAGNOSTIC_FILENAME).read_text(encoding="utf-8")
    )
    assert receipt["primary"]["code"] == "consumer_projection_invalid"
    assert receipt["primary"]["cleanup_status"] == "failed"
    assert events.index("cleanup_receipt") < events.index("configuration_close")
    assert events.index("configuration_close") < events.index("diagnostic_publish")
    assert not holder["task_temp"].exists()


def test_live_snapshot_includes_diagnostic_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke, _repository, _events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
    )
    invoke()
    assert "scripts/bounded_live_producer_diagnostics.py" in holder["required_paths"]


def test_observe_live_locked_image_secure_failure_stops_before_services_and_cleans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        secure_check_error=EvaluationError(
            "source_archive_invalid",
            "docker",
            False,
        ),
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "source_archive_invalid"
    assert raised.value.phase.value == "docker"
    assert raised.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert events.index("build") < events.index("secure_check")
    assert "start_mysql" not in events
    assert "start_backend" not in events
    assert "create" not in events
    assert "cleanup_receipt" in events
    assert not holder["task_temp"].exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_observe_live_outer_deadline_blocks_probe_after_input_budget_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeMonotonic()
    invoke, repository, events, _holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        clock=clock,
        configuration_seconds=3_331.0,
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "evaluation_internal_error"
    assert raised.value.phase.value == "internal"
    assert "configuration_close" in events
    assert not any(event.startswith("probe:") for event in events)
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_observe_live_outer_deadline_blocks_post_cleanup_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeMonotonic()
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        clock=clock,
        cleanup_seconds=119.0,
        publication_seconds=3_332.0,
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "evaluation_internal_error"
    assert raised.value.phase.value == "internal"
    assert raised.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert "cleanup_receipt" in events
    assert "publication" in events
    assert not holder["task_temp"].exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


@pytest.mark.parametrize(
    ("pre_guard_failure", "snapshot_seconds", "expected_code", "has_task_temp"),
    [
        ("probe", 0.0, "docker_unavailable", False),
        ("snapshot", 0.0, "source_archive_invalid", True),
        ("project", 0.0, "evaluation_internal_error", True),
        ("track", 0.0, "evaluation_internal_error", True),
        (None, 3_331.0, "service_start_failed", True),
    ],
)
def test_observe_live_pre_guard_failure_closes_configuration_and_removes_task_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pre_guard_failure: str | None,
    snapshot_seconds: float,
    expected_code: str,
    has_task_temp: bool,
) -> None:
    clock = _FakeMonotonic()
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        clock=clock,
        snapshot_seconds=snapshot_seconds,
        pre_guard_failure=pre_guard_failure,
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == expected_code
    assert "configuration_close" in events
    assert "assert_unclaimed" not in events
    assert "cleanup_receipt" not in events
    if has_task_temp:
        assert not holder["task_temp"].exists()
    else:
        assert "task_temp" not in holder
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


def test_observe_live_pre_guard_failure_preserves_primary_and_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeMonotonic()
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        clock=clock,
        snapshot_seconds=3_331.0,
        fail_pre_guard_cleanup=True,
    )
    try:
        with pytest.raises(BaseExceptionGroup) as caught:
            invoke()
        primary, cleanup = caught.value.exceptions
        assert isinstance(primary, EvaluationError)
        assert primary.code.value == "service_start_failed"
        assert isinstance(cleanup, EvaluationError)
        assert cleanup.code.value == "cleanup_failed"
        assert cleanup.cleanup_status is CleanupStatus.FAILED
        assert "configuration_close" in events
        assert holder["task_temp"].exists()
        assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
        assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()
    finally:
        holder["real_rmtree"](holder["task_temp"])


def test_observe_live_preclaim_failure_still_cleans_temp_without_claiming_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        fail_preclaim=True,
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "compose_config_invalid"
    assert raised.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert "cleanup_receipt" in events
    assert holder["project"]._project_claimed is False
    assert not holder["task_temp"].exists()


def test_observe_live_cleanup_refresh_failure_still_executes_owned_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke, repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        fail_cleanup_refresh=True,
    )
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "cleanup_failed"
    assert raised.value.phase.value == "cleanup"
    assert raised.value.cleanup_status is CleanupStatus.FAILED
    assert "resource_refresh:3" in events
    assert "cleanup_receipt" in events
    assert not holder["task_temp"].exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.json").exists()
    assert not (repository / "docs/evidence/bounded-live-producer-v1.md").exists()


@pytest.mark.parametrize(
    "publication_error",
    [RuntimeError("private publication failure"), KeyboardInterrupt("private cancellation")],
)
def test_observe_live_post_cleanup_unknown_or_interrupt_reports_cleanup_succeeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    publication_error: BaseException,
) -> None:
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        publication_error=publication_error,
    )
    try:
        invoke()
    except BaseException as raised:
        error = raised
    else:
        pytest.fail("publication failure was not propagated")
    assert isinstance(error, EvaluationError)
    assert error.code.value == "evaluation_internal_error"
    assert error.phase.value == "internal"
    assert error.cleanup_status is CleanupStatus.SUCCEEDED
    assert "cleanup_receipt" in events
    assert not holder["task_temp"].exists()


def test_observe_live_post_cleanup_accounting_failure_is_stable_and_closes_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    invoke, _repository, events, holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
    )
    original_milliseconds = module._milliseconds

    def fail_after_cleanup(*args: Any, **kwargs: Any) -> int:
        if "cleanup_receipt" in events:
            raise RuntimeError("private accounting failure")
        return original_milliseconds(*args, **kwargs)

    monkeypatch.setattr(module, "_milliseconds", fail_after_cleanup)
    with pytest.raises(EvaluationError) as raised:
        invoke()
    assert raised.value.code.value == "evaluation_internal_error"
    assert raised.value.phase.value == "internal"
    assert raised.value.cleanup_status is CleanupStatus.SUCCEEDED
    assert "cleanup_receipt" in events
    assert "configuration_close" in events
    assert not holder["task_temp"].exists()


def test_main_projects_dual_failure_as_primary_with_failed_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    primary = EvaluationError("run_failed", "observe", False)
    cleanup = EvaluationError(
        "cleanup_failed",
        "cleanup",
        False,
        CleanupStatus.FAILED,
    )

    def fail(**_kwargs):
        raise ExceptionGroup("local-only", [primary, cleanup])

    monkeypatch.setattr(module, "run_provider_free_check", fail)
    assert module.main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "schema_version": "dra.bounded-live-producer-evaluation-error.v1",
        "code": "run_failed",
        "phase": "observe",
        "retryable": False,
        "cleanup_status": "failed",
    }


def test_live_cli_accepts_only_public_declarations_and_fixed_output_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")
    captured_arguments: dict[str, Any] = {}

    def fake_observe_live(**kwargs):
        captured_arguments.update(kwargs)
        return _report()

    monkeypatch.setattr(module, "observe_live", fake_observe_live)
    env_file = tmp_path / "live.env"
    diagnostic_dir = tmp_path / "diagnostic"
    arguments = [
        "observe-live",
        "--env-file",
        str(env_file),
        "--provider-id",
        "approved-provider",
        "--provider-base-url",
        "https://provider.example/v1",
        "--primary-model-id",
        "approved-model",
        "--fallback-model-id",
        "approved-model",
        "--diagnostic-dir",
        str(diagnostic_dir),
        "--pricing-basis",
        "operator-v1",
        "--currency",
        "USD",
        "--retain-task-images",
    ]
    assert module.main(arguments) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "mode": "live",
        "schema_version": "dra.bounded-live-producer-evaluation.v1",
        "status": "valid",
    }
    assert output.err == ""
    assert captured_arguments == {
        "env_file": env_file,
        "provider_id": "approved-provider",
        "provider_base_url": "https://provider.example/v1",
        "primary_model_id": "approved-model",
        "fallback_model_id": "approved-model",
        "diagnostic_dir": diagnostic_dir,
        "pricing_basis": "operator-v1",
        "currency": "USD",
        "retain_task_images": True,
    }
    assert not any(
        name in captured_arguments
        for name in ("query", "scope", "output", "project_name", "api_key", "retry")
    )


@pytest.mark.parametrize(
    "extra",
    [
        ["--query", "private"],
        ["--output", "report.json"],
        ["--provider-i", "abbreviated"],
        ["--pricing-basis", "operator-v1"],
        ["--currency", "USD"],
    ],
)
def test_live_cli_rejects_unapproved_or_partial_arguments(
    extra: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "observe-live",
        "--env-file",
        "live.env",
        "--provider-id",
        "approved-provider",
        "--provider-base-url",
        "https://provider.example/v1",
        "--primary-model-id",
        "model-a",
        "--fallback-model-id",
        "model-a",
        *extra,
    ]
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["phase"] == "input"


def test_container_fixture_uses_production_dispatch_fence_and_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_path = PROJECT_ROOT / "scripts/bounded_live_producer_container_fixture.py"
    assert fixture_path.is_file()
    source = fixture_path.read_text(encoding="utf-8")
    assert "start_run_dispatch" in source
    assert "finalize_run_transaction" in source
    assert "build_generic_result_artifact" in source
    assert "create_run_dispatch_worker" in source
    assert "run_deep_agent" in source
    assert "sqlite3" not in source
    assert "live evidence" not in source.lower()

    guard = subprocess.run(
        [sys.executable, str(fixture_path), "serve"],
        cwd=PROJECT_ROOT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHON_DOTENV_DISABLED": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert guard.returncode == 1
    assert guard.stdout == ""
    assert guard.stderr == '{"code":"fixture_disabled"}\n'

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE", "true")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION", "false")
    server_was_loaded = "api.server" in sys.modules
    module = importlib.import_module(
        "scripts.bounded_live_producer_container_fixture"
    )
    assert ("api.server" in sys.modules) is server_was_loaded

    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_or_replay_run, get_run
    from api.run_result_service import resolve_run_result

    db_path = str(tmp_path / "fixture.db")
    accepted = create_or_replay_run(
        db_path=db_path,
        idempotency_key="fixture-key-0123456789abcdef0123456789abcdef",
        thread_id="fixture-thread-0123456789abcdef0123456789abcdef",
        query="bounded fixture query",
        profile_id="generic",
        profile_version="1",
        scope={},
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id="dispatch_worker_" + "a" * 32,
        lease_seconds=30,
        run_id=accepted.run_id,
    )
    assert claim is not None
    worker = module.create_fixture_worker(db_path)
    worker.scheduler(claim)

    status = get_run(db_path=db_path, run_id=accepted.run_id)
    resolved = resolve_run_result(db_path=db_path, run_id=accepted.run_id)
    assert status is not None
    assert status["state_version"] == 2
    assert status["segments"][0]["status"] == "completed"
    result = {
        "run_id": resolved.run_id,
        "execution_status": resolved.execution_status,
        "delivery_status": resolved.delivery_status,
        "artifact": resolved.artifact,
    }
    projected = project_live_observation(
        status_payload=status,
        result_payload=result,
        result_response_bytes=len(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        expected_run_id=accepted.run_id,
        expected_thread_id=accepted.thread_id,
        expected_segment_id=accepted.segment_id,
        required_cited_domains=("docs.python.org", "peps.python.org"),
    )
    assert projected.result.consumer_support == "supported"
    assert [urlsplit(row.source_url).hostname for row in projected.evidence] == [
        "docs.python.org",
        "peps.python.org",
    ]
    assert "live evidence" not in resolved.artifact["content"].lower()


def test_bounded_live_producer_check_is_required_before_non_docker_ci() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    backend_steps = workflow["jobs"]["backend"]["steps"]
    check_step = {
        "name": "Run bounded live producer contract check",
        "env": {"PYTHON_DOTENV_DISABLED": "1"},
        "run": "python scripts/bounded_live_producer_proof.py check",
    }
    assert backend_steps.count(check_step) == 1
    assert backend_steps.index(check_step) > next(
        index
        for index, step in enumerate(backend_steps)
        if step.get("name") == "Install dependencies"
    )
    assert backend_steps.index(check_step) < next(
        index
        for index, step in enumerate(backend_steps)
        if step.get("run") == 'python -m pytest -q -m "not docker"'
    )

    workflow_text = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    assert "observe-live" not in workflow_text
    assert "bounded-live-producer-v1.json" not in workflow_text
    assert "bounded-live-producer-v1.md" not in workflow_text
    for credential in ("OPENAI_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY"):
        assert credential not in workflow_text

    docker_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("run") == "python -m pytest -q -m docker"
    ]
    assert len(docker_steps) == 1
