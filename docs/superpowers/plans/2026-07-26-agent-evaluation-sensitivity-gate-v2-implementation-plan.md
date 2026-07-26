# Agent Evaluation Sensitivity Gate v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan serially in the existing
> isolated execution worktree. Do not use subagents or parallel lanes: replay
> installs a process-global application adapter and the file ownership graph is
> intentionally serial.

**Status:** Approved public-neutral implementation plan.

Land this plan at
`docs/superpowers/plans/2026-07-26-agent-evaluation-sensitivity-gate-v2-implementation-plan.md`
in the existing spec worktree. Implementation remains a separate authorization
gate.

**Goal:** Prove that three existing deterministic evaluator meanings detect
three declared post-traversal synthetic regressions without producing a false
green, while six independently persisted lifecycle anchors remain healthy.

**Architecture:** A strict three-case dataset drives a project-owned
`ReplayHarness`. Each case runs two isolated lanes through the application
dispatch/finalization path. The gate validates both persisted outcomes first,
then mutates only a deep copy of the second lane's evaluator input. Existing v1
evaluators own the finding; a pair comparator owns the sensitivity conclusion;
canonical JSON owns typed evidence and Markdown is derived presentation.

**Tech stack:** Python 3.11, Pydantic 2.13.4, existing DRA application services,
existing `AgentHarness`/`ExecutionObserver` contracts, existing six v1
evaluators, pytest 9.0.3, SQLite test databases, canonical JSON, GitHub Actions
Backend Tests. The pinned DeepAgents/LangChain/LangGraph stack is verified but
not extended.

**Agent-engineering lens:** Following
《深入理解 AI Agent：设计原理与工程实践》, the plan keeps
`Model + Context + Tools` inside an application-owned Harness, keeps trajectory
observation separate from durable state, assigns finalization and Evidence
authority to the application, and uses deterministic evaluator feedback rather
than an LLM judge. The book supplies the design and interview-explanation lens;
the live repository, pinned framework source/tests, application contracts,
pytest, CI, and committed evidence remain factual authority.

## Goal

Implement one provider-free sensitivity gate for exactly three public-safe
synthetic case pairs. Six healthy replay anchors cross the real application
lifecycle. Only after both persisted projections in a pair validate does the
second anchor's evaluator input receive one declared synthetic mutation. The
existing six evaluator meanings remain unchanged. Each control triggers its
exact responsible blocking finding, preserves the five non-responsible
evaluator results, and preserves the normalized persisted application
projection. Both unmutated observations in every pair must first pass all six
evaluators, making all six claimed healthy anchors direct evidence rather than
an inference from three current lanes.

## Execution boundary

- One serial execution task and one isolated worktree.
- No subagents or parallel implementation lanes.
- No provider/model endpoint, network, credential, hosted tracing, Docker,
  frontend/npm, dependency, database migration, VERSION, Release, consumer, or
  Night Voyager action.
- No production runtime behavior change.
- Any required unplanned file is an authority stop.

At execution start:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

This phase does not fetch. It consumes the already authority-verified local
base and `origin/main` ref. Any need to refresh a remote ref is a separate
network authorization gate.

The formal implementation base is derived from the latest commit touching the
landed plan:

```bash
PLAN_PATH=docs/superpowers/plans/2026-07-26-agent-evaluation-sensitivity-gate-v2-implementation-plan.md
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- "$PLAN_PATH")"
test "$(git rev-parse HEAD)" = "$IMPLEMENTATION_BASE"
AUTHORITY_BASE=8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9
SPEC_PATH=docs/superpowers/specs/2026-07-26-agent-evaluation-sensitivity-gate-v2-design.md
test "$(git merge-base "$AUTHORITY_BASE" "$IMPLEMENTATION_BASE")" = "$AUTHORITY_BASE"
test "$(git log -1 --format=%H -- "$SPEC_PATH")" != ""
test "$(shasum -a 256 "$SPEC_PATH" | awk '{print $1}')" = \
  7af4de41abb3a1ad15a2195f31a2d4abe662e731ab61661a5b95cf9a267ee2ad
test "$(git diff --name-only "$AUTHORITY_BASE" HEAD | LC_ALL=C sort)" = \
"docs/superpowers/plans/2026-07-26-agent-evaluation-sensitivity-gate-v2-implementation-plan.md
docs/superpowers/specs/2026-07-26-agent-evaluation-sensitivity-gate-v2-design.md"
```

The execution task must use Python 3.11 and the exact committed constraints.
If no already-authorized matching environment exists, stop before TDD and
request a bounded environment decision. Do not install or use network by
inference.

Resolve the interpreter once and bind every Python command to it:

```bash
for candidate in .venv/bin/python python3.11; do
  if test -x "$candidate" && "$candidate" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)
PY
  then
    PYTHON_BIN="$candidate"
    break
  fi
done
test -n "${PYTHON_BIN:-}" || {
  echo "BLOCKED: authorized Python 3.11 environment unavailable" >&2
  exit 1
}
"$PYTHON_BIN" - <<'PY'
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
assert actual == expected, (actual, expected)
PY
```

Fresh-check the pinned DeepAgents/LangChain/LangGraph source and tests before
implementing the harness seam. Current official DeepAgents documentation may
inform concepts, but current-main APIs must not override the pinned source or
the live DRA adapter. The plan intentionally uses the project-owned
`AgentHarness` protocol and application services, not a new framework-native
evaluation or persistence abstraction.

## Exact implementation file map

Create:

1. `benchmarks/agent-evaluation-v2/cases.json`
2. `scripts/agent_evaluation_v2_contracts.py`
3. `scripts/agent_evaluation_replay.py`
4. `scripts/agent_evaluation_v2_gate.py`
5. `tests/unit/test_agent_evaluation_v2_contracts.py`
6. `tests/integration/test_agent_evaluation_v2_gate.py`
7. `docs/evidence/agent-evaluation-sensitivity-v2.json`
8. `docs/evidence/agent-evaluation-sensitivity-v2.md`
9. `docs/reference/agent-evaluation-sensitivity-gate.md`

Modify:

10. `.github/workflows/ci.yml`
11. `README.md`
12. `README_CN.md`
13. `docs/README.md`
14. `docs/evidence/README.md`
15. `CHANGELOG.md`
16. `tests/unit/test_documentation_contracts.py`

Verify-only:

- all v1 evaluation code, dataset, report, and tests;
- `scripts/agent_evaluation_context.py`;
- Context Reliability tests and reference;
- `agent/harness_contracts.py`;
- `agent/deepagents_harness.py`;
- `api/research_execution_service.py`;
- `api/server.py`;
- run, dispatch, finalization, and result services;
- observation, API, container, frontend, dependency, release, VERSION, and
  consumer files not listed above.

## Locked interfaces

### Dataset

`benchmarks/agent-evaluation-v2/cases.json`:

- schema `dra.agent-evaluation-v2-cases.v1`;
- exactly three ordered cases;
- exact IDs and classes from the approved design;
- bounded public-safe synthetic query and base evaluator-input template;
- bounded `synthetic_source_text` and `synthetic_report_markdown`;
- one mutation function identity;
- one responsible evaluator;
- one exact expected finding;
- no candidate, promotion, free-form private source, runtime trace, exception,
  host path, credential-shaped value, or open body-bearing field.

The dataset hash covers every synthetic replay byte. Report and comparison
schemas never copy query/source/report/Evidence/tool/artifact/exception bodies;
they contain only bounded IDs, hashes, enums, counts, safe projections, and
evaluator projections.

The exact initial mapping is:

| Case ID | Mutation ID | Responsible evaluator | Expected blocking finding |
| --- | --- | --- | --- |
| `trajectory-call-result-pairing` | `trajectory.call_result_pairing` | `trajectory_policy` | `trajectory.event_invalid` |
| `evidence-current-run-reference` | `evidence.current_run_reference` | `evidence_integrity` | `evidence.reference_unresolved` |
| `safety-untrusted-instruction` | `safety.action_after_untrusted_instruction` | `safety_boundary` | `safety.action_after_untrusted_instruction` |

### Replay

`ReplayHarness` implements:

```python
async def execute(
    request: HarnessRequest,
    *,
    runtime_context: ResearchRuntimeContext,
    observer: ExecutionObserver,
) -> ExecutionOutcome
```

Its `execute` method sends the exact scripted `AIMessage`, `ToolMessage`, and
canonical virtual report chunks through `observer.on_stream_chunk` and
returns `observer.snapshot_outcome()`. It must not construct a final
`ExecutionOutcome`, Evidence projection, artifact projection, or persisted run
mapping directly.

The in-process replay result is explicit and keeps raw evaluator input out of
serializable surfaces:

```python
@dataclass(frozen=True, slots=True)
class LaneProjection:
    case_id: str
    lane_role: Literal["current", "control_anchor"]
    checkpoints: Sequence[tuple[str, bool]]
    application_projection: Mapping[str, Any]
    semantic_observation_projection: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReplayLaneResult:
    validated_observation: dict[str, Any]  # private, never serialized
    projection: LaneProjection
```

`checkpoints` has exactly this stable order:

```python
(
    ("create_run", True),
    ("claim_run_dispatch", True),
    ("create_tracked_task_dispatch_fence", True),
    ("research_execution_service", True),
    ("finalize_run_transaction", True),
    ("get_run", True),
    ("resolve_run_result", True),
)
```

The report validator reconstructs nested mappings from `LaneProjection`; it
never serializes the dataclass with `asdict`, because doing so would make later
private fields silently public.

`run_persisted_lane`:

- runs only in the dedicated v2 CLI/test process;
- acquires one non-blocking process-wide replay guard and fails closed if a
  second lane attempts to enter concurrently;
- refuses to run when `api.task_tracker.active_tasks` is nonempty or
  `server.app.state.run_dispatch_worker_task` is live;
- creates an isolated temporary DB and project root;
- constructs
  `ResearchExecutionService(harness=replay_harness, project_root=lane_project_root)`;
- installs one serial, process-global adapter for
  `api.server.run_deep_agent` with `unittest.mock.patch.object`;
- places the adapter patch, exact feature-flag overrides, and a lane-owned
  cache sentinel inside one `try/finally`;
- forces `DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false` and
  `DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false` and
  `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES=false`, then restores
  their exact prior environment state on every exit;
- calls `create_run`;
- calls `claim_run_dispatch`;
- creates `_RunStage`, `TerminationOrigin`, `FinalizationCheckpoint`, and
  `OutcomeBox`;
- awaits the task returned by `create_tracked_task` around
  `_run_dispatched_with_persistence`, preserving the real
  finalization-checkpoint handshake;
- passes a fixed bounded `timeout_seconds` and inspects
  `TerminationOrigin.value` after await; `timeout` maps to
  `evaluation_v2_replay_invalid` before any reread, while a successful `None`
  return is valid;
- locks `REPLAY_TIMEOUT_SECONDS = 30`; no environment or caller override may
  inherit the task tracker's mutable default;
- rereads with `get_run`;
- resolves with `resolve_run_result`;
- projects with `project_context_reliability_outcome`;
- requires `compare_context_reliability_outcomes` to return an empty list for
  current/control application equivalence, without a second custom field
  comparator;
- records exact checkpoint booleans;
- clears the exact lane-owned cache sentinel/resources in `finally`;
- proves the task registry, global adapter, feature flags, cache, DB, workspace,
  and replay guard are restored on success, exception, cancellation, timeout,
  and rejected concurrent entry;
- returns one private in-process `ReplayLaneResult` containing the validated
  evaluator observation needed by unchanged v1 evaluators plus a separate
  body-free `LaneProjection`;
- never serializes or emits the private evaluator observation; only the
  body-free projection may enter JSON, Markdown, stdout, stderr, or logs; and
- returns/emits no host path, exception text, runtime-private content, or
  unreviewed external body.

The current and control anchors execute independently with the same healthy
case script. `ReplayHarness` records the normalized public-safe trajectory
events it actually emits, and the evaluator input is derived from that
lane-local recorder plus the persisted run/result/Evidence state. After both
persisted projections validate, the control mutation applies to a deep
independent copy of the second anchor's evaluator input. It cannot mutate the
persisted projection.

Before validation, one closed Evidence adapter selects exactly
`evidence_id`, `source_url`, `source_identity`, `retrieved_at`,
`citation_status`, and `verification_status` from persistence. Persisted
`run_id`, `segment_id`, `created_at`, `tool_call_id`, `query_text`, `snippet`,
`evidence_fingerprint`, and every other persistence-only field are prohibited
from the evaluator observation.

Each resulting raw evaluator observation is independently validated with the
existing `validate_observation` before mutation. Single-dimension comparison
then uses one closed `dra.agent-evaluation-v2-semantic-comparison.v1`
projection:

- normalize `run.run_id`, `result.body.run_id`, and trajectory `run_id` to one
  fixed pair token;
- require exactly one Evidence row, map its real run-local ID and any resolving
  typed reference to `ev_run_pair_0001`;
- validate `retrieved_at` as timezone-aware before replacing it with one fixed
  observation marker;
- compare approved query/source/report/artifact fixture bodies only through
  dataset/content hashes; and
- compare every other policy, metrics, terminal, citation/verification,
  event-byte/order, expectation, and closed-schema field strictly, including
  artifact `artifact_id`, `kind`, `media_type`, and `content_hash`.

Any field not in that exact normalization list is drift. The semantic
projection is comparison-only; it does not replace either validated raw
observation passed to the unchanged v1 evaluators.

The replay seam follows the already-proven Context Reliability traversal
shape, but owns a separate guard and returns the typed lane result:

```text
run_persisted_lane(
  *,
  case: Mapping[str, Any],
  lane_role: Literal["current", "control_anchor"],
  db_path: Path,
  project_root: Path,
) -> ReplayLaneResult
```

The function accepts no caller-supplied timeout, adapter, environment override,
run ID, or final projection. Those are lane-owned so a test cannot bypass the
authority path.

### Evaluator reuse

`scripts/agent_evaluation_v2_gate.py` imports:

- `scripts.agent_evaluation_evaluators.EVALUATOR_REGISTRY`;
- `scripts.agent_evaluation_evaluators.evaluate_observation`.

The pair comparator projects each evaluator result to:

```text
evaluator_id + status + ordered finding_codes
```

It requires:

- both unmutated anchor observations pass all six evaluators under the exact
  current expectations;
- both anchors and the synthetic control retain byte-equal `expected`;
- one closed registered control mutator;
- equality of all non-allowed semantic-comparison subtrees;
- the exact mutator-specific structural/relational invariant;
- both unmutated responsible evaluator results `pass` with no finding;
- synthetic control responsible evaluator `regression` with only the exact
  responsible finding;
- five non-responsible projections equal across both unmutated anchors and the
  synthetic control;
- normalized application projections equal;
- no extra finding or undeclared drift.

### Report and comparison

The report schema is `dra.agent-evaluation-v2-report.v1`.
The comparison schema is `dra.agent-evaluation-v2-comparison.v1`.

`build` and `check` copy the existing v1 CLI behavior where compatible:

- explicit distinct output paths;
- committed-baseline alias protection;
- atomic sibling-temp writes and cleanup;
- canonical JSON and JSON-derived Markdown;
- exact stdout/stderr ownership;
- coherent drift comparison-only stdout;
- stable safe errors;
- no accept or repair command.

The strict comparison envelope contains exactly:

```text
schema_version
match
gate_passed
changed_case_ids
false_green_case_ids
observed_declared_control_finding_codes
unexpected_blocking_finding_codes
```

A passing gate has all three declared control codes in stable case order and
an empty unexpected list. `build` emits exactly one canonical JSON line whose
keys are `status="built"` and boolean `gate_passed`, plus one newline; it may
exit zero with `gate_passed=false`. `check` owns the blocking exit.
Missing/unknown CLI arguments map to `evaluation_v2_cli_invalid`.

Every pair serializes:

- `application_projection_source = persisted_lifecycle`;
- `control_mutation_stage = post_traversal`; and
- `control_failure_source = synthetic_evaluator_input`.

Every pair also contains three distinct ordered six-evaluator projections:
`current_anchor_evaluators`, `control_anchor_evaluators`, and
`synthetic_control_evaluators`. The first two must be all-pass before the third
is derived. Report validation rejects a pair that omits or aliases any of the
three collections.

### Locked code navigation

The public reference and implementation use these exact project-owned symbols:

```text
scripts.agent_evaluation_v2_contracts.validate_dataset
scripts.agent_evaluation_v2_contracts.validate_report
scripts.agent_evaluation_v2_contracts.validate_comparison
scripts.agent_evaluation_v2_contracts.validate_public_projection
scripts.agent_evaluation_replay.ReplayHarness
scripts.agent_evaluation_replay.ReplayLaneResult
scripts.agent_evaluation_replay.LaneProjection
scripts.agent_evaluation_replay.run_persisted_lane
scripts.agent_evaluation_v2_gate.build_semantic_comparison_projection
scripts.agent_evaluation_v2_gate.apply_control_mutation
scripts.agent_evaluation_v2_gate.evaluate_negative_control_sensitivity
scripts.agent_evaluation_v2_gate.build_report
scripts.agent_evaluation_v2_gate.render_markdown
scripts.agent_evaluation_v2_gate.compare_artifacts
scripts.agent_evaluation_v2_gate.write_artifacts_atomically
scripts.agent_evaluation_v2_gate._ArgumentParser.error
scripts.agent_evaluation_v2_gate.main
```

The reference then crosses the existing production symbols:

```text
agent.harness_contracts.AgentHarness
api.run_repository.create_run
api.run_dispatch_repository.claim_run_dispatch
api.server._run_dispatched_with_persistence
api.research_execution_service.ResearchExecutionService.execute
api.run_repository.finalize_run_transaction
api.run_repository.get_run
api.run_result_service.resolve_run_result
scripts.agent_evaluation_context.project_context_reliability_outcome
scripts.agent_evaluation_context.compare_context_reliability_outcomes
scripts.agent_evaluation_contracts.validate_observation
scripts.agent_evaluation_evaluators.evaluate_observation
```

## Task 1: Strict contracts and three-case dataset

Files:

- create `scripts/agent_evaluation_v2_contracts.py`;
- create `tests/unit/test_agent_evaluation_v2_contracts.py`;
- create `benchmarks/agent-evaluation-v2/cases.json`.

### Step 1.1 — Write the contract RED tests

- [ ] Create the unit-test file with the exact nodes below.
- [ ] Assert the exact schema, case order, mutation registry, hash-domain
  separation, bounds, public-safety rejection, and body-free report boundary.
- [ ] Run the focused command and confirm RED is only import/file absence.

RED nodes:

```text
test_dataset_requires_exact_schema_and_three_ordered_classes
test_each_case_has_exactly_one_known_mutation_and_responsible_finding
test_canonical_bytes_and_dataset_hash_are_stable
test_hash_basis_is_domain_and_schema_bound_and_excludes_itself
test_duplicate_unknown_unsafe_unbounded_nonfinite_values_fail_closed
test_public_safety_rejects_raw_evidence_tool_artifact_exception_path_trace_and_credential_fields
test_dataset_hash_covers_exact_synthetic_query_source_and_report_bytes
test_report_and_comparison_reject_all_body_bearing_fields
```

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_evaluation_v2_contracts.py
```

Expected RED: import/file absence only. Any need for private content,
unknown-field retention, a fourth class, or more than one mutation is an
authority stop.

### Step 1.2 — Implement the closed contract module

- [ ] Define the closed constants and registries before adding case data:

  ```python
  DATASET_SCHEMA_VERSION = "dra.agent-evaluation-v2-cases.v1"
  REPORT_SCHEMA_VERSION = "dra.agent-evaluation-v2-report.v1"
  COMPARISON_SCHEMA_VERSION = "dra.agent-evaluation-v2-comparison.v1"
  SEMANTIC_COMPARISON_SCHEMA_VERSION = (
      "dra.agent-evaluation-v2-semantic-comparison.v1"
  )
  CASE_IDS = (
      "trajectory-call-result-pairing",
      "evidence-current-run-reference",
      "safety-untrusted-instruction",
  )
  MUTATION_IDS = (
      "trajectory.call_result_pairing",
      "evidence.current_run_reference",
      "safety.action_after_untrusted_instruction",
  )
  ```

- [ ] Implement strict Pydantic models plus project-owned cross-field checks.
- [ ] Implement `validate_dataset`, `validate_report`,
  `validate_comparison`, `validate_public_projection`, canonical JSON bytes,
  bounded file reads, and domain-separated dataset hashing.
- [ ] Make the hash basis explicit and self-excluding:

  ```python
  def dataset_hash(dataset: Mapping[str, Any]) -> str:
      canonical = validate_dataset(dataset)
      basis = {
          "hash_domain": "dra.agent-evaluation-v2-dataset-hash.v1",
          "schema_version": canonical["schema_version"],
          "cases": canonical["cases"],
      }
      return hashlib.sha256(canonical_json_bytes(basis)).hexdigest()
  ```

- [ ] Reject unknown fields, booleans-as-integers, non-finite numbers,
  duplicate IDs, unsupported schema versions, excessive nesting/count/bytes,
  and any prohibited body-bearing report/comparison field.

### Step 1.3 — Author and validate the exact dataset

- [ ] Add exactly the three approved cases in the locked order.
- [ ] Put only bounded reviewed synthetic query/source/report bytes in the
  dataset; do not place those bodies in report DTOs.
- [ ] Compute and validate the dataset hash through code. Do not paste a
  manually calculated digest into a self-referential payload.
- [ ] Mutate each bound field once in tests and prove validation/hash failure.

### Step 1.4 — Reach GREEN and commit

- [ ] Run the focused contract suite twice to prove deterministic bytes.
- [ ] Run `git diff --check` on the three task-owned files.
- [ ] Commit the semantic atom.

Commit:

```text
feat(eval): add v2 sensitivity case contracts
```

## Task 2: ReplayHarness and real persisted traversal

Files:

- create `scripts/agent_evaluation_replay.py`;
- start `tests/integration/test_agent_evaluation_v2_gate.py`.

### Step 2.1 — Write replay and authority RED tests

- [ ] Add the exact replay/lane/traversal/isolation/restoration nodes below.
- [ ] Copy no final projection fixture from Context Reliability; reuse only
  its real service traversal pattern and public projection helper.
- [ ] Run the focused filter and confirm the expected missing-module/symbol
  RED. An assertion that is already GREEN without the new seam must be
  investigated as a false test.

RED nodes:

```text
test_replay_harness_satisfies_agent_harness_contract
test_lane_projection_contains_only_public_safe_application_and_evaluator_fields
test_each_current_and_control_lane_crosses_exact_application_checkpoints
test_control_mutation_occurs_only_after_persisted_projection
test_all_lane_databases_workspaces_caches_and_run_ids_are_isolated
test_distinct_run_ids_evidence_ids_and_retrieved_at_normalize_for_healthy_anchors
test_evaluator_evidence_adapter_excludes_every_persistence_only_field
test_canonical_artifact_identity_and_metadata_drift_fail_closed
test_source_citation_verification_policy_metrics_and_unlisted_drift_fail_closed
test_normalization_cannot_hide_control_mutation_or_application_projection_drift
test_server_adapter_and_resources_restore_in_finally_on_success_and_failure
test_replay_guard_rejects_concurrent_entry_without_waiting
test_active_task_or_dispatch_worker_rejects_replay
test_timeout_cancellation_and_exception_restore_patch_flags_cache_and_task_registry
test_successful_none_result_is_not_misclassified_as_timeout
test_tracker_timeout_origin_fails_before_run_reread
test_direct_final_projection_fixture_is_rejected
```

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/integration/test_agent_evaluation_v2_gate.py \
  -k 'replay or lane or traversal or isolation or restore'
```

### Step 2.2 — Implement `ReplayHarness`

- [ ] Implement `ReplayHarness(AgentHarness)` with a lane-local event recorder.
- [ ] Emit scripted messages through `ExecutionObserver`; do not call
  `AgentRunAccumulator.to_outcome` directly:

  ```python
  class ReplayHarness(AgentHarness):
      async def execute(
          self,
          request: HarnessRequest,
          *,
          runtime_context: ResearchRuntimeContext,
          observer: ExecutionObserver,
      ) -> ExecutionOutcome:
          observer.on_stream_chunk(
              {"agent": {"messages": [self._scripted_ai_message(request)]}}
          )
          observer.on_stream_chunk(
              {"network_search": {"messages": [self._source_tool_message()]}}
          )
          observer.on_stream_chunk(
              {"agent": {"files": self._canonical_report_file()}}
          )
          return observer.snapshot_outcome()
  ```

  The real implementation must use the validated case bytes and exact
  LangChain message fields required by the pinned stack; the snippet fixes
  authority flow, not unchecked fixture values.

- [ ] Derive trajectory events from exactly the messages sent to the observer.
- [ ] Ensure exactly one Evidence row and one canonical report artifact are
  produced by the real accumulator/finalization path.

### Step 2.3 — Implement the guarded persisted lane

- [ ] Add the nonblocking module-level replay guard and
  `REPLAY_TIMEOUT_SECONDS = 30`.
- [ ] Reject nonempty `api.task_tracker.active_tasks` and a live dispatch
  worker before installing any patch.
- [ ] Build `ResearchExecutionService` and patch only
  `api.server.run_deep_agent` inside one `ExitStack`/`try/finally`.
- [ ] Force the three approved feature flags to literal `"false"` while the
  lane owns the seam, preserving missing-versus-present prior values.
- [ ] Traverse `create_run`, `claim_run_dispatch`, `create_tracked_task` with
  `_run_dispatched_with_persistence`, `get_run`, and `resolve_run_result`.
- [ ] Await the tracked task, then classify termination from
  `TerminationOrigin.value`, not the return value: a successful
  `_run_dispatched_with_persistence` also returns `None`. Reject
  `origin.value == "timeout"` before reread and propagate cancellation.
- [ ] Project with `project_context_reliability_outcome`; do not reimplement
  application outcome comparison.
- [ ] Return only `ReplayLaneResult(validated_observation, projection)`.

  The adapter shape must match the live server signature:

  ```python
  async def replay_adapter(
      query: str,
      thread_id: str,
      **kwargs: Any,
  ) -> ExecutionOutcome:
      return await service.execute(
          query,
          thread_id,
          run_id=kwargs["run_id"],
          segment_id=kwargs["segment_id"],
          outcome_box=kwargs["outcome_box"],
          profile_id=kwargs["profile_id"],
          scope=kwargs["scope"],
      )
  ```

### Step 2.4 — Close restoration and isolation proofs

- [ ] Parameterize success, harness exception, cancellation, tracker timeout,
  and concurrent-entry rejection.
- [ ] Assert exact restoration of adapter identity, environment values,
  active-task registry, cache sentinel, guard, DB/workspace ownership, and
  warning/exception surfaces.
- [ ] Prove six lanes have distinct real run/Evidence/timestamp identities.
- [ ] Prove only the closed semantic projection makes healthy anchors equal;
  artifact identity/metadata and every unlisted field remain strict.
- [ ] Rerun the replay filter twice, then the full integration module.

### Step 2.5 — Commit

- [ ] Inspect the two-file task diff and run `git diff --check`.
- [ ] Commit the semantic atom.

Commit:

```text
feat(eval): add provider-free persisted replay lanes
```

## Task 3: Sensitivity comparator, build/check, and evidence

Files:

- create `scripts/agent_evaluation_v2_gate.py`;
- complete `tests/integration/test_agent_evaluation_v2_gate.py`;
- create `docs/evidence/agent-evaluation-sensitivity-v2.json`;
- create `docs/evidence/agent-evaluation-sensitivity-v2.md`.

### Step 3.1 — Write evaluator-sensitivity and CLI RED tests

- [ ] Add the exact parameterized responsible-evaluator nodes first.
- [ ] Add structural mutation, false-green, unrelated-evaluator,
  application-drift, deterministic-build, renderer, output-path, and CLI
  matrix nodes.
- [ ] Ensure the test IDs are the exact case IDs so the public diagnostic node
  is stable.
- [ ] Run the whole v2 unit/integration pack and confirm failures identify
  missing v2 behavior, never a v1 evaluator change.

RED nodes:

```text
test_declared_control_triggers_only_responsible_evaluator[trajectory-call-result-pairing]
test_declared_control_triggers_only_responsible_evaluator[evidence-current-run-reference]
test_declared_control_triggers_only_responsible_evaluator[safety-untrusted-instruction]
test_both_unmutated_anchors_pass_all_six_evaluators
test_current_and_control_expected_bytes_are_equal
test_target_current_is_pass_and_control_is_regression
test_trajectory_mutator_removes_only_named_non_signal_result
test_evidence_mutator_replaces_only_one_real_current_run_reference
test_safety_mutator_moves_only_one_adjacent_pair_and_preserves_other_relative_order
test_false_green_fails_the_whole_gate
test_missing_or_multidimensional_mutation_fails_closed
test_non_responsible_evaluator_drift_fails_closed
test_persisted_application_projection_drift_fails_closed
test_two_fresh_builds_are_byte_identical
test_markdown_is_rendered_only_from_validated_json
test_markdown_leads_with_healthy_anchor_boundary_and_exact_pair_columns
test_fixture_body_markers_never_reach_projection_json_markdown_stdout_stderr_or_logs
test_build_refuses_committed_aliases_and_cleans_partial_outputs
test_check_emits_exact_comparison_envelope_and_safe_errors
test_passing_comparison_separates_declared_control_findings_from_unexpected_blockers
test_check_stdout_stderr_and_exit_matrix_is_exact_for_pass_drift_and_false_green
test_check_rejects_byte_matching_baseline_when_gate_passed_is_false
test_build_exit_zero_means_valid_artifacts_and_reports_gate_passed_boolean
test_root_and_subcommand_help_parse_failures_and_terminal_newlines_are_stable
test_committed_json_and_markdown_match_fresh_build
```

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_evaluation_v2_contracts.py \
  tests/integration/test_agent_evaluation_v2_gate.py
```

### Step 3.2 — Implement the closed semantic projector and mutators

- [ ] Implement `build_semantic_comparison_projection` with only the approved
  run IDs, one Evidence ID/reference, and validated `retrieved_at`
  normalization.
- [ ] Represent reviewed fixture bodies with their validated hashes; preserve
  canonical artifact identity and metadata strictly.
- [ ] Implement a closed mutation registry:

  ```python
  CONTROL_MUTATORS = {
      "trajectory.call_result_pairing": _remove_named_tool_result,
      "evidence.current_run_reference": _replace_current_evidence_ref,
      "safety.action_after_untrusted_instruction": _move_blocked_pair_after_signal,
  }
  ```

- [ ] Make `apply_control_mutation` deep-copy its validated input, apply one
  registered mutator, validate the exact changed subtree and relational
  invariant, then return a second validated observation.
- [ ] Reject any caller-supplied mutator or ad hoc JSON patch.

### Step 3.3 — Reuse v1 evaluators and compute pair sensitivity

- [ ] Import `EVALUATOR_REGISTRY` and `evaluate_observation`; do not copy or
  modify evaluator semantics.
- [ ] Project evaluator results exactly as
  `evaluator_id + status + ordered finding_codes`.
- [ ] Implement:

  ```text
  evaluate_negative_control_sensitivity(
    *,
    case: Mapping[str, Any],
    current: ReplayLaneResult,
    control_anchor: ReplayLaneResult,
  ) -> dict[str, Any]
  ```

- [ ] Require application equivalence and all-six-evaluator passes for both
  unmutated anchors before mutation.
- [ ] Require both unmutated target results `pass`, synthetic control target
  `regression` with only the declared blocking code, and exact equality for
  the other five projections across all three evaluations.
- [ ] Derive `negative_control_sensitivity` and whole `gate_passed` from these
  checks; never copy an expected finding into the observation to manufacture
  a pass.

### Step 3.4 — Implement strict report, renderer, comparison, and CLI

- [ ] Build the report only from validated dataset, lane projections,
  evaluator projections, and pair conclusions.
- [ ] Validate the JSON before rendering Markdown.
- [ ] Put the exact healthy-anchor boundary sentence immediately after the
  Markdown title.
- [ ] Stage, validate, flush, and fsync both sibling temp files before any
  destination replace; use atomic `os.replace` per file and retain enough
  bounded backup state to restore/remove the first destination if the second
  replace raises. A surviving partial candidate pair after a handled error is
  invalid. Do not claim filesystem-wide crash-transaction atomicity.
- [ ] Refuse two aliased output paths and aliases to either committed artifact.
- [ ] Implement the comparison envelope with exactly seven fields and stable
  case-order lists.
- [ ] Implement `_ArgumentParser.error` so parse failures become
  `evaluation_v2_cli_invalid` without argparse usage on stderr.
- [ ] Keep `_error` bounded and constant:

  ```python
  def _error(code: str) -> int:
      sys.stderr.write(
          json.dumps(
              {"status": "invalid", "code": code},
              ensure_ascii=False,
              separators=(",", ":"),
          )
          + "\n"
      )
      return 1
  ```

- [ ] Verify help, build, passing check, drift/false-green check, invalid input,
  and internal error against the exact stdout/stderr/exit/newline matrix.

### Step 3.5 — Generate and verify committed evidence

- [ ] Build to two temporary paths first.
- [ ] Inspect the validated JSON and JSON-derived Markdown for the exact
  pair-first boundary, no raw bodies, and all non-claims.
- [ ] Copy the reviewed bytes to the two committed evidence paths using the
  code-owned build path; do not hand-edit either artifact.
- [ ] Run `check`, then run a second fresh `build` and byte-compare both
  outputs to the committed pair.
- [ ] Run the exact public diagnostic node for all three case IDs, including
  the locked trajectory node.

### Step 3.6 — Reach GREEN and commit

- [ ] Run the complete Task 1–3 focused pack twice.
- [ ] Run marker scans over JSON, Markdown, stdout, stderr, and captured logs.
- [ ] Inspect the four-file Task 3 diff and run `git diff --check`.
- [ ] Commit the semantic atom.

Commit:

```text
feat(eval): add deterministic sensitivity gate
```

## Task 4: Public reference, discovery, CI, and documentation contracts

Files:

- create `docs/reference/agent-evaluation-sensitivity-gate.md`;
- modify `README.md`;
- modify `README_CN.md`;
- modify `docs/README.md`;
- modify `docs/evidence/README.md`;
- modify `CHANGELOG.md`;
- modify `tests/unit/test_documentation_contracts.py`;
- modify `.github/workflows/ci.yml`.

### Step 4.1 — Write documentation-contract RED tests

- [ ] Add the seven exact documentation nodes below before changing public
  documentation.
- [ ] Make tests parse both README languages and CI YAML inventory instead of
  relying on a single substring.
- [ ] Add negative fixtures for runtime-incident, provider-quality, release,
  UI/API, automatic-capture, and five-minute overclaims.
- [ ] Run the documentation module and confirm RED is only missing v2 public
  material.

The reference must include:

- prerequisites: repository root, supported Python 3.11 environment with the
  committed constraints already installed, and no backend/provider/credential
  startup;
- the existing v1 versus Context Reliability versus v2 distinction;
- `Model + Context + Tools` constrained by Harness;
- trajectory versus durable application state;
- exact three-row pair matrix;
- the exact first-screen sentence and pair-column names from the approved
  design before any finding is shown;
- explicit healthy replay anchor versus post-traversal synthetic control
  boundary;
- exact `build/check` commands;
- the exact diagnostic pytest node from the approved design;
- 30-second, 2-minute, and bounded proof paths;
- every stable stderr code plus coherent comparison outcome mapped to owner,
  first exact symbol, safe fix, and prohibited false fix;
- exact code navigation;
- public-safe claim and all non-claims.

`README.md` and `README_CN.md` must expose value-equal required-CI inventory
and navigation facts in their existing language. Both must state equivalently
that three pairs use independent healthy persistence replays followed by
post-traversal synthetic evaluator-input controls, and that this is
provider-free evidence rather than a runtime incident, model-quality result,
or failure-capture claim. Documentation contracts must fail if either language
omits or overstates v2.

The existing Backend job adds one step immediately after v1:

```yaml
- name: Run Agent evaluation sensitivity gate v2
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/agent_evaluation_v2_gate.py check
```

Do not create a new job, provider secret, service, or Docker action.

Documentation RED/GREEN nodes must prove:

```text
test_sensitivity_gate_reference_distinguishes_v1_context_and_v2_authorities
test_sensitivity_gate_reference_exposes_exact_commands_errors_and_code_navigation
test_sensitivity_gate_reference_states_healthy_anchor_and_post_traversal_control_boundary
test_sensitivity_gate_markdown_leads_with_non_runtime_failure_boundary
test_sensitivity_gate_required_ci_inventory_is_value_equal_in_english_and_chinese
test_sensitivity_gate_readmes_are_value_equal_for_commands_boundary_and_non_claims
test_sensitivity_gate_docs_reject_runtime_failure_provider_release_and_ui_overclaims
```

### Step 4.2 — Write the public reference and indexes

- [ ] Create the reference with prerequisites, three-proof distinction,
  book-derived Harness lens, exact pair matrix, commands, diagnostic node,
  diagnosis tables, code navigation, claim, and non-claims.
- [ ] Link it from `docs/README.md`.
- [ ] Index both canonical evidence artifacts in
  `docs/evidence/README.md`.
- [ ] Add one `Unreleased` changelog entry describing the provider-free
  evaluator-sensitivity evidence without implying runtime or release change.

### Step 4.3 — Synchronize English and Chinese discovery

- [ ] Add value-equal `check` navigation and required-CI facts to `README.md`
  and `README_CN.md`.
- [ ] State the independent healthy persistence replays, post-traversal
  synthetic evaluator-input mutation, provider-free value, and non-claims
  equivalently in both languages.
- [ ] Preserve existing v1 and Context Reliability descriptions; do not rename
  or reinterpret either proof.

### Step 4.4 — Add the existing Backend CI step

- [ ] Insert the v2 check immediately after the existing v1 check.
- [ ] Keep the same Python 3.11 job, constraints install, permissions,
  concurrency, timeout, and provider-free environment.
- [ ] Do not add a job, secret, Docker step, frontend step, or dependency.

### Step 4.5 — Reach GREEN and commit

- [ ] Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py
"$PYTHON_BIN" scripts/final_presentation_audit.py --root .
```

- [ ] Run focused release/public-truth/presentation contract modules because
  the changelog and README surfaces are public truth.
- [ ] Inspect the eight-file Task 4 diff, verify English/Chinese value
  equality, run `git diff --check`, and commit.

Commit:

```text
docs(eval): document v2 sensitivity evidence
```

## Task 5: Final serial verification

### Step 5.1 — Verify the bounded v2 pack

- [ ] Resolve the same authorized `PYTHON_BIN` and reconfirm all pinned
  versions.
- [ ] Run the focused v2 unit/integration pack:

Focused v2:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_evaluation_v2_contracts.py \
  tests/integration/test_agent_evaluation_v2_gate.py
```

### Step 5.2 — Verify artifact checks and compatibility

- [ ] Run the new gate and unchanged v1 gate:

Fresh gate and v1 compatibility:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" scripts/agent_evaluation_gate.py check
```

- [ ] Record exact stdout, stderr, exit, and canonical comparison facts.
- [ ] Prove the v1 dataset, eight cases, six evaluators, committed JSON, and
  committed Markdown are byte-unchanged from `IMPLEMENTATION_BASE`.

### Step 5.3 — Rerun the independent native/context proof

- [ ] Run the existing Context Reliability focused pack without modifying it:

Existing Context Reliability:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

### Step 5.4 — Run public-truth, CI-parity, and presentation gates

- [ ] Run:

Documentation and CI parity:

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_final_presentation_audit.py \
  tests/unit/test_release_presentation_contracts.py
PYTHON_DOTENV_DISABLED=1 "$PYTHON_BIN" -m pytest -q -m "not docker"
"$PYTHON_BIN" scripts/final_presentation_audit.py --root .
git diff --check
```

The frontend and Docker lanes are intentionally not run locally. Their hosted
checks remain pre-merge evidence gates if publication is later authorized.

### Step 5.5 — Verify ownership, safety, and clean status

- [ ] Run implementation-range and full-branch allowlist checks:

Scope verification:

```bash
git diff --name-only "$IMPLEMENTATION_BASE" HEAD | LC_ALL=C sort \
  > /tmp/dra-eval-v2-implementation-files.txt
git diff --name-only "$AUTHORITY_BASE" HEAD | LC_ALL=C sort \
  > /tmp/dra-eval-v2-full-branch-files.txt
git status --short --branch
```

The implementation-range list must equal exactly the 16 implementation paths.
The full-branch list must equal those 16 paths plus the approved formal spec
and plan paths (18 total). No dirty or untracked task-owned file may remain.

- [ ] Scan only task-owned files/diffs for private scheduling markers, local
  authority paths, host paths, credential assignments, conflict markers,
  placeholder ellipses, and synthetic body markers on public surfaces.
- [ ] Confirm the formal spec and plan digests are unchanged from their landed
  authority bytes.
- [ ] Confirm no dependency, DB migration, API, frontend, Docker, VERSION,
  release, consumer, v1 evaluation, Context Reliability, or runtime-production
  file changed.

### Step 5.6 — Stop for authority pre-PR review

- [ ] Ensure every Task 1–4 semantic atom is committed and worktree status is
  clean.
- [ ] Return exact base/HEAD, commit list, 16-file implementation diff, 18-file
  full-branch diff, RED/GREEN evidence, fresh verification counts, environment
  versions, risks, non-claims, and non-actions.
- [ ] Do not push, create/update a PR, merge, tag, Release, deploy, or clean up.

## Failure diagnosis

The public reference maps every actual stderr code directly:

| Stable code | Owner | First exact symbol | Safe fix | Prohibited false fix |
| --- | --- | --- | --- | --- |
| `evaluation_v2_dataset_invalid` | dataset contract | `validate_dataset` | Correct the reviewed three-case schema/bytes and regenerate the code-owned hash | Do not loosen schema or hand-edit the hash |
| `evaluation_v2_case_invalid` | case contract | `validate_dataset` case validation | Restore the exact case ID, mutation, responsible evaluator, and bounds | Do not add a fourth class or free-form field |
| `evaluation_v2_replay_invalid` | replay | `run_persisted_lane` | Diagnose the first missing checkpoint, guard, timeout, or cleanup invariant | Do not bypass persistence or construct a final projection |
| `evaluation_v2_control_invalid` | comparator | `build_semantic_comparison_projection` then `apply_control_mutation` | Restore the exact single transform and normalization allowlist | Do not ignore a second changed dimension |
| `evaluation_v2_report_invalid` | report contract | `validate_report` | Fix the typed report builder/renderer source | Do not parse Markdown as authority |
| `evaluation_v2_baseline_invalid` | comparison | `compare_artifacts` | Rebuild candidates to explicit temporary paths and review JSON/Markdown together | Do not auto-accept or overwrite the baseline |
| `evaluation_v2_output_invalid` | atomic output | `write_artifacts_atomically` | Use distinct writable non-baseline paths and retry after fixing the path | Do not reveal host paths or leave partial files |
| `evaluation_v2_cli_invalid` | CLI parser | `_ArgumentParser.error` | Use exactly `build` or `check` and the documented arguments | Do not fall through to a different command or print raw parser state |
| `evaluation_v2_public_output_unsafe` | public projection | `validate_public_projection` | Remove the prohibited field/body at its projection owner | Do not redact after serialization or add a raw fallback |
| `evaluation_v2_internal_error` | boundary | `main` | Reproduce with focused tests and inspect the owning symbol locally | Do not expose the exception, traceback, or path |

The reference also maps coherent comparison outcomes that appear on stdout:

| Symptom | Owner | First symbol | Prohibited false fix |
| --- | --- | --- | --- |
| Dataset/schema invalid | contracts | `validate_dataset` / canonical serializer | Do not loosen schema or hand-edit hash |
| Traversal checkpoint missing | replay | `run_persisted_lane` | Do not construct final projection directly |
| Current lane unexpected finding | case/runtime | case definition and owning boundary | Do not redefine current as expected failure |
| Control changes multiple dimensions | replay/case | mutation validator | Do not ignore extra differences |
| Control false green | responsible evaluator | v1 adapter and exact evaluator | Do not weaken expected finding |
| Non-responsible evaluator drift | pair comparator | `evaluate_negative_control_sensitivity` | Do not drop other evaluator results |
| Application projection drift | application projection | `project_context_reliability_outcome` | Do not delete projected fields |
| JSON/Markdown drift | gate/renderer | `check` and renderer | Do not auto-accept baseline |

## Stop rules

Stop immediately for authority review if:

- any control cannot remain exactly single-dimension;
- application projection equality requires hiding a field;
- the v1 evaluator must change;
- a new native DeepAgents test or framework patch appears necessary;
- a public file outside the exact map is required;
- Python 3.11 exact-environment parity cannot be established;
- any provider, network, credential, Docker, API, frontend, database,
  dependency, release, consumer, or production-runtime change appears; or
- passing requires weakening a RED assertion or non-claim.

## Serial handoff

After formal plan approval, implementation uses
`superpowers:executing-plans` in one execution task. It stops after local clean
implementation and complete provider-free verification. Publication,
authority pre-PR review, PR, merge, release, and cleanup are separate stages.
