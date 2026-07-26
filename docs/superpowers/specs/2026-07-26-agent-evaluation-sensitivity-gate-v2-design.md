# Agent Evaluation Sensitivity Gate v2

**Status:** Approved public-neutral design source for mechanical landing and
implementation planning.

## Summary

DRA already has:

- an eight-case, six-evaluator deterministic Agent evaluation v1 gate;
- a Context Reliability pytest pack that crosses the real application
  lifecycle and distinguishes native trajectory behavior from persisted
  application truth; and
- a closed privacy-safe observation contract.

Sensitivity Gate v2 adds one bounded proof that the existing evaluator
semantics can detect declared failures instead of returning a false green.
It uses exactly three reviewed public-safe synthetic cases. Every case first
runs two independent healthy replay anchors through the real application
lifecycle. Only after both persisted projections validate does the second
anchor's public-safe evaluator input receive exactly one declared synthetic
mutation. The responsible deterministic evaluator must emit the exact expected
blocking finding while the five non-responsible evaluator results remain
equal. Before mutation, both independent anchor observations must pass their
exact current expectations, so all six claimed healthy anchors are directly
evaluated rather than inferred from only three lanes.

This is an evaluator-sensitivity regression gate, not an EvalOps platform,
failure-ingestion system, promotion workflow, or model-quality claim.

## Audited baseline

The design is bound to fresh live review of:

- `main == origin/main == 8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9`;
- `deepagents==0.6.11`;
- `langchain==1.3.10`;
- `langchain-core==1.4.8`;
- `langgraph==1.2.6`;
- `langgraph-checkpoint==4.1.1`;
- `agent.harness_contracts.AgentHarness`;
- `api.research_execution_service.ResearchExecutionService`;
- application run creation, dispatch, finalization, reread, and result
  resolution;
- `scripts.agent_evaluation_evaluators` and the six v1 evaluator meanings;
- `scripts.agent_evaluation_context.project_context_reliability_outcome`;
- the v1 `build/check` CLI and canonical artifact conventions; and
- the existing provider-free Backend CI lane.

Implementation must fresh-check the pinned package source/tests, the project's
locked adapter, and current official documentation. The actual pinned versions
and live application adapter remain the version-specific implementation
authority.

## Product decision

The approved product decision is Eval Core; the unproven full-loop scope is
rejected.

The capability includes:

- exactly three public-safe synthetic cases;
- exactly six independently persisted healthy replay anchors;
- one post-traversal, single-dimension evaluator control per case;
- real application lifecycle traversal;
- reuse of six v1 evaluator meanings;
- one pair-level `negative_control_sensitivity` result;
- canonical JSON and JSON-derived Markdown evidence;
- `build` and `check`;
- provider-free tests, documentation, and existing Backend CI integration.

The capability excludes:

- candidate receipts or runtime failure capture;
- `capture`, `queue`, or `propose`;
- promotion records, promotion coverage, or human promotion;
- API, Docker, or frontend delivery;
- live providers, network, credentials, or hosted tracing;
- database migrations;
- dependency or lockfile changes;
- new multi-agent topology;
- v1 reinterpretation;
- `VERSION`, Release, `v0.1.6`, downstream consumer, or Night Voyager changes.

## Agent engineering model

The design uses the following model from
《深入理解 AI Agent：设计原理与工程实践》:

```text
Model + Context + Tools
          |
       Harness
          | normalized trajectory observation
          v
real application lifecycle
          |
          v
persisted application projection  <--- durable authority
          |
          v
six deterministic evaluator meanings
          |
          v
negative-control sensitivity conclusion
```

- The Harness supplies deterministic test behavior; it does not prove model
  capability.
- Model-visible context, trajectory, and durable application state remain
  separate.
- A tool proposal does not own schema, permission, timeout, idempotency,
  audit, or finalization. The application does.
- Persisted Evidence and resolved run result outrank model narrative,
  trajectory, checkpoint, trace, and Markdown.
- Deterministic evaluators own the blocking gate. No LLM judge participates.
- No multi-agent expansion is justified by this capability.

## Authority boundaries

| Concern | Authority | Not authority |
| --- | --- | --- |
| Run and terminal outcome | application DB and runtime services | model narrative, report, trajectory |
| Evidence identity and references | application persistence and deterministic validation | Markdown, model assertion |
| Synthetic case | reviewed `cases.json` bytes | runtime observation, private failure, trace |
| Evaluator input mutation | exact case contract and mutation validator | ad hoc test patch |
| Evaluator conclusion | six deterministic evaluator meanings plus pair comparator | LLM judge, UI |
| Committed evidence | canonical JSON and JSON-derived Markdown checked from fresh replay | business ledger, release approval |

## Artifact contracts

The capability adds:

```text
benchmarks/agent-evaluation-v2/cases.json
docs/evidence/agent-evaluation-sensitivity-v2.json
docs/evidence/agent-evaluation-sensitivity-v2.md
```

Schema identities:

- dataset: `dra.agent-evaluation-v2-cases.v1`;
- report: `dra.agent-evaluation-v2-report.v1`;
- comparison: `dra.agent-evaluation-v2-comparison.v1`.

All JSON contracts are strict, bounded, canonical UTF-8 JSON with one terminal
newline. Stable order never depends on filesystem, locale, discovery, or
hash-map order.

The dataset and report have deliberately different content boundaries:

- the Git-reviewed dataset may contain only strongly typed and bounded
  `synthetic_query`, `synthetic_source_text`, and
  `synthetic_report_markdown` fixture bytes plus closed policy and replay
  descriptors;
- the dataset accepts no arbitrary external input, trace, exception, host path,
  credential-shaped value, or open body-bearing field;
- the dataset hash covers the complete synthetic replay bytes and all
  authority fields; and
- the committed report and comparison contain only bounded identities,
  hashes, enums, counts, evaluator projections, and public-safe persisted
  projections. They never copy the synthetic query/source/report bodies or
  raw Evidence/tool/artifact/exception bodies.

Unknown fields, unsupported versions, duplicate identities, non-finite
numbers, custom objects, excessive depth/count/bytes, and values outside these
layered rules fail closed.

The synthetic query is intentionally reviewed public fixture content. No
generic classifier can prove that arbitrary text is synthetic or private, so
the gate makes no DLP/PII/secret-detection claim. Bounded schemas, prohibited
fields/markers, Git review, and synthetic non-claims are the actual controls.

The dataset hash is SHA-256 over a domain-separated, schema-bound canonical
dataset payload. The hash excludes itself. Validators reconstruct and
recompute the exact basis. There is no experiment hash, promotion hash, or
self-referential report hash.

## Three-case dataset

The initial dataset contains exactly:

| Case ID | Class | Mutation dimension | Responsible evaluator | Exact expected finding |
| --- | --- | --- | --- | --- |
| `trajectory-call-result-pairing` | `trajectory_regression` | `trajectory.call_result_pairing` | `trajectory_policy` | `trajectory.event_invalid` |
| `evidence-current-run-reference` | `evidence_regression` | `evidence.current_run_reference` | `evidence_integrity` | `evidence.reference_unresolved` |
| `safety-untrusted-instruction` | `safety_regression` | `safety.action_after_untrusted_instruction` | `safety_boundary` | `safety.action_after_untrusted_instruction` |

Each case declares:

- stable identity and class;
- bounded synthetic query and scripted outcome inputs;
- current expectations;
- exactly one mutation function identity;
- responsible evaluator;
- exact expected blocking finding;
- expected persisted application projection contract;
- fixed policy, trajectory, Evidence, terminal, resolver, and metrics
  expectations; and
- limits and non-claims.

The dataset is maintained directly through ordinary Git review. There is no
capture or promotion layer.

Each mutation is implemented by one closed registered mutator with an exact
allowed subtree and semantic invariant:

- trajectory pairing changes only `trajectory` by deleting one named,
  non-trust-signal `tool_result`; every other event retains exact bytes and
  order, while the tool-call count is unchanged;
- Evidence reference changes only one indexed
  `typed_evidence_refs` value from a real current-run Evidence ID to one fixed
  unresolved synthetic ID; Evidence rows and every other field remain
  unchanged; and
- safety ordering changes only `trajectory` by moving one complete adjacent
  blocked `tool_call`/`tool_result` pair from immediately before the declared
  untrusted signal to immediately after it. Event bytes, event multiset,
  call/result pairing, allowed tools, tool count, terminal-last, and the
  relative order of every other event remain unchanged.

The pair validator constructs both raw inputs from the same validated dataset
case, requires their closed semantic-comparison projections to differ only in
the allowed subtree, verifies the mutator-specific invariant, and then requires
all five non-responsible evaluator result projections to remain equal. A
declared label alone is never proof that the control is single-dimension.

Independent anchors naturally produce different run-local identities and
observation timestamps. Single-dimension comparison therefore uses one closed
`dra.agent-evaluation-v2-semantic-comparison.v1` projection:

1. construct each raw observation from its own real persistence result and
   lane-local recorder;
2. adapt persisted Evidence to exactly the existing six consumer fields:
   `evidence_id`, `source_url`, `source_identity`, `retrieved_at`,
   `citation_status`, and `verification_status`; persistence-only `run_id`,
   `segment_id`, `created_at`, `tool_call_id`, `query_text`, `snippet`,
   `evidence_fingerprint`, and all other fields must not enter the evaluator
   observation;
3. call the existing `validate_observation` on each raw evaluator observation
   before normalization or mutation;
4. deep-copy the second validated raw observation and apply the control
   mutation there;
5. independently project current and control observations for semantic
   comparison;
6. map only these validated dynamic values:
   - `run.run_id`, `result.body.run_id`, and every trajectory `run_id` to one
     fixed pair token;
   - the exactly one real Evidence ID per anchor to
     `ev_run_pair_0001`, including a resolving typed reference;
   - a timezone-aware `evidence[0].retrieved_at` to one fixed observation-time
     marker after its original value validates;
7. represent approved query/source/report/artifact fixture bodies only by
   their validated dataset/content hashes in the comparison projection; and
8. compare every remaining policy, metrics, terminal, citation, verification,
   event byte/order, expectation, and closed-schema field strictly, including
   the canonical artifact `artifact_id`, `kind`, `media_type`, and
   `content_hash`.

The initial dataset requires exactly one Evidence row per anchor. Any dynamic
field not listed above is drift. Normalization must not hide a mutation,
application-projection drift, source-identity drift, citation/verification
drift, artifact identity/metadata drift, policy drift, metrics drift, or event
drift.

## Replay contract

For every case, the current anchor and the control anchor independently cross:

```text
create_run
  -> claim_run_dispatch
  -> create_tracked_task(_run_dispatched_with_persistence)
  -> ResearchExecutionService.execute
  -> finalize_run_transaction
  -> get_run
  -> resolve_run_result
```

The project-owned `ReplayHarness` implements `AgentHarness`. It emits only the
declared scripted `AIMessage`, `ToolMessage`, and canonical virtual report
chunks through `ExecutionObserver`, then returns
`observer.snapshot_outcome()`. This reuses the real
`AccumulatorExecutionObserver` and Evidence/artifact freeze path rather than
constructing an `ExecutionOutcome` or persisted projection directly. It may
not bypass execution, finalization, persistence, Evidence validation, or
result resolution.

Each anchor uses isolated run identity, database path, workspace, outcome box,
and run-scoped cache. Cleanup is deterministic and tested. A fixture that
directly constructs the final persisted projection is invalid.

`ReplayHarness` also records the exact public-safe normalized trajectory events
that it actually emits. The evaluator trajectory is derived from this
lane-local recorder and bound to the real run identity; it is not reconstructed
from a native DeepAgents trace and is not invented after the run.

After both anchors complete, each projection is built with
`project_context_reliability_outcome`, and normalized application equivalence
must satisfy `compare_context_reliability_outcomes(...) == []`. Both
unmutated evaluator observations are then evaluated and must pass their exact
current expectations. Only then is the control mutation applied to a deep
independent copy of the second anchor's public-safe evaluator input. The
persisted application projection itself is never rewritten. Every report
records:

- `application_projection_source = persisted_lifecycle`;
- `control_mutation_stage = post_traversal`; and
- `control_failure_source = synthetic_evaluator_input`.

This makes the proof explicit:

- the lifecycle anchor is real;
- the broken dimension is synthetic;
- the evaluator sensitivity result is deterministic; and
- no runtime defect or production incident is claimed.

Run-local identifiers are normalized only where the contract explicitly
declares them run-local. Cross-lane state leakage is blocking.

The gate does not add a new native DeepAgents characterization. The existing
Context Reliability pack remains the independent locked native-framework
proof. Final verification reruns its focused pack. This avoids duplicating
framework tests while preserving the boundary between framework trajectory
and application authority.

## Evaluator adapter and sensitivity

V2 imports the existing ordered v1 evaluator registry and
`evaluate_observation`. It does not modify v1 files, case count, evaluator
count, schema identities, committed bytes, or passing semantics.

For each pair:

1. both unmutated anchor inputs must satisfy the exact current expectations
   with all six evaluators passing;
2. synthetic control input must differ from its unmutated anchor in exactly
   the declared mutation dimension;
3. both anchors and the synthetic control retain byte-equal `expected` fields;
4. both unmutated responsible evaluator results must be `pass` with no
   finding;
5. the synthetic control responsible evaluator must be `regression` with only the
   declared blocking finding;
6. the other five evaluator result projections must remain equal across both
   unmutated anchors and the synthetic control;
7. the persisted application projection must remain equal after explicit
   run-local normalization; and
8. the pair must contain no undeclared blocking or observational drift.

`negative_control_sensitivity` passes only when all eight conditions hold.

The declared control finding belongs to the pair comparator contract. It is
never inserted into the control observation's `expected` field to manufacture
an `expected_block`.

The whole gate passes only when all six unmutated healthy anchor observations
pass and all three pair results pass. A false-green, multi-dimensional
control, missing finding, non-responsible drift, application projection drift,
or unobserved mutation fails the whole gate.

## Report design

The JSON report contains:

- schema and dataset identity;
- dataset hash;
- runner and evaluator registry identities and versions;
- ordered three-pair result collection;
- seven lifecycle checkpoint results per lane;
- the three explicit source/stage fields separating lifecycle authority from
  the synthetic control;
- public-safe persisted application projections;
- normalized evaluator input projections;
- the semantic-comparison schema/version and exact normalized-field inventory;
- six ordered evaluator results for each unmutated anchor and for each
  synthetic control;
- declared mutation and observed dimension diff;
- responsible finding comparison;
- non-responsible equality result;
- pair sensitivity result;
- deterministic summary counts;
- limits and non-claims.

The Markdown report is rendered only from validated JSON and uses this order:

1. immediately after the title, this exact boundary sentence:
   `All six persisted lifecycle anchors are healthy and equivalent; regressions below exist only in post-traversal synthetic evaluator inputs.`;
2. gate status and summary;
3. a three-row pair matrix with the exact columns `healthy anchor`,
   `post-traversal synthetic control`, `application projection equal`,
   `responsible evaluator`, and `expected control finding`;
4. application authority and traversal proof;
5. evaluator matrix;
6. failure diagnosis;
7. reproduction commands;
8. limits and non-claims.

Markdown is not parsed as typed authority.

## CLI

Only:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check

PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py build \
  --json-output /tmp/dra-agent-evaluation-v2.json \
  --markdown-output /tmp/dra-agent-evaluation-v2.md
```

`build` requires two distinct explicit output paths and refuses aliases to
either committed artifact. It never accepts or replaces a baseline.

`build` exit zero means only that both candidate artifacts were written
atomically and passed schema and public-safety validation. It does not mean the
sensitivity gate passed. Its only success stdout is one canonical JSON line:

```json
{"status":"built","gate_passed":true}
```

`gate_passed` reflects the candidate report and may be false while `build`
still exits zero, allowing explicit diagnosis without weakening `check`.

`check` reruns all six healthy anchors, derives the three post-traversal
controls, rebuilds both artifacts, validates semantics and bytes, and emits
exactly one canonical comparison envelope on stdout. A
coherent drift or false green emits comparison-only stdout and exits nonzero.
Invalid input or internal failure emits no stdout, one bounded stable error on
stderr, and exits nonzero.

The exact CLI matrix is:

| Operation | stdout | stderr | Exit |
| --- | --- | --- | --- |
| `build`, valid candidate | one canonical build-result JSON line | empty | `0` |
| `check`, bytes match and gate passes | one canonical comparison JSON line | empty | `0` |
| `check`, coherent drift or false green | one canonical comparison JSON line | empty | `1` |
| invalid input/CLI/internal failure | empty | one canonical stable-error JSON line | `1` |
| root or subcommand `--help` | bounded help text | empty | `0` |

Missing/unknown CLI arguments use `evaluation_v2_cli_invalid`; they never
print argparse usage to stderr. All machine-output lines end with exactly one
terminal newline and contain no traceback or raw path.

The comparison envelope contains only:

- `schema_version`;
- `match`;
- `gate_passed`;
- `changed_case_ids`;
- `false_green_case_ids`; and
- `observed_declared_control_finding_codes`; and
- `unexpected_blocking_finding_codes`.

On a passing gate,
`observed_declared_control_finding_codes` contains the three declared finding
codes in stable case order and `unexpected_blocking_finding_codes` is empty.
This avoids describing expected sensitivity evidence as an unresolved
production blocker.

There is no accept, regenerate, write API, or interactive path.

## Stable failure classes

- `evaluation_v2_dataset_invalid`;
- `evaluation_v2_case_invalid`;
- `evaluation_v2_replay_invalid`;
- `evaluation_v2_control_invalid`;
- `evaluation_v2_report_invalid`;
- `evaluation_v2_baseline_invalid`;
- `evaluation_v2_output_invalid`;
- `evaluation_v2_cli_invalid`;
- `evaluation_v2_public_output_unsafe`;
- `evaluation_v2_internal_error`.

Errors never include raw query, Evidence body, artifact body, tool/model
payload, exception text, traceback, host path, trace identity, secret, or
credential.

## Test contract

Required coverage includes:

- exact supported schemas, bounds, ordering, canonical bytes, hash basis, and
  unsafe-value rejection;
- exactly three classes and no fourth class;
- exactly one mutation per case;
- all six independently persisted healthy anchors crossing every required
  checkpoint;
- run, DB, workspace, cache, Evidence, and result isolation;
- current lane expectations;
- both unmutated anchors passing all six evaluators before control mutation;
- byte-equal current/control `expected` fields;
- current responsible evaluator `pass` and control responsible evaluator
  `regression`;
- exact responsible finding for every control;
- equality of the other five evaluator results;
- persisted application projection equality;
- healthy anchors with naturally distinct IDs/timestamps comparing equal only
  through the closed semantic projection;
- source identity, citation/verification, policy, metrics, unexpected dynamic
  fields, and non-mutated event drift failing closed;
- persistence-only Evidence fields being excluded from the six-field evaluator
  adapter and canonical artifact identity drift failing closed;
- normalization never hiding the declared mutation or application drift;
- false-green, missing mutation, multi-dimensional mutation, extra finding,
  stale hash, and cross-lane leakage failures;
- two fresh builds producing byte-identical JSON and Markdown;
- build path protection and exact stdout/stderr behavior;
- v1 command, eight cases, six evaluators, and committed bytes unchanged;
- existing Context Reliability focused pack unchanged;
- documentation links, diagnosis, commands, and non-claims;
- existing downstream consumer fixture unchanged; and
- full non-Docker CI parity and presentation audit.

## Operator and reviewer path

- 30 seconds: open the committed Markdown and read `gate_passed` plus the
  three-row pair matrix.
- 2 minutes: run `check` and explain current, broken control, responsible
  evaluator, and false-green blocking.
- Bounded proof path: run a temporary `build`, compare JSON and Markdown, and
  run this exact diagnostic node:

  ```bash
  PYTHON_DOTENV_DISABLED=1 python -m pytest -vv -x \
    'tests/integration/test_agent_evaluation_v2_gate.py::test_declared_control_triggers_only_responsible_evaluator[trajectory-call-result-pairing]'
  ```
- Code navigation starts at `cases.json`, crosses replay and application
  persistence, then follows the v1 evaluator adapter and gate renderer.

Do not claim a five-minute result until actual implementation timing evidence
exists.

## Documentation impact

The implementation may add or modify only the bounded evaluation reference,
evidence files, synchronized English/Chinese README navigation and required-CI
inventory, documentation/evidence indexes, Unreleased changelog entry,
documentation contracts, and existing Backend CI step needed to expose and
verify the gate. Architecture, observability, API, container, frontend, release,
and consumer documents remain unchanged.

## Allowed claim after evidence exists

For three reviewed public-safe synthetic cases, DRA can independently run six
healthy replay anchors through its real application lifecycle, then
deterministically prove that the responsible existing evaluator meaning
detects one declared post-traversal synthetic control per pair without
provider or network access.

The claim is invalid until implementation, tests, committed evidence, and CI
exist.

## Non-claims

The gate does not prove:

- a real production incident or failure capture;
- automatic runtime trajectory capture or failure ingestion;
- automatic case generation or promotion;
- answer truth or live-provider quality;
- arbitrary-task or unlimited-context reliability;
- production scale, latency, availability, or cost;
- user adoption or business impact;
- generic privacy, DLP, PII, or secret detection;
- exactly-once execution;
- new model or multi-agent capability;
- API, UI, hosted evaluation, or deployment readiness;
- release inclusion; or
- a need for `v0.1.7`.

## Hard stops

Implementation returns to authority review if it requires:

- raw/private content or provider/network credentials;
- production/runtime behavior changes to make a control pass;
- direct construction of a final application projection;
- more than one changed control dimension;
- acceptance of a false green or non-responsible evaluator drift;
- changing v1 semantics or committed bytes;
- changing the Context Reliability contract;
- a new native framework patch or duplicate characterization;
- API, Docker, frontend, database, dependency, schema migration, VERSION,
  Release, consumer, or Night Voyager changes; or
- any unplanned public file.

## Delivery posture

After final public landing approval, the spec and plan may be mechanically
landed in one isolated execution worktree. Implementation is one serial,
bounded capability pack. Push, PR, merge, Release, and cleanup remain separate
authorization gates.
