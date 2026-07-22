# Bounded Result Diagnostic Receipt v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one opt-in, provider-free-tested, public-safe result diagnostic receipt that makes the next `consumer_projection_invalid` live failure actionable without changing the existing public error, runtime contract, cleanup boundary, or business authority.

**Architecture:** Extend the existing strict evaluation error with optional proof-owned result diagnostic metadata, classify each generic result rejection at the HTTP and consumer-projection boundaries, and publish one JSON-only receipt to a preflighted repo-external owner-only directory after cleanup. The existing public error envelope remains unchanged; the new receipt is non-authoritative, fixed-name, non-overwriting, and absent unless the operator explicitly supplies `--diagnostic-dir`.

**Tech Stack:** Python 3.11, Pydantic v2 strict models, standard-library `http.client`, descriptor-relative filesystem APIs, pytest, existing bounded live producer proof contracts.

## Global Constraints

- Implement against `origin/main@f0d7e440438d18bb2941f01ec8b7b11625a6ef1b` plus the approved spec commit already present on the task branch.
- Keep `VERSION=0.1.5` and do not add release metadata, live evidence, migrations, dependencies, framework changes, or CI provider activity.
- Preserve byte-identical default serialization for `dra.bounded-live-producer-evaluation-error.v1` and `bounded_live_producer_proof.py check`.
- `observe-live` without `--diagnostic-dir` must remain behaviorally and byte compatible.
- The diagnostic receipt is eligible only for `consumer_projection_invalid` in phase `result`; existing artifact, hash, Evidence, state, fallback, create, usage, restart, replay, output, cleanup, and internal classifications remain authoritative.
- Do not change REST/OpenAPI, API/DB/Agent code, canonical result, Evidence, downstream consumer acceptance semantics, LangChain, DeepAgents, LangGraph, LangSmith, middleware order, provider/model budgets, Dockerfile, Compose, or frontend code.
- Do not retain or serialize raw response bytes, body strings, artifact content, Evidence content, response key names, URLs, headers, queries, ports, Docker identifiers, exceptions, tracebacks, paths, credentials, provider/model IDs, request IDs, or secret-derived values.
- The receipt contains only closed enums, bounded integers, and the existing public primary error fields.
- The output directory is absolute, repo-external, pre-existing, non-symlinked, owned by the effective user, owner-writable and owner-searchable, and has no group/world permission bits. The output basename is fixed to `bounded-live-producer-result-diagnostic-v1.json`.
- Publication is JSON-only, at most 4 KiB, mode `0600`, descriptor-relative, `O_NOFOLLOW` where available, exclusive, atomic without overwrite, file- and directory-`fsync` bounded by remaining outer time.
- Build diagnostic facts before cleanup, publish only after final cleanup status is known, and never let diagnostic publication replace the original result failure or cleanup failure.
- No live/provider/model/search/credential operation is authorized by this plan. Required tests are deterministic and provider-free.
- TDD is mandatory. Each task starts with an observed RED failure, reaches focused GREEN, and commits only its owned files.

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `scripts/bounded_live_producer_contracts.py` | Diagnostic enums, strict models, valid stage/reason registry, optional `EvaluationError` metadata, canonical receipt serialization, shared response-byte bound |
| `scripts/bounded_live_producer_http.py` | Attach exact structural diagnostic metadata to generic result transport/status/body/JSON/identity failures only |
| `scripts/bounded_live_producer_diagnostics.py` | Preflight one owner-only repo-external directory and publish the fixed diagnostic file safely without overwrite |
| `scripts/bounded_live_producer_proof.py` | Preserve consumer/projection diagnostic metadata through cleanup/group projection, wire optional CLI sink, and publish after cleanup |
| `tests/unit/test_bounded_live_producer_contracts.py` | Strict schema, serializer, registry, public-envelope compatibility, and unsafe-data rejection |
| `tests/unit/test_bounded_live_producer_http.py` | Exact result-stage classification and unchanged non-result/public behavior |
| `tests/unit/test_bounded_live_producer_diagnostics.py` | Directory ownership, symlink/race, fixed-name, atomic publication, bounds, non-overwrite, and cleanup tests |
| `tests/integration/test_bounded_live_producer_proof.py` | Consumer mapping, lifecycle ordering, dual failure, CLI, success absence, and publication-failure behavior |
| `docs/reference/bounded-live-producer-evaluation.md` | Operator-facing diagnostic use, receipt contract, privacy boundary, and stop condition |
| `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md` | Narrow post-observation amendment superseding only the old no-output-option statement |
| `docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md` | Historical-plan amendment recording the fixed diagnostic directory exception and unchanged live gates |
| `docs/superpowers/specs/2026-07-22-bounded-result-diagnostic-receipt-design.md` | Approved authority for this implementation; unchanged unless a verified contradiction requires a targeted correction |
| `docs/superpowers/plans/2026-07-22-bounded-result-diagnostic-receipt-implementation.md` | This implementation plan |
| `tests/unit/test_documentation_contracts.py` | Exact discovery, compatibility, non-claims, and amendment contracts |

## Ordering And Parallel Work

Task 1 owns the shared diagnostic contract and must run first. After Task 1 commits, Tasks 2 and 3 are independent and may run in parallel when the execution parent has safe subagent support:

```text
Task 1 shared contracts
  ├─ Task 2 HTTP classification
  └─ Task 3 safe diagnostic sink
       ↓
Task 4 proof/lifecycle integration
       ↓
Task 5 documentation and full verification
```

Task 2 owns only `bounded_live_producer_http.py` and its unit test. Task 3 owns only the new diagnostics module and its unit test. The parent owns contracts, proof integration, documentation, final branch state, and full verification. If parallel execution is unavailable or coordination cost is higher than the expected gain, execute Tasks 2 and 3 serially without changing task content.

---

### Task 1: Define Strict Diagnostic Contracts

**Files:**
- Modify: `scripts/bounded_live_producer_contracts.py`
- Modify: `tests/unit/test_bounded_live_producer_contracts.py`

**Interfaces:**
- Consumes: existing `StrictModel`, `CleanupStatus`, `FailureCode`, `FailurePhase`, `EvaluationError`, `serialize_error`.
- Produces: `MAX_HTTP_RESPONSE_BYTES`, `MAX_DIAGNOSTIC_BYTES`, `RESULT_DIAGNOSTIC_SCHEMA_VERSION`, `ResultDiagnosticStage`, `ResultDiagnosticReason`, `ResultBoundaryDiagnostic`, `ResultDiagnosticPrimary`, `ResultDiagnosticReceipt`, `serialize_result_diagnostic(error: EvaluationError) -> bytes`, and `EvaluationError.diagnostic`.

- [ ] **Step 1: Write RED strict-contract tests**

Add imports and focused tests that define the exact interface:

```python
from scripts.bounded_live_producer_contracts import (
    MAX_DIAGNOSTIC_BYTES,
    CleanupStatus,
    EvaluationError,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticReceipt,
    ResultDiagnosticStage,
    serialize_error,
    serialize_result_diagnostic,
)


def _diagnostic() -> ResultBoundaryDiagnostic:
    return ResultBoundaryDiagnostic(
        stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
        reason=ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
        http_status=200,
        response_bytes=1234,
    )


def test_result_diagnostic_receipt_is_strict_exact_and_bounded() -> None:
    error = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )
    raw = serialize_result_diagnostic(error)
    receipt = ResultDiagnosticReceipt.model_validate_json(raw, strict=True)

    assert len(raw) <= MAX_DIAGNOSTIC_BYTES
    assert receipt.model_dump(mode="json") == {
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
            "response_bytes": 1234,
        },
    }


def test_default_public_error_bytes_ignore_internal_diagnostic() -> None:
    baseline = EvaluationError(
        "consumer_projection_invalid", "result", False, CleanupStatus.SUCCEEDED
    )
    enriched = EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=_diagnostic(),
    )
    assert serialize_error(enriched) == serialize_error(baseline)
```

Add parameterized tests for every valid stage/reason pair and reject cross-pairs, `bool` as integer, status outside `100..599`, response bytes outside `0..2_097_152`, extra keys, mutable model assignment, a non-`ResultBoundaryDiagnostic` metadata object, diagnostic metadata on an ineligible primary error, raw/private string injection, and a silent subprocess import. The expected eligible pair table is:

```python
VALID_PAIRS = {
    "connection": {"connection_failed"},
    "response_status": {"response_status_invalid"},
    "response_body": {"response_read_failed", "response_size_exceeded"},
    "response_json": {
        "response_utf8_invalid",
        "response_json_invalid",
        "response_not_object",
    },
    "response_identity": {"run_identity_mismatch"},
    "consumer_contract": {"contract_result_invalid", "contract_schema_invalid"},
    "projection_disposition": {"projection_disposition_invalid"},
}
```

- [ ] **Step 2: Run the new tests and capture RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  -k 'diagnostic or default_public_error_bytes'
```

Expected: collection or assertion failures because the diagnostic constants, enums, models, serializer, and `EvaluationError.diagnostic` do not exist.

- [ ] **Step 3: Implement the strict models and internal metadata**

Move the existing `StrictModel` definition before the new models without changing its configuration, move the shared HTTP bound into this contract module, and add:

```python
RESULT_DIAGNOSTIC_SCHEMA_VERSION = (
    "dra.bounded-live-producer-result-diagnostic.v1"
)
MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 4 * 1024


class ResultDiagnosticStage(str, Enum):
    CONNECTION = "connection"
    RESPONSE_STATUS = "response_status"
    RESPONSE_BODY = "response_body"
    RESPONSE_JSON = "response_json"
    RESPONSE_IDENTITY = "response_identity"
    CONSUMER_CONTRACT = "consumer_contract"
    PROJECTION_DISPOSITION = "projection_disposition"


class ResultDiagnosticReason(str, Enum):
    CONNECTION_FAILED = "connection_failed"
    RESPONSE_STATUS_INVALID = "response_status_invalid"
    RESPONSE_READ_FAILED = "response_read_failed"
    RESPONSE_SIZE_EXCEEDED = "response_size_exceeded"
    RESPONSE_UTF8_INVALID = "response_utf8_invalid"
    RESPONSE_JSON_INVALID = "response_json_invalid"
    RESPONSE_NOT_OBJECT = "response_not_object"
    RUN_IDENTITY_MISMATCH = "run_identity_mismatch"
    CONTRACT_RESULT_INVALID = "contract_result_invalid"
    CONTRACT_SCHEMA_INVALID = "contract_schema_invalid"
    PROJECTION_DISPOSITION_INVALID = "projection_disposition_invalid"


_RESULT_DIAGNOSTIC_PAIRS = {
    ResultDiagnosticStage.CONNECTION: frozenset(
        {ResultDiagnosticReason.CONNECTION_FAILED}
    ),
    ResultDiagnosticStage.RESPONSE_STATUS: frozenset(
        {ResultDiagnosticReason.RESPONSE_STATUS_INVALID}
    ),
    ResultDiagnosticStage.RESPONSE_BODY: frozenset(
        {
            ResultDiagnosticReason.RESPONSE_READ_FAILED,
            ResultDiagnosticReason.RESPONSE_SIZE_EXCEEDED,
        }
    ),
    ResultDiagnosticStage.RESPONSE_JSON: frozenset(
        {
            ResultDiagnosticReason.RESPONSE_UTF8_INVALID,
            ResultDiagnosticReason.RESPONSE_JSON_INVALID,
            ResultDiagnosticReason.RESPONSE_NOT_OBJECT,
        }
    ),
    ResultDiagnosticStage.RESPONSE_IDENTITY: frozenset(
        {ResultDiagnosticReason.RUN_IDENTITY_MISMATCH}
    ),
    ResultDiagnosticStage.CONSUMER_CONTRACT: frozenset(
        {
            ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
            ResultDiagnosticReason.CONTRACT_SCHEMA_INVALID,
        }
    ),
    ResultDiagnosticStage.PROJECTION_DISPOSITION: frozenset(
        {ResultDiagnosticReason.PROJECTION_DISPOSITION_INVALID}
    ),
}


class ResultBoundaryDiagnostic(StrictModel):
    stage: ResultDiagnosticStage
    reason: ResultDiagnosticReason
    http_status: int | None
    response_bytes: int | None

    @model_validator(mode="after")
    def validate_pair_and_bounds(self) -> "ResultBoundaryDiagnostic":
        if self.reason not in _RESULT_DIAGNOSTIC_PAIRS[self.stage]:
            raise ValueError("result_diagnostic_pair_invalid")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("result_diagnostic_status_invalid")
        if self.response_bytes is not None and not (
            0 <= self.response_bytes <= MAX_HTTP_RESPONSE_BYTES
        ):
            raise ValueError("result_diagnostic_size_invalid")
        return self


class ResultDiagnosticPrimary(StrictModel):
    code: Literal[FailureCode.CONSUMER_PROJECTION_INVALID]
    phase: Literal[FailurePhase.RESULT]
    retryable: Literal[False]
    cleanup_status: CleanupStatus


class ResultDiagnosticReceipt(StrictModel):
    schema_version: Literal[
        "dra.bounded-live-producer-result-diagnostic.v1"
    ]
    primary: ResultDiagnosticPrimary
    result_boundary: ResultBoundaryDiagnostic
```

Extend `EvaluationError` without changing its four existing arguments:

```python
__slots__ = ("code", "phase", "retryable", "cleanup_status", "diagnostic")

def __init__(
    self,
    code: FailureCode | str,
    phase: FailurePhase | str,
    retryable: bool,
    cleanup_status: CleanupStatus | str = CleanupStatus.NOT_STARTED,
    *,
    diagnostic: ResultBoundaryDiagnostic | None = None,
) -> None:
    # keep existing validation
    if diagnostic is not None and (
        type(diagnostic) is not ResultBoundaryDiagnostic
        or validated_code is not FailureCode.CONSUMER_PROJECTION_INVALID
        or validated_phase is not FailurePhase.RESULT
    ):
        raise ValueError("evaluation_error_invalid")
    self.diagnostic = diagnostic
```

Add the canonical serializer near `serialize_error`:

```python
def serialize_result_diagnostic(error: EvaluationError) -> bytes:
    if error.diagnostic is None:
        _validation_fail("diagnostic_invalid")
    receipt = ResultDiagnosticReceipt(
        schema_version=RESULT_DIAGNOSTIC_SCHEMA_VERSION,
        primary=ResultDiagnosticPrimary(
            code=error.code,
            phase=error.phase,
            retryable=error.retryable,
            cleanup_status=error.cleanup_status,
        ),
        result_boundary=error.diagnostic,
    )
    raw = (
        json.dumps(
            receipt.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(raw) > MAX_DIAGNOSTIC_BYTES:
        _validation_fail("diagnostic_invalid")
    _assert_public_safe(receipt.model_dump(mode="json"))
    return raw
```

Keep `serialize_error` unchanged.

- [ ] **Step 4: Run focused contracts GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py
```

Expected: all contract tests pass, including exact old error bytes.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_contracts.py
git commit -m "feat(eval): define bounded result diagnostics"
```

---

### Task 2: Classify HTTP Result Failures

**Files:**
- Modify: `scripts/bounded_live_producer_http.py`
- Modify: `tests/unit/test_bounded_live_producer_http.py`

**Interfaces:**
- Consumes: Task 1 `MAX_HTTP_RESPONSE_BYTES`, `ResultBoundaryDiagnostic`, `ResultDiagnosticStage`, `ResultDiagnosticReason`, and `EvaluationError(..., diagnostic=...)`.
- Produces: every generic `ProofHttpClient.result()` failure carries one exact structural diagnostic; all other HTTP methods and public codes remain unchanged.

- [ ] **Step 1: Write RED HTTP classification tests**

Add a helper that asserts the unchanged public code plus exact internal metadata:

```python
def _assert_result_diagnostic(
    error: EvaluationError,
    *,
    stage: str,
    reason: str,
    http_status: int | None,
    response_bytes: int | None,
) -> None:
    assert error.code.value == "consumer_projection_invalid"
    assert error.phase.value == "result"
    assert error.diagnostic is not None
    assert error.diagnostic.model_dump(mode="json") == {
        "stage": stage,
        "reason": reason,
        "http_status": http_status,
        "response_bytes": response_bytes,
    }
```

Add focused tests for connection/getresponse failure, invalid status type/range, malformed or
negative declared length, oversized declared and streamed bodies, read failure, invalid UTF-8,
invalid JSON, non-object JSON, unexpected complete `404/409/500`, and run identity mismatch. A
representative test is:

```python
def test_result_classifies_invalid_json_without_retaining_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _client(
        monkeypatch,
        FakeResponse(status=200, body=b"not-json"),
    )
    with pytest.raises(EvaluationError) as caught:
        client.result(run_id="run-1")
    _assert_result_diagnostic(
        caught.value,
        stage="response_json",
        reason="response_json_invalid",
        http_status=200,
        response_bytes=8,
    )
    assert "not-json" not in repr(caught.value)
```

Add regression tests that exact canonical `409 run_result_unavailable` still maps to
`artifact_invalid` with `diagnostic is None`, valid result returns normally, and `health`, `create`,
`status`, and `usage` retain existing classifications without diagnostic metadata. Preserve the
existing `run_observation_deadline/observe` classification when the deadline itself rejects the
request; it is not a result transport diagnostic.

- [ ] **Step 2: Run HTTP tests and capture RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_http.py \
  -k 'result or diagnostic'
```

Expected: diagnostic assertions fail because current result failures still carry only the public
code.

- [ ] **Step 3: Implement result-only stage metadata**

Import Task 1 contracts and remove the local duplicate byte bound:

```python
from scripts.bounded_live_producer_contracts import (
    MAX_HTTP_RESPONSE_BYTES,
    EvaluationError,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticStage,
)
```

Give `_BodyReadFailure` a closed reason without response content:

```python
class _BodyReadFailure(Exception):
    def __init__(self, reason: ResultDiagnosticReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _result_diagnostic(
    stage: ResultDiagnosticStage,
    reason: ResultDiagnosticReason,
    *,
    status: int | None = None,
    response_bytes: int | None = None,
) -> ResultBoundaryDiagnostic:
    return ResultBoundaryDiagnostic(
        stage=stage,
        reason=reason,
        http_status=status,
        response_bytes=response_bytes,
    )
```

Add `result_diagnostic: bool = False` to `_request_json`. Split UTF-8 and JSON parsing so exact
reasons can be attached only when that flag is true:

```python
def _load_object_json(
    raw: bytes,
    *,
    code: str,
    phase: str,
    result_diagnostic: bool = False,
    response_status: int | None = None,
) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        diagnostic = (
            _result_diagnostic(
                ResultDiagnosticStage.RESPONSE_JSON,
                ResultDiagnosticReason.RESPONSE_UTF8_INVALID,
                status=response_status,
                response_bytes=len(raw),
            )
            if result_diagnostic
            else None
        )
        raise EvaluationError(code, phase, False, diagnostic=diagnostic) from None
    try:
        parsed = json.loads(
            decoded,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (json.JSONDecodeError, ValueError):
        diagnostic = (
            _result_diagnostic(
                ResultDiagnosticStage.RESPONSE_JSON,
                ResultDiagnosticReason.RESPONSE_JSON_INVALID,
                status=response_status,
                response_bytes=len(raw),
            )
            if result_diagnostic
            else None
        )
        raise EvaluationError(code, phase, False, diagnostic=diagnostic) from None
    if type(parsed) is not dict:
        diagnostic = (
            _result_diagnostic(
                ResultDiagnosticStage.RESPONSE_JSON,
                ResultDiagnosticReason.RESPONSE_NOT_OBJECT,
                status=response_status,
                response_bytes=len(raw),
            )
            if result_diagnostic
            else None
        )
        raise EvaluationError(code, phase, False, diagnostic=diagnostic)
    return parsed
```

Refactor `_request_json` only enough to attach:

- `connection/connection_failed` before a complete valid response status;
- `response_status/response_status_invalid` for invalid or unexpected status;
- `response_body/response_read_failed` or `response_size_exceeded` for bounded reads; and
- exact status/body length when safely observed.

Call it from `result()` with `result_diagnostic=True`. On run identity mismatch raise:

```python
raise EvaluationError(
    "consumer_projection_invalid",
    "result",
    False,
    diagnostic=_result_diagnostic(
        ResultDiagnosticStage.RESPONSE_IDENTITY,
        ResultDiagnosticReason.RUN_IDENTITY_MISMATCH,
        status=observation.status_code,
        response_bytes=observation.response_bytes,
    ),
)
```

Extend `HttpObservation` with `response_bytes: int` so the identity and later proof layers receive
only the completed length, not raw bytes. Add an internal `result_observation()` method that returns
the completed `HttpObservation`; keep `result()` as a compatibility wrapper returning only
`observation.body`. The proof integration in Task 4 uses `result_observation()` while all existing
callers keep the current return type.

Classify malformed or negative `Content-Length` as
`response_body/response_read_failed`, declared or streamed overflow as
`response_body/response_size_exceeded`, and an unexpected complete HTTP status as
`response_status/response_status_invalid`. `response_bytes` is `None` unless a complete body was
retained. The exact canonical `409 run_result_unavailable` remains `artifact_invalid` without a
diagnostic; any other complete `409` is the unexpected-status case.

- [ ] **Step 4: Run full HTTP GREEN and adjacent contract regression**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py
```

Expected: all tests pass; old public codes and canonical `409` mapping remain unchanged.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_http.py
git commit -m "feat(eval): classify result observation failures"
```

---

### Task 3: Add The Safe Diagnostic Sink

**Files:**
- Create: `scripts/bounded_live_producer_diagnostics.py`
- Create: `tests/unit/test_bounded_live_producer_diagnostics.py`

**Interfaces:**
- Consumes: Task 1 `EvaluationError`, `MAX_DIAGNOSTIC_BYTES`, and `serialize_result_diagnostic`.
- Produces: `DIAGNOSTIC_FILENAME`, frozen `DiagnosticSink`, `preflight_diagnostic_dir(path: Path, repository_root: Path) -> DiagnosticSink`, and `publish_result_diagnostic(sink: DiagnosticSink, error: EvaluationError, remaining_seconds: Callable[[float], float]) -> Path`.

- [ ] **Step 1: Write RED sink ownership and publication tests**

Create the test file with a safe-directory helper:

```python
from pathlib import Path
import os

import pytest

from scripts.bounded_live_producer_contracts import (
    CleanupStatus,
    EvaluationError,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticStage,
)
from scripts.bounded_live_producer_diagnostics import (
    DIAGNOSTIC_FILENAME,
    preflight_diagnostic_dir,
    publish_result_diagnostic,
)


def _safe_dir(tmp_path: Path) -> Path:
    path = tmp_path / "diagnostic"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _error() -> EvaluationError:
    return EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=ResultBoundaryDiagnostic(
            stage=ResultDiagnosticStage.RESPONSE_JSON,
            reason=ResultDiagnosticReason.RESPONSE_JSON_INVALID,
            http_status=200,
            response_bytes=8,
        ),
    )


def test_publishes_fixed_non_overwriting_mode_0600_file(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)

    path = publish_result_diagnostic(
        sink,
        _error(),
        remaining_seconds=lambda requested: requested,
    )

    assert path == output / DIAGNOSTIC_FILENAME
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_bytes().endswith(b"\n")
    with pytest.raises(Exception):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )
```

Add tests rejecting relative paths, repository-contained paths, symlink leaf and parent components,
missing paths, files instead of directories, wrong owner, owner without write/search permissions,
any group/world permission bit, pre-existing final basename, directory replacement between
preflight and publication, temporary-name collision, short writes, file/directory `fsync` failure,
link failure, and a serializer exceeding 4 KiB. Assert no unrelated path is removed, and verify a
subprocess import of the new module emits no stdout or stderr.

- [ ] **Step 2: Run the new sink test and capture RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_diagnostics.py
```

Expected: collection fails because `bounded_live_producer_diagnostics.py` does not exist.

- [ ] **Step 3: Implement preflight with identity pinning**

Create the module with no imports from API, Agent, provider, Docker, or lifecycle code:

```python
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
from typing import Callable

from scripts.bounded_live_producer_contracts import (
    EvaluationError,
    MAX_DIAGNOSTIC_BYTES,
    serialize_result_diagnostic,
)


DIAGNOSTIC_FILENAME = "bounded-live-producer-result-diagnostic-v1.json"


@dataclass(frozen=True, slots=True)
class DiagnosticSink:
    path: Path
    device: int
    inode: int
    uid: int
    permission_bits: int


class DiagnosticOutputError(Exception):
    def __init__(self) -> None:
        super().__init__("diagnostic_output_invalid")


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise DiagnosticOutputError


def _preflight_diagnostic_dir(path: Path, *, repository_root: Path) -> DiagnosticSink:
    if not isinstance(path, Path) or not path.is_absolute():
        raise DiagnosticOutputError
    _reject_symlink_components(path)
    resolved = path.resolve(strict=True)
    repository = repository_root.resolve(strict=True)
    if resolved == repository or repository in resolved.parents:
        raise DiagnosticOutputError
    descriptor = os.open(
        resolved,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        observed = os.fstat(descriptor)
        permissions = stat.S_IMODE(observed.st_mode)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or permissions & 0o077
            or permissions & 0o300 != 0o300
        ):
            raise DiagnosticOutputError
        try:
            os.stat(DIAGNOSTIC_FILENAME, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise DiagnosticOutputError
        return DiagnosticSink(
            path=resolved,
            device=observed.st_dev,
            inode=observed.st_ino,
            uid=observed.st_uid,
            permission_bits=permissions,
        )
    finally:
        os.close(descriptor)


def preflight_diagnostic_dir(path: Path, *, repository_root: Path) -> DiagnosticSink:
    try:
        return _preflight_diagnostic_dir(path, repository_root=repository_root)
    except DiagnosticOutputError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DiagnosticOutputError from exc
```

Use only the private stable `DiagnosticOutputError` rather than exposing `OSError` text. Convert
all path, ownership, identity, permission, and pre-existing-output failures to that exception.
Task 4 maps it to the existing `output_invalid/input` error without serializing the private
exception.

- [ ] **Step 4: Implement atomic fixed-name publication**

Re-open the exact directory without following the leaf, compare `st_dev`, `st_ino`, owner, and
permissions to the preflight receipt, then publish canonical bytes:

```python
def _publish_result_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> Path:
    raw = serialize_result_diagnostic(error)
    if len(raw) > MAX_DIAGNOSTIC_BYTES:
        raise DiagnosticOutputError
    remaining_seconds(1.0)
    descriptor = os.open(
        sink.path,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = f".{DIAGNOSTIC_FILENAME}.{secrets.token_hex(16)}.tmp"
    temporary_created = False
    try:
        observed = os.fstat(descriptor)
        if (
            (observed.st_dev, observed.st_ino, observed.st_uid, stat.S_IMODE(observed.st_mode))
            != (sink.device, sink.inode, sink.uid, sink.permission_bits)
        ):
            raise DiagnosticOutputError
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(temporary, flags, 0o600, dir_fd=descriptor)
        temporary_created = True
        try:
            os.fchmod(file_descriptor, 0o600)
            if stat.S_IMODE(os.fstat(file_descriptor).st_mode) != 0o600:
                raise DiagnosticOutputError
            view = memoryview(raw)
            while view:
                remaining_seconds(1.0)
                written = os.write(file_descriptor, view)
                if written <= 0:
                    raise DiagnosticOutputError
                view = view[written:]
            remaining_seconds(1.0)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        remaining_seconds(1.0)
        os.link(
            temporary,
            DIAGNOSTIC_FILENAME,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
            follow_symlinks=False,
        )
        remaining_seconds(1.0)
        os.fsync(descriptor)
        remaining_seconds(1.0)
        os.unlink(temporary, dir_fd=descriptor)
        temporary_created = False
        remaining_seconds(1.0)
        os.fsync(descriptor)
        return sink.path / DIAGNOSTIC_FILENAME
    except (OSError, ValueError) as exc:
        raise DiagnosticOutputError from exc
    finally:
        if temporary_created:
            try:
                os.unlink(temporary, dir_fd=descriptor)
            except OSError:
                pass
        os.close(descriptor)


def publish_result_diagnostic(
    sink: DiagnosticSink,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> Path:
    try:
        return _publish_result_diagnostic(
            sink,
            error,
            remaining_seconds=remaining_seconds,
        )
    except DiagnosticOutputError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DiagnosticOutputError from exc
```

Do not remove a temporary name that was not created by this call. Test the exact ownership flag
before unlinking. Every write, link, unlink, and `fsync` consumes only the existing remaining outer
deadline; publication does not create a new timeout budget.

- [ ] **Step 5: Run sink and contract GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_diagnostics.py
```

Expected: all tests pass with no repository file created.

- [ ] **Step 6: Commit Task 3**

```bash
git add scripts/bounded_live_producer_diagnostics.py \
  tests/unit/test_bounded_live_producer_diagnostics.py
git commit -m "feat(eval): add safe result diagnostic sink"
```

---

### Task 4: Integrate Consumer Diagnostics, Cleanup, And CLI

**Files:**
- Modify: `scripts/bounded_live_producer_proof.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`

**Interfaces:**
- Consumes: Tasks 1-3 contracts, result diagnostics, `preflight_diagnostic_dir`, and `publish_result_diagnostic`.
- Produces: consumer-contract and projection-disposition diagnostic reasons, diagnostic preservation through cleanup and exception groups, optional `--diagnostic-dir`, and post-cleanup best-effort publication with unchanged public stderr.

- [ ] **Step 1: Write RED consumer and cleanup propagation tests**

Extend the existing `ContractValidationError` monkeypatch matrix:

```python
@pytest.mark.parametrize(
    ("contract_code", "reason"),
    [
        ("contract_result_invalid", "contract_result_invalid"),
        ("contract_schema_invalid", "contract_schema_invalid"),
    ],
)
def test_project_live_observation_attaches_consumer_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    contract_code: str,
    reason: str,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_proof")

    def fail_projection(**_kwargs: Any) -> dict[str, Any]:
        raise module.ContractValidationError(contract_code)

    monkeypatch.setattr(module, "project_consumer_case", fail_projection)
    with pytest.raises(EvaluationError) as caught:
        _snapshot()

    assert caught.value.code.value == "consumer_projection_invalid"
    assert caught.value.diagnostic is not None
    assert caught.value.diagnostic.stage.value == "consumer_contract"
    assert caught.value.diagnostic.reason.value == reason
```

Add a mutation where the projection returns an unexpected `expected` disposition and assert
`projection_disposition_invalid`. Add grouped primary-plus-cleanup tests proving `_group_error`
preserves the primary diagnostic and changes only cleanup status.

- [ ] **Step 2: Write RED CLI and lifecycle publication tests**

Use the existing provider-free live boundary fixture and inject one terminal result diagnostic.
Assert the event order and file behavior:

```python
def test_observe_live_publishes_diagnostic_only_after_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_dir = tmp_path / "diagnostic"
    diagnostic_dir.mkdir(mode=0o700)
    diagnostic_dir.chmod(0o700)
    invoke, _repository, events, _holder = _install_provider_free_live_boundaries(
        tmp_path,
        monkeypatch,
        terminal_error=EvaluationError(
            "consumer_projection_invalid",
            "result",
            False,
            diagnostic=ResultBoundaryDiagnostic(
                stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
                reason=ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
                http_status=200,
                response_bytes=512,
            ),
        ),
        diagnostic_dir=diagnostic_dir,
    )

    with pytest.raises(EvaluationError) as caught:
        invoke()

    assert caught.value.cleanup_status is CleanupStatus.SUCCEEDED
    receipt = diagnostic_dir / "bounded-live-producer-result-diagnostic-v1.json"
    assert receipt.is_file()
    assert events.index("cleanup_receipt") < events.index("diagnostic_publish")
```

Add tests for:

- invalid diagnostic directory stops before live configuration, Docker, credentials, or provider;
- success produces no diagnostic file;
- no argument produces no diagnostic file and byte-identical public stderr;
- artifact/state/Evidence/fallback/hash failures produce no generic receipt;
- diagnostic publication failure preserves the original public error and cleanup status;
- a primary-plus-cleanup group publishes `cleanup_status=failed` with the primary stage/reason;
- `check` rejects `--diagnostic-dir` and remains byte-identical;
- help remains exit 0; and
- source snapshot required paths include `scripts/bounded_live_producer_diagnostics.py`.

- [ ] **Step 3: Run proof tests and capture RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_bounded_live_producer_proof.py \
  -k 'diagnostic or consumer_failure_class or group_error'
```

Expected: failures because consumer metadata, sink preflight, CLI wiring, and post-cleanup
publication are absent or diagnostic metadata is dropped.

- [ ] **Step 4: Preserve diagnostic metadata through consumer projection**

Extend `_error` with an optional keyword-only diagnostic and attach exact reasons only to the two
remaining consumer contract codes:

```python
def _error(
    code: FailureCode | str,
    phase: FailurePhase | str,
    *,
    diagnostic: ResultBoundaryDiagnostic | None = None,
) -> EvaluationError:
    return EvaluationError(code, phase, False, diagnostic=diagnostic)


def _consumer_diagnostic(
    reason: ResultDiagnosticReason,
    *,
    response_bytes: int,
) -> ResultBoundaryDiagnostic:
    return ResultBoundaryDiagnostic(
        stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
        reason=reason,
        http_status=200,
        response_bytes=response_bytes,
    )
```

Add `result_response_bytes: int` to `project_live_observation`. In `observe_terminal`, call Task 2's
internal `client.result_observation()`, pass its `body` as `result_payload`, and pass its exact
`response_bytes` separately. Keep `ProofHttpClient.result()` returning the body for existing
callers. Do not add metadata fields to the DRA result payload.

Map `contract_result_invalid` and `contract_schema_invalid` to the matching internal reason. Keep
existing artifact, state, Evidence, fallback, and hash error mappings unchanged. Attach
`projection_disposition_invalid` when the consumer projection returns any disposition other than
the existing supported or fallback cases.

- [ ] **Step 5: Preserve metadata through cleanup and grouped errors**

Every `EvaluationError` reconstruction must copy `diagnostic=exc.diagnostic`. `_group_error` must
copy `primary.diagnostic`:

```python
return EvaluationError(
    primary.code,
    primary.phase,
    primary.retryable,
    CleanupStatus.FAILED if cleanup_failed else primary.cleanup_status,
    diagnostic=primary.diagnostic,
)
```

In `observe_live`, project both `EvaluationError` and `BaseExceptionGroup` to one final error after
cleanup, then publish only when the error is eligible and a sink exists:

```python
def _publish_diagnostic_best_effort(
    sink: DiagnosticSink | None,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> None:
    if sink is None or error.diagnostic is None:
        return
    try:
        publish_result_diagnostic(
            sink,
            error,
            remaining_seconds=remaining_seconds,
        )
    except (DiagnosticOutputError, EvaluationValidationError):
        return
```

Do not catch `KeyboardInterrupt` or `SystemExit`, and do not serialize any publication exception.
The helper is invoked only after managed cleanup has reached its final status.

- [ ] **Step 6: Wire safe preflight and the optional CLI argument**

Add to `observe_live`:

```python
diagnostic_dir: Path | None = None,
```

Preflight immediately after the existing fixed evidence-output preflight and before manifest,
credential configuration, Docker, or task-temp mutation:

```python
diagnostic_sink = (
    preflight_diagnostic_dir(diagnostic_dir, repository_root=repository_root)
    if diagnostic_dir is not None
    else None
)
```

Catch only `DiagnosticOutputError` from preflight and map it to the existing
`output_invalid/input` error. Add to only the `observe-live` parser:

```python
live.add_argument("--diagnostic-dir", type=Path)
```

Pass it through `main`, add the new diagnostics module to `required_paths`, and keep `check`
unchanged. Do not accept a filename, environment fallback, default directory, repository path, or
retry option.

- [ ] **Step 7: Run focused integration GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/integration/test_bounded_live_producer_proof.py
```

Expected: all result classifications, lifecycle order, CLI, cleanup, and compatibility tests pass.

- [ ] **Step 8: Prove deterministic output remains byte-identical**

Run:

```bash
_CHECK_DIR=$(mktemp -d)
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check \
  > "$_CHECK_DIR/first.json"
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check \
  > "$_CHECK_DIR/second.json"
cmp "$_CHECK_DIR/first.json" "$_CHECK_DIR/second.json"
shasum -a 256 "$_CHECK_DIR/first.json"
```

Expected: `cmp` exits 0 and the SHA-256 remains the reviewed provider-free baseline
`95b645891ccf87c6771a60c52f14e7235e5f351ba28a70eab1e55ea32f3859b3`.

Remove only this exact task-owned temporary directory after recording the result:

```bash
rm -rf -- "$_CHECK_DIR"
```

- [ ] **Step 9: Commit Task 4**

```bash
git add scripts/bounded_live_producer_proof.py \
  tests/integration/test_bounded_live_producer_proof.py
git commit -m "feat(eval): publish result diagnostic receipts"
```

---

### Task 5: Publish Documentation And Complete Verification

**Files:**
- Modify: `docs/reference/bounded-live-producer-evaluation.md`
- Modify: `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md`
- Modify: `docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Verify unchanged: `docs/superpowers/specs/2026-07-22-bounded-result-diagnostic-receipt-design.md`
- Verify unchanged: `docs/superpowers/plans/2026-07-22-bounded-result-diagnostic-receipt-implementation.md`

**Interfaces:**
- Consumes: implemented diagnostic schema, CLI, privacy boundary, and stop sequence from Tasks 1-4.
- Produces: public discovery and exact compatibility/non-claim contracts; complete provider-free handoff evidence.

- [ ] **Step 1: Write RED documentation contracts**

Add one exact documentation test:

```python
def test_bounded_result_diagnostic_receipt_is_scoped_and_discoverable() -> None:
    reference = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    ).read_text(encoding="utf-8")
    old_design = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    ).read_text(encoding="utf-8")
    old_plan = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join((reference + old_design + old_plan).split())

    for phrase in (
        "dra.bounded-live-producer-result-diagnostic.v1",
        "--diagnostic-dir",
        "bounded-live-producer-result-diagnostic-v1.json",
        "existing public error envelope remains unchanged",
        "not live evidence",
        "does not authorize a retry",
        "fixed basename",
        "after cleanup",
    ):
        assert phrase in normalized

    for forbidden in (
        "raw response is retained",
        "automatic retry",
        "new REST error contract",
        "diagnostic receipt is canonical",
    ):
        assert forbidden not in normalized
```

Add a mutation contract proving removal of the narrow amendment or restoration of an arbitrary
output filename fails.

- [ ] **Step 2: Run documentation RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  -k 'bounded_result_diagnostic'
```

Expected: failure because the reference and existing design/plan do not yet contain the new
diagnostic amendment.

- [ ] **Step 3: Update the operator reference and narrow amendments**

In `docs/reference/bounded-live-producer-evaluation.md`, document:

```text
observe-live --diagnostic-dir <owner-only repo-external directory>
  -> no retry
  -> unchanged public stderr error
  -> cleanup
  -> optional bounded-live-producer-result-diagnostic-v1.json
```

List the exact receipt schema, stage/reason pairs, fixed output rules, raw-data exclusions, and
one-shot stop condition. State that success and non-eligible failures create no receipt.

Append `### Post-Observation Result Diagnostic Amendment` to both the 2026-07-18 design and plan.
Use the same exact boundary text in each:

```markdown
### Post-Observation Result Diagnostic Amendment

A later bounded observation showed that `consumer_projection_invalid` still
collapsed multiple result-boundary stages after existing artifact, state,
Evidence, fallback, and hash classifications. The separately approved Bounded
Result Diagnostic Receipt v1 adds one optional `--diagnostic-dir` with a fixed
basename and owner-only repo-external directory. This is the only exception to
Change 1's prohibition on output-path options; it does not permit an arbitrary
filename or general output root.

The existing public error envelope remains unchanged. The JSON-only receipt is
written after cleanup, is not live evidence or application authority, contains
no raw response or provider material, and does not authorize a retry. REST,
OpenAPI, database, Agent/framework authority, canonical result, Evidence,
downstream consumer acceptance, dependencies, CI provider policy, VERSION,
and release metadata remain unchanged.
```

Do not update README, CHANGELOG, release notes, VERSION, docs evidence indexes, or CI.

- [ ] **Step 4: Run docs and focused feature GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_diagnostics.py \
  tests/integration/test_bounded_live_producer_proof.py
```

Expected: all tests pass; published release history remains unchanged.

- [ ] **Step 5: Run all deterministic proof gates**

Run with `PYTHON_DOTENV_DISABLED=1` where supported:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py
```

Expected: every proof reports valid/match or zero violations, and no command invokes a provider.

- [ ] **Step 6: Run the complete non-Docker backend suite**

Use the repository's locked Python 3.11 environment. Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
```

Expected: all selected tests pass. If the host environment cannot reproduce locked dependencies,
use the already established task-specific locked environment or exact CI installation method;
do not install or modify dependencies without authorization and do not use an import stub to claim
the full suite passed.

- [ ] **Step 7: Run the required provider-free Docker lane**

Preflight Docker daemon and Docker VM filesystem capacity using the existing project method, then
run:

```bash
PYTHON_DOTENV_DISABLED=1 \
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
python -m pytest -q -m docker
```

Expected: all Docker-marked tests pass, including the exact tracked source snapshot with the new
diagnostics module. Record task-owned container, volume, network, image, and temporary-directory
inventory before and after. Do not run broad prune or delete pre-existing Docker resources.

- [ ] **Step 8: Audit scope, public safety, and absence of live evidence**

Run:

```bash
git diff --check origin/main..HEAD
git diff --name-only origin/main..HEAD
git diff --name-only origin/main..HEAD -- \
  api agent frontend requirements.txt constraints.txt pyproject.toml \
  .github/workflows VERSION docs/releases docs/evidence
test ! -e docs/evidence/bounded-live-producer-v1.json
test ! -e docs/evidence/bounded-live-producer-v1.md
python scripts/final_presentation_audit.py
rg -n -i '(api[_ -]?key[=:]|secret[=:]|authorization:[[:space:]]*bearer)' \
  $(git diff --name-only origin/main..HEAD) || true
```

Expected:

- `git diff --check` exits 0;
- prohibited runtime/version/dependency/CI/release/evidence diff is empty;
- both live evidence files are absent;
- presentation and credential-assignment scans have no unapproved finding; and
- `VERSION` remains `0.1.5`.

Review any scan hit in test fixtures before classifying it. Do not delete a legitimate negative
test merely to make a text scan empty.

- [ ] **Step 9: Commit documentation and test contracts**

```bash
git add docs/reference/bounded-live-producer-evaluation.md \
  docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md \
  docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(eval): publish result diagnostic contract"
```

- [ ] **Step 10: Produce the terminal handoff**

Report:

- base, branch, worktree, ordered commits, and final HEAD;
- exact changed files and diff stat;
- RED-to-GREEN evidence per task;
- focused, full non-Docker, Docker, deterministic proof, identity, presentation, and diff-check
  results;
- default error/check byte-compatibility evidence;
- public/private and credential scans;
- Docker and temporary-resource before/after inventory;
- explicit confirmation that no live/provider/model/search/credential operation occurred;
- explicit confirmation that API, DB, Agent/framework authority, canonical result, Evidence,
  downstream acceptance, dependencies, CI, VERSION, release metadata, and live evidence did not
  change; and
- remaining environment risk without converting it into a success claim.

Keep the branch and worktree clean. Do not push, create or modify a PR, merge, tag, release, deploy,
run `observe-live`, access provider credentials, publish live evidence, or clean up the final task
worktree. Stop for authoritative branch-diff review.

## Plan Self-Review

- Spec coverage: Tasks 1-5 cover the strict receipt, every stage/reason, public-envelope
  compatibility, HTTP/consumer classification, fixed safe output, cleanup ordering, dual failure,
  documentation, deterministic gates, and live stop condition.
- Scope: the only new production file is proof-owned diagnostics code; no application runtime,
  database, framework, dependency, frontend, release, or live evidence surface is added.
- Type consistency: Task 1 defines every enum/model and `EvaluationError.diagnostic`; Tasks 2-4
  consume those exact names; Task 3 owns only sink identity/publication; Task 4 owns integration.
- Parallel safety: Tasks 2 and 3 have disjoint file ownership after Task 1 and join only in Task 4.
- Completion scan: no unresolved implementation marker or deferred behavior is present.
- Compatibility: the public error serializer is intentionally unchanged, and the provider-free
  baseline hash is an explicit gate.
- Stop boundary: implementation and provider execution remain separate authorizations.
