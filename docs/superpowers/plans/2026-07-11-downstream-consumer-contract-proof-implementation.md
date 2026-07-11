# Downstream Consumer Contract Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents for this repository unless the owner explicitly authorizes them.

**Goal:** Publish a versioned, deterministic, public-safe fixture and strict reference validator that prove how a downstream Agent consumes the existing ResearchRun, run-level Evidence, and canonical result contracts without adding a runtime API or business authority.

**Architecture:** Seed fixed synthetic states in a disposable application database through the existing run repository, resolve results through `resolve_run_result()`, project only an explicit consumer allowlist, validate the exact fixture schema and state/result combinations, and byte-compare a fresh build with the committed JSON. The proof remains offline and imports no DeepAgents, LangGraph, LangSmith, provider, search, telemetry, or token-usage runtime.

**Tech Stack:** Python 3.11, standard library (`argparse`, `hashlib`, `json`, `sqlite3`, `tempfile`, `unittest.mock`), existing application repository/result modules, pytest

## Global Constraints

- Keep `ResearchRun`, `EvidenceLedger`, review, verification, publication, and delivery authority in the application database.
- Do not change REST endpoints, response fields, database schema, migrations, generic structured outcome, Evidence capture, failure persistence, usage persistence, or profiles.
- Do not import or invoke DeepAgents, LangGraph execution, LangSmith clients, provider models, network tools, telemetry collectors, or token collectors.
- Do not add dependencies, credentials, real personal data, network access, or unstable LLM output.
- Do not add consumer-specific business fields or parse Markdown into typed findings, claims, limitations, conflicts, or Evidence references.
- Treat `research_report_fallback_markdown` and `completed_with_fallback` as blocked downstream content, even when delivery is `ready`.
- Use a project-supported fresh Python 3.11 environment. Set `PYTHON_DOTENV_DISABLED=1` for CI-parity verification and do not read credentials.
- Keep all output public-neutral and free of host paths, raw exceptions, tracebacks, checkpoint data, credentials, snippets, query text, and private workflow details.

---

## Scope And File Map

| File | Responsibility |
|---|---|
| `scripts/downstream_consumer_contract.py` | Deterministic disposable-state builder, public-safe projector, strict validator, and `build` / `check` CLI |
| `tests/integration/test_downstream_consumer_contract.py` | RED/GREEN coverage for current repository/result behavior, deterministic bytes, schema mutations, state matrix, artifact integrity, Evidence allowlist, privacy, and CLI |
| `docs/evidence/downstream-consumer-contract-v1.json` | Committed generated compatibility fixture |
| `docs/reference/downstream-consumer-contract.md` | Reusable downstream Agent consumption and failure-handling reference |
| `docs/evidence/README.md` | Evidence index entry and proof boundary |
| `docs/AGENT_INTEGRATION.md` | Link from the existing Agent integration surface |
| `docs/README.md` | Reference index entry |
| `tests/unit/test_documentation_contracts.py` | Documentation/index contract for fixture version, commands, and no-Markdown-parsing boundary |

Approved inputs:

- `docs/superpowers/specs/2026-07-11-downstream-consumer-contract-proof-design.md`
- `docs/superpowers/plans/2026-07-11-downstream-consumer-contract-proof-implementation.md`

Do not modify `api/`, `agent/`, `tools/`, migrations, dependency files, Docker,
frontend, benchmark, review, verification, publication, or release files.

## Stable Contract Vocabulary

Use these exact constants in `scripts/downstream_consumer_contract.py`:

```python
SCHEMA_VERSION = "dra.downstream-consumer.v1"
FIXTURE_TIMESTAMP = "2026-07-11T00:00:00+00:00"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_FIXTURE_BYTES = 2 * 1024 * 1024

EXECUTION_STATUSES = {
    "pending",
    "running",
    "completed",
    "completed_with_fallback",
    "failed",
}
REVIEW_STATUSES = {"not_required", "required", "resolved"}
DELIVERY_STATUSES = {
    "pending",
    "ready",
    "review_required",
    "blocked",
    "failed",
}
EVIDENCE_KEYS = {
    "evidence_id",
    "source_url",
    "source_identity",
    "retrieved_at",
    "citation_status",
    "verification_status",
}
CANONICAL_KIND = "research_report_markdown"
FALLBACK_KIND = "research_report_fallback_markdown"
```

The exact state/disposition table is:

```python
STATE_DISPOSITIONS = {
    ("pending", "not_required", "pending"): ("supported", "wait"),
    ("running", "not_required", "pending"): ("supported", "wait"),
    ("completed", "not_required", "ready"): ("supported", "accept_draft"),
    ("completed_with_fallback", "not_required", "ready"): (
        "partial",
        "block_fallback",
    ),
    ("completed", "required", "review_required"): (
        "supported",
        "await_review",
    ),
    ("completed", "resolved", "blocked"): ("supported", "block"),
    ("failed", "not_required", "failed"): ("supported", "block"),
}
```

For the active fallback case, start from `completed/not_required/ready` and
override the expected support/disposition to `partial/block_fallback` after the
artifact kind is validated. A ready run with no valid artifact is
`supported/block` with result code `run_result_unavailable`.

## Task 1: Define The Strict Consumer Projection And Validator

**Files:**
- Create: `scripts/downstream_consumer_contract.py`
- Create: `tests/integration/test_downstream_consumer_contract.py`

**Interfaces:**
- Produces: `ContractValidationError(code: str)`
- Produces: `project_consumer_case(*, case_id: str, status_payload: dict[str, Any], result_http_status: int, result_payload: dict[str, Any]) -> dict[str, Any]`
- Produces: `validate_fixture_bundle(payload: Any) -> dict[str, Any]`
- Produces: `serialize_fixture(payload: dict[str, Any]) -> bytes`

- [ ] **Step 1: Write failing tests for the exact projection and schema**

Create the test file with a minimal canonical source pair:

```python
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest


def _canonical_status() -> dict:
    return {
        "run_id": "run_fixture_canonical",
        "profile_id": "generic",
        "profile_version": "1",
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "state_version": 1,
        "query": "must not be projected",
        "evidence": [
            {
                "evidence_id": "ev_run_fixture_canonical_01",
                "run_id": "run_fixture_canonical",
                "segment_id": "run_fixture_canonical_seg_000",
                "query_text": "must not be projected",
                "subagent_name": "network_search",
                "tool_name": "internet_search",
                "source_url": "https://example.com/public-source",
                "source_identity": "https://example.com/public-source",
                "snippet": "must not be projected",
                "evidence_fingerprint": "f" * 64,
                "retrieved_at": "2026-07-11T00:00:00+00:00",
                "tool_call_id": "tool-private",
                "citation_status": "cited",
                "verification_status": "unverified",
                "created_at": "2026-07-11T00:00:00+00:00",
            }
        ],
    }


def _canonical_result() -> dict:
    content = "# Synthetic Research Report\n\nPublic-safe contract proof."
    return {
        "run_id": "run_fixture_canonical",
        "execution_status": "completed",
        "delivery_status": "ready",
        "artifact": {
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    }


def test_canonical_projection_is_strict_and_public_safe():
    from scripts.downstream_consumer_contract import project_consumer_case

    projected = project_consumer_case(
        case_id="canonical_ready",
        status_payload=_canonical_status(),
        result_http_status=200,
        result_payload=_canonical_result(),
    )

    assert projected["expected"] == {
        "support": "supported",
        "disposition": "accept_draft",
    }
    assert set(projected["evidence"][0]) == {
        "evidence_id",
        "source_url",
        "source_identity",
        "retrieved_at",
        "citation_status",
        "verification_status",
    }
    serialized = json.dumps(projected, ensure_ascii=False)
    for forbidden in ("query_text", "snippet", "tool-private", "network_search"):
        assert forbidden not in serialized
```

Add parameterized RED tests for:

- unknown execution/review/delivery values;
- impossible state combinations;
- wrong result HTTP/error code for each state;
- unknown artifact kind, non-Markdown media type, empty/oversized content,
  malformed hash, and hash mismatch;
- fallback expected as accepted;
- `decision_brief_markdown` passed to this generic validator;
- malformed Evidence identity, non-public fixture URL, and missing allowlist
  source fields;
- empty Evidence list as valid, plus duplicate Evidence IDs as invalid;
- wrong/missing bundle schema version, extra bundle/case/Evidence keys, and
  unknown disposition;
- duplicate case IDs, invalid/non-integer/negative `state_version`, and malformed
  required `run_id` / `profile_id` values.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py -q
```

Expected: collection fails with
`ModuleNotFoundError: scripts.downstream_consumer_contract`.

- [ ] **Step 3: Implement the validation primitives and projector**

Implement one bounded exception and explicit helpers; do not add a model
hierarchy:

```python
class ContractValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require_exact_keys(value: object, expected: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractValidationError(code)
    return value


def _fail(code: str) -> None:
    raise ContractValidationError(code)
```

Implement `project_consumer_case()` in this order:

1. Validate required upstream run fields and known enums.
2. Resolve the allowed state combination.
3. Validate result HTTP/body consistency.
4. For HTTP 200, validate generic artifact ID/kind/media/content/hash.
5. Override canonical `completed/ready` to
   `partial/block_fallback` when artifact kind is fallback.
6. Build Evidence by reading required source fields and emitting exactly
   `EVIDENCE_KEYS`.
7. Return exact `case_id/profile_id/run/evidence/result/expected` keys.

Do not reject unrelated extra keys in the raw upstream status payload; real
`GET /api/runs/{run_id}` has more fields. Reject extras only after projection
inside the versioned fixture.

Implement `validate_fixture_bundle()` with exact nested keys. Re-run each case
through fixture-level validation, recompute generic artifact hashes, and reject
any Evidence key outside `EVIDENCE_KEYS`. Require the service object and each
capability list to equal the published constants exactly, including order and
uniqueness. Reject public fixture strings containing host absolute paths, raw
tracebacks, checkpoint identifiers, or credential-like assignments. This
fixture check does not claim the runtime endpoint is a general DLP system.
Return the same dict on success.

For non-success results, derive disposition from the run-state tuple and stable
result code. Do not trust the current envelope's `retryable` boolean by itself:
all `409` result errors currently set it to `true`, including blocked and failed
states.

Implement deterministic bytes:

```python
def serialize_fixture(payload: dict[str, object]) -> bytes:
    validate_fixture_bundle(payload)
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
```

- [ ] **Step 4: Run focused validation tests and verify GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py \
  -k "projection or schema or state or artifact or evidence" -q
```

Expected: all new projection/validator tests pass.

- [ ] **Step 5: Commit the strict validator boundary**

```bash
git add scripts/downstream_consumer_contract.py \
  tests/integration/test_downstream_consumer_contract.py
git commit -m "feat(contract): validate downstream run consumption"
```

## Task 2: Build Deterministic Cases Through Existing Application Contracts

**Files:**
- Modify: `scripts/downstream_consumer_contract.py`
- Modify: `tests/integration/test_downstream_consumer_contract.py`

**Interfaces:**
- Consumes: `project_consumer_case()`, `validate_fixture_bundle()`, `serialize_fixture()`
- Produces: `build_fixture_bundle() -> dict[str, Any]`

- [ ] **Step 1: Add RED tests for deterministic repository/result generation**

Add these tests:

```python
def test_build_fixture_bundle_covers_required_states_and_is_deterministic():
    from scripts.downstream_consumer_contract import (
        build_fixture_bundle,
        serialize_fixture,
    )

    first = build_fixture_bundle()
    second = build_fixture_bundle()

    assert serialize_fixture(first) == serialize_fixture(second)
    assert [case["case_id"] for case in first["cases"]] == [
        "pending",
        "running",
        "canonical_ready",
        "fallback_ready",
        "compatibility_fallback",
        "review_required",
        "blocked",
        "failed",
        "result_unavailable",
    ]


def test_fixture_capabilities_keep_untyped_semantics_unknown():
    from scripts.downstream_consumer_contract import build_fixture_bundle

    capabilities = build_fixture_bundle()["capabilities"]
    assert "run_level_evidence" in capabilities["supported"]
    assert "retrieved_at_is_not_source_as_of" in capabilities["partial"]
    assert "typed_limitations" in capabilities["unknown"]
    assert "claim_level_evidence_refs" in capabilities["unknown"]
    assert "persistent_failure_cause" in capabilities["unknown"]
    assert "persistent_usage_cost" in capabilities["unknown"]
```

Add assertions that:

- canonical and both fallback cases contain one allowlisted Evidence row;
- fallback cases are `block_fallback` even with HTTP 200;
- pending/running use `run_not_terminal`;
- review-required, blocked, failed, and unavailable use their exact result
  codes;
- all IDs and timestamps are fixed;
- no bundle string contains `/Users/`, `/private/`, `Traceback`, `checkpoint`,
  `api_key`, `secret`, query text, Evidence snippet, or tool call ID.

- [ ] **Step 2: Run the builder tests and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py \
  -k "build_fixture or capabilities or required_states" -q
```

Expected: FAIL because `build_fixture_bundle()` does not exist.

- [ ] **Step 3: Implement disposable deterministic state seeding**

Use `tempfile.TemporaryDirectory()` and patch only deterministic inputs:

```python
with TemporaryDirectory(prefix="dra-consumer-contract-") as temp_dir:
    db_path = str(Path(temp_dir) / "contract.db")
    with (
        patch("api.run_repository._now", return_value=FIXTURE_TIMESTAMP),
        patch(
            "api.publication_repository.evidence_verification_enabled",
            return_value=False,
        ),
        patch(
            "api.run_repository.uuid.uuid4",
            side_effect=[UUID(int=index) for index in range(1, 10)],
        ),
    ):
        sources = _seed_source_cases(db_path)
```

For each source case:

- create with `create_run()`;
- use `transition_run()` for running;
- use `finalize_run_transaction()` for terminal states;
- use fixed `EvidenceEntry` values with fixed `created_at` and `retrieved_at`;
- use `build_generic_result_artifact()` with fixed `ExecutionOutcome`,
  `ReportCandidate`, content, and `generated_at` values for canonical and
  fallback artifacts;
- call `get_run()` for the status payload;
- call `resolve_run_result()` for success, or convert
  `RunResultUnavailable.status_code` and `.payload(run_id=...)` to the same
  bounded body returned by the HTTP endpoint.

Do not call `api.server`, `TestClient`, provider code, network tools, or feature
flagged review/verification workers. Review-required and blocked cases may use
the application repository's accepted state combinations directly because the
proof validates the downstream status/result boundary, not the durable worker.

Treat Evidence `verification_status` as a compatibility field only. Do not
derive human decision, verification origin, or review approval from it.

Return exact service and capability values:

```python
{
    "schema_version": SCHEMA_VERSION,
    "service": {
        "name": "decision-research-agent",
        "health": {"status": "ok", "service": "decision-research-agent"},
        "status_endpoint": "/api/runs/{run_id}",
        "result_endpoint": "/api/runs/{run_id}/result",
    },
    "capabilities": {
        "supported": [
            "run_state",
            "run_level_evidence",
            "generic_canonical_artifact",
            "fallback_distinction",
            "review_and_delivery_gates",
            "stable_result_errors",
        ],
        "partial": [
            "retrieved_at_is_not_source_as_of",
            "fallback_content_is_not_canonical",
            "completed_with_fallback_is_compatibility_only",
        ],
        "unknown": [
            "claim_level_evidence_refs",
            "typed_limitations",
            "typed_conflicts_and_gaps",
            "source_title_publisher_and_effective_date",
            "persistent_failure_cause",
            "persistent_usage_cost",
        ],
    },
    "cases": cases,
}
```

Sort cases in the exact order asserted by the test.

- [ ] **Step 4: Run all proof tests and verify GREEN**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py -q
```

Expected: all builder, projection, validation, privacy, and mutation tests pass.

- [ ] **Step 5: Commit deterministic generation**

```bash
git add scripts/downstream_consumer_contract.py \
  tests/integration/test_downstream_consumer_contract.py
git commit -m "test(contract): build deterministic consumer cases"
```

## Task 3: Add The Build/Check CLI And Commit The Fixture

**Files:**
- Modify: `scripts/downstream_consumer_contract.py`
- Modify: `tests/integration/test_downstream_consumer_contract.py`
- Create: `docs/evidence/downstream-consumer-contract-v1.json`

**Interfaces:**
- Consumes: `build_fixture_bundle()`, `serialize_fixture()`, `validate_fixture_bundle()`
- Produces: `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write failing CLI and committed-fixture tests**

Add tests that require:

```python
def test_committed_fixture_matches_fresh_build():
    from scripts.downstream_consumer_contract import (
        build_fixture_bundle,
        serialize_fixture,
    )

    committed = Path(
        "docs/evidence/downstream-consumer-contract-v1.json"
    ).read_bytes()
    assert committed == serialize_fixture(build_fixture_bundle())
```

Also test:

- `build --output <tmp>` writes exactly the deterministic bytes;
- `check --input <tmp>` returns 0 for a valid fixture;
- modified fixture returns non-zero and bounded `contract_fixture_drift`;
- invalid JSON, non-object root, unsupported schema, and validator errors return
  stable bounded codes without raw path/content/traceback.
- a file larger than 2 MiB fails before JSON parsing;
- unreadable input and unwritable output map to bounded errors without exposing
  the requested path.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py \
  -k "committed_fixture or cli or drift" -q
```

Expected: FAIL because the CLI and committed fixture do not exist.

- [ ] **Step 3: Implement CLI parsing and bounded errors**

Support exactly:

```text
python scripts/downstream_consumer_contract.py build --output PATH
python scripts/downstream_consumer_contract.py check --input PATH
```

`build` writes fresh deterministic bytes. `check`:

1. reads UTF-8 JSON with a `MAX_FIXTURE_BYTES` 2 MiB limit;
2. validates the exact fixture schema;
3. builds a fresh bundle;
4. compares exact bytes;
5. prints `{"status":"valid","schema_version":"dra.downstream-consumer.v1"}`
   on success.

Catch `OSError`, `UnicodeError`, `json.JSONDecodeError`, and
`ContractValidationError`. Print only
`{"status":"invalid","code":"<stable_code>"}` to stderr and return 1.
On successful build print
`{"status":"built","schema_version":"dra.downstream-consumer.v1"}` without
the output path. Never print an input path, exception string, fixture body, or
traceback.

- [ ] **Step 4: Generate and validate the committed fixture**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py build \
  --output docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
```

Expected: check prints the exact valid status and exits 0.

- [ ] **Step 5: Run proof tests and deterministic rebuild check**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py -q
sha256sum docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py build \
  --output /tmp/dra-downstream-consumer-contract-v1.json
cmp docs/evidence/downstream-consumer-contract-v1.json \
  /tmp/dra-downstream-consumer-contract-v1.json
rm -f /tmp/dra-downstream-consumer-contract-v1.json
```

Expected: tests pass, `cmp` prints no output, and the temporary file is removed.

- [ ] **Step 6: Commit the proof artifact**

```bash
git add scripts/downstream_consumer_contract.py \
  tests/integration/test_downstream_consumer_contract.py \
  docs/evidence/downstream-consumer-contract-v1.json
git commit -m "test(contract): publish consumer compatibility fixture"
```

## Task 4: Document Reusable Agent Consumption Boundaries

**Files:**
- Create: `docs/reference/downstream-consumer-contract.md`
- Modify: `docs/evidence/README.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/README.md`
- Modify: `tests/unit/test_documentation_contracts.py`

- [ ] **Step 1: Add a failing documentation contract test**

Add a test with these exact assertions:

```python
def test_downstream_consumer_contract_is_indexed_and_bounded():
    reference = Path(
        "docs/reference/downstream-consumer-contract.md"
    ).read_text(encoding="utf-8")
    evidence_index = Path("docs/evidence/README.md").read_text(encoding="utf-8")
    integration = Path("docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")
    docs_index = Path("docs/README.md").read_text(encoding="utf-8")

    assert "dra.downstream-consumer.v1" in reference
    assert "supported" in reference
    assert "partial" in reference
    assert "unknown" in reference
    assert "block_fallback" in reference
    assert "must not parse Markdown" in reference
    assert "downstream-consumer-contract-v1.json" in evidence_index
    assert "downstream-consumer-contract.md" in integration
    assert "downstream-consumer-contract.md" in docs_index
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py \
  -k "downstream_consumer_contract" -q
```

Expected: FAIL because the reference and links do not exist.

- [ ] **Step 3: Write the consumer reference**

Document:

- exact health/status/result sequence;
- fixture schema version and `build` / `check` commands;
- state/result/disposition table;
- canonical generic artifact checks;
- fallback always blocked;
- Evidence allowlist;
- `supported`, `partial`, and `unknown` lists;
- result retry behavior and stable error codes;
- why `retryable=true` on a `409` does not override blocked/failed/review state;
- `accept_draft` is not approval or verification;
- client timeout does not cancel the server run;
- consumers must not parse Markdown into typed claims/limitations/refs;
- application ledger, LangGraph checkpoint, and LangSmith trace authority
  boundaries;
- versioning rule: a breaking fixture schema change requires a new schema/file,
  while additive upstream API fields are ignored unless explicitly projected.

State that the script is a reference proof, not a packaged SDK or production
service.

- [ ] **Step 4: Link the reference and fixture from existing indexes**

- Add one short Agent integration link without duplicating the full contract.
- Add the JSON fixture and boundary to `docs/evidence/README.md`.
- Add the reference under the appropriate Reference section in `docs/README.md`.
- Do not change release notes or claim a new release.

- [ ] **Step 5: Run documentation and proof verification**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py \
  tests/integration/test_downstream_consumer_contract.py -q
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
```

Expected: tests pass and both audits return `status=ok` with no violations.

- [ ] **Step 6: Commit documentation**

```bash
git add docs/reference/downstream-consumer-contract.md \
  docs/evidence/README.md docs/AGENT_INTEGRATION.md docs/README.md \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(contract): explain downstream consumption boundary"
```

## Task 5: Final Verification And Local-Ready Handoff

**Files:**
- Verify: all files changed from the plan base
- Do not modify: runtime/API/database/framework/frontend/release surfaces

- [ ] **Step 1: Confirm the supported fresh Python**

Use the project-supported Python 3.11 runtime. If the repository has no usable
environment, create a temporary ignored virtual environment outside tracked
paths from the pinned `constraints.txt`; do not relax pins or read `.env`.

Run:

```bash
python --version
python -m pip check
```

Expected: Python 3.11.x and no broken requirements.

- [ ] **Step 2: Run focused contract verification**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_downstream_consumer_contract.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/unit/test_documentation_contracts.py -q
PYTHON_DOTENV_DISABLED=1 python \
  scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
```

Expected: all focused tests pass and the fixture reports `status=valid`.

- [ ] **Step 3: Run the full Python suite**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
```

Expected: full suite passes. Record fresh passed/skipped/warning counts; do not
reuse historical counts.

- [ ] **Step 4: Run presentation, identity, diff, and privacy gates**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
git diff --check origin/main...HEAD
git diff --name-only origin/main...HEAD
rg -n "/U[s]ers|Developer/[C]areer|Night[[:space:]]Voyager|Global[[:space:]]Study|G[S]A|求[职]|面[试]|api[_-]?key[=:]|Trace[b]ack \(most recent call last\)" \
  scripts/downstream_consumer_contract.py \
  docs/reference/downstream-consumer-contract.md \
  docs/evidence/downstream-consumer-contract-v1.json \
  docs/evidence/README.md docs/AGENT_INTEGRATION.md docs/README.md \
  docs/superpowers/specs/2026-07-11-downstream-consumer-contract-proof-design.md \
  docs/superpowers/plans/2026-07-11-downstream-consumer-contract-proof-implementation.md
```

Expected: audits report `status=ok`, diff check is silent, changed files match
the approved map, and the privacy scan has no matches.

- [ ] **Step 5: Verify architectural absence mechanically**

```bash
rg -n "deepagents|langgraph|langsmith|ChatOpenAI|TokenUsageCollector|TelemetryCollector|api\.server|TestClient" \
  scripts/downstream_consumer_contract.py
git diff --name-only origin/main...HEAD | \
  rg "^(api|agent|tools|frontend)/|requirements|constraints|Docker|docker-compose|docs/releases"
```

Expected: both commands have no matches. The proof uses only application
repository/result modules and offline standard-library helpers.

- [ ] **Step 6: Confirm excluded gates remain excluded**

Do not run provider, network, benchmark, frontend, Docker, durable HITL,
real-source proof, release, or deployment gates unless the actual diff touches
those contracts. If it does, stop because the approved scope has expanded.

- [ ] **Step 7: Prepare the local-ready execution report**

Run:

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: worktree clean, branch contains the design/plan and focused
implementation commits, and no unrelated file is changed. Report exact
RED/GREEN evidence, fresh verification, fixture hash, diff scope, and skipped
gates. Do not push, create a PR, merge, tag, release, deploy, or delete the
worktree.

## Stop Conditions

Stop implementation and return to the planning/review task if any of these is
required:

1. A REST endpoint, response field, profile, database table/column, migration,
   or packaged SDK.
2. A generic structured outcome, new Evidence capture semantic, typed
   finding/claim/limitation contract, persisted failure cause, or persisted
   usage/cost model.
3. Any file under `api/`, `agent/`, `tools/`, `frontend/`, dependencies, Docker,
   benchmarks, review, verification, publication, or release notes.
4. Provider credentials, network access, real personal data, or unstable model
   output.
5. Markdown parsing or URL text matching used to manufacture typed contract
   fields.
6. A validator that treats fallback as accepted, review approval as Evidence
   verification, or `retrieved_at` as official source freshness.
7. A failure outside the approved proof/docs scope that cannot be explained by
   the fresh environment.

## Review Depth

This is a contract-level offline proof with no runtime behavior change. The
approved review sequence is:

1. design/spec self-review;
2. focused engineering plan review before execution;
3. TDD, focused tests, full Python suite, proof rebuild/check, public audits,
   and clean local commit in the execution task;
4. one authoritative diff review by the planning/review task, focused on
   deterministic generation, state/result consistency, Evidence allowlisting,
   hash semantics, fail-closed unknowns, privacy, and documentation accuracy;
5. targeted re-review after fixes; rerun full review only if the architecture or
   approved file map expands.

Full Autoplan is intentionally not required because this plan adds no product
surface, UI, framework behavior, business authority, runtime API, or deployment
architecture.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---:|---|---|
| CEO Review | `/plan-ceo-review` | Scope and strategy | 0 | Not required | Approved direction already fixes the product scope; no new product surface |
| Codex Review | `/codex review` | Independent second opinion | 0 | Not required | Project policy disables extra agents by default; no unresolved architecture question |
| Eng Review | `/plan-eng-review` | Architecture and tests | 1 | CLEAR | 6 issues found and folded; 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | Not applicable | No UI change |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | Not required | Build/check commands and failure contract are specified in the plan |

**Eng review findings folded:**

- Kept the proof on existing repository/result contracts instead of creating a
  runtime projection endpoint.
- Made generic and DecisionBrief hash semantics explicitly profile-specific.
- Removed ambient feature-flag dependence from deterministic state seeding.
- Required state/error-code authority instead of trusting the broad `409`
  `retryable` flag.
- Separated synthetic review-state compatibility from durable HITL proof.
- Added exact capability lists, 2 MiB fixture input bounds, public-safe marker
  validation, duplicate identity cases, and existing API regression tests.

**Test coverage diagram:**

```text
build_fixture_bundle()
  + fixed IDs/time/feature flags                    -> integration tests
  + pending/running                                 -> run_not_terminal
  + canonical ready                                 -> accept_draft + SHA-256
  + active/compatibility fallback                   -> block_fallback
  + review_required/blocked/failed/unavailable      -> stable fail-closed code
  + repeated build                                  -> byte identity

project_consumer_case()
  + known valid state tuple                         -> expected disposition
  + unknown/impossible state                        -> contract_state_invalid
  + canonical artifact                              -> ID/kind/media/size/hash
  + fallback/profile-specific artifact              -> block or reject
  + raw Evidence                                    -> six-field allowlist only

validate_fixture_bundle()
  + exact schema/service/capabilities/cases          -> valid
  + extra/missing/duplicate/malformed values         -> bounded invalid code
  + unsafe public marker                            -> bounded invalid code

CLI build/check
  + valid build/check                               -> deterministic JSON status
  + invalid/oversized/unreadable/unwritable/drift    -> private bounded error

Existing HTTP result contract
  + status/result integration suites                -> endpoint parity regression
```

**Performance:** Fixed nine-case generation uses one temporary SQLite database,
bounded 1 MiB artifacts, and a 2 MiB fixture limit. There is no network, cache,
background worker, N+1 request path, or production runtime overhead.

**VERDICT:** ENG CLEARED - ready for isolated TDD implementation. No Autoplan,
CEO, design, DX, or outside-model review is required for the approved scope.

NO UNRESOLVED DECISIONS
