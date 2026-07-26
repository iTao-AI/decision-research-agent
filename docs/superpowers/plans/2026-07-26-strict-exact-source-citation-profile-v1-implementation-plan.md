# Strict Exact-Source Citation Profile v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan serially, task by task,
> in the current execution window. Do not dispatch subagents, create another
> branch/worktree, or run tasks in parallel. Every behavior task is
> RED-first and ends with a semantic atomic commit.

**Status:** Approved for implementation after AutoPlan review. Creation of one
task-local `.venv` and installation of the repository's existing exact pins
are authorized. No behavior implementation may begin until the closed
environment gate below passes.

**Goal:** Add the opt-in `generic-strict-citation@1` profile so a ready
canonical generic artifact contains at least one exact admitted URL from
current-run source Evidence, using a zero-call fast path or exactly one
application-level bounded semantic placement invocation followed by
application-owned validation, insertion, recomputation, fencing, and
persistence.

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
- The generic graph's existing `ModelCallLimitMiddleware`,
  `ToolCallLimitMiddleware`, and `TokenTrackingMiddleware` remain unchanged.
  The application-owned strict correction happens after that graph returns
  and has its own zero/one-`ainvoke` bound; do not claim that the correction
  call is counted by generic-harness budget or token telemetry.
- A strict ready result must be a non-fallback
  `research_report_markdown` artifact with at least one current-outcome
  Evidence row marked `cited` by the existing exact-URL matcher after the
  final bytes are rendered. The result resolver must fail closed unless its
  one-transaction delivery snapshot contains exact producer identity
  `generic-strict-citation@1`, a canonical artifact, and at least one
  persisted cited source URL that still exactly matches the artifact bytes.
- If the initial canonical artifact already satisfies the invariant, make
  zero correction invocations. If it does not, make at most one direct
  application-level `chat_model.ainvoke(...)`. Do not use tools,
  `bind_tools`, `with_structured_output`, `with_retry`, a second application
  call, or a prompt-only retry.
- Calling the configured model wrapper once preserves its already configured
  provider boundary. Do not unwrap, replace, or add provider fallback logic
  inside strict finalization.
- The one-call invariant counts application-level `ainvoke` entries. The
  already configured wrapper may retain its existing transport retry and
  provider-fallback behavior. This feature must not add either behavior or
  claim that one application invocation equals one provider HTTP request.
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
- Reuse the existing task tracker's exception-string log as the bounded
  operator diagnostic: it may contain exactly one closed
  `strict_citation_*` code and no caught exception text or payload. Do not add
  a public failure field, raw traceback logger, packet logger, or new
  telemetry schema.
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
- One task-local `.venv` creation and one installation of the unchanged exact
  versions in `constraints.txt` are authorized solely for this implementation
  and its provider-free tests. Do not add, update, relax, or resolve any
  dependency outside those existing pins.
- No credential read, provider call, network test, Docker execution,
  `.github/workflows` change, push, PR, merge, tag, Release, deploy, or cleanup
  is authorized by this plan.

## Execution Environment And Framework Gate

Before the first RED, use one authority-supplied absolute Python 3.11 bootstrap
interpreter. If the task-local `.venv` does not yet exist, create it and
install only the unchanged exact constraints:

```bash
case "${DRA_BOOTSTRAP_PYTHON:-}" in
  /*) ;;
  *) echo "DRA_BOOTSTRAP_PYTHON_REQUIRED"; exit 1 ;;
esac
test -x "$DRA_BOOTSTRAP_PYTHON"
test "$("$DRA_BOOTSTRAP_PYTHON" -c \
  'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = \
  "3.11"
test ! -e .venv || test -x .venv/bin/python
if test ! -x .venv/bin/python; then
  "$DRA_BOOTSTRAP_PYTHON" -m venv .venv
  "$PWD/.venv/bin/python" -m pip install --no-deps -r constraints.txt
fi
```

Do not reuse a partial or foreign `.venv`. If `.venv` exists without an
executable interpreter or the exact-pin gate below fails after installation,
stop and return `DRA_PINNED_ENVIRONMENT_REQUIRED`; do not repair it by adding
packages or changing pins.

Then keep the resolved task-local interpreter path for every Python command:

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
from importlib.metadata import PackageNotFoundError, version

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
try:
    actual = {name: version(name) for name in expected}
except PackageNotFoundError:
    raise SystemExit("DRA_PINNED_ENVIRONMENT_REQUIRED") from None
if actual != expected:
    raise SystemExit("DRA_PINNED_ENVIRONMENT_REQUIRED")
print("DRA_PINNED_ENVIRONMENT_OK")
PY
```

If this gate fails after the authorized bootstrap, stop and report the closed
code. Do not use the known non-authoritative Python 3.13 environment, install
additional packages, or change a pin to make the gate pass.
Both a missing distribution and a version mismatch must exit with only
`DRA_PINNED_ENVIRONMENT_REQUIRED`; an uncaught package exception is not an
accepted gate result.

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
| `api/run_result_service.py` | Modify | Share generic artifact selection while requiring exact strict profile version, canonical kind, and a still-matching persisted cited URL for strict resolution. |
| `api/run_repository.py` | Modify | Add one read-only exact run/segment/state fence predicate and include profile version plus cited source URLs in the internal one-transaction delivery snapshot. |
| `api/strict_citation_finalization.py` | Create | Bounded targets/sources/packet preparation, strict one-call invocation/response parser, deterministic renderer, recomputation, and closed internal errors. |
| `api/server.py` | Modify | Orchestrate generic-family artifact construction, pure strict preparation, immediately-pre-call fence check, one-call invocation, and existing terminal failure/persistence paths. |
| `tests/unit/test_profile_registry.py` | Modify | Profile registration/version/schema, shared policy, generic-family helpers, compiler reuse, and fail-closed policy tests. |
| `tests/unit/test_deepagents_harness.py` | Modify | Strict profile Skill parity and Talent non-regression. |
| `tests/unit/test_agent_run_result.py` | Modify | Strict generic-family outer Evidence capture and Talent/non-source rejection. |
| `tests/unit/test_research_run.py` | Modify | Lock the public exact-URL predicate and unchanged `mark_cited_evidence` behavior. |
| `tests/integration/test_harness_execution.py` | Modify | Strict generic-family validated nested Evidence capture through `ResearchExecutionService`. |
| `tests/unit/test_run_result_service.py` | Modify | Strict canonical/cited resolver invariant plus generic fallback and Talent/unknown non-regression. |
| `tests/unit/test_run_repository.py` | Modify | Exact pre-invocation fence predicate and atomic cited-source delivery snapshot coverage. |
| `tests/unit/test_strict_citation_finalization.py` | Create | Exhaustive bounds, privacy exclusions, parser, renderer, one-call, zero-call, and post-recompute unit proof. |
| `tests/integration/test_strict_citation_profile.py` | Create | Provider-free create-to-resolve lifecycle, idempotency, success/failure, timeout/cancel, fence, and compatibility proof. |
| `tests/unit/test_decision_research_agent_tool.py` | Modify | Prove the existing `--profile` option can run the strict profile through the canonical wait/result golden path without a new CLI command. |
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

The existing internal `get_run_delivery_snapshot()` additionally reads
`profile_version` from the same `research_runs_v2` row and exact non-null
`source_url` values from current-run Evidence rows whose persisted
`citation_status` is `cited`. It returns the URLs as an internal immutable
`cited_source_urls` tuple ordered by `created_at ASC, evidence_id ASC`.
`profile_version` and `cited_source_urls` are resolver inputs only; neither is
added to a REST response, artifact, profile manifest, database schema, or
downstream fixture.

### Strict finalization constants and records

`api/strict_citation_finalization.py` will define:

```python
MAX_TARGETS = 128
MAX_SOURCES = 100
MAX_CONTEXT_BYTES = 512
MAX_PACKET_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
CANONICAL_LINK_LABEL = "Source"
CANONICAL_LINK_PREFIX = " [Source](<"
CANONICAL_LINK_SUFFIX = ">)"

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

@dataclass(frozen=True)
class PreparedStrictCitation:
    outcome: ExecutionOutcome
    initial_artifact: Mapping[str, str]
    targets: tuple[CitationTarget, ...]
    sources: tuple[CitationSource, ...]
    messages: tuple[SystemMessage | HumanMessage, ...]
    config: RunnableConfig

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

The module has a pure preparation boundary and one narrow async invocation
boundary:

```python
def prepare_strict_citation(
    *,
    outcome: ExecutionOutcome,
    initial_artifact: Mapping[str, str],
) -> StrictCitationResult | PreparedStrictCitation: ...

async def invoke_prepared_strict_citation(
    *,
    prepared: PreparedStrictCitation,
    chat_model: BaseChatModel,
) -> StrictCitationResult: ...
```

`prepare_strict_citation()` owns this exact sequence without a model, network,
database, or other external call:

1. Require the strict profile and require `initial_artifact` to equal a fresh
   `build_generic_result_artifact(outcome)` result with canonical non-fallback
   kind; then use only current outcome Evidence and current exact-URL
   recomputation.
2. Return immediately with zero model calls if at least one row is already
   cited.
3. Build deterministic eligible targets and admitted, Markdown-round-tripping
   sources.
4. Serialize the canonical JSON packet and reject it before invocation if any
   count, ID, field, or byte limit fails; construct and freeze the exact
   messages and config in `PreparedStrictCitation`.

For a prepared correction, `api/server.py` performs the exact current fence
read. If the fence is true, it immediately awaits
`invoke_prepared_strict_citation()`. That function performs no validation,
scan, serialization, message construction, callback lookup, or other
material work before its first operation:

```python
response = await chat_model.ainvoke(
    prepared.messages,
    config=prepared.config,
)
```

After that single application-level invocation, it owns this sequence:

5. Require one `AIMessage` with exact string content no larger than `64 KiB`.
6. Parse the response through the strict project-owned validator.
7. Apply placements in canonical target order, using reverse offsets for byte
   stability and the exact application-owned source URL.
8. Rebuild the artifact through `build_generic_result_artifact()` using a
   replacement of the existing `outcome.report_candidate` with only
   `content=corrected_content` changed. This preserves its already validated
   canonical path instead of constructing an underspecified new candidate.
9. Require the rebuilt kind to remain canonical, rerun
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
character offsets while preserving original line endings. This is a
conservative closed scanner, not a general Markdown parser. A target is either
one contiguous non-empty paragraph of plain prose or one simple
unordered/ordered-list (`-`, `*`, `+`, `1.`, or `1)`) or blockquote prose
line outside:

- fenced code opened by backticks or tildes after removing a conservative
  structural view of up to three spaces plus enclosing blockquote/list
  markers; the closer must use the same marker and at least the opener
  length, and a mismatched or unterminated fence excludes the remainder;
- four-space or tab-indented code and indented list-definition
  continuations;
- multi-line raw HTML blocks, comments, processing instructions, declarations,
  CDATA, and tag blocks from opener through their conservative closing or
  blank-line boundary;
- Markdown link-definition lines and their indented continuation lines until
  the next blank line;
- ATX and setext headings, including the prose line immediately before a
  setext underline;
- thematic breaks, hard-break lines ending in two spaces or an unescaped
  backslash, task-list controls, every line containing a pipe character
  (escaped or unescaped), and structural-only marker paragraphs; and
- any paragraph whose bounded excerpt matches the closed sensitive-marker
  guard described below.

The scanner delays emitting a prose paragraph until enough following-line
state is known to reject setext headings and link-definition continuations.
Containerized fences, HTML blocks, definitions, or other ambiguous structures
fail closed as non-targets. It never repairs, normalizes, or reflows Markdown.

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

Before admitting a source to the packet, reject exact URL strings containing
`<`, `>`, or `\`, then render the strict-local CommonMark-safe destination:

```text
[Source](<EXACT_PERSISTED_URL>)
```

and require
`is_exact_source_url_cited(entry.source_url, rendered) is True`. The public
pure predicate is the same implementation used by `mark_cited_evidence` and
the strict result resolver. This keeps insertion aligned to the live exact-URL
matcher without changing global admission.

Also pass a minimal canonical report containing that rendered link through
the public `build_generic_result_artifact()` path and require a non-fallback
artifact whose final bytes still satisfy
`is_exact_source_url_cited(entry.source_url, content)`. This strict-local
preflight catches URLs that the existing result sanitizer would redact or
drop before spending the semantic call. It does not change the global source
admission policy or call a private sanitizer helper.

The packet includes the exact admitted URL because the model must distinguish
sources, but URL bytes used for insertion are looked up again from the
validated `source_id`; model output never owns them.

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

On the correction branch, the target excerpts, admitted public source URLs,
and source snippets in this bounded packet are sent to the already configured
model boundary. They are ephemeral application inputs, not persisted
artifacts, Evidence fields, or public diagnostics. Existing operator-enabled
transport fallback, retry, and tracing may still observe the call; the
feature neither disables them nor claims local-only processing.

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
       prepare_strict_citation
         canonical initial artifact and cited > 0 -> zero-call result
         otherwise -> fully validated PreparedStrictCitation
       read exact current fence after preparation
         false -> return as stale no-op
         true  -> immediately await invoke_prepared_strict_citation once
  -> existing finalization checkpoint
  -> existing termination-origin override
  -> existing fenced finalize_run_transaction
```

The fence-to-call path performs no packet/message construction, artifact
scan, source sanitizer round-trip, database write, or other material work.
The preparation or invocation result returns the final artifact and
recomputed Evidence. An ordinary error is handled by the existing
finalization-stage exception path, which writes `failed/not_required/failed`,
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
- the same artifact and URL fail closed when the snapshot omits
  `profile_version` or contains any version other than exact string `"1"`;
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

1. exact snapshot producer identity
   `profile_id == "generic-strict-citation"` and `profile_version == "1"`;
2. the existing generic artifact hash/media/safety checks;
3. `kind == "research_report_markdown"`; and
4. at least one `cited_source_url` from the repository delivery snapshot for
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
- exclusion of flat and nested list/blockquote fenced code, with backtick and
  tilde openers, longer valid closers, mismatched markers, and unterminated
  fences that exclude the remainder;
- exclusion of indented code, multi-line HTML blocks/comments/declarations,
  link definitions plus continuation lines, ATX headings, and the prose line
  preceding a setext underline;
- exclusion of thematic breaks, hard-break lines, task-list controls,
  escaped-pipe and unescaped-pipe table-like lines, indented list
  continuations, and structural-only paragraphs;
- safe extraction of simple unordered/ordered (`1.` and `1)`) list and
  blockquote prose lines;
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
- an admitted URL containing `(` survives the angle-bracket Markdown
  destination and exact citation matcher;
- exact URLs containing `<`, `>`, or `\`, URLs that cannot round-trip through
  canonical Markdown plus `mark_cited_evidence`, and URLs that do not survive
  a public generic-artifact sanitizer round-trip are rejected before the
  model call;
- IDs are deterministic and capped at 100;
- snippets are UTF-8 bounded to 512 bytes;
- obvious credential/provider/path markers produce `[context omitted]`;
- packet keys and ID uniqueness are exact;
- target/source counts and serialized packet remain within declared bounds;
- packet contains no separately injected query, run/thread/segment ID,
  exception, unrelated Evidence body, or host path; and
- no eligible source fails before any model invocation.

- [ ] **Step 4: Implement source projection and canonical packet encoding**

Use `is_publishable_source_url()`, the strict-local Markdown-destination
guard, the live citation matcher, and the public generic artifact builder.
Serialize with:

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

## Task 4: Add Strict Preparation, Response Validation, Rendering, And One Direct Call

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
- the canonical suffix is exactly ` [Source](<EXACT_URL>)`;
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

- initially cited canonical artifact returns `StrictCitationResult` directly
  from preparation with `call_count == 0`;
- an initial artifact not value-equal to
  `build_generic_result_artifact(outcome)` fails with `call_count == 0`;
- eligible zero-citation artifact returns a fully built
  `PreparedStrictCitation` while `call_count == 0`, and invoking that prepared
  value succeeds with `call_count == 1`;
- no source/target/fallback fails with `call_count == 0`;
- provider exception is replaced by the stable model-failed code with
  `call_count == 1`, `raise ... from None`, and no provider text in the
  rendered exception or traceback;
- malformed response makes exactly one call;
- a defensive post-render recomputation forced to remain uncited makes exactly
  one call and raises invariant-failed;
- no path performs a second application invocation;
- only `SystemMessage` and `HumanMessage` are sent;
- the human payload is bounded and delimited; and
- config contains only the locked callbacks/run-name/tags/metadata values.

- [ ] **Step 6: Implement the prepare/invoke split**

`prepare_strict_citation()` owns all initial-artifact validation,
recomputation, target/source projection, sanitizer round-trips, packet
serialization, and message/config construction. It returns either the final
zero-call result or immutable prepared-call inputs.

The first material operation in `invoke_prepared_strict_citation()` is
`await chat_model.ainvoke(prepared.messages, config=prepared.config)`, exactly
once. Re-raise `asyncio.CancelledError`; map every other invocation exception to
`strict_citation_model_failed` with `raise ... from None` and without retaining
provider text in a rendered traceback or diagnostic. Apply the same visible
context-suppression rule when mapping parser exceptions. Require `AIMessage`
with exact string content. After rendering, rebuild through a replacement of
the existing canonical `ReportCandidate`, recompute citations, and require at
least one cited row.

- [ ] **Step 7: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_strict_citation_finalization.py
git diff --check
git add api/strict_citation_finalization.py \
  tests/unit/test_strict_citation_finalization.py
git commit -m "feat: prepare and invoke strict citation correction"
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
    -k 'finalization_fence_is_current or delivery_snapshot_profile_version or delivery_snapshot_cited_source'
```

Expected RED: predicate is absent.

- [ ] **Step 2: Write delivery-snapshot citation RED tests**

Finalize strict-shaped runs with exact version `"1"` plus a mismatched
version, and with zero, one, duplicate, cited, and uncited Evidence rows.
Assert `get_run_delivery_snapshot()` returns the exact persisted
`profile_version` plus an immutable deterministically ordered tuple containing
only exact non-null source URLs from rows persisted as `cited`, while keeping
all existing snapshot fields unchanged.

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

Add one focused ordering test with an event recorder around only the new
preparation, fence, and model seams. Require
`prepare_complete -> fence_read -> model_entered`, require all serialized
packet/messages to exist at `fence_read`, and require no preparation event
after a true fence. A false fence must end after `fence_read` with zero model
entries.

Expected RED: strict profile either behaves like warning-only generic or is
unsupported by server finalization.

- [ ] **Step 6: Implement server orchestration**

Import the generic-family/strict helpers, configured chat-model singleton,
fence predicate, pure strict preparation, and prepared-call invocation. Build
generic artifacts for both generic-family profiles. Keep literal generic's
existing citation recomputation unchanged. For strict:

1. call `prepare_strict_citation()` before the fence;
2. if it returns a zero-call `StrictCitationResult`, use that result directly;
3. if it returns `PreparedStrictCitation`, read the exact current fence in
   `asyncio.to_thread`;
4. return immediately when the predicate is false;
5. after a true fence, immediately
   `await invoke_prepared_strict_citation(...)`; and
6. pass only the resulting artifact/Evidence to the existing checkpoint and
   terminal transaction.

There must be no artifact scan, target/source projection, sanitizer
round-trip, packet serialization, message construction, callback lookup,
second fence wait, or other material work between the true fence result and
the invocation function's first `chat_model.ainvoke`.

Do not add a new exception response, status, database write, retry, or logging
of caught content.

- [ ] **Step 7: Verify and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_run_repository.py \
    -k 'finalization_fence_is_current or delivery_snapshot_profile_version or delivery_snapshot_cited_source' \
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
- each source/target/packet/model/response/target-stale/artifact/invariant
  failure leaves exactly its closed `strict_citation_*` code in the existing
  task-tracker exception-string log, with no prompt, excerpt, URL, response,
  provider text, host path, or chained exception content;
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

- preparation completes before the fence, then a writer already stale at the
  fence read returns without invoking the model or overwriting the winner;
- a true fence is followed immediately by model entry, with no packet/message
  preparation event between them; and
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
- a strict ready snapshot whose persisted `profile_version` is missing or not
  exact string `"1"` fails closed in `resolve_run_result`, even when its
  artifact and cited URL otherwise match; and
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
- Modify: `tests/unit/test_decision_research_agent_tool.py`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_public_truth_documentation.py`

- [ ] **Step 1: Write documentation contract RED tests**

Lock these exact public truths:

- opt in with existing `profile_id="generic-strict-citation"`;
- discover exact ID/version with
  `GET /api/profiles/generic-strict-citation`; the endpoint does not enumerate
  profiles and the proof schema is documentation identity, not a manifest or
  result field;
- use the existing Tool Client option
  `--profile generic-strict-citation --wait --result` with no new command or
  configuration variable;
- profile version `1` and proof schema
  `dra.strict-citation-profile.v1`;
- ready proves at least one exact current-run admitted URL in a canonical
  non-fallback artifact after application recomputation;
- zero-call initial success and at most one direct semantic placement call;
- the one-call count is application-level and does not claim one transport
  request when the configured wrapper already owns retry or fallback;
- the correction call occurs after the generic DeepAgents graph returns,
  uses its own application-level zero/one-call bound, and is not claimed as
  consumed or measured by the generic harness's model/tool/token middleware;
- application-owned URLs/insertion/recomputation/terminal state;
- the correction branch sends bounded target excerpts, admitted public URLs,
  and bounded source snippets to the configured model, while making no DLP or
  local-only-processing claim;
- generic zero-citation behavior and Talent behavior remain unchanged;
- strict failure reuses `finalization/run_finalization_failed`, retains
  Evidence, and exposes no artifact;
- REST/result callers inspect the existing run status for the bounded failure
  cause, while operators may use only the closed `strict_citation_*` task-log
  code to distinguish local source/target/model/response/invariant categories;
  neither diagnostic is a new result or consumer field;
- no new request/response/DB/status/artifact/failure field;
- a consumer upgrades only by intentionally pinning
  `repository + release/tag-or-commit + profile_id + profile_version +
  proof_schema`;
- a DRA version change does not automatically force a consumer upgrade;
- the proof schema is a documented producer-pin identity and is not falsely
  presented as an API-discoverable field;
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

The canonical reference must provide this developer path:

1. **Choose:** use literal `generic` for backward-compatible warning-only
   delivery; choose strict only when ready must imply at least one exact
   admitted current-run URL.
2. **Discover:** copyable
   `GET /api/profiles/generic-strict-citation`, with explicit version `"1"`,
   no profile-list endpoint claim, and no claim that
   `dra.strict-citation-profile.v1` is returned by the manifest.
3. **Run:** one copyable `POST /api/runs` body and one existing Tool Client
   command:

   ```bash
   python tools/decision_research_agent_tool.py run \
     --profile generic-strict-citation \
     --query "Research question" \
     --wait \
     --result
   ```

4. **Interpret:** zero-call initial success, prepared one-call correction,
   canonical ready invariant, and unchanged result/artifact shapes.
5. **Troubleshoot:** use `GET /api/runs/{run_id}` for the existing
   `finalization/run_finalization_failed` cause; explain that an operator log
   may carry one closed internal `strict_citation_*` category while REST
   deliberately remains coarse. Do not suggest same-run retry or expose raw
   model/provider content.
6. **Understand cost and data:** disclose bounded target excerpts, admitted
   public URLs, and bounded snippets sent to the configured model; distinguish
   one application call from wrapper transport retry/fallback and generic
   harness middleware budgets.
7. **Pin intentionally:** show a small decision table for an existing generic
   consumer, a consumer opting into strict v1, an unrelated future DRA
   version, and a future coherent Release. Only the strict opt-in case needs a
   new producer pin and its own acceptance.
8. **Respect non-claims:** no source truth, entailment, completeness,
   live-provider reliability, one-provider-request, hosted-observability,
   adoption, or release claim.

In `tests/unit/test_decision_research_agent_tool.py`, add one provider-free
CLI test that passes the existing `--profile generic-strict-citation` together
with `--wait --result`, asserts the exact strict profile reaches
`start_run()`, and asserts only the canonical result payload is printed. Do
not modify the Tool Client implementation.

Add the capability to `CHANGELOG.md` under `Unreleased`; do not edit
`VERSION`, a release note, tag, artifact, or release claim.

- [ ] **Step 3: Verify docs and commit**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_decision_research_agent_tool.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
git diff --check
git add docs/reference/strict-citation-profile.md docs/README.md README.md \
  README_CN.md docs/reference/api-contract.md \
  docs/reference/state-machines.md \
  docs/decisions/framework-runtime-boundaries.md docs/architecture.md \
  docs/AGENT_INTEGRATION.md \
  docs/reference/downstream-consumer-contract.md CHANGELOG.md \
  tests/unit/test_decision_research_agent_tool.py \
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
  tests/unit/test_decision_research_agent_tool.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py

PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/bounded_live_producer_proof.py check

PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q -m "not docker"
```

The seven proof commands exactly mirror the current backend CI lane before
the full non-Docker pytest suite. No provider, credential, network, Docker,
or hosted trace is used.

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

- the exact Python 3.11 pinned environment remains unavailable after the one
  authorized task-local bootstrap;
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
- strict result resolution cannot require exact persisted profile version,
  canonical artifact bytes, and still-matching cited source URLs from one
  delivery snapshot;
- provider-free tests cannot traverse create, dispatch, execution service,
  Evidence, correction, persistence, status, and resolver;
- generic, Talent, v0.1.6, or immutable consumer proofs require
  reinterpretation; or
- any provider, credential, network, Docker, dependency, CI, release, or
  downstream mutation becomes necessary.

Do not work around a stop condition with a second call, deterministic source
appendix, consumer gate relaxation, generic contract change, hidden field,
unbounded prompt/response, new dependency, or unapproved environment change.

---

## AutoPlan Review — Phase 1 CEO (Selective Expansion)

This phase reviews strategy, scope, authority, failure behavior, and
long-term product fit. The product-premise gate was explicitly confirmed
before this review. Implementation remains prohibited until every later
AutoPlan phase, the final approval gate, and the execution-environment gate
are closed.

### Step 0A — Premise challenge

| Premise | Live evidence | Decision |
| --- | --- | --- |
| Literal `generic` completion may remain warning-only at zero cited Evidence | `agent/research.py` emits `no_cited_evidence` as a quality issue, while `api/server.py` currently makes a completed canonical generic run ready. Existing compatibility and consumer tests encode that behavior. | Confirmed. A strict global reinterpretation would be a breaking policy change. |
| A strict caller cannot infer exact-source delivery integrity from generic `ready` | The generic terminal path validates a non-empty canonical artifact but does not require any persisted `cited` source URL. | Confirmed. The missing contract is application-owned finalization, not more retrieval volume. |
| A versioned opt-in profile is the smallest legitimate policy surface | `profile_id` already participates in registry selection, persistence, idempotency, manifest lookup, and execution. | Confirmed. No flag, migration, status, artifact kind, or public failure code is justified. |
| One bounded semantic placement step is necessary only when the initial artifact is not already cited | Existing Evidence already contains admitted URLs and the existing matcher can prove the zero-call branch. Ordering alone cannot establish semantic support. | Confirmed. The model selects opaque ID pairs; the application retains every state-changing authority. |
| The configured model wrapper can be invoked once without claiming one provider request | `agent/llm.py` already owns optional transport behavior and provider fallback. | Confirmed with wording correction: the invariant is one application-level `ainvoke`, not one provider HTTP attempt. |
| Provider-free lifecycle proof is the acceptance authority | The deterministic claims are profile routing, count bounds, parsing, rendering, fencing, persistence, and resolution. None requires live-provider quality to be true. | Confirmed. No live-provider, entailment, completeness, or adoption claim follows. |

No premise requires changing the approved product direction.

### Step 0B — Existing-code leverage map

| Sub-problem | Existing authority reused |
| --- | --- |
| Feature selection and immutable identity | `ProfileRegistry`, `ProfileSpec`, `AgentFactory`, existing `profile_id` request/persistence/idempotency path |
| Research execution | The already compiled generic `DeepAgentsHarness`, generic graph, tools, subagents, skills, middleware, budgets, VFS, and `ResearchExecutionService` |
| Source capture | `ExecutionOutcome.evidence_entries`, `extract_evidence_entries()`, nested-stream validation, and `is_publishable_source_url()` |
| Canonical artifact | `build_generic_result_artifact()`, `ReportCandidate`, existing 1 MiB limit, sanitizer, artifact ID, kind, hash, and media type |
| Citation truth | The exact matcher currently private in `agent/research.py` and `mark_cited_evidence()` |
| Deadline and cancellation | `_RunStage`, `create_tracked_task()`, `TerminationOrigin`, and `FinalizationCheckpoint` |
| Stale-writer protection | Existing state-version/segment terminal compare-and-swap in `finalize_run_transaction()` |
| Durable Evidence and artifact state | Existing one-transaction run, segment, Evidence, failure-cause, artifact, and publication write |
| Delivery resolution | `get_run_delivery_snapshot()` and `resolve_run_result()` |
| Privacy-safe diagnostics | Closed failure-cause taxonomy and bounded provider-observability helpers |
| Provider-free proof | Existing fake-harness, fake-model, run lifecycle, timeout/cancel, repository, resolver, and immutable consumer test patterns |

The plan adds a strict finalizer and small closed profile-family branches. It
does not introduce a parallel Agent runtime, evidence store, publication
model, or consumer protocol.

### Step 0C — Dream state

```text
CURRENT
generic ready
  -> canonical non-empty report
  -> Evidence may exist independently
  -> exact cited count may be zero
  -> strict caller cannot distinguish this from exact-source success

THIS PLAN
existing profile_id selects generic-strict-citation@1
  -> exact same generic graph and source admission
  -> application builds canonical artifact and recomputes citation state
  -> already cited: zero correction calls
  -> otherwise: prepare bounded packet, read current fence, then make one
     application-level placement invocation
       -> model returns only target_id/source_id pairs
       -> application renders exact admitted URLs
       -> application rebuilds, sanitizes, recomputes, and persists via CAS
  -> ready only with exact strict version, canonical artifact, and a
     persisted still-matching cited URL
  -> otherwise failed, Evidence retained, no artifact

12-MONTH IDEAL
multiple explicit finalization policies share one small application-owned
policy interface; every ready invariant has a versioned producer identity,
provider-free lifecycle proof, and intentional consumer pin; richer semantic
evaluation or hosted observability exists only when real evidence justifies it
```

### Step 0C-bis — Alternatives

| Approach | Effort | Contract strength | Main advantage | Main cost / risk | Decision |
| --- | ---: | ---: | --- | --- | --- |
| A. Prompt/query strengthening only | S | Low | Minimal code and no new profile | Cannot make generic `ready` imply exact URL presence; repeats an already observed failure mode | Reject as primary fix |
| B. Opt-in strict application finalization | M | High for the declared invariant | Backward compatible, bounded, demonstrable, and application-authoritative | Adds one model-egress path and cross-layer tests | Select |
| C. Downstream relaxation or deterministic source appendix | S/M | False confidence | Avoids semantic call | Either weakens the consumer gate or manufactures a relationship from ordering | Reject |
| D. Global source-aware report-composer redesign | L/XL | Potentially broader | Could make citations native to report generation | Reinterprets generic, enlarges graph/model/tool authority, and cannot close as one bounded phase | Defer until real multi-profile demand |

Approach B is the only option that directly closes the observed contract gap
without changing generic or downstream authority. Approach D is the plausible
long-term alternative, but choosing it now would trade a verifiable invariant
for a broad redesign with no additional consumer evidence.

### Step 0D — Selective-expansion decisions

| Decision | Classification | Result |
| --- | --- | --- |
| Add public disclosure of bounded correction-model inputs and existing tracing/transport boundary | In blast radius, required | Approved and added to Task 7 |
| Distinguish one application invocation from provider retry/fallback attempts | Existing-runtime truth, required | Approved and added to global constraints and docs tests |
| Make Markdown destination strict-local and sanitizer-round-trip before invocation | In blast radius, bounded correctness fix | Approved and added to source/renderer tests |
| Preserve the canonical `ReportCandidate.path` when rebuilding | In blast radius, exact implementation correction | Approved |
| Suppress mapped provider/parser exception context from visible tracebacks | In blast radius, privacy correction | Approved |
| Change `agent/main_agent.py` or `agent/profile_middleware.py` | Duplicate of shared-graph design | Rejected; compiler/harness routing already supplies the strict profile with the exact generic graph |
| Add new logs, counters, telemetry schema, or hosted tracing | Outside the demonstrated need | Deferred |
| Add a new public citation failure code or result field | Consumer coupling without diagnostic benefit | Rejected |
| Change global source admission to make Markdown rendering easier | Outside strict-local policy | Rejected |
| Bump `VERSION`, tag, release, or re-pin a consumer | Separate distribution/consumer authority | Deferred |

### Step 0E — Temporal interrogation

- **Hour 1:** the executor must satisfy the exact-pinned Python 3.11 gate,
  inspect pinned LangChain source, and record the first profile-routing RED.
  The current audit found no already-authorized environment satisfying this
  gate. Final approval later granted one task-local exact-pin bootstrap; the
  closed runtime gate must still pass before implementation begins.
- **Hours 2–3:** profile-family routing and Evidence/result plumbing establish
  that strict execution is the same generic runtime with a different
  application finalization policy. Any need to modify the generic graph or
  middleware is a stop condition.
- **Hours 3–5:** pure target/source projection, strict response parsing,
  CommonMark-safe rendering, artifact-sanitizer round-trip, exception
  suppression, and zero/one-call tests close the local correctness surface.
- **Hours 5–7:** the real tracked lifecycle proves fence, timeout,
  cancellation, failure retention, terminal atomicity, resolver consistency,
  and generic/Talent/consumer non-regression.
- **Closeout:** docs disclose opt-in semantics and model-boundary data flow;
  full provider-free verification and authority review occur before any
  remote or release action.

### Step 0F — Mode confirmation

Mode remains **SELECTIVE EXPANSION**. The five approved corrections are inside
the already declared finalization, privacy, renderer, and documentation blast
radius and do not change the product direction. Broader evaluation,
observability, generic redesign, consumer mutation, and release work remain
outside this phase.

### Step 0.5 — Independent voices and degradation

The required fresh subagent voice did not return a completed review after two
bounded attempts. The Codex CLI voice inspected the live tree but exceeded
the ten-minute phase timeout before producing a final verdict. Per the
AutoPlan degradation rule, neither incomplete stream is counted as a review
voice or as consensus; only findings independently reproduced against live
code by the architecture-authority review are retained.

| Dimension | Independent subagent | Codex CLI | Consensus |
| --- | --- | --- | --- |
| Premises valid | N/A | N/A | Not counted |
| Right problem | N/A | N/A | Not counted |
| Scope calibration | N/A | N/A | Not counted |
| Alternatives explored | N/A | N/A | Not counted |
| Product/market risk | N/A | N/A | Not counted |
| Six-month trajectory | N/A | N/A | Not counted |

No dual-voice user challenge exists because no two completed outside voices
exist. The phase proceeds in documented single-reviewer mode rather than
inventing agreement.

### Section 1 — Architecture

```text
POST /api/runs(profile_id=generic-strict-citation)
  -> existing registry / idempotency / persisted profile version
  -> existing generic DeepAgents graph and middleware
  -> ExecutionOutcome + current-run Evidence + canonical ReportCandidate
  -> existing generic artifact builder and exact citation recomputation
       | already cited
       |   `-> zero-call strict result
       ` correction needed
           -> pure target/source/packet/message preparation
           -> read current run/segment/state fence immediately before call
           -> one configured-model ainvoke with bounded untrusted packet
           -> strict ID-only response validation
           -> application-owned CommonMark link insertion
           -> public artifact-builder sanitizer round-trip
           -> application-owned citation recomputation
  -> existing finalization checkpoint / termination precedence
  -> existing fenced terminal transaction
  -> one-snapshot strict result resolver
```

This preserves the core authority split: framework execution creates a
candidate, while the application decides admission, rendering, citation
state, terminal status, persistence, and delivery. `agent/main_agent.py`
already registers every non-literal-generic profile graph returned by the
factory, and the strict compiler can return the exact generic graph object.
`agent/profile_middleware.py` is only used while the generic graph is built,
so modifying it would create a second policy path rather than improve reuse.

### Section 2 — Error and rescue map

| Failure point | Closed internal result | Rescue / terminal behavior | Public observation |
| --- | --- | --- | --- |
| Initial artifact is fallback, mismatched, empty, or excessive | `strict_citation_initial_artifact_invalid` | No model call; existing finalization failure path | `finalization/run_finalization_failed`, no artifact |
| No admitted and renderer-safe current-run source | `strict_citation_source_unavailable` | No model call; retain frozen Evidence | Same bounded public cause |
| No safe prose target | `strict_citation_target_unavailable` | No model call | Same bounded public cause |
| Count, ID, field, or packet bytes invalid | `strict_citation_packet_invalid` | No model call | Same bounded public cause |
| Configured model invocation raises | `strict_citation_model_failed` | One application call; map outside visible provider context | Same bounded public cause |
| Response type, bytes, JSON, keys, or IDs invalid | `strict_citation_response_invalid` | No retry or second call | Same bounded public cause |
| Target bytes/hash changed | `strict_citation_target_stale` | Reject all partial output | Same bounded public cause |
| Rebuilt artifact fallback, sanitized unexpectedly, or too large | `strict_citation_artifact_invalid` | Persist neither partial nor ready artifact | Same bounded public cause |
| Post-render cited count remains zero | `strict_citation_invariant_failed` | No retry; retain original Evidence | Same bounded public cause |
| Writer already stale before invocation | No strict exception | Return without model call or mutation | Existing winner remains authoritative |
| Writer loses after invocation | Terminal CAS returns false | No overwrite, no fallback terminal cause | Existing winner remains authoritative |
| Shared deadline wins | Existing timeout classification | Cancel in-flight model call; timeout callback finalizes | `finalization/run_timeout` |
| Explicit cancellation wins | Existing cancellation classification | Propagate `CancelledError`; cancellation callback finalizes | `finalization/cancelled` |

The rescue policy is intentionally fail closed and non-retrying. Original
Evidence remains useful diagnosis, while a partial corrected artifact never
becomes a shadow delivery channel.

### Section 3 — Security and threat model

| Threat | Boundary | Mitigation | Residual truth |
| --- | --- | --- | --- |
| Prompt injection in report/source text | Correction packet | Fixed system instruction, explicit untrusted delimiters, bounded excerpts, ID-only output parser | Delimiting is not a proof of semantic model compliance |
| Model invents or rewrites a URL | Response boundary | Response accepts issued IDs only; application looks up exact admitted URL | Model still chooses semantic placement |
| Unsafe/private URL becomes public citation | Source projection | Reuse public-HTTPS policy, strict-local Markdown guard, citation round-trip, artifact-sanitizer round-trip | Source admission does not prove source quality |
| Sensitive report/snippet content is sent to the configured model | Model input | 512-byte bounds, narrow marker exclusion/omission, no separately injected query or IDs, explicit public documentation | The guard is not DLP; bounded source/report text still crosses the configured model boundary |
| Provider exception leaks through diagnostics | Exception mapping | Closed code, `raise ... from None`, stable task log string, no prompt/response persistence | Operator-owned underlying transport may have its own bounded observability |
| Hosted trace or configured fallback is silently disabled/redefined | Framework boundary | Reuse wrapper unchanged and document that tracing/retry/fallback remain operator/runtime owned | One `ainvoke` does not prove one provider HTTP request |
| Stale writer spends or persists work | Fence + terminal CAS | Pre-call fence prevents already stale spend; terminal CAS prevents overwrite | A writer that becomes stale in flight may spend its one call |

The dominant new confidentiality surface is the correction packet sent to the
configured model. The plan now requires public disclosure of exactly which
bounded fields cross that boundary and explicitly avoids a DLP or local-only
claim. No credential, provider call, or hosted trace is used by CI acceptance.

### Section 4 — Data flow and shadow paths

```text
validated tool output
  -> EvidenceEntry in ExecutionOutcome
  -> strict-local source projection
       -> ephemeral prepared packet
       -> current fence
       -> configured model -> ephemeral ID response
  -> deterministic corrected report bytes
  -> recomputed Evidence citation_status
  -> one terminal SQLite transaction
       -> run / segment / Evidence / artifact / failure cause
  -> one delivery snapshot
       -> profile_version + artifact + cited_source_urls
  -> strict resolver
```

The packet, prompts, response, target text, and partial corrected artifact
must never enter SQLite, public status, Evidence, artifact history, or public
docs. Timeout, cancellation, ordinary failure, and lost-writer paths all end
with either the existing winning state or retained Evidence plus no artifact.
The resolver rechecks exact URL presence from a single snapshot, preventing a
persisted cited flag from becoming sufficient by itself.

### Section 5 — Code quality

One closed `is_generic_family()` helper is preferable to scattering a third
profile literal, while one `is_strict_citation_profile()` helper keeps strict
terminal behavior explicit. The new finalizer should remain mostly pure
projection/parser/renderer functions with one narrow async adapter, rather
than becoming a generic policy framework before a second finalizer exists.
Preserving the existing `ReportCandidate` path and using the public artifact
builder avoids duplicating canonicalization and sanitizer internals.

The planned no-change boundary for `agent/main_agent.py` and
`agent/profile_middleware.py` is sound and testable. If implementation cannot
reuse the exact compiled graph through `compile_profile_agent()` and
`DeepAgentsHarness.with_profile_graph()`, the correct response is to stop,
not to build parallel middleware.

### Section 6 — Test strategy

```text
pure REDs
  profile family
  source/target bounds
  Markdown + sanitizer round-trip
  strict parser
  deterministic renderer
  visible exception suppression
  zero/one application call
       |
       v
repository REDs
  current fence
  cited-source delivery snapshot
       |
       v
provider-free production lifecycle
  create -> dispatch -> generic harness stream -> Evidence
  -> zero/one correction -> timeout/cancel/fence/CAS
  -> SQLite -> status -> resolver
       |
       v
non-regression
  literal generic + Talent + immutable consumer + docs + full non-Docker suite
```

The positive lifecycle must not patch the terminal transaction, resolver,
Evidence persistence, citation matcher, tracker, or status projection.
Focused negative controls may patch only the exact layer whose defensive
failure is under test and must still assert call count and durable state.
Provider-free proof establishes deterministic application behavior but does
not establish live-provider quality, semantic entailment, or completeness.

### Section 7 — Performance

The zero-call path adds citation recomputation only. The correction path scans
at most a 1 MiB artifact and bounded Evidence, builds at most 128 targets and
100 sources, sends at most 512 KiB, receives at most 64 KiB, and performs one
application-level model invocation. Database overhead is one short
pre-invocation fence read and one cited-source query inside the existing
delivery snapshot.

The main latency cost is deliberately opt-in and dominated by the configured
model boundary. Existing wrapper retries or fallback may add transport work,
which is why the plan does not claim one provider request. This post-graph
call has its own application bound and is not claimed as counted by generic
DeepAgents model/tool/token middleware. No cache, queue, new connection pool,
migration, or hosted service is added.

### Section 8 — Observability and debuggability

Public diagnosis remains the existing terminal state and bounded failure
cause. Internal strict errors are closed codes suitable for stable task-log
strings; raw prompts, packets, responses, target/source excerpts, and provider
exception text are excluded. Tests provide call counts and state-transition
evidence without creating a new runtime telemetry contract.

No hosted trace is needed for acceptance, and an operator-enabled trace is
not silently overridden. Future observability fields require a demonstrated
operator task and a separate privacy review; this phase does not add them.

### Section 9 — Deployment, rollback, and release

The feature is inert unless a caller selects the new profile. There is no
schema migration, dependency change, CI workflow change, version bump, tag,
or release artifact, so code rollback is a bounded commit/merge revert.
Generic, Talent, v0.1.6, and the immutable consumer fixture remain unchanged.

At review time, the execution environment did not satisfy the exact-pinned
Python 3.11 gate and no installation authority existed. Final approval later
authorized one task-local `.venv` populated only from the unchanged exact
constraints. A failing post-bootstrap gate remains an implementation-start
blocker, not a reason to weaken the plan or use another interpreter. Release
remains a separate decision after a coherent bounded pack or real consumer
distribution need exists.

### Section 10 — Long-term trajectory

This phase creates one versioned proof boundary rather than promising that
all future DRA outputs are citation-complete. If a second application-owned
finalization policy appears, a small explicit finalizer registry may become
worthwhile; until then, a generic framework would be speculative. Consumers
upgrade only by intentionally pinning a new producer tuple, so DRA can evolve
without forcing downstream lockstep.

Six-month regret would come from describing one `ainvoke` as one provider
request, hiding model-boundary data egress, or allowing renderer/sanitizer
differences to turn exact URL presence into malformed Markdown. Those risks
are now explicit plan tests and documentation contracts. Broader source
quality, entailment, and evaluation belong to later evidence-backed phases.

### Section 11 — Design

Skipped because no UI behavior, component, layout, interaction, or visual
state changes. The frontend currently presents result content as preformatted
text; this plan changes backend artifact integrity and developer contracts,
not presentation.

### What already exists

The leverage map above is authoritative: profile identity, generic execution,
Evidence admission, artifact construction, exact citation matching, tracked
deadline/cancellation, fenced persistence, durable failure causes, result
resolution, and provider-free lifecycle patterns all exist. The net-new
product behavior is only the opt-in finalization invariant and its bounded
semantic placement adapter.

### NOT in scope

- changing literal `generic` or Talent behavior;
- prompt/query-only retries or a second semantic call;
- one-provider-request guarantees, provider selection, transport retry, or
  fallback redesign;
- deterministic source appendices or application-selected semantic support;
- source truth, quality, entailment, completeness, or ranking evaluation;
- a new graph, subagent, tool, middleware, checkpoint, or trace authority;
- new database fields, migrations, statuses, artifact kinds, public failure
  codes, response fields, or consumer-fixture fields;
- DLP, credential scanning, generic process-log safety, or local-only model
  processing claims;
- hosted observability, dashboards, UI, benchmarks, or live-provider tests;
- consumer mutation, automatic re-pin, version bump, tag, Release, deploy, or
  cleanup.

### Failure modes registry

| Failure mode | Detection | Required end state |
| --- | --- | --- |
| Initial canonical invariant already holds | Exact current-outcome recomputation | Ready, canonical artifact, cited Evidence, zero call |
| Initial artifact cannot support strict delivery | Kind/value/size/sanitizer checks | Failed, Evidence retained, no artifact, zero call |
| No renderer-safe source or target | Pure projection | Failed, Evidence retained, no artifact, zero call |
| Packet exceeds a closed bound | Canonical encoded-byte check | Failed, no call |
| Configured model fails | Closed exception mapping | Failed, Evidence retained, no artifact, one application call |
| Model returns malformed or unauthorized data | Exact JSON/type/key/ID parser | Failed, no retry |
| Markdown destination or artifact sanitizer cannot preserve exact URL | Strict-local preflight and post-build check | Source rejected before call or strict failure after call |
| Target changed after extraction | Slice + hash check | Failed, no partial artifact |
| Post-correction cited count remains zero | Existing citation recomputation | Failed, no second call |
| Deadline or cancellation wins | Existing tracker/origin | Existing finalization timeout/cancel cause |
| Writer stale after preparation but before call | Exact immediately-pre-call fence read | No call and no mutation |
| Writer loses after call | Existing terminal CAS | No overwrite; winner remains authoritative |
| Persisted cited flag and artifact bytes diverge | One-snapshot strict resolver | Existing unavailable result |
| Persisted strict profile version is missing or mismatched | One-snapshot producer identity check | Existing unavailable result |
| Exact-pinned environment remains unavailable after authorized bootstrap | Pre-RED environment gate | Stop with the closed prerequisite code |

### Dream-state delta

After this plan, DRA will have one verifiable application-owned strict
citation invariant, not a general evaluation platform. It will still lack
semantic entailment proof, citation completeness, provider-quality evidence,
and a generic finalization-policy framework. Those omissions are deliberate:
they require new evidence and separate product decisions rather than being
smuggled into this bounded closeout.

### CEO implementation tasks

- [x] **CEO-1 (P1):** close the exact-pinned Python 3.11 environment authority
  gate before the first RED; final approval authorized only the task-local
  exact-pin bootstrap, while the runtime gate remains mandatory.
- [ ] **CEO-2 (P2):** implement strict-local CommonMark destination and public
  artifact-sanitizer round-trip tests without changing global URL admission.
- [ ] **CEO-3 (P2):** preserve the canonical `ReportCandidate.path` on rebuild
  and prove all non-insertion bytes remain stable.
- [ ] **CEO-4 (P2):** suppress visible provider/parser exception context and
  prove raw exception text does not reach diagnostics or rendered traceback.
- [ ] **CEO-5 (P2):** document bounded correction-model inputs and distinguish
  one application invocation from configured retry/fallback transport work.

### CEO decision audit trail

| ID | Finding | Decision | Basis |
| --- | --- | --- | --- |
| CEO-D1 | Model-input disclosure was implicit | Require explicit public docs | Security boundary and developer informed opt-in |
| CEO-D2 | One-call wording could be read as one HTTP request | Define it as one application `ainvoke` | Reuse the configured wrapper without reinterpretation |
| CEO-D3 | Bare Markdown destination is unsafe for some admitted URLs | Use angle-bracket destination plus strict-local guard | Exact URL bytes and valid deterministic Markdown |
| CEO-D4 | Citation-regex round-trip does not prove sanitizer survival | Add public artifact-builder preflight | Avoid a predictable wasted call and post-build drift |
| CEO-D5 | New `ReportCandidate(...)` was underspecified | Replace the existing canonical candidate | Reuse validated path authority |
| CEO-D6 | Stable exception string alone may leave visible chained context | Require `raise ... from None` and traceback test | Privacy-safe failure diagnostics |
| CEO-D7 | No exact-pinned environment existed at review time | Keep implementation blocked pending authority; final approval later granted bounded bootstrap authority | No implicit dependency install or non-authoritative interpreter |
| CEO-D8 | Main-agent/middleware edits were considered | Reject them | The strict profile must reuse the exact compiled generic graph |
| CEO-D9 | Release/version/consumer update was considered | Defer | Distribution is not an implementation invariant |

### Phase 1 completion summary

| Area | Result |
| --- | --- |
| Premises | 6 confirmed; no direction change |
| Selected approach | Opt-in application-owned strict finalization |
| Scope mode | Selective expansion |
| Required plan corrections | 5, all applied inside existing blast radius |
| Architecture | Shared generic graph; strict finalizer; existing terminal authority |
| Security | Bounded model egress disclosed; output/exception fail closed |
| Tests | Provider-free unit + real lifecycle + compatibility matrix |
| Performance | Zero/one application call with closed byte/count limits |
| Deploy/release | Inert unless selected; no automatic release |
| Outside voices | Unavailable; single-reviewer mode, no invented consensus |
| User challenges | 0 |
| Taste decisions | 0 |
| Execution prerequisite | Environment authority granted; exact runtime gate pending |

**Phase 1 complete.** Outside voices produced no completed verdict and are
recorded unavailable. Primary review found five bounded plan corrections,
applied them, and found no reason to change the approved product direction.
UI design review is skipped; the next phase is the full engineering review.

## AutoPlan Review — Phase 2 Design (Skipped)

The feature has no frontend, visual, interaction, layout, navigation, or
component-state change. Existing API status and result payload shapes are
unchanged, and the current frontend displays result content without a new
rendering contract. Design review is therefore explicitly skipped rather than
manufacturing UI scope. Backend developer experience is reviewed in Phase 4.

## AutoPlan Review — Phase 3 Engineering

This phase challenges implementation order, authority boundaries, failure
atomicity, parser/renderer correctness, test completeness, CI parity, and
operational cost. It reviews the plan against current source, tests,
repository schema, and CI configuration. It does not grant dependency,
provider, release, or implementation authority.

### Engineering scope and complexity challenge

The approved behavior crosses profile registration, generic-family routing,
Evidence capture, artifact preparation, one model boundary, repository
fencing, terminal persistence, and result resolution. That cross-layer path
is irreducible for a ready-result invariant, but the implementation surface is
still bounded:

- one new production module owns preparation, parsing, rendering, and the
  single async invocation;
- existing source admission, artifact construction, citation matching,
  deadline/cancellation, terminal CAS, and public error shapes remain
  authoritative;
- one internal delivery-snapshot field and one internal cited-URL tuple are
  added without migration or response-schema change;
- only two literal generic-family observation branches change;
- `agent/main_agent.py` and `agent/profile_middleware.py` remain unchanged;
- no new dependency, graph, middleware, tool, subagent, checkpoint, queue,
  cache, telemetry schema, frontend path, or release workflow is justified.

The planned file count looks broad because the invariant requires tests and
public contract updates across existing seams, not because many production
abstractions are being introduced. Tasks remain serial: Task 2 depends on
Task 1 profile identity; Tasks 3–4 establish pure preparation/invocation;
Task 5 binds them to the live repository fence; Task 6 proves lifecycle
failure behavior; docs and full CI parity follow only after behavior is
closed.

### Independent engineering voice and convergence

The collaboration subagent did not return a completed report and was
interrupted after bounded attempts. A separate read-only Codex CLI review did
complete against the live tree and returned `CHANGES REQUIRED`. It identified
four verified plan defects. The architecture-authority review independently
reproduced all four and found two additional clarity/diagnostic gaps.

| Finding | Collaboration subagent | Codex CLI | Architecture authority | Result |
| --- | --- | --- | --- | --- |
| Fence occurred before expensive preparation instead of immediately before `ainvoke` | Unavailable | High severity | P1 | Converged; corrected |
| Strict resolver omitted exact persisted `profile_version` | Unavailable | High severity | P1 | Converged; corrected |
| Target scanner omitted container/block structural cases | Unavailable | High severity | P2 | Converged; corrected |
| Full verification omitted seven backend CI proof commands | Unavailable | Medium severity | P1 | Converged; corrected |
| Missing-package environment gate exposed an uncontrolled exception shape | Unavailable | Considered functionally fail-closed | P2 refinement | Closed stable code added |
| Correction-call budget could be confused with generic harness middleware | Unavailable | Not raised | P2 clarity | Closed disclosure added |
| `main_agent.py` and `profile_middleware.py` can remain unchanged | Unavailable | Confirmed | Confirmed | No-change boundary retained |

This is one completed independent voice plus primary verification, not
two-outside-voice consensus. No unavailable or partial output is counted as a
verdict.

### Locked dependency and authority graph

```text
POST /api/runs(profile_id=generic-strict-citation)
  -> profile_registry: exact profile_id/version + shared GENERIC_POLICY
  -> profile_agents/deepagents_harness: exact existing generic graph
  -> run_result/research_execution_service: existing admitted source Evidence
  -> ExecutionOutcome + canonical ReportCandidate
  -> build_generic_result_artifact
  -> prepare_strict_citation                  [pure, bounded, no model/DB]
       | cited already
       |   `-> StrictCitationResult           [zero call]
       ` correction needed
           -> targets + sources + packet + messages
           -> PreparedStrictCitation          [ephemeral]
           -> run_finalization_fence_is_current
                | false -> stale no-op         [zero call]
                ` true
                    -> invoke_prepared_strict_citation
                         first material operation:
                         chat_model.ainvoke    [one application call]
                         -> strict JSON parser
                         -> deterministic exact-URL renderer
                         -> canonical artifact rebuild
                         -> citation recomputation
                         -> StrictCitationResult
  -> existing finalization checkpoint / termination precedence
  -> existing fenced finalize_run_transaction [single terminal authority]
  -> get_run_delivery_snapshot
       profile_id + profile_version + artifact + cited_source_urls
  -> strict resolver
       exact generic-strict-citation@1
       + canonical non-fallback artifact
       + still-matching persisted cited URL
```

The split removes duplicate initial-citation logic from the server and makes
the fence contract mechanically testable. Preparation may consume bounded
local CPU before discovering that a writer is stale, but no model spend occurs
after staleness is observed. A writer that becomes stale during the already
started call may spend that call but cannot win the existing terminal CAS.

### Code-quality review

- `is_generic_family()` centralizes only the two profiles that share the graph
  and Evidence behavior; `is_strict_citation_profile()` keeps terminal policy
  explicit.
- `PreparedStrictCitation` is an ephemeral value object. It is never a
  database row, public model, artifact, status, or consumer field.
- Pure preparation contains every scan, sanitizer round-trip, byte/count
  check, packet serialization, and message construction. The async adapter is
  intentionally narrow and starts with the model call.
- The renderer looks up application-owned URLs from issued IDs, validates
  original target bytes/hash, applies reverse-offset insertions, and rebuilds
  through the public generic artifact builder.
- `get_run_delivery_snapshot()` extends one existing consistent read instead
  of creating a second resolver query or migration.
- Conservative Markdown structure recognition is preferable to a new parser
  dependency for one insertion policy. Ambiguous container/block content is
  rejected, not normalized.
- Closed mapped exceptions use stable codes and suppress caught provider or
  parser context. Cancellation remains outside ordinary-error translation.

If implementation needs a second graph, server-side duplicate preparation,
new parser dependency, second model call, public field, migration, or new
terminal writer, it has diverged from the reviewed architecture and must
stop.

### Exhaustive RED-to-GREEN test map

```text
environment gate
  missing package / mismatched pin -> one closed prerequisite code

profile and graph
  identity/version/policy -> same generic graph -> Talent negative control

Evidence and artifact plumbing
  outer + nested admitted source -> generic-family Evidence
  wrong namespace/tool/profile -> no Evidence
  generic canonical/fallback behavior unchanged

pure strict preparation
  canonical equality + initial recomputation
  | cited -> zero-call result
  ` uncited
      -> conservative target scanner
      -> strict-local source admission + sanitizer round-trip
      -> count/byte-bounded packet + exact messages
      -> prepared value, still zero calls

one-call adapter
  AIMessage + exact JSON + issued IDs
  -> reverse-offset renderer -> rebuilt artifact -> recomputed cited Evidence
  malformed/model error/stale target/oversize/zero cited
  -> closed failure, never retry

tracked production lifecycle
  prepare_complete -> fence_read
  | false -> stale no-op, zero calls
  ` true -> immediate model_entered, one call
      | success -> checkpoint -> terminal CAS -> ready
      | ordinary failure -> retained Evidence, no artifact
      | timeout/cancel -> existing termination cause
      ` lost writer -> CAS no-op

delivery
  one snapshot: exact profile version + artifact + cited URLs
  | exact v1 + canonical + still matching -> result
  ` missing/mismatched version, fallback, no cited URL, or byte divergence
      -> existing unavailable result

non-regression and parity
  literal generic + Talent + immutable v0.1.6 consumer
  docs contracts + seven deterministic backend proofs
  + full pytest -m "not docker"
```

Structural scanner REDs explicitly cover setext lookahead, ATX headings,
multi-line HTML blocks/comments/declarations, link-definition continuations,
flat and nested list/blockquote fences, backtick/tilde marker and length
rules, mismatched/unterminated fences, `1.` and `1)` lists, indented
continuations, hard breaks, escaped and unescaped pipes, and structural-only
paragraphs. No test may call a provider or weaken the current exact-URL
matcher to turn a rendering bug into success.

### Performance and resource review

- Zero-call strict success performs one canonical artifact build and citation
  recomputation.
- Correction preparation scans at most 1 MiB, caps targets at 128, sources at
  100, each excerpt at 512 bytes, the packet at 512 KiB, and the response at
  64 KiB.
- The immediately-pre-call fence is one short read. No SQLite transaction is
  held across the model boundary.
- The correction model call occurs after the generic graph returns. Its
  zero/one application-call bound is separate from generic
  `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`, and
  `TokenTrackingMiddleware`.
- The configured wrapper may perform existing transport retry or provider
  fallback internally. The feature adds neither and claims neither one
  provider request nor a latency bound.
- Persistence remains one terminal transaction; resolution remains one
  delivery snapshot. No cache, queue, pool, migration, background worker, or
  hosted service is added.

### Engineering failure registry

| Severity | Failure | Prevention / proof | Status in plan |
| --- | --- | --- | --- |
| P1 | Writer becomes stale during packet preparation but still spends a call | Pure prepare, then one exact fence immediately before async adapter; ordering RED | Closed |
| P1 | Resolver accepts another strict profile version | Snapshot carries version; resolver requires exact `generic-strict-citation@1`; negative RED | Closed |
| P1 | Local completion differs from required backend CI | Run all seven current deterministic proof commands before full non-Docker pytest | Closed |
| P2 | Markdown structure is misclassified as prose | Conservative state rules plus exhaustive container/block REDs | Closed |
| P2 | Missing package emits uncontrolled prerequisite error | Catch `PackageNotFoundError`; missing and mismatch emit one closed code | Closed |
| P2 | Correction call is attributed to generic harness budgets | Global constraint and public docs explicitly separate the bounds | Closed |
| P2 | Provider/parser text leaks through chained exceptions | Stable code, `raise ... from None`, traceback/diagnostic assertions | Closed in CEO phase |
| P2 | Persisted cited flag drifts from artifact bytes | One-snapshot cited URLs plus live exact matcher in resolver | Closed |
| Blocker | Exact-pinned Python 3.11 gate remains false after authorized bootstrap | Stop before first RED with the closed prerequisite code | Runtime check pending |

### What already exists

- versioned profile registry, policy validation, idempotent creation, and
  persisted profile version;
- one compiled generic DeepAgents graph with current model/tool/token
  middleware;
- outer and nested source-Evidence capture with current admission policy;
- canonical generic artifact builder and exact URL citation matcher;
- one tracked deadline/cancellation origin and finalization checkpoint;
- fenced terminal SQLite transaction and durable bounded failure cause;
- internal one-snapshot result resolution;
- provider-free fake-model and end-to-end repository test patterns;
- seven deterministic backend proof scripts and a full non-Docker CI suite.

### Engineering NOT in scope

- a general finalization framework before a second real policy exists;
- `agent/main_agent.py` or `agent/profile_middleware.py` changes;
- a new Markdown dependency or global source-admission reinterpretation;
- moving correction into DeepAgents or counting it as generic middleware work;
- a preliminary plus final fence, durable lease, or transaction held across
  the model call;
- new status/failure/API/DB/consumer fields or a migration;
- provider-backed, network, Docker, frontend, hosted-trace, or benchmark work;
- version bump, release, downstream re-pin, push, PR, merge, or cleanup.

### Sequential engineering tasks

- [ ] **ENG-SC-1 (P1):** implement and prove the pure
  `prepare_strict_citation()` / immediate
  `invoke_prepared_strict_citation()` split around the repository fence.
- [ ] **ENG-SC-2 (P1):** carry `profile_version` in the internal delivery
  snapshot and require exact strict v1 producer identity in resolution.
- [ ] **ENG-SC-3 (P1):** run all seven backend deterministic proof commands
  plus the full non-Docker suite in the exact-pinned environment.
- [ ] **ENG-SC-4 (P2):** implement the conservative container/block Markdown
  scanner and exhaustive structural RED matrix.
- [ ] **ENG-SC-5 (P2):** keep the environment gate's missing/mismatch result
  to one stable closed prerequisite code.
- [ ] **ENG-SC-6 (P2):** document that post-graph correction has its own
  application-call bound and is not generic harness budget/telemetry.

These are implementation checkboxes, not unresolved plan decisions. Their
interfaces, failure behavior, and tests are now locked above. Environment
authority is granted, but the exact runtime gate must pass before ENG-SC-1
may begin.

### Engineering decision audit trail

| ID | Finding | Decision | Rejected alternative |
| --- | --- | --- | --- |
| ENG-D1 | Original fence preceded bounded but material preparation | Return a fully prepared ephemeral call, then fence, then invoke immediately | Keep early fence; add vague stale tests |
| ENG-D2 | A second fence could close timing while retaining old API | Use one fence after pure preparation | Add redundant DB read and two notions of freshness |
| ENG-D3 | Resolver identity omitted version | Include existing persisted version in the same snapshot and require exact v1 | Add a public field or migration |
| ENG-D4 | Flat scanner rules missed CommonMark containers/blocks | Fail closed on explicit ambiguous structures with no new dependency | Install a parser or accept best-effort placement |
| ENG-D5 | Pytest alone did not mirror backend CI | Run all seven exact current proof commands, then full non-Docker pytest | Treat proof scripts as implied by pytest |
| ENG-D6 | Missing package still failed nonzero | Normalize prerequisite output to one closed code | Leak package exception details |
| ENG-D7 | Post-graph call could be misattributed to harness budgets | Declare a separate zero/one application-call authority | Modify generic middleware or invent unified telemetry |
| ENG-D8 | Main-agent/middleware edits were considered | Keep both unchanged and stop if graph reuse fails | Duplicate graph assembly |
| ENG-D9 | Parallel tasks/worktrees were considered | Execute Tasks 1–8 serially in the existing isolated worktree | Create merge conflicts across shared profile/server/tests |

### Phase 3 completion summary

| Area | Result |
| --- | --- |
| Completed independent voices | 1 Codex CLI; collaboration subagent unavailable |
| Verified required changes | 6 |
| Plan corrections applied | 6 |
| Call timing | Pure prepare -> exact fence -> immediate one application call |
| Producer identity | Exact persisted `generic-strict-citation@1` |
| Markdown placement | Conservative structural fail-closed scanner |
| CI parity | Seven proof scripts + full non-Docker pytest |
| Framework reuse | Existing generic graph and wrapper; no new dependency |
| No-change files | `agent/main_agent.py`, `agent/profile_middleware.py` |
| Implementation prerequisite | Authority granted; exact runtime gate pending |

**Phase 3 complete.** The prior Engineering verdict `CHANGES REQUIRED` is
closed at plan level. At phase completion implementation still awaited DX and
final approval; both were completed later in this plan.

## AutoPlan Review — Phase 4 Developer Experience

This phase reviews how an API caller, Tool Client user, operator, downstream
consumer, and repository maintainer discover, select, verify, troubleshoot,
and intentionally pin the strict profile. It does not add a UI, new endpoint,
CLI option, public field, installer, or release workflow.

### Developer personas and jobs

| Persona | Job | Required shortest path | Primary footgun |
| --- | --- | --- | --- |
| REST integrator | Request an exact-source-ready run | Manifest GET -> existing POST with strict `profile_id` -> status -> result | Assuming a ready generic run has the strict invariant |
| Tool Client integrator | Use the canonical local client | Existing `run --profile ... --wait --result` | Assuming a new command or config variable is required |
| Operator | Diagnose a fail-closed run safely | Status failure cause + one closed task-log code | Logging raw prompt, response, URL, or provider exception |
| Downstream consumer | Adopt strict output intentionally | Pin repository/release-or-commit + profile ID/version + proof schema | Treating every DRA version as a forced consumer upgrade |
| Repository maintainer | Implement and prove the feature | Exact environment gate -> serial TDD -> seven proofs -> full suite | Installing implicitly or claiming local pytest equals CI |

### Existing developer surface

- `POST /api/runs` already accepts `profile_id`; no request change is needed.
- `GET /api/profiles/{profile_id}` already returns one server-owned manifest;
  there is no profile-list route.
- The Tool Client already supports `run --profile`; no CLI implementation
  change is needed.
- `GET /api/runs/{run_id}` already owns bounded status and failure cause.
- `GET /api/runs/{run_id}/result` and the selected artifact route already own
  delivery; result errors deliberately remain coarse.
- README, API contract, Agent Integration, downstream contract, state machine,
  architecture/runtime-boundary docs, and the docs index already provide the
  correct information architecture.
- The repository already distinguishes a selected verification subset from
  the exact required CI proof inventory.

The DX change is therefore a precise reference and cross-linking job, plus one
CLI non-regression test and closed-log assertions. Building a new discovery
endpoint, CLI command, result field, diagnostics API, or setup script would
duplicate existing surfaces.

### Independent DX voice and live revalidation

One bounded collaboration voice completed with `CHANGES REQUIRED`. Two of its
observations—missing CI proofs and ambiguity about harness budgets—had already
been corrected in the live plan during Engineering review; they were
revalidated against the current text and are not counted as new open
findings. Two findings remained actionable and were independently reproduced:

| Finding | Independent voice | Live revalidation | Resolution |
| --- | --- | --- | --- |
| Seven backend proof scripts must be local completion gates | P1 | Already present in current Task 8 | Closed in Phase 3 |
| Post-graph call is outside generic middleware budgets | P2 | Already explicit in constraints/docs tests | Closed in Phase 3 |
| Generic public failure cause is insufficient for operator root-category diagnosis | P1 | Existing task tracker logs the re-raised exception string safely | Lock one closed internal code; no new public field |
| Profile cannot be enumerated and proof schema is absent from manifest | P2 | Confirmed by current profile route and planned manifest contract | Add exact discovery/run wording and non-field warning |
| Environment gate was actionable but separately blocked | Clean | Confirmed | Final approval later granted bounded bootstrap authority; preserve stop gate |
| Consumer version/release decoupling is understandable | Clean | Confirmed | Preserve decision table |

No stale observation overrides the current plan. The voice is counted for its
completed report; every retained finding is based on a fresh live-tree
recheck.

### Golden developer journey

```text
Choose
  generic
    -> backward-compatible warning-only citation behavior
  generic-strict-citation
    -> ready requires exact strict-v1 invariant

Discover
  GET /api/profiles/generic-strict-citation
    -> profile_id + version + existing manifest fields
    -> proof_schema is documented pin identity, not response data

Run
  REST: existing POST /api/runs profile_id
  CLI: existing run --profile generic-strict-citation --wait --result

Observe
  GET /api/runs/{run_id}
    -> existing status/failure_cause

Deliver
  GET /api/runs/{run_id}/result
    -> unchanged result and artifact shapes

Troubleshoot
  public: finalization/run_finalization_failed
  operator: exactly one closed strict_citation_* task-log code
  -> no same-run retry; correct input/config and start a new run if needed

Adopt
  consumer explicitly pins commit/release + profile ID/version + proof schema
  -> unrelated DRA versions do not force lockstep
```

### API and CLI ergonomics

The new profile is an existing-field opt-in, so the most discoverable and
least coupled interface is:

```json
{
  "query": "Research question",
  "profile_id": "generic-strict-citation",
  "scope": {}
}
```

and:

```bash
python tools/decision_research_agent_tool.py run \
  --profile generic-strict-citation \
  --query "Research question" \
  --wait \
  --result
```

The reference must not suggest `profile_version` or `proof_schema` as request
fields. Version remains server-owned; the proof schema is a documented
producer identity for intentional pinning. The profile GET proves current
server identity but does not enumerate choices. README and docs-index links
make the canonical reference the discoverability surface.

### Failure and troubleshooting ergonomics

REST remains intentionally stable:

- strict ordinary failure produces the existing status cause
  `finalization/run_finalization_failed`;
- the result endpoint returns the existing `409 run_failed`;
- retained Evidence remains on the run;
- no partial or ready artifact is exposed;
- no same-run semantic retry exists.

For operators, the existing task tracker receives the original re-raised
`StrictCitationFinalizationError` and logs its string. The implementation must
prove that this string is exactly one declared `strict_citation_*` code and
that no provider text, prompt, packet, excerpt, URL, response, path, or chained
exception is present. This supplies bounded root-category diagnosis without
creating a public contract field or new logging surface.

The canonical reference should group those closed categories into:

- initial artifact;
- source/target/packet preparation;
- model invocation;
- response validation;
- stale target/artifact rebuild;
- post-recompute invariant.

These are operator diagnostics, not result codes, retry instructions, source
quality claims, or consumer compatibility fields.

### Documentation information architecture

- `docs/reference/strict-citation-profile.md` is the one complete reference:
  choose, discover, run, interpret, troubleshoot, cost/data, pin, and
  non-claims.
- `README.md` and `README_CN.md` add one capability bullet, one shortest
  opt-in example/cross-link, and one known-boundary statement.
- `docs/README.md` indexes the canonical reference beside API and downstream
  contracts.
- `docs/reference/api-contract.md` records strict ready/failure semantics at
  the existing profile/run/result routes.
- `docs/AGENT_INTEGRATION.md` owns the copyable Tool Client golden path.
- `docs/reference/state-machines.md` owns zero-call, prepared one-call,
  failure, timeout, and cancellation transitions.
- `docs/decisions/framework-runtime-boundaries.md` owns direct-call,
  retry/fallback, tracing, and generic-budget separation.
- `docs/reference/downstream-consumer-contract.md` owns the intentional pin
  decision table and unchanged v0.1.6 fixture boundary.
- `CHANGELOG.md` records the implementation under `Unreleased`; it does not
  turn the change into a release.

Documentation tests must lock both English and Chinese public truth without
copying operator-only/private workflow context.

### Setup and verification ergonomics

The plan's environment gate is intentionally a stop gate:

- resolve one absolute Python 3.11 interpreter;
- require every exact pinned distribution;
- emit only `DRA_PINNED_ENVIRONMENT_REQUIRED` for missing or mismatched
  packages;
- install only the unchanged `constraints.txt` set during the one authorized
  bootstrap; do not add packages, weaken pins, or perform a second repair
  install.

Environment authority is now granted. Every Python command uses the same
task-local `DRA_PYTHON_BIN` and `PYTHON_DOTENV_DISABLED=1` after the exact gate
passes. Completion runs focused tests, the seven exact backend proof commands,
and full non-Docker pytest. Docker and frontend verification are not silently
skipped claims; they are unchanged and outside this backend-only feature's
authorized local scope.

### DX anti-footguns

- Do not present strict as the new default; literal `generic` remains default.
- Do not use `--result` without `--wait` in the Tool Client golden path.
- Do not claim a profile-list endpoint.
- Do not claim `proof_schema` is returned by manifest, status, result, or
  artifact payloads.
- Do not pass `profile_version` or `proof_schema` in the run request.
- Do not infer strict readiness from execution status alone; resolve the
  canonical result.
- Do not infer the operator-only closed code from the public result envelope.
- Do not expose raw provider/model/packet data to make troubleshooting easier.
- Do not retry the same terminal run; create a new run after correcting the
  relevant input/configuration.
- Do not treat provider-free call count as provider transport count or semantic
  quality.
- Do not re-pin an existing consumer merely because DRA's repository version
  changes.
- Do not describe `Unreleased` as v0.1.6 or as a published capability.

### Sequential DX tasks

- [ ] **DX-SC-1 (P1):** write the canonical choose/discover/run/interpret/
  troubleshoot/cost/pin/non-claims reference and targeted cross-links.
- [ ] **DX-SC-2 (P1):** prove every ordinary strict failure reaches the
  existing task tracker as exactly one safe closed diagnostic code while REST
  remains unchanged.
- [ ] **DX-SC-3 (P2):** add one provider-free Tool Client test for the existing
  strict `--profile ... --wait --result` golden path without changing CLI
  source.
- [ ] **DX-SC-4 (P2):** lock manifest discoverability limits and clarify that
  proof schema is documented identity, not an API field.
- [ ] **DX-SC-5 (P2):** publish the intentional consumer-pin decision table
  and unchanged v0.1.6/Release boundary.
- [ ] **DX-SC-6 (P2):** keep setup and verification copyable through one
  authorized interpreter and exact CI-parity commands.

### DX decision audit trail

| ID | Finding | Decision | Rejected alternative |
| --- | --- | --- | --- |
| DX-D1 | Strict opt-in was described but not a complete runnable journey | Add one canonical reference plus REST/CLI examples | Scatter partial examples across READMEs |
| DX-D2 | Existing profile route does not enumerate and manifest omits proof schema | State both limits and use docs index for discoverability | Add list endpoint or manifest field |
| DX-D3 | Public failure cause is intentionally coarse | Reuse one safe closed task-log code for operator diagnosis | Add public result/failure field or raw logs |
| DX-D4 | Existing Tool Client already supports profiles | Add a non-regression test and docs only | Add a strict-specific command |
| DX-D5 | Consumer upgrade concern needs an operational rule | Pin only when intentionally adopting a new producer tuple | Force lockstep on every DRA version |
| DX-D6 | Local environment was absent | Preserve explicit stop; final approval grants one bounded exact-pin bootstrap | Auto-install extras or use Python 3.13 |
| DX-D7 | CI and budget findings were repeated by the voice | Revalidate current plan and mark already closed | Duplicate tasks or claim stale text is current |

### Phase 4 completion summary

| Area | Result |
| --- | --- |
| Developer personas | REST, Tool Client, operator, consumer, maintainer |
| New required DX changes | 4 |
| Previously closed findings revalidated | CI parity; harness-budget separation |
| Discoverability | Exact manifest GET + docs index; no list endpoint claim |
| Golden path | Existing REST field and existing Tool Client `--profile` |
| Troubleshooting | Existing public cause + safe internal category; no new field |
| Consumer coupling | Intentional producer pin only; no automatic lockstep |
| Setup | Bounded bootstrap authority granted; exact gate pending execution |
| Release | `Unreleased` only; no version/tag/Release claim |

**Phase 4 complete.** All actionable DX findings are closed at plan level.
Cross-phase verification passed, and final approval later authorized
implementation subject to the exact environment gate.

## AutoPlan Cross-Phase Synthesis

### Final consistency audit

| Contract surface | Final plan state | Spec consistency |
| --- | --- | --- |
| Product direction | One opt-in `generic-strict-citation@1` profile | Exact |
| Generic/Talent | Existing graph and behavior unchanged | Exact |
| Model authority | IDs only; application owns URL bytes, rendering, citation, and terminal state | Exact |
| Call bound | Zero calls when already cited; otherwise one application `ainvoke` | Exact, with transport clarification |
| Stale writer | Pure preparation, immediately-pre-call fence, existing terminal CAS | Strengthens spec requirement |
| Target safety | Conservative bounded structural scanner; ambiguous Markdown rejected | Bounded implementation detail |
| Source safety | Current admission plus strict-local Markdown and artifact-sanitizer round-trip | Strengthens without global reinterpretation |
| Failure | Existing public cause; Evidence retained; no artifact; safe internal category only | Exact |
| Result authority | One snapshot requires exact v1, canonical artifact, and still-matching cited URL | Completes producer identity |
| Framework boundary | Same DeepAgents graph; direct post-graph LangChain call; no new dependency | Exact |
| Verification | Provider-free TDD, real lifecycle, seven CI proofs, full non-Docker pytest | Exact and CI-parity complete |
| Consumer | Intentional new producer pin only; immutable v0.1.6 fixture unchanged | Exact |
| Release | `Unreleased` implementation record only; no automatic version/tag/Release | Exact |

No phase changed the approved product direction. Engineering corrections
made the existing fence, producer identity, Markdown safety, and CI
requirements mechanically executable. DX corrections made the same contract
discoverable and diagnosable without introducing a new public surface.

### Cross-phase themes

1. **Application authority over framework/model output:** CEO, Engineering,
   and DX all preserve IDs-only model output, application-owned exact URLs,
   application-owned terminal state, and application-DB delivery authority.
2. **Bounded privacy-safe failure:** CEO required exception-context
   suppression; Engineering locked durable failure behavior; DX added one
   closed operator category without changing REST.
3. **Precise call accounting:** CEO separated application invocation from
   provider transport; Engineering separated post-graph correction from
   generic middleware; DX made both distinctions developer-visible.
4. **Consumer/release decoupling:** CEO retained the immutable v0.1.6
   boundary; DX turned intentional producer pinning into an operational
   decision table.
5. **Provider-free proof parity:** Engineering restored all seven CI proof
   commands; DX made the exact local completion path explicit.

### Decision summary

- Product-premise confirmation: 1, explicitly approved before CEO review.
- Auto-decided review decisions recorded in audit trails: 25.
- Taste choices requiring user selection: 0.
- User challenges: 0.
- Deferred work items: 0. Rejected or later-evidence-dependent scope remains
  in the plan's explicit NOT-in-scope sections; no repository backlog file is
  created.
- Execution precondition, not an unresolved plan decision: bounded environment
  authority is granted, and the exact-pinned Python 3.11 gate must pass.

### Final stop boundary

Final AutoPlan approval does not itself install packages. Before the first
RED, the executor must use the granted bounded bootstrap authority, satisfy
the closed exact-pin gate, inspect pinned LangChain source without a model
call, and stop if that source contradicts the locked direct-call contract.
Release remains outside implementation approval.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` via `/autoplan` | Scope and strategy | 1 | CLEAR | 5 bounded corrections applied; 0 product challenges |
| Codex Review | AutoPlan independent Codex voice | Independent second opinion | 2 attempts / 1 completed | CLEAR (degraded coverage) | Engineering voice found 4 issues, all applied; CEO attempt unavailable and not counted |
| Eng Review | `/plan-eng-review` via `/autoplan` | Architecture and tests | 1 | CLEAR | 6 issues closed; provider-free lifecycle and CI-parity plan complete |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | SKIPPED | No UI, interaction, or frontend scope |
| DX Review | `/plan-devex-review` via `/autoplan` | Developer experience gaps | 1 | CLEAR | 4 new gaps closed; 2 Engineering findings revalidated as already closed |

**CODEX:** The completed Engineering voice identified fence timing, producer version, Markdown structure, and CI parity; every retained finding is incorporated. The CEO Codex attempt produced no final verdict and is not counted.

**CROSS-MODEL:** No phase had two completed outside voices. Every retained outside finding was independently reproduced against the live repository; no unavailable stream is presented as consensus.

**VERDICT:** APPROVED — CEO + ENG + DX CLEARED; DESIGN SKIPPED. Implementation is authorized after the bounded task-local environment passes the exact-pin gate.

NO UNRESOLVED DECISIONS
