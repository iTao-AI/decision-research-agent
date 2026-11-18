"""Optional, locally journaled Chat Completions requests for the findings benchmark.

The operator entry point verifies the frozen public input files and supplies the
operator's explicit opt-in. An approval digest binds the opt-in to proposal bytes.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from time import monotonic
from typing import Any, Callable, Never, TypeVar

import httpx


MODEL = "gpt-5.4-mini-2026-03-17"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
KEY_ENV = "FINDINGS_QUALITY_OPENAI_API_KEY"
PROPOSAL_SCHEMA = "findings-quality-budget-proposal-v1"
_PRICE = {"input": "0.75", "output": "4.50"}
_SERVICE_TIER = "default"
_KNOWN_SERVICE_TIERS = frozenset({"auto", "default", "fast", "flex", "priority", "scale"})
_SHA256 = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)
_TEXT_ROLES = frozenset({"system", "developer", "user", "tool", "assistant"})
_MESSAGE_FIELDS = frozenset({"role", "content", "name", "tool_call_id", "tool_calls"})
_MAX_RESPONSE_BYTES = 256 * 1024
# Reserve one token per UTF-8 wire byte and additional service framing.
_INPUT_FRAMING_RESERVE = 256
Validated = TypeVar("Validated")


class LiveCallError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ChatBudget:
    max_requests: int
    max_input_tokens: int
    max_output_tokens: int
    max_input_tokens_per_request: int
    max_output_tokens_per_request: int
    max_elapsed_seconds: int
    max_estimated_microusd: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise LiveCallError("invalid_budget")
        if (
            self.max_input_tokens_per_request > self.max_input_tokens
            or self.max_output_tokens_per_request > self.max_output_tokens
        ):
            raise LiveCallError("invalid_budget")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate JSON key")
        data[key] = value
    return data


def _json_object(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object,
    )
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _encoded(value: dict[str, Any]) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def load_proposal(path: Path, *, repo_root: Path) -> tuple[str, ChatBudget]:
    """Verify provider settings and file digests; return approval ID and limits."""
    try:
        raw = path.read_bytes()
        proposal = _json_object(raw)
        if (
            proposal["schema"] != PROPOSAL_SCHEMA
            or proposal["provider"] != "OpenAI"
            or proposal["model"] != MODEL
            or proposal["endpoint"] != ENDPOINT
            or proposal["pricing_usd_per_million"] != _PRICE
        ):
            raise ValueError()
        budget = ChatBudget(**proposal["budget"])
        files = proposal["files"]
        if not isinstance(files, dict) or not files:
            raise ValueError()
        root = repo_root.resolve(strict=True)
    except (KeyError, OSError, TypeError, ValueError, RecursionError):
        raise LiveCallError("invalid_proposal") from None

    for name, expected in files.items():
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or relative.as_posix() != name
            or ".." in relative.parts
            or not isinstance(expected, str)
            or not _SHA256.fullmatch(expected)
        ):
            raise LiveCallError("invalid_proposal")
        try:
            source = (root / relative).resolve(strict=True)
            if not source.is_relative_to(root) or not source.is_file():
                raise LiveCallError("invalid_proposal")
            actual = _sha256(source.read_bytes())
        except OSError:
            raise LiveCallError("proposal_input_changed") from None
        if actual != expected:
            raise LiveCallError("proposal_input_changed")
    return _sha256(raw), budget


def _estimated_microusd(input_tokens: int, output_tokens: int) -> int:
    # USD per million tokens is numerically equal to micro-USD per token.
    return (3 * input_tokens + 18 * output_tokens + 3) // 4


def _tool_call_name(call: object) -> str:
    if not isinstance(call, dict):
        raise ValueError("invalid tool call")
    name = call["function"]["name"]
    if (
        call["type"] != "function"
        or not _IDENTIFIER.fullmatch(call["id"])
        or not _IDENTIFIER.fullmatch(name)
        or not isinstance(call["function"]["arguments"], str)
    ):
        raise ValueError("invalid tool call")
    return name


def _request(
    kind: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, output_limit: int,
) -> tuple[bytes, set[str]]:
    if kind not in {"generation", "judge"} or not isinstance(messages, list) or not messages:
        raise ValueError("invalid request")
    for message in messages:
        if not isinstance(message, dict) or message["role"] not in _TEXT_ROLES:
            raise ValueError("invalid message")
        if set(message) - _MESSAGE_FIELDS:
            raise ValueError("invalid message field")
        content = message.get("content")
        calls = message.get("tool_calls")
        if calls is not None:
            if message["role"] != "assistant" or not isinstance(calls, list) or not calls:
                raise ValueError("invalid message tool calls")
            for call in calls:
                _tool_call_name(call)
        if not isinstance(content, str) and (content is not None or not calls):
            raise ValueError("invalid message content")
        for field in ("name", "tool_call_id"):
            if field in message and not _IDENTIFIER.fullmatch(message[field]):
                raise ValueError("invalid message identifier")

    payload = {
        "messages": messages,
        "model": MODEL,
        "reasoning_effort": "none",
        "service_tier": _SERVICE_TIER,
        "store": False,
        "max_completion_tokens": output_limit,
        "stream": False,
    }
    allowed_tools: set[str] = set()
    if tools:
        if kind != "generation" or not isinstance(tools, list):
            raise ValueError("invalid tool definitions")
        for tool in tools:
            name = tool["function"]["name"]
            if tool["type"] != "function" or not _IDENTIFIER.fullmatch(name) or name in allowed_tools:
                raise ValueError("invalid tool definition")
            allowed_tools.add(name)
        payload["tools"] = tools
    return _encoded(payload), allowed_tools


def _assistant(body: dict[str, Any], allowed_tools: set[str]) -> dict[str, Any]:
    if body.get("model") != MODEL or body.get("object") != "chat.completion":
        raise ValueError("unexpected response kind or model")
    choices = body["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("expected one completion")
    choice = choices[0]
    message = choice["message"]
    if message["role"] != "assistant" or message.get("refusal"):
        raise ValueError("assistant output unavailable")
    content = message.get("content")
    calls = message.get("tool_calls")
    if choice["finish_reason"] == "tool_calls":
        if (
            not isinstance(calls, list) or not calls
            or (content is not None and not isinstance(content, str))
            or any(_tool_call_name(call) not in allowed_tools for call in calls)
        ):
            raise ValueError("invalid tool response")
    elif choice["finish_reason"] != "stop" or not isinstance(content, str) or not content.strip() or calls:
        raise ValueError("invalid completion")
    return message


def _usage(body: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = body.get("usage")
    if usage is None:
        return None, None
    if not isinstance(usage, dict):
        raise ValueError("invalid usage")
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    for count in (input_tokens, output_tokens):
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError("invalid token count")
    return input_tokens, output_tokens


class BoundedChat:
    """One serial, explicit opt-in evaluation with a fresh local receipt directory."""

    def __init__(
        self,
        *,
        opt_in: bool,
        approval_id: str | None,
        proposal_sha256: str,
        budget: ChatBudget,
        receipt_dir: Path,
        transport: httpx.AsyncBaseTransport | None = None,
        key_loader: Callable[[], str | None] | None = None,
    ) -> None:
        self._authorized = (
            opt_in is True
            and isinstance(approval_id, str)
            and _SHA256.fullmatch(approval_id) is not None
            and approval_id == proposal_sha256
        )
        self._proposal_sha256 = proposal_sha256
        self._budget = budget
        self._receipt_dir = receipt_dir
        self._transport = transport
        self._key_loader = key_loader if key_loader is not None else lambda: os.getenv(KEY_ENV)
        self._mode = "scripted" if transport is not None else "live"
        self._client: httpx.AsyncClient | None = None
        self._deadline = 0.0
        self._lock = asyncio.Lock()
        self._stopped = False
        self._seen: set[str] = set()
        self._reserved_input = 0
        self._reserved_output = 0

    async def __aenter__(self) -> BoundedChat:
        if not self._authorized:
            raise LiveCallError("not_authorized")
        try:
            self._receipt_dir.mkdir(mode=0o700, parents=True)
        except FileExistsError:
            raise LiveCallError("receipt_path_exists") from None
        except OSError:
            raise LiveCallError("receipt_failure") from None
        self._write("run.json", {
            "schema": "findings-quality-live-run-v1",
            "execution_mode": self._mode,
            "proposal_sha256": self._proposal_sha256,
            "model": MODEL,
            "budget": asdict(self._budget),
        })
        self._deadline = monotonic() + self._budget.max_elapsed_seconds
        self._client = httpx.AsyncClient(
            transport=(
                self._transport if self._transport is not None
                else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
            ),
            trust_env=False,
            follow_redirects=False,
            headers={"Accept-Encoding": "identity", "Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _write(self, filename: str, record: dict[str, Any]) -> None:
        try:
            with (self._receipt_dir / filename).open("xb") as output:
                output.write(_encoded(record) + b"\n")
        except OSError:
            self._stopped = True
            raise LiveCallError("receipt_failure") from None

    def _budget_block(self, input_tokens: int, output_tokens: int) -> str | None:
        budget = self._budget
        total_input = self._reserved_input + input_tokens
        total_output = self._reserved_output + output_tokens
        if monotonic() >= self._deadline:
            return "elapsed"
        if len(self._seen) >= budget.max_requests:
            return "request_count"
        if input_tokens > budget.max_input_tokens_per_request:
            return "input_per_request"
        if total_input > budget.max_input_tokens:
            return "input_total"
        if total_output > budget.max_output_tokens:
            return "output_total"
        if _estimated_microusd(total_input, total_output) > budget.max_estimated_microusd:
            return "estimated_cost"
        return None

    def _block(self, sequence: str, record: dict[str, Any], status: str, reason: str) -> Never:
        self._stopped = True
        self._write(f"{sequence}-blocked.json", {**record, "status": status, "reason": reason})
        raise LiveCallError(status)

    async def _exchange(
        self, client: httpx.AsyncClient, payload: bytes, key: str, result: dict[str, Any],
    ) -> dict[str, Any]:
        remaining = self._deadline - monotonic()
        if remaining <= 0:
            raise LiveCallError("timeout")
        async with asyncio.timeout(remaining):
            async with client.stream(
                "POST", ENDPOINT, content=payload, headers={"Authorization": f"Bearer {key}"},
                timeout=remaining,
            ) as response:
                result["http_status"] = response.status_code
                if response.status_code != 200:
                    raise LiveCallError("provider_failure")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise LiveCallError("invalid_response")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise LiveCallError("invalid_response")
                    raw.extend(chunk)
        return _json_object(raw)

    async def complete(
        self,
        *,
        kind: str,
        request_id: str,
        messages: list[dict[str, Any]],
        validate: Callable[[dict[str, Any]], Validated],
        tools: list[dict[str, Any]] | None = None,
    ) -> Validated:
        async with self._lock:
            client = self._client
            if client is None:
                raise LiveCallError("not_open")
            if self._stopped:
                raise LiveCallError("run_stopped")
            if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
                self._stopped = True
                raise LiveCallError("invalid_request")
            record = {
                "schema": "findings-quality-live-request-v1",
                "execution_mode": self._mode,
                "request_id": request_id,
                "proposal_sha256": self._proposal_sha256,
                "kind": kind if kind in ("generation", "judge") else None,
                "model": MODEL,
            }
            sequence = f"{len(self._seen) + 1:04d}"
            if request_id in self._seen:
                self._block(sequence, record, "invalid_request", "duplicate_request_id")
            output_limit = self._budget.max_output_tokens_per_request
            try:
                payload, allowed_tools = _request(kind, messages, tools, output_limit)
            except (KeyError, TypeError, ValueError, RecursionError):
                self._block(sequence, record, "invalid_request", "invalid_payload")
            input_reserve = len(payload) + _INPUT_FRAMING_RESERVE
            record.update({
                "request_sha256": _sha256(payload),
                "reserved_input_tokens": input_reserve,
                "reserved_output_tokens": output_limit,
                "reserved_estimated_microusd": _estimated_microusd(input_reserve, output_limit),
                "http_status": None,
                "service_tier": None,
                "provider_response_id": None,
                "input_tokens": None,
                "output_tokens": None,
                "observed_estimated_microusd": None,
            })
            blocked = self._budget_block(input_reserve, output_limit)
            if blocked:
                self._block(sequence, record, "budget_exhausted", blocked)
            try:
                key = self._key_loader()
            except Exception:
                self._block(sequence, record, "credential_unavailable", "key_load_failed")
            if not isinstance(key, str) or not key or not key.isascii() or not key.isprintable() or " " in key:
                self._block(sequence, record, "credential_unavailable", "key_missing_or_invalid")
            if monotonic() >= self._deadline:
                self._block(sequence, record, "budget_exhausted", "elapsed")

            self._write(f"{sequence}-started.json", {**record, "status": "started"})
            self._seen.add(request_id)
            self._reserved_input += input_reserve
            self._reserved_output += output_limit
            started = monotonic()
            try:
                try:
                    body = await self._exchange(client, payload, key, record)
                except (TimeoutError, httpx.TimeoutException):
                    raise LiveCallError("timeout") from None
                except httpx.HTTPError:
                    raise LiveCallError("provider_failure") from None
                except LiveCallError:
                    raise
                except (TypeError, ValueError, RecursionError):
                    raise LiveCallError("invalid_response") from None
                response_id = body.get("id")
                if isinstance(response_id, str) and _IDENTIFIER.fullmatch(response_id):
                    record["provider_response_id"] = response_id
                try:
                    input_tokens, output_tokens = _usage(body)
                except ValueError:
                    raise LiveCallError("invalid_response") from None
                record.update(input_tokens=input_tokens, output_tokens=output_tokens)
                service_tier = body.get("service_tier")
                if isinstance(service_tier, str) and service_tier in _KNOWN_SERVICE_TIERS:
                    record["service_tier"] = service_tier
                if service_tier not in (None, _SERVICE_TIER):
                    raise LiveCallError("unexpected_service_tier")
                if input_tokens is not None and output_tokens is not None:
                    record["observed_estimated_microusd"] = _estimated_microusd(input_tokens, output_tokens)
                if (
                    (input_tokens is not None and input_tokens > input_reserve)
                    or (output_tokens is not None and output_tokens > output_limit)
                ):
                    raise LiveCallError("usage_overrun")
                try:
                    value = validate(_assistant(body, allowed_tools))
                except Exception:
                    raise LiveCallError("invalid_response") from None
                if monotonic() >= self._deadline:
                    raise LiveCallError("timeout")
            except (LiveCallError, asyncio.CancelledError) as exc:
                self._stopped = True
                status = exc.code if isinstance(exc, LiveCallError) else "cancelled"
                self._record_result(sequence, record, status, started)
                raise

            self._record_result(sequence, record, "success", started)
            return value

    def _record_result(self, sequence: str, record: dict[str, Any], status: str, started: float) -> None:
        self._write(f"{sequence}-result.json", {
            **record,
            "status": status,
            "elapsed_ms": round((monotonic() - started) * 1000),
        })
