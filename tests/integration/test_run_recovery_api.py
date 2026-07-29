from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

import api.server as server
from api.run_execution_models import RunExecutionConflict
from api.run_recovery_models import (
    RunRecoveryAcceptance,
    RunRecoveryConflict,
)


AUTH = {"X-API-Key": "test-integration-key"}
KEY = "recovery-key-0123456789abcdef"
SOURCE = "run_source"


def _acceptance(*, replay: bool = False) -> RunRecoveryAcceptance:
    return RunRecoveryAcceptance(
        reason="previous_boot_interrupted",
        interrupted_phase="execution",
        source_run_id=SOURCE,
        run_id="run_replacement",
        thread_id="caller-thread",
        segment_id="run_replacement_seg_000",
        recovery_attempt=1,
        idempotent_replay=replay,
    )


class _Worker:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None]] = []
        self.dispatch_result = True
        self.dispatch_exception: BaseException | None = None
        self.wake_exception: BaseException | None = None
        self._stopped = asyncio.Event()

    async def run_forever(self) -> None:
        await self._stopped.wait()

    def stop(self) -> None:
        self._stopped.set()

    async def dispatch_run(self, run_id: str) -> bool:
        self.events.append(("dispatch", run_id))
        if self.dispatch_exception is not None:
            raise self.dispatch_exception
        return self.dispatch_result

    def wake(self) -> None:
        self.events.append(("wake", None))
        if self.wake_exception is not None:
            raise self.wake_exception


@pytest.fixture
def recovery_client(tmp_path, monkeypatch, authenticated_runtime_access):
    worker = _Worker()
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_DB_PATH",
        str(tmp_path / "application" / "runs.db"),
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "false",
    )
    monkeypatch.setattr(server, "output_dir", tmp_path / "output")
    monkeypatch.setattr(
        server,
        "create_run_dispatch_worker",
        lambda *args, **kwargs: worker,
    )
    with TestClient(server.app) as client:
        yield client, worker


def _post(
    client: TestClient,
    *,
    source: str = SOURCE,
    key: str | None = KEY,
    content=None,
    headers: dict[str, str] | None = None,
):
    request_headers = dict(AUTH)
    if key is not None:
        request_headers["Idempotency-Key"] = key
    request_headers.update(headers or {})
    return client.post(
        f"/api/runs/{source}/retries",
        content=content,
        headers=request_headers,
    )


def _install_acceptance(monkeypatch, events, *, replay=False):
    def repository(**kwargs):
        events.append(("repository", kwargs["source_run_id"]))
        return _acceptance(replay=replay)

    monkeypatch.setattr(server, "create_or_replay_run_recovery", repository)


def _assert_error(response, *, status: int, code: str, retryable: bool):
    assert response.status_code == status
    body = (
        response.json()
        if hasattr(response, "json")
        else json.loads(response.body)
    )
    assert set(body) == {
        "code",
        "problem",
        "cause",
        "fix",
        "retryable",
        "run_id",
        "request_id",
    }
    assert body["code"] == code
    assert body["retryable"] is retryable
    assert body["run_id"] is None
    assert re.fullmatch(r"request_[0-9a-f]{32}", body["request_id"])
    return body


def test_missing_api_key_is_rejected_before_body_repository_and_wake(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []
    monkeypatch.setattr(
        server,
        "_require_zero_recovery_body",
        lambda request: events.append(("body", None)),
    )
    _install_acceptance(monkeypatch, events)

    response = client.post(
        f"/api/runs/{SOURCE}/retries",
        headers={"Idempotency-Key": KEY},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "api_key_invalid"
    assert events == []
    assert worker.events == []


def test_wrong_api_key_is_rejected_before_body_repository_and_wake(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []
    _install_acceptance(monkeypatch, events)

    response = client.post(
        f"/api/runs/{SOURCE}/retries",
        headers={"X-API-Key": "wrong", "Idempotency-Key": KEY},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "api_key_invalid"
    assert events == []
    assert worker.events == []


def test_correct_api_key_reaches_zero_body_guard_then_repository(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []
    real_guard = server._require_zero_recovery_body

    async def body_guard(request):
        events.append(("body", None))
        await real_guard(request)

    monkeypatch.setattr(server, "_require_zero_recovery_body", body_guard)
    _install_acceptance(monkeypatch, events)

    response = _post(client)

    assert response.status_code == 202
    assert events == [("body", None), ("repository", SOURCE)]
    assert worker.events == [
        ("dispatch", "run_replacement"),
        ("wake", None),
    ]


def test_loopback_mode_preserves_existing_runtime_access_behavior(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    monkeypatch.setattr(
        server.app.state,
        "runtime_access_policy",
        server.load_runtime_access_policy({}),
    )
    recovery = client.post(
        f"/api/runs/{SOURCE}/retries",
        headers={"Idempotency-Key": KEY},
    )
    ordinary = client.post("/api/runs", json={"query": "q"})

    assert recovery.status_code == ordinary.status_code == 503
    assert recovery.json() == ordinary.json()
    assert worker.events == []


def test_recovery_does_not_add_a_second_authentication_header():
    operation = server.app.openapi()["paths"][
        "/api/runs/{source_run_id}/retries"
    ]["post"]
    header_names = [
        parameter["name"]
        for parameter in operation["parameters"]
        if parameter["in"] == "header"
    ]
    assert header_names == ["Idempotency-Key"]


def test_zero_bytes_without_content_length_are_accepted(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    _install_acceptance(monkeypatch, [])
    response = _post(client, content=None)
    assert response.status_code == 202


def test_zero_content_length_and_zero_bytes_are_accepted(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    _install_acceptance(monkeypatch, [])
    response = _post(
        client,
        content=b"",
        headers={"Content-Length": "0"},
    )
    assert response.status_code == 202


def test_positive_content_length_is_rejected_before_stream_and_repository(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []
    _install_acceptance(monkeypatch, events)
    response = _post(
        client,
        content=b"x",
        headers={"Content-Length": "1"},
    )
    _assert_error(
        response,
        status=422,
        code="run_recovery_body_not_allowed",
        retryable=False,
    )
    assert events == []
    assert worker.events == []


def test_invalid_content_length_is_rejected_before_stream_and_repository(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []
    _install_acceptance(monkeypatch, events)
    response = _post(
        client,
        content=b"",
        headers={"Content-Length": "invalid"},
    )
    _assert_error(
        response,
        status=422,
        code="run_recovery_body_not_allowed",
        retryable=False,
    )
    assert events == []
    assert worker.events == []


@pytest.mark.parametrize("body", [b" ", b"{}", b"null", b"x"])
def test_whitespace_object_null_and_one_byte_chunk_are_rejected(
    recovery_client,
    monkeypatch,
    body,
):
    client, worker = recovery_client
    events = []
    _install_acceptance(monkeypatch, events)
    response = _post(client, content=body)
    _assert_error(
        response,
        status=422,
        code="run_recovery_body_not_allowed",
        retryable=False,
    )
    assert events == []
    assert worker.events == []


@pytest.mark.asyncio
async def test_chunked_body_guard_stops_after_first_nonempty_chunk():
    observed = []

    class Request:
        headers = {}

        async def stream(self):
            observed.append("first")
            yield b"x"
            observed.append("second")
            yield b"not-read"

    with pytest.raises(server.RunRecoveryBodyNotAllowed):
        await server._require_zero_recovery_body(Request())
    assert observed == ["first"]


def test_body_is_never_parsed_as_json_or_pydantic(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    _install_acceptance(monkeypatch, [])
    monkeypatch.setattr(
        "starlette.requests.Request.json",
        lambda self: pytest.fail("request.json must not be called"),
    )
    response = _post(client)
    assert response.status_code == 202


@pytest.mark.parametrize("key", [None, "short", "bad key", "x" * 129])
def test_missing_or_malformed_recovery_key_fails_after_body_before_repository(
    recovery_client,
    monkeypatch,
    key,
):
    client, worker = recovery_client
    events = []
    _install_acceptance(monkeypatch, events)
    response = _post(client, key=key)
    _assert_error(
        response,
        status=422,
        code="run_recovery_key_invalid",
        retryable=False,
    )
    assert events == []
    assert worker.events == []


def test_first_recovery_returns_exact_ten_field_202_contract(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    _install_acceptance(monkeypatch, [])
    response = _post(client)
    assert response.status_code == 202
    assert response.json() == _acceptance().model_dump(mode="json")
    assert len(response.json()) == 10


def test_replay_returns_same_replacement_and_only_flips_replay_flag(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    calls = []

    def repository(**kwargs):
        calls.append(kwargs)
        return _acceptance(replay=len(calls) > 1)

    monkeypatch.setattr(server, "create_or_replay_run_recovery", repository)
    first = _post(client).json()
    second = _post(client).json()
    assert {**first, "idempotent_replay": True} == second


def test_source_not_found_maps_to_exact_404_envelope(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(
            RunRecoveryConflict("run_recovery_source_not_found")
        ),
    )
    _assert_error(
        _post(client),
        status=404,
        code="run_recovery_source_not_found",
        retryable=False,
    )


@pytest.mark.parametrize(
    "code",
    [
        "run_recovery_not_eligible",
        "run_recovery_exhausted",
        "run_recovery_conflict",
    ],
)
def test_not_eligible_exhausted_and_conflict_map_to_exact_409_envelopes(
    recovery_client,
    monkeypatch,
    code,
):
    client, _ = recovery_client
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(RunRecoveryConflict(code)),
    )
    _assert_error(
        _post(client),
        status=409,
        code=code,
        retryable=False,
    )


def test_profile_drift_maps_to_not_eligible_and_preserves_failed_source(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(
            RunRecoveryConflict("run_recovery_not_eligible")
        ),
    )
    response = _post(client)
    _assert_error(
        response,
        status=409,
        code="run_recovery_not_eligible",
        retryable=False,
    )
    assert worker.events == []


def test_one_hop_exhaustion_creates_no_hidden_fallback_or_second_post(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    ordinary = []
    monkeypatch.setattr(
        server,
        "create_or_replay_run",
        lambda **kwargs: ordinary.append(kwargs),
    )
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(
            RunRecoveryConflict("run_recovery_exhausted")
        ),
    )
    response = _post(client)
    assert response.status_code == 409
    assert ordinary == []
    assert worker.events == []


@pytest.mark.parametrize(
    "exception",
    [
        RunRecoveryConflict("run_recovery_state_invalid"),
        RunRecoveryConflict("run_recovery_unavailable"),
        RunExecutionConflict("run_execution_recovery_unavailable"),
        sqlite3.DatabaseError("private database path"),
        ValidationError.from_exception_data("private", []),
    ],
)
def test_state_corruption_and_repository_failure_map_to_exact_503_envelope(
    recovery_client,
    monkeypatch,
    exception,
):
    client, _ = recovery_client
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(exception),
    )
    _assert_error(
        _post(client),
        status=503,
        code="run_recovery_unavailable",
        retryable=True,
    )


@pytest.mark.parametrize(
    ("code", "status", "retryable"),
    [
        ("run_recovery_source_not_found", 404, False),
        ("run_recovery_not_eligible", 409, False),
        ("run_recovery_exhausted", 409, False),
        ("run_recovery_conflict", 409, False),
        ("run_recovery_key_invalid", 422, False),
        ("run_recovery_body_not_allowed", 422, False),
        ("run_recovery_unavailable", 503, True),
    ],
)
def test_every_recovery_error_has_exact_keys_messages_retryability_and_request_id(
    code,
    status,
    retryable,
):
    response = server._run_recovery_error(code)
    body = _assert_error(
        response,
        status=status,
        code=code,
        retryable=retryable,
    )
    assert body["problem"].endswith(".")
    assert body["cause"].endswith(".")
    assert body["fix"].endswith(".")


def test_recovery_errors_never_expose_private_authority_or_exception_text(
    recovery_client,
    monkeypatch,
):
    client, _ = recovery_client
    private = "/private/database.sqlite owner_secret boot_secret traceback"
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(sqlite3.DatabaseError(private)),
    )
    response = _post(client)
    encoded = response.text
    for forbidden in private.split():
        assert forbidden not in encoded


def test_repository_commit_precedes_targeted_dispatch_and_wake(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    events = []

    def repository(**kwargs):
        events.append(("commit", kwargs["source_run_id"]))
        return _acceptance()

    async def dispatch(run_id):
        events.append(("dispatch", run_id))
        return True

    def wake():
        events.append(("wake", None))

    monkeypatch.setattr(server, "create_or_replay_run_recovery", repository)
    worker.dispatch_run = dispatch
    worker.wake = wake
    assert _post(client).status_code == 202
    assert events == [
        ("commit", SOURCE),
        ("dispatch", "run_replacement"),
        ("wake", None),
    ]


def test_dispatch_false_after_commit_still_returns_same_202(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    _install_acceptance(monkeypatch, [])
    worker.dispatch_result = False
    assert _post(client).json() == _acceptance().model_dump(mode="json")


def test_wake_exception_after_commit_still_returns_same_202(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    _install_acceptance(monkeypatch, [])
    worker.wake_exception = RuntimeError("private wake failure")
    response = _post(client)
    assert response.status_code == 202
    assert response.json() == _acceptance().model_dump(mode="json")


def test_post_commit_failure_logs_only_bounded_code_without_identities(
    recovery_client,
    monkeypatch,
    caplog,
):
    client, worker = recovery_client
    _install_acceptance(monkeypatch, [])
    worker.dispatch_exception = RuntimeError(
        "private run_replacement /private/database boot_secret"
    )
    with caplog.at_level(logging.ERROR):
        assert _post(client).status_code == 202
    assert "run_recovery_post_commit_wake_deferred" in caplog.text
    assert "run_replacement" not in caplog.text
    assert "/private/database" not in caplog.text
    assert "boot_secret" not in caplog.text


def test_replay_requests_targeted_dispatch_and_wake_again(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    _install_acceptance(monkeypatch, [], replay=True)
    assert _post(client).status_code == 202
    assert _post(client).status_code == 202
    assert worker.events == [
        ("dispatch", "run_replacement"),
        ("wake", None),
        ("dispatch", "run_replacement"),
        ("wake", None),
    ]


def test_precommit_failure_returns_503_and_never_dispatches(
    recovery_client,
    monkeypatch,
):
    client, worker = recovery_client
    monkeypatch.setattr(
        server,
        "create_or_replay_run_recovery",
        lambda **kwargs: (_ for _ in ()).throw(
            RunRecoveryConflict("run_recovery_unavailable")
        ),
    )
    response = _post(client)
    assert response.status_code == 503
    assert worker.events == []
