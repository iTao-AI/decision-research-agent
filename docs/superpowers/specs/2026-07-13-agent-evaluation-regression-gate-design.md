# Agent Evaluation And Regression Gate v1 Design

## Status

Approved for implementation planning.

## Summary

Decision Research Agent already has strong, separate proofs for the Talent
profile, durable review feasibility, real-source workflow behavior, and
downstream contract compatibility. The missing release asset is a coherent,
versioned Agent evaluation surface that converts those contract boundaries
into one deterministic regression gate.

This change adds a public-safe evaluation dataset, an evaluator registry, a
deterministic replay/check command, an opt-in bounded live observation command,
and machine- plus human-readable reports. It evaluates canonical result
behavior, normalized tool trajectory, Evidence integrity, terminal state,
safety boundaries, and efficiency observations without changing runtime
authority or introducing an LLM judge.

The deterministic gate is required, credential-free, network-free, and stable
enough for CI. Live observation remains explicit and non-required. LangSmith
may supply optional trace correlation, but the application database and
repository-visible report remain the evaluation authority.

This capability is intended to be the principal engineering addition for a
future `v0.1.1` release. Version bumping, tagging, publishing, and release
creation are separate actions.

## Inspected Baseline

- Branch and commit: `main@c67e952fcc83fbcfcd46b9779d84fdbeac52741f`.
- `main` matches `origin/main`; no open pull request was present at inspection
  time.
- Released backend contract: annotated `v0.1.0` at
  `646f430490cc7b498cedffe4f2d690a7f91f8e5e`.
- The current commit has successful backend, frontend, and code-analysis
  checks on GitHub.
- `scripts/talent_value_gate_runner.py` already provides a narrow, bounded
  Talent-versus-generic comparison. It owns its current benchmark semantics
  and is not replaced by this design.
- `scripts/durable_hitl_gate_runner.py`, `scripts/real_source_proof.py`, and
  `scripts/downstream_consumer_contract.py` retain their separate durability,
  real-source, and consumer-compatibility proof boundaries.
- The downstream fixture already types terminal status, generic canonical and
  fallback result behavior, run-level Evidence, and fail-closed consumer
  disposition. The new gate reuses that proof rather than rebuilding it.
- Telemetry and token/cost tracking are process-local. Cost is a local estimate,
  not a provider invoice, and neither surface becomes durable in this change.

## Problem

The repository has substantial Agent engineering evidence, but a maintainer
cannot currently answer one release question with one command: did a change
regress the Agent's result contract, tool policy, Evidence integrity, terminal
state semantics, safety boundary, or bounded execution footprint?

Existing proofs intentionally answer narrower questions:

- the Talent value gate compares two profiles on one fixed sample;
- the durable HITL gate checks controlled single-node review durability;
- the real-source proof demonstrates one bounded workflow lifecycle;
- the downstream consumer proof validates status/result/Evidence consumption;
- unit and integration tests protect implementation behavior but do not emit a
  versioned cross-dimension Agent evaluation report.

Combining those scripts into one orchestration wrapper would create misleading
coupling: they have different inputs, costs, authorities, and success meanings.
Instead, the project needs one small evaluation contract that reuses current
typed proof output where applicable and adds only the missing normalized
trajectory, safety, and efficiency observations.

## Goals

1. Define a versioned, public-safe Agent evaluation case contract.
2. Ship one fixed deterministic scenario set covering successful and adverse
   paths without credentials, network, provider output, or wall-clock drift.
3. Evaluate six explicit dimensions through a registry:
   - canonical result and artifact contract;
   - normalized tool selection and trajectory policy;
   - Evidence identity and typed reference integrity;
   - terminal execution/review/delivery state;
   - declared trust-boundary and public-output safety rules;
   - assistant/tool counts, elapsed time, tokens, and estimated cost.
4. Produce deterministic JSON and Markdown reports containing evaluator and
   dataset identity, per-case findings, gate decisions, and baseline comparison.
5. Fail required CI on contract, Evidence, state, or safety regressions while
   keeping efficiency measurements observational until stable thresholds are
   approved from repeated evidence.
6. Provide an opt-in bounded live observation path using the existing Agent
   runtime without turning live variability into a required release gate.
7. Keep DeepAgents, LangGraph, the application database, and LangSmith in their
   current authority roles.

## Non-Goals

- No REST endpoint, Tool Client method, database table, migration, profile,
  frontend surface, runtime Skill, or provider integration change.
- No rewrite, wrapper orchestration, or semantic expansion of the Talent,
  durable HITL, real-source, or downstream consumer proofs.
- No generic structured findings, claims, limitations, conflicts, source
  metadata, or claim-level Evidence schema.
- No persistent failure taxonomy, terminal-cause column, durable telemetry,
  durable token usage, billing record, or provider-invoice claim.
- No LLM-as-judge in required CI and no automatic human-quality score.
- No automatic bad-case ingestion, baseline update, or release approval.
- No LangSmith API key requirement, trace export authority, or business-state
  decision based on a trace.
- No benchmark of answer truth, broad research quality, latency SLO, market
  coverage, or provider comparison.
- No Async Subagents, memory, multi-user/RBAC, anonymous public research, MCP
  adapter, or additional Agent-native integration surface.
- No `POST /api/runs` idempotency, duplicate-create behavior, or lost-response
  reconciliation. That is a separate public API and persistence design
  candidate for a later release.

## Considered Approaches

### A. Treat the existing pytest suite as the evaluation gate

This is simple but does not produce a versioned Agent-level report, dataset
identity, per-dimension results, or an intentional baseline review workflow.
Rejected as the complete solution; the existing test suite remains necessary.

### B. Run every existing proof from one release script

This would mix deterministic fixtures, real-provider execution, durability
experiments, independent review, and consumer compatibility into a single
success signal. It would also make CI slow and credential-dependent. Rejected.

### C. Add a deterministic evaluation contract plus optional live observation

Recommended. Reuse typed output from the downstream proof for result/state
semantics, add a small normalized observation envelope for trajectory, safety,
and efficiency, and compare a generated report with an explicitly reviewed
baseline. Keep live provider behavior separate and opt-in.

### D. Use LangSmith datasets and evaluators as the canonical gate

LangSmith is useful for trace diagnostics, but requiring a hosted workspace and
service key would violate the repository's credential-free CI and authority
boundaries. Rejected as the canonical path; optional correlation remains
supported.

## Architecture

```mermaid
flowchart LR
    Manifest["Versioned scenario manifest"] --> Builder["Deterministic observation builder"]
    Consumer["Existing downstream contract proof"] --> Builder
    Builder --> Registry["Evaluator registry"]
    Registry --> JSON["Canonical JSON report"]
    JSON --> Markdown["Deterministic Markdown renderer"]
    JSON --> Compare["Reviewed baseline comparison"]
    Compare --> Gate["CI regression decision"]

    Runtime["Existing Agent runtime"] --> Live["Bounded live observation"]
    Live --> Registry
    Trace["Optional LangSmith trace reference"] -. diagnostics .-> Live

    DB[("Application DB authority")] -. unchanged .-> Runtime
    Graph["LangGraph workflow state"] -. runtime only .-> Runtime
    Deep["DeepAgents harness"] -. execution only .-> Runtime
```

The evaluator consumes a normalized observation envelope. It does not become a
new run ledger or runtime result model. Deterministic observations are built
from fixed public-safe inputs; status/result/Evidence cases are sourced through
the existing downstream compatibility builder. Live observations are ephemeral
operator artifacts unless the operator explicitly saves them outside the
committed baseline.

## Authority Boundaries

- The application database remains authoritative for `ResearchRun`,
  `EvidenceLedger`, review, verification, publication, and delivery.
- DeepAgents remains the research harness and tool/subagent execution surface.
- LangGraph remains workflow execution and checkpoint-compatible review
  position, not the business ledger.
- LangSmith remains privacy-first diagnostics. A trace reference may help an
  operator investigate a finding but cannot clear or create a gate finding.
- The committed evaluation report is release proof for fixed inputs. It is not
  runtime output, production monitoring, independent fact verification, or a
  provider quality ranking.
- Human review remains separate. The registry produces deterministic contract
  findings, not subjective answer-quality judgments.

No ADR is required because the authority model and runtime contract remain
unchanged. If implementation requires a new endpoint, persisted field,
checkpoint dependency, profile behavior, or business decision authority, stop
and return to architecture design.

## Evaluation Case Contract

The scenario manifest is versioned as `dra.agent-evaluation-cases.v1`. Each
case contains fixed public-safe inputs and exact expected findings. It does not
contain model credentials, live provider output, host paths, wall-clock
timestamps, or private source material.

The normalized evaluator input is conceptually:

```json
{
  "case_id": "canonical_success",
  "source": "deterministic",
  "run": {},
  "result": {},
  "trajectory": [],
  "typed_evidence_refs": [],
  "trust_signals": [],
  "metrics": {},
  "expected": {
    "blocking_finding_codes": [],
    "observational_finding_codes": []
  }
}
```

`run`, `result`, and run-level Evidence retain the public-safe projection from
the downstream contract proof. The evaluation layer must not fork or relax
that validator. `trajectory`, typed refs, trust signals, and metrics are
evaluation-only data and are not presented as persisted runtime fields.

### Normalized Trajectory Events

Trajectory events use a small exact vocabulary:

- `assistant`: bounded assistant message metadata, without raw content;
- `tool_call`: `event_id`, declared tool name, and current `run_id`;
- `tool_result`: matching call ID, trust classification, and current `run_id`;
- `terminal`: terminal state observation.

Required deterministic reports do not include prompts, tool arguments, tool
results, Evidence snippets, or generated answer text. The registry evaluates
event order and metadata only.

### Trust Signals

The evaluator does not claim to detect arbitrary prompt injection. A trust
signal is a structured, fixture-declared fact such as
`untrusted_instruction_present`. Safety rules can then verify that no
prohibited tool action follows that signal and that the public report contains
no forbidden material. Live mode may omit trust signals when the runtime does
not provide a typed equivalent; omission must remain visible as `not_observed`,
not silently treated as safe.

### Metrics

Metrics use these semantics:

- assistant and tool counts are non-negative integers;
- elapsed time is an observation, never a deterministic wall-clock assertion;
- token counts may be absent when the current collector has no record;
- cost is always named `cost_estimate` and carries currency and pricing-basis
  metadata;
- no cost field may be labeled as billed, invoiced, or provider-reported unless
  a future contract actually supplies that authority.

## Deterministic Scenario Matrix

| Case | Contract path | Expected evaluator result |
|---|---|---|
| `canonical_success` | completed, ready, canonical Markdown, safe trajectory, current-run Evidence | no blocking findings |
| `fallback_blocked` | completed, ready fallback artifact | expected `result.fallback_blocked`; no regression when correctly blocked |
| `review_required` | completed, review required, result withheld | expected `state.review_required`; no regression when delivery stays blocked |
| `failed_terminal` | failed terminal state and stable result error | expected `state.failed`; no regression when failure is represented consistently |
| `evidence_missing` | canonical-looking result without required declared Evidence | expected blocking `evidence.missing` |
| `prohibited_tool` | trajectory contains a tool outside the case allowlist | expected blocking `trajectory.tool_prohibited` |
| `untrusted_instruction_action` | declared untrusted instruction followed by a prohibited action | expected blocking `safety.action_after_untrusted_instruction` |
| `cross_run_reference` | tool result or Evidence identity points at another run | expected blocking `isolation.cross_run_reference` |

Adverse cases pass the regression suite only when the evaluator emits the exact
expected blocking finding and disposition. A case being intentionally adverse
does not make the unsafe behavior acceptable at runtime.

## Evaluator Registry

Each evaluator has a stable ID, version, severity policy, and deterministic
output. Registry order is fixed so reports are byte-stable.

### `result_contract.v1`

- delegates generic status/result validation to the existing downstream
  consumer contract;
- verifies canonical/fallback artifact kind, media type, size, and hash;
- treats fallback as inspectable but blocked;
- does not parse Markdown or evaluate answer truth.

### `trajectory_policy.v1`

- verifies allowed tool names for the case;
- requires unique event IDs and tool-call/result pairing;
- rejects calls or results associated with another `run_id`;
- verifies terminal event ordering;
- does not score reasoning text or require a particular number of subagents.

### `evidence_integrity.v1`

- verifies Evidence identities belong to the current run;
- verifies any explicitly typed Evidence refs resolve to declared current-run
  Evidence;
- emits `not_observed` for claim-level support when no typed refs exist;
- never extracts citations, limitations, or claims from Markdown.

### `terminal_state.v1`

- checks execution/review/delivery combinations and stable result disposition;
- distinguishes expected fallback, review-required, and failed paths;
- does not invent a persistent timeout/provider/cancel cause that the current
  run contract does not store.

### `safety_boundary.v1`

- verifies declared trust-signal policy and prohibits configured unsafe actions
  after an untrusted instruction signal;
- checks the generated evaluation artifacts for explicitly forbidden public
  material such as credential assignments, host absolute paths, raw
  tracebacks, raw prompts, and tool payloads;
- is a bounded proof-artifact check, not a general DLP or prompt-injection
  detector.

### `efficiency_observation.v1`

- records assistant/tool counts, elapsed time, token counts when available, and
  local cost estimate metadata;
- validates types and internal count consistency;
- produces observational findings only in v1;
- cannot fail the release gate for threshold drift until an approved baseline
  establishes stable thresholds across repeated runs.

## Deterministic Replay Mode

The required command:

1. loads the exact versioned scenario manifest;
2. validates its schema and computes a SHA-256 dataset hash;
3. obtains current status/result/Evidence projections from the existing
   downstream proof builder;
4. builds the normalized deterministic observations;
5. runs the fixed evaluator registry;
6. compares actual findings with each case's exact expectations;
7. serializes canonical JSON and derived Markdown;
8. compares both outputs with the committed reviewed baseline.

The mode must not initialize provider models, network tools, DeepAgents,
LangGraph execution, LangSmith clients, process-global telemetry, or token
collectors. It must run with no `.env` and no credentials.

Equivalent source and fixed input must produce identical UTF-8 bytes. JSON uses
sorted keys, two-space indentation, and one trailing newline. Markdown is
rendered only from the validated JSON report.

## Bounded Live Observation Mode

Live mode is explicit, operator-run, and never required in CI. It may execute
one existing profile through the current runtime with:

- an explicit query or declared fixture input;
- a positive per-run timeout with a conservative upper bound;
- unique run, thread, and segment identities;
- existing provider and search configuration;
- bounded output written only to an explicit operator-selected path;
- no automatic baseline update or commit.

The command normalizes only fields available from the current execution
outcome and current process-local collectors. Missing fields remain typed as
`not_observed`. It must preserve the current Evidence and result boundaries,
sanitize exported errors, and avoid raw prompts, tool payloads, credentials,
or host paths.

A live report has `source="live_observation"`, includes no deterministic
baseline-pass claim, and records environment variable names/status only when a
preflight is requested. It does not print secret values. Provider/model names
may be recorded only if already public-safe and explicitly allowlisted.

An optional LangSmith trace reference may be recorded when tracing is already
configured. The command must not accept an API key on the command line, query
LangSmith to decide the gate, or fail because no trace exists.

## Report Contract

The canonical JSON report schema is `dra.agent-evaluation-report.v1` and
contains exact top-level sections:

```text
schema_version
evaluator_version
source
dataset
registry
summary
cases
limits
```

Required identity fields include:

- manifest schema version and SHA-256 hash;
- evaluator/report version;
- ordered evaluator IDs and versions;
- ordered case IDs;
- deterministic/live source classification.

Each case records:

- expected and actual blocking/observational finding codes;
- evaluator-level status: `pass`, `expected_block`, `regression`, or
  `not_observed`;
- bounded finding metadata without raw content;
- normalized metric observations and estimate labels;
- whether exact expectations match.

The summary separates:

- `blocking_regression_count`;
- `expectation_mismatch_count`;
- `observational_change_count`;
- `not_observed_count`;
- `release_gate_passed`.

The committed deterministic report has no generation wall clock, Git commit,
host path, random identifier, or provider metadata. Version control records
which source revision produced it.

The Markdown report renders dataset/evaluator identity, gate status, the case
matrix, finding counts, and explicit limitations. It contains no additional
facts absent from the validated JSON.

Baseline comparison is a separate, non-circular envelope with schema
`dra.agent-evaluation-comparison.v1`. It records the candidate and baseline
SHA-256 hashes, whether they match, changed case IDs, blocking regression
codes, and observational changes. `check` may print this bounded envelope or
write it to an explicit path, but it is not embedded in the report being
compared. The committed JSON and Markdown therefore remain reproducible
without comparing a document to a field inside itself.

## Baseline And Release Gate

The baseline is reviewed evidence, not a snapshot that tests automatically
rewrite.

- `check` exits zero only when the manifest is valid, evaluator expectations
  match, no unexpected blocking regression exists, and generated JSON/Markdown
  equal the committed baseline.
- A mismatch emits the bounded comparison envelope with stable finding codes
  and changed case IDs, not raw report bodies or a host path.
- `build` writes candidate artifacts only to explicit paths. It does not replace
  committed baselines implicitly.
- A maintainer must inspect scenario, evaluator, report, and documentation
  changes together before accepting a new baseline.
- Contract, Evidence, terminal-state, isolation, and safety mismatches are
  blocking.
- Efficiency changes remain observational for v1. Adding a blocking threshold
  requires repeated measurements, an explicit unit and environment boundary,
  an approved tolerance, and a new evaluator/baseline version.
- Live observation can support a release narrative but cannot make a failing
  deterministic gate pass.

## CLI And Failure Handling

The implementation provides one repository script with bounded commands:

```text
check             validate, evaluate, and compare committed artifacts
build             write candidate deterministic JSON and Markdown
observe           run one bounded live observation to explicit outputs
```

All commands return non-zero for invalid inputs or blocking failure. Stable
public errors include:

- `evaluation_manifest_invalid`;
- `evaluation_schema_unsupported`;
- `evaluation_case_invalid`;
- `evaluation_registry_invalid`;
- `evaluation_expectation_mismatch`;
- `evaluation_blocking_regression`;
- `evaluation_baseline_drift`;
- `evaluation_output_invalid`;
- `live_observation_timeout`;
- `live_observation_failed`.

CLI error output must not contain raw exceptions, tracebacks, credentials,
provider responses, prompt/tool content, or local paths. The implementation may
log a bounded case ID and evaluator ID.

## Testing Strategy

### Dataset and report contracts

- exact manifest/report schema versions and keys;
- deterministic dataset hash and registry order;
- byte-identical JSON and Markdown builds;
- committed baseline equals a fresh build;
- duplicate/unknown case or evaluator IDs fail closed;
- Markdown contains no information absent from JSON.

### Scenario behavior

- all eight required cases emit exact expected finding codes;
- canonical success has no blocking finding;
- fallback, review-required, and failed cases are correctly represented rather
  than treated as generic success;
- missing Evidence, prohibited tool, unsafe post-instruction action, and
  cross-run reference are caught;
- an adverse case with a missing expected finding fails the suite;
- an unexpected finding in a safe case fails the suite.

### Evaluator mutation coverage

- artifact kind/media/hash/size mutation;
- unknown tool, duplicate event ID, orphan tool result, terminal event followed
  by another action;
- missing/foreign Evidence identity and unresolved typed ref;
- impossible execution/review/delivery combination and unknown result code;
- trust signal without prohibited action versus prohibited action after signal;
- negative/non-integer counts, malformed elapsed/token/cost estimate fields;
- unknown enum, extra public-report key, and unsupported schema version.

### Privacy and authority coverage

- fixture and generated reports reject host absolute paths, credential-like
  assignments, raw tracebacks, raw prompts, and tool payloads;
- generic Markdown headings do not create typed findings or Evidence refs;
- no deterministic path imports or initializes provider, network, DeepAgents,
  LangGraph execution, LangSmith client, telemetry collector, or token
  collector;
- missing token/cost or LangSmith data remains `not_observed` and non-blocking;
- cost labels remain explicit estimates.

### Live mode tests

- mock the existing runtime to verify unique identities, timeout, one-run bound,
  sanitization, and explicit output requirement;
- ensure live mode cannot write or update the committed baseline;
- ensure missing credentials/configuration fails with bounded guidance;
- ensure no LangSmith configuration is required;
- do not perform provider or network execution in required tests.

### Broader verification

- focused new unit/integration tests;
- existing downstream consumer contract tests and `check` command;
- existing Talent value-gate runner tests to prove no semantic regression;
- full backend pytest suite under supported Python 3.11;
- documentation contract tests and `git diff --check`.

Frontend checks are not required unless implementation unexpectedly touches the
frontend; that would be scope growth and requires review.

## Documentation

Add a public reference explaining:

- what the deterministic gate does and does not prove;
- deterministic versus live observation modes;
- evaluator registry and scenario matrix;
- report schema, dataset hash, baseline review, and stable failure codes;
- why efficiency and cost are observational estimates in v1;
- why generic Markdown is not parsed into typed facts;
- why LangSmith is optional diagnostics and the application ledger remains
  authoritative;
- how existing Talent, durability, real-source, and downstream proofs remain
  separate.

Link the reference and committed reports from the evidence/documentation
indexes and the README verification section. Update `CHANGELOG.md` under
`Unreleased` only after implementation exists. Do not add a release tag or
claim `v0.1.1` is published in the implementation change.

## Compatibility, Migration, And Rollback

- Runtime API, persistence, Tool Client, Agent profiles, and result/Evidence
  contracts are unchanged.
- The dataset and report schemas are offline evaluation contracts; version them
  independently from the REST API.
- There is no data migration or backfill.
- Existing proof artifacts remain valid and separately documented.
- Rollback removes the new manifest, evaluator script/modules, reports, tests,
  and links. Runtime behavior and persisted data are unaffected.
- A baseline update without a matching reviewed evaluator/dataset explanation
  is invalid.

## Deferred `POST /api/runs` Idempotency And Reconciliation Gate

A later, independent release may address duplicate run creation and a lost
create response. That work changes public API and persistence semantics and
must not be inferred from this evaluation feature.

Before implementation, a separate design must establish at least:

- caller-supplied idempotency identity and authentication scope;
- canonical request fingerprinting;
- same-key/same-payload replay behavior;
- same-key/different-payload conflict behavior;
- concurrent duplicate-create serialization;
- durable lookup after process restart;
- recovery when the server committed a run but the caller lost the response;
- bounded retention/expiry and migration behavior, if expiry is adopted;
- Tool Client recovery semantics and stable public errors;
- tests for duplicate requests, races, restart, and simulated response loss.

No exact header name, table shape, retention period, or conflict status is
approved by this document. Those choices require current consumer/operator
evidence and their own contract review.

## Review Strategy

This is a Level 3 offline evaluation contract with an opt-in live runner and no
runtime authority change. A focused engineering plan review is required. A
full Autoplan is not required because the work stays within one repository and
does not expand product or business authority.

After implementation, run one authoritative diff review focused on evaluator
coverage, expected-adverse-case semantics, deterministic bytes, reuse of the
downstream proof, no hidden live dependency, safety claims, estimate labeling,
baseline update controls, and documentation boundaries. Use targeted re-review
after any fixes.
