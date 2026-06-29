# CLI Golden Path And Structured Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents for this repository unless the owner explicitly authorizes them.

**Goal:** Add a bounded `run --wait --result` golden path and make every Tool Client runtime failure use one private, actionable structured error contract.

**Architecture:** Keep command composition in the existing Python Tool Client. The client starts a run, validates the returned `run_id`, polls the existing run endpoint with a monotonic deadline, and asks the canonical result endpoint for the deliverable. A client-owned error catalog normalizes local failures while preserving bounded service-owned error fields; server APIs, persistence, and Agent runtime remain unchanged.

**Tech Stack:** Python 3.11, `argparse`, `urllib.request`, `json`, `time.monotonic`, `pytest`

---

## Scope And File Map

Implementation is limited to these existing files:

| File | Responsibility in this change |
|---|---|
| `tools/decision_research_agent_tool.py` | CLI flags, command composition, bounded polling, scope loading, and structured errors |
| `tests/unit/test_decision_research_agent_tool.py` | TDD coverage for compatibility, ordering, deadlines, privacy, and error envelopes |
| `README.md` | One-command local golden path |
| `docs/AGENT_INTEGRATION.md` | Complete Tool Client flag, success, timeout, and error reference |
| `TODOS.md` | Close the two shipped post-v0.1.0 CLI DX items |

The approved design and this plan are implementation inputs:

- `docs/superpowers/specs/2026-06-29-cli-dx-design.md`
- `docs/superpowers/plans/2026-06-29-cli-dx-implementation.md`

Do not modify `api/`, `agent/`, migrations, database schemas, Docker files,
dependencies, benchmark code, durable review behavior, or frontend code.

## Stable Error Vocabulary

Implement the following local codes exactly. The prose is deliberately static
so raw exception strings, URLs, response bodies, and file paths never become
CLI output.

```python
_LOCAL_ERROR_DETAILS: dict[str, tuple[str, str, str, bool]] = {
    "connection_failed": (
        "Cannot reach Decision Research Agent.",
        "The configured service endpoint is unavailable.",
        "Start the backend or verify DECISION_RESEARCH_AGENT_URL.",
        True,
    ),
    "request_timeout": (
        "The service request timed out.",
        "The backend did not respond within the configured request timeout.",
        "Retry the command or increase DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS.",
        True,
    ),
    "invalid_json_response": (
        "The service returned invalid JSON.",
        "The response could not be decoded as a JSON document.",
        "Check backend health and retry after the service is stable.",
        False,
    ),
    "json_response_not_object": (
        "The service returned an unsupported JSON value.",
        "The Tool Client requires a JSON object response.",
        "Check the backend and Tool Client versions before retrying.",
        False,
    ),
    "scope_file_unreadable": (
        "The scope file cannot be read.",
        "The file is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 JSON file.",
        False,
    ),
    "scope_file_invalid": (
        "The scope file is invalid.",
        "Research scope must be a JSON object.",
        "Correct the scope document and retry the command.",
        False,
    ),
    "run_response_invalid": (
        "The run creation response is invalid.",
        "The service did not return a non-empty string run_id.",
        "Check backend compatibility before creating another run.",
        False,
    ),
    "result_requires_wait": (
        "Canonical result retrieval requires --wait.",
        "The --result flag composes run creation, bounded waiting, and delivery.",
        "Use --wait --result, or call result --run-id separately.",
        False,
    ),
    "run_poll_seconds_must_be_positive": (
        "Run polling interval must be positive.",
        "The provided --poll-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "run_wait_timeout_seconds_must_be_positive": (
        "Run wait timeout must be positive.",
        "The provided --wait-timeout-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "run_wait_timeout": (
        "The run did not finish before the wait deadline.",
        "Client polling stopped while the server-side run may still be active.",
        "Inspect the run by ID or retry result --run-id later.",
        True,
    ),
    "run_has_no_durable_review": (
        "The run has no durable review workflow.",
        "No review identifier is attached to the run.",
        "Inspect the run state before requesting review details.",
        False,
    ),
    "confirm_source_match_required": (
        "Source confirmation is required.",
        "Evidence verification requires explicit source matching confirmation.",
        "Retry with --confirm-source-match after checking the source.",
        False,
    ),
    "exactly_one_reason_source_required": (
        "Exactly one reason source is required.",
        "The command requires either a reason file or standard input.",
        "Choose one reason input method and retry.",
        False,
    ),
    "rejection_reason_must_be_1_to_1000_characters": (
        "The rejection reason length is invalid.",
        "The reason must contain between 1 and 1000 characters.",
        "Provide a complete reason within the allowed limit.",
        False,
    ),
    "rejection_reason_unreadable": (
        "The rejection reason cannot be read.",
        "The selected input is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 reason and retry.",
        False,
    ),
    "verification_reason_must_be_1_to_1000_characters": (
        "The verification reason length is invalid.",
        "The reason must contain between 1 and 1000 characters.",
        "Provide a complete reason within the allowed limit.",
        False,
    ),
    "verification_reason_unreadable": (
        "The verification reason cannot be read.",
        "The selected input is unavailable or is not valid UTF-8 text.",
        "Provide a readable UTF-8 reason and retry.",
        False,
    ),
    "review_poll_seconds_must_be_positive": (
        "Review polling interval must be positive.",
        "The provided --poll-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "review_wait_timeout_seconds_must_be_positive": (
        "Review wait timeout must be positive.",
        "The provided --wait-timeout-seconds value is zero or negative.",
        "Provide a value greater than zero.",
        False,
    ),
    "review_wait_timeout": (
        "The review did not finish before the wait deadline.",
        "Client polling stopped before the workflow reached a terminal state.",
        "Inspect the review by run ID and retry later.",
        True,
    ),
    "manual_recovery": (
        "The review requires manual recovery.",
        "The durable workflow cannot resume automatically.",
        "Follow the controlled review recovery runbook.",
        False,
    ),
}
```

## Task 0: Confirm The Baseline And Scope Boundary

**Files:**
- Read: `tools/decision_research_agent_tool.py`
- Read: `tests/unit/test_decision_research_agent_tool.py`
- Read: `docs/superpowers/specs/2026-06-29-cli-dx-design.md`

- [ ] **Step 1: Confirm the isolated worktree is clean except for approved design artifacts**

Run:

```bash
git status --short --branch
git diff --check
```

Expected: branch is `codex/cli-dx-design`; no unrelated modified files or
formatting errors are present.

- [ ] **Step 2: Run the existing Tool Client tests**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: the existing suite passes before implementation begins. Record the
actual count in the execution handoff; do not copy an old count into the PR.

- [ ] **Step 3: Reconfirm the hard file boundary**

Run:

```bash
{
  git diff --name-only main...HEAD
  git ls-files --others --exclude-standard
} | sort -u
```

Expected: only the approved spec/plan files are present before code work. Stop
if the implementation would require changes under `api/`, `agent/`, database
code, Docker files, dependency manifests, or frontend code.

- [ ] **Step 4: Record the approved design and execution plan**

After the owner explicitly approves implementation, change the design status
from `Proposed for implementation after owner review.` to
`Approved for implementation.` Then run:

```bash
git add \
  docs/superpowers/specs/2026-06-29-cli-dx-design.md \
  docs/superpowers/plans/2026-06-29-cli-dx-implementation.md
git commit -m "docs(cli): define golden path contract"
```

Expected: both implementation inputs are tracked before production code is
modified. Do not make this commit before owner approval.

## Task 1: Normalize Local And Service Error Envelopes

**Files:**
- Modify: `tools/decision_research_agent_tool.py:16-87`
- Modify: `tools/decision_research_agent_tool.py:428-485`
- Modify: `tools/decision_research_agent_tool.py:550-579`
- Modify: `tools/decision_research_agent_tool.py:831-838`
- Test: `tests/unit/test_decision_research_agent_tool.py`

- [ ] **Step 1: Add failing envelope and privacy tests**

Add this shared assertion near `FakeResponse`:

```python
def assert_error_envelope(payload, *, code):
    assert payload["code"] == code
    assert isinstance(payload["problem"], str) and payload["problem"]
    assert isinstance(payload["cause"], str) and payload["cause"]
    assert isinstance(payload["fix"], str) and payload["fix"]
    assert isinstance(payload["retryable"], bool)
```

Add focused tests that exercise the public `main()` output and lower-level
exception payloads:

```python
@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (tool.error.URLError("https://secret.example/path"), "connection_failed"),
        (TimeoutError("provider token leaked"), "request_timeout"),
    ],
)
def test_transport_failures_are_structured_and_private(
    monkeypatch, capsys, raised, code
):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(raised),
    )

    exit_code = tool.main(["healthcheck"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert_error_envelope(payload, code=code)
    rendered = json.dumps(payload)
    assert "secret.example" not in rendered
    assert "provider token" not in rendered


def test_invalid_json_response_is_structured_and_private(monkeypatch, capsys):
    class InvalidJSONResponse(FakeResponse):
        def read(self):
            return b'{"secret": invalid}'

    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: InvalidJSONResponse({}),
    )

    assert tool.main(["healthcheck"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="invalid_json_response")
    assert "secret" not in json.dumps(payload)


def test_non_object_json_response_is_structured(monkeypatch, capsys):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: FakeResponse(["unexpected"]),
    )

    assert tool.main(["healthcheck"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="json_response_not_object",
    )


def test_structured_http_error_fills_minimum_fields(monkeypatch):
    body = io.BytesIO(
        json.dumps({"code": "run_review_required", "problem": "Review required."}).encode()
    )
    http_error = tool.error.HTTPError(
        "https://secret.example/result", 409, "Conflict", {}, body
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.result("run_1", tool.ToolConfig())

    assert captured.value.status == 409
    assert_error_envelope(captured.value.payload, code="run_review_required")
```

Replace the existing raw HTTP status assertion with:

```python
def test_http_failure_raises_structured_error(monkeypatch):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: FakeResponse({"detail": "bad request"}, status=400),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.healthcheck(tool.ToolConfig())

    assert captured.value.status == 400
    assert_error_envelope(captured.value.payload, code="http_400")
```

- [ ] **Step 2: Run the error tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "transport_failures or invalid_json_response or non_object_json_response or structured_http_error" -q
```

Expected: failures show that local errors still serialize as `{status,error}`
and service payloads can omit required fields.

- [ ] **Step 3: Implement the bounded error model**

Add `_LOCAL_ERROR_DETAILS` exactly as defined in **Stable Error Vocabulary**,
then implement these helpers and exception classes:

```python
def _local_error_payload(
    code: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    problem, cause, fix, retryable = _LOCAL_ERROR_DETAILS[code]
    return {
        "code": code,
        "problem": problem,
        "cause": cause,
        "fix": fix,
        "retryable": retryable,
        **(context or {}),
    }


def _normalize_service_error(
    payload: dict[str, Any],
    *,
    status: int,
) -> dict[str, Any]:
    normalized = dict(payload)
    defaults = {
        "code": f"http_{status}",
        "problem": "The service rejected the request.",
        "cause": "The request could not be completed.",
        "fix": "Inspect the error code and retry when safe.",
    }
    for field, default in defaults.items():
        if not isinstance(normalized.get(field), str) or not normalized[field]:
            normalized[field] = default
    if not isinstance(normalized.get("retryable"), bool):
        normalized["retryable"] = status >= 500
    return normalized


class ToolClientError(RuntimeError):
    """Bounded client error safe for JSON serialization."""

    def __init__(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ):
        self.payload = payload or _local_error_payload(code, context=context)
        super().__init__(self.payload["code"])


class ToolClientHTTPError(ToolClientError):
    """Bounded service error retaining its HTTP status."""

    def __init__(self, status: int, payload: dict[str, Any]):
        self.status = status
        super().__init__(
            str(payload.get("code") or f"http_{status}"),
            payload=_normalize_service_error(payload, status=status),
        )
```

Replace `_read_json()` exception serialization and `_request_json()` transport
handling with stable codes:

```python
def _read_json(response: Any) -> dict[str, Any]:
    raw = response.read()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ToolClientError("invalid_json_response") from exc
    if not isinstance(parsed, dict):
        raise ToolClientError("json_response_not_object")
    return parsed


def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or isinstance(
        getattr(exc, "reason", None), TimeoutError
    )
```

In `_request_json()`:

```python
    except error.HTTPError as exc:
        try:
            parsed = _read_json(exc)
        except ToolClientError:
            parsed = {
                "code": f"http_{exc.code}",
                "problem": "The server returned a non-JSON error.",
            }
        raise ToolClientHTTPError(exc.code, parsed) from exc
    except ToolClientError:
        raise
    except (OSError, error.URLError, TimeoutError) as exc:
        code = "request_timeout" if _is_timeout_error(exc) else "connection_failed"
        raise ToolClientError(code) from exc
    if status < 200 or status >= 300:
        raise ToolClientHTTPError(status, parsed)
```

Finally, make both failure branches in `main()` serialize only the bounded
payload:

```python
    except ToolClientError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2))
        return 1
```

The single base-class handler is sufficient because `ToolClientHTTPError`
inherits `ToolClientError` and already owns a normalized payload.

- [ ] **Step 4: Convert existing domain errors without changing their codes**

Keep existing `raise ToolClientError("...")` call sites for catalogued stable
codes. Replace the dynamic manual-recovery string with bounded context:

```python
def _bounded_error_code(value: Any) -> str:
    rendered = str(value)
    if not 1 <= len(rendered) <= 128:
        return "unknown"
    if not all(character.isalnum() or character in "._-" for character in rendered):
        return "unknown"
    return rendered


        if status == "manual_recovery":
            recovery_code = _bounded_error_code(
                result["workflow"].get("last_error_code") or "unknown"
            )
            raise ToolClientError(
                "manual_recovery",
                context={"recovery_code": recovery_code},
            )
```

Update the current manual recovery test and add catalog coverage:

```python
def test_wait_for_review_fails_closed_on_manual_recovery(monkeypatch):
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "workflow": {
                "status": "manual_recovery",
                "last_error_code": "checkpoint_corrupt",
            }
        },
    )

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )

    assert_error_envelope(captured.value.payload, code="manual_recovery")
    assert captured.value.payload["recovery_code"] == "checkpoint_corrupt"


@pytest.mark.parametrize("code", sorted(tool._LOCAL_ERROR_DETAILS))
def test_local_error_catalog_always_builds_minimum_envelope(code):
    assert_error_envelope(tool.ToolClientError(code).payload, code=code)
```

Add the unsafe recovery-code regression test:

```python
def test_manual_recovery_does_not_expose_unbounded_error_code(monkeypatch):
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "workflow": {
                "status": "manual_recovery",
                "last_error_code": "/private/path",
            }
        },
    )

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )

    assert captured.value.payload["recovery_code"] == "unknown"
    assert "/private/path" not in json.dumps(captured.value.payload)
```

- [ ] **Step 5: Run the complete Tool Client suite**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: PASS; existing success payload tests remain unchanged.

- [ ] **Step 6: Commit the error boundary**

```bash
git add tools/decision_research_agent_tool.py tests/unit/test_decision_research_agent_tool.py
git commit -m "refactor(cli): normalize tool client errors"
```

## Task 2: Add Bounded Run Polling

**Files:**
- Modify: `tools/decision_research_agent_tool.py:533-547`
- Modify: `tools/decision_research_agent_tool.py:616-622`
- Test: `tests/unit/test_decision_research_agent_tool.py:776-793`

- [ ] **Step 1: Add failing deadline and parser tests**

Add a reusable fake clock and run-specific tests alongside the existing review
wait tests:

```python
class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_run_wait_parser_defaults():
    args = tool._build_parser().parse_args(["run", "--query", "q", "--wait"])

    assert args.result is False
    assert args.poll_seconds == 1
    assert args.wait_timeout_seconds == 600


@pytest.mark.parametrize(
    ("poll_seconds", "timeout_seconds", "code"),
    [
        (0, 1, "run_poll_seconds_must_be_positive"),
        (1, 0, "run_wait_timeout_seconds_must_be_positive"),
    ],
)
def test_wait_for_run_rejects_non_positive_bounds(
    poll_seconds, timeout_seconds, code
):
    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_run(
            "run_1",
            tool.ToolConfig(),
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )

    assert captured.value.payload["code"] == code


def test_wait_for_run_sleep_does_not_cross_deadline(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(tool.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(tool.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        tool,
        "get_run",
        lambda run_id, config: {"execution_status": "running"},
    )

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_run(
            "run_1",
            tool.ToolConfig(),
            poll_seconds=10,
            timeout_seconds=1,
        )

    assert captured.value.payload["code"] == "run_wait_timeout"
    assert clock.now == 1
    assert clock.sleeps == [1]
```

Replace the existing terminal-state test with:

```python
@pytest.mark.parametrize(
    "terminal_status",
    ["completed", "completed_with_fallback", "failed"],
)
def test_wait_for_run_polls_until_terminal(monkeypatch, terminal_status):
    responses = iter(
        [
            {"run_id": "run-1", "execution_status": "running"},
            {"run_id": "run-1", "execution_status": terminal_status},
        ]
    )
    monkeypatch.setattr(tool, "get_run", lambda run_id, config: next(responses))
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    result = tool.wait_for_run(
        "run-1",
        tool.ToolConfig(),
        poll_seconds=0.01,
        timeout_seconds=1,
    )

    assert result["execution_status"] == terminal_status
```

- [ ] **Step 2: Run the bounded-wait tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "run_wait_parser or wait_for_run" -q
```

Expected: parser attributes and `timeout_seconds` do not exist, and polling can
sleep indefinitely.

- [ ] **Step 3: Add parser flags and monotonic deadline logic**

Add the flags to the existing `run` parser:

```python
    run.add_argument("--wait", action="store_true")
    run.add_argument("--result", action="store_true")
    run.add_argument("--poll-seconds", type=float, default=1)
    run.add_argument("--wait-timeout-seconds", type=float, default=600)
```

Replace `wait_for_run()` with:

```python
def wait_for_run(
    run_id: str,
    config: ToolConfig,
    *,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    if poll_seconds <= 0:
        raise ToolClientError("run_poll_seconds_must_be_positive")
    if timeout_seconds <= 0:
        raise ToolClientError("run_wait_timeout_seconds_must_be_positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        run = get_run(run_id, config)
        if run.get("execution_status") in {
            "completed",
            "completed_with_fallback",
            "failed",
        }:
            return run
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ToolClientError("run_wait_timeout")
        time.sleep(min(poll_seconds, remaining))
```

This deliberately performs one immediate poll. The total deadline controls
subsequent polling sleeps; it does not replace the per-request HTTP timeout.

- [ ] **Step 4: Run focused and complete Tool Client tests**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "run_wait_parser or wait_for_run" -q
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: both commands pass.

- [ ] **Step 5: Commit bounded polling**

```bash
git add tools/decision_research_agent_tool.py tests/unit/test_decision_research_agent_tool.py
git commit -m "fix(cli): bound run polling"
```

## Task 3: Compose The Canonical Run Result Golden Path

**Files:**
- Modify: `tools/decision_research_agent_tool.py:705-728`
- Test: `tests/unit/test_decision_research_agent_tool.py:183-335`

- [ ] **Step 1: Add failing command-composition tests**

Add these tests around the current run/result consumer-flow coverage:

```python
def test_cli_run_result_requires_wait_before_network(monkeypatch, capsys):
    monkeypatch.setattr(
        tool,
        "start_run",
        lambda **kwargs: pytest.fail("network path must not be called"),
    )

    assert tool.main(["run", "--query", "q", "--result"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="result_requires_wait",
    )


@pytest.mark.parametrize("run_id", [None, "", 123])
def test_cli_run_wait_rejects_invalid_creation_run_id(
    monkeypatch, capsys, run_id
):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": run_id})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: pytest.fail("invalid run_id must fail first"),
    )

    assert tool.main(["run", "--query", "q", "--wait"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="run_response_invalid",
    )


def test_cli_run_wait_result_prints_only_canonical_result(monkeypatch, capsys):
    calls = []

    def fake_wait(
        run_id, config, *, poll_seconds, timeout_seconds
    ):
        calls.append(("poll", poll_seconds, timeout_seconds))
        return {"run_id": run_id, "execution_status": "completed"}

    monkeypatch.setattr(
        tool,
        "start_run",
        lambda **kwargs: calls.append(("create",)) or {"run_id": "run_1"},
    )
    monkeypatch.setattr(tool, "wait_for_run", fake_wait)
    monkeypatch.setattr(
        tool,
        "result",
        lambda *args, **kwargs: calls.append(("result",))
        or {"run_id": "run_1", "artifact": {"content": "# Report"}},
    )

    exit_code = tool.main(
        [
            "run", "--query", "q", "--wait", "--result",
            "--poll-seconds", "0.25",
            "--wait-timeout-seconds", "30",
        ]
    )

    assert exit_code == 0
    assert calls == [("create",), ("poll", 0.25, 30), ("result",)]
    assert json.loads(capsys.readouterr().out) == {
        "run_id": "run_1",
        "artifact": {"content": "# Report"},
    }
```

Add a failure test where `result()` raises:

```python
def test_cli_run_result_error_retains_service_code_and_safe_run_id(
    monkeypatch, capsys
):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": "run_1"})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: {"execution_status": "completed"},
    )
    monkeypatch.setattr(
        tool,
        "result",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                409,
                {
                    "code": "run_review_required",
                    "problem": "Review required.",
                    "fix": "Resolve the controlled review.",
                },
            )
        ),
    )

    assert tool.main(
        ["run", "--query", "private query", "--wait", "--result"]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="run_review_required")
    assert payload["run_id"] == "run_1"
    assert "private query" not in json.dumps(payload)
```

Add the local timeout recovery test explicitly:

```python
def test_cli_run_wait_timeout_includes_only_safe_run_context(monkeypatch, capsys):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": "run_1"})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            tool.ToolClientError("run_wait_timeout")
        ),
    )

    assert tool.main(
        ["run", "--query", "private query", "--wait"]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="run_wait_timeout")
    assert payload["run_id"] == "run_1"
    rendered = json.dumps(payload)
    assert "private query" not in rendered
    assert "thread" not in payload
```

- [ ] **Step 2: Run the composition tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "run_result_requires or invalid_creation_run_id or prints_only_canonical or safe_run_id" -q
```

Expected: `--result` is not composed, creation responses are indexed without
validation, and post-create failures do not carry recovery context.

- [ ] **Step 3: Add bounded scope-file loading**

Add this helper before `start_run()`:

```python
def read_scope_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ToolClientError("scope_file_unreadable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolClientError("scope_file_invalid") from exc
    if not isinstance(parsed, dict):
        raise ToolClientError("scope_file_invalid")
    return parsed
```

Add exact scope tests:

```python
def test_scope_file_unreadable_is_private(tmp_path):
    path = tmp_path / "private-scope.json"
    with pytest.raises(tool.ToolClientError) as captured:
        tool.read_scope_file(path)

    assert_error_envelope(captured.value.payload, code="scope_file_unreadable")
    assert str(path) not in json.dumps(captured.value.payload)


@pytest.mark.parametrize("content", ['{"broken":', "[]"])
def test_scope_file_invalid_is_private(tmp_path, content):
    path = tmp_path / "private-scope.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(tool.ToolClientError) as captured:
        tool.read_scope_file(path)

    assert_error_envelope(captured.value.payload, code="scope_file_invalid")
    rendered = json.dumps(captured.value.payload)
    assert str(path) not in rendered
    assert content not in rendered
```

- [ ] **Step 4: Add safe post-create error context**

Add a helper that retains the error subtype and service status:

```python
def _with_error_context(
    exc: ToolClientError,
    *,
    context: dict[str, Any],
) -> ToolClientError:
    payload = {**exc.payload, **context}
    if isinstance(exc, ToolClientHTTPError):
        return ToolClientHTTPError(exc.status, payload)
    return ToolClientError(str(payload["code"]), payload=payload)
```

Only pass `{"run_id": run_id}` from the composed run path. Do not pass query,
scope, thread ID, endpoint URL, API key, or provider configuration.

- [ ] **Step 5: Implement the command composition in `main()`**

Replace the `run` branch with this control flow:

```python
        elif args.command == "run":
            if args.result and not args.wait:
                raise ToolClientError("result_requires_wait")
            scope = (
                read_scope_file(Path(args.scope_file))
                if args.scope_file
                else {}
            )
            created = start_run(
                query=args.query,
                thread_id=args.thread_id,
                profile_id=args.profile,
                scope=scope,
                config=config,
            )
            if not args.wait:
                result = created
            else:
                run_id = created.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ToolClientError("run_response_invalid")
                try:
                    terminal = wait_for_run(
                        run_id,
                        config,
                        poll_seconds=args.poll_seconds,
                        timeout_seconds=args.wait_timeout_seconds,
                    )
                    result_fn = globals()["result"]
                    result = result_fn(run_id, config) if args.result else terminal
                except ToolClientError as exc:
                    raise _with_error_context(
                        exc,
                        context={"run_id": run_id},
                    ) from exc
```

Use `globals()["result"]` consistently with the existing separate command
branch because `result` is also the local output variable in `main()`.

- [ ] **Step 6: Replace the old two-command consumer test with the golden path**

Update `test_cli_run_wait_then_result_is_secret_safe_consumer_flow` to invoke
one command containing `--wait --result`:

```python
    exit_code = tool.main(
        [
            "--base-url",
            "http://127.0.0.1:9000",
            "run",
            "--query",
            "bounded public smoke",
            "--thread-id",
            "thread_1",
            "--wait",
            "--result",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "run_id": "run_1",
        "artifact": {
            "artifact_id": "research-report.md",
            "content": "# Report",
        },
    }
    assert "secret-key" not in captured.out
    assert "secret-key" not in captured.err
```

Keep the request-order assertions:

```python
assert [item["method"] for item in requests] == ["POST", "GET", "GET"]
assert [item["url"] for item in requests] == [
    "http://127.0.0.1:9000/api/runs",
    "http://127.0.0.1:9000/api/runs/run_1",
    "http://127.0.0.1:9000/api/runs/run_1/result",
]
```

Assert one JSON document is printed and that it is the canonical result, not
the creation or terminal run projection.

- [ ] **Step 7: Run focused and complete Tool Client tests**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "scope_file or run_wait or run_result or consumer_flow" -q
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: all focused and complete Tool Client tests pass.

- [ ] **Step 8: Commit the golden path**

```bash
git add tools/decision_research_agent_tool.py tests/unit/test_decision_research_agent_tool.py
git commit -m "feat(cli): add canonical run result flow"
```

## Task 4: Document The Shipped CLI Contract

**Files:**
- Modify: `README.md:84-120`
- Modify: `docs/AGENT_INTEGRATION.md:54-89`
- Modify: `docs/AGENT_INTEGRATION.md:172-188`
- Modify: `TODOS.md:38-46`
- Test: `tests/unit/test_decision_research_agent_tool.py`

- [ ] **Step 1: Add a failing public documentation contract test**

Add a test that reads the public docs from the repository root:

```python
def test_public_docs_describe_cli_golden_path_and_error_contract():
    readme = Path("README.md").read_text(encoding="utf-8")
    integration = Path("docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")

    assert "--wait --result" in readme
    assert "--wait-timeout-seconds" in integration
    assert "run_wait_timeout" in integration
    for field in ("code", "problem", "cause", "fix", "retryable"):
        assert f"`{field}`" in integration
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "public_docs_describe_cli_golden_path" -q
```

Expected: FAIL because the golden-path flags and complete minimum envelope are
not yet documented.

- [ ] **Step 3: Update `README.md` with the shortest successful path**

Add this example to the Tool Client section without removing the separate
`run` and `result` reference commands:

```bash
python tools/decision_research_agent_tool.py run \
  --query "Compare the evidence behind the proposed decision" \
  --wait \
  --result
```

State that the command prints only the canonical result payload. State that
the backend must already be running and that a run requiring controlled review
returns a structured recovery error instead of bypassing review.

- [ ] **Step 4: Update the integration reference**

Document all three run flags and defaults:

```text
--result                     fetch the canonical result after terminal execution
--poll-seconds FLOAT         polling interval, default 1
--wait-timeout-seconds FLOAT total polling deadline, default 600
```

Document these compatibility rules:

- `run` still prints the creation response.
- `run --wait` still prints the terminal run projection.
- `run --wait --result` prints only the canonical result.
- `--result` without `--wait` performs no request.
- timeout does not cancel the server-side run; the error includes `run_id`.
- `result --run-id` remains available for later recovery.

Add the five-field error example from the design and state that service-owned
fields are preserved while missing minimum fields are filled by the client.

- [ ] **Step 5: Close the two CLI DX checklist entries**

In `TODOS.md`, mark the bounded golden path and consistent structured errors as
completed. Keep deferred JSON/PDF export and UI work unchanged; do not add a
new feature commitment.

- [ ] **Step 6: Run docs-focused verification**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py \
  -k "public_docs_describe_cli_golden_path" -q
python scripts/final_presentation_audit.py --root .
python scripts/check_canonical_identity.py --root .
```

Expected: test passes and both audits return `status=ok` with no violations.

- [ ] **Step 7: Commit documentation**

```bash
git add README.md docs/AGENT_INTEGRATION.md TODOS.md tests/unit/test_decision_research_agent_tool.py
git commit -m "docs(cli): document golden result flow"
```

## Task 5: Run Final Verification And Prepare The Review Handoff

**Files:**
- Verify: all files changed from `main`
- Do not modify: server, runtime, database, dependency, Docker, benchmark, or frontend files

- [ ] **Step 1: Run the focused suite**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py -q
```

Expected: all Tool Client tests pass with no newly introduced warning.

- [ ] **Step 2: Run the full Python suite**

Run:

```bash
python -m pytest -q
```

Expected: full suite passes. Record the fresh count and warning count rather
than reusing any release-era number.

- [ ] **Step 3: Run release presentation and identity checks**

Run:

```bash
python scripts/final_presentation_audit.py --root .
python scripts/check_canonical_identity.py --root .
git diff --check main...HEAD
```

Expected: both scripts report `status=ok`; diff check prints no output.

- [ ] **Step 4: Verify scope and privacy mechanically**

Run:

```bash
git diff --name-only main...HEAD
rg -n "/U[s]ers|Developer/[C]areer|求[职]|面[试]|api[_-]?key[=:]|Traceback \\(most recent call last\\)" \
  README.md docs/AGENT_INTEGRATION.md TODOS.md \
  docs/superpowers/specs/2026-06-29-cli-dx-design.md \
  docs/superpowers/plans/2026-06-29-cli-dx-implementation.md
```

Expected: changed files are limited to the approved map. The privacy scan has
no match; references to literal error field names in tests are acceptable only
when they contain no secret value or raw diagnostic.

- [ ] **Step 5: Confirm excluded gates remain unnecessary**

Do not run Docker, durable HITL, real-source proof, provider, benchmark, or
frontend gates unless the actual diff unexpectedly touches one of those
contracts. If it does, stop instead of silently expanding verification scope.

- [ ] **Step 6: Prepare a clean local handoff**

Run:

```bash
git status --short --branch
git log --oneline main..HEAD
git diff --stat main...HEAD
```

Expected: worktree is clean and the branch contains the planned focused
commits. Report RED/GREEN evidence, fresh test results, audit results, diff
scope, and explicit non-goals. Do not push, create a PR, merge, tag, release,
deploy, or delete the worktree without separate owner authorization.

## Stop Conditions

Stop implementation and return to the planning window if any of these occurs:

1. The golden path needs a server API, schema, artifact, or status change.
2. A new dependency is required.
3. The implementation needs files under `api/`, `agent/`, migrations,
   persistence, Docker, benchmark, or frontend surfaces.
4. Existing success payloads must change beyond the approved
   `run --wait --result` behavior and bounded default timeout.
5. A proposed diagnostic requires serializing raw exceptions, response bodies,
   URLs, local paths, queries, scope data, thread IDs, provider settings, or
   secrets.
6. Full tests or release audits fail for a reason outside the approved client
   and documentation scope.

## Review Depth

This is a Level 2 Tool Client behavior change. A full Autoplan is not required.
After implementation and full verification, run one lightweight pre-PR review
focused on:

- compatibility of existing commands and success output;
- monotonic deadline and no-oversleep behavior;
- preservation of service-owned error codes;
- absence of raw diagnostics and sensitive context;
- documentation matching the executable parser and actual output.

Use targeted re-review after fixes. Escalate to a full plan review only when a
stop condition expands the architecture or public service contract.
