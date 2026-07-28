# Evidence-Gated Loop Kernel v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan serially, task by task,
> in the existing isolated execution worktree. Do not dispatch subagents or
> parallel lanes: the schemas, three lineage records, fixed verification
> profiles, canonical artifacts, and documentation contracts form one tightly
> coupled authority surface. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Pending designated-authority AutoPlan review and the implementation
gate. Landing this plan does not authorize implementation, dependency
installation, provider/model use, Docker, push, PR, merge, release, deployment,
or cleanup.

**Goal:** Add a provider-free Evidence-Gated Loop Kernel v1 that preserves
three reviewed DRA failure or verification lineages, validates structured
diagnosis and update-carrier decisions, runs fixed retained and safety
verification, and records candidate, consumer, closure, release-hold, and
rollback-recommendation semantics without granting runtime mutation authority.

**Architecture:** Keep online DRA execution unchanged and place the kernel
under offline Verification. Strict Pydantic contracts load bounded,
public-safe registry and case records; a code-owned profile registry runs only
fixed provider-free commands; a deterministic gate renders canonical JSON and
Markdown. Human-reviewed decisions remain data, candidates remain immutable
Git identities, external consumer proof remains a frozen reviewed reference,
and the verifier cannot be supplied or weakened by manifest bytes.

**Tech Stack:** Python 3.11, the repository-pinned Pydantic 2.13.4, Python
standard library (`argparse`, `dataclasses`, `hashlib`, `json`, `os`,
`pathlib`, `re`, `subprocess`, `sys`, `tempfile`, `typing`,
`urllib.parse`), pytest 9.0.3, Markdown, JSON, and GitHub Actions.

## Global Constraints

- Authority spec:
  `docs/superpowers/specs/2026-07-28-evidence-gated-loop-kernel-v1-design.md`
  with SHA-256
  `43d5cb6337f01c5728f62e8858491268f8dd07fd88013a7f4e4e9a0a657d832a`.
- Audited DRA base is
  `01ba21f2996769e68cbc88f4bb0596740df27f6b`; implementation begins only
  from the later commit that contains this reviewed plan.
- Latest Release remains
  `v0.1.6@7d43324b469cb5e445c2e8be83af3be4d841cf1c`. The kernel and all
  referenced post-v0.1.6 capabilities remain `[Unreleased]`.
- Required schemas are exactly:
  `dra.evidence-gated-loop-registry.v1`, `dra.evolution-case.v1`, and
  `dra.evidence-gated-loop-report.v1`.
- The four carrier values are exactly `knowledge`, `prompt_skill`,
  `program_harness`, and `model_parameters`; `no_change` is an action, not a
  carrier; `evaluation_proof` is a change surface, not a carrier.
- Every v1 change episode has exactly one selected carrier and exactly one
  candidate. Multi-carrier work requires consecutive independently reviewable
  episodes; an inseparable composite requires a new schema review.
- Preserve three independent axes:
  `record_status`, `candidate_verdict`, and `closure_status`. Do not add a
  scalar or aggregate `loop_outcome`.
- `model_parameters` remains schema-visible but unsupported. Selecting it
  fails closed.
- Online execution records application-owned state and bounded evidence only.
  The offline kernel does not ingest live traffic, diagnose automatically,
  generate or modify candidates, edit tests/verifiers, promote, publish,
  release, deploy, or execute rollback.
- A green kernel result means the record and required proof are coherent. It
  does not mean every candidate is accepted or a release is authorized.
- External GitHub and Night Voyager evidence is a reviewed immutable
  reference. Required DRA CI performs no network revalidation and makes no
  live-provider success claim.
- Privacy-safe observation PR #127 remains a closed, lossy, diagnostic online
  boundary and is not a fourth evolution-success case. Raw observation data is
  never imported into manifests or reports.
- Historical RED provenance and current executable regression are separate
  report fields. Never claim that DRA CI checks out and reruns historical
  commits.
- The manifest layer supplies no command, argument vector, pytest selector,
  import path, environment override, dynamic tool, URL to execute, or writable
  output path.
- All required execution is provider-free, model-free, credential-free,
  network-free by design, Docker-free, and migration-free. Do not perform a
  third provider attempt.
- Use the existing pinned Pydantic dependency and standard library only. Do
  not add or upgrade a dependency.
- Do not modify runtime Agent/profile/finalization/persistence/API/frontend/
  migration code, Night Voyager, `VERSION`, release notes, existing v1/v2
  evaluation datasets or artifacts, or existing downstream fixture bytes.
- Public outputs must not contain prompts, queries, snippets, raw tool or
  provider payloads, exceptions, tracebacks, credentials, tokens, host paths,
  private markers, or private coordination identifiers.
- CLI failures emit one canonical JSON line with a stable code and no raw
  subprocess output or traceback.
- If any RED requires a runtime/API/database/dependency/consumer/release
  change, dynamic verification, provider/network/Docker access, or mutation of
  an existing baseline/fixture to pass, stop and return to architecture review.

---

## Implementation Approval And Environment Gate

Implementation may start only after the designated review authority has
reviewed the landed plan diff, completed the required AutoPlan review, and
opened the implementation gate. At that time, lock the implementation base
and unchanged spec. Run every command block from the repository root; do not
assume a shell variable survives into a later tool invocation:

```bash
PLAN_PATH=docs/superpowers/plans/2026-07-28-evidence-gated-loop-kernel-v1-implementation-plan.md
SPEC_PATH=docs/superpowers/specs/2026-07-28-evidence-gated-loop-kernel-v1-design.md
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- "$PLAN_PATH")"
test -n "$IMPLEMENTATION_BASE"
test "$(git rev-parse HEAD)" = "$IMPLEMENTATION_BASE"
test "$(git status --porcelain)" = ""
test "$(shasum -a 256 "$SPEC_PATH" | awk '{print $1}')" = \
  43d5cb6337f01c5728f62e8858491268f8dd07fd88013a7f4e4e9a0a657d832a
git show --stat --oneline "$IMPLEMENTATION_BASE" -- "$PLAN_PATH" "$SPEC_PATH"
```

Use the plan-owning commit as the implementation-only diff base, recomputing it
from the exact plan path in any later shell block that needs it. Reuse the
existing task-local `.venv`; this phase adds no dependency and does not
authorize network-backed environment bootstrap. If the interpreter is absent
or its exact pins do not match, return `BLOCKED · DRA_PINNED_ENVIRONMENT_REQUIRED`.
Environment creation or installation requires a separate explicit
authorization and is not part of Tasks 1-7:

```bash
PYTHON_BIN="$PWD/.venv/bin/python"
test -x "$PYTHON_BIN" || {
  echo "DRA_PINNED_ENVIRONMENT_REQUIRED"
  exit 1
}
test "$("$PYTHON_BIN" -c \
  'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = \
  "3.11" || {
  echo "DRA_PINNED_ENVIRONMENT_REQUIRED"
  exit 1
}
```

Verify the existing pins without provider/model initialization:

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" - <<'PY'
from importlib.metadata import PackageNotFoundError, version

expected = {
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

The implementation uses the repository's established Pydantic v2 patterns:
`ConfigDict(extra="forbid", frozen=True, strict=True)`,
`@model_validator(mode="after")`, and a `Field(discriminator="kind")`
union. If implementation requires another Pydantic/framework seam, stop and
return to authority rather than widening scope.

## Exact Planned File Map

Create:

1. `benchmarks/evidence-gated-loop-v1/registry.json`
2. `benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json`
3. `benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json`
4. `benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json`
5. `scripts/evidence_gated_loop_contracts.py`
6. `scripts/evidence_gated_loop_profiles.py`
7. `scripts/evidence_gated_loop_gate.py`
8. `tests/unit/test_evidence_gated_loop_contracts.py`
9. `tests/unit/test_evidence_gated_loop_profiles.py`
10. `tests/integration/test_evidence_gated_loop_gate.py`
11. `docs/evidence/evidence-gated-loop-kernel-v1.json`
12. `docs/evidence/evidence-gated-loop-kernel-v1.md`
13. `docs/reference/evidence-gated-loop-kernel.md`
14. `docs/decisions/evidence-gated-evolution-authority.md`

Modify:

15. `docs/architecture.md`
16. `docs/README.md`
17. `docs/evidence/README.md`
18. `README.md`
19. `README_CN.md`
20. `CHANGELOG.md`
21. `.github/workflows/ci.yml`
22. `tests/unit/test_documentation_contracts.py`
23. `tests/unit/test_public_truth_documentation.py`

Verify-only:

- `agent/`, `api/`, `frontend/`, `migrations/`, `constraints.txt`,
  `requirements.txt`, `VERSION`, `docs/releases/`;
- `benchmarks/agent-evaluation-v1/`,
  `benchmarks/agent-evaluation-v2/`;
- existing `docs/evidence/agent-evaluation-*.json`,
  `docs/evidence/agent-evaluation-*.md`;
- `scripts/downstream_consumer_contract.py` and
  `docs/evidence/downstream-consumer-contract-v1.json`;
- every Night Voyager file.

No other path is authorized.

### Module ownership and dependency direction

Keep imports acyclic and use these exact ownership boundaries:

```text
scripts/evidence_gated_loop_contracts.py
  owns bounded-read/public-safety helpers, core constants, registry/case
  Pydantic models, canonical JSON, and registry/case validators

scripts/evidence_gated_loop_profiles.py
  imports contracts; owns the code-only profile registry, profile result
  model, minimal subprocess environment, and profile runner

scripts/evidence_gated_loop_gate.py
  imports contracts and profiles; owns cross-case/profile coherence, report
  models/validation, rendering, baseline comparison, atomic writes, and CLI
```

The concrete exception ownership is:

```python
class LoopBoundedReadError(ValueError):
    pass

class LoopContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

class LoopProfileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

class LoopGateError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
```

`LoopBoundedReadError` and `LoopContractError` live in contracts,
`LoopProfileError` lives in profiles, and `LoopGateError` lives in the gate.
The gate catches the first three at its public boundary and emits only their
approved stable code. No lower layer imports the gate.

## Locked Contract And Interface Map

### Registry

`benchmarks/evidence-gated-loop-v1/registry.json` has this exact shape:

```json
{
  "case_paths": [
    "benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json",
    "benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json",
    "benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json"
  ],
  "kernel_id": "dra.evidence-gated-loop-kernel",
  "kernel_version": "1",
  "limits": {
    "max_case_bytes": 262144,
    "max_case_count": 32,
    "max_collection_items": 256,
    "max_depth": 16,
    "max_registry_bytes": 65536,
    "max_report_bytes": 2097152,
    "max_text_bytes": 8192
  },
  "non_claims": [
    "No runtime self-modification, automatic diagnosis, candidate generation, promotion, release, or rollback.",
    "No live-provider success, production reliability, user-adoption, business-impact, or universal Agent-quality claim.",
    "Post-v0.1.6 capabilities are not part of the immutable v0.1.6 release."
  ],
  "schema_version": "dra.evidence-gated-loop-registry.v1",
  "verification_profiles": [
    {
      "profile_id": "context-resolver-coherence",
      "profile_version": "1"
    },
    {
      "profile_id": "evaluation-sensitivity",
      "profile_version": "1"
    },
    {
      "profile_id": "strict-citation-consumer",
      "profile_version": "1"
    }
  ]
}
```

Object-key order is canonicalized by serialization; array order is contract.
`case_paths` must be unique, sorted, repository-relative `.json` paths under
the fixed cases directory. The registry accepts up to 32 cases so a future
case using existing evidence and verification kinds does not require a schema
change.

### Evolution case and episode types

The public type names are `EvidenceRef`, `Diagnosis`, `CarrierAssessment`,
`ChangeAction`, `NoChangeAction`, `CapabilityIdentity`, `CandidateRef`,
`VerificationProfileRef`, `ReviewedDecision`, `DecisionEpisode`,
`EvolutionCase`, and `LoopRegistry`. The exact shared aliases are:

```python
Carrier = Literal[
    "knowledge", "prompt_skill", "program_harness", "model_parameters"
]
ChangeSurface = Literal[
    "knowledge", "prompt_skill", "runtime_harness",
    "evaluation_proof", "model_parameters"
]

Action = Annotated[ChangeAction | NoChangeAction, Field(discriminator="kind")]
```

Use these exact field types:

```python
CommitSha = Annotated[
    str, StringConstraints(pattern=r"^[0-9a-f]{40}$")
]

class EvidenceRef(_StrictModel):
    evidence_id: Identifier
    origin_kind: Literal[
        "repository_audit", "verification_gap", "downstream_consumer"
    ]
    repository: PublicText
    commit_sha: CommitSha
    tree_sha: CommitSha
    locator: PublicText
    proof_kind: Literal[
        "reviewed_historical_red",
        "reviewed_verification_gap",
        "independent_consumer_contract",
    ]
    reviewed_summary: PublicText
    claim_scope: PublicText
    public_safe: Literal[True]

class Diagnosis(_StrictModel):
    status: Literal["confirmed", "inconclusive"]
    failure_mode_code: Identifier
    root_cause_layer: Literal[
        "knowledge", "prompt_skill", "program_harness",
        "evaluation_proof", "consumer_contract", "environment",
        "model_parameters",
    ]
    expected_invariant: PublicText
    observed_invariant: PublicText
    scope: PublicText

class CarrierAssessment(_StrictModel):
    carrier: Carrier
    disposition: Literal[
        "selected", "rejected", "unsupported", "deferred"
    ]
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)

class ChangeAction(_StrictModel):
    kind: Literal["change"]
    selected_carrier: Carrier
    change_surface: ChangeSurface
    runtime_effect: Literal["none", "changed"]

class NoChangeAction(_StrictModel):
    kind: Literal["no_change"]
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)

Action = Annotated[
    ChangeAction | NoChangeAction, Field(discriminator="kind")
]

class CapabilityIdentity(_StrictModel):
    profile_id: Identifier
    profile_version: Identifier
    proof_schema: Identifier

class CandidateRef(_StrictModel):
    candidate_id: Identifier
    carrier: Carrier
    change_surface: ChangeSurface
    repository: PublicText
    commit_sha: CommitSha
    tree_sha: CommitSha
    predecessor_or_rollback_ref: CommitSha
    capability_identity: CapabilityIdentity | None

class ReviewedDecision(_StrictModel):
    candidate_verdict: Literal[
        "accepted", "rejected", "need_more_evidence", "not_applicable"
    ]
    consumer_proof_status: Literal[
        "accepted", "rejected", "pending", "not_required"
    ]
    loop_closure_status: Literal[
        "closed_accepted", "closed_rejected", "closed_no_change",
        "open_waiting_evidence", "open_waiting_consumer",
    ]
    release_disposition: Literal[
        "hold", "eligible_for_separate_release_review",
        "rollback_recommended",
    ]
    rollback_target: CommitSha | None
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)

class DecisionEpisode(_StrictModel):
    episode_id: Identifier
    predecessor_episode_id: Identifier | None
    input_evidence_ids: list[Identifier] = Field(min_length=1, max_length=256)
    diagnosis: Diagnosis
    carrier_assessments: list[CarrierAssessment] = Field(
        min_length=4, max_length=4
    )
    action: Action
    candidate_refs: list[CandidateRef] = Field(max_length=1)
    verification_profile_ref: VerificationProfileRef
    reviewed_decision: ReviewedDecision

class EvolutionCase(_StrictModel):
    schema_version: Literal["dra.evolution-case.v1"]
    case_id: Identifier
    case_version: Literal["1"]
    title: PublicText
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=256)
    episodes: list[DecisionEpisode] = Field(min_length=1, max_length=256)
```

All identifier/reason/input lists preserve authored semantic order and reject
duplicates; they are not silently sorted. `validate_public_projection`
enforces UTF-8 byte limits in addition to Pydantic character bounds.

For raw Pydantic shape/type failures, choose the first code in this fixed
specificity order when any error location contains the named segment:

```python
CASE_ERROR_LOCATIONS = (
    ("reviewed_decision", "loop_decision_invalid"),
    ("candidate_refs", "loop_candidate_identity_invalid"),
    ("verification_profile_ref", "loop_verification_profile_invalid"),
    ("action", "loop_action_invalid"),
    ("carrier_assessments", "loop_action_invalid"),
    ("diagnosis", "loop_diagnosis_invalid"),
    ("episodes", "loop_episode_invalid"),
    ("evidence_refs", "loop_evidence_ref_invalid"),
)
```

If none matches, use `loop_case_invalid`. Cross-field validators raise their
own exact code directly instead of relying on Pydantic message text.

The callable interfaces are
`read_bounded_bytes(path: Path, *, limit: int) -> bytes`,
`canonical_json_bytes(value: Any) -> bytes`,
`validate_public_projection(value: Any) -> Any`,
`validate_registry(value: Mapping[str, Any]) -> LoopRegistry`,
`load_registry(path: Path = REGISTRY_PATH) -> LoopRegistry`,
`validate_case(value: Mapping[str, Any]) -> EvolutionCase`, and
`load_case_file(path: Path) -> EvolutionCase`.

Contracts also expose these fixed constants for tests and downstream modules:

```python
PROJECT_ROOT: Path
REGISTRY_PATH: Path
CASES_ROOT: Path
MAX_REGISTRY_BYTES = 65536
MAX_CASE_BYTES = 262144
MAX_REPORT_BYTES = 2097152
MAX_TEXT_BYTES = 8192
MAX_COLLECTION_ITEMS = 256
MAX_DEPTH = 16
REQUIRED_NON_CLAIMS = (
    "No runtime self-modification, automatic diagnosis, candidate "
    "generation, promotion, release, or rollback.",
    "No live-provider success, production reliability, user-adoption, "
    "business-impact, or universal Agent-quality claim.",
    "Post-v0.1.6 capabilities are not part of the immutable v0.1.6 release.",
)
```

All models are strict, frozen, and `extra="forbid"`. `commit_sha` and
`tree_sha` are lowercase 40-hex. IDs match
`[a-z0-9][a-z0-9._-]{0,127}`. Public repository references are inert
HTTPS strings with no userinfo, query, fragment, command, or execution
semantics.

`validate_public_projection` recursively checks only JSON-compatible scalar,
list, and object values. It rejects:

- depth greater than 16, any collection longer than 256, or UTF-8 text longer
  than 8192 bytes;
- non-finite numbers, non-string object keys, NUL/ASCII control characters,
  CR, or LF inside public scalar strings;
- raw-content keys matching `prompt`, `query`, `snippet`, `tool_payload`,
  `provider_payload`, `exception`, `traceback`, `credential`, `password`,
  `secret`, `token`, `thread_id`, or `source_thread_id`, case-insensitively
  after `-` to `_` normalization;
- value markers matching `Traceback`, POSIX home paths such as `/Users/...`
  or `/home/...`, Windows drive/UNC host paths, or credential assignments
  such as `api_key=...`, `password:...`, `secret=...`, and `token:...`.

Bare public-neutral words such as `prompt_skill`, `credentials`, `token
budget`, and `No live-provider strict success` are not rejected. The
assignment/path patterns, forbidden raw-content keys, and structural bounds
are the authority; do not add a broad substring ban that would reject the
approved carrier enums, non-claims, or safety explanations.

Repository validation uses `urllib.parse.urlsplit` and requires exact
`https`, a non-empty hostname, no username/password, query, fragment, or
control characters, and a non-empty public path. It treats the value only as
an inert identity string and never opens it.

Each case has:

```text
schema_version, case_id, case_version, title, evidence_refs, episodes
```

Each evidence reference has:

```text
evidence_id, origin_kind, repository, commit_sha, tree_sha, locator,
proof_kind, reviewed_summary, claim_scope, public_safe
```

Allowed `origin_kind` values are `repository_audit`, `verification_gap`, and
`downstream_consumer`. Allowed `proof_kind` values are
`reviewed_historical_red`, `reviewed_verification_gap`, and
`independent_consumer_contract`. `public_safe` is literal `true`.

Every episode assesses carriers in this exact order:

```text
knowledge, prompt_skill, program_harness, model_parameters
```

with one of `selected`, `rejected`, `unsupported`, or `deferred`.
`model_parameters` must be `unsupported`; no-change episodes select none.

`ChangeAction` fields are exactly:

```text
kind="change", selected_carrier, change_surface,
runtime_effect="none"|"changed"
```

`NoChangeAction` fields are exactly:

```text
kind="no_change", reason_codes
```

The reviewed decision fields and enums are:

```text
candidate_verdict =
  accepted | rejected | need_more_evidence | not_applicable
consumer_proof_status =
  accepted | rejected | pending | not_required
loop_closure_status =
  closed_accepted | closed_rejected | closed_no_change |
  open_waiting_evidence | open_waiting_consumer
release_disposition =
  hold | eligible_for_separate_release_review | rollback_recommended
rollback_target = null | immutable 40-hex commit
reason_codes = non-empty ordered unique identifiers
```

### Exact reference-case matrix

The JSON files must encode the following complete semantic matrix. Text fields
may use the exact public-neutral sentences shown here; they must not add raw
failure content.

#### `context-resolver-projection`

```text
case_version: "1"
title: Context resolver projection false green
evidence:
  context-red
    origin_kind: repository_audit
    repository: https://github.com/iTao-AI/decision-research-agent
    commit_sha: 2dadae56f038790f66c4c3af05b7bae10d8e0462
    tree_sha: 1c27d38370cd9ecbb04b77630b75df9b0c4d46f1
    locator: PR #122 provider-free context regression
    proof_kind: reviewed_historical_red
    reviewed_summary: PR #122 preserved the reviewed provider-free regression
      surface later used to expose context projection false greens.
    claim_scope: incompatible resolver and persisted-state combinations were
      not yet rejected by the retained projection test set
episode: context-projection-episode-1
predecessor: null
inputs: [context-red]
diagnosis:
  status: confirmed
  failure_mode_code: context.projection_false_green
  root_cause_layer: evaluation_proof
  expected_invariant: persisted terminal state and resolver result must form a
    production-coherent pair
  observed_invariant: the retained projection set omitted incompatible pairs
    and unknown terminal enums
  scope: provider-free context projection verification
carrier assessments:
  knowledge: rejected / deterministic_invariant_not_knowledge
  prompt_skill: rejected / deterministic_invariant_not_instruction
  program_harness: selected / executable_projection_verifier
  model_parameters: unsupported / no_training_authority
action:
  kind: change
  selected_carrier: program_harness
  change_surface: evaluation_proof
  runtime_effect: none
candidate:
  candidate_id: context-projection-pr-123
  carrier: program_harness
  change_surface: evaluation_proof
  repository: https://github.com/iTao-AI/decision-research-agent
  commit_sha: 2c50f233c2cc1df4fe2818551e95ab98cd61ede5
  tree_sha: 8da21672e9fd63352e9bc15365818f7edd12d106
  predecessor_or_rollback_ref:
    2dadae56f038790f66c4c3af05b7bae10d8e0462
  capability_identity: null
verification: context-resolver-coherence@1
decision:
  candidate_verdict: accepted
  consumer_proof_status: not_required
  loop_closure_status: closed_accepted
  release_disposition: hold
  rollback_target: 2dadae56f038790f66c4c3af05b7bae10d8e0462
  reason_codes: [historical_red_closed, retained_and_safety_profiles_passed]
```

#### `evaluation-sensitivity`

```text
case_version: "1"
title: Evaluation sensitivity false green
evidence:
  evaluator-gap
    origin_kind: verification_gap
    repository: https://github.com/iTao-AI/decision-research-agent
    commit_sha: 6a3020863fbaaf9d218420b7981150a5736b7fb8
    tree_sha: d6b0dd3a0911125795eb7146bcd659c99233067d
    locator: PR #128 reviewed evaluator-sensitivity gap
    proof_kind: reviewed_verification_gap
    reviewed_summary: Review found that healthy anchors alone did not prove
      that each responsible evaluator detected its declared failure dimension.
    claim_scope: healthy anchors alone did not prove sensitivity to each
      evaluator's declared failure dimension
  evaluator-red
    origin_kind: repository_audit
    repository: https://github.com/iTao-AI/decision-research-agent
    commit_sha: 6a3020863fbaaf9d218420b7981150a5736b7fb8
    tree_sha: d6b0dd3a0911125795eb7146bcd659c99233067d
    locator: PR #128 one-dimensional post-traversal negative controls
    proof_kind: reviewed_historical_red
    reviewed_summary: PR #128 retained one-dimensional post-traversal controls
      that distinguish responsible sensitivity from unrelated drift.
    claim_scope: responsible evaluators had to detect their fixed synthetic
      control while unrelated projections remained stable
episode: evaluation-sensitivity-episode-1
predecessor: null
inputs: [evaluator-gap, evaluator-red]
diagnosis:
  status: confirmed
  failure_mode_code: evaluation.verifier_sensitivity_unproven
  root_cause_layer: evaluation_proof
  expected_invariant: each responsible evaluator detects its declared
    one-dimensional control without unrelated drift
  observed_invariant: a healthy baseline did not establish failure sensitivity
  scope: provider-free Evaluation Sensitivity v2 proof
carrier assessments:
  knowledge: rejected / verifier_gap_not_knowledge
  prompt_skill: rejected / deterministic_verifier_not_instruction
  program_harness: selected / executable_negative_control_harness
  model_parameters: unsupported / no_training_authority
action:
  kind: change
  selected_carrier: program_harness
  change_surface: evaluation_proof
  runtime_effect: none
candidate:
  candidate_id: evaluation-sensitivity-pr-128
  carrier: program_harness
  change_surface: evaluation_proof
  repository: https://github.com/iTao-AI/decision-research-agent
  commit_sha: 6a3020863fbaaf9d218420b7981150a5736b7fb8
  tree_sha: d6b0dd3a0911125795eb7146bcd659c99233067d
  predecessor_or_rollback_ref:
    8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9
  capability_identity: null
verification: evaluation-sensitivity@1
decision:
  candidate_verdict: accepted
  consumer_proof_status: not_required
  loop_closure_status: closed_accepted
  release_disposition: hold
  rollback_target: 8efc7d5a39cc515e15f7ea9b29901f7e6e064ae9
  reason_codes: [verifier_sensitivity_proven, retained_and_safety_profiles_passed]
```

#### `strict-citation-consumer`

```text
case_version: "1"
title: Strict citation downstream consumer failure
evidence:
  strict-live-25-0
    origin_kind: downstream_consumer
    repository: https://github.com/iTao-AI/night-voyager
    commit_sha: 95cce4f28357150450c7f87105adcb47abf1a15d
    tree_sha: 7e310124de9c7d081723eee5b42c152a258b0919
    locator: docs/decisions/0011-dra-v0-1-6-live-consumer-boundary.md
      reviewed 25 Evidence and zero cited summary
    proof_kind: reviewed_historical_red
    reviewed_summary: The first governed live attempt retained 25 same-run
      Evidence rows, produced zero cited rows, and stopped before import.
    claim_scope: governed live attempt stopped before import with 25 same-run
      Evidence rows and zero cited rows
  strict-live-83-0
    origin_kind: downstream_consumer
    repository: https://github.com/iTao-AI/night-voyager
    commit_sha: 95cce4f28357150450c7f87105adcb47abf1a15d
    tree_sha: 7e310124de9c7d081723eee5b42c152a258b0919
    locator: docs/decisions/0011-dra-v0-1-6-live-consumer-boundary.md
      reviewed 83 Evidence and zero cited summary
    proof_kind: reviewed_historical_red
    reviewed_summary: The second governed live attempt retained 83 same-run
      Evidence rows, produced zero cited rows, and stopped before import.
    claim_scope: governed live attempt stopped before import with 83 same-run
      Evidence rows and zero cited rows
  strict-consumer-pr-75
    origin_kind: downstream_consumer
    repository: https://github.com/iTao-AI/night-voyager
    commit_sha: 95cce4f28357150450c7f87105adcb47abf1a15d
    tree_sha: 7e310124de9c7d081723eee5b42c152a258b0919
    locator: PR #75 merge-SHA run 30257237706 with successful python,
      frontend, and compose jobs
    proof_kind: independent_consumer_contract
    reviewed_summary: Night Voyager PR #75 pinned the exact strict producer
      tuple and passed consumer-owned provider-free contract checks.
    claim_scope: exact producer tuple, zero-cited stop, reconciliation, and
      evaluation contracts passed consumer-owned provider-free checks
episode 1: strict-citation-change-episode-1
predecessor: null
inputs: [strict-live-25-0, strict-live-83-0]
diagnosis:
  status: confirmed
  failure_mode_code: citation.delivery_invariant_mismatch
  root_cause_layer: program_harness
  expected_invariant: strict consumers require at least one exact public HTTPS
    citation before candidate import
  observed_invariant: generic delivery could complete with same-run Evidence
    while cited count remained zero
  scope: opt-in strict citation delivery invariant
carrier assessments:
  knowledge: rejected / evidence_rows_already_present
  prompt_skill: rejected / repeated_prompt_changes_not_accepted
  program_harness: selected / deterministic_finalization_invariant
  model_parameters: unsupported / no_training_authority
action:
  kind: change
  selected_carrier: program_harness
  change_surface: runtime_harness
  runtime_effect: changed
candidate:
  candidate_id: strict-citation-pr-129
  carrier: program_harness
  change_surface: runtime_harness
  repository: https://github.com/iTao-AI/decision-research-agent
  commit_sha: 01ba21f2996769e68cbc88f4bb0596740df27f6b
  tree_sha: 06e5282414d3801b11040bba735dd107105e8a30
  predecessor_or_rollback_ref:
    6a3020863fbaaf9d218420b7981150a5736b7fb8
  capability_identity:
    profile_id: generic-strict-citation
    profile_version: "1"
    proof_schema: dra.strict-citation-profile.v1
verification: strict-citation-consumer@1
decision:
  candidate_verdict: accepted
  consumer_proof_status: pending
  loop_closure_status: open_waiting_consumer
  release_disposition: hold
  rollback_target: 6a3020863fbaaf9d218420b7981150a5736b7fb8
  reason_codes: [historical_red_closed, independent_consumer_proof_required]
episode 2: strict-citation-consumer-close-episode-2
predecessor: strict-citation-change-episode-1
inputs: [strict-consumer-pr-75]
diagnosis:
  status: confirmed
  failure_mode_code: consumer.contract_proof_received
  root_cause_layer: consumer_contract
  expected_invariant: an independent consumer pins and validates the exact
    producer tuple without weakening fail-closed behavior
  observed_invariant: PR #75 supplies provider-free contract proof while live
    strict acceptance remains unobserved
  scope: independent provider-free consumer acceptance
carrier assessments:
  knowledge: rejected / no_new_knowledge_change_required
  prompt_skill: rejected / no_new_instruction_change_required
  program_harness: rejected / existing_candidate_closes_contract_gap
  model_parameters: unsupported / no_training_authority
action:
  kind: no_change
  reason_codes: [consumer_proof_accepts_existing_candidate,
    live_provider_retry_not_authorized]
candidate_refs: []
verification: strict-citation-consumer@1
decision:
  candidate_verdict: not_applicable
  consumer_proof_status: accepted
  loop_closure_status: closed_no_change
  release_disposition: hold
  rollback_target: null
  reason_codes: [provider_free_consumer_contract_accepted,
    release_requires_separate_review]
```

Every evidence object also sets `public_safe: true` and uses the exact
`reviewed_summary`/`claim_scope` above. Every episode contains the complete
field set from the spec; arrays are ordered and unique.

### Fixed profile interfaces

`scripts/evidence_gated_loop_profiles.py` defines:

```python
@dataclass(frozen=True)
class VerificationProfile:
    profile_id: str
    profile_version: str
    argv: Sequence[str]
    timeout_seconds: int
    coverage: Sequence[
        Literal["fail_to_pass", "retained", "safety_compatibility"]
    ]
    failure_code: str

class VerificationResult(_StrictModel):
    profile_id: str
    profile_version: str
    provider_free: Literal[True]
    status: Literal["passed"]
    coverage: list[
        Literal["fail_to_pass", "retained", "safety_compatibility"]
    ]
    diagnostic_code: Literal["loop_verification_passed"]

PROFILE_REGISTRY: Mapping[tuple[str, str], VerificationProfile]
```

The callable interfaces are
`run_verification_profile(ref: VerificationProfileRef, *,
project_root: Path = PROJECT_ROOT) -> VerificationResult` and
`run_required_profiles(registry: LoopRegistry, *,
project_root: Path = PROJECT_ROOT) -> tuple[VerificationResult, ...]`.
The concrete dataclass stores `argv` and `coverage` as tuples before exposure.
`run_required_profiles` validates every declared registry identity against
`PROFILE_REGISTRY`, executes each declared identity exactly once in registry
order even when multiple episodes reference it, and returns results in that
same order. A nonzero exit, signal, timeout, missing executable, or OS error
raises `LoopProfileError("loop_verification_failed")`; v1 does not turn a
currently failing executable gate into a green stored report. Structurally
valid `rejected` and `need_more_evidence` episode records are tested
separately, as required by the spec.

`VerificationResult.coverage` is accepted only in this exact order with no
duplicates:

```python
[
    "fail_to_pass",
    "retained",
    "safety_compatibility",
]
```

The three immutable argument vectors are:

```python
CONTEXT_ARGV = (
    sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projects_production_coherent_resolver_errors",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projection_rejects_unknown_persisted_terminal_status",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projection_rejects_resolver_error_incompatible_with_persisted_state",
    "tests/unit/test_agent_evaluation_context.py::"
    "test_projects_resolver_error_without_problem_or_fix",
)

EVALUATION_ARGV = (
    sys.executable, "scripts/agent_evaluation_v2_gate.py", "check",
)

STRICT_ARGV = (
    sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_initial_success_uses_zero_correction_calls",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_correction_success_calls_once_and_persists_exact_url",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_failures_are_closed_and_retain_only_safe_state",
    "tests/integration/test_strict_citation_profile.py::"
    "test_post_insertion_zero_citation_fails_once_without_retry",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_profile_uses_existing_identity_and_manifest_surfaces",
    "tests/integration/test_strict_citation_profile.py::"
    "test_strict_resolver_rejects_nonexact_persisted_profile_version",
    "tests/integration/test_strict_citation_profile.py::"
    "test_literal_generic_zero_citation_remains_ready_without_correction",
    "tests/integration/test_evidence_gated_loop_gate.py::"
    "test_frozen_generic_downstream_fixture_rejects_strict_profile",
    "tests/unit/test_v0_1_6_release_metadata.py::"
    "test_v0_1_6_version_identity_is_consistent",
)
```

Timeouts are 120 seconds for context, 300 seconds for Evaluation Sensitivity
v2, and 180 seconds for strict citation. Every profile declares all three
coverage kinds. Use `subprocess.run(..., shell=False, cwd=project_root,
stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)` with only
these environment values plus present platform temp/path keys:

```python
{
    "PYTHON_DOTENV_DISABLED": "1",
    "LANGCHAIN_TRACING_V2": "false",
    "PYTHONHASHSEED": "0",
}
```

Allowlist inherited names only from
`("PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR")`; never copy the
full environment and never inspect credential-named values. Unknown profile,
nonzero exit, signal, timeout, executable failure, or OS error maps to a
stable kernel code without output.

### Report and CLI

The report top-level closed set is:

```text
schema_version
kernel_id
kernel_version
registry
cases
verification_results
summary
limits
non_claims
```

`registry` is `{sha256, value}`. Each `cases` item is
`{sha256, value}`. Values are revalidated strict models before serialization.
The summary is:

```json
{
  "accepted_candidate_count": 3,
  "case_count": 3,
  "closed_no_change_count": 1,
  "episode_count": 4,
  "need_more_evidence_count": 0,
  "record_status": "valid",
  "rejected_candidate_count": 0,
  "release_disposition": "hold"
}
```

This is a dimensional summary, not an aggregate outcome. The report contains
no timestamp, duration, branch, local path, command output, or network result.
Derive summary release disposition conservatively: any
`rollback_recommended` episode yields `rollback_recommended`; otherwise any
`hold` episode yields `hold`; only a set with no rollback and no hold yields
`eligible_for_separate_release_review`. The three canonical cases therefore
derive `hold`. This field summarizes release authority only and must not be
renamed or reused as a loop outcome.

Public gate constants are `PROJECT_ROOT: Path`, `REGISTRY_PATH: Path`,
`BASELINE_JSON_PATH: Path`, and `BASELINE_MARKDOWN_PATH: Path`. Public
callable interfaces are:

```text
build_report() -> dict[str, Any]
validate_report(value: Mapping[str, Any]) -> dict[str, Any]
serialize_report(report: Mapping[str, Any]) -> bytes
render_markdown(report: Mapping[str, Any]) -> str
compare_artifacts(candidate_report: Mapping[str, Any],
                  candidate_markdown: str,
                  baseline_json: bytes,
                  baseline_markdown: bytes) -> dict[str, Any]
write_artifacts_atomically(report: Mapping[str, Any],
                           markdown: str,
                           *,
                           json_output: Path,
                           markdown_output: Path) -> None
main(argv: Sequence[str] | None = None) -> int
```

All report models and the functions in this block live in
`scripts/evidence_gated_loop_gate.py`; they do not move into contracts or
profiles. `validate_report` reuses `validate_registry`, `validate_case`, and
`VerificationResult.model_validate(..., strict=True)` through one-way imports.

CLI surface is exact:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check

PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py build \
  --json-output /tmp/dra-evidence-gated-loop-v1.json \
  --markdown-output /tmp/dra-evidence-gated-loop-v1.md
```

Success stdout is one canonical line:

```json
{"match":true,"record_status":"valid","status":"valid"}
```

for `check`, and:

```json
{"record_status":"valid","status":"built"}
```

for `build`. Failure stderr is:

```json
{"code":"<stable-code>","status":"invalid"}
```

with empty stdout. Stable codes are exactly those in the spec, including
`loop_internal_error` as the final catch-all.

```python
STABLE_ERROR_CODES = (
    "loop_registry_invalid",
    "loop_case_invalid",
    "loop_evidence_ref_invalid",
    "loop_episode_invalid",
    "loop_diagnosis_invalid",
    "loop_action_invalid",
    "loop_candidate_identity_invalid",
    "loop_verification_profile_invalid",
    "loop_verification_failed",
    "loop_decision_invalid",
    "loop_report_invalid",
    "loop_baseline_invalid",
    "loop_output_invalid",
    "loop_public_output_unsafe",
    "loop_internal_error",
)
```

Parser shape errors map to `loop_output_invalid`; report construction and
validation errors map to `loop_report_invalid`.

`compare_artifacts` returns exactly:

```python
{
    "match": True,
    "record_status": "valid",
    "status": "valid",
}
```

only after candidate JSON, candidate Markdown, baseline JSON, and baseline
Markdown are each canonical, mutually coherent, and byte-equal. Any parse,
schema, canonicalization, Markdown-derivation, or byte-drift failure raises
`LoopGateError("loop_baseline_invalid")`; `check` never emits a false success
payload with `"match": false`.

`main(["--help"])` and `main(["build", "--help"])` return 0 after argparse
writes normal help to stdout. Override parser errors to raise
`loop_output_invalid`, and catch only the help `SystemExit(0)` path; never let
argparse write a raw usage error or traceback for invalid input.

Markdown order is fixed:

1. title and provider-free/offline boundary;
2. record status and dimensional counts;
3. case lineage matrix;
4. evidence and historical RED boundary;
5. fixed verification profile results;
6. candidate, consumer, and closure axes;
7. release hold and recommendation-only rollback;
8. reproduction commands;
9. limits and non-claims.

`build` refuses committed baseline aliases, identical outputs, missing or
non-directory parents, directories, and symlinks. It stages both sibling
temporary files, flushes/fsyncs, validates the complete pair, atomically
replaces targets, restores the first target if the second replace fails, and
cleans task-owned temporary files. `check` bounded-reads fixed baselines,
revalidates JSON, derives Markdown from that JSON, and requires byte equality.

---

### Task 1: Add The Bounded Registry And Public-Safety Foundation

**Files:**

- Create: `benchmarks/evidence-gated-loop-v1/registry.json`
- Create: `scripts/evidence_gated_loop_contracts.py`
- Create: `tests/unit/test_evidence_gated_loop_contracts.py`

**Interfaces:**

- Consumes: the locked registry JSON and global schema constants above.
- Produces: `LoopBoundedReadError`, `LoopContractError`, `_StrictModel`,
  `LoopRegistry`, `VerificationProfileRef`, the fixed path/limit constants,
  `read_bounded_bytes`, `canonical_json_bytes`,
  `validate_public_projection`, `validate_registry`, and `load_registry`.

- [ ] **Step 1: Write RED registry, bounded-I/O, and public-safety tests**

Add these concrete tests and helpers:

```python
REGISTRY_PATH = (
    PROJECT_ROOT / "benchmarks/evidence-gated-loop-v1/registry.json"
)

def _registry_value() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

def test_registry_accepts_exact_closed_provider_free_contract() -> None:
    registry = load_registry()
    assert registry.schema_version == "dra.evidence-gated-loop-registry.v1"
    assert registry.kernel_id == "dra.evidence-gated-loop-kernel"
    assert [ref.profile_id for ref in registry.verification_profiles] == [
        "context-resolver-coherence",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert list(registry.case_paths) == sorted(registry.case_paths)

@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.__setitem__("extra", True),
         "loop_registry_invalid"),
        (lambda value: value["case_paths"].append(value["case_paths"][0]),
         "loop_registry_invalid"),
        (lambda value: value["verification_profiles"].append(
            dict(value["verification_profiles"][0])
        ), "loop_registry_invalid"),
        (lambda value: value["case_paths"].reverse(),
         "loop_registry_invalid"),
        (lambda value: value["case_paths"].__setitem__(0, "../escape.json"),
         "loop_registry_invalid"),
        (lambda value: value["case_paths"].__setitem__(
            0,
            "benchmarks/evidence-gated-loop-v1/cases/nested/case.json",
        ), "loop_registry_invalid"),
        (lambda value: value["verification_profiles"][0].__setitem__(
            "command", ["pytest"]),
         "loop_registry_invalid"),
        (lambda value: value["verification_profiles"][0].__setitem__(
            "selector", "tests/unit/test_private.py"),
         "loop_registry_invalid"),
        (lambda value: value["verification_profiles"][0].__setitem__(
            "import_path", "private.module"),
         "loop_registry_invalid"),
        (lambda value: value["verification_profiles"][0].__setitem__(
            "environment", {"TOKEN": "value"}),
         "loop_registry_invalid"),
        (lambda value: value["verification_profiles"][0].__setitem__(
            "output_path", "/tmp/report"),
         "loop_registry_invalid"),
        (lambda value: value["non_claims"].__setitem__(
            0, "No additional boundary."
        ), "loop_registry_invalid"),
    ],
)
def test_registry_rejects_schema_order_path_and_executable_surface_mutations(
    mutation, code
) -> None:
    value = _registry_value()
    mutation(value)
    with pytest.raises(LoopContractError, match=code):
        validate_registry(value)

def test_bounded_read_stops_at_limit_plus_one(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"x" * (MAX_REGISTRY_BYTES + 1))
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)

def test_registry_requires_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    value = _registry_value()
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)

def test_registry_symlink_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(canonical_json_bytes(_registry_value()))
    link = tmp_path / "registry.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(link)

@pytest.mark.parametrize(
    "unsafe",
    [
        {"items": list(range(MAX_COLLECTION_ITEMS + 1))},
        {"number": float("nan")},
    ],
)
def test_public_projection_rejects_excessive_or_nonfinite_values(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError,
                       match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)

def test_public_projection_rejects_excessive_depth() -> None:
    unsafe: dict[str, object] = {}
    cursor = unsafe
    for index in range(MAX_DEPTH + 1):
        child: dict[str, object] = {}
        cursor[f"level_{index}"] = child
        cursor = child
    with pytest.raises(LoopContractError,
                       match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)

@pytest.mark.parametrize(
    "unsafe",
    [
        {"prompt": "body"},
        {"safe": "Traceback: private"},
        {"safe": "/Users/private/repo"},
        {"safe": "api_key=secret"},
        {"tool_payload": {"value": "body"}},
    ],
)
def test_public_projection_rejects_body_path_trace_and_credentials(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError,
                       match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)
```

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_evidence_gated_loop_contracts.py -k \
  'registry or bounded or public_projection'
```

Expected: FAIL during import or missing registry because the new contract does
not exist.

- [ ] **Step 3: Implement the minimal registry and safety contract**

Use these exact foundations:

```python
import json
import math
import re
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = (
    PROJECT_ROOT / "benchmarks/evidence-gated-loop-v1/registry.json"
)
CASES_ROOT = REGISTRY_PATH.parent / "cases"
MAX_REGISTRY_BYTES = 65536
MAX_CASE_BYTES = 262144
MAX_REPORT_BYTES = 2097152
MAX_TEXT_BYTES = 8192
MAX_COLLECTION_ITEMS = 256
MAX_DEPTH = 16
REQUIRED_NON_CLAIMS = (
    "No runtime self-modification, automatic diagnosis, candidate "
    "generation, promotion, release, or rollback.",
    "No live-provider success, production reliability, user-adoption, "
    "business-impact, or universal Agent-quality claim.",
    "Post-v0.1.6 capabilities are not part of the immutable v0.1.6 release.",
)

class LoopBoundedReadError(ValueError):
    pass

class LoopContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

Identifier = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
]
PublicText = Annotated[str, StringConstraints(min_length=1, max_length=8192)]

class VerificationProfileRef(_StrictModel):
    profile_id: Identifier
    profile_version: Identifier

class RegistryLimits(_StrictModel):
    max_case_bytes: Literal[262144]
    max_case_count: Literal[32]
    max_collection_items: Literal[256]
    max_depth: Literal[16]
    max_registry_bytes: Literal[65536]
    max_report_bytes: Literal[2097152]
    max_text_bytes: Literal[8192]

class LoopRegistry(_StrictModel):
    schema_version: Literal["dra.evidence-gated-loop-registry.v1"]
    kernel_id: Literal["dra.evidence-gated-loop-kernel"]
    kernel_version: Literal["1"]
    case_paths: list[str] = Field(min_length=1, max_length=32)
    verification_profiles: list[VerificationProfileRef] = Field(
        min_length=1, max_length=16
    )
    limits: RegistryLimits
    non_claims: list[PublicText] = Field(min_length=3, max_length=16)

    @model_validator(mode="after")
    def _closed_ordered_registry(self) -> "LoopRegistry":
        if self.case_paths != sorted(set(self.case_paths)):
            raise ValueError("case path order")
        path_pattern = re.compile(
            r"^benchmarks/evidence-gated-loop-v1/cases/"
            r"[a-z0-9][a-z0-9._-]{0,127}\.json$"
        )
        if any(
            path_pattern.fullmatch(path) is None
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            for path in self.case_paths
        ):
            raise ValueError("case path")
        identities = [
            (item.profile_id, item.profile_version)
            for item in self.verification_profiles
        ]
        if identities != sorted(set(identities)):
            raise ValueError("profile order")
        if tuple(self.non_claims) != REQUIRED_NON_CLAIMS:
            raise ValueError("non-claims")
        return self
```

Implement bounded reads, finite/depth/collection checks, forbidden-key and
forbidden-marker scans, strict `model_validate_json(..., strict=True)`,
canonical compact JSON (`sort_keys=True`, `separators=(",", ":")`,
`allow_nan=False`, UTF-8, one trailing newline), and stable error mapping.
Reject a symlink before reading it and require registry bytes to equal their
canonical representation. `read_bounded_bytes` reads at most `limit + 1`
bytes and raises `LoopBoundedReadError` for missing, non-regular, symlink,
I/O, or oversized input; `load_registry` maps that boundary to
`loop_registry_invalid`.

- [ ] **Step 4: Run the Task 1 tests and verify GREEN**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add \
  benchmarks/evidence-gated-loop-v1/registry.json \
  scripts/evidence_gated_loop_contracts.py \
  tests/unit/test_evidence_gated_loop_contracts.py
git diff --cached --check
git commit -m "feat(loop): add bounded kernel registry"
```

### Task 2: Validate Evolution Cases And Episode Decision Semantics

**Files:**

- Create:
  `benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json`
- Create:
  `benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json`
- Create:
  `benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json`
- Modify: `scripts/evidence_gated_loop_contracts.py`
- Modify: `tests/unit/test_evidence_gated_loop_contracts.py`

**Interfaces:**

- Consumes: Task 1 strict models, canonical bytes, safety validation, registry
  paths, and the exact reference-case matrix.
- Produces: `EvidenceRef`, `Diagnosis`, `CarrierAssessment`, discriminated
  `Action`, `CandidateRef`, `ReviewedDecision`, `DecisionEpisode`,
  `EvolutionCase`, `validate_case`, and `load_case_file`.

- [ ] **Step 1: Write RED case and cross-field tests**

Load each canonical case, deep-copy it, and add these exact test families:

```python
def _case(name: str) -> dict[str, object]:
    path = CASES_ROOT / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))

def test_case_file_requires_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    value = _case("context-resolver-projection")
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        load_case_file(path)

def test_case_file_symlink_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(
        canonical_json_bytes(_case("context-resolver-projection"))
    )
    link = tmp_path / "case.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        load_case_file(link)

def set_nested(value: object, path: tuple[object, ...], replacement: object) -> None:
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement

def test_three_reference_cases_and_four_episodes_are_ordered() -> None:
    cases = [
        load_case_file(CASES_ROOT / "context-resolver-projection.json"),
        load_case_file(CASES_ROOT / "evaluation-sensitivity.json"),
        load_case_file(CASES_ROOT / "strict-citation-consumer.json"),
    ]
    assert [case.case_id for case in cases] == [
        "context-resolver-projection",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert [episode.episode_id for episode in cases[2].episodes] == [
        "strict-citation-change-episode-1",
        "strict-citation-consumer-close-episode-2",
    ]

@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case["episodes"][0]["carrier_assessments"].append(
            copy.deepcopy(case["episodes"][0]["carrier_assessments"][2])
        ),
        lambda case: case["episodes"][0]["candidate_refs"].append(
            copy.deepcopy(case["episodes"][0]["candidate_refs"][0])
        ),
        lambda case: case["episodes"][0]["action"].__setitem__(
            "selected_carrier", "knowledge"
        ),
        lambda case: case["episodes"][0]["candidate_refs"][0].__setitem__(
            "carrier", "prompt_skill"
        ),
    ],
)
def test_change_rejects_multiple_or_mismatched_carrier_candidate(
    mutation,
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)

@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case["episodes"][0]["action"].pop(
            "selected_carrier"
        ),
        lambda case: case["episodes"][0].__setitem__(
            "candidate_refs", []
        ),
    ],
)
def test_change_rejects_missing_selected_carrier_or_candidate(
    mutation,
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)

def test_no_change_rejects_selected_carrier_or_candidate() -> None:
    case = _case("strict-citation-consumer")
    episode = case["episodes"][1]
    episode["candidate_refs"] = [
        copy.deepcopy(case["episodes"][0]["candidate_refs"][0])
    ]
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)

def test_inconclusive_diagnosis_cannot_accept_candidate() -> None:
    case = _case("context-resolver-projection")
    case["episodes"][0]["diagnosis"]["status"] = "inconclusive"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)

def test_inconclusive_diagnosis_can_wait_with_no_change() -> None:
    case = _case("context-resolver-projection")
    episode = case["episodes"][0]
    episode["diagnosis"]["status"] = "inconclusive"
    episode["carrier_assessments"][2]["disposition"] = "deferred"
    episode["action"] = {
        "kind": "no_change",
        "reason_codes": ["insufficient_evidence_for_change"],
    }
    episode["candidate_refs"] = []
    episode["reviewed_decision"] = {
        "candidate_verdict": "not_applicable",
        "consumer_proof_status": "not_required",
        "loop_closure_status": "open_waiting_evidence",
        "release_disposition": "hold",
        "rollback_target": None,
        "reason_codes": ["more_reviewed_evidence_required"],
    }
    assert validate_case(case).episodes[0].reviewed_decision \
        .loop_closure_status == "open_waiting_evidence"

def test_accepted_candidate_requires_historical_red() -> None:
    case = _case("evaluation-sensitivity")
    case["episodes"][0]["input_evidence_ids"] = ["evaluator-gap"]
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)

def test_selected_model_parameters_fail_closed() -> None:
    case = _case("context-resolver-projection")
    assessments = case["episodes"][0]["carrier_assessments"]
    assessments[2]["disposition"] = "rejected"
    assessments[3]["disposition"] = "selected"
    case["episodes"][0]["action"]["selected_carrier"] = "model_parameters"
    with pytest.raises(LoopContractError, match="loop_action_invalid"):
        validate_case(case)

@pytest.mark.parametrize(
    ("consumer_status", "verdict", "closure"),
    [
        ("pending", "accepted", "open_waiting_consumer"),
        ("rejected", "rejected", "closed_rejected"),
    ],
)
def test_pending_or_rejected_consumer_cannot_be_release_eligible(
    consumer_status, verdict, closure
) -> None:
    case = _case("strict-citation-consumer")
    decision = case["episodes"][0]["reviewed_decision"]
    decision["consumer_proof_status"] = consumer_status
    decision["candidate_verdict"] = verdict
    decision["loop_closure_status"] = closure
    decision["release_disposition"] = "eligible_for_separate_release_review"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)

def test_accepted_closed_candidate_can_be_eligible_for_separate_review() -> None:
    case = _case("context-resolver-projection")
    decision = case["episodes"][0]["reviewed_decision"]
    decision["release_disposition"] = \
        "eligible_for_separate_release_review"
    decision["reason_codes"] = ["separate_release_review_required"]
    assert validate_case(case).episodes[0].reviewed_decision \
        .release_disposition == "eligible_for_separate_release_review"

def test_rollback_recommendation_requires_accepted_predecessor_and_target() -> None:
    case = _case("strict-citation-consumer")
    evidence = case["evidence_refs"][2]
    evidence["reviewed_summary"] = (
        "A reviewed consumer contract rejected the exact producer tuple "
        "without changing the approved public gate."
    )
    evidence["claim_scope"] = (
        "consumer-owned contract rejection of the exact producer tuple"
    )
    decision = case["episodes"][1]["reviewed_decision"]
    decision["release_disposition"] = "rollback_recommended"
    decision["loop_closure_status"] = "closed_rejected"
    decision["consumer_proof_status"] = "rejected"
    decision["reason_codes"] = ["reviewed_consumer_rejection"]
    decision["rollback_target"] = None
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)
    decision["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    assert validate_case(case).episodes[1].reviewed_decision \
        .release_disposition == "rollback_recommended"

def test_valid_rejected_and_need_more_records_remain_structurally_valid() -> None:
    for verdict, closure in [
        ("rejected", "closed_rejected"),
        ("need_more_evidence", "open_waiting_evidence"),
    ]:
        case = _case("context-resolver-projection")
        decision = case["episodes"][0]["reviewed_decision"]
        decision["candidate_verdict"] = verdict
        decision["loop_closure_status"] = closure
        decision["reason_codes"] = [f"reviewed_{verdict}"]
        assert validate_case(case).episodes[0].reviewed_decision.candidate_verdict \
            == verdict

def test_existing_kind_new_case_requires_no_core_schema_change() -> None:
    case = _case("context-resolver-projection")
    case["case_id"] = "future-context-case"
    case["evidence_refs"][0]["evidence_id"] = "future-red"
    case["episodes"][0]["episode_id"] = "future-episode-1"
    case["episodes"][0]["input_evidence_ids"] = ["future-red"]
    case["episodes"][0]["candidate_refs"][0]["candidate_id"] = \
        "future-candidate"
    assert validate_case(case).case_id == "future-context-case"

@pytest.mark.parametrize(
    ("field_path", "value", "code"),
    [
        (("schema_version",), "dra.evolution-case.v2",
         "loop_case_invalid"),
        (("evidence_refs", 0, "proof_kind"), "new_kind",
         "loop_evidence_ref_invalid"),
        (("episodes", 0, "predecessor_episode_id"), "missing",
         "loop_episode_invalid"),
        (("episodes", 0, "candidate_refs", 0, "commit_sha"),
         "short", "loop_candidate_identity_invalid"),
        (("episodes", 0, "candidate_refs", 0, "tree_sha"),
         "short", "loop_candidate_identity_invalid"),
    ],
)
def test_unknown_kind_predecessor_and_identity_fail_closed(
    field_path, value, code
) -> None:
    case = _case("context-resolver-projection")
    set_nested(case, field_path, value)
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)

@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("evidence", "loop_evidence_ref_invalid"),
        ("candidate", "loop_candidate_identity_invalid"),
    ],
)
@pytest.mark.parametrize(
    "repository",
    [
        "http://example.com/repository",
        "https://user@example.com/repository",
        "https://example.com/repository?run=1",
        "https://example.com/repository#fragment",
        "https://example.com",
    ],
)
def test_repository_identity_is_inert_public_https(
    target, code, repository
) -> None:
    case = _case("context-resolver-projection")
    if target == "evidence":
        case["evidence_refs"][0]["repository"] = repository
    else:
        case["episodes"][0]["candidate_refs"][0]["repository"] = repository
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)
```

Add the remaining closed negative matrix explicitly:

```python
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda case: case["evidence_refs"].append(
                copy.deepcopy(case["evidence_refs"][0])
            ),
            "loop_evidence_ref_invalid",
        ),
        (
            lambda case: case["episodes"][0].__setitem__(
                "input_evidence_ids", ["missing-evidence"]
            ),
            "loop_episode_invalid",
        ),
        (
            lambda case: case["episodes"][0]["diagnosis"].__setitem__(
                "extra", True
            ),
            "loop_diagnosis_invalid",
        ),
        (
            lambda case: case["episodes"][0]["reviewed_decision"].__setitem__(
                "extra", True
            ),
            "loop_decision_invalid",
        ),
        (
            lambda case: case["evidence_refs"][0].__setitem__(
                "reviewed_summary", "Traceback: private"
            ),
            "loop_public_output_unsafe",
        ),
    ],
)
def test_case_reference_section_and_public_safety_fail_closed(
    mutation, code
) -> None:
    case = _case("context-resolver-projection")
    mutation(case)
    with pytest.raises(LoopContractError, match=code):
        validate_case(case)

def test_third_episode_must_reference_immediate_predecessor() -> None:
    case = _case("strict-citation-consumer")
    third = copy.deepcopy(case["episodes"][1])
    third["episode_id"] = "strict-citation-consumer-close-episode-3"
    third["predecessor_episode_id"] = case["episodes"][0]["episode_id"]
    case["episodes"].append(third)
    with pytest.raises(LoopContractError, match="loop_episode_invalid"):
        validate_case(case)

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_verdict", "accepted"),
        ("loop_closure_status", "closed_accepted"),
        ("release_disposition", "rollback_recommended"),
    ],
)
def test_no_change_decision_axes_must_remain_coherent(field, value) -> None:
    case = _case("strict-citation-consumer")
    case["episodes"][1]["reviewed_decision"][field] = value
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)

def test_pending_consumer_cannot_claim_closed_acceptance() -> None:
    case = _case("strict-citation-consumer")
    case["episodes"][0]["reviewed_decision"]["loop_closure_status"] = \
        "closed_accepted"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)

def test_rollback_requires_earlier_accepted_candidate() -> None:
    case = _case("strict-citation-consumer")
    first = case["episodes"][0]["reviewed_decision"]
    first["candidate_verdict"] = "rejected"
    first["consumer_proof_status"] = "not_required"
    first["loop_closure_status"] = "closed_rejected"
    second = case["episodes"][1]["reviewed_decision"]
    second["consumer_proof_status"] = "rejected"
    second["loop_closure_status"] = "closed_rejected"
    second["release_disposition"] = "rollback_recommended"
    second["rollback_target"] = \
        "6a3020863fbaaf9d218420b7981150a5736b7fb8"
    with pytest.raises(LoopContractError, match="loop_decision_invalid"):
        validate_case(case)
```

Cross-case duplicate case/evidence/episode/candidate IDs are covered in Task
4, where all three validated cases are available together. Do not duplicate
that authority in the single-case validator.

- [ ] **Step 2: Run case tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_evidence_gated_loop_contracts.py -k \
  'case or episode or carrier or candidate or decision or existing_kind'
```

Expected: FAIL because case files/models are absent.

- [ ] **Step 3: Implement strict case models and exact JSON records**

Use `Annotated[ChangeAction | NoChangeAction, Field(discriminator="kind")]`.
Catch Pydantic errors at section boundaries and map them to the matching
stable code. In `EvolutionCase` validation:

1. require unique evidence/episode/candidate IDs;
2. require immediate predecessor lineage;
3. require every input evidence ID to resolve;
4. require all four carrier assessments in canonical order;
5. require exactly one selected supported carrier and candidate for change;
6. require no selected carrier/candidate for no-change;
7. bind action carrier/surface to candidate carrier/surface;
8. require accepted candidates to consume at least one
   `reviewed_historical_red`;
9. enforce diagnosis/verdict/consumer/closure/release combinations;
10. validate `rollback_recommended` only on a later no-change episode whose
    `consumer_proof_status` is `rejected`, whose closure is
    `closed_rejected`, whose immediate lineage contains an earlier accepted
    change candidate, and whose immutable `rollback_target` equals that
    candidate's `predecessor_or_rollback_ref`;
11. run `validate_public_projection` over the canonical model dump;
12. reject symlink/oversized/non-regular case inputs and require input file
    bytes to be canonical.

Create the three case files exactly from the locked matrix.

- [ ] **Step 4: Run the whole contract suite and verify GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_evidence_gated_loop_contracts.py
```

Expected: PASS, including valid rejected and need-more-evidence structural
records and the multiple-carrier/candidate negative control.

- [ ] **Step 5: Commit Task 2**

```bash
git add \
  benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json \
  benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json \
  benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json \
  scripts/evidence_gated_loop_contracts.py \
  tests/unit/test_evidence_gated_loop_contracts.py
git diff --cached --check
git commit -m "feat(loop): validate evolution case lineage"
```

### Task 3: Add Code-Owned Fixed Verification Profiles

**Files:**

- Create: `scripts/evidence_gated_loop_profiles.py`
- Create: `tests/unit/test_evidence_gated_loop_profiles.py`
- Create: `tests/integration/test_evidence_gated_loop_gate.py`

**Interfaces:**

- Consumes: Task 1 `LoopRegistry`/`VerificationProfileRef`, the fixed selector
  vectors, and existing provider-free tests/gate.
- Produces: `LoopProfileError`, `VerificationProfile`, `VerificationResult`,
  `PROFILE_REGISTRY`, `run_verification_profile`, and
  `run_required_profiles`.

- [ ] **Step 1: Write RED profile-registry and subprocess-boundary tests**

Add:

```python
def test_profile_registry_owns_exact_commands_timeout_and_coverage() -> None:
    assert list(PROFILE_REGISTRY) == [
        ("context-resolver-coherence", "1"),
        ("evaluation-sensitivity", "1"),
        ("strict-citation-consumer", "1"),
    ]
    assert PROFILE_REGISTRY[("context-resolver-coherence", "1")].argv \
        == CONTEXT_ARGV
    assert PROFILE_REGISTRY[("evaluation-sensitivity", "1")].argv \
        == EVALUATION_ARGV
    assert PROFILE_REGISTRY[("strict-citation-consumer", "1")].argv \
        == STRICT_ARGV
    assert [
        profile.timeout_seconds for profile in PROFILE_REGISTRY.values()
    ] == [120, 300, 180]
    assert all(
        profile.coverage
        == ("fail_to_pass", "retained", "safety_compatibility")
        for profile in PROFILE_REGISTRY.values()
    )

def test_manifest_bytes_cannot_override_profile_command() -> None:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    value["verification_profiles"][0]["argv"] = ["python", "-c", "pass"]
    with pytest.raises(LoopContractError,
                       match="loop_registry_invalid"):
        validate_registry(value)

def test_unknown_profile_fails_closed_without_subprocess(monkeypatch) -> None:
    calls = []
    def unexpected_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("subprocess must not run")
    monkeypatch.setattr(subprocess, "run", unexpected_run)
    with pytest.raises(LoopProfileError,
                       match="loop_verification_profile_invalid"):
        run_verification_profile(
            VerificationProfileRef(
                profile_id="unknown", profile_version="1"
            )
        )
    assert calls == []

def test_runner_uses_shell_false_fixed_cwd_devnull_and_minimal_env(
    monkeypatch, tmp_path
) -> None:
    observed = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read-or-copied")
    def fake_run(argv, **kwargs):
        observed.update(argv=tuple(argv), **kwargs)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_verification_profile(
        VerificationProfileRef(
            profile_id="context-resolver-coherence",
            profile_version="1",
        ),
        project_root=tmp_path,
    )
    assert result.status == "passed"
    assert observed["shell"] is False
    assert observed["cwd"] == tmp_path
    assert observed["stdout"] is subprocess.DEVNULL
    assert observed["stderr"] is subprocess.DEVNULL
    assert observed["env"]["PYTHON_DOTENV_DISABLED"] == "1"
    assert observed["env"]["LANGCHAIN_TRACING_V2"] == "false"
    assert observed["env"]["PYTHONHASHSEED"] == "0"
    assert "OPENAI_API_KEY" not in observed["env"]
    assert set(observed["env"]) <= {
        "PYTHON_DOTENV_DISABLED", "LANGCHAIN_TRACING_V2",
        "PYTHONHASHSEED", "PATH", "TMPDIR", "TEMP", "TMP",
        "SYSTEMROOT", "WINDIR",
    }

def test_required_profiles_run_once_in_registry_order(monkeypatch) -> None:
    calls = []
    def fake_run(ref, **kwargs):
        calls.append((ref.profile_id, ref.profile_version))
        return VerificationResult(
            profile_id=ref.profile_id,
            profile_version=ref.profile_version,
            provider_free=True,
            status="passed",
            coverage=[
                "fail_to_pass", "retained", "safety_compatibility"
            ],
            diagnostic_code="loop_verification_passed",
        )
    monkeypatch.setattr(profiles, "run_verification_profile", fake_run)
    results = run_required_profiles(load_registry())
    assert calls == [
        ("context-resolver-coherence", "1"),
        ("evaluation-sensitivity", "1"),
        ("strict-citation-consumer", "1"),
    ]
    assert [result.profile_id for result in results] == [
        "context-resolver-coherence",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]

@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess(("python",), 1),
        subprocess.TimeoutExpired(("python",), 1),
        OSError("private host detail"),
    ],
)
def test_runner_maps_all_failures_without_raw_output(
    monkeypatch, capsys, outcome
) -> None:
    def fail(*args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(LoopProfileError,
                       match="loop_verification_failed"):
        run_verification_profile(
            VerificationProfileRef(
                profile_id="context-resolver-coherence",
                profile_version="1",
            )
        )
    assert capsys.readouterr() == ("", "")
```

In the integration file add the actual frozen-fixture proof:

```python
def test_frozen_generic_downstream_fixture_rejects_strict_profile() -> None:
    from scripts.downstream_consumer_contract import (
        ContractValidationError,
        build_fixture_bundle,
        validate_fixture_bundle,
    )

    payload = build_fixture_bundle()
    payload["cases"][0]["profile_id"] = "generic-strict-citation"
    with pytest.raises(ContractValidationError,
                       match="contract_schema_invalid"):
        validate_fixture_bundle(payload)
```

- [ ] **Step 2: Run profile tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_evidence_gated_loop_profiles.py \
  tests/integration/test_evidence_gated_loop_gate.py::\
test_frozen_generic_downstream_fixture_rejects_strict_profile
```

Expected: FAIL because the profile module does not exist.

- [ ] **Step 3: Implement the fixed registry and fail-closed runner**

Create frozen dataclasses and Pydantic result model from the locked interface.
Build the subprocess environment only from fixed values and allowlisted
platform keys. Pass the immutable tuple directly; never parse shell text.
Map unknown references to `loop_verification_profile_invalid` and every
execution failure to `loop_verification_failed`. Return only the bounded
identity/coverage result on zero exit. Implement `run_required_profiles` by
iterating `registry.verification_profiles`, not episode references, so the
strict profile shared by two episodes runs once.

- [ ] **Step 4: Run Task 3 tests and each real profile**

Run the Step 2 command, then:

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" - <<'PY'
from scripts.evidence_gated_loop_contracts import load_registry
from scripts.evidence_gated_loop_profiles import run_required_profiles

results = run_required_profiles(load_registry())
assert [item.status for item in results] == ["passed", "passed", "passed"]
print("EVIDENCE_GATED_LOOP_PROFILES_OK")
PY
```

Expected: tests PASS and the final line is
`EVIDENCE_GATED_LOOP_PROFILES_OK`. No provider, credential, network, or
Docker access occurs.

- [ ] **Step 5: Commit Task 3**

```bash
git add \
  scripts/evidence_gated_loop_profiles.py \
  tests/unit/test_evidence_gated_loop_profiles.py \
  tests/integration/test_evidence_gated_loop_gate.py
git diff --cached --check
git commit -m "feat(loop): add fixed verification profiles"
```

### Task 4: Build The Deterministic Report, Gate, And Atomic CLI

**Files:**

- Create: `scripts/evidence_gated_loop_gate.py`
- Modify: `tests/integration/test_evidence_gated_loop_gate.py`

**Interfaces:**

- Consumes: validated canonical registry/cases and successful fixed profile
  results.
- Produces: `LoopGateError`, report models, `validate_kernel_inputs`,
  `validate_report`, `build_report`, `serialize_report`,
  `render_markdown`, `compare_artifacts`,
  `write_artifacts_atomically`, and stable `main`.

- [ ] **Step 1: Write RED report, CLI, drift, and atomic-output tests**

Add these exact behaviors:

```python
def _passing_profile_results() -> tuple[VerificationResult, ...]:
    coverage = ["fail_to_pass", "retained", "safety_compatibility"]
    return tuple(
        VerificationResult(
            profile_id=profile_id,
            profile_version="1",
            provider_free=True,
            status="passed",
            coverage=coverage,
            diagnostic_code="loop_verification_passed",
        )
        for profile_id in (
            "context-resolver-coherence",
            "evaluation-sensitivity",
            "strict-citation-consumer",
        )
    )

@pytest.fixture
def deterministic_report(monkeypatch) -> dict[str, object]:
    monkeypatch.setattr(
        gate,
        "run_required_profiles",
        lambda registry, **kwargs: _passing_profile_results(),
    )
    return gate.build_report()

def test_report_keeps_record_candidate_and_closure_axes_separate(
    deterministic_report
) -> None:
    summary = deterministic_report["summary"]
    assert summary == {
        "accepted_candidate_count": 3,
        "case_count": 3,
        "closed_no_change_count": 1,
        "episode_count": 4,
        "need_more_evidence_count": 0,
        "record_status": "valid",
        "rejected_candidate_count": 0,
        "release_disposition": "hold",
    }
    assert "loop_outcome" not in json.dumps(deterministic_report)

def test_report_binds_registry_case_hashes_and_profile_results(
    deterministic_report
) -> None:
    assert deterministic_report["registry"]["sha256"] == hashlib.sha256(
        canonical_json_bytes(deterministic_report["registry"]["value"])
    ).hexdigest()
    assert len(deterministic_report["cases"]) == 3
    assert [item["value"]["case_id"]
            for item in deterministic_report["cases"]] == [
        "context-resolver-projection",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert [item["status"]
            for item in deterministic_report["verification_results"]] \
        == ["passed", "passed", "passed"]
    assert [
        (
            item["profile_id"],
            item["profile_version"],
            item["coverage"],
        )
        for item in deterministic_report["verification_results"]
    ] == [
        (
            "context-resolver-coherence",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
        (
            "evaluation-sensitivity",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
        (
            "strict-citation-consumer",
            "1",
            ["fail_to_pass", "retained", "safety_compatibility"],
        ),
    ]

@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("case", "loop_case_invalid"),
        ("evidence", "loop_evidence_ref_invalid"),
        ("episode", "loop_episode_invalid"),
        ("candidate", "loop_candidate_identity_invalid"),
    ],
)
def test_cross_case_duplicate_identities_fail_closed(kind, code) -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    if kind == "case":
        values[1]["case_id"] = values[0]["case_id"]
    elif kind == "evidence":
        duplicate = values[0]["evidence_refs"][0]["evidence_id"]
        old = values[1]["evidence_refs"][0]["evidence_id"]
        values[1]["evidence_refs"][0]["evidence_id"] = duplicate
        values[1]["episodes"][0]["input_evidence_ids"] = [
            duplicate if item == old else item
            for item in values[1]["episodes"][0]["input_evidence_ids"]
        ]
    elif kind == "episode":
        values[1]["episodes"][0]["episode_id"] = \
            values[0]["episodes"][0]["episode_id"]
    else:
        values[1]["episodes"][0]["candidate_refs"][0]["candidate_id"] = \
            values[0]["episodes"][0]["candidate_refs"][0]["candidate_id"]
    cases = tuple(validate_case(value) for value in values)
    with pytest.raises(LoopContractError, match=code):
        validate_kernel_inputs(load_registry(), cases)

def test_unknown_verification_profile_fails_closed_before_execution(
    monkeypatch,
) -> None:
    values = [
        _case("context-resolver-projection"),
        _case("evaluation-sensitivity"),
        _case("strict-citation-consumer"),
    ]
    values[0]["episodes"][0]["verification_profile_ref"] = {
        "profile_id": "unknown",
        "profile_version": "1",
    }
    calls = []
    monkeypatch.setattr(
        profiles,
        "run_verification_profile",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(LoopContractError,
                       match="loop_verification_profile_invalid"):
        validate_kernel_inputs(
            load_registry(),
            tuple(validate_case(value) for value in values),
        )
    assert calls == []

def test_registry_case_count_order_and_path_identity_are_exact() -> None:
    registry = load_registry()
    cases = tuple(
        load_case_file(PROJECT_ROOT / path)
        for path in registry.case_paths
    )
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, cases[:-1])
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, tuple(reversed(cases)))
    mutated = _case("context-resolver-projection")
    mutated["case_id"] = "different-case-id"
    mismatched = (validate_case(mutated), *cases[1:])
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        validate_kernel_inputs(registry, mismatched)

def test_declared_unused_unknown_profile_fails_closed() -> None:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    value["verification_profiles"].append(
        {"profile_id": "zz-unknown", "profile_version": "1"}
    )
    registry = validate_registry(value)
    cases = tuple(
        load_case_file(PROJECT_ROOT / path)
        for path in registry.case_paths
    )
    with pytest.raises(LoopContractError,
                       match="loop_verification_profile_invalid"):
        validate_kernel_inputs(registry, cases)

def test_registered_case_symlink_fails_before_case_parse(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(
        canonical_json_bytes(_case("context-resolver-projection"))
    )
    cases_root = tmp_path / "benchmarks/evidence-gated-loop-v1/cases"
    cases_root.mkdir(parents=True)
    link = cases_root / "context-resolver-projection.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_case_invalid"):
        gate._resolve_registered_case_path(
            "benchmarks/evidence-gated-loop-v1/cases/"
            "context-resolver-projection.json",
            project_root=tmp_path,
        )

def test_failed_profile_cannot_build_an_accepted_report(monkeypatch) -> None:
    def fail_profiles(*args, **kwargs):
        raise LoopProfileError("loop_verification_failed")
    monkeypatch.setattr(gate, "run_required_profiles", fail_profiles)
    with pytest.raises(LoopGateError, match="loop_verification_failed"):
        build_report()

def test_two_renderings_are_byte_identical(deterministic_report) -> None:
    assert serialize_report(deterministic_report) \
        == serialize_report(copy.deepcopy(deterministic_report))
    assert render_markdown(deterministic_report) \
        == render_markdown(copy.deepcopy(deterministic_report))

def test_report_enforces_declared_canonical_byte_bound(
    deterministic_report, monkeypatch
) -> None:
    monkeypatch.setattr(gate, "MAX_REPORT_BYTES", 64)
    with pytest.raises(LoopGateError, match="loop_report_invalid"):
        validate_report(deterministic_report)

@pytest.mark.parametrize(
    "missing",
    ["fail_to_pass", "retained", "safety_compatibility"],
)
def test_accepted_report_requires_all_verification_coverage(
    monkeypatch, missing
) -> None:
    results = list(_passing_profile_results())
    first = results[0].model_copy(
        update={
            "coverage": [
                item for item in results[0].coverage if item != missing
            ]
        }
    )
    results[0] = first
    monkeypatch.setattr(
        gate,
        "run_required_profiles",
        lambda registry, **kwargs: tuple(results),
    )
    with pytest.raises(LoopGateError,
                       match="loop_verification_profile_invalid"):
        build_report()

def test_markdown_is_derived_only_from_validated_json(
    deterministic_report
) -> None:
    markdown = render_markdown(deterministic_report)
    assert "provider-free offline verification" in markdown
    assert "Release disposition: `hold`" in markdown
    assert "live-provider strict success" in markdown
    unsafe = copy.deepcopy(deterministic_report)
    unsafe["cases"][0]["value"]["title"] = "/private/example/path"
    with pytest.raises(LoopGateError,
                       match="loop_public_output_unsafe"):
        render_markdown(unsafe)

def test_build_refuses_baseline_alias_and_identical_outputs(
    deterministic_report, tmp_path
) -> None:
    markdown = render_markdown(deterministic_report)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            markdown,
            json_output=BASELINE_JSON_PATH,
            markdown_output=tmp_path / "report.md",
        )
    same = tmp_path / "same"
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            markdown,
            json_output=same,
            markdown_output=same,
        )

def test_build_refuses_symlink_output_without_mutating_target(
    deterministic_report, tmp_path
) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"unchanged\n")
    link = tmp_path / "report.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=link,
            markdown_output=tmp_path / "report.md",
        )
    assert target.read_bytes() == b"unchanged\n"
    assert link.is_symlink()

@pytest.mark.parametrize(
    "json_output_factory",
    [
        lambda root: root / "missing-parent/report.json",
        lambda root: root,
    ],
)
def test_build_refuses_missing_parent_and_directory_target(
    deterministic_report, tmp_path, json_output_factory
) -> None:
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output_factory(tmp_path),
            markdown_output=tmp_path / "report.md",
        )

def test_compare_rejects_noncanonical_json_markdown_drift_and_byte_drift(
    deterministic_report
) -> None:
    candidate_json = serialize_report(deterministic_report)
    candidate_markdown = render_markdown(deterministic_report)
    pretty_json = (
        json.dumps(deterministic_report, indent=2).encode("utf-8") + b"\n"
    )
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            pretty_json,
            candidate_markdown.encode("utf-8"),
        )
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            candidate_json,
            (candidate_markdown + "\n").encode("utf-8"),
        )
    drifted = copy.deepcopy(deterministic_report)
    drifted["cases"][0]["value"]["title"] = \
        "Context resolver projection reviewed lineage"
    drifted["cases"][0]["sha256"] = hashlib.sha256(
        canonical_json_bytes(drifted["cases"][0]["value"])
    ).hexdigest()
    with pytest.raises(LoopGateError, match="loop_baseline_invalid"):
        compare_artifacts(
            deterministic_report,
            candidate_markdown,
            serialize_report(drifted),
            render_markdown(drifted).encode("utf-8"),
        )

def test_second_replace_failure_restores_first_and_leaves_no_temps(
    deterministic_report, tmp_path, monkeypatch
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    json_output.write_bytes(b"old-json\n")
    markdown_output.write_bytes(b"old-markdown\n")
    actual_replace = os.replace
    calls = 0
    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("private replace detail")
        actual_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert json_output.read_bytes() == b"old-json\n"
    assert markdown_output.read_bytes() == b"old-markdown\n"
    assert list(tmp_path.glob(".*.tmp")) == []

def test_second_replace_failure_removes_new_first_when_no_prior_file(
    deterministic_report, tmp_path, monkeypatch
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    actual_replace = os.replace
    calls = 0
    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("private replace detail")
        actual_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert not json_output.exists()
    assert not markdown_output.exists()
    assert list(tmp_path.glob(".*.tmp")) == []

def test_oversized_existing_output_fails_before_mutation(
    deterministic_report, tmp_path
) -> None:
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    json_output.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
    markdown_output.write_bytes(b"old-markdown\n")
    with pytest.raises(LoopGateError, match="loop_output_invalid"):
        write_artifacts_atomically(
            deterministic_report,
            render_markdown(deterministic_report),
            json_output=json_output,
            markdown_output=markdown_output,
        )
    assert json_output.stat().st_size == MAX_REPORT_BYTES + 1
    assert markdown_output.read_bytes() == b"old-markdown\n"

def test_cli_error_matrix_has_one_safe_json_line(monkeypatch, capsys) -> None:
    for code in STABLE_ERROR_CODES:
        def fail_known(args, *, selected_code=code):
            raise LoopGateError(selected_code)
        monkeypatch.setattr(gate, "_run", fail_known)
        assert main(["check"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == json.dumps(
            {"code": code, "status": "invalid"},
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n"
    def fail_private(args):
        raise RuntimeError("private host detail")
    monkeypatch.setattr(gate, "_run", fail_private)
    assert main(["check"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == \
        '{"code":"loop_internal_error","status":"invalid"}\n'
    assert "private host detail" not in captured.err

@pytest.mark.parametrize("argv", [["--help"], ["build", "--help"]])
def test_cli_help_is_successful(argv, capsys) -> None:
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert captured.err == ""

def test_cli_shape_error_is_stable(capsys) -> None:
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == \
        '{"code":"loop_output_invalid","status":"invalid"}\n'
```

- [ ] **Step 2: Run gate tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/integration/test_evidence_gated_loop_gate.py -k \
  'report or duplicate or registry_case or declared_unused or registered_case or unknown_verification or rendering or markdown or build or compare or cli'
```

Expected: FAIL because the report/gate interfaces do not exist.

- [ ] **Step 3: Implement report validation and cross-case coherence**

Add strict report models matching the locked top-level set. Load case paths
from the validated registry, resolve them under `PROJECT_ROOT`, reject symlink
or escape, and validate:

```python
def _resolve_registered_case_path(
    relative_path: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    cases_root = (
        project_root / "benchmarks/evidence-gated-loop-v1/cases"
    )
    candidate = project_root / relative_path
    try:
        if candidate.is_symlink():
            raise OSError
        resolved_root = cases_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        if (
            not resolved.is_relative_to(resolved_root)
            or not resolved.is_file()
        ):
            raise OSError
        return resolved
    except OSError:
        raise LoopContractError("loop_case_invalid") from None

def _load_kernel_inputs() -> tuple[LoopRegistry, tuple[EvolutionCase, ...]]:
    registry = load_registry(REGISTRY_PATH)
    cases = tuple(
        load_case_file(_resolve_registered_case_path(path))
        for path in registry.case_paths
    )
    validate_kernel_inputs(registry, cases)
    return registry, cases

def validate_kernel_inputs(
    registry: LoopRegistry,
    cases: Sequence[EvolutionCase],
) -> None:
    expected_case_ids = [
        Path(path).stem for path in registry.case_paths
    ]
    actual_case_ids = [case.case_id for case in cases]
    if (
        len(cases) != len(registry.case_paths)
        or actual_case_ids != expected_case_ids
    ):
        raise LoopContractError("loop_case_invalid")
    identity_sets = {
        "loop_case_invalid": actual_case_ids,
        "loop_evidence_ref_invalid": [
            item.evidence_id for case in cases for item in case.evidence_refs
        ],
        "loop_episode_invalid": [
            item.episode_id for case in cases for item in case.episodes
        ],
        "loop_candidate_identity_invalid": [
            candidate.candidate_id
            for case in cases
            for episode in case.episodes
            for candidate in episode.candidate_refs
        ],
    }
    for code, identities in identity_sets.items():
        if len(identities) != len(set(identities)):
            raise LoopContractError(code)
    declared = [
        (item.profile_id, item.profile_version)
        for item in registry.verification_profiles
    ]
    referenced = []
    for case in cases:
        for episode in case.episodes:
            identity = (
                episode.verification_profile_ref.profile_id,
                episode.verification_profile_ref.profile_version,
            )
            if identity not in referenced:
                referenced.append(identity)
    if (
        set(referenced) != set(declared)
        or any(identity not in PROFILE_REGISTRY for identity in declared)
    ):
        raise LoopContractError("loop_verification_profile_invalid")
```

Use these report model fields; no report field is optional:

```python
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

class HashedRegistry(_StrictModel):
    sha256: Sha256
    value: LoopRegistry

class HashedCase(_StrictModel):
    sha256: Sha256
    value: EvolutionCase

class ReportSummary(_StrictModel):
    accepted_candidate_count: int = Field(ge=0, le=256)
    case_count: int = Field(ge=1, le=32)
    closed_no_change_count: int = Field(ge=0, le=256)
    episode_count: int = Field(ge=1, le=256)
    need_more_evidence_count: int = Field(ge=0, le=256)
    record_status: Literal["valid"]
    rejected_candidate_count: int = Field(ge=0, le=256)
    release_disposition: Literal[
        "hold",
        "eligible_for_separate_release_review",
        "rollback_recommended",
    ]

class LoopReport(_StrictModel):
    schema_version: Literal["dra.evidence-gated-loop-report.v1"]
    kernel_id: Literal["dra.evidence-gated-loop-kernel"]
    kernel_version: Literal["1"]
    registry: HashedRegistry
    cases: list[HashedCase] = Field(min_length=1, max_length=32)
    verification_results: list[VerificationResult] = Field(
        min_length=1, max_length=16
    )
    summary: ReportSummary
    limits: RegistryLimits
    non_claims: list[str] = Field(min_length=3, max_length=16)
```

Build the report only after every declared fixed profile passes. Derive all
summary counts from canonical episode decisions; do not copy a summary from a
manifest. `validate_report` must revalidate the embedded registry and cases,
recompute every SHA-256, require verification results to match the declared
profile order and coverage, recompute the dimensional summary, and compare
limits/non-claims with the registry. Revalidate the complete public projection
and canonical byte bound before serialization. Map any contracts/profile
exception at this layer to `LoopGateError` with the same approved code; map
report-model or recomputation mismatch to `loop_report_invalid`.

- [ ] **Step 4: Implement deterministic Markdown, compare, atomic pair, and CLI**

Use the existing `agent_evaluation_v2_gate.py` atomic-write mechanics, but
implement these exact v1 differences:

1. `_resolve_output` rejects the raw path when `is_symlink()` is true before
   resolving it; it then rejects either baseline alias, identical resolved
   outputs, a missing/non-directory parent, and a directory target.
2. `_stage_file` creates one sibling `NamedTemporaryFile(delete=False)`,
   writes the complete bytes, flushes, and `fsync`s before returning it.
3. `write_artifacts_atomically` validates report/Markdown coherence, stages
   both files, bounded-reads an existing first target for rollback, replaces
   JSON then Markdown, restores or removes JSON if the second replace fails,
   and unlinks only its own remaining temporary files in `finally`.
4. `compare_artifacts` requires baseline JSON bytes to equal
   `serialize_report(validated_baseline)`, requires baseline Markdown bytes to
   equal `render_markdown(validated_baseline).encode("utf-8")`, and then
   requires both candidate byte streams to equal both baselines. Any mismatch
   is `loop_baseline_invalid`.
5. `render_markdown` revalidates first, escapes `|` in table cells, rejects
   CR/LF in scalar cells through public-safety validation, and renders only
   the nine locked sections.

Implement the parser/public boundary with this control shape:

```python
class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise LoopGateError("loop_output_invalid")

def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="evidence_gated_loop_gate.py")
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=_ArgumentParser,
    )
    build = commands.add_parser("build")
    build.add_argument("--json-output", type=Path, required=True)
    build.add_argument("--markdown-output", type=Path, required=True)
    commands.add_parser("check")
    return parser

def _error(code: str) -> int:
    sys.stderr.write(
        json.dumps(
            {"code": code, "status": "invalid"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 1

def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        return _run(args)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        return _error("loop_output_invalid")
    except (LoopGateError, LoopProfileError, LoopContractError) as exc:
        return _error(exc.code)
    except Exception:
        return _error("loop_internal_error")

if __name__ == "__main__":
    raise SystemExit(main())
```

`_run` emits sorted compact JSON with the exact success shapes already
locked. It reads baselines with `read_bounded_bytes(...,
limit=MAX_REPORT_BYTES)` and maps all baseline read failures to
`loop_baseline_invalid`. Do not import or call runtime Agent modules.

- [ ] **Step 5: Run Task 4 tests and verify GREEN**

Run the Step 2 command without `-k`.

Expected: PASS. Profile-runner calls inside deterministic report tests are
monkeypatched to fixed validated `VerificationResult` values; the real
provider-free profiles remain covered by Task 3 and the final gate command.

- [ ] **Step 6: Commit Task 4**

```bash
git add \
  scripts/evidence_gated_loop_gate.py \
  tests/integration/test_evidence_gated_loop_gate.py
git diff --cached --check
git commit -m "feat(loop): add deterministic evidence gate"
```

### Task 5: Generate Canonical Evidence And Prove The Three Real Lineages

**Files:**

- Create: `docs/evidence/evidence-gated-loop-kernel-v1.json`
- Create: `docs/evidence/evidence-gated-loop-kernel-v1.md`
- Modify: `tests/integration/test_evidence_gated_loop_gate.py`

**Interfaces:**

- Consumes: all three canonical case records, fixed real profiles, and Task 4
  build/check CLI.
- Produces: committed canonical evidence and integration proof of case order,
  strict two-episode closure, dimensional decisions, byte stability, and
  baseline coherence.

- [ ] **Step 1: Write RED committed-baseline and real-lineage tests**

Add:

```python
def _provider_free_test_env() -> dict[str, str]:
    result = {
        "PYTHON_DOTENV_DISABLED": "1",
        "LANGCHAIN_TRACING_V2": "false",
        "PYTHONHASHSEED": "0",
    }
    for name in (
        "PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR"
    ):
        if name in os.environ:
            result[name] = os.environ[name]
    return result

def test_strict_case_preserves_change_then_no_change_lineage() -> None:
    case = load_case_file(
        CASES_ROOT / "strict-citation-consumer.json"
    )
    first, second = case.episodes
    assert first.action.kind == "change"
    assert first.reviewed_decision.candidate_verdict == "accepted"
    assert first.reviewed_decision.consumer_proof_status == "pending"
    producer = first.candidate_refs[0]
    assert producer.commit_sha == \
        "01ba21f2996769e68cbc88f4bb0596740df27f6b"
    assert producer.tree_sha == \
        "06e5282414d3801b11040bba735dd107105e8a30"
    assert producer.capability_identity is not None
    assert producer.capability_identity.model_dump() == {
        "profile_id": "generic-strict-citation",
        "profile_version": "1",
        "proof_schema": "dra.strict-citation-profile.v1",
    }
    assert second.predecessor_episode_id == first.episode_id
    assert second.action.kind == "no_change"
    assert second.reviewed_decision.candidate_verdict == "not_applicable"
    assert second.reviewed_decision.consumer_proof_status == "accepted"
    assert second.reviewed_decision.loop_closure_status == "closed_no_change"
    consumer = next(
        item for item in case.evidence_refs
        if item.evidence_id == "strict-consumer-pr-75"
    )
    assert consumer.commit_sha == \
        "95cce4f28357150450c7f87105adcb47abf1a15d"
    assert consumer.tree_sha == \
        "7e310124de9c7d081723eee5b42c152a258b0919"
    assert consumer.locator == (
        "PR #75 merge-SHA run 30257237706 with successful python, "
        "frontend, and compose jobs"
    )
    assert "live-provider" not in consumer.claim_scope

def test_reference_case_git_identities_are_exact() -> None:
    context = load_case_file(
        CASES_ROOT / "context-resolver-projection.json"
    )
    evaluation = load_case_file(
        CASES_ROOT / "evaluation-sensitivity.json"
    )
    strict = load_case_file(
        CASES_ROOT / "strict-citation-consumer.json"
    )
    observed = [
        (
            context.evidence_refs[0].commit_sha,
            context.evidence_refs[0].tree_sha,
            context.episodes[0].candidate_refs[0].commit_sha,
            context.episodes[0].candidate_refs[0].tree_sha,
        ),
        (
            evaluation.evidence_refs[0].commit_sha,
            evaluation.evidence_refs[0].tree_sha,
            evaluation.episodes[0].candidate_refs[0].commit_sha,
            evaluation.episodes[0].candidate_refs[0].tree_sha,
        ),
        (
            strict.evidence_refs[0].commit_sha,
            strict.evidence_refs[0].tree_sha,
            strict.episodes[0].candidate_refs[0].commit_sha,
            strict.episodes[0].candidate_refs[0].tree_sha,
        ),
    ]
    assert observed == [
        (
            "2dadae56f038790f66c4c3af05b7bae10d8e0462",
            "1c27d38370cd9ecbb04b77630b75df9b0c4d46f1",
            "2c50f233c2cc1df4fe2818551e95ab98cd61ede5",
            "8da21672e9fd63352e9bc15365818f7edd12d106",
        ),
        (
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
            "d6b0dd3a0911125795eb7146bcd659c99233067d",
            "6a3020863fbaaf9d218420b7981150a5736b7fb8",
            "d6b0dd3a0911125795eb7146bcd659c99233067d",
        ),
        (
            "95cce4f28357150450c7f87105adcb47abf1a15d",
            "7e310124de9c7d081723eee5b42c152a258b0919",
            "01ba21f2996769e68cbc88f4bb0596740df27f6b",
            "06e5282414d3801b11040bba735dd107105e8a30",
        ),
    ]

def test_historical_red_and_executable_profiles_are_distinct(
    deterministic_report
) -> None:
    evidence = [
        ref for item in deterministic_report["cases"]
        for ref in item["value"]["evidence_refs"]
    ]
    assert any(ref["proof_kind"] == "reviewed_historical_red"
               for ref in evidence)
    assert all(
        result["status"] == "passed"
        for result in deterministic_report["verification_results"]
    )
    assert "historical RED was re-executed" not in \
        json.dumps(deterministic_report)

def test_committed_json_and_markdown_match_fresh_build() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evidence_gated_loop_gate.py", "check"],
        cwd=PROJECT_ROOT,
        env=_provider_free_test_env(),
        text=True,
        capture_output=True,
        check=False,
        timeout=660,
    )
    assert completed.returncode == 0
    assert completed.stdout == (
        '{"match":true,"record_status":"valid","status":"valid"}\n'
    )
    assert completed.stderr == ""

def test_two_builds_are_byte_identical(
    deterministic_report,
) -> None:
    second = gate.build_report()
    assert serialize_report(deterministic_report) \
        == serialize_report(second) \
        == BASELINE_JSON_PATH.read_bytes()
    assert render_markdown(deterministic_report).encode("utf-8") \
        == render_markdown(second).encode("utf-8") \
        == BASELINE_MARKDOWN_PATH.read_bytes()
```

- [ ] **Step 2: Run the new integration tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/integration/test_evidence_gated_loop_gate.py -k \
  'strict_case or historical_red or committed_json or two_builds'
```

Expected: FAIL because committed canonical evidence is absent.

- [ ] **Step 3: Build the canonical pair to explicit temporary paths**

```bash
TMP_DIR="$(mktemp -d)"
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/evidence_gated_loop_gate.py build \
  --json-output "$TMP_DIR/evidence-gated-loop-kernel-v1.json" \
  --markdown-output "$TMP_DIR/evidence-gated-loop-kernel-v1.md"
shasum -a 256 \
  "$TMP_DIR/evidence-gated-loop-kernel-v1.json" \
  "$TMP_DIR/evidence-gated-loop-kernel-v1.md"
printf 'JSON_SOURCE=%s\nMARKDOWN_SOURCE=%s\n' \
  "$TMP_DIR/evidence-gated-loop-kernel-v1.json" \
  "$TMP_DIR/evidence-gated-loop-kernel-v1.md"
```

Expected stdout:

```json
{"record_status":"valid","status":"built"}
```

Read back the two printed source paths, then copy their exact validated bytes
to the exact committed paths using `apply_patch`; do not use `cp` and do not
add a baseline-regeneration CLI. Re-run `cmp` between each source and its
committed destination before proceeding.

- [ ] **Step 4: Verify the committed pair and full kernel integration**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_evidence_gated_loop_contracts.py \
  tests/unit/test_evidence_gated_loop_profiles.py \
  tests/integration/test_evidence_gated_loop_gate.py
```

Expected: canonical check exits 0 with exact valid JSON stdout; all tests
PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add \
  docs/evidence/evidence-gated-loop-kernel-v1.json \
  docs/evidence/evidence-gated-loop-kernel-v1.md \
  tests/integration/test_evidence_gated_loop_gate.py
git diff --cached --check
git commit -m "test(loop): retain three reviewed loop lineages"
```

### Task 6: Document Verification Authority, Architecture, And Reviewer Path

**Files:**

- Create: `docs/reference/evidence-gated-loop-kernel.md`
- Create: `docs/decisions/evidence-gated-evolution-authority.md`
- Modify: `docs/architecture.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**

- Consumes: implemented schemas, CLI, evidence pair, and the authority
  boundaries proven by Tasks 1-5.
- Produces: durable ADR, architecture placement under Verification, operator
  and reviewer reference, evidence index entries, and executable doc
  contracts.

- [ ] **Step 1: Write RED documentation contracts**

Add exact assertions:

```python
def test_evidence_gated_loop_reference_locks_commands_and_nonclaims() -> None:
    text = LOOP_REFERENCE.read_text(encoding="utf-8")
    for phrase in (
        "dra.evidence-gated-loop-registry.v1",
        "dra.evolution-case.v1",
        "dra.evidence-gated-loop-report.v1",
        "python scripts/evidence_gated_loop_gate.py check",
        "historical RED",
        "fixed verification profile",
        "record_status",
        "candidate_verdict",
        "closure_status",
        "release `hold`",
        "recommendation-only rollback",
        "No runtime self-modification",
        "No live-provider strict success",
    ):
        assert phrase in text

def test_evidence_gated_evolution_adr_keeps_verifier_outside_candidate() -> None:
    text = LOOP_ADR.read_text(encoding="utf-8")
    for phrase in (
        "Status: Accepted",
        "Offline Verification",
        "candidate cannot modify",
        "verification profile registry",
        "human-reviewed verdict",
        "consumer-owned proof",
        "privacy-safe observation",
        "not a fourth evolution-success case",
        "runtime self-modification",
        "automatic release",
    ):
        assert phrase in text

def test_architecture_places_loop_kernel_under_verification() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "Evidence-Gated Loop Kernel" in text
    assert "Verification" in text
    assert "Framework Runtime" in text
    assert "does not own application state" in text

def test_loop_indexes_use_repository_relative_links() -> None:
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    evidence_index = EVIDENCE_INDEX.read_text(encoding="utf-8")
    assert (
        "[Evidence-Gated Loop Kernel]"
        "(reference/evidence-gated-loop-kernel.md)"
    ) in docs_index
    assert (
        "[Evidence-Gated Evolution Authority]"
        "(decisions/evidence-gated-evolution-authority.md)"
    ) in docs_index
    assert (
        "[JSON](evidence-gated-loop-kernel-v1.json)"
    ) in evidence_index
    assert (
        "[Markdown](evidence-gated-loop-kernel-v1.md)"
    ) in evidence_index
    assert (
        "[Reference](../reference/evidence-gated-loop-kernel.md)"
    ) in evidence_index
```

- [ ] **Step 2: Run documentation tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_documentation_contracts.py -k evidence_gated
```

Expected: FAIL because documents/indexes are absent.

- [ ] **Step 3: Write the ADR and reference with exact authority boundaries**

The ADR sections are:

```text
# ADR: Evidence-Gated Evolution Authority
Status: Accepted
Context
Decision
Authority Matrix
Candidate And Verifier Isolation
Online Execution / Offline Verification
Release And Rollback
Rejected Alternatives
Consequences
Non-Claims
```

Reject runtime self-modification, manifest-supplied verification, hosted
EvalOps, model-owned verdicts, automatic release/rollback, and multiple new
Agent roles. State that candidate generation is outside v1 and that a future
new evidence/proof kind requires adapter/profile review.

The reference sections are:

```text
# Evidence-Gated Loop Kernel
What It Proves
What It Does Not Prove
Schemas And Case Lineage
Diagnosis And Carrier Selection
Fixed Verification Profiles
Commands
Reading The JSON And Markdown
Accept, Reject, Need More Evidence, And No Change
Independent Consumer Proof
Release Hold And Recommendation-Only Rollback
Adding A Reviewed Case Of An Existing Kind
When A New Kind Requires Review
Stable Error Codes
Reviewer Checklist
Non-Claims
```

Use the exact CLI, schema values, carrier enum, three decision axes, and hard
stops from this plan.

- [ ] **Step 4: Update architecture and indexes**

Place the kernel in the architecture Verification section. State that it reads
reviewed public-safe offline records, executes fixed provider-free profiles,
and owns neither application truth nor runtime mutation. Add reference/ADR and
JSON/Markdown links to `docs/README.md` and `docs/evidence/README.md` using
the exact repository-relative link literals asserted above.

- [ ] **Step 5: Run documentation contracts and verify GREEN**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add \
  docs/reference/evidence-gated-loop-kernel.md \
  docs/decisions/evidence-gated-evolution-authority.md \
  docs/architecture.md \
  docs/README.md \
  docs/evidence/README.md \
  tests/unit/test_documentation_contracts.py
git diff --cached --check
git commit -m "docs(loop): define evidence-gated authority"
```

### Task 7: Publish The Bilingual Boundary, CI Gate, And Full Verification

**Files:**

- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_public_truth_documentation.py`

**Interfaces:**

- Consumes: completed kernel/check command, public reference, evidence pair,
  and current CI ordering.
- Produces: equivalent English/Chinese public wording, `[Unreleased]` truth,
  required provider-free CI, and final public-truth guards.

- [ ] **Step 1: Write RED public-truth and CI-order tests**

Add:

```python
def test_readmes_publish_equivalent_bounded_loop_kernel_claim() -> None:
    english = README.read_text(encoding="utf-8")
    chinese = README_CN.read_text(encoding="utf-8")
    for text in (english, chinese):
        assert "Evidence-Gated Loop Kernel" in text
        assert "provider-free" in text
        assert "three reviewed" in text or "三个已审查" in text
        assert "accept" in text or "接受" in text
        assert "reject" in text or "拒绝" in text
        assert "no-change" in text or "不修改" in text
        assert "release" in text or "发布" in text
        assert "rollback" in text or "回滚" in text
        assert "v0.1.6" in text

def test_ci_runs_loop_after_v2_and_before_remaining_proofs() -> None:
    text = CI.read_text(encoding="utf-8")
    v2 = "python scripts/agent_evaluation_v2_gate.py check"
    loop = "python scripts/evidence_gated_loop_gate.py check"
    next_gate = "python scripts/run_creation_idempotency_proof.py check"
    assert text.index(v2) < text.index(loop) < text.index(next_gate)
    assert "PYTHON_DOTENV_DISABLED: '1'" in text

def test_unreleased_changelog_does_not_claim_release_or_runtime_evolution() -> None:
    unreleased = _unreleased_section()
    normalized = " ".join(unreleased.split())
    assert "Evidence-Gated Loop Kernel" in unreleased
    assert "provider-free" in unreleased
    assert "release remains on hold" in normalized
    assert "not runtime self-modification" in normalized
    assert (
        "not runtime self-modification, live-provider success, "
        "or a v0.1.7 release"
    ) in normalized
    for forbidden in (
        "autonomous self-improvement",
        "implements runtime self-modification",
        "demonstrates live-provider strict success",
        "released in v0.1.7",
    ):
        assert forbidden not in normalized

def test_readmes_link_commands_schemas_and_nonclaims() -> None:
    for text in (
        README.read_text(encoding="utf-8"),
        README_CN.read_text(encoding="utf-8"),
    ):
        for required in (
            "python scripts/evidence_gated_loop_gate.py check",
            "[Evidence-Gated Loop Kernel]"
            "(docs/reference/evidence-gated-loop-kernel.md)",
            "[canonical JSON]"
            "(docs/evidence/evidence-gated-loop-kernel-v1.json)",
            "dra.evidence-gated-loop-registry.v1",
            "dra.evolution-case.v1",
            "dra.evidence-gated-loop-report.v1",
        ):
            assert required in text
        assert (
            "not runtime self-modification" in text
            or "不是运行时自修改" in text
        )
        assert (
            "not a v0.1.7 release" in text
            or ("不证明" in text and "v0.1.7 已发布" in text)
        )
```

- [ ] **Step 2: Run public-truth tests and observe RED**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py -k \
  'evidence_gated or loop_kernel'
```

Expected: FAIL because README/CI/changelog surfaces are not updated.

- [ ] **Step 3: Update README, Chinese README, changelog, and CI**

Under the existing required CI proof inventory sections, add these reviewed
copies verbatim, placing each near the current Evaluation Sensitivity v2
proof. Preserve the surrounding README structure.

English:

````markdown
### Evidence-Gated Loop Kernel

Evidence-Gated Loop Kernel v1 preserves three reviewed failure and verification
lineages, executes fixed provider-free retained and safety profiles, keeps
online application state separate from offline change decisions, and records
accept, reject, need-more-evidence, no-change, release hold, and rollback
recommendation explicitly. Its public schemas are
`dra.evidence-gated-loop-registry.v1`, `dra.evolution-case.v1`, and
`dra.evidence-gated-loop-report.v1`.

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
```

See the [Evidence-Gated Loop Kernel](docs/reference/evidence-gated-loop-kernel.md)
and its [canonical JSON](docs/evidence/evidence-gated-loop-kernel-v1.json).
This provider-free contract proof is not runtime self-modification, live-provider
strict success, production reliability, or a v0.1.7 release. The immutable
v0.1.6 release does not contain the post-v0.1.6 kernel.
````

Chinese:

````markdown
### Evidence-Gated Loop Kernel

Evidence-Gated Loop Kernel v1 固化了三个已审查的失败或验证谱系，以固定、
provider-free 的保留集与安全检查复核候选，并把在线应用状态与离线变更决策分开。
它显式记录接受、拒绝、需要更多证据、不修改、发布保持 hold 与回滚建议。公开
schema 为 `dra.evidence-gated-loop-registry.v1`、`dra.evolution-case.v1` 和
`dra.evidence-gated-loop-report.v1`。

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
```

详情见 [Evidence-Gated Loop Kernel](docs/reference/evidence-gated-loop-kernel.md)
及其 [canonical JSON](docs/evidence/evidence-gated-loop-kernel-v1.json)。
这项 provider-free contract proof 不是运行时自修改，也不证明 live-provider
strict success、生产可靠性或 v0.1.7 已发布；不可变的 v0.1.6 release 不包含这一
post-v0.1.6 kernel。
````

At the top of `[Unreleased]`, add:

```markdown
### Evidence-gated loop kernel

- Added a provider-free offline verification kernel for three reviewed DRA
  failure and verification lineages, with fixed retained/safety profiles,
  immutable candidate and consumer identities, explicit accept/reject/
  no-change decisions; release remains on hold. This is not runtime
  self-modification, live-provider success, or a v0.1.7 release.
```

Insert exactly this CI step after Evaluation Sensitivity v2 and before the
idempotency proof:

```yaml
      - name: Run evidence-gated loop kernel
        env:
          PYTHON_DOTENV_DISABLED: '1'
        run: python scripts/evidence_gated_loop_gate.py check
```

- [ ] **Step 4: Run focused docs/CI and kernel verification**

```bash
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/evidence_gated_loop_gate.py check
```

Expected: PASS and exact canonical valid stdout.

- [ ] **Step 5: Run the full non-Docker verification matrix**

```bash
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- \
  docs/superpowers/plans/2026-07-28-evidence-gated-loop-kernel-v1-implementation-plan.md)"
test -n "$IMPLEMENTATION_BASE"
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" -m pytest -q -m "not docker"
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/final_presentation_audit.py --root .
PYTHON_DOTENV_DISABLED=1 "$PWD/.venv/bin/python" \
  scripts/check_canonical_identity.py --root .
git diff --check
git diff --check "$IMPLEMENTATION_BASE"
```

Expected: all commands exit 0; the presentation and identity audits report
`"status": "ok"` with no violations. No Docker/frontend/provider run is
required because those surfaces are unchanged.

- [ ] **Step 6: Verify forbidden-surface immutability and public safety**

```bash
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- \
  docs/superpowers/plans/2026-07-28-evidence-gated-loop-kernel-v1-implementation-plan.md)"
test -n "$IMPLEMENTATION_BASE"
test -z "$(git diff --name-only "$IMPLEMENTATION_BASE" -- \
  agent api frontend migrations constraints.txt requirements.txt VERSION \
  docs/releases \
  benchmarks/agent-evaluation-v1 benchmarks/agent-evaluation-v2 \
  scripts/downstream_consumer_contract.py \
  docs/evidence/downstream-consumer-contract-v1.json)"

! rg -n \
  '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
  benchmarks/evidence-gated-loop-v1 \
  scripts/evidence_gated_loop_contracts.py \
  scripts/evidence_gated_loop_profiles.py \
  scripts/evidence_gated_loop_gate.py \
  docs/evidence/evidence-gated-loop-kernel-v1.json \
  docs/evidence/evidence-gated-loop-kernel-v1.md \
  docs/reference/evidence-gated-loop-kernel.md \
  docs/decisions/evidence-gated-evolution-authority.md

! rg -n \
  '/Users/|/home/|/private/|Traceback|api[_-]?key[=:]|credential[=:]|password[=:]|secret[=:]|token[=:]|thread_id|source_thread_id' \
  benchmarks/evidence-gated-loop-v1 \
  docs/evidence/evidence-gated-loop-kernel-v1.json \
  docs/evidence/evidence-gated-loop-kernel-v1.md \
  docs/reference/evidence-gated-loop-kernel.md \
  docs/decisions/evidence-gated-evolution-authority.md
```

The first scan catches actual local identities across code and artifacts. The
second applies raw-payload markers only to data and prose, because contracts
code intentionally contains generic rejection patterns such as `/Users/` and
`token=`. Inspect any match; do not weaken validators or delete safety tests to
make a scan green.

- [ ] **Step 7: Commit Task 7**

```bash
git add \
  README.md \
  README_CN.md \
  CHANGELOG.md \
  .github/workflows/ci.yml \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py
git diff --cached --check
git commit -m "ci(loop): require evidence-gated kernel proof"
```

- [ ] **Step 8: Final implementation-only diff audit**

```bash
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- \
  docs/superpowers/plans/2026-07-28-evidence-gated-loop-kernel-v1-implementation-plan.md)"
test -n "$IMPLEMENTATION_BASE"
git status --short --branch
git diff --name-status "$IMPLEMENTATION_BASE"..HEAD
git diff --stat "$IMPLEMENTATION_BASE"..HEAD
git log --oneline "$IMPLEMENTATION_BASE"..HEAD
git diff --check "$IMPLEMENTATION_BASE"..HEAD
test "$(git status --porcelain --untracked-files=all | \
  rg -v '^.. \\.venv/' || true)" = ""
```

Expected:

- only the 23 exact planned files changed;
- no task-owned staged, dirty, or untracked file remains;
- seven semantic implementation commits exist after the plan commit;
- release disposition remains `hold`;
- no push, PR, merge, tag, Release, deploy, or cleanup has occurred.

## Verification And Review Handoff

The implementer returns the exact branch/worktree, final HEAD, commit list,
file list, focused/full commands and outcomes, canonical JSON stdout,
immutable-surface diff check, public-safety scan, and remaining risks. It does
not publish.

The designated review authority then:

1. reviews the actual branch diff against the spec and this plan;
2. runs one findings-only authoritative GStack review before PR;
3. returns verified findings to the implementer for targeted repair;
4. performs targeted re-review on the repaired HEAD;
5. asks for publication authorization only after the reviewed HEAD, clean
   state, and required local evidence are exact.

Hosted CI success on the exact reviewed PR head remains an acceptance
criterion. It is not claimed by local execution.

## Hard Stops And Non-Claims

Stop implementation immediately if:

- a manifest must define or alter executable verification;
- a candidate or model must modify its verifier, test, verdict, or release
  gate;
- runtime, API, database, migration, dependency, consumer, existing
  evaluation baseline, downstream fixture, or release files must change;
- provider/model credentials, network, Docker, hosted tracing, or a third
  provider attempt becomes necessary;
- historical RED can only be represented by pretending it was re-executed;
- a new evidence/proof kind is needed without an explicit adapter and profile
  review;
- scope expands beyond the three reference cases before v1 proof closes.

Even after implementation, merge, and exact-head hosted CI, do not claim
autonomous/continuous self-improvement, runtime self-modification, automatic
trajectory aggregation/diagnosis/candidate generation/promotion/release/
rollback, demonstrated knowledge/Prompt/Skill/model-parameter evolution,
live-provider strict success, production reliability, hosted deployment, SLA,
user adoption, business impact, source truth, semantic entailment, citation
completeness, universal Agent quality, or inclusion of post-v0.1.6
capabilities in v0.1.6.
