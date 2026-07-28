# Consumer-Derived Loop Proof v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan serially, task by task,
> in the existing isolated execution worktree. Do not dispatch subagents or
> parallel lanes: the manifest, validator, retained selector allowlist,
> generated evidence, CI ordering, and bilingual documentation form one
> tightly coupled contract. Every behavior task is RED-first and ends with a
> semantic atomic commit.

**Status:** Pending AutoPlan review and explicit user approval. Landing this
plan does not authorize implementation, dependency installation, provider or
model use, Docker, publication, or release.

**Goal:** Add one provider-free, deterministic, consumer-derived Loop
Engineering proof that turns two already reviewed downstream fail-closed
observations into a structured diagnosis, records why the existing strict
citation candidate used the `program/Harness` carrier, runs a fixed retained
regression set, accepts or rejects immutable producer and independent consumer
proof explicitly, and keeps release plus rollback as separate human-owned
decisions.

**Architecture:** A reviewed immutable manifest is the only proof input. A
project-owned standard-library validator fails closed on any missing Loop link
or non-exact identity, derives canonical JSON and Markdown evidence, checks
committed-artifact drift, and launches only nine fixed provider-free pytest
selectors. Online Agent execution remains evidence-only; all diagnosis,
carrier selection, candidate evaluation, acceptance, release hold, and
rollback disposition remain offline. No runtime authority, profile behavior,
Prompt, Skill, Agent role, database state, or consumer repository is changed.

**Tech Stack:** Python 3.11 standard library (`argparse`, `hashlib`, `json`,
`os`, `pathlib`, `re`, `stat`, `subprocess`, `sys`, `tempfile`,
`urllib.parse`), pytest 9.0.3, the existing strict-citation and compatibility
tests, canonical JSON/Markdown, and GitHub Actions Backend Tests. No new
package, framework abstraction, hosted evaluation service, provider-backed
lane, Docker lane, migration, or frontend change is permitted.

**Agent-engineering lens:** This plan directly applies the relevant original
chapters of 《深入理解 AI Agent：设计原理与工程实践》 rather than using
“Loop Engineering” as a label. Chapter 1 keeps deterministic control and
verification in the Harness around the model. Chapter 2 requires choosing the
smallest update carrier and forbids converting one failure into an automatic
permanent Prompt/Skill rule. Chapter 4 favors a fixed, parameter-faithful tool
surface instead of dynamic tool discovery. Chapter 6 separates observation
from evaluation and requires real failure evidence, retained FAIL_TO_PASS and
PASS_TO_PASS coverage, safety vetoes, and deterministic external feedback.
Chapter 8 keeps online execution evidence-only while offline evolution
aggregates trajectories, diagnoses root cause, creates or selects an isolated
candidate, verifies it, and makes an explicit release/rollback decision.
Chapter 10 treats independent consumer execution and tests as genuinely new
information, uses explicit artifact handoff, and rejects extra Agent roles or
same-chain debate that would amplify error without adding evidence. The book
supplies the design and interview-explanation lens; live repository code,
tests, CI, immutable Git/GitHub identities, Release state, and independent
consumer proof remain factual authority.

---

## Global Constraints

- Authority spec:
  `docs/superpowers/specs/2026-07-28-consumer-derived-loop-proof-v1-design.md`.
- Audited producer base:
  `01ba21f2996769e68cbc88f4bb0596740df27f6b`.
- Latest Release remains
  `v0.1.6@7d43324b469cb5e445c2e8be83af3be4d841cf1c`; the strict profile is
  post-v0.1.6 and must never be rewritten as part of that release.
- Strict producer identity is exactly:
  `https://github.com/iTao-AI/decision-research-agent` +
  `01ba21f2996769e68cbc88f4bb0596740df27f6b` +
  `generic-strict-citation@1` + `profile_version=1` +
  `proof_schema=dra.strict-citation-profile.v1`.
- DRA PR #129 identity is exact: reviewed HEAD
  `3ddb8bafc9947ca6b521547177e7a327291dcdf8`, squash merge
  `01ba21f2996769e68cbc88f4bb0596740df27f6b`, and reviewed/merge tree
  `06e5282414d3801b11040bba735dd107105e8a30`.
- Night Voyager PR #75 remains consumer-owned evidence: repository
  `https://github.com/iTao-AI/night-voyager`, reviewed HEAD
  `a7d6eee704537a0876396d56e483485ef77b291b`, squash merge
  `95cce4f28357150450c7f87105adcb47abf1a15d`, reviewed/merge tree
  `7e310124de9c7d081723eee5b42c152a258b0919`, and merge-SHA run
  `30257237706` with successful `python`, `frontend`, and `compose` jobs.
  Current consumer baseline `19bd17ad35131435e7dbec4a33fe939c9976007c`
  may be recorded separately but cannot replace the PR #75 proof identity.
- The two public-safe consumer failure summaries are exactly Evidence/cited
  `25/0` and `83/0`. Both stopped before candidate import and mutated no
  candidate, promotion, planning, review, or decision state. Do not add raw
  queries, Markdown, URLs from Evidence rows, provider payloads, private
  receipt IDs, local paths, credentials, or model output.
- Root cause is exactly
  `generic delivery invariant < strict consumer delivery invariant`.
- The original candidate carrier is `program/Harness`; the current closeout
  carrier is `evaluation/proof-only`; the current runtime decision is
  `no-change`.
- This is not an automated diagnosis engine, candidate generator, generic
  EvalOps platform, new replay Harness, runtime self-modification loop,
  automatic release workflow, or live-provider retry.
- Required commands are provider-free, network-free by design, credential-free,
  and Docker-free. Do not perform a third provider attempt.
- Keep all runtime and business authority unchanged. `agent/`, `api/`, database,
  migrations, profile registry, Prompt/Skill behavior, dependencies,
  `VERSION`, release notes/tags, existing Evidence, the frontend, and Night
  Voyager are verify-only and must not change.
- No arbitrary pytest selector, manifest path, baseline path, repository URL,
  branch/ref, provider input, or output body may be supplied to
  `run-retained`.
- CLI failures emit one canonical JSON line only, with no traceback, exception
  text, pytest output, fixture body, host path, environment value, credential,
  or external payload.
- The proof commit does not replace the strict producer pin and does not require
  a consumer re-pin. Release remains `HOLD`; a later `v0.1.7` decision requires
  a separately coherent release pack or a real consumer need for a published
  artifact.
- If any RED requires runtime code, a new framework seam, provider/network
  access, another consumer mutation, or a file outside the exact map below,
  stop and return to architecture authority with the preserved RED evidence.

## Implementation Approval And Environment Gate

Implementation may start only after this plan has been reviewed by AutoPlan
and the user has explicitly approved the complete reviewed plan. At that time,
derive the implementation base from the latest commit touching this plan:

```bash
PLAN_PATH=docs/superpowers/plans/2026-07-28-consumer-derived-loop-proof-v1-implementation-plan.md
IMPLEMENTATION_BASE="$(git log -1 --format=%H -- "$PLAN_PATH")"
test -n "$IMPLEMENTATION_BASE"
test "$(git status --porcelain)" = ""
git show --stat --oneline "$IMPLEMENTATION_BASE" -- "$PLAN_PATH"
SPEC_PATH=docs/superpowers/specs/2026-07-28-consumer-derived-loop-proof-v1-design.md
test "$(shasum -a 256 "$SPEC_PATH" | awk '{print $1}')" = \
  0eb0fc153ef5a9544789c7ca537c21d6767e547e4c2e7d47637587fb33d33580
```

Use `"$IMPLEMENTATION_BASE"..HEAD` for the implementation-only allowlist.
The execution task must use Python 3.11 and the exact committed constraints.
One task-local `.venv` and one installation of the unchanged exact pins are
part of the plan only if the user approves the complete plan. Resolve an
authority-supplied absolute Python 3.11 interpreter; never hard-code a personal
host path in the repository:

```bash
case "${DRA_BOOTSTRAP_PYTHON:-}" in
  /*) ;;
  *) echo "DRA_BOOTSTRAP_PYTHON_REQUIRED"; exit 1 ;;
esac
test -x "$DRA_BOOTSTRAP_PYTHON"
test "$("$DRA_BOOTSTRAP_PYTHON" -c \
  'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = \
  "3.11"
if test ! -x .venv/bin/python; then
  "$DRA_BOOTSTRAP_PYTHON" -m venv .venv
  "$PWD/.venv/bin/python" -m pip install --no-deps -r constraints.txt
fi
DRA_PYTHON_BIN="$PWD/.venv/bin/python"
```

Then verify the exact environment without provider/model initialization:

```bash
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

If this gate fails after the one approved exact-pin installation, stop with
`DRA_PINNED_ENVIRONMENT_REQUIRED`. Do not change a pin, add a dependency, use
the system Python 3.9/3.13, or switch to Docker. No Context7 lookup is required
because this slice adds no framework API use; if implementation unexpectedly
requires a framework API, stop and return to authority instead of expanding
scope.

## Exact Planned File Map

Create:

1. `benchmarks/consumer-derived-loop-v1/manifest.json`
2. `scripts/consumer_derived_loop_proof.py`
3. `tests/unit/test_consumer_derived_loop_proof.py`
4. `docs/evidence/consumer-derived-loop-proof-v1.json`
5. `docs/evidence/consumer-derived-loop-proof-v1.md`
6. `docs/reference/consumer-derived-loop-proof.md`

Modify:

7. `.github/workflows/ci.yml`
8. `README.md`
9. `README_CN.md`
10. `docs/README.md`
11. `docs/evidence/README.md`
12. `CHANGELOG.md`

Verify-only:

- `agent/`, `api/`, `frontend/`, `migrations/`, `constraints.txt`,
  `requirements.txt`, `VERSION`, `docs/releases/`, every existing Evidence
  artifact, every existing spec/plan, and all Night Voyager files.

No other path is authorized. If an existing documentation contract test needs
modification rather than the new proof test owning the new contract, stop and
return to authority instead of expanding the file map.

## Locked Manifest And Report Contract

### Manifest

`benchmarks/consumer-derived-loop-v1/manifest.json` uses canonical JSON
(sorted keys, two-space indentation, UTF-8, one trailing newline) and exact
top-level keys in this order-independent closed set:

```text
schema_version
loop_id
scope
producer_baseline
failure_receipts
diagnosis
carrier_decision
candidate
retained_regressions
independent_consumer_proof
decision
rollback
non_claims
```

The reviewed nested value contract is:

```json
{
  "schema_version": "dra.consumer-derived-loop-manifest.v1",
  "loop_id": "strict-citation-consumer-loop-v1",
  "scope": {
    "mode": "offline_evaluation_proof",
    "online_execution": "evidence_only",
    "offline_evolution": "reviewed_candidate_verification",
    "runtime_change": "none"
  },
  "producer_baseline": {
    "latest_release": {
      "tag": "v0.1.6",
      "commit": "7d43324b469cb5e445c2e8be83af3be4d841cf1c"
    },
    "strict_candidate": {
      "commit": "01ba21f2996769e68cbc88f4bb0596740df27f6b",
      "profile_id": "generic-strict-citation",
      "profile_version": "1",
      "proof_schema": "dra.strict-citation-profile.v1"
    }
  },
  "failure_receipts": [
    {
      "failure_id": "consumer-live-acceptance-25-0",
      "evidence_count": 25,
      "cited_count": 0,
      "stopped_before_candidate_import": true,
      "mutations": {
        "candidate": false,
        "promotion": false,
        "planning": false,
        "review": false,
        "decision": false
      }
    },
    {
      "failure_id": "consumer-live-acceptance-83-0",
      "evidence_count": 83,
      "cited_count": 0,
      "stopped_before_candidate_import": true,
      "mutations": {
        "candidate": false,
        "promotion": false,
        "planning": false,
        "review": false,
        "decision": false
      }
    }
  ],
  "diagnosis": {
    "classification": "delivery_invariant_mismatch",
    "root_cause": "generic delivery invariant < strict consumer delivery invariant"
  },
  "carrier_decision": {
    "knowledge": "reject",
    "prompt_or_skill": "reject",
    "program_or_harness": "accept_existing_candidate",
    "current_runtime_change": "no-change",
    "current_phase": "evaluation/proof-only"
  },
  "candidate": {
    "repository": "https://github.com/iTao-AI/decision-research-agent",
    "commit": "01ba21f2996769e68cbc88f4bb0596740df27f6b",
    "profile_id": "generic-strict-citation",
    "profile_version": "1",
    "proof_schema": "dra.strict-citation-profile.v1",
    "pull_request": {
      "number": 129,
      "reviewed_head": "3ddb8bafc9947ca6b521547177e7a327291dcdf8",
      "merge_commit": "01ba21f2996769e68cbc88f4bb0596740df27f6b",
      "reviewed_tree": "06e5282414d3801b11040bba735dd107105e8a30",
      "merge_tree": "06e5282414d3801b11040bba735dd107105e8a30"
    }
  },
  "retained_regressions": {
    "runner": "pytest",
    "provider_free": true,
    "selectors": [
      "tests/integration/test_strict_citation_profile.py::test_literal_generic_zero_citation_remains_ready_without_correction",
      "tests/integration/test_strict_citation_profile.py::test_strict_initial_success_uses_zero_correction_calls",
      "tests/integration/test_strict_citation_profile.py::test_strict_correction_success_calls_once_and_persists_exact_url",
      "tests/integration/test_strict_citation_profile.py::test_post_insertion_zero_citation_fails_once_without_retry",
      "tests/integration/test_strict_citation_profile.py::test_strict_failures_are_closed_and_retain_only_safe_state",
      "tests/integration/test_strict_citation_profile.py::test_strict_profile_uses_existing_identity_and_manifest_surfaces",
      "tests/integration/test_strict_citation_profile.py::test_strict_resolver_rejects_nonexact_persisted_profile_version",
      "tests/integration/test_downstream_consumer_contract.py::test_generic_v1_rejects_non_generic_profile_in_projector_and_fixture",
      "tests/unit/test_v0_1_6_release_metadata.py::test_v0_1_6_version_identity_is_consistent"
    ]
  },
  "independent_consumer_proof": {
    "repository": "https://github.com/iTao-AI/night-voyager",
    "current_baseline_commit": "19bd17ad35131435e7dbec4a33fe939c9976007c",
    "authority": "consumer-owned",
    "proof_kind": "provider-free",
    "pull_request": {
      "number": 75,
      "reviewed_head": "a7d6eee704537a0876396d56e483485ef77b291b",
      "merge_commit": "95cce4f28357150450c7f87105adcb47abf1a15d",
      "reviewed_tree": "7e310124de9c7d081723eee5b42c152a258b0919",
      "merge_tree": "7e310124de9c7d081723eee5b42c152a258b0919",
      "run_id": 30257237706,
      "successful_jobs": ["python", "frontend", "compose"]
    }
  },
  "decision": {
    "candidate": "accept_contract_level",
    "consumer_proof": "accept_independent",
    "live_success": "reject",
    "runtime_expansion": "reject",
    "automatic_release": "reject",
    "release": "HOLD",
    "semantic_overclaim": "reject"
  },
  "rollback": {
    "proof_change": "revert_independently",
    "consumer_action": "retain_previous_immutable_pin_or_reject_candidate",
    "runtime_mutation": false,
    "database_migration": false
  },
  "non_claims": [
    "autonomous_evolution_or_runtime_self_modification",
    "live_provider_success_or_provider_quality",
    "source_truth_entailment_or_citation_completeness",
    "automatic_release_or_v0_1_7_publication",
    "production_reliability_user_adoption_or_business_impact"
  ]
}
```

The implementation may reorder object keys only through canonical
serialization; array order is contract. Validation is strict by Python type:
`true` is not `1`, integers are not strings, extra keys fail, missing keys
fail, duplicate selectors fail, and every expected literal is exact. Use
section-specific stable codes rather than one permissive schema:

```text
loop_manifest_invalid
loop_source_evidence_invalid
loop_diagnosis_invalid
loop_carrier_decision_invalid
loop_candidate_identity_invalid
loop_retained_regression_invalid
loop_consumer_proof_invalid
loop_decision_invalid
loop_artifact_drift
loop_retained_regression_failed
```

Validation order is fixed: envelope/scope; producer and candidate identity;
failure receipts; diagnosis; carrier; retained set; independent consumer
proof; decision/rollback/non-claims. A mutation maps to the corresponding
first stable code. Repository identities accept only the two exact public
HTTPS URLs above; commits/trees/heads are lowercase 40-hex; no branch, query,
fragment, userinfo, alternate host, shortened hash, or floating URL is valid.

### Report

The generated report uses schema `dra.consumer-derived-loop-proof.v1` and
contains this exact top-level closed set:

```text
schema_version
loop_id
manifest
scope
producer_baseline
failure_receipts
diagnosis
carrier_decision
candidate
retained_regressions
independent_consumer_proof
decision
rollback
non_claims
summary
```

`manifest` contains exactly `schema_version` and `sha256`; the hash covers the
canonical manifest bytes. Every other manifest section is copied only after
validation. `summary` contains exactly:

```json
{
  "failure_receipt_count": 2,
  "retained_selector_count": 9,
  "candidate_decision": "accept_contract_level",
  "consumer_proof_decision": "accept_independent",
  "release_disposition": "HOLD"
}
```

`validate_report()` reconstructs the manifest from the report, validates every
section again, recomputes the manifest hash, and validates the summary. The
report does not claim that `build` itself executed tests. Markdown is generated
only from a validated report and says explicitly that the fixed retained gate
is executed separately by `run-retained`.

### Script Interfaces

`scripts/consumer_derived_loop_proof.py` defines:

```python
PROJECT_ROOT: Path
MANIFEST_PATH: Path
BASELINE_JSON_PATH: Path
BASELINE_MARKDOWN_PATH: Path
MANIFEST_SCHEMA_VERSION = "dra.consumer-derived-loop-manifest.v1"
REPORT_SCHEMA_VERSION = "dra.consumer-derived-loop-proof.v1"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024
RETAINED_SELECTORS: tuple[str, ...]

class LoopProofError(ValueError):
    code: str

def validate_manifest(value: object) -> dict[str, object]: ...
def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, object]: ...
def build_report(*, manifest_path: Path = MANIFEST_PATH) -> dict[str, object]: ...
def validate_report(value: object) -> dict[str, object]: ...
def serialize_report(report: dict[str, object]) -> bytes: ...
def render_markdown(report: dict[str, object]) -> str: ...
def run_retained(*, manifest_path: Path = MANIFEST_PATH) -> None: ...
def main(argv: list[str] | None = None) -> int: ...
```

Helpers remain private. `load_manifest` opens a bounded regular file without
following symlinks, rejects invalid UTF-8/JSON/duplicates, requires canonical
bytes, and then validates semantics. Canonical JSON uses
`ensure_ascii=False`, `sort_keys=True`, `indent=2`, UTF-8, and one trailing
newline. The Markdown order is fixed: title/boundary; failure receipts;
diagnosis; carrier decision; immutable producer candidate; independent
consumer proof; retained selectors; accept/reject/release decision; rollback;
non-claims.

CLI surface is exact:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/consumer_derived_loop_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/consumer_derived_loop_proof.py run-retained
PYTHON_DOTENV_DISABLED=1 python scripts/consumer_derived_loop_proof.py build \
  --json-output /tmp/dra-consumer-loop-v1.json \
  --markdown-output /tmp/dra-consumer-loop-v1.md
```

- `build` requires both distinct output paths, validates both paths before
  report construction, stages both sibling temporary files, flushes/fsyncs,
  atomically replaces each regular target, and cleans every task-owned temp on
  all exits. It rejects symlink, directory, hardlink/resolved aliases, missing
  or non-writable parents, identical outputs, and aliases to the manifest or
  committed baselines. Whole-file atomicity is required; cross-file
  transactionality is not claimed, and `check` rejects an incoherent pair.
- `check` accepts no path override. It rebuilds from the fixed manifest,
  bounded-reads the fixed committed JSON/Markdown, validates JSON and its
  derived Markdown, and requires byte equality.
- `run-retained` accepts no options. It validates the fixed manifest and then
  calls exactly:
  `sys.executable -m pytest -q -p no:cacheprovider <nine fixed selectors>`
  with `cwd=PROJECT_ROOT`, a fixed timeout of 300 seconds, captured output,
  `PYTHON_DOTENV_DISABLED=1`, `LANGCHAIN_TRACING_V2=false`, and only bounded
  non-secret process variables required for execution. It must not copy or
  inspect credential variables. Nonzero exit, signal, timeout, missing pytest,
  or unexpected subprocess error maps to
  `loop_retained_regression_failed`; raw pytest output is never echoed.
- Success stdout is one line:
  `{"status":"valid","match":true}` for `check`,
  `{"status":"built"}` for `build`, and
  `{"status":"passed","selector_count":9}` for `run-retained`.
- Failure stderr is exactly one canonical line
  `{"status":"invalid","code":"<stable-code>"}` and stdout is empty.
  `--help` succeeds; import is silent and initializes no runtime/provider.

## Task 1: Lock The Reviewed Manifest And Every Necessary Loop Link

**Files:**

- Create: `benchmarks/consumer-derived-loop-v1/manifest.json`
- Create: `scripts/consumer_derived_loop_proof.py`
- Create: `tests/unit/test_consumer_derived_loop_proof.py`

- [ ] **Step 1: Write RED contract tests before the script or manifest exists**

Add exact tests:

```text
test_manifest_accepts_only_exact_reviewed_loop_contract
test_manifest_rejects_missing_or_extra_top_level_keys
test_manifest_rejects_failure_receipt_drift_with_source_code
test_manifest_rejects_diagnosis_drift_with_diagnosis_code
test_manifest_rejects_carrier_drift_with_carrier_code
test_manifest_rejects_nonexact_candidate_identity_with_candidate_code
test_manifest_rejects_retained_selector_drift_with_retained_code
test_manifest_rejects_nonexact_consumer_identity_with_consumer_code
test_manifest_rejects_decision_rollback_or_nonclaim_drift
test_manifest_rejects_private_or_body_bearing_fields
test_report_reconstructs_and_revalidates_every_manifest_link
```

Use parameterized deep-copy mutations for the five Loop links that could
otherwise false-green: root cause, carrier, immutable candidate identity,
retained selector set, and rollback/release decision. Also mutate the two
failure receipts and independent consumer proof. Assert the exact first stable
code; do not merely assert `ValueError`.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k 'manifest or report'
```

Expected RED: collection/import fails because
`scripts.consumer_derived_loop_proof` and/or the fixed manifest does not yet
exist. Record the exact failure in the implementation report; do not weaken
the tests.

- [ ] **Step 2: Add the canonical manifest and the minimal strict validator**

Create the manifest with the exact reviewed JSON above. Implement only the
constants, `LoopProofError`, bounded canonical loader, section validators,
`validate_manifest`, report reconstruction, `build_report`,
`validate_report`, `serialize_report`, and `render_markdown`. Prefer explicit
closed dictionaries/tuples and strict recursive equality over a reusable
schema engine. Do not import Pydantic or any DRA runtime module.

- [ ] **Step 3: Prove GREEN and direct false-green resistance**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k 'manifest or report'
```

Expected: all selected tests pass. Then manually mutate a temporary copy of
one necessary link and prove the validator returns its stable code; never edit
the committed manifest for this check.

- [ ] **Step 4: Commit the manifest contract**

```bash
git add benchmarks/consumer-derived-loop-v1/manifest.json \
  scripts/consumer_derived_loop_proof.py \
  tests/unit/test_consumer_derived_loop_proof.py
git diff --cached --check
git commit -m "feat(loop): validate consumer-derived proof manifest"
```

## Task 2: Build Canonical Evidence And A Fail-Closed CLI

**Files:**

- Modify: `scripts/consumer_derived_loop_proof.py`
- Modify: `tests/unit/test_consumer_derived_loop_proof.py`
- Create: `docs/evidence/consumer-derived-loop-proof-v1.json`
- Create: `docs/evidence/consumer-derived-loop-proof-v1.md`

- [ ] **Step 1: Add RED tests for deterministic artifacts and output safety**

Add exact tests:

```text
test_two_fresh_reports_and_renderings_are_byte_identical
test_markdown_is_derived_only_from_validated_json
test_build_writes_exact_canonical_pair_and_check_matches
test_check_rejects_missing_corrupt_oversized_symlink_or_drifted_baseline
test_build_validates_both_targets_before_report_construction
test_build_rejects_manifest_baseline_samefile_and_hardlink_aliases
test_build_write_failure_preserves_whole_targets_and_cleans_temps
test_cli_invalid_arguments_emit_one_stable_public_safe_line
test_cli_unexpected_errors_never_emit_exception_or_path
test_help_succeeds_and_import_is_silent
test_generated_artifacts_exclude_private_and_credential_markers
```

For privacy assertions scan both artifacts for `/Users/`, `/private/`,
`Traceback`, `Career`, `source_thread_id`, `API_KEY`, `token=`, raw query/body
keys, and known credential variable names. The public Night Voyager repository
name is allowed; private task/window identifiers are not.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k \
  'build or check or cli or artifact or markdown or import'
```

Expected RED: missing CLI/output helpers and baselines cause failures.

- [ ] **Step 2: Implement bounded build/check and generate candidate evidence**

Implement the fixed parser, bounded regular-file reads, alias-safe target
validation, staged whole-file writes, temp cleanup, stable error projection,
and `main()`. Generate to a task-owned temporary directory first:

```bash
LOOP_TMP_DIR="$(mktemp -d)"
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py build \
  --json-output "$LOOP_TMP_DIR/first.json" \
  --markdown-output "$LOOP_TMP_DIR/first.md"
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py build \
  --json-output "$LOOP_TMP_DIR/second.json" \
  --markdown-output "$LOOP_TMP_DIR/second.md"
cmp "$LOOP_TMP_DIR/first.json" "$LOOP_TMP_DIR/second.json"
cmp "$LOOP_TMP_DIR/first.md" "$LOOP_TMP_DIR/second.md"
```

After reviewing the candidate pair, use the same command to write the exact
committed paths. The implementation task owns only that temporary directory;
remove it after comparison. This does not authorize broad cleanup.

- [ ] **Step 3: Prove GREEN and committed drift detection**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k \
  'build or check or cli or artifact or markdown or import'
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py check
```

Expected: targeted tests pass and stdout is exactly
`{"status":"valid","match":true}`.

- [ ] **Step 4: Commit deterministic evidence**

```bash
git add scripts/consumer_derived_loop_proof.py \
  tests/unit/test_consumer_derived_loop_proof.py \
  docs/evidence/consumer-derived-loop-proof-v1.json \
  docs/evidence/consumer-derived-loop-proof-v1.md
git diff --cached --check
git commit -m "feat(loop): build canonical consumer-derived proof"
```

## Task 3: Add The Fixed Provider-Free Retained Regression Gate

**Files:**

- Modify: `scripts/consumer_derived_loop_proof.py`
- Modify: `tests/unit/test_consumer_derived_loop_proof.py`

- [ ] **Step 1: Add RED tests for fixed selector and process authority**

Add exact tests:

```text
test_retained_selector_allowlist_matches_reviewed_existing_tests
test_run_retained_invokes_exact_sys_executable_pytest_command
test_run_retained_uses_fixed_cwd_timeout_and_nonsecret_environment
test_run_retained_accepts_no_selector_or_path_override
test_run_retained_failure_is_one_stable_line_without_pytest_output
test_run_retained_success_reports_exact_selector_count
```

Monkeypatch `subprocess.run` to capture the full call. Assert the exact ordered
nine selectors, `sys.executable`, `-m pytest -q -p no:cacheprovider`, project
root cwd, timeout `300`, captured bytes, and absence of credential keys. Feed a
failure result whose stdout/stderr contains a fake traceback, host path, and
secret marker; assert none escapes. Assert `run-retained extra` and every
option form fail before subprocess entry.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k retained
```

Expected RED: `run_retained` and the CLI command are not implemented.

- [ ] **Step 2: Implement the minimal fixed runner**

Read selectors only from the already validated fixed manifest and require
byte/value equality with `RETAINED_SELECTORS`. Construct no shell command.
Call `subprocess.run([...], shell=False, check=False, capture_output=True,
timeout=300, cwd=PROJECT_ROOT, env=...)`. The child environment is a small
allowlist of non-secret execution variables plus
`PYTHON_DOTENV_DISABLED=1`, `LANGCHAIN_TRACING_V2=false`, and
`PYTHONHASHSEED=0`; do not copy the entire parent environment and pop secrets
afterward.

- [ ] **Step 3: Prove GREEN with fakes, then execute the real retained set**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k retained
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py run-retained
```

Expected: unit tests pass; real runner prints exactly
`{"status":"passed","selector_count":9}`. If the real fixed set fails, run
the same explicit nine selectors directly for developer diagnostics, preserve
the exact RED, and stop. Do not add a selector, remove a selector, call a
provider, or change runtime under this task.

- [ ] **Step 4: Commit the retained gate**

```bash
git add scripts/consumer_derived_loop_proof.py \
  tests/unit/test_consumer_derived_loop_proof.py
git diff --cached --check
git commit -m "test(loop): retain strict consumer regressions"
```

## Task 4: Publish The Proof Boundary And Require Both Gates In Backend CI

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/reference/consumer-derived-loop-proof.md`
- Modify: `tests/unit/test_consumer_derived_loop_proof.py`

- [ ] **Step 1: Add RED documentation and CI contract tests**

Add exact tests:

```text
test_backend_ci_runs_loop_check_then_retained_before_broad_non_docker_pytest
test_readmes_publish_value_equal_loop_commands_and_boundaries
test_reference_explains_online_offline_carrier_accept_reject_and_rollback
test_evidence_index_classifies_loop_pair_as_required_deterministic_baseline
test_changelog_records_unreleased_proof_without_version_or_release_claim
test_public_docs_preserve_exact_identity_and_nonclaims
```

Require Backend Tests to contain exactly once, in this order after the bounded
live producer contract check and before broad non-Docker pytest:

```yaml
- name: Run consumer-derived Loop proof check
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/consumer_derived_loop_proof.py check
- name: Run consumer-derived Loop retained regression
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/consumer_derived_loop_proof.py run-retained
```

Assert neither command appears in container/frontend jobs and no provider,
credential, `observe-live`, Docker, Release, or Night Voyager command is added.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py -k \
  'ci or readme or reference or evidence_index or changelog or public_docs'
```

Expected RED: new CI steps and public documentation are absent.

- [ ] **Step 2: Add concise bilingual navigation and the full reference**

Update English and Chinese README verification sections with both exact
commands in the selected local subset and required CI inventory. Add one
value-equivalent paragraph stating that this is a provider-free offline
consumer-derived Loop proof over real reviewed downstream safe-stop summaries,
a fixed retained set, immutable producer identity, independent consumer proof,
explicit accept/reject, rollback, and release `HOLD`; it is not autonomous
evolution, live-provider success, or production/business evidence. Add the
reference link to both documentation lists.

`docs/reference/consumer-derived-loop-proof.md` uses these headings:

```text
# Consumer-Derived Loop Proof
## What It Proves
## Online And Offline Authority
## Diagnose And Choose The Carrier
## Reproduce
## Read The Immutable Identities
## Interpret Accept And Reject
## Release Hold And Rollback
## 30-Second Explanation
## 2-Minute Walkthrough
## Non-Claims
```

The 30-second and 2-minute sections are public-neutral technical explanations,
not job-search claims. They must explain the causal chain:

```text
real downstream safe stops
-> structured diagnosis
-> smallest carrier decision
-> existing candidate
-> FAIL_TO_PASS/PASS_TO_PASS retained regression
-> immutable producer pin
-> independent consumer proof
-> explicit accept/reject
-> separate release/rollback decision
```

Add JSON and Markdown rows to
`docs/evidence/README.md` under `Required Deterministic CI/Release Baseline`,
while stating that the two failure summaries are reviewed public-safe inputs
and not raw runtime traces. Add reference/evidence links to `docs/README.md`.
Add a new `[Unreleased]` subsection before the strict citation subsection in
`CHANGELOG.md`; keep `VERSION` and every release note unchanged.

- [ ] **Step 3: Wire CI and prove GREEN**

Add the two exact Backend Tests steps, then run:

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py run-retained
```

Expected: all new tests and both gates pass.

- [ ] **Step 4: Commit public proof documentation and CI**

```bash
git add .github/workflows/ci.yml README.md README_CN.md \
  docs/README.md docs/evidence/README.md CHANGELOG.md \
  docs/reference/consumer-derived-loop-proof.md \
  tests/unit/test_consumer_derived_loop_proof.py
git diff --cached --check
git commit -m "docs(loop): publish consumer-derived proof boundary"
```

## Task 5: Full Verification And Authority Handoff

**Files:** Verify all exact planned files; do not add or modify another path.

- [ ] **Step 1: Prove deterministic fresh builds outside the repository**

```bash
LOOP_VERIFY_DIR="$(mktemp -d)"
for pass in first second; do
  PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
    scripts/consumer_derived_loop_proof.py build \
    --json-output "$LOOP_VERIFY_DIR/$pass.json" \
    --markdown-output "$LOOP_VERIFY_DIR/$pass.md"
done
cmp "$LOOP_VERIFY_DIR/first.json" "$LOOP_VERIFY_DIR/second.json"
cmp "$LOOP_VERIFY_DIR/first.md" "$LOOP_VERIFY_DIR/second.md"
cmp "$LOOP_VERIFY_DIR/first.json" \
  docs/evidence/consumer-derived-loop-proof-v1.json
cmp "$LOOP_VERIFY_DIR/first.md" \
  docs/evidence/consumer-derived-loop-proof-v1.md
```

Remove only `"$LOOP_VERIFY_DIR"` after all comparisons. Report what was
removed; do not perform repository/worktree cleanup.

- [ ] **Step 2: Run focused and full provider-free verification**

```bash
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py check
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/consumer_derived_loop_proof.py run-retained
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q \
  tests/unit/test_consumer_derived_loop_proof.py
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" -m pytest -q -m "not docker"
PYTHON_DOTENV_DISABLED=1 "$DRA_PYTHON_BIN" \
  scripts/check_canonical_identity.py --root .
```

Do not run Docker, npm, a provider/model, network observation, or a third live
attempt. Container and frontend no-regression remain hosted PR checks after a
separate publication authorization.

- [ ] **Step 3: Audit exact scope, public neutrality, and release boundaries**

```bash
git diff --check "$IMPLEMENTATION_BASE"..HEAD
git diff --name-only "$IMPLEMENTATION_BASE"..HEAD | LC_ALL=C sort
rg -n '/Users/|/private/|source_thread_id|threadId|hostId|Career|API_KEY|token=' \
  benchmarks/consumer-derived-loop-v1/manifest.json \
  scripts/consumer_derived_loop_proof.py \
  tests/unit/test_consumer_derived_loop_proof.py \
  docs/evidence/consumer-derived-loop-proof-v1.json \
  docs/evidence/consumer-derived-loop-proof-v1.md \
  docs/reference/consumer-derived-loop-proof.md \
  README.md README_CN.md docs/README.md docs/evidence/README.md CHANGELOG.md
```

The marker scan must be interpreted: public repository URLs and the public
project name are allowed; private coordination identifiers, host paths,
credentials, and job-search context are not. Confirm:

```bash
test -z "$(git diff --name-only "$IMPLEMENTATION_BASE"..HEAD -- \
  agent api migrations frontend constraints.txt requirements.txt VERSION docs/releases)"
git diff --exit-code "$IMPLEMENTATION_BASE"..HEAD -- \
  docs/evidence/agent-evaluation-regression-v1.json \
  docs/evidence/agent-evaluation-sensitivity-v2.json \
  docs/evidence/downstream-consumer-contract-v1.json \
  docs/evidence/bounded-live-producer-v1.json
```

- [ ] **Step 4: Verify commit and worktree state, then stop before publication**

```bash
git status --short --branch
git log --oneline "$IMPLEMENTATION_BASE"..HEAD
git diff --stat "$IMPLEMENTATION_BASE"..HEAD
```

The worktree must be clean and every task-owned phase committed. Return one
`READY` report with branch, worktree, implementation base, final HEAD, exact
files, RED/GREEN evidence, focused/full commands and results, deterministic
byte comparisons, non-claims, and remaining hosted checks. Do not push, create
a PR, merge, tag, Release, deploy, or clean the worktree/branch.

## Hard Stops And Non-Claims

Stop immediately and return to authority if:

- any required change touches runtime, profiles, database, migration,
  dependency, framework adapter, consumer repository, VERSION, release notes,
  Docker, frontend, or an existing Evidence artifact;
- a retained selector is missing, no longer provider-free, or cannot express
  the reviewed behavior;
- immutable producer/consumer facts conflict with the manifest;
- tests reveal a new exact runtime failure rather than proof-orchestration
  drift; or
- safe public evidence would require raw consumer data, credentials, local
  paths, provider output, or another live attempt.

One new exact runtime failure permits only preservation of one bounded RED and
return to authority. It does not authorize a fix under this plan.

Even after all local gates pass, do not claim autonomous evolution, runtime
self-modification, automated diagnosis/candidate generation, live-provider
success, source truth, entailment, citation completeness, provider quality,
production reliability, user adoption, business impact, a published
`v0.1.7`, or automatic consumer upgrade. The supported claim begins only after
a reviewed merge and hosted CI success, and remains a personal open-source,
provider-free, contract-level demonstration of an evidence-gated offline Loop.

---
