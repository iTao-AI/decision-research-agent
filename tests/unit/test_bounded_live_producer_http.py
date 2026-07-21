from __future__ import annotations

import http.client
import json
from typing import Any

import pytest

from scripts.bounded_live_producer_contracts import EvaluationError
from scripts.bounded_live_producer_http import (
    CreateAmbiguous,
    HttpObservation,
    ProofHttpClient,
)


API_KEY = "proof-api-key"
IDEMPOTENCY_KEY = "proof-key-123456"
REQUEST_BYTES = b'{"profile_id":"generic","query":"bounded","scope":{},"thread_id":"thread-1"}'


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes = b"{}",
        content_length: str | None = None,
        read_error: BaseException | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._content_length = content_length
        self._read_error = read_error

    def getheader(self, name: str) -> str | None:
        assert name == "Content-Length"
        return self._content_length

    def read(self, amount: int) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.closed = False

    def putrequest(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("putrequest", args, kwargs))

    def putheader(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("putheader", args, kwargs))

    def endheaders(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("endheaders", args, kwargs))

    def getresponse(self) -> FakeResponse:
        self.calls.append(("getresponse", (), {}))
        return self.response

    def close(self) -> None:
        self.closed = True


def _json_body(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _client(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    *,
    remaining=lambda requested: requested,
) -> tuple[ProofHttpClient, FakeConnection, list[tuple[str, int, float]]]:
    connection = FakeConnection(response)
    constructions: list[tuple[str, int, float]] = []

    def make_connection(host: str, port: int, *, timeout: float):
        constructions.append((host, port, timeout))
        return connection

    monkeypatch.setattr(http.client, "HTTPConnection", make_connection)
    return (
        ProofHttpClient(
            port=49152,
            api_key=API_KEY,
            remaining_seconds=remaining,
        ),
        connection,
        constructions,
    )


@pytest.mark.parametrize("port", [True, False, 0, -1, 65536, 1.0, "8000", None])
def test_constructor_rejects_every_non_positive_integer_port(port):
    with pytest.raises(EvaluationError, match="service_identity_invalid") as exc_info:
        ProofHttpClient(
            port=port,
            api_key=API_KEY,
            remaining_seconds=lambda requested: requested,
        )

    assert exc_info.value.phase.value == "docker"


def test_connection_uses_only_exact_ipv4_loopback_and_remaining_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    client, _, constructions = _client(
        monkeypatch,
        FakeResponse(body=_json_body({"status": "ok", "service": "decision-research-agent"})),
        remaining=lambda requested: 1.25,
    )

    client.health(timeout_seconds=5.0)

    assert constructions == [("127.0.0.1", 49152, 1.25)]


def test_ambient_proxy_variables_never_change_the_wire_target(
    monkeypatch: pytest.MonkeyPatch,
):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "http://attacker.invalid:9999")
    client, _, constructions = _client(
        monkeypatch,
        FakeResponse(body=_json_body({"status": "ok", "service": "decision-research-agent"})),
    )

    client.health()

    assert constructions == [("127.0.0.1", 49152, 30.0)]


def test_health_uses_exact_low_level_request_and_header_allowlist(
    monkeypatch: pytest.MonkeyPatch,
):
    client, connection, _ = _client(
        monkeypatch,
        FakeResponse(body=_json_body({"status": "ok", "service": "decision-research-agent"})),
    )

    observation = client.health()

    assert observation == {"status": "ok", "service": "decision-research-agent"}
    assert connection.calls == [
        ("putrequest", ("GET", "/health"), {"skip_host": True, "skip_accept_encoding": True}),
        ("putheader", ("Host", "127.0.0.1:49152"), {}),
        ("putheader", ("Accept", "application/json"), {}),
        ("putheader", ("Accept-Encoding", "identity"), {}),
        ("putheader", ("X-API-Key", API_KEY), {}),
        ("endheaders", (), {}),
        ("getresponse", (), {}),
    ]
    assert connection.closed is True


def test_create_uses_exact_post_path_headers_and_original_request_bytes(
    monkeypatch: pytest.MonkeyPatch,
):
    acknowledgement = {
        "status": "started",
        "run_id": "run-1",
        "thread_id": "thread-1",
        "segment_id": "run-1_seg_000",
        "idempotent_replay": False,
    }
    client, connection, _ = _client(
        monkeypatch,
        FakeResponse(body=_json_body(acknowledgement)),
    )

    assert client.create(
        request_bytes=REQUEST_BYTES,
        idempotency_key=IDEMPOTENCY_KEY,
    ) == acknowledgement

    assert connection.calls == [
        ("putrequest", ("POST", "/api/runs"), {"skip_host": True, "skip_accept_encoding": True}),
        ("putheader", ("Host", "127.0.0.1:49152"), {}),
        ("putheader", ("Accept", "application/json"), {}),
        ("putheader", ("Accept-Encoding", "identity"), {}),
        ("putheader", ("X-API-Key", API_KEY), {}),
        ("putheader", ("Content-Type", "application/json"), {}),
        ("putheader", ("Content-Length", str(len(REQUEST_BYTES))), {}),
        ("putheader", ("Idempotency-Key", IDEMPOTENCY_KEY), {}),
        ("endheaders", (REQUEST_BYTES,), {}),
        ("getresponse", (), {}),
    ]
    assert connection.closed is True


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_rejected_without_following(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
):
    client, connection, constructions = _client(
        monkeypatch,
        FakeResponse(status=status, body=b"{}"),
    )

    with pytest.raises(EvaluationError, match="service_identity_invalid"):
        client.health()

    assert len(constructions) == 1
    assert connection.closed is True


def test_complete_http_create_error_is_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
):
    client, connection, _ = _client(
        monkeypatch,
        FakeResponse(status=409, body=b'{"code":"run_idempotency_conflict"}'),
    )

    with pytest.raises(EvaluationError, match="create_rejected") as exc_info:
        client.create(request_bytes=REQUEST_BYTES, idempotency_key=IDEMPOTENCY_KEY)

    assert not isinstance(exc_info.value, CreateAmbiguous)
    assert connection.closed is True


def test_declared_oversized_response_is_rejected_before_read(
    monkeypatch: pytest.MonkeyPatch,
):
    response = FakeResponse(content_length=str(2 * 1024 * 1024 + 1))
    client, connection, _ = _client(monkeypatch, response)

    with pytest.raises(EvaluationError, match="service_identity_invalid"):
        client.health()

    assert response._offset == 0
    assert connection.closed is True


def test_actual_oversized_response_is_rejected_while_streaming(
    monkeypatch: pytest.MonkeyPatch,
):
    client, connection, _ = _client(
        monkeypatch,
        FakeResponse(body=b"{" + b" " * (2 * 1024 * 1024) + b"}"),
    )

    with pytest.raises(EvaluationError, match="service_identity_invalid"):
        client.health()

    assert connection.closed is True


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null", b"1", b'"object"'])
def test_non_object_or_malformed_health_json_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
):
    client, connection, _ = _client(monkeypatch, FakeResponse(body=body))

    with pytest.raises(EvaluationError, match="service_identity_invalid"):
        client.health()

    assert connection.closed is True


def test_create_body_read_failure_is_ambiguous_once(
    monkeypatch: pytest.MonkeyPatch,
):
    client, connection, _ = _client(
        monkeypatch,
        FakeResponse(read_error=OSError("injected")),
    )

    with pytest.raises(CreateAmbiguous):
        client.create(request_bytes=REQUEST_BYTES, idempotency_key=IDEMPOTENCY_KEY)

    assert connection.closed is True


def test_malformed_create_json_is_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
):
    client, connection, _ = _client(monkeypatch, FakeResponse(body=b"not-json"))

    with pytest.raises(EvaluationError, match="create_response_invalid") as exc_info:
        client.create(request_bytes=REQUEST_BYTES, idempotency_key=IDEMPOTENCY_KEY)

    assert not isinstance(exc_info.value, CreateAmbiguous)
    assert connection.closed is True


@pytest.mark.parametrize(
    "mutation",
    [
        {"thread_id": "other-thread"},
        {"run_id": ""},
        {"segment_id": 1},
        {"idempotent_replay": 0},
        {"extra": "not-allowed"},
    ],
)
def test_create_acknowledgement_requires_exact_identity_and_key_set(
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, Any],
):
    acknowledgement: dict[str, Any] = {
        "status": "started",
        "run_id": "run-1",
        "thread_id": "thread-1",
        "segment_id": "run-1_seg_000",
        "idempotent_replay": False,
    }
    acknowledgement.update(mutation)
    client, _, _ = _client(monkeypatch, FakeResponse(body=_json_body(acknowledgement)))

    with pytest.raises(EvaluationError, match="create_identity_mismatch"):
        client.create(request_bytes=REQUEST_BYTES, idempotency_key=IDEMPOTENCY_KEY)


@pytest.mark.parametrize(
    ("method_name", "path", "body"),
    [
        ("status", "/api/runs/run-1", {"run_id": "run-1", "state_version": 2}),
        (
            "result",
            "/api/runs/run-1/result",
            {"run_id": "run-1", "artifact": {"artifact_id": "research-report.md"}},
        ),
        (
            "usage",
            "/api/token-usage/runs/run-1",
            {
                "total_prompt": 1,
                "total_completion": 2,
                "total_tokens": 3,
                "total_cost": 0.0,
                "call_count": 1,
            },
        ),
    ],
)
def test_typed_get_methods_use_exact_paths(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    path: str,
    body: dict[str, Any],
):
    client, connection, _ = _client(monkeypatch, FakeResponse(body=_json_body(body)))

    result = getattr(client, method_name)(run_id="run-1")

    assert result == body
    assert connection.calls[0] == (
        "putrequest",
        ("GET", path),
        {"skip_host": True, "skip_accept_encoding": True},
    )


@pytest.mark.parametrize("method_name", ["status", "result"])
def test_run_responses_must_match_the_requested_run_identity(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
):
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(body=_json_body({"run_id": "run-2"})),
    )

    expected_code = "run_state_invalid" if method_name == "status" else "consumer_projection_invalid"
    with pytest.raises(EvaluationError, match=expected_code):
        getattr(client, method_name)(run_id="run-1")


def test_result_maps_only_exact_matching_unavailable_envelope_to_artifact_invalid(
    monkeypatch: pytest.MonkeyPatch,
):
    body = {
        "code": "run_result_unavailable",
        "problem": "The run completed without a canonical result artifact.",
        "fix": "Inspect the run and retry with a new run intent if authorized.",
        "retryable": True,
        "run_id": "run-1",
    }
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(status=409, body=_json_body(body)),
    )

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "artifact_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize(
    "mutation",
    [
        {"code": "run_not_terminal"},
        {"retryable": False},
        {"retryable": 1},
        {"run_id": "run-2"},
        {"code": 409},
        {"problem": 1},
        {"problem": ""},
        {"fix": None},
        {"fix": ""},
        {"extra": "field"},
    ],
)
def test_result_rejects_noncanonical_unavailable_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, Any],
):
    body: dict[str, Any] = {
        "code": "run_result_unavailable",
        "problem": "The run completed without a canonical result artifact.",
        "fix": "Inspect the run and retry with a new run intent if authorized.",
        "retryable": True,
        "run_id": "run-1",
    }
    body.update(mutation)
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(status=409, body=_json_body(body)),
    )

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


def test_result_rejects_unavailable_envelope_with_missing_key(
    monkeypatch: pytest.MonkeyPatch,
):
    body = {
        "code": "run_result_unavailable",
        "problem": "The run completed without a canonical result artifact.",
        "retryable": True,
        "run_id": "run-1",
    }
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(status=409, body=_json_body(body)),
    )

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize("status", [404, 409, 500])
def test_result_keeps_other_non_success_responses_generic(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
):
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(status=status, body=_json_body({"code": "other"})),
    )

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null"])
def test_result_keeps_malformed_409_json_generic(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
):
    client, _, _ = _client(monkeypatch, FakeResponse(status=409, body=body))

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status=409, content_length=str(2 * 1024 * 1024 + 1)),
        FakeResponse(status=409, read_error=OSError("injected private error")),
    ],
)
def test_result_keeps_409_read_failures_generic(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
):
    client, _, _ = _client(monkeypatch, response)

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize("failure", [OSError("injected"), TimeoutError("injected")])
def test_result_keeps_connection_and_timeout_failures_generic(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
):
    def fail_connection(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(http.client, "HTTPConnection", fail_connection)
    client = ProofHttpClient(
        port=49152,
        api_key=API_KEY,
        remaining_seconds=lambda requested: requested,
    )

    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.phase.value == "result"


@pytest.mark.parametrize(
    "mutation",
    [
        {"total_prompt": True},
        {"total_completion": -1},
        {"total_tokens": 4},
        {"total_cost": "0.0"},
        {"call_count": -1},
        {"extra": 1},
    ],
)
def test_usage_requires_exact_consistent_key_set_and_types(
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, Any],
):
    body: dict[str, Any] = {
        "total_prompt": 1,
        "total_completion": 2,
        "total_tokens": 3,
        "total_cost": 0.0,
        "call_count": 1,
    }
    body.update(mutation)
    client, _, _ = _client(monkeypatch, FakeResponse(body=_json_body(body)))

    with pytest.raises(EvaluationError, match="usage_invalid"):
        client.usage(run_id="run-1")


def test_exact_health_body_is_required(monkeypatch: pytest.MonkeyPatch):
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(body=_json_body({"status": "ok", "service": "wrong-service"})),
    )

    with pytest.raises(EvaluationError, match="service_identity_invalid"):
        client.health()


def test_deadline_exhaustion_happens_before_connection_or_io(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[float] = []

    def exhausted(requested: float) -> float:
        calls.append(requested)
        raise EvaluationError("run_observation_deadline", "observe", False)

    client, connection, constructions = _client(
        monkeypatch,
        FakeResponse(),
        remaining=exhausted,
    )

    with pytest.raises(EvaluationError, match="run_observation_deadline"):
        client.status(run_id="run-1", timeout_seconds=9.0)

    assert calls == [9.0]
    assert constructions == []
    assert connection.calls == []


@pytest.mark.parametrize("remaining", [0, -0.1, True, float("inf"), float("nan")])
def test_invalid_remaining_timeout_fails_before_connection(
    monkeypatch: pytest.MonkeyPatch,
    remaining: object,
):
    client, connection, constructions = _client(
        monkeypatch,
        FakeResponse(),
        remaining=lambda _requested: remaining,
    )

    with pytest.raises(EvaluationError, match="run_observation_deadline"):
        client.status(run_id="run-1")

    assert constructions == []
    assert connection.calls == []


def test_http_observation_is_frozen_and_has_only_status_and_body():
    observation = HttpObservation(status_code=200, body={"status": "ok"})

    assert observation.status_code == 200
    assert observation.body == {"status": "ok"}
    with pytest.raises((AttributeError, TypeError)):
        observation.status_code = 201
