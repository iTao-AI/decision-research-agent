# Evidence-Gated Loop Kernel v1 Design

**Status:** Authority-approved for mechanical landing and implementation planning. Implementation is not yet authorized.

**Date:** 2026-07-28

## 1. Audited baseline

The design is anchored to the following reviewed public state:

- Decision Research Agent `main` is `01ba21f2996769e68cbc88f4bb0596740df27f6b`.
- The latest release remains `v0.1.6`, targeting `7d43324b469cb5e445c2e8be83af3be4d841cf1c`. Context Reliability, privacy-safe observation, Evaluation Sensitivity v2, and strict citation are post-`v0.1.6` capabilities.
- Context Reliability PR #123 is merged as `2c50f233c2cc1df4fe2818551e95ab98cd61ede5`, tree `8da21672e9fd63352e9bc15365818f7edd12d106`.
- Evaluation Sensitivity v2 PR #128 is merged as `6a3020863fbaaf9d218420b7981150a5736b7fb8`, tree `d6b0dd3a0911125795eb7146bcd659c99233067d`.
- Strict citation PR #129 is merged as `01ba21f2996769e68cbc88f4bb0596740df27f6b`, tree `06e5282414d3801b11040bba735dd107105e8a30`.
- Night Voyager strict-consumer PR #75 is merged as `95cce4f28357150450c7f87105adcb47abf1a15d`, tree `7e310124de9c7d081723eee5b42c152a258b0919`.
- The strict producer identity is the exact commit above plus `generic-strict-citation@1`, `profile_version=1`, and `proof_schema=dra.strict-citation-profile.v1`. It is not part of the immutable `v0.1.6` release.
- The existing Application DB, Evidence, artifact, review, verification, delivery, profile, and consumer authority boundaries remain authoritative.

The former Consumer-Derived Loop Proof v1 design was a one-case acceptance receipt. It is superseded by this design because it could not demonstrate a reusable case lineage, fixed verification profiles, or a durable distinction between candidate verdict, consumer proof, and release disposition.

## 2. Product decision

Add a bounded, provider-free, code-first offline kernel named **Evidence-Gated Loop Kernel v1**.

The kernel validates this chain:

```text
reviewed evidence
-> structured diagnosis
-> update-carrier assessment
-> change or no-change action
-> immutable candidate identity when applicable
-> historical RED plus executable retained and safety verification
-> reviewed candidate verdict
-> independent consumer proof when required
-> release, hold, or rollback recommendation
```

The kernel is not a runtime learning loop. It does not ingest live traffic, modify the Agent, generate a candidate, edit a verifier, merge code, move a consumer pin, publish a release, or execute rollback.

A valid record may conclude `accepted`, `rejected`, `need_more_evidence`, or `no_change`. A green kernel result means that the record and its required proofs are coherent; it does not mean that every candidate was accepted or that a release is authorized.

## 3. Goals

1. Preserve an ordered, versioned lineage from evidence through diagnosis, action, verification, verdict, consumer proof, and release disposition.
2. Reuse three independently reviewed DRA failure or verification episodes rather than inventing synthetic product claims.
3. Keep online application truth, diagnostic observation, offline evaluation, human review, consumer proof, and release authority separate.
4. Make change, reject, no-change, and need-more-evidence first-class outcomes.
5. Run all required local verification without provider, model endpoint, credentials, network, Docker, database migration, or hosted observability.
6. Prevent manifests from supplying arbitrary commands, pytest paths, dynamic tools, or verifier logic.
7. Produce canonical JSON and Markdown evidence with strict schemas, bounded I/O, stable errors, deterministic ordering, and public-safe projections.
8. Permit a future case of an already supported evidence and verification kind to be added through reviewed manifests without rewriting the core schema.
9. Require an explicit adapter and verification-profile review when a genuinely new evidence or proof kind appears.
10. Preserve generic behavior, the immutable `v0.1.6` release, and existing consumer contracts.

## 4. Non-goals

This phase does not add:

- runtime self-modification or self-training;
- automatic trajectory capture or aggregation;
- automatic root-cause diagnosis;
- automatic candidate generation or promotion;
- Prompt, Skill, knowledge, or model-parameter mutation;
- a generic EvalOps platform, hosted service, UI, scheduler, queue, database, or API;
- a new Agent role or multi-Agent product topology;
- dynamic tool or test discovery;
- a context compactor or memory subsystem;
- provider/model calls, credentials, live data, or a third provider attempt;
- Night Voyager changes;
- release, tag, deployment, or rollback execution.

## 5. Design principles

### 5.1 Online execution and offline evolution remain separate

Online DRA execution continues to complete bounded work and persist application-owned state. Privacy-safe observation remains diagnostic only. The new kernel consumes reviewed public-safe references offline and never mutates online state.

### 5.2 Evaluation starts with the verifier

An apparent Agent failure may be a verifier false green. The kernel therefore records the failure layer and keeps evaluator changes distinct from runtime changes. Context PR #123 and Evaluation Sensitivity v2 are reference cases for this rule.

### 5.3 A candidate cannot approve itself

The candidate identity, kernel contract, fixed verification profile, reviewed verdict, and external consumer proof are separate records. Manifests cannot define commands or lower thresholds. The kernel does not turn candidate output into a verdict.

### 5.4 Evidence is not instruction

Raw prompts, queries, snippets, tool payloads, exceptions, credentials, host paths, and private traces are forbidden from public case manifests and reports. Reviewed summaries identify only the bounded claim and immutable source reference.

### 5.5 Historical RED and current executable regression are distinct

Historical RED is a reviewed provenance record. Current CI does not claim to check out and re-run every pre-fix commit. A current fail-to-pass regression must still exercise the failing dimension provider-free. Both are required and reported separately.

### 5.6 No-change is a successful engineering decision

When existing behavior and proof already close the diagnosed gap, the correct action may be no further code change. The kernel must validate that outcome without inventing a candidate.

## 6. Authority model

| Surface | Authority |
|---|---|
| ResearchRun, Evidence, artifact, terminal state, review, verification, delivery | Existing application-owned database and services |
| LangGraph checkpoint and LangSmith trace | Workflow position and diagnostics only |
| Privacy-safe observation | Closed, lossy diagnostic evidence only |
| Historical source record | Reviewed immutable Git identity plus bounded frozen summary |
| Case and episode coherence | Evidence-Gated Loop Kernel contracts |
| Verification execution | Code-owned fixed verification-profile registry |
| Diagnosis, carrier selection, candidate verdict, release/rollback recommendation | Human review |
| Candidate implementation identity | Git repository, exact commit, and tree; capability tuple when applicable |
| Independent consumer proof | Consumer repository and its reviewed checks |
| Published release truth | Git tag and GitHub Release |
| Model | No v1 diagnosis, mutation, verdict, or publication authority |

External GitHub and consumer proof is reviewed before it is frozen into a case. Provider-free CI validates the closed reference and report bytes; it does not claim to contact GitHub or re-certify external hosted checks.

## 7. Versioned contracts

The implementation introduces three public schemas:

```text
dra.evidence-gated-loop-registry.v1
dra.evolution-case.v1
dra.evidence-gated-loop-report.v1
```

All schema models are strict, frozen, and `extra="forbid"`. Identifiers, SHA values, collection sizes, text sizes, nesting depth, and file reads are bounded.

### 7.1 Registry

The registry contains:

```text
schema_version
kernel_id
kernel_version
case_paths
verification_profiles
limits
non_claims
```

`case_paths` are repository-relative paths under one fixed benchmark directory and are canonically ordered. The registry contains no command, argument vector, pytest selector, import path, URL to execute, environment override, or writable output path.

### 7.2 Evolution case

An evolution case contains:

```text
schema_version
case_id
case_version
title
evidence_refs
episodes
```

A case is a stable failure or verification lineage. It is not one run and not one candidate.

Each evidence reference contains:

```text
evidence_id
subject_candidate_id
origin_kind
repository
commit_sha
tree_sha
locator
proof_kind
reviewed_summary
claim_scope
public_safe
```

Allowed `origin_kind` values in v1 are:

```text
repository_audit
verification_gap
downstream_consumer
```

Allowed `proof_kind` values in v1 are:

```text
reviewed_historical_red
reviewed_verification_gap
independent_consumer_contract
reviewed_candidate_regression
reviewed_candidate_safety_failure
reviewed_candidate_verification_inconclusive
independent_consumer_rejection
```

These values distinguish reviewed pre-candidate provenance, an
evaluation-system gap, consumer-owned provider-free acceptance proof, and the
three typed rollback evidence classes. They do not claim that external
history is re-executed by DRA CI.

`subject_candidate_id` is `null` for pre-candidate provenance. Candidate
verification outcomes, candidate-owned consumer proof, and all rollback
evidence bind it to an exact candidate in the same case. The candidate record
then closes repository, commit, tree, optional profile tuple, and predecessor
or rollback target.

The code-owned origin/proof matrix is closed:

- `reviewed_historical_red` uses `repository_audit` or
  `downstream_consumer`;
- `reviewed_verification_gap` uses `verification_gap`;
- `reviewed_candidate_regression` and
  `reviewed_candidate_safety_failure` use `repository_audit` or
  `verification_gap`;
- `reviewed_candidate_verification_inconclusive` uses
  `verification_gap`;
- both consumer proof kinds use `downstream_consumer`.

Other combinations fail closed.

`reviewed_summary` is a bounded public-safe projection, not raw source material. `public_safe` must be the literal `true`.

### 7.3 Decision episode

Each case contains one or more ordered episodes:

```text
episode_id
predecessor_episode_id
input_evidence_ids
diagnosis
carrier_assessments
action
candidate_refs
verification_profile_ref
reviewed_decision
```

Episode IDs are unique. The first episode has no predecessor. Every later episode points to the immediately preceding episode. Earlier episodes are immutable and cannot be overwritten by later evidence.

### 7.4 Diagnosis

Diagnosis contains:

```text
status
failure_mode_code
root_cause_layer
expected_invariant
observed_invariant
scope
```

Allowed `status` values are `confirmed` and `inconclusive`. An inconclusive diagnosis cannot accept a change candidate and must end in `need_more_evidence` or `no_change` with release `hold`.

Allowed `root_cause_layer` values are:

```text
knowledge
prompt_skill
program_harness
evaluation_proof
consumer_contract
environment
model_parameters
```

A root-cause layer is not automatically the update carrier.

### 7.5 Carrier assessment and action

The four update carriers are:

```text
knowledge
prompt_skill
program_harness
model_parameters
```

Every episode assesses all four in canonical order with one of:

```text
selected
rejected
unsupported
deferred
```

`no_change` is not a carrier. It is an action kind.

Action is one of:

```text
change
no_change
```

A v1 change action contains exactly one selected carrier and exactly one candidate. The action records:

```text
kind = change
selected_carrier
change_surface
runtime_effect = none | changed
```

A no-change action contains no selected carrier and no candidate and records bounded `reason_codes`.

If a future update genuinely requires multiple carriers, each independently reviewable candidate must use a consecutive episode with its own verification profile and verdict. An inseparable composite candidate requires a new schema review. V1 does not compress mixed candidate outcomes into one verdict.

The change surface is separate from the carrier:

```text
knowledge
prompt_skill
runtime_harness
evaluation_proof
model_parameters
```

For example, PR #123 uses carrier `program_harness` with surface `evaluation_proof` and runtime effect `none`.

`model_parameters` remains schema-visible for long-term semantic completeness but is unsupported in v1. Selecting it fails closed because this repository has no approved training, held-out evaluation, forgetting, or safety-regression evidence.

### 7.6 Candidate identity

A candidate contains:

```text
candidate_id
carrier
change_surface
repository
commit_sha
tree_sha
predecessor_or_rollback_ref
capability_identity
```

`capability_identity` is optional only when the candidate has no versioned profile or proof schema. When present, it closes the relevant profile ID, profile version, and proof schema.

The strict citation candidate uses:

```text
repository + commit
+ profile_id
+ profile_version
+ proof_schema
```

### 7.7 Reviewed decision

Reviewed decision contains independent axes:

```text
reviewed_candidate_verification_status
reviewed_verification_evidence_ids
candidate_verdict
consumer_proof_status
loop_closure_status
release_disposition
rollback_basis
rollback_evidence_ids
rollback_subject_candidate_id
rollback_target
reason_codes
```

Allowed reviewed verification statuses are:

```text
passed
failed
inconclusive
not_applicable
```

This is the human-reviewed outcome for a change episode's candidate under its
referenced profile at decision time. It is not the result of the kernel's
current subprocess execution. The report keeps that reviewed temporal fact
separate from the current code-owned profile result. A `failed` or
`inconclusive` status requires one or more
`reviewed_verification_evidence_ids` resolving to the current episode's
inputs and binding the exact current candidate. `failed` accepts only
`reviewed_candidate_regression` or
`reviewed_candidate_safety_failure`; `inconclusive` accepts only
`reviewed_candidate_verification_inconclusive`. `passed` uses an empty list
because current code-owned execution supplies the retained-state proof. A
no-change episode must use `not_applicable` and an empty list.

Allowed candidate verdicts are:

```text
accepted
rejected
need_more_evidence
not_applicable
```

Allowed consumer statuses are:

```text
accepted
rejected
pending
not_required
```

Allowed closure statuses are:

```text
closed_accepted
closed_rejected
closed_no_change
open_waiting_evidence
open_waiting_consumer
```

Allowed release dispositions are:

```text
hold
eligible_for_separate_release_review
rollback_recommended
```

`rollback_basis` is `null` unless release disposition is
`rollback_recommended`. Its non-null values are `regression`, `safety`, and
`consumer_rejection`. `rollback_evidence_ids` is empty unless rollback is
recommended. `rollback_subject_candidate_id` is `null` unless rollback is
recommended; when non-null it resolves to the exact earlier accepted candidate
whose immutable identity and predecessor or pin are under review.

The report-level release disposition is derived conservatively in this exact
priority order: any `rollback_recommended` episode yields
`rollback_recommended`; otherwise any `hold` episode yields `hold`; only a
record in which every episode is `eligible_for_separate_release_review` yields
that value. Manifests cannot supply the aggregate.

No value means that a release, rollback, or deployment happened.

## 8. Reference case registry

### 8.1 Context resolver projection false green

Public lineage:

- Context Reliability PR #122 established the provider-free regression pack.
- Independent audit found that an incompatible persisted terminal state and stable resolver error pair could remain green.
- PR #123 introduced six cross-state RED cases and three unknown-enum RED cases, then closed them without changing production runtime.

Decision:

```text
origin_kind       = repository_audit
root_cause_layer  = evaluation_proof
action            = change
carrier           = program_harness
change_surface    = evaluation_proof
candidate         = 2c50f233... / tree 8da21672...
candidate_verdict = accepted
consumer_status   = not_required
release           = hold
```

### 8.2 Evaluation sensitivity false green

Public lineage:

- A healthy baseline did not prove that the responsible evaluator detected its declared failure dimension.
- Evaluation Sensitivity v2 added six healthy persisted anchors and three one-dimensional post-traversal controls.
- The responsible evaluator must detect its control while non-responsible evaluators and application-owned projections remain stable.

Decision:

```text
origin_kind       = verification_gap
root_cause_layer  = evaluation_proof
action            = change
carrier           = program_harness
change_surface    = evaluation_proof
candidate         = 6a302086... / tree d6b0dd3a...
candidate_verdict = accepted
consumer_status   = not_required
release           = hold
```

This case is not a production incident or automatic failure capture.

### 8.3 Strict citation downstream consumer failure

Public lineage:

- Two governed live attempts retained 25 and 83 same-run Evidence rows respectively while producing zero cited rows.
- Both stopped before candidate import and caused no candidate, promotion, planning, review, or decision mutation.
- Continuing query or Prompt changes, weakening the consumer exact-public-HTTPS gate, and a third provider attempt were rejected.
- DRA PR #129 added the opt-in strict profile while preserving literal generic behavior.
- Night Voyager PR #75 adopted the exact producer tuple and completed independent provider-free consumer contract proof.

Episode 1:

```text
origin_kind       = downstream_consumer
root_cause_layer  = program_harness
action            = change
carrier           = program_harness
change_surface    = runtime_harness
candidate         = 01ba21f... / tree 06e52824...
candidate_verdict = accepted
consumer_status   = pending at producer acceptance
release           = hold
```

Episode 2:

```text
new evidence      = Night Voyager PR #75
consumer_status   = accepted for provider-free contract proof
action            = no_change
loop_closure       = closed_no_change
release            = hold
```

PR #75 does not prove live-provider strict success. Strict live acceptance remains unobserved and is not required for this provider-free kernel record.

The `strict-consumer-pr-75` evidence binds
`subject_candidate_id = strict-citation-pr-129`; the two pre-candidate live
failure references keep `subject_candidate_id = null`.

### 8.4 Privacy-safe observation boundary

Privacy-safe observation PR #127 is not a fourth evolution-success case. It defines the closed, lossy, non-authoritative online evidence boundary that the kernel must preserve. Raw observation data is not imported into case manifests.

## 9. Verification state machine

The kernel preserves a reviewed verification fact and three separate outcome
axes:

```text
reviewed_candidate_verification_status = passed | failed | inconclusive | not_applicable
record_status      = valid | invalid
candidate_verdict  = accepted | rejected | need_more_evidence | not_applicable
closure_status     = closed_accepted | closed_rejected | closed_no_change | open_waiting_evidence | open_waiting_consumer
```

It does not derive a single aggregate `loop_outcome`. A record can be valid while its candidate is rejected, consumer proof is pending, or release is held. This preserves the diagnostic dimension instead of converting uncertainty or a partial result into a false green.

### 9.1 Change path

```text
evidence registered
-> diagnosis confirmed
-> carrier assessed
-> change selected
-> candidate identity closed
-> historical RED present
-> reviewed candidate verification status recorded
-> current fixed verification profile passes
-> reviewed candidate verdict
-> consumer proof when required
-> hold, separate release review, or rollback recommendation
```

An accepted candidate requires:

1. confirmed diagnosis;
2. exactly one selected supported carrier;
3. exactly one candidate identity bound to that carrier;
4. reviewed historical RED provenance;
5. reviewed candidate verification status `passed`;
6. executable fail-to-pass regression;
7. pass-to-pass retained checks;
8. safety and compatibility checks;
9. provider-free execution;
10. required consumer proof or explicit `open_waiting_consumer` with release `hold`;
11. a human-reviewed verdict.

### 9.2 Reject and need-more-evidence paths

An episode whose reviewed candidate verification status is `failed` cannot produce
`accepted`. It must produce `rejected` or `need_more_evidence` with release
`hold`. An `inconclusive` reviewed status must produce
`need_more_evidence` with release `hold`. A change episode cannot use
`not_applicable`.

Current fixed-profile execution is a separate freshness and safety gate. A
nonzero exit, signal, timeout, missing executable, or OS error makes the report
invalid with `loop_verification_failed`; the kernel never converts an
execution or infrastructure failure into a green rejected record. Structurally
valid `rejected` and `need_more_evidence` episodes therefore still require all
current fixed profiles to pass.

A candidate may also be rejected after passing tests when reviewed cost, compatibility, authority, or scope evidence is unacceptable. The reason code must identify that boundary.

### 9.3 No-change path

A no-change episode requires:

- no selected carrier;
- no candidate;
- an explicit evidence-backed reason;
- applicable retained and safety checks;
- reviewed candidate verification `not_applicable` with no verification evidence IDs;
- candidate verdict `not_applicable`;
- closure `closed_no_change` or `open_waiting_evidence`;
- release `hold` unless an existing immutable subject separately qualifies for release review.

### 9.4 Consumer proof

Consumer proof is owned by the consumer repository. DRA records its exact merge commit, tree, proof scope, and reviewed hosted-check identity. DRA CI does not re-run the consumer repository or claim external network verification.

A provider-free consumer proof can close a provider-free contract requirement while live-provider acceptance remains unobserved. The proof scope must remain explicit.

### 9.5 Rollback

Rollback is recommendation-only. It requires:

- a previously accepted candidate;
- a typed basis of `regression`, `safety`, or `consumer_rejection`;
- one or more explicit `rollback_evidence_ids` that are inputs to the new episode and were not consumed by any earlier episode in the lineage;
- exact `rollback_subject_candidate_id` resolution to that earlier accepted candidate;
- evidence whose `subject_candidate_id` equals the rollback subject;
- code-owned basis compatibility: `reviewed_candidate_regression` for regression, `reviewed_candidate_safety_failure` for safety, and `independent_consumer_rejection` plus consumer status `rejected` for consumer rejection;
- an immutable prior candidate or consumer pin;
- human review;
- release disposition `rollback_recommended`.

The kernel never executes `git revert`, changes a consumer pin, deletes a release, or changes runtime state. New evidence creates a new episode and does not rewrite the earlier accepted verdict.

## 10. Fixed verification profiles

Manifests reference only:

```text
verification_profile_id
verification_profile_version
```

The code-owned profile registry contains the exact immutable argument vectors, environment, timeout, expected exit behavior, and stable diagnostic code. It rejects unknown profiles and cannot be extended by manifest data.

The same code-owned registry also binds every canonical
`case_id + episode_id` pair to its exact profile identity. Set equality is not
enough: replacing a reference with another known profile, or swapping two
known references, fails before subprocess execution. Adding a reviewed case of
an existing kind requires an explicit binding review but does not require a
core schema change.

### 10.1 `context-resolver-coherence@1`

Runs fixed provider-free pytest selectors covering:

- production-coherent resolver errors;
- unknown persisted terminal statuses;
- resolver errors incompatible with persisted state;
- privacy-safe resolver error projection.

### 10.2 `evaluation-sensitivity@1`

Runs the existing canonical command:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check
```

It reuses the existing six healthy anchors, three one-dimensional controls, evaluator registry, canonical artifacts, and false-green diagnostics. The new kernel does not duplicate replay or evaluator logic.

### 10.3 `strict-citation-consumer@1`

Runs fixed provider-free pytest selectors covering:

- already-cited zero-call success;
- one-call correction success;
- fail-closed safe-state retention;
- exact strict profile identity and version rejection;
- literal generic compatibility;
- the frozen generic downstream fixture rejecting a strict profile.

No profile calls a provider, reads credentials, starts Docker, changes a database schema, or accesses Night Voyager.

## 11. CLI and canonical artifacts

The CLI is:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check

PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py build \
  --json-output /tmp/dra-evidence-gated-loop-v1.json \
  --markdown-output /tmp/dra-evidence-gated-loop-v1.md
```

`check` loads bounded registry and case bytes, executes all referenced fixed profiles, builds the canonical report, and compares it byte-for-byte with committed JSON and Markdown.

`build` writes only to two explicit non-baseline paths. It validates the complete pair before atomic replacement and cleans task-owned temporary files on failure.

There is no `accept`, `promote`, `repair`, `regenerate-baseline`, `release`, or `rollback` command.

Stable public failure codes include:

```text
loop_registry_invalid
loop_case_invalid
loop_evidence_ref_invalid
loop_episode_invalid
loop_diagnosis_invalid
loop_action_invalid
loop_candidate_identity_invalid
loop_verification_profile_invalid
loop_verification_failed
loop_decision_invalid
loop_report_invalid
loop_baseline_invalid
loop_output_invalid
loop_public_output_unsafe
loop_internal_error
```

Public errors expose no raw exception, command output, host path, credential, query, prompt, snippet, trace, or private payload.

## 12. Intended implementation surface

The implementation plan may refine test grouping but must stay within this architecture and these repository surfaces:

```text
benchmarks/evidence-gated-loop-v1/registry.json
benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json
benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json
benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json
scripts/evidence_gated_loop_contracts.py
scripts/evidence_gated_loop_profiles.py
scripts/evidence_gated_loop_gate.py
tests/unit/test_evidence_gated_loop_contracts.py
tests/unit/test_evidence_gated_loop_profiles.py
tests/integration/test_evidence_gated_loop_gate.py
docs/evidence/evidence-gated-loop-kernel-v1.json
docs/evidence/evidence-gated-loop-kernel-v1.md
docs/reference/evidence-gated-loop-kernel.md
docs/decisions/evidence-gated-evolution-authority.md
docs/architecture.md
docs/README.md
docs/evidence/README.md
README.md
README_CN.md
CHANGELOG.md
.github/workflows/ci.yml
tests/unit/test_documentation_contracts.py
tests/unit/test_public_truth_documentation.py
```

The implementation must use the already pinned Pydantic dependency and standard library. It must not add or upgrade a dependency.

The implementation must not modify:

- runtime Agent, profile, finalization, persistence, API, frontend, or migration code;
- existing v1 or v2 evaluation datasets and canonical artifacts;
- existing downstream consumer fixture bytes;
- `VERSION` or release notes;
- Night Voyager;
- provider, model, credential, Docker, or deployment configuration.

## 13. Architecture and documentation

Because this is an offline verification authority, implementation requires:

1. a new ADR defining evidence-gated evolution authority and rejected self-modification alternatives;
2. an architecture update that places the kernel under Verification, not Framework Runtime or Domain Authority;
3. a reference document with commands, reviewer paths, diagnosis codes, update rules, and non-claims;
4. canonical JSON and Markdown evidence indexes;
5. equivalent English and Chinese README command, claim, and boundary text;
6. an `[Unreleased]` changelog entry that does not imply a release.

CI adds one real provider-free kernel `check` step after the existing Evaluation Sensitivity v2 check and before the remaining deterministic proofs and full pytest suite. Default pytest artifact-coherence tests use fixed validated profile results and must not launch a nested real kernel check; the final command matrix likewise runs the real kernel once.

## 14. TDD and negative controls

Implementation starts RED-first. Tests must reject at least:

- unknown or extra schemas and fields;
- duplicate case, evidence, episode, candidate, or profile IDs;
- missing or non-immediate episode predecessors;
- dangling evidence references;
- candidate-owned evidence with a missing or mismatched `subject_candidate_id`;
- malformed commit or tree SHA;
- a change action without a selected carrier or candidate;
- a change action with multiple selected carriers or candidates;
- a no-change action with a selected carrier or candidate;
- selected `model_parameters` in v1;
- candidate carrier and action carrier mismatch;
- accepted verdict with inconclusive diagnosis;
- accepted verdict with failed or inconclusive reviewed candidate verification;
- failed or inconclusive reviewed candidate verification without explicit input evidence IDs;
- failed or inconclusive reviewed candidate verification whose proof kind or
  `subject_candidate_id` does not match the status and exact current candidate;
- a change action with `not_applicable` candidate verification or a no-change action with any other value;
- accepted verdict with missing historical RED;
- any current fixed-profile execution failure, including when the stored verdict is rejected or need-more-evidence;
- a known profile attached to the wrong case or episode;
- release eligibility while required consumer proof is pending or rejected;
- rollback recommendation without an accepted predecessor, exact subject candidate, typed basis, new matching input evidence, or immutable target;
- rollback evidence whose subject or proof kind does not match the code-owned basis matrix;
- manifest-supplied command, selector, import path, environment override, or output path;
- raw content, prompts, queries, snippets, exceptions, credentials, tokens, host paths, or private markers;
- oversized reads, deep nesting, excessive collections, non-canonical ordering, or JSON/Markdown drift;
- partial paired output writes and leaked temporary files;
- raw subprocess output or traceback escaping a stable error boundary.

Tests must also prove:

- all three reference cases validate in canonical order;
- strict citation contains two ordered episodes;
- at least one accepted change and one closed no-change outcome exist;
- valid rejected and need-more-evidence records with failed or inconclusive
  reviewed candidate verification, status-compatible proof kinds, and exact
  candidate-bound input evidence remain structurally green in isolated
  contract tests only when current fixed profiles pass;
- adding a case of an existing kind does not require a core schema change;
- adding an unknown evidence or verification kind fails closed;
- fixed profiles cannot be overridden by manifest bytes or swapped between canonical case/episode bindings;
- mixed episode release dispositions use the exact conservative report-level priority;
- default pytest does not launch a nested real kernel check;
- two builds are byte-identical;
- the committed JSON and Markdown pair is coherent;
- existing Evaluation v1/v2 artifacts and downstream fixture remain unchanged.

## 15. Acceptance criteria

The phase is complete only when:

1. the three reviewed cases and exact identities above are present;
2. every episode has closed evidence, diagnosis, carrier assessment, action, verification, decision, and release semantics;
3. the strict case preserves its change episode and later no-change episode;
4. historical RED and current executable regressions are reported separately;
5. all fixed profiles pass provider-free;
6. canonical JSON and Markdown are byte-stable and match committed baselines;
7. negative controls prove that false acceptance, arbitrary verification, unsafe projection, and invalid rollback fail closed;
8. existing runtime, API, database, dependency, release, v1/v2 evaluation, generic profile, and consumer fixture behavior remains unchanged;
9. focused tests, documentation contracts, full non-Docker pytest, presentation audit, and `git diff --check` pass;
10. hosted CI succeeds on the exact reviewed head;
11. the report records release `hold` and no publication action occurs;
12. public documentation preserves all non-claims.

## 16. Release and rollback disposition

This phase is recorded only under `[Unreleased]`.

Completing and merging the kernel does not authorize `v0.1.7`. A later release decision still requires a separate audit showing either:

1. a coherent bounded release pack; or
2. a real consumer need for a published artifact rather than an immutable commit pin.

Until then, release disposition remains `hold`.

Consumer rollback means retaining or restoring a previously approved immutable pin. Producer rollback means a separately reviewed Git or release action. Neither is executed by the kernel.

## 17. Public claim boundary

After implementation, authority review, merge, and exact-head hosted CI succeed, the repository may state:

> Decision Research Agent includes a provider-free evidence-gated outer-loop kernel for offline reviewed decisions and current-state verification. It preserves three reviewed failure and verification lineages, separates online evidence from offline change decisions, validates fixed retained and safety profiles, records immutable producer and independent consumer proof, and treats reviewed accept, reject, no-change, release hold, and rollback recommendation as explicit outcomes.

The statement must retain personal open-source, provider-free, contract-level, and non-production boundaries.

The project must not claim:

- autonomous or continuous self-improvement;
- runtime self-modification;
- automatic trajectory aggregation, root-cause analysis, candidate generation, promotion, release, or rollback;
- arbitrary historical-candidate checkout or automatic inference of a human verdict from a failed current profile;
- demonstrated knowledge, Prompt/Skill, or model-parameter evolution;
- live-provider strict success;
- production reliability, hosted deployment, SLA, user adoption, or business impact;
- source truth, semantic entailment, citation completeness, or universal Agent quality;
- that post-`v0.1.6` capabilities are included in the `v0.1.6` release.

## 18. Hard stops

Stop and request architecture review if implementation would require:

- runtime, API, database, migration, dependency, consumer, or release changes;
- provider/model calls, credentials, network, Docker, or hosted tracing;
- arbitrary commands or dynamic verification from manifests;
- automatic diagnosis, candidate generation, promotion, release, or rollback;
- changing an existing evaluation baseline or downstream fixture to make the kernel pass;
- treating raw observation or trace content as application truth;
- making a candidate or model the authority for its own verifier or verdict;
- claiming that historical RED was re-executed when only reviewed provenance exists;
- expanding beyond the three reference cases before the v1 contract and retained profiles are proven.

## 19. Required sequence after spec landing

1. Mechanically land this approved spec only.
2. Perform designated-authority review of the actual spec diff.
3. Use `superpowers:writing-plans` to create the implementation plan.
4. Mechanically land the new plan.
5. Run designated-authority Max AutoPlan review on the landed plan.
6. Obtain the implementation approval gate.
7. Execute RED-first implementation in the project execution window.

No later step is implied or authorized by landing this document.
