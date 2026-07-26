# Strict Exact-Source Citation Profile v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan serially, task by task,
> in the current execution window. Do not dispatch subagents, create another
> branch/worktree, or run tasks in parallel. Every behavior task is
> RED-first and ends with a semantic atomic commit.

**Status:** Architecture-authority implementation plan pending AutoPlan
review and final product approval. This file does not authorize implementation
until those gates close.

**Goal:** Add the opt-in `generic-strict-citation@1` profile so a ready
canonical generic artifact contains at least one exact admitted URL from
current-run source Evidence, using a zero-call fast path or exactly one
bounded semantic placement invocation followed by application-owned
validation, insertion, recomputation, fencing, and persistence.

**Architecture:** Register one profile that reuses the immutable generic
DeepAgents graph and policy. Extend literal-`generic` observation and result
branches through one closed generic-family helper. Add a project-owned strict
citation finalizer that extracts bounded opaque targets and sources, invokes
the already configured LangChain chat model once, accepts only strict
ID-to-ID JSON, inserts exact persisted URLs itself, and reruns the existing
citation matcher. The existing application deadline, cancellation origin,
pre-invocation fence read, and terminal transaction remain authoritative.

**Tech Stack:** Python 3.11, `deepagents==0.6.11`,
`langchain==1.3.10`, `langchain-core==1.4.8`, `langgraph==1.2.6`,
`langgraph-checkpoint==4.1.1`, `pydantic==2.13.4`, SQLite application
persistence, pytest, and provider-free `BaseChatModel` fakes. No new
dependency, migration, provider-backed CI lane, hosted service, or frontend
change is permitted.

---

## Global Constraints

- Authority spec:
  `docs/superpowers/specs/2026-07-26-strict-exact-source-citation-profile-v1-design.md`.
- Keep the literal `generic` profile warning-only for zero exact citations.
  It must never call the strict correction path.
- Keep `talent-hiring-signal` graph, scope, review, publication, result, and
  Evidence behavior unchanged.
- Add only `profile_id=generic-strict-citation`, `profile_version=1`, and the
  documented proof identity `dra.strict-citation-profile.v1`. Do not add a
  request flag, database field, migration, status, artifact kind, public
  failure code, or field to `dra.downstream-consumer.v1`.
- Reuse the generic graph, tools, subagents, skills, budgets, VFS, execution
  service, Evidence admission, artifact kind, resolver, and terminal
  transaction. Do not create a second graph or enter DeepAgents for citation
  correction.
- A strict ready result must be a non-fallback
  `research_report_markdown` artifact with at least one current-outcome
  Evidence row marked `cited` by the existing exact-URL matcher after the
  final bytes are rendered. The result resolver must fail closed unless its
  one-transaction delivery snapshot contains a canonical artifact and at
  least one persisted cited source URL that still exactly matches the
  artifact bytes.
- If the initial canonical artifact already satisfies the invariant, make
  zero correction invocations. If it does not, make at most one direct
  application-level `chat_model.ainvoke(...)`. Do not use tools,
  `bind_tools`, `with_structured_output`, `with_retry`, a second application
  call, or a prompt-only retry.
- Calling the configured model wrapper once preserves its already configured
  provider boundary. Do not unwrap, replace, or add provider fallback logic
  inside strict finalization.
- The model may select only application-issued `target_id` and `source_id`
  values. It never supplies a trusted URL, Markdown, replacement report,
  score, terminal state, retry instruction, or citation result.
- The application owns exact URL bytes, placement validation, deterministic
  insertion order, artifact-size validation, citation recomputation, terminal
  state, Evidence persistence, and resolver behavior.
- Correction remains inside the existing tracked task. The task tracker's one
  shared deadline and `TerminationOrigin` own timeout/cancellation
  precedence. Let `asyncio.CancelledError` propagate unchanged.
- Read the current run/segment fence immediately before the model invocation.
  An already stale writer returns without invoking the model or mutating
  state. A writer that loses after that read remains a no-op at the existing
  fenced terminal transaction.
- Any ordinary strict-finalization exception must expose only a closed
  internal code to the surrounding task. Provider exception text, prompts,
  target text, Evidence snippets, raw model responses, host paths, and
  credentials must not enter public state or application diagnostics.
- Existing privacy-first LangSmith configuration remains an operator
  boundary; this feature neither depends on hosted tracing nor claims to
  disable an operator-configured trace. Required tests use no hosted tracing.
- Preserve `MAX_RESULT_BYTES=1 MiB`. Correction input is at most `512 KiB`;
  response is at most `64 KiB`; targets are at most `128`; sources are at
  most `100`; each exposed target/source context is at most `512` UTF-8
  bytes.
- Preserve all original artifact bytes except declared source-link
  insertions. Reject code fences, indented code, raw HTML, link definitions,
  and structural-only regions as placement targets. Plain prose paragraphs
  and simple list/blockquote prose lines may be targets. Apply insertions from
  the end of the report in canonical target order so offsets remain stable.
- A URL is eligible for Markdown insertion only when it passes the current
  public-HTTPS admission policy and round-trips as `cited` through the current
  `mark_cited_evidence` matcher when rendered by the canonical link rule.
  Do not relax or globally reinterpret source admission.
- A missing/fallback report, no admitted current-run source, no safe target,
  excessive packet, model error, malformed response, stale target, excessive
  corrected artifact, or zero cited rows after correction fails through
  existing `finalization/run_finalization_failed`, retains already frozen
  Evidence, and persists no ready artifact.
- `v0.1.6`, its tag/release notes/artifacts, `VERSION`, and the immutable
  `dra.downstream-consumer.v1` fixture remain unchanged. A separate future
  consumer may intentionally pin a new immutable producer tuple; this
  implementation does not modify any consumer.
- No credential read, provider call, network test, Docker execution,
  dependency installation, dependency update, `.github/workflows` change,
  push, PR, merge, tag, Release, deploy, or cleanup is authorized by this
  plan.

## Execution Environment And Framework Gate

Before the first RED, select one already-authorized exact Python 3.11
interpreter and keep its resolved absolute path for every Python command:

```bash
DRA_PYTHON_BIN="${DRA_PYTHON_BIN:-$PWD/.venv/bin/python}"
case "$DRA_PYTHON_BIN" in
  /*) ;;
  *) echo "DRA_PYTHON_3_11_AUTHORITY_REQUIRED"; exit 1 ;;
esac
test -x "$DRA_PYTHON_BIN" || {
  echo "DRA_PYTHON_3_11_AUTHORITY_REQUIRED"
  exit 1
}
test "$("$DRA_PYTHON_BIN" -c \
  'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = \
  "3.11" || {
  echo "DRA_PYTHON_3_11_AUTHORITY_REQUIRED"
  exit 1
}
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" - <<'PY'
from importlib.metadata import version

expected = {
    "deepagents": "0.6.11",
    "langchain": "1.3.10",
    "langchain-core": "1.4.8",
    "langgraph": "1.2.6",
    "langgraph-checkpoint": "4.1.1",
    "pydantic": "2.13.4",
    "pytest": "9.0.3",
    "pytest-asyncio": "1.4.0",
}
actual = {name: version(name) for name in expected}
if actual != expected:
    raise SystemExit(f"DRA_PINNED_ENVIRONMENT_REQUIRED:{actual!r}")
print("DRA_PINNED_ENVIRONMENT_OK")
PY
```

If this gate fails, stop and request environment authority. Do not use the
known non-authoritative Python 3.13 environment, install packages, access a
package registry, or change a pin to make the gate pass.

Then use `langchain-dev-guide` and current official LangChain documentation to
fresh-check the pinned `BaseChatModel.ainvoke` and `AIMessage` behavior. Verify
the installed source without invoking a model:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" - <<'PY'
from inspect import signature
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

print(signature(BaseChatModel.ainvoke))
print(AIMessage.__name__, HumanMessage.__name__, SystemMessage.__name__)
PY
```

Stop for architecture review if pinned source contradicts a single direct
`ainvoke(list[BaseMessage], config=...) -> AIMessage` call or requires a new
compatibility dependency.

At implementation start, derive the implementation-only base from the latest
commit touching this plan, which must be the final approved AutoPlan state:

```bash
PLAN_PATH='docs/superpowers/plans/2026-07-26-strict-exact-source-citation-profile-v1-implementation-plan.md'
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- "$PLAN_PATH")"
test -n "$IMPLEMENTATION_BASE"
test "$(git status --porcelain)" = ""
git show --stat --oneline "$IMPLEMENTATION_BASE" -- "$PLAN_PATH"
```

Use `"$IMPLEMENTATION_BASE"..HEAD` for the implementation-only allowlist.
Use `6a3020863fbaaf9d218420b7981150a5736b7fb8..HEAD` only for the full
approved spec + plan + implementation review.

---

## Exact Planned File Map

| Path | Action | Responsibility |
| --- | --- | --- |
| `agent/profile_registry.py` | Modify | Register the strict profile, proof-schema constant, and closed generic-family/strict helpers while reusing `GENERIC_POLICY`. |
| `agent/profile_agents.py` | Modify | Compile both generic-family profiles to the same generic graph and fail closed on a mismatched policy. |
| `agent/deepagents_harness.py` | Modify | Treat the strict profile as generic for release-owned Skill discovery; keep Talent special handling unchanged. |
| `agent/run_result.py` | Modify | Permit generic-family `network_search/internet_search` ToolMessages to create source Evidence. |
| `agent/research.py` | Modify | Expose one exact source-URL citation predicate reused by marking, strict rendering checks, and strict result resolution. |
| `api/research_execution_service.py` | Modify | Permit validated nested generic-family source streams to reach the existing Evidence extractor. |
| `api/run_result_service.py` | Modify | Share generic artifact selection while requiring canonical kind plus a still-matching persisted cited URL for strict resolution. |
| `api/run_repository.py` | Modify | Add one read-only exact run/segment/state fence predicate and include cited source URLs in the internal one-transaction delivery snapshot. |
| `api/strict_citation_finalization.py` | Create | Bounded targets/sources/packet, strict response parser, one-call adapter, deterministic renderer, recomputation, and closed internal errors. |
| `api/server.py` | Modify | Orchestrate generic-family artifact construction, strict zero/one-call finalization, pre-call fence check, and existing terminal failure/persistence paths. |
| `tests/unit/test_profile_registry.py` | Modify | Profile registration/version/schema, shared policy, generic-family helpers, compiler reuse, and fail-closed policy tests. |
| `tests/unit/test_deepagents_harness.py` | Modify | Strict profile Skill parity and Talent non-regression. |
| `tests/unit/test_agent_run_result.py` | Modify | Strict generic-family outer Evidence capture and Talent/non-source rejection. |
| `tests/unit/test_research_run.py` | Modify | Lock the public exact-URL predicate and unchanged `mark_cited_evidence` behavior. |
| `tests/integration/test_harness_execution.py` | Modify | Strict generic-family validated nested Evidence capture through `ResearchExecutionService`. |
| `tests/unit/test_run_result_service.py` | Modify | Strict canonical/cited resolver invariant plus generic fallback and Talent/unknown non-regression. |
| `tests/unit/test_run_repository.py` | Modify | Exact pre-invocation fence predicate and atomic cited-source delivery snapshot coverage. |
| `tests/unit/test_strict_citation_finalization.py` | Create | Exhaustive bounds, privacy exclusions, parser, renderer, one-call, zero-call, and post-recompute unit proof. |
| `tests/integration/test_strict_citation_profile.py` | Create | Provider-free create-to-resolve lifecycle, idempotency, success/failure, timeout/cancel, fence, and compatibility proof. |
| `tests/unit/test_documentation_contracts.py` | Modify | Lock profile opt-in, invariant, non-claims, state machine, consumer pinning, and Release separation. |
| `tests/unit/test_public_truth_documentation.py` | Modify | Lock public-neutral README/CHANGELOG truth and immutable v0.1.6 boundary. |
| `docs/reference/strict-citation-profile.md` | Create | Canonical operator/developer reference for profile identity, lifecycle, limits, failures, pinning, and non-claims. |
| `docs/README.md` | Modify | Index the strict citation reference. |
| `README.md` | Modify | Add concise English opt-in capability and boundary. |
| `README_CN.md` | Modify | Add equivalent concise Chinese opt-in capability and boundary. |
| `docs/reference/api-contract.md` | Modify | Document `profile_id`, profile manifest, ready semantics, and unchanged response/storage fields. |
| `docs/reference/state-machines.md` | Modify | Document zero-call/one-call/fail-closed finalization and timeout/cancel precedence. |
| `docs/decisions/framework-runtime-boundaries.md` | Modify | Record reuse of one direct LangChain call and rejection of graph/tool authority for correction. |
| `docs/architecture.md` | Modify | Place strict finalization between generic execution and fenced persistence without changing DB authority. |
| `docs/AGENT_INTEGRATION.md` | Modify | Document caller opt-in and immutable producer pinning without forcing upgrades. |
| `docs/reference/downstream-consumer-contract.md` | Modify | State that the frozen v1 fixture is unchanged and strict capability requires a separately pinned producer identity. |
| `CHANGELOG.md` | Modify | Record the capability under `Unreleased` and explicitly state no version/tag/Release claim. |

**Verify-only authority files:** `constraints.txt`, `.github/workflows/ci.yml`,
`VERSION`, `docs/releases/v0.1.6.md`,
`docs/evidence/downstream-consumer-contract-v1.json`,
`tests/integration/test_downstream_consumer_contract.py`, and existing Talent
tests. They must not change.

**Hard stop:** If implementation requires any other production, persistence,
migration, dependency, CI, release, frontend, profile-scope, status, artifact,
failure-taxonomy, or consumer file, preserve the RED evidence and return to
architecture authority instead of expanding this map.

---

## Locked Interfaces And Data Shapes

### Profile identity

`agent/profile_registry.py` will expose:

```python
STRICT_CITATION_PROFILE_ID = "generic-strict-citation"
STRICT_CITATION_PROFILE_VERSION = "1"
STRICT_CITATION_PROOF_SCHEMA = "dra.strict-citation-profile.v1"
GENERIC_FAMILY_PROFILE_IDS = frozenset(
    {"generic", STRICT_CITATION_PROFILE_ID}
)

def is_generic_family(profile_id: str) -> bool: ...
def is_strict_citation_profile(profile_id: str) -> bool: ...
```

`STRICT_CITATION_PROFILE` is a normal `ProfileSpec` with version `"1"`,
`harness_policy_id=GENERIC_POLICY.policy_id`, and every existing schema,
renderer, and canonicalization field equal to `GENERIC_PROFILE`. The proof
schema is a public identity constant and documented contract; it is not a new
`ProfileSpec`, manifest, run-status, artifact, or consumer-fixture field.

### Fence read

`api/run_repository.py` will expose:

```python
def run_finalization_fence_is_current(
    *,
    run_id: str,
    segment_id: str,
    expected_state_version: int,
    db_path: str | None = None,
) -> bool: ...
```

It performs one parameterized SQLite read joining `research_runs_v2` and
`run_segments`. It returns true only for the exact run and segment when:

```text
run.execution_status == running
run.state_version == expected_state_version
segment.status == running
segment.run_id == run_id
```

It does not acquire durable ownership, mutate state, refresh a lease, or
replace the terminal compare-and-swap. It only prevents an already stale
writer from spending the one semantic call.

The existing internal `get_run_delivery_snapshot()` additionally reads, in
the same SQLite snapshot, exact non-null `source_url` values from current-run
Evidence rows whose persisted `citation_status` is `cited`. It returns them
as an internal immutable `cited_source_urls` tuple ordered by
`created_at ASC, evidence_id ASC`. This is resolver input only; it is not added
to a REST response,
artifact, profile manifest, database schema, or downstream fixture.

### Strict finalization constants and records

`api/strict_citation_finalization.py` will define:

```python
MAX_TARGETS = 128
MAX_SOURCES = 100
MAX_CONTEXT_BYTES = 512
MAX_PACKET_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
CANONICAL_LINK_LABEL = "Source"

@dataclass(frozen=True)
class CitationTarget:
    target_id: str
    start: int
    end: int
    basis_sha256: str
    excerpt: str

@dataclass(frozen=True)
class CitationSource:
    source_id: str
    source_url: str
    snippet: str

@dataclass(frozen=True)
class CitationPlacement:
    target_id: str
    source_id: str

@dataclass(frozen=True)
class StrictCitationResult:
    artifact: dict[str, str]
    evidence_entries: list[EvidenceEntry]

class StrictCitationFinalizationError(RuntimeError):
    code: str
```

Closed internal error codes:

```text
strict_citation_initial_artifact_invalid
strict_citation_source_unavailable
strict_citation_target_unavailable
strict_citation_packet_invalid
strict_citation_model_failed
strict_citation_response_invalid
strict_citation_target_stale
strict_citation_artifact_invalid
strict_citation_invariant_failed
```

The exception constructor accepts only one of these codes and uses the code
as its complete exception string. No caught provider/parser exception is
chained into a public payload or copied into diagnostics.

The module entry point is:

```python
async def finalize_strict_citation(
    *,
    outcome: ExecutionOutcome,
    initial_artifact: Mapping[str, str],
    chat_model: BaseChatModel,
) -> StrictCitationResult: ...
```

It owns this exact sequence:

1. Require the strict profile and require `initial_artifact` to equal a fresh
   `build_generic_result_artifact(outcome)` result with canonical non-fallback
   kind; then use only current outcome Evidence and current exact-URL
   recomputation.
2. Return immediately with zero model calls if at least one row is already
   cited.
3. Build deterministic eligible targets and admitted, Markdown-round-tripping
   sources.
4. Serialize the canonical JSON packet and reject it before invocation if any
   count, ID, field, or byte limit fails.
5. Call `await chat_model.ainvoke(messages, config=config)` once.
6. Require one `AIMessage` with exact string content no larger than `64 KiB`.
7. Parse the response through the strict project-owned validator.
8. Apply placements in canonical target order, using reverse offsets for byte
   stability and the exact application-owned source URL.
9. Rebuild the artifact through `build_generic_result_artifact()` using
   `dataclasses.replace(outcome, report_candidate=ReportCandidate(...))`.
10. Require the rebuilt kind to remain canonical, rerun
    `mark_cited_evidence`, and require at least one cited row.

The call config is bounded metadata only:

```python
{
    "callbacks": [],
    "run_name": "strict-citation-finalization",
    "tags": ["dra:strict-citation-finalization"],
    "metadata": {
        "profile_id": "generic-strict-citation",
        "proof_schema": "dra.strict-citation-profile.v1",
    },
}
```

Do not claim that this overrides an operator-enabled global tracer. Required
tests set no tracing configuration and assert no hosted callback or service.

### Target extraction rule

Operate on the already sanitized canonical artifact string. Scan with
character offsets while preserving original line endings. A target is either
one contiguous non-empty paragraph of plain prose or one simple
unordered/ordered-list or blockquote prose line outside:

- fenced code opened by up to three spaces plus backticks or tildes;
- four-space or tab-indented code;
- raw HTML lines;
- Markdown link-definition lines;
- headings, thematic breaks, task-list controls, table delimiter/table-row
  lines, and structural-only marker lines; and
- any paragraph whose bounded excerpt matches the closed sensitive-marker
  guard described below.

The insertion offset is the end of the paragraph before its trailing newline.
IDs are `t001` through `t128` in report order. `basis_sha256` hashes the exact
full paragraph bytes. `excerpt` is a UTF-8-safe prefix of at most 512 bytes;
it never changes the report.

The sensitive-marker guard is deliberately a narrow packet-exclusion rule,
not a DLP claim. Case-insensitive obvious credential/diagnostic markers
(`authorization`, `bearer`, `api_key`, `api-key`, `password`, `secret`,
`cookie`, `traceback`, `exception`, `provider diagnostic`) and absolute host
path prefixes (`/Users/`, `/home/`, `/private/`, `/var/`, `/tmp/`,
or Windows drive roots matching `^[A-Za-z]:[\\/]`) make a report paragraph
ineligible. A source snippet with one of these markers becomes exactly
`[context omitted]`; it never copies the matched value.

### Source rule

`agent/research.py` will expose:

```python
def is_exact_source_url_cited(source_url: str, report_text: str) -> bool: ...
```

It preserves the current URL tokenization and trailing-punctuation
normalization. `mark_cited_evidence()` delegates to this predicate so there is
one exact citation authority.

Read only `outcome.evidence_entries`. Preserve first-seen deterministic order,
require `entry.thread_id == outcome.thread_id`, require exact string
`source_url`, re-run `is_publishable_source_url`, deduplicate by exact URL,
and cap after 100 eligible sources. IDs are `s001` through `s100`.
Pre-persistence `EvidenceEntry` has no `run_id` field; current-run authority
comes from using only the exact frozen `ExecutionOutcome` for the run that
will atomically associate those rows with `run_id` and `segment_id`.

Before admitting a source to the packet, render:

```text
[Source](EXACT_PERSISTED_URL)
```

and require
`is_exact_source_url_cited(entry.source_url, rendered) is True`. The public
pure predicate is the same implementation used by `mark_cited_evidence` and
the strict result resolver. This keeps insertion aligned to the live exact-URL
matcher without changing global admission. The packet includes the exact
admitted URL because the model must distinguish sources, but URL bytes used
for insertion are looked up again from the validated `source_id`; model
output never owns them.

### Packet and response shapes

The UTF-8 encoded input is canonical compact JSON with exact top-level keys:

```json
{
  "schema": "dra.strict-citation-profile.v1",
  "instruction": "Select semantically supported source placements using only issued IDs.",
  "targets": [
    {"target_id": "t001", "excerpt": "bounded untrusted report data"}
  ],
  "sources": [
    {
      "source_id": "s001",
      "source_url": "https://example.com/source",
      "snippet": "bounded untrusted source data"
    }
  ]
}
```

The system message states that all packet values are untrusted data and that
the response may contain only the required JSON. The human message wraps the
canonical packet between fixed `BEGIN_UNTRUSTED_PACKET` and
`END_UNTRUSTED_PACKET` delimiters. No query, run ID, thread ID, segment ID,
host path, provider diagnostic, exception, or unrelated Evidence field is
added as a separate value. Bounded report/source excerpts may naturally
contain words also present in the query; this contract makes no semantic DLP
claim.

The response must be exact JSON:

```json
{"placements":[{"target_id":"t001","source_id":"s001"}]}
```

Validation requires:

- top-level exact `dict` with keys exactly `{"placements"}`;
- exact `list` length `1..min(128, len(targets))`;
- every item exact `dict` with keys exactly
  `{"target_id", "source_id"}`;
- both IDs exact non-empty strings issued in this packet;
- unique target IDs and unique `(target_id, source_id)` pairs; and
- no coercion, explanation, URL, Markdown, score, null, boolean, number,
  nested field, or unknown key.

The same source may be selected for more than one distinct target. Response
order does not grant insertion order.

### Server orchestration

`api/server.py` binds the already configured singleton once as:

```python
strict_citation_chat_model = configured_chat_model
```

This is the only test seam for the correction model. Production does not
construct, unwrap, or choose another model.

In `_run_started_v2_with_persistence`:

```text
completed generic-family outcome
  -> build existing generic artifact
  -> literal generic: existing mark_cited_evidence and continue unchanged
  -> strict:
       recompute initial citation state
       canonical initial artifact and cited > 0 -> zero-call result
       otherwise read exact current fence
         false -> return as stale no-op
         true  -> await finalize_strict_citation once
  -> existing finalization checkpoint
  -> existing termination-origin override
  -> existing fenced finalize_run_transaction
```

The strict entry point returns the final artifact and recomputed Evidence. An
ordinary error is handled by the existing finalization-stage exception path,
which writes `failed/not_required/failed`,
`finalization/run_finalization_failed`, retained outcome Evidence, and no
artifact. Cancellation is not translated and remains owned by the existing
timeout/cancel path.

---

## Task 1: Register The Strict Profile And Reuse The Generic Graph

**Files:**

- Modify: `agent/profile_registry.py`
- Modify: `agent/profile_agents.py`
- Modify: `agent/deepagents_harness.py`
- Modify: `tests/unit/test_profile_registry.py`
- Modify: `tests/unit/test_deepagents_harness.py`

- [ ] **Step 1: Write profile identity and family RED tests**

Add tests that assert:

```python
strict = profile_registry.get("generic-strict-citation")
generic = profile_registry.get("generic")

assert strict.version == "1"
assert strict.harness_policy_id == generic.harness_policy_id
assert profile_registry.policy_for(strict.profile_id) is GENERIC_POLICY
assert STRICT_CITATION_PROOF_SCHEMA == "dra.strict-citation-profile.v1"
assert is_generic_family("generic")
assert is_generic_family("generic-strict-citation")
assert not is_generic_family("talent-hiring-signal")
assert is_strict_citation_profile("generic-strict-citation")
assert not is_strict_citation_profile("generic")
assert profile_registry.manifest(strict.profile_id)["profile"]["profile_id"] == (
    "generic-strict-citation"
)
assert "proof_schema" not in profile_registry.manifest(strict.profile_id)["profile"]
```

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_profile_registry.py \
  tests/unit/test_deepagents_harness.py::test_generic_skills_are_real_and_talent_has_none
```

Expected RED: unknown strict profile and missing helper/constants.

- [ ] **Step 2: Implement the smallest registry/family change**

Create `STRICT_CITATION_PROFILE` by copying every current generic
`ProfileSpec` value except `profile_id`. Register it beside generic and Talent
with the same immutable `GENERIC_POLICY`. Add only the constants and exact
membership helpers listed above.

- [ ] **Step 3: Write compiler and Skill-routing RED tests**

Assert `compile_profile_agent()` returns the exact supplied generic graph for
both generic-family profiles, rejects a generic-family profile paired with
Talent policy, and still creates the Talent researcher. Assert:

```python
assert load_skill_names("generic-strict-citation") == load_skill_names("generic")
assert load_skill_names("talent-hiring-signal") == set()
```

Expected RED: strict compiler/Skill discovery fails closed as unknown.

- [ ] **Step 4: Route only the generic family**

Use `is_generic_family()` in `compile_profile_agent()` and
`load_skill_names()`. Require `GENERIC_POLICY.policy_id` before returning the
shared graph. Do not change `agent/main_agent.py`,
`build_generic_harness()`, middleware assembly, tools, subagents, budgets, or
Talent special handling.

- [ ] **Step 5: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_profile_registry.py \
  tests/unit/test_deepagents_harness.py
git diff --check
git status --short
git add agent/profile_registry.py agent/profile_agents.py \
  agent/deepagents_harness.py tests/unit/test_profile_registry.py \
  tests/unit/test_deepagents_harness.py
git commit -m "feat: register strict citation profile"
```

---

## Task 2: Extend Generic-Family Evidence And Result Plumbing

**Files:**

- Modify: `agent/run_result.py`
- Modify: `agent/research.py`
- Modify: `api/research_execution_service.py`
- Modify: `api/run_result_service.py`
- Modify: `tests/unit/test_agent_run_result.py`
- Modify: `tests/unit/test_research_run.py`
- Modify: `tests/integration/test_harness_execution.py`
- Modify: `tests/unit/test_run_result_service.py`

- [ ] **Step 1: Write outer and nested Evidence RED tests**

Duplicate the existing generic positive cases with
`profile_id="generic-strict-citation"` and assert the same single
`EvidenceEntry` is produced only for the exact
`network_search/internet_search` pair. Add negative controls for database,
knowledge-base, outer `task`, invalid namespace, and Talent streams.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_run_result.py -k 'evidence and strict' \
  tests/integration/test_harness_execution.py -k 'nested and strict'
```

Expected RED: strict profile is filtered by literal-`generic` checks.

- [ ] **Step 2: Replace only the two literal family checks**

Use `is_generic_family()` in:

- `agent.run_result.process_stream_chunk`; and
- `api.research_execution_service.AccumulatorExecutionObserver.on_nested_stream_chunk`.

Do not alter namespace validation, role/tool allowlists, Evidence extraction,
deduplication, limits, timestamps, or Talent packet behavior.

- [ ] **Step 3: Write result resolver RED tests**

First expose and test `is_exact_source_url_cited()` against the existing
positive, URL-prefix-only, trailing-punctuation, and unmatched cases. Assert
`mark_cited_evidence()` produces unchanged results through the shared
predicate.

Then persist or construct strict-profile ready snapshots and assert:

- canonical artifact plus a persisted `cited` source URL that exactly appears
  in content resolves;
- fallback artifact fails closed;
- canonical artifact with zero persisted cited source URLs fails closed;
- canonical artifact whose persisted cited URL no longer exactly appears in
  content fails closed;
- literal generic still resolves its existing canonical and fallback kinds;
  and
- Talent remains on the Talent resolver while unknown profile fails closed.

Expected RED: strict profile falls through `_select_artifact_id()` or
`_valid_artifact()`, and no shared public exact-URL predicate exists.

- [ ] **Step 4: Extend only generic-family selection/validation**

Make `_select_artifact_id()` choose `research-report.md` for the generic
family. Keep `_valid_generic_artifact()` unchanged for literal generic. Add a
strict branch that requires:

1. the existing generic artifact hash/media/safety checks;
2. `kind == "research_report_markdown"`; and
3. at least one `cited_source_url` from the repository delivery snapshot for
   which `is_publishable_source_url(url)` and
   `is_exact_source_url_cited(url, content)` are both true.

The delivery snapshot extension is implemented in Task 5 so the focused
resolver tests may monkeypatch the snapshot shape here. Do not change artifact
IDs, kinds, size bounds, hashing, sanitization, literal-generic fallback
semantics, Talent selection, or public error payloads.

- [ ] **Step 5: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_research_run.py \
  tests/integration/test_harness_execution.py \
  tests/unit/test_run_result_service.py
git diff --check
git add agent/run_result.py agent/research.py api/research_execution_service.py \
  api/run_result_service.py tests/unit/test_agent_run_result.py \
  tests/unit/test_research_run.py \
  tests/integration/test_harness_execution.py \
  tests/unit/test_run_result_service.py
git commit -m "feat: route strict profile through generic evidence"
```

---

## Task 3: Build Bounded Targets, Sources, And Correction Packet

**Files:**

- Create: `api/strict_citation_finalization.py`
- Create: `tests/unit/test_strict_citation_finalization.py`

- [ ] **Step 1: Write target extraction RED tests**

Cover:

- deterministic `t001..t128` order and exact character offsets;
- UTF-8-safe 512-byte excerpts;
- exclusion of fenced/indented code, raw HTML, link definitions, headings,
  thematic breaks, task-list controls, and tables;
- safe extraction of simple unordered/ordered-list and blockquote prose lines;
- existing inline link destinations remain byte-identical;
- sensitive-marker paragraphs are omitted rather than copied; and
- no eligible prose returns the closed target-unavailable error.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_strict_citation_finalization.py -k 'target'
```

Expected RED: module is absent.

- [ ] **Step 2: Implement pure deterministic target extraction**

Add the constants/dataclasses, UTF-8 prefix helper, line-state scanner, exact
paragraph hash, closed sensitive-marker guard, and target cap. Do not parse
Markdown with a new dependency and do not mutate the report.

- [ ] **Step 3: Write source and packet RED tests**

Use real `EvidenceEntry` rows to prove:

- only current-outcome/current-thread admitted public HTTPS URLs enter;
- exact duplicate URLs collapse first-seen;
- query/fragment/private-host/overlong/unpublishable URLs are rejected by the
  existing policy;
- a URL that cannot round-trip through canonical Markdown plus
  `mark_cited_evidence` is rejected;
- IDs are deterministic and capped at 100;
- snippets are UTF-8 bounded to 512 bytes;
- obvious credential/provider/path markers produce `[context omitted]`;
- packet keys and ID uniqueness are exact;
- target/source counts and serialized packet remain within declared bounds;
- packet contains no separately injected query, run/thread/segment ID,
  exception, unrelated Evidence body, or host path; and
- no eligible source fails before any model invocation.

- [ ] **Step 4: Implement source projection and canonical packet encoding**

Use `is_publishable_source_url()` and the live citation matcher. Serialize
with:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

Check the encoded byte length before constructing messages. Keep snippets and
target excerpts visibly delimited as untrusted data.

- [ ] **Step 5: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_strict_citation_finalization.py -k 'target or source or packet'
git diff --check
git add api/strict_citation_finalization.py \
  tests/unit/test_strict_citation_finalization.py
git commit -m "feat: build bounded citation correction packet"
```

---

## Task 4: Add Strict Response Validation, Rendering, And One Direct Call

**Files:**

- Modify: `api/strict_citation_finalization.py`
- Modify: `tests/unit/test_strict_citation_finalization.py`

- [ ] **Step 1: Write strict parser RED tests**

Accept the one exact valid shape. Reject:

- empty or non-string content;
- over-64-KiB UTF-8 response;
- malformed JSON;
- top-level list/null/scalar;
- missing or extra top-level keys;
- empty or excessive placements;
- non-dict placement;
- missing/extra placement keys;
- non-string, empty, unknown target/source IDs;
- duplicate target IDs and duplicate pairs; and
- URLs, Markdown, explanations, scores, or nested unknown fields.

Expected RED: parser is absent.

- [ ] **Step 2: Implement the exact parser**

Use stdlib JSON and exact built-in type checks. Never coerce provider output.
Every invalid shape raises only
`StrictCitationFinalizationError("strict_citation_response_invalid")`.

- [ ] **Step 3: Write renderer RED tests**

Assert:

- response order cannot change canonical target-order insertion;
- links use exact source URL bytes from the source map, never response text;
- the canonical suffix is exactly ` [Source](EXACT_URL)`;
- all non-insertion bytes in the canonical initial artifact remain identical;
- repeated source IDs on distinct targets are allowed;
- stale paragraph bytes/hash fail closed;
- unknown IDs cannot reach rendering;
- corrected content over 1 MiB fails closed; and
- rebuilding produces the existing canonical artifact kind/hash.

- [ ] **Step 4: Implement reverse-offset deterministic rendering**

Sort placements by their target's canonical index, validate every target slice
and hash against the original report, then apply replacements from the
greatest `start` offset to the smallest. Rebuild through the existing generic
artifact builder. Do not call private artifact helpers or append a source
list.

- [ ] **Step 5: Write one-call/zero-call RED tests**

Create a provider-free `BaseChatModel` fake with declared scripted responses,
`call_count`, captured messages, and captured config. Prove:

- initially cited canonical artifact returns with `call_count == 0`;
- an initial artifact not value-equal to
  `build_generic_result_artifact(outcome)` fails with `call_count == 0`;
- eligible zero-citation artifact succeeds with `call_count == 1`;
- no source/target/fallback fails with `call_count == 0`;
- provider exception is replaced by the stable model-failed code with
  `call_count == 1` and no exception text;
- malformed response makes exactly one call;
- a defensive post-render recomputation forced to remain uncited makes exactly
  one call and raises invariant-failed;
- no path performs a second application invocation;
- only `SystemMessage` and `HumanMessage` are sent;
- the human payload is bounded and delimited; and
- config contains only the locked callbacks/run-name/tags/metadata values.

- [ ] **Step 6: Implement `finalize_strict_citation()`**

Call `chat_model.ainvoke(...)` exactly once in the eligible branch. Re-raise
`asyncio.CancelledError`; map every other invocation exception to
`strict_citation_model_failed` without including or chaining provider text.
Require `AIMessage` with exact string content. After rendering, rebuild,
recompute citations, and require at least one cited row.

- [ ] **Step 7: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_strict_citation_finalization.py
git diff --check
git add api/strict_citation_finalization.py \
  tests/unit/test_strict_citation_finalization.py
git commit -m "feat: finalize strict citations with one bounded call"
```

---

## Task 5: Add Fence Predicate And Production Finalization Orchestration

**Files:**

- Modify: `api/run_repository.py`
- Modify: `api/server.py`
- Modify: `tests/unit/test_run_repository.py`
- Create: `tests/integration/test_strict_citation_profile.py`

- [ ] **Step 1: Write exact fence-predicate RED tests**

Create and start a real dispatch, then assert the predicate is true only for
the exact running run, initial segment, and state version `1`. Assert false
for wrong run, wrong segment, wrong version, pending, completed, failed, and a
stale writer after a competing terminal transition.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_run_repository.py \
    -k 'finalization_fence_is_current or delivery_snapshot_cited_source'
```

Expected RED: predicate is absent.

- [ ] **Step 2: Write delivery-snapshot citation RED tests**

Finalize strict-shaped runs with zero, one, duplicate, cited, and uncited
Evidence rows. Assert `get_run_delivery_snapshot()` returns an immutable
deterministically ordered tuple containing only exact non-null source URLs
from rows persisted as `cited`, while keeping all existing snapshot fields
unchanged.

- [ ] **Step 3: Implement the read-only predicate and snapshot extension**

Use one parameterized query and exact persisted values. Do not call
`get_run()`, mutate a lease/status, or hold a SQLite transaction across the
model call. Read cited source URLs inside the existing delivery snapshot
transaction; do not expose Evidence bodies or add public fields.

- [ ] **Step 4: Build the provider-free production-path fixture**

In `tests/integration/test_strict_citation_profile.py`, add:

- a `ScriptedGenericHarness` that emits a validated nested
  `network_search/internet_search` ToolMessage and a canonical report through
  the real `AccumulatorExecutionObserver`;
- a `ResearchExecutionService` adapter assigned only at the existing
  `server.run_deep_agent` boundary;
- a scripted `BaseChatModel` fake assigned only to the new server correction
  model boundary;
- real `create_run`/`create_or_replay_run`, dispatch claim/start,
  `_run_dispatched_with_persistence`, `create_tracked_task`,
  `finalize_run_transaction`, `get_run`, and `resolve_run_result`; and
- a helper returning the persisted status, resolved result or expected
  `RunResultUnavailable`, model call count, and dispatch state.

No test may patch the repository terminal transaction, result resolver,
Evidence persistence, citation matcher, task tracker, or status projection in
the positive lifecycle cases.

- [ ] **Step 5: Write initial-success and correction-success RED tests**

Prove through the real lifecycle:

1. strict initial report already contains the exact admitted URL:
   `completed/not_required/ready`, canonical artifact, cited Evidence, zero
   correction calls;
2. strict initial report has zero URL, one valid placement response:
   exactly one call, exact persisted admitted URL bytes in the resolved
   canonical artifact, cited Evidence, correct content hash, and ready status.

Expected RED: strict profile either behaves like warning-only generic or is
unsupported by server finalization.

- [ ] **Step 6: Implement server orchestration**

Import the generic-family/strict helpers, configured chat-model singleton,
fence predicate, and strict finalizer. Build generic artifacts for both
generic-family profiles. Keep literal generic's existing citation
recomputation unchanged. For strict:

1. recompute initial citation state in the server and use the initial
   canonical artifact directly when at least one row is cited;
2. if correction is needed, read the fence in `asyncio.to_thread`;
3. return immediately when the predicate is false;
4. otherwise await the strict finalizer once; and
5. pass only its artifact/Evidence to the existing checkpoint and terminal
   transaction.

Do not add a new exception response, status, database write, retry, or logging
of caught content.

- [ ] **Step 7: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_run_repository.py \
    -k 'finalization_fence_is_current or delivery_snapshot_cited_source' \
  tests/integration/test_strict_citation_profile.py \
    -k 'initial_success or correction_success'
git diff --check
git add api/run_repository.py api/server.py \
  tests/unit/test_run_repository.py \
  tests/integration/test_strict_citation_profile.py
git commit -m "feat: enforce strict citation finalization"
```

---

## Task 6: Prove Fail-Closed Lifecycle, Deadline, Cancellation, And Compatibility

**Files:**

- Modify: `tests/integration/test_strict_citation_profile.py`

- [ ] **Step 1: Add strict finalization failure cases**

Through the same production fixture, prove:

- malformed JSON and unknown ID each make exactly one call;
- a focused negative-control monkeypatch that forces only the
  post-insertion recomputation to remain uncited makes one call and no second;
- no admitted source makes zero calls;
- fallback report makes zero calls;
- no eligible target makes zero calls;
- model exception makes one call while provider text is absent from status,
  failure cause, Evidence, artifacts, and exception string;
- every ordinary strict failure ends
  `failed/not_required/failed` with
  `finalization/run_finalization_failed`;
- current-run Evidence survives when it existed;
- no ready or partial corrected artifact is persisted; and
- `resolve_run_result` returns the existing `run_failed` unavailable result.

- [ ] **Step 2: Add timeout and explicit cancellation cases**

Use a blocking fake model that signals entry into `ainvoke`.

For timeout, run the real `create_tracked_task` with a bounded short deadline,
wait for the entry signal, and let the tracker win. Assert:

```text
failed / not_required / failed
failure_cause = finalization/run_timeout
Evidence retained
no artifact
model call count = 1
```

For cancellation, cancel the tracked task after the entry signal and assert
the same state with `finalization/cancelled`. Do not use blocking sleeps or
patch the classification.

- [ ] **Step 3: Add stale-fence cases**

Prove:

- a writer already stale before the fence read returns without invoking the
  model or overwriting the winner; and
- a writer made stale while its one model call is in flight loses at the
  existing terminal transaction and cannot overwrite the winner.

The second case may spend its already-started call; neither case creates an
additional call, artifact, Evidence mutation, or terminal rewrite.

- [ ] **Step 4: Add API identity and idempotency cases**

Use the existing profile registry and run-creation interfaces to prove:

- `profile_id=generic-strict-citation` persists version `"1"`;
- the profile manifest resolves through the existing endpoint shape;
- same key + same strict request replays the same run;
- same key + `generic` versus strict conflicts because `profile_id` is already
  in the existing idempotency fingerprint;
- unknown profile remains fail closed, while the registered profile version
  remains server-owned and is persisted as `"1"`; and
- no request/response/storage field was added.

- [ ] **Step 5: Add generic/Talent/consumer non-regression**

Prove literal generic with Evidence but zero exact URL still becomes ready,
retains uncited Evidence, and makes zero correction calls. Run existing Talent
and immutable consumer-contract tests without changing their fixtures.

- [ ] **Step 6: Run the complete behavior slice and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_profile_registry.py \
  tests/unit/test_deepagents_harness.py \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_research_run.py \
  tests/unit/test_research_execution_service.py \
  tests/unit/test_run_result_service.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_strict_citation_finalization.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_strict_citation_profile.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_downstream_consumer_contract.py
git diff --check
git add tests/integration/test_strict_citation_profile.py
git commit -m "test: prove strict citation lifecycle"
```

---

## Task 7: Document Opt-In Semantics, Pinning, Non-Claims, And Release Boundary

**Files:**

- Create: `docs/reference/strict-citation-profile.md`
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/reference/state-machines.md`
- Modify: `docs/decisions/framework-runtime-boundaries.md`
- Modify: `docs/architecture.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/reference/downstream-consumer-contract.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_public_truth_documentation.py`

- [ ] **Step 1: Write documentation contract RED tests**

Lock these exact public truths:

- opt in with existing `profile_id="generic-strict-citation"`;
- profile version `1` and proof schema
  `dra.strict-citation-profile.v1`;
- ready proves at least one exact current-run admitted URL in a canonical
  non-fallback artifact after application recomputation;
- zero-call initial success and at most one direct semantic placement call;
- application-owned URLs/insertion/recomputation/terminal state;
- generic zero-citation behavior and Talent behavior remain unchanged;
- strict failure reuses `finalization/run_finalization_failed`, retains
  Evidence, and exposes no artifact;
- no new request/response/DB/status/artifact/failure field;
- a consumer upgrades only by intentionally pinning
  `repository + release/tag-or-commit + profile_id + profile_version +
  proof_schema`;
- a DRA version change does not automatically force a consumer upgrade;
- `dra.downstream-consumer.v1` and its v0.1.6 fixture are unchanged;
- Release is a separate decision and this change does not claim v0.1.6
  publication; and
- no claim of correctness, completeness, entailment, source quality,
  production provider reliability, hosted observability, business impact, or
  downstream adoption.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
```

Expected RED: the reference and public wording are absent.

- [ ] **Step 2: Write the canonical reference and targeted cross-links**

Create one concise complete reference and update only the affected sections of
existing docs. Keep wording public-neutral. Do not name a private consumer,
workspace, machine, credential, governance label, career goal, or unverified
live-provider result.

Add the capability to `CHANGELOG.md` under `Unreleased`; do not edit
`VERSION`, a release note, tag, artifact, or release claim.

- [ ] **Step 3: Verify docs and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
git diff --check
git add docs/reference/strict-citation-profile.md docs/README.md README.md \
  README_CN.md docs/reference/api-contract.md \
  docs/reference/state-machines.md \
  docs/decisions/framework-runtime-boundaries.md docs/architecture.md \
  docs/AGENT_INTEGRATION.md \
  docs/reference/downstream-consumer-contract.md CHANGELOG.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
git commit -m "docs: explain strict citation profile"
```

---

## Task 8: Full Verification, Public Boundary Audit, And Review Handoff

**Files:** Verify only. No new implementation scope.

- [ ] **Step 1: Check implementation-only allowlist**

```bash
git diff --name-only "$IMPLEMENTATION_BASE"..HEAD | sort
git diff --stat "$IMPLEMENTATION_BASE"..HEAD
git diff --check "$IMPLEMENTATION_BASE"..HEAD
```

Compare the output exactly with the planned implementation/test/docs file map.
The spec and plan are outside `"$IMPLEMENTATION_BASE"..HEAD`.

- [ ] **Step 2: Scan public files for forbidden private/sensitive content**

Use fixed-string searches for the private coordination labels supplied out of
band, local absolute paths, credential-like values, raw prompts/responses, and
private consumer names. Do not write the private marker values into this plan,
test fixtures, source, commit messages, PR body, or retained command output.

Also run:

```bash
rg -n \
  '(LANGSMITH_API_KEY=|Authorization: Bearer|api[_-]?key[=:]|/Users/|/home/|/private/var/)' \
  agent api tests docs README.md README_CN.md CHANGELOG.md \
  --glob '!docs/superpowers/plans/*.md' \
  --glob '!docs/superpowers/specs/*.md'
```

Review every match; existing documentation examples are not automatically a
finding, but new task-owned secrets/paths are a hard failure.

- [ ] **Step 3: Run focused and full backend verification**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_profile_registry.py \
  tests/unit/test_deepagents_harness.py \
  tests/unit/test_agent_run_result.py \
  tests/unit/test_research_run.py \
  tests/unit/test_research_execution_service.py \
  tests/unit/test_run_result_service.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_strict_citation_finalization.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_strict_citation_profile.py \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_downstream_consumer_contract.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py

PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q -m "not docker"
```

No provider, credential, network, Docker, or hosted trace is used.

- [ ] **Step 4: Verify immutable release/consumer files**

```bash
git diff --exit-code "$IMPLEMENTATION_BASE"..HEAD -- \
  VERSION \
  docs/releases/v0.1.6.md \
  docs/evidence/downstream-consumer-contract-v1.json \
  tests/integration/test_downstream_consumer_contract.py \
  constraints.txt \
  .github/workflows/ci.yml
```

The command must produce no diff. Re-run the existing consumer test from Step
3 as verification only.

- [ ] **Step 5: Run completion verification and self-review**

Use `superpowers:verification-before-completion`, then inspect:

```bash
git log --oneline "$IMPLEMENTATION_BASE"..HEAD
git status --short --branch
git diff --check "$IMPLEMENTATION_BASE"..HEAD
```

Confirm:

- every behavior task has recorded RED evidence before its production change;
- zero-call and exactly-one-call counts come from provider-free fakes;
- timeout/cancel/fence tests traverse the production tracker/repository path;
- no test relaxes the generic or consumer contract;
- no raw packet/model/provider content reaches persistence or public docs;
- all required files are committed and the worktree is clean; and
- no push, PR, merge, tag, Release, deploy, or cleanup occurred.

- [ ] **Step 6: Return for authority review**

Return one `READY` report containing:

- worktree, branch, final HEAD, and implementation base;
- exact changed-file list and semantic commits;
- representative RED failures and final GREEN commands/results;
- generic/Talent/v0.1.6/consumer non-regression evidence;
- documentation impact;
- residual risks, including that provider-free proof does not prove live
  provider quality or semantic entailment; and
- explicit confirmation that no remote/release/downstream action occurred.

Do not push or open a PR. The architecture authority performs the pre-PR
GStack review and returns any findings to this execution window.

---

## Stop Conditions

Stop and return to architecture authority without expanding scope if:

- the exact Python 3.11 pinned environment is unavailable without an
  unauthorized install;
- pinned LangChain behavior contradicts the locked direct-call contract;
- profile registration requires a request field, migration, public status,
  artifact kind, failure code, or downstream contract-field change;
- the strict profile cannot reuse the exact generic graph/policy/budgets;
- correction cannot share the existing task deadline, cancellation origin, or
  fenced terminal transaction;
- an already stale writer cannot be detected before invocation or a losing
  writer can overwrite the terminal winner;
- exact URL insertion cannot round-trip through current source admission and
  citation recomputation without weakening either;
- safe target/source projection cannot retain at least one target and source
  inside the declared bounds;
- strict failure cannot retain Evidence while exposing no ready artifact;
- provider-free tests cannot traverse create, dispatch, execution service,
  Evidence, correction, persistence, status, and resolver;
- generic, Talent, v0.1.6, or immutable consumer proofs require
  reinterpretation; or
- any provider, credential, network, Docker, dependency, CI, release, or
  downstream mutation becomes necessary.

Do not work around a stop condition with a second call, deterministic source
appendix, consumer gate relaxation, generic contract change, hidden field,
unbounded prompt/response, new dependency, or unapproved environment change.
