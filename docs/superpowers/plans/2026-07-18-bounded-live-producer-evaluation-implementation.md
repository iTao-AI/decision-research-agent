# Bounded Live Producer Evaluation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-free required gate and a separately authorized managed-Compose
observation command that can prove one exact DRA source revision produced a canonical generic
result, public run-level Evidence, restart-stable state, and same-key create reconciliation without
changing any runtime business contract.

**Architecture:** Keep the feature entirely proof-owned. A strict checked-in manifest supplies the
only research scenario and acceptance policy. Separate modules own strict contracts/serialization,
an exact loopback HTTP transport, and tracked-source/Compose lifecycle control. The CLI composes
those modules with the existing `project_consumer_case` projection. Required CI validates the
manifest, mutations, transport, lifecycle, output safety, and a provider-free Docker fixture;
`observe-live` remains an explicit one-run operation that this implementation phase must not run.

**Tech Stack:** Python 3.11, Pydantic 2.13 strict models, pytest 9, Python standard-library
`argparse`, `decimal`, `hashlib`, `http.client`, `ipaddress`, `json`, `os`, `pathlib`, `secrets`,
`subprocess`, `tarfile`, `threading`, and `time`; Docker Compose and MySQL 8; existing DRA REST,
SQLite application authority, `scripts/downstream_consumer_contract.py`, and GitHub Actions.

## Global Constraints

- Implement only
  `docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md` from the clean
  branch containing the approved design and this plan.
- This plan delivers Change 1 only: harness, deterministic contracts, provider-free CI, required
  Docker fixture, reference documentation, and `Unreleased` discovery. Keep `VERSION=0.1.5`.
- Do not execute `observe-live`, use provider credentials, make a model/search request, or create
  `docs/evidence/bounded-live-producer-v1.json` or `.md` during implementation or required CI.
- Do not modify REST/OpenAPI paths or payloads, database schemas or migrations, canonical result or
  Evidence schemas, Tool Client behavior, profiles, middleware, LangGraph/DeepAgents/LangChain
  authority, LangSmith authority, Docker product defaults, or existing evidence baselines.
- Do not add dependencies. Prefer strict Pydantic models and the existing downstream projection;
  keep Git, Docker, HTTP observation, report publication, and cleanup in small application-owned
  modules because the Agent frameworks do not own those concerns.
- `check` must be provider-free, credential-free, Docker-free, external-network-free, import-silent,
  and deterministic. It validates the canonical manifest and contract registry; it does not emit or
  imitate live evidence.
- `observe-live` may accept only the dedicated external env-file path and bounded non-secret
  provider/model/pricing declarations. Credentials remain in the external file or the exact
  `DECISION_RESEARCH_AGENT_API_KEY` process variable and are never CLI values or output fields.
- Live output destinations are fixed to the two exact absent evidence paths. Do not add arbitrary
  output options. Validate them before Docker mutation and publish only after successful cleanup.
- Reuse `scripts.downstream_consumer_contract.project_consumer_case` unchanged. Acceptance is
  exactly `supported / accept_draft`; never translate that into delivery, approval, truth, adoption,
  or downstream business authority.
- Preserve the exact request bytes and one idempotency key through at most one ambiguous-create
  replay. Do not retry complete HTTP errors, terminal execution failures, provider/tool failures,
  restart drift, replay drift, output failures, or cleanup failures.
- One outer monotonic 3,450-second deadline starts before input validation. Non-cleanup work is
  capped at 3,330 seconds, cleanup has a 120-second child reserve contained in the outer bound, and
  report publication consumes only outer time remaining after cleanup. Tests must prove no
  negative sleep, post-deadline publication, or fresh retry budget.
- Public reports and stable errors must contain no secrets, raw query/scope, report content,
  snippets, tool/provider payloads, logs, raw errors, tracebacks, local paths, local ports, Docker
  resource names, host identity, private consumer names, or unsupported production claims.
- Use TDD for every behavior change: focused RED, minimal implementation, focused GREEN, broader
  affected matrix, then a small local commit. A green test that bypasses the actual typed,
  transport, lifecycle, consumer, or cleanup path is not completion evidence.
- Public documentation remains English and public-neutral. The implementation branch must contain
  no private paths, private project names, credentials, or development motivation.
- Do not push, create or update a pull request, merge, tag, publish a release, deploy, or clean a
  worktree without separate authorization.

---

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `benchmarks/bounded-live-producer-v1/manifest.json` | Exact public scenario, terminal/artifact/Evidence policy, resource bounds, usage policy, fixed output policy, and non-claims |
| `scripts/bounded_live_producer_contracts.py` | Strict manifest/report/error models, bounded canonical reads, public-safety validation, JSON/Markdown serializers, fixed boundaries and limits |
| `scripts/bounded_live_producer_http.py` | `http.client`-based exact-loopback transport, header allowlist, no proxy/redirect behavior, bounded bodies, stable typed failures, ambiguous-create classification |
| `scripts/bounded_live_producer_lifecycle.py` | Clean Git/source receipt, safe tracked archive/extraction, env preflight, sanitized Compose projection, subprocess budgets, task-owned lifecycle and cleanup |
| `scripts/bounded_live_producer_proof.py` | Provider-free `check`, separately authorized `observe-live`, run polling, consumer projection, usage, restart/replay comparison, stable CLI and paired publication |
| `scripts/bounded_live_producer_container_fixture.py` | Test-only deterministic dispatch server used by the required Docker lane; no public runtime flag or provider call |
| `tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml` | Tracked test-only override that changes only the backend command and exact fixture guard without adding services, ports or mounts |
| `tests/unit/test_bounded_live_producer_contracts.py` | Strict model, manifest, report, serializer, public-safety, size and decimal contracts |
| `tests/unit/test_bounded_live_producer_http.py` | Exact loopback, headers, response bounds, redirects, errors, create ambiguity, identity and deadline tests |
| `tests/unit/test_bounded_live_producer_lifecycle.py` | Git/archive/env/Compose/subprocess/deadline/ownership/cleanup unit and mutation tests |
| `tests/integration/test_bounded_live_producer_proof.py` | Fake lifecycle plus real orchestrator, status/result/Evidence/usage/restart/replay and CLI fail-closed matrix |
| `tests/integration/test_bounded_live_producer_container.py` | Required provider-free Docker lifecycle from exact tracked archive through restart, replay and zero-residue cleanup |
| existing required-Docker budget contracts | Account for the fourth bounded lifecycle and preserve at least 15 minutes of hosted-job headroom |
| `.github/workflows/ci.yml` | Run provider-free `check` before non-Docker pytest; existing required Docker job discovers the new Docker-marked test |
| `docs/reference/bounded-live-producer-evaluation.md` | Public command, authorization boundary, exact scenario, evidence interpretation, failure codes, operation and non-claims |
| shared README/docs/CHANGELOG files | Discover the implemented harness while stating that no live observation is yet committed |
| documentation/release contract tests | Lock discovery, provider-free/live separation, unchanged version, absent live evidence and honest non-claims |

## Exact Contract Shapes

### Manifest

The checked-in manifest is canonical JSON with these exact field-order keys and values:

```json
{
  "schema_version": "dra.bounded-live-producer-manifest.v1",
  "scenario_id": "cpython-313-free-threaded-pilot",
  "profile_id": "generic",
  "query": "Using official Python documentation and Python Enhancement Proposals, compare the principal deployment benefits, compatibility limits, and operational caveats of the optional free-threaded CPython 3.13 build. Produce a concise decision brief for a backend team evaluating a bounded pilot, cite factual claims, and state unresolved limitations.",
  "scope": {},
  "required_cited_domains": [
    "docs.python.org",
    "peps.python.org"
  ],
  "terminal_policy": {
    "execution_status": "completed",
    "review_status": "not_required",
    "delivery_status": "ready",
    "failure_cause": null,
    "artifact_id": "research-report.md",
    "artifact_kind": "research_report_markdown",
    "artifact_media_type": "text/markdown",
    "consumer_support": "supported",
    "consumer_disposition": "accept_draft"
  },
  "bounds": {
    "query_utf8_bytes_min": 1,
    "query_utf8_bytes_max": 4096,
    "scope_utf8_bytes_max": 16384,
    "scope_depth_max": 8,
    "scope_nodes_max": 256,
    "required_domains_min": 1,
    "required_domains_max": 8,
    "idempotency_key_ascii_length_min": 8,
    "idempotency_key_ascii_length_max": 128,
    "idempotency_key_entropy_bits_min": 128,
    "archive_bytes_max": 67108864,
    "archive_members_max": 4096,
    "archive_member_bytes_max": 16777216,
    "subprocess_stream_bytes_max": 1048576,
    "http_response_bytes_max": 2097152,
    "artifact_utf8_bytes_min": 1,
    "artifact_utf8_bytes_max": 1048576,
    "evidence_count_min": 1,
    "evidence_count_max": 100,
    "public_json_bytes_max": 1048576,
    "public_markdown_bytes_max": 1048576,
    "docker_probe_seconds": 30,
    "active_lifecycle_seconds": 3300,
    "build_start_seconds": 1200,
    "research_seconds": 1800,
    "restart_replay_seconds": 300,
    "cleanup_seconds": 120,
    "total_wall_seconds": 3450
  },
  "usage_policy": {
    "token_usage": "observed_or_not_observed",
    "cost_estimate": "not_observed",
    "search_cost": "not_observed",
    "durable_usage": "not_claimed",
    "provider_invoice": "not_claimed"
  },
  "output_policy": {
    "json_path": "docs/evidence/bounded-live-producer-v1.json",
    "markdown_path": "docs/evidence/bounded-live-producer-v1.md",
    "overwrite": false
  },
  "non_claims": [
    "downstream_business_acceptance",
    "source_truth_or_independent_verification",
    "exactly_once_execution_or_provider_side_effects",
    "running_execution_recovery",
    "multi_instance_high_availability",
    "durable_usage_or_provider_billing",
    "hosted_production_or_sla"
  ]
}
```

The loader requires the file bytes to equal the canonical serializer output plus one final newline.
The published manifest SHA-256 therefore binds the exact checked-in bytes, not an equivalent but
differently formatted JSON object.

### Public Live Report

The report uses this exact top-level key set; the model preserves the shown field order while the
JSON serializer uses stable sorted-key output:

```text
schema_version, status, source, scenario, lifecycle, run, result, evidence,
usage, restart, replay, cleanup, boundaries, limits
```

Nested responsibilities are fixed as follows:

| Field | Exact public content |
|---|---|
| `source` | canonical repository/service names, VERSION, commit, tree, archive/manifest/sanitized-Compose hashes, backend image ID, bounded Docker/Compose versions, `source_clean=true`, `build_context=tracked_archive` |
| `scenario` | scenario ID, manifest/request hashes, `profile_id=generic`, ordered required domains, bounded operator-declared provider and model IDs; no query/scope/key |
| `lifecycle` | integer phase/active/total milliseconds and booleans for loopback binding and exact health; no timestamps, local ports or resource names |
| `run` | run/thread/segment IDs, accepted state version and exact terminal tuple with null failure cause |
| `result` | artifact ID/kind/media type, UTF-8 byte length, SHA-256, consumer support/disposition; no content |
| `evidence` | ordered six-field allowlist rows only |
| `usage` | discriminated `observed` or `not_observed`; nested cost estimate is independently discriminated |
| `restart` | same-identity/state/Evidence/artifact and non-regressing-version booleans |
| `replay` | `idempotent_replay=true`, same run/thread/segment booleans, and unchanged terminal projection boolean |
| `cleanup` | attempted/succeeded plus zero unapproved task-owned container/volume/network/temp residue booleans; an explicitly retained task image is local-only and never described in the report |
| `boundaries` | one fixed strict object covering producer observation and all non-claims |
| `limits` | one fixed ordered list rendered unchanged in Markdown |

Use strict frozen `extra="forbid"` Pydantic models for every nested object. The error envelope has
exact keys `schema_version`, `code`, `phase`, `retryable`, and `cleanup_status`, with schema
`dra.bounded-live-producer-evaluation-error.v1`. `cleanup_status` is exactly one of
`not_started`, `succeeded`, or `failed`.

The failure registry uses the approved phase/code pairs and rejects cross-phase combinations:

| Phase | Codes |
|---|---|
| `input` | `manifest_invalid`, `source_dirty`, `source_identity_invalid`, `credential_source_invalid`, `output_invalid` |
| `docker` | `docker_unavailable`, `compose_config_invalid`, `source_archive_invalid`, `image_build_failed`, `service_start_failed`, `service_identity_invalid` |
| `create` | `create_rejected`, `create_response_invalid`, `create_identity_mismatch`, `create_reconciliation_unresolved` |
| `observe` | `run_observation_deadline`, `run_state_invalid`, `run_failed`, `run_fallback_rejected`, `run_delivery_not_ready` |
| `result` | `consumer_projection_invalid`, `artifact_invalid`, `artifact_hash_mismatch` |
| `evidence` | `evidence_missing`, `evidence_invalid`, `evidence_domain_rejected`, `required_cited_domain_missing` |
| `usage` | `usage_invalid` |
| `restart` | `backend_restart_failed`, `restart_identity_drift`, `restart_evidence_drift`, `restart_artifact_drift` |
| `replay` | `idempotent_replay_invalid`, `duplicate_run_observed` |
| `output` | `report_invalid`, `output_exists`, `output_write_failed` |
| `cleanup` | `cleanup_failed` |
| `internal` | `evaluation_internal_error` |

Deadline exhaustion maps to the stable code for the active phase; do not add a generic deadline
code outside this registry.

## Ordering, Isolation, And Parallel Work

1. Task 1 is foundational and serial.
2. After Task 1 commits, Tasks 2 and 3 are independent candidates for parallel isolated lanes:
   Task 2 owns only HTTP files; Task 3 owns only lifecycle files. Both start from the exact Task 1
   commit and may import contracts but may not modify them.
3. The parent integrates those lanes, resolves no semantic conflicts by default, and owns Task 4's
   orchestrator, shared contracts adjustments, and full focused verification.
4. Task 5 depends on Tasks 1–4. A docs lane for the non-shared reference draft may run while the
   required Docker test executes, but the parent alone owns CI, shared README/docs indexes,
   `CHANGELOG.md`, documentation tests, and final wording.
5. If isolated worktrees, child-agent permissions, or clean file ownership are unavailable, execute
   the same tasks serially. Do not create parallelism around shared contract, CI, or discovery files.
6. Child lanes return one bounded clean commit. The parent owns integration, near-field review,
   complete verification, worktree inventory, and the final clean branch handoff.

---

## Task 1: Add The Canonical Manifest And Strict Contracts

**Files:**

- Create: `benchmarks/bounded-live-producer-v1/manifest.json`
- Create: `scripts/bounded_live_producer_contracts.py`
- Create: `tests/unit/test_bounded_live_producer_contracts.py`

**Interfaces:**

- Produces: `ManifestModel`, `LiveReportModel`, `ErrorEnvelope`, `FailurePhase`, `FailureCode`,
  `CleanupStatus`, `EvaluationValidationError`, `EvaluationError`, `load_manifest`,
  `serialize_manifest`, `validate_live_report`, `serialize_report`, `render_markdown`,
  `serialize_error`, and fixed boundary/limit registries.
- Consumes: bounded Python objects and exact manifest/report bytes only. It imports no API server,
  Agent runtime, Docker client, network transport, or credential loader.

- [ ] **Step 1: Write strict RED tests for the manifest and variants**

Cover exact keys, frozen instances, no coercion, newline normalization, scope byte/depth/node
bounds, exact lowercase DNS domains, duplicate domains, the exact 8-128 ASCII idempotency-key
length bounds, the 128-bit minimum entropy bound, canonical manifest bytes, exact output paths, and
every terminal/non-claim value. Include both valid usage variants and both cost variants:

```python
def test_manifest_is_canonical_and_exact():
    raw = MANIFEST_PATH.read_bytes()
    manifest = load_manifest(MANIFEST_PATH)

    assert manifest.schema_version == "dra.bounded-live-producer-manifest.v1"
    assert manifest.profile_id == "generic"
    assert manifest.required_cited_domains == (
        "docs.python.org",
        "peps.python.org",
    )
    assert serialize_manifest(manifest) == raw


def test_strict_usage_rejects_bool_as_integer():
    with pytest.raises(ValidationError):
        ObservedUsage.model_validate(
            {
                "status": "observed",
                "prompt_tokens": True,
                "completion_tokens": 1,
                "total_tokens": 2,
                "call_count": 1,
                "cost_estimate": {"status": "not_observed"},
            },
            strict=True,
        )


def test_report_adapter_maps_usage_validation_to_stable_error(safe_report_dict):
    safe_report_dict["usage"]["prompt_tokens"] = True

    with pytest.raises(EvaluationValidationError, match="usage_invalid"):
        validate_live_report(safe_report_dict)
```

- [ ] **Step 2: Write RED report/public-safety/serializer tests**

Build one in-memory safe report fixture in the test file and mutate every exact top-level key,
nested identity, Evidence field, URL, decimal, size, boundary, limit, ordering and public-safety
rule. Assert query text, report Markdown, snippets, credentials, paths, local ports, Docker names,
raw errors, NaN/Infinity, unknown keys and private URL shapes fail closed. Assert serialization of
one validated object is byte-identical twice and Markdown is derived only from validated JSON data.

- [ ] **Step 3: Run Task 1 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_contracts.py -q
```

Expected: collection fails because `scripts.bounded_live_producer_contracts` does not exist.

- [ ] **Step 4: Implement the minimal strict model registry**

Define `FailurePhase`, `FailureCode`, and `CleanupStatus` from the exact fixed registry above.
`EvaluationValidationError(ValueError)` represents an in-memory manifest/report/serializer
contract violation and is never serialized directly. `EvaluationError(Exception)` is a frozen
operational failure carrying one validated phase/code pair, `retryable`, and `cleanup_status`; only
it may be converted to the public error envelope. No later task defines a second exception or
stringly typed failure registry.

Use a common model base and explicit discriminators:

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CostNotObserved(StrictModel):
    status: Literal["not_observed"]


class ObservedUsage(StrictModel):
    status: Literal["observed"]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    call_count: int = Field(gt=0)
    cost_estimate: CostNotObserved
    search_cost: CostNotObserved


class UsageNotObserved(StrictModel):
    status: Literal["not_observed"]


UsageObservation = Annotated[
    ObservedUsage | UsageNotObserved,
    Field(discriminator="status"),
]
```

Reject every observed-cost object in Change 1, including a syntactically canonical legacy variant;
only `{"status":"not_observed"}` is valid for cost estimate and search cost. Enforce exact six-field
Evidence models and URL/domain rules independently of the current consumer validator so unsafe
additive fields cannot enter the report; still use the existing consumer projection later for
semantic acceptance.

- [ ] **Step 5: Implement bounded canonical reads and renderers**

`load_manifest` must use `lstat`, regular-file/no-symlink checks, `O_NOFOLLOW` where available,
inode recheck, a strict byte maximum, UTF-8 decoding, strict Pydantic validation, and canonical-byte
equality. `serialize_manifest` uses strict model field order, two-space indentation and one final
newline so it matches the displayed checked-in manifest. `serialize_report` uses
`model_dump(mode="json")`, sorted keys, two-space indentation and one final newline.
`render_markdown` validates the model first and emits only allowlisted receipt facts in fixed
section order.

- [ ] **Step 6: Run Task 1 GREEN and mutation checks**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_contracts.py -q
```

Expected: all tests pass, including manifest formatting and public-safety mutations.

- [ ] **Step 7: Commit Task 1**

```bash
git add benchmarks/bounded-live-producer-v1/manifest.json \
  scripts/bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_contracts.py
git diff --cached --check
git commit -m "feat(eval): define bounded live producer contracts"
```

---

## Task 2: Add The Exact Loopback HTTP Transport

**Files:**

- Create: `scripts/bounded_live_producer_http.py`
- Create: `tests/unit/test_bounded_live_producer_http.py`

**Interfaces:**

- Produces: `ProofHttpClient`, `HttpObservation`, `CreateAmbiguous`, and typed methods `health`,
  `create`, `status`, `result`, and `usage`.
- Consumes: an inspected positive backend host port, in-memory API key, and a callable that returns
  the remaining monotonic deadline. It never reads ambient proxy variables or credential files.

- [ ] **Step 1: Write RED transport construction tests**

Expose no base-URL or hostname input. Accept only an inspected positive integer port and reject
bool, zero, overflow and other malformed values. Patch `http.client.HTTPConnection` and require the
wire target to be exactly host `127.0.0.1` plus that port. Because callers cannot supply a scheme,
host, userinfo, path prefix, query or fragment, those URL variants are absent from the construction
surface rather than parsed and normalized. Assert ambient `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`
and `NO_PROXY` never affect the target.

- [ ] **Step 2: Write RED request/response tests**

Freeze exact methods, paths and the complete wire header set. Build requests with
`putrequest(..., skip_host=True, skip_accept_encoding=True)` and explicit `putheader` calls so
`http.client` cannot add unreviewed defaults. Every request includes exact `Host`,
`Accept: application/json`, `Accept-Encoding: identity`, and `X-API-Key`; `POST` additionally uses
exact JSON `Content-Type`, byte-accurate `Content-Length`, and `Idempotency-Key`. No other wire
header is permitted. Reject any 3xx without following it. Stream in bounded chunks, reject
oversized declared or actual bodies, reject non-object JSON, close every connection, and map
complete HTTP errors without retry.

Cover create semantics explicitly:

```python
def test_create_body_read_failure_is_ambiguous_once(client, connection):
    connection.response.read.side_effect = OSError("injected")

    with pytest.raises(CreateAmbiguous):
        client.create(request_bytes=REQUEST_BYTES, idempotency_key="proof-key-123456")


def test_malformed_create_json_is_not_ambiguous(client, connection):
    connection.response.status = 200
    connection.response.read.return_value = b"not-json"

    with pytest.raises(EvaluationError, match="create_response_invalid"):
        client.create(request_bytes=REQUEST_BYTES, idempotency_key="proof-key-123456")
```

- [ ] **Step 3: Write RED identity and deadline tests**

Require create acknowledgement thread/run/segment identity, replay flag type, requested run ID on
status/result, exact health body, and the token-usage key set. Use a fake monotonic remaining-time
callable to prove every connection receives only remaining time and exhaustion happens before I/O.

- [ ] **Step 4: Run Task 2 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_http.py -q
```

Expected: collection fails because `scripts.bounded_live_producer_http` does not exist.

- [ ] **Step 5: Implement the minimal no-proxy/no-redirect client**

Use `http.client.HTTPConnection` directly; it has no environment-proxy or redirect behavior:

```python
class ProofHttpClient:
    def __init__(
        self,
        *,
        port: int,
        api_key: str,
        remaining_seconds: Callable[[float], float],
    ) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise EvaluationError("service_identity_invalid", "docker", False)
        self._port = port
        self._api_key = api_key
        self._remaining_seconds = remaining_seconds

    def _connection(self, requested_timeout: float) -> HTTPConnection:
        timeout = self._remaining_seconds(requested_timeout)
        return HTTPConnection("127.0.0.1", self._port, timeout=timeout)
```

Implement one `_request_json` path with the explicit low-level wire construction above,
response-size accounting and stable typed failures. Never include request URLs, headers, response
bodies or exception text in an `EvaluationError`.

- [ ] **Step 6: Run Task 2 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_http.py -q
```

- [ ] **Step 7: Commit Task 2**

```bash
git add scripts/bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_http.py
git diff --cached --check
git commit -m "feat(eval): add bounded live proof transport"
```

---

## Task 3: Add Tracked Source And Managed Compose Lifecycle

**Files:**

- Create: `scripts/bounded_live_producer_lifecycle.py`
- Create: `tests/unit/test_bounded_live_producer_lifecycle.py`

**Interfaces:**

- Produces: `LifecycleBudget`, `ActiveDeadline`, `SourceSnapshot`, `CredentialDeclaration`,
  `ManagedComposeProject`, `prepare_source_snapshot`, `load_live_configuration`,
  `sanitize_compose_projection`, `run_bounded_subprocess`, and `cleanup_receipt`.
- Consumes: the current clean Git checkout, one strict external env file, non-secret declaration,
  Docker CLI/Compose, and a task-owned temporary root.

- [ ] **Step 1: Write RED source identity and archive tests**

Use tiny temporary Git repositories. Require exact 40-character HEAD and tree, empty porcelain
status including untracked files, strict VERSION, and required tracked paths. Assert dirty or
untracked source fails before a fake Docker mutation counter increments.

Generate a real uncompressed `git archive --format=tar HEAD`. Test exact SHA, member count, total
size, per-member size, duplicate/case-colliding paths, absolute paths, `..`, backslash, NUL, links,
devices, sparse/special types and extraction escape. Extraction writes only regular files and
directories under a newly created task temp root. Compare accepted archive membership to
`git ls-tree -r --name-only HEAD` so a bounded but incomplete archive also fails closed.

- [ ] **Step 2: Write RED env/declaration/Compose sanitation tests**

Require the env file to be a current-user-owned regular non-symlink with owner-read permission and
no group/other permission bits, unique keys, UTF-8 bounded lines and an exact allowlist. Accept
owner-only `0400` or `0600`; do not require owner write permission. Require non-empty `API_SECRET`, MySQL passwords,
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, and `TAVILY_API_KEY`.
Require the process API key to match `API_SECRET` without publishing either value.

Require all three optional product fixtures/gates false, tracing false, LangSmith/RAGFlow credential
values empty, and provider/model values equal the bounded operator declaration. Validate the
provider URL as public HTTPS with no userinfo/query/fragment/non-default port and only empty or
`/v1` path. Reject IP literals that are not global and local/private suffixes.

The dedicated env file accepts exactly these names:

```text
OPENAI_BASE_URL
OPENAI_API_KEY
LLM_MODEL
LLM_FALLBACK_MODEL
API_SECRET
TAVILY_API_KEY
MYSQL_ROOT_PASSWORD
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES
DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL
DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION
LANGSMITH_TRACING
LANGSMITH_API_KEY
LANGSMITH_HIDE_INPUTS
LANGSMITH_HIDE_OUTPUTS
RAGFLOW_API_KEY
TOKEN_PRICING_JSON
TOKEN_PRICING_BASIS
TOKEN_PRICING_CURRENCY
```

The first ten values are non-empty. The three feature flags and tracing are exactly `false`;
LangSmith/RAGFlow keys are empty; the two LangSmith privacy flags are exactly `true`.
`TOKEN_PRICING_JSON`, `TOKEN_PRICING_BASIS`, and `TOKEN_PRICING_CURRENCY` are either all absent or
all present. When present, pricing JSON is bounded canonical JSON with finite non-negative rates,
and basis/currency match the optional public CLI declaration. Unknown names, legacy model aliases,
database path overrides, CORS configuration, proxy variables and unrelated service configuration
fail preflight.

Mutate resolved Compose shapes around services, build, ports, env file, secrets, volumes, health,
privileges and networks. `sanitize_compose_projection` must reject unknown secret-bearing shapes,
replace approved secret/path fields with constant type markers, and hash only canonical safe JSON.

- [ ] **Step 3: Write RED global/phase deadline and subprocess tests**

Test the exact live budget:

```python
LIVE_BUDGET = LifecycleBudget(
    docker_probe_seconds=30,
    active_seconds=3300,
    build_start_seconds=1200,
    research_seconds=1800,
    restart_replay_seconds=300,
    cleanup_seconds=120,
    total_wall_seconds=3450,
)
```

Use a fake clock to prove nested phase bounds never extend the active deadline, one retry receives
only remaining time, no negative sleep occurs, and cleanup gets exactly its independent reserve.
`run_bounded_subprocess` must drain both streams while retaining at most 1 MiB each, kill/wait on
timeout, reject overflow unless the exact command uses an approved quiet mode, and never inherit
proxy/provider/credential variables outside the scrubbed allowlist.

Close the validated in-memory credential snapshot on every later exit path. Record the exact
random task-temp path before snapshot preparation; if probe, snapshot, project construction,
ownership transition, or the final pre-guard deadline check fails, remove only that path through a
cleanup child inside the total deadline's 120-second reserve. Preserve primary plus cleanup failure
as the existing stable dual-cause contract, then hand authority to normal project cleanup only
after the pre-guard transition succeeds.

- [ ] **Step 4: Write RED ownership and cleanup tests**

Require a random exact project ID, refusal if any resource already has its exact Compose label,
recorded IDs before deletion, dynamic host-port overrides `0`, loopback HostIp, exact backend/MySQL
services, and no global/prefix cleanup. Cover primary-only, cleanup-only and grouped dual failures.
Cleanup attempts recorded containers, volumes, networks, temp paths and task image tags in fixed
order, preserves pre-existing images/cache, and verifies zero task-owned residue.

- [ ] **Step 5: Run Task 3 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_lifecycle.py -q
```

Expected: collection fails because `scripts.bounded_live_producer_lifecycle` does not exist.

- [ ] **Step 6: Implement the minimal source and deadline primitives**

Use a frozen typed budget and deadline:

```python
@dataclass(frozen=True)
class LifecycleBudget:
    docker_probe_seconds: int
    active_seconds: int
    build_start_seconds: int
    research_seconds: int
    restart_replay_seconds: int
    cleanup_seconds: int
    total_wall_seconds: int


class ActiveDeadline:
    def __init__(
        self,
        seconds: float,
        *,
        code: FailureCode,
        phase: FailurePhase,
        monotonic=time.monotonic,
    ) -> None:
        self._monotonic = monotonic
        self._deadline = monotonic() + seconds
        self._code = code
        self._phase = phase

    def remaining(self, requested: float) -> float:
        value = self._deadline - self._monotonic()
        if value <= 0:
            raise EvaluationError(self._code, self._phase, False)
        return min(requested, value)
```

Create archive output only inside a new task temp directory. Inspect with `tarfile` but extract
members manually; do not call `extractall`. Hash exact archive bytes and verify every required file
exists in the extracted snapshot before Compose runs. Execute the existing
`scripts/secure_local_runtime_proof.py check` from the extracted snapshot under the scrubbed
provider-free environment; do not copy its Compose/Dockerfile security rules into the new harness.

- [ ] **Step 7: Implement managed lifecycle and cleanup**

All Compose commands use the extracted root, explicit `--env-file`, explicit checked-in Compose
file, exact random project name, a scrubbed environment, bounded stream capture and remaining
deadline. Expose separate `build_backend`, `start_mysql`, and `start_backend` methods.
`ManagedComposeProject` accepts an internally constructed, validated ordered tuple of tracked
Compose paths: the live orchestrator uses only the product Compose file, while the Docker test uses
that file plus the exact tracked fixture override for every Compose operation. Neither the live CLI
nor the manifest may supply a shell command, arbitrary path, or fixture mode.

Record immutable container/image/network/volume receipts before observation. The live CLI must not
accept a shell command or fixture mode. Cleanup uses exact recorded IDs plus `docker compose down
-v --remove-orphans`, followed by removal of only the exact task image tag/ID when retention was not
requested. Do not use `--rmi local`, name-prefix deletion, label-wide deletion or any prune command.
Verify the receipt inventory and preserve the shared MySQL image and build cache.

- [ ] **Step 8: Run Task 3 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_lifecycle.py -q
```

- [ ] **Step 9: Commit Task 3**

```bash
git add scripts/bounded_live_producer_lifecycle.py \
  tests/unit/test_bounded_live_producer_lifecycle.py
git diff --cached --check
git commit -m "feat(eval): add managed producer lifecycle"
```

---

## Task 4: Compose Run Observation, Restart, Replay And CLI

**Files:**

- Create: `scripts/bounded_live_producer_proof.py`
- Create: `tests/integration/test_bounded_live_producer_proof.py`
- Modify if a strict model gap is exposed: `scripts/bounded_live_producer_contracts.py`
- Modify corresponding tests only: `tests/unit/test_bounded_live_producer_contracts.py`

**Interfaces:**

- Produces: `run_provider_free_check`, `observe_live`, `project_live_observation`,
  `reconcile_create`, `observe_usage`, `compare_restart`, `validate_replay`, atomic paired output,
  and stable `main`.
- Consumes: Tasks 1–3, existing REST payloads, and
  `scripts.downstream_consumer_contract.project_consumer_case`.

- [ ] **Step 1: Write RED provider-free check and CLI tests**

`check` loads the exact manifest, validates fixed registries and performs deterministic serializer
round trips without Docker, credentials or network. Assert exact success stdout:

```json
{"mode":"provider_free","schema_version":"dra.bounded-live-producer-manifest.v1","status":"valid"}
```

Assert invalid/missing commands and arguments return one canonical error line on stderr, empty
stdout and exit 1; `--help`, `check --help`, and `observe-live --help` return 0. Importing the module
must be silent and must not import `api.server`, Agent provider modules or initialize Docker.

- [ ] **Step 2: Write RED create and terminal-state orchestration tests**

Use fake lifecycle and real `ProofHttpClient` method doubles. Cover first acceptance, one ambiguous
acknowledgement replay, second ambiguity, complete HTTP error, conflict/unavailable ledger,
malformed/identity-mismatched acknowledgement, and exact key/request object identity across calls.

Poll with one research deadline. Cover every supported/rejected execution/review/delivery/failure
tuple. Accept only `completed/not_required/ready`, null failure cause and generic profile. Deadline
expiry stops client observation without calling cancellation.

- [ ] **Step 3: Write RED consumer/result/Evidence tests**

Call the real `project_consumer_case` with the observed status and result. Mutation-test
`supported/accept_draft`, requested identity, canonical artifact ID/kind/media/size/hash, fallback,
missing/duplicate/reordered Evidence, extra fields, non-public URLs, query/fragment/port, malformed
timestamps, uncited rows, and missing each required domain. Assert artifact text remains only in
bounded memory and is absent from report/error/diagnostic serialization.

- [ ] **Step 4: Write RED usage, restart and replay tests**

Cover zero/missing usage as `not_observed`; positive consistent token totals as `observed`; and
malformed totals as `usage_invalid`. In Change 1, cost estimate and search cost are always
`not_observed`: the aggregate endpoint cannot bind tokens to exact per-call model and rate
selection, even when declarations and runtime pricing configuration are present. Mutation-test a
well-formed legacy observed-cost variant and require strict rejection.

After a fake backend restart, require exact health, run/thread/segment identity, non-regressing state
version, byte-identical ordered Evidence allowlist, artifact metadata/length/hash, and unchanged
consumer disposition. Then replay the exact request/key and require `idempotent_replay=true`, exact
identities and unchanged terminal projection. Mutations must map to the stable restart/replay codes.

- [ ] **Step 5: Write RED paired-output and dual-failure tests**

Validate only the exact repository destinations before mutation. Reject existing files, symlinks,
aliases, unwritable parents and path replacement races. Stage sibling files with `O_EXCL`, fsync,
publish Markdown first and JSON machine authority last using atomic no-replace hard-link semantics,
then fsync the directory. A failure before the JSON link must leave no authoritative JSON even when
unlink and rename rollback persistently fail. JSON is acceptable only with matching Markdown and a
successful reviewed publication; an unremovable Markdown-only residue is non-authoritative and
blocks overwrite. Preserve stable primary output errors and all pre-existing paths.

Inject primary-only, cleanup-only and dual failures. The internal grouped exception retains both
typed causes; the public line retains only stable primary code plus `cleanup_status=failed`.

- [ ] **Step 6: Run Task 4 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_bounded_live_producer_proof.py -q
```

Expected: collection fails because `scripts.bounded_live_producer_proof` does not exist.

- [ ] **Step 7: Implement provider-free `check` and the stable CLI boundary**

Use a parser whose `.error()` raises a typed evaluation error. The live parser accepts exactly:

```text
observe-live
  --env-file PATH
  --provider-id IDENTIFIER
  --provider-base-url HTTPS_URL
  --primary-model-id IDENTIFIER
  --fallback-model-id IDENTIFIER
  [--pricing-basis IDENTIFIER --currency ISO_4217]
  [--retain-task-images]
```

Pricing flags are an all-or-none pair and must match the optional three-field pricing declaration
inside the dedicated env file. Their absence forces `cost_estimate.status=not_observed`.

No credential, query, scope, URL override, Compose file, project name, repository root, output path,
retry count or deadline option is accepted. The process API key comes only from
`DECISION_RESEARCH_AGENT_API_KEY`. `main` emits canonical sorted compact JSON success/error lines
and never prints exception text.

- [ ] **Step 8: Implement one-run orchestration**

Generate a thread ID and idempotency key with at least 128 random bits, build one immutable request
object, and retain its canonical bytes. Use contract-safe prefixes plus `secrets.token_hex(16)`;
do not use `uuid.uuid4()` as the entropy proof. Compute the request digest through the existing
`api.run_creation_models.run_create_request_hash` rather than defining a second fingerprint.
Reconciliation is exactly:

```python
def reconcile_create(client, *, request_bytes: bytes, key: str):
    try:
        accepted = client.create(
            request_bytes=request_bytes,
            idempotency_key=key,
        )
        require_create_identity(accepted, replay=False)
        return accepted
    except CreateAmbiguous:
        try:
            replayed = client.create(
                request_bytes=request_bytes,
                idempotency_key=key,
            )
        except CreateAmbiguous as exc:
            raise EvaluationError(
                "create_reconciliation_unresolved",
                "create",
                False,
            ) from exc
        require_create_identity(replayed, replay=True)
        return replayed
```

Keep the key out of all model dumps and local diagnostics. Pass status/result to the existing
consumer projection and require exact acceptance before usage/restart/replay.

- [ ] **Step 9: Implement validation, cleanup-first publication and error projection**

Capture bounded comparison facts before restart, not raw content. Build and validate the final
report only after cleanup succeeds and its receipt is added. Serialize the same validated model
twice and require byte equality before paired publication. On any failure after mutation, always
attempt cleanup. One wall deadline created before input validation reserves cleanup inside the
3,450-second total, narrows every non-cleanup phase, and bounds post-cleanup report serialization
and paired publication before output mutation. Do not expose failed output as acceptable live
evidence.

- [ ] **Step 10: Run Task 4 GREEN and combined focused tests**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py -q

PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
```

Expected CLI stdout is the exact provider-free success object; stderr is empty.

- [ ] **Step 11: Commit Task 4**

```bash
git add scripts/bounded_live_producer_contracts.py \
  scripts/bounded_live_producer_proof.py \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/integration/test_bounded_live_producer_proof.py
git diff --cached --check
git commit -m "feat(eval): reconcile bounded live producer runs"
```

---

## Task 5: Prove The Provider-Free Docker Lifecycle

**Files:**

- Create: `scripts/bounded_live_producer_container_fixture.py`
- Create: `tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml`
- Create: `tests/integration/test_bounded_live_producer_container.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`
- Modify only if test seams are required: `scripts/bounded_live_producer_lifecycle.py`
- Modify corresponding tests only: `tests/unit/test_bounded_live_producer_lifecycle.py`

**Interfaces:**

- Produces: one test-only fixture server guarded by
  `DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE=true`, one tracked Compose command override,
  and one Docker-marked lifecycle test.
- Consumes: production repository finalization, the exact tracked archive lifecycle, and public
  protected API observation. It never invokes the Agent runtime or provider/search network.

- [ ] **Step 1: Write RED fixture, override and Docker lifecycle tests**

The tracked override changes only the backend command to
`python scripts/bounded_live_producer_container_fixture.py serve` and sets
`DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE=true`; it adds no service, port or bind mount.
Without the exact test-only flag the fixture server fails at startup. Import `api.server` under the
provider-disabled fixture environment, replace only `api.server.create_run_dispatch_worker` before
entering the application lifespan, and then serve the existing FastAPI app. The existing server
module transitively imports `agent.main_agent`; import isolation is therefore not a claim. The first
real protected `POST /api/runs` still crosses the production idempotency ledger, dispatch claim,
and start fence. The deterministic scheduler must never call `run_deep_agent`, provider clients or
search tools; it finalizes one canonical Markdown artifact and two cited public Evidence rows for
the required domains through production repository functions.

Use the production repository functions rather than SQL shortcuts:

```python
started = start_run_dispatch(
    db_path=db_path,
    claim=claim,
)
finalized = finalize_run_transaction(
    run_id=claim.run_id,
    segment_id=claim.segment_id,
    expected_state_version=1,
    allowed_previous_statuses={"running"},
    execution_status="completed",
    review_status="not_required",
    delivery_status="ready",
    evidence_entries=evidence_entries,
    artifacts=[artifact],
)
```

Build the artifact through `build_generic_result_artifact` and production `EvidenceEntry` values.
Assert `started is True`. Patch `api.server.run_deep_agent` with a fail-on-call sentinel and assert
it remains untouched. Also assert the fixture creates no provider/search callbacks, enables no
review or verification, and never describes its output as live evidence.

Add the Docker-marked test now as well. It must begin from a clean tracked `HEAD`, request the
exact checked-in override, perform a real protected create through the lifecycle API, and require
the production ledger/start fence, restart, replay, privilege checks and exact cleanup receipts.
Before the fixture and seam exist, it must fail closed without provider access.

- [ ] **Step 2: Run the focused non-Docker RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  -q -m "not docker" -k "container_fixture or fixture_override"
```

Expected: the new fixture/override contracts fail because the tracked server, override and
lifecycle seam do not exist yet. This RED does not build an archive from a dirty worktree.

- [ ] **Step 3: Commit the RED test contracts so Docker can archive a clean HEAD**

```bash
git add tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_bounded_live_producer_container.py
git diff --cached --check
git commit -m "test(eval): define provider-free producer lifecycle"
test -z "$(git status --porcelain)"
```

- [ ] **Step 4: Run the archive-based Docker RED from that clean HEAD**

```bash
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest \
  tests/integration/test_bounded_live_producer_container.py -q -m docker
```

Expected: the Docker-marked test fails at the exact absent tracked fixture/override or lifecycle
seam before any Agent/provider execution. Capture the real failure and confirm any task-owned
Docker resources or temporary paths were cleaned.

- [ ] **Step 5: Implement the fixture, override and lifecycle seam**

From the real repository HEAD, prepare and build the exact tracked archive with a unique project,
engine-assigned loopback ports, isolated mode-0600 env and disabled provider endpoints. Start the
tracked fixture server through the checked-in override. The first real create must return
`idempotent_replay=false` and reach the deterministic scheduler through the production API/ledger.

Use the real proof transport and projection to require exact health, protected access, terminal
state, canonical artifact and Evidence. Restart backend, compare persistence, replay the same
request/key, inspect privileges and credential isolation, then require zero task-owned containers,
volumes, networks, temp paths and image tags.

The production live CLI must still have no fixture option or arbitrary override. The Docker test
may call explicit Python methods on `ManagedComposeProject` in this order:

```text
probe -> prepare archive -> build backend -> start fixture backend -> real create ->
observe -> restart -> compare -> real replay -> cleanup
```

Use one Docker-test lifecycle capped at 720 active seconds plus 120 cleanup seconds; it does not
alter the hard-coded live CLI budget. The four required lifecycles plus four 30-second daemon probes
have a 3,480-second worst-case bound inside the updated 75-minute job, leaving 1,020 seconds of
headroom. Inspect actual HostIp/HostPort values but publish none. Verify the backend container does
not receive a non-empty MySQL root password and receives no host credential outside the isolated
env file.

- [ ] **Step 6: Run the focused non-Docker GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  -q -m "not docker" -k "container_fixture or fixture_override"
```

Expected: the provider-free fixture/override contracts pass without starting Docker.

- [ ] **Step 7: Commit the exact Docker source snapshot before GREEN execution**

```bash
git add scripts/bounded_live_producer_container_fixture.py \
  scripts/bounded_live_producer_lifecycle.py \
  tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml \
  tests/unit/test_bounded_live_producer_lifecycle.py
git diff --cached --check
git commit -m "test(eval): prove provider-free producer lifecycle"
test -z "$(git status --porcelain)"
```

The Docker test archives `HEAD`; therefore all fixture, override and test inputs must already be
tracked in a clean commit. Do not treat a `source_dirty` failure as the feature RED.

- [ ] **Step 8: Run the archive-based Docker GREEN from clean HEAD**

```bash
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest \
  tests/integration/test_bounded_live_producer_container.py -q -m docker
```

After the run, inspect the exact project label inventory and task temp root. Expected: test passes
and all task-owned inventories are empty. Do not run `docker prune` or remove pre-existing images.

- [ ] **Step 9: Repair only real Docker failures through targeted TDD**

If Step 8 fails, use `superpowers:systematic-debugging` to identify the production or harness
boundary. Add the narrowest provider-free regression test, implement the repair, commit it, confirm
the worktree is clean again, and rerun Step 8. Do not hide archive cleanliness, lifecycle or
cleanup failures with retries or broader Docker deletion.

- [ ] **Step 10: Run the full new feature matrix**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py -q -m "not docker"

DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest \
  tests/integration/test_bounded_live_producer_container.py -q -m docker
```

- [ ] **Step 11: Record cleanup and source-integrity evidence**

Record the exact committed HEAD used by the archive, project name, bounded lifecycle result and
zero task-owned container/volume/network/temp/tag residue. Confirm the worktree remains clean.
These are local verification facts, not live-provider evidence and not release metadata.

---

## Task 6: Publish The Harness Contract And Required Gate

**Files:**

- Create: `docs/reference/bounded-live-producer-evaluation.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_release_metadata.py`
- Modify only if the current presentation suite owns the same discovery surface:
  `tests/unit/test_release_presentation_contracts.py`
- Modify: `tests/integration/test_bounded_live_producer_proof.py`
- Modify: `tests/integration/test_durable_review_container.py`
- Modify: `tests/unit/test_durable_review_container.py`
- Modify: `tests/unit/test_secure_local_container_contracts.py`

**Interfaces:**

- Produces: discoverable provider-free `check`, a documented but separately authorized live
  command, CI ordering, exact non-claims, and release-truth assertions.
- Consumes: the completed harness contract only. It creates no live evidence and no release
  metadata.

- [ ] **Step 1: Write RED documentation and CI contracts**

Require:

- the reference document exists and is indexed;
- README/README_CN describe the provider-free gate and state no live report is committed;
- evidence index distinguishes contract availability from absent live evidence;
- `CHANGELOG.md` adds the harness under `Unreleased` only;
- `VERSION` and all package versions remain `0.1.5`;
- `docs/releases/v0.1.5.md` and all historical sections remain byte-unchanged;
- CI runs `python scripts/bounded_live_producer_proof.py check` after dependency installation and
  before non-Docker pytest exactly once;
- required CI contains no `observe-live`, provider credential or evidence publication step;
- the existing Docker job remains the sole owner of `pytest -m docker`.
- the required Docker lifecycle count is four, the job timeout is 75 minutes, and the worst-case
  contract retains more than 15 minutes of headroom without rewriting the historical secure-runtime
  implementation plan.

- [ ] **Step 2: Run Task 6 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py -q
```

Expected: failures identify missing discovery/reference/CI entries while prior release assertions
remain green.

- [ ] **Step 3: Write the public reference**

Document exact `check` and `observe-live` syntax, external env-file permissions, process API key,
operator declarations, one-run/3,450-second boundary, source archive identity, accepted terminal
tuple, consumer `supported/accept_draft`, Evidence domain acceptance, estimate-only usage, restart,
replay, cleanup, fixed output paths, stable error taxonomy and rollback.

State clearly that implementation alone proves only deterministic contracts and a provider-free
Docker lifecycle. A later authorized run and reviewed evidence PR are required before any
provider-backed observation claim. Retain all producer-only, truth, business, exactly-once,
durability, billing, hosted and SLA non-claims.

- [ ] **Step 4: Update discovery and CI minimally**

Add one backend step:

```yaml
- name: Run bounded live producer contract check
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/bounded_live_producer_proof.py check
```

Do not create a new CI job or duplicate Docker execution. Update the current required-Docker budget
contracts from three to four lifecycles and the current job timeout from 60 to 75 minutes. Keep the
historical secure-runtime plan's recorded `3 / 60-minute` facts unchanged. Add concise links and an exact
`Unreleased` entry without changing current release metadata. The evidence index may link to the
reference but must not link to absent JSON/Markdown files as completed evidence.

- [ ] **Step 5: Run Task 6 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py -q

PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
```

- [ ] **Step 6: Commit Task 6**

```bash
git add .github/workflows/ci.yml CHANGELOG.md README.md README_CN.md \
  docs/README.md docs/evidence/README.md docs/architecture.md \
  docs/AGENT_INTEGRATION.md \
  docs/reference/bounded-live-producer-evaluation.md \
  tests/integration/test_bounded_live_producer_proof.py \
  tests/integration/test_durable_review_container.py \
  tests/unit/test_durable_review_container.py \
  tests/unit/test_secure_local_container_contracts.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
git diff --cached --check
git commit -m "docs(eval): publish bounded producer contract"
```

---

## Task 7: Complete Branch Verification And Clean Handoff

**Files:**

- Verify: every file changed by Tasks 1–6
- Do not create live evidence or release metadata

- [ ] **Step 1: Run deterministic feature gates twice**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check \
  > /tmp/dra-bounded-producer-check-1.json
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check \
  > /tmp/dra-bounded-producer-check-2.json
cmp /tmp/dra-bounded-producer-check-1.json \
  /tmp/dra-bounded-producer-check-2.json
```

Both runs must be byte-identical. Remove only these task-owned temporary files after comparison.

- [ ] **Step 2: Run all new non-Docker and required Docker tests**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_bounded_live_producer_contracts.py \
  tests/unit/test_bounded_live_producer_http.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_bounded_live_producer_proof.py -q -m "not docker"

DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest \
  tests/integration/test_bounded_live_producer_container.py -q -m docker
```

- [ ] **Step 3: Run existing proof and compatibility gates**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/check_canonical_identity.py --root .
PYTHON_DOTENV_DISABLED=1 python scripts/final_presentation_audit.py
```

- [ ] **Step 4: Run the repository test matrix**

Use the repository's locked Python 3.11 environment:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
```

Then run the unchanged frontend gate for CI parity:

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
```

Return to the repository root before the remaining audits.

- [ ] **Step 5: Audit scope, public safety and residue**

Confirm:

- `git diff --check origin/main..HEAD` is clean;
- no diff in `VERSION`, frontend manifests, dependencies, constraints, runtime API/DB/migrations,
  Tool Client, profiles, middleware, Compose product defaults or existing evidence baselines;
- no committed `bounded-live-producer-v1.json` or `.md` live evidence;
- no private paths/names, credentials, query duplication, raw content, local ports, Docker resource
  names, tracebacks, development markers or unsupported claims in added public files;
- the live CLI is never invoked by tests or CI;
- no task-owned Docker container, volume, network, temp root or image tag remains;
- every child worktree is clean and its commit is retained by the parent branch.

- [ ] **Step 6: Final implementation-plan self-check**

Map every design section to executable code/tests/docs. Search the final diff for unfinished
markers and type/name drift. Confirm report/error/manifest schemas, failure taxonomy, deadlines,
paths, domains, terminal tuple, consumer disposition and non-claims exactly match the approved
design.

- [ ] **Step 7: Stop at the clean local branch handoff**

The final report must include base/final HEAD, ordered commits, exact changed files, RED-to-GREEN
evidence, provider-free/Docker/full verification, Docker residue, worktree inventory, framework
reuse decision, remaining risk, and explicit confirmation that `observe-live`, provider access,
evidence publication, push, PR, merge, tag, release and deploy were not performed.

Do not start Change 2. The next gate is authoritative branch-diff review of the actual
implementation.

---

## Later Changes Outside This Plan

### Change 2 — Separately Authorized Live Evidence

After Change 1 merges, a new clean branch may execute exactly one `observe-live` command only with
authorization covering the merged commit, manifest, provider/model declaration, external
credential source, one-run intent, 3,450-second bound, estimate-only cost boundary and two absent
evidence paths. Successful sanitized JSON/Markdown plus index updates are evidence-only. Any
runtime/contract defect stops the attempt and becomes a separate design/fix.

### Change 3 — `v0.1.6` Release Preparation

Only after reviewed live evidence merges may a pure metadata branch evaluate `v0.1.6`. Release
notes must distinguish deterministic contracts, provider-free Docker lifecycle and one bounded
provider observation. Tag, GitHub Release, archive validation and runtime smoke remain separately
authorized.

### Real Agent Evaluation v2

Quality benchmarking across a frozen set of real or sanitized observations requires a separate
design. One producer report must not be promoted into a general model, research-quality or
downstream-product benchmark.
