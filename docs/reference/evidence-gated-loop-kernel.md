# Evidence-Gated Loop Kernel

## What It Proves

The Evidence-Gated Loop Kernel is provider-free offline verification for three
reviewed lineages. It validates `dra.evidence-gated-loop-registry.v1`,
`dra.evolution-case.v1`, and `dra.evidence-gated-loop-report.v1` records,
executes each fixed verification profile, and keeps historical RED distinct
from current executable regression.

## What It Does Not Prove

No runtime self-modification, automatic diagnosis, candidate generation,
promotion, release, or rollback is performed. No live-provider strict success,
production reliability, adoption, or business impact is claimed. Current fixed
profiles verify retained repository state; they do not check out arbitrary
historical candidates or infer human verdicts. The v0.1.6 selector verifies
current release metadata only; it does not execute historical release behavior.

## Schemas And Case Lineage

The registry owns sorted case paths and profile identities. Each append-only
case links evidence, diagnosis, carrier assessment, action, candidate identity,
verification, and reviewed decision. A candidate-bound pass receipt is required
for an accepted change. A code-owned case and episode binding prevents manifest
data from choosing executable verification.

## Diagnosis And Carrier Selection

Every episode assesses `knowledge`, `prompt_skill`, `program_harness`, and
`model_parameters`. V1 permits one selected supported carrier and candidate,
or an explicit no-change action. `model_parameters` remains unsupported.

## Fixed Verification Profiles

- `context-resolver-coherence@1`
- `evaluation-sensitivity@1`
- `strict-citation-consumer@1`

The human-reviewed `reviewed_candidate_verification_status` records
candidate-time evidence. Current fixed profile execution is a separate
pass-only freshness gate.

## Prerequisites And First Result

Use the repository [Contributing](../../CONTRIBUTING.md#environment) steps for
the pinned Python 3.11 environment. The kernel itself needs no `.env`, provider
credential, backend, network, or Docker.

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
```

No intermediate output is expected while the fixed profiles run. They have a
420-second aggregate profile deadline plus bounded load, render, and compare
overhead. That deadline does not include cold environment setup or dependency
installation and is not an end-to-end TTHW claim.

Expected stdout:

```json
{"match":true,"record_status":"valid","status":"valid"}
```

## Commands

`check` validates fixed inputs, runs fixed profiles, and compares committed
artifacts. `build` writes a candidate pair only to explicit non-baseline paths.

## Safe Candidate Build

```bash
LOOP_OUTPUT_DIR="$(mktemp -d)"
cleanup_loop_output() {
  rm -f \
    "$LOOP_OUTPUT_DIR/evidence-gated-loop-kernel-v1.json" \
    "$LOOP_OUTPUT_DIR/evidence-gated-loop-kernel-v1.md"
  rmdir "$LOOP_OUTPUT_DIR"
}
trap cleanup_loop_output EXIT
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py build \
  --json-output "$LOOP_OUTPUT_DIR/evidence-gated-loop-kernel-v1.json" \
  --markdown-output "$LOOP_OUTPUT_DIR/evidence-gated-loop-kernel-v1.md"
```

Use a fresh task-owned directory because existing targets may be replaced. The
parent must already exist; output paths must be distinct non-symlink,
non-baseline files. Candidate JSON is the generated pair authority and
Markdown is its deterministic projection.
Only reviewed committed JSON is the repository baseline. `build` never
accepts or rewrites that baseline.

## Reading The JSON And Markdown

`record_status`, `candidate_verdict`, and `closure_status` are separate axes.
The report preserves evidence hashes, cases, current profile results, limits,
and non-claims without timestamps, branches, paths, or raw subprocess output.

## Accept, Reject, Need More Evidence, And No Change

A structurally valid record can retain accepted, rejected,
need-more-evidence, or no-change outcomes. Current profile success does not
infer a human verdict.

## Independent Consumer Proof

Consumer-owned proof binds the exact producer candidate while retaining the
consumer repository's own immutable commit, tree, and proof scope.

## Release Hold And Recommendation-Only Rollback

The canonical report retains release `hold`. Rollback is
recommendation-only rollback and requires `rollback_basis`,
`rollback_evidence_ids`, `rollback_subject_candidate_id`, an earlier accepted
candidate, and an immutable predecessor target.

## Adding A Reviewed Case Of An Existing Kind

| Change | Version rule | Required review |
|---|---|---|
| New case, existing kinds | start `case_version=1`; bump affected `profile_version`; keep `kernel_version=1` only for compatible semantics | sorted registry path, globally unique IDs, reviewed evidence, code-owned episode binding, artifacts, docs, and CI |
| Append episode to an existing lineage | increment `case_version`; bump every changed profile binding | predecessor, inputs, decision, and terminal aggregation |
| Profile contract change | bump `profile_version` | argv, timeout, coverage, failure code, and compatibility |
| New evidence, proof, field, enum, or verifier kind | require ADR and a parallel versioned schema | adapter, authority, compatibility, migration, and negative controls |

The checklist is: add the sorted registry path; preserve unique IDs; update
versions; update the code-owned episode binding; write RED tests; use a
temporary `build`; review the JSON and Markdown diff; update indexes and
contracts; then run the real `check` once.
No manifest command or dynamic verifier is allowed.
No automatic baseline acceptance is allowed.

## When A New Kind Requires Review

A new evidence, proof, field, enum, or verifier kind requires architecture
review and a parallel versioned schema/kernel contract; v1 is not reinterpreted
in place.

## Stable Error Codes

| Stable code | Owner | Likely cause | First exact symbol or bounded check | Safe fix | Prohibited false fix |
|---|---|---|---|---|---|
| `loop_registry_invalid` | registry contract | schema, order, path, or non-claim drift | `validate_registry` | restore reviewed canonical bytes | do not loosen or add executable fields |
| `loop_case_invalid` | case contract | malformed, missing, duplicate, or mismatched case | `validate_case`, then `validate_kernel_inputs` | restore registered case/path | do not drop unknown cases |
| `loop_evidence_ref_invalid` | evidence contract | identity, proof, subject, or safety drift | `EvidenceRef` | repair reviewed subject binding | do not remove provenance |
| `loop_episode_invalid` | lineage contract | predecessor or input drift | `EvolutionCase` | repair append-only lineage | do not rewrite history |
| `loop_diagnosis_invalid` | diagnosis contract | unsupported diagnosis | `Diagnosis` | restore reviewed diagnosis | do not auto-diagnose raw data |
| `loop_action_invalid` | action contract | carrier/candidate incoherence | `DecisionEpisode` | select one carrier or no-change | do not enable model authority |
| `loop_candidate_identity_invalid` | candidate contract | immutable identity drift | `CandidateRef` | restore exact commit/tree | do not use moving refs |
| `loop_verification_profile_invalid` | profile binding | unknown version or binding | `PROFILE_REGISTRY`, then `validate_kernel_inputs` | review a versioned binding | do not load commands dynamically |
| `loop_verification_failed` | profile execution | nonzero, timeout, signal, or missing executable | `run_required_profiles` | isolate the first fixed profile | do not expose output or skip |
| `loop_decision_invalid` | decision contract | incoherent verdict/consumer/closure/release/rollback | `ReviewedDecision` | correct evidence-bound decision | do not infer acceptance |
| `loop_report_invalid` | report builder | hash, order, summary, limits, or rendering drift | `validate_report` | fix typed builder | do not hand-edit authority |
| `loop_baseline_invalid` | comparison | invalid or drifted pair | `compare_artifacts` | build temporary pair and review | do not auto-accept |
| `loop_output_invalid` | CLI/output | command, path, alias, or write failure | `_ArgumentParser.error`, `_resolve_output`, writer | use supported commands and paths | do not target baselines |
| `loop_public_output_unsafe` | public projection | raw content, path, credential, or trace | `validate_public_projection` | remove at owning projection | do not redact afterward |
| `loop_internal_error` | public boundary | unexpected typed-layer escape | `main` | reproduce provider-free and review | do not expose traceback |

For `loop_verification_failed`, isolate in order:
`context-resolver-coherence@1`, `evaluation-sensitivity@1`, then
`strict-citation-consumer@1`. Each uses its exact command above and retains no
subprocess output.

## Reviewer Checklist

Confirm canonical hashes, code-owned bindings, candidate-bound receipts,
terminal episode release aggregation, fixed profile results, JSON/Markdown
coherence, public-safety scans, and release/non-claim boundaries.

## Non-Claims

No runtime self-modification. No live-provider strict success. Current fixed
profiles verify retained repository state only. Release and rollback remain
human-owned.
