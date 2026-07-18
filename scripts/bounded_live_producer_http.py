"""Exact loopback HTTP transport for bounded live producer evaluation."""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import math
import re
from typing import Any, Callable

from scripts.bounded_live_producer_contracts import EvaluationError


MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
_READ_CHUNK_BYTES = 64 * 1024
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_IDEMPOTENCY_KEY_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z",
    re.ASCII,
)


@dataclass(frozen=True, slots=True)
class HttpObservation:
    """One bounded JSON response retained without headers or URL details."""

    status_code: int
    body: dict[str, Any]


class CreateAmbiguous(Exception):
    """The create request may have been accepted without a valid acknowledgement."""

    def __init__(self) -> None:
        super().__init__("create_ambiguous")


class _BodyReadFailure(Exception):
    pass


def _evaluation_error(code: str, phase: str) -> EvaluationError:
    return EvaluationError(code, phase, False)


def _require_identifier(value: object, *, code: str, phase: str) -> str:
    if type(value) is not str or _RUN_ID_RE.fullmatch(value) is None:
        raise _evaluation_error(code, phase)
    return value


def _load_object_json(raw: bytes, *, code: str, phase: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _evaluation_error(code, phase) from None
    if type(parsed) is not dict:
        raise _evaluation_error(code, phase)
    return parsed


class ProofHttpClient:
    """No-proxy, no-redirect client for one inspected loopback backend port."""

    def __init__(
        self,
        *,
        port: int,
        api_key: str,
        remaining_seconds: Callable[[float], float],
    ) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise _evaluation_error("service_identity_invalid", "docker")
        if (
            type(api_key) is not str
            or not api_key
            or len(api_key.encode("utf-8")) > 4096
            or not api_key.isascii()
            or any(character in api_key for character in "\r\n")
        ):
            raise _evaluation_error("credential_source_invalid", "input")
        if not callable(remaining_seconds):
            raise _evaluation_error("evaluation_internal_error", "internal")
        self._port = port
        self._api_key = api_key
        self._remaining_seconds = remaining_seconds

    def _connection(self, requested_timeout: float) -> http.client.HTTPConnection:
        if (
            type(requested_timeout) not in (int, float)
            or not math.isfinite(requested_timeout)
            or requested_timeout <= 0
        ):
            raise _evaluation_error("run_observation_deadline", "observe")
        timeout = self._remaining_seconds(float(requested_timeout))
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise _evaluation_error("run_observation_deadline", "observe")
        return http.client.HTTPConnection(
            "127.0.0.1",
            self._port,
            timeout=float(timeout),
        )

    @staticmethod
    def _read_bounded(response: http.client.HTTPResponse) -> bytes:
        declared = response.getheader("Content-Length")
        if declared is not None:
            try:
                declared_size = int(declared, 10)
            except (TypeError, ValueError):
                raise _BodyReadFailure from None
            if declared_size < 0 or declared_size > MAX_HTTP_RESPONSE_BYTES:
                raise _BodyReadFailure

        retained = bytearray()
        try:
            while True:
                remaining = MAX_HTTP_RESPONSE_BYTES - len(retained)
                chunk = response.read(min(_READ_CHUNK_BYTES, remaining + 1))
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    raise _BodyReadFailure
                retained.extend(chunk)
                if len(retained) > MAX_HTTP_RESPONSE_BYTES:
                    raise _BodyReadFailure
        except _BodyReadFailure:
            raise
        except Exception:
            raise _BodyReadFailure from None
        return bytes(retained)

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        code: str,
        phase: str,
        timeout_seconds: float,
        response_code: str | None = None,
        request_bytes: bytes | None = None,
        idempotency_key: str | None = None,
        ambiguous_create: bool = False,
    ) -> HttpObservation:
        connection: http.client.HTTPConnection | None = None
        response_status: int | None = None
        try:
            connection = self._connection(timeout_seconds)
            connection.putrequest(
                method,
                path,
                skip_host=True,
                skip_accept_encoding=True,
            )
            connection.putheader("Host", f"127.0.0.1:{self._port}")
            connection.putheader("Accept", "application/json")
            connection.putheader("Accept-Encoding", "identity")
            connection.putheader("X-API-Key", self._api_key)
            if method == "POST":
                assert request_bytes is not None
                assert idempotency_key is not None
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(request_bytes)))
                connection.putheader("Idempotency-Key", idempotency_key)
                connection.endheaders(request_bytes)
            else:
                connection.endheaders()
            response = connection.getresponse()
            response_status = response.status
            if type(response_status) is not int or not 100 <= response_status <= 599:
                raise _evaluation_error(code, phase)
            raw = self._read_bounded(response)
        except EvaluationError:
            raise
        except _BodyReadFailure:
            if ambiguous_create and response_status == 200:
                raise CreateAmbiguous from None
            raise _evaluation_error(code, phase) from None
        except Exception:
            if ambiguous_create:
                raise CreateAmbiguous from None
            raise _evaluation_error(code, phase) from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

        if response_status != 200:
            raise _evaluation_error(code, phase)
        return HttpObservation(
            status_code=response_status,
            body=_load_object_json(raw, code=response_code or code, phase=phase),
        )

    def health(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
        observation = self._request_json(
            method="GET",
            path="/health",
            code="service_identity_invalid",
            phase="docker",
            timeout_seconds=timeout_seconds,
        )
        if observation.body != {
            "status": "ok",
            "service": "decision-research-agent",
        }:
            raise _evaluation_error("service_identity_invalid", "docker")
        return observation.body

    def create(
        self,
        *,
        request_bytes: bytes,
        idempotency_key: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if (
            type(request_bytes) is not bytes
            or not request_bytes
            or len(request_bytes) > MAX_HTTP_RESPONSE_BYTES
            or type(idempotency_key) is not str
            or _IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key) is None
        ):
            raise _evaluation_error("create_response_invalid", "create")
        request = _load_object_json(
            request_bytes,
            code="create_response_invalid",
            phase="create",
        )
        requested_thread_id = _require_identifier(
            request.get("thread_id"),
            code="create_identity_mismatch",
            phase="create",
        )
        observation = self._request_json(
            method="POST",
            path="/api/runs",
            code="create_rejected",
            phase="create",
            response_code="create_response_invalid",
            timeout_seconds=timeout_seconds,
            request_bytes=request_bytes,
            idempotency_key=idempotency_key,
            ambiguous_create=True,
        )
        body = observation.body
        if set(body) != {
            "status",
            "run_id",
            "thread_id",
            "segment_id",
            "idempotent_replay",
        }:
            raise _evaluation_error("create_identity_mismatch", "create")
        if body.get("status") != "started" or body.get("thread_id") != requested_thread_id:
            raise _evaluation_error("create_identity_mismatch", "create")
        _require_identifier(
            body.get("run_id"),
            code="create_identity_mismatch",
            phase="create",
        )
        _require_identifier(
            body.get("segment_id"),
            code="create_identity_mismatch",
            phase="create",
        )
        if type(body.get("idempotent_replay")) is not bool:
            raise _evaluation_error("create_identity_mismatch", "create")
        return body

    def status(
        self,
        *,
        run_id: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        validated_run_id = _require_identifier(
            run_id,
            code="run_state_invalid",
            phase="observe",
        )
        observation = self._request_json(
            method="GET",
            path=f"/api/runs/{validated_run_id}",
            code="run_state_invalid",
            phase="observe",
            timeout_seconds=timeout_seconds,
        )
        if observation.body.get("run_id") != validated_run_id:
            raise _evaluation_error("run_state_invalid", "observe")
        return observation.body

    def result(
        self,
        *,
        run_id: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        validated_run_id = _require_identifier(
            run_id,
            code="consumer_projection_invalid",
            phase="result",
        )
        observation = self._request_json(
            method="GET",
            path=f"/api/runs/{validated_run_id}/result",
            code="consumer_projection_invalid",
            phase="result",
            timeout_seconds=timeout_seconds,
        )
        if observation.body.get("run_id") != validated_run_id:
            raise _evaluation_error("consumer_projection_invalid", "result")
        return observation.body

    def usage(
        self,
        *,
        run_id: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        validated_run_id = _require_identifier(
            run_id,
            code="usage_invalid",
            phase="usage",
        )
        observation = self._request_json(
            method="GET",
            path=f"/api/token-usage/runs/{validated_run_id}",
            code="usage_invalid",
            phase="usage",
            timeout_seconds=timeout_seconds,
        )
        body = observation.body
        if set(body) != {
            "total_prompt",
            "total_completion",
            "total_tokens",
            "total_cost",
            "call_count",
        }:
            raise _evaluation_error("usage_invalid", "usage")
        for key in ("total_prompt", "total_completion", "total_tokens", "call_count"):
            if type(body[key]) is not int or body[key] < 0:
                raise _evaluation_error("usage_invalid", "usage")
        if body["total_prompt"] + body["total_completion"] != body["total_tokens"]:
            raise _evaluation_error("usage_invalid", "usage")
        total_cost = body["total_cost"]
        if (
            type(total_cost) not in (int, float)
            or not math.isfinite(total_cost)
            or total_cost < 0
        ):
            raise _evaluation_error("usage_invalid", "usage")
        return body
