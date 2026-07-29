# Decision Research Agent v0.1.7 — Evidence-Governed Reliability and Recovery

Status: Approved design; implementation and publication remain separately gated.

Planning baseline: `main@8064a33bec6dfb403149e056a373f074c2cea409`.

## 1. Outcome

Publish a coherent, immutable `v0.1.7` source release containing the reviewed post-`v0.1.6` reliability, evaluation, evidence-governance, strict-citation, and recovery work already merged into `main`.

This phase converts verified repository state into a bounded release artifact. It does not introduce another Agent capability, autonomous evolution platform, hosted EvalOps system, provider-backed acceptance attempt, or deployment.

The release theme is:

> Evidence-governed Agent reliability: privacy-safe observations, evaluator sensitivity, consumer-derived retained verification, explicit human release/rollback authority, and crash-safe startup convergence.

## 2. Included capability pack

The release includes these already-merged surfaces:

1. Context Reliability Regression v1.
2. Privacy-safe observation contract.
3. Agent Evaluation Sensitivity Gate v2.
4. Opt-in `generic-strict-citation@1`.
5. Independent provider-free strict consumer contract evidence.
6. Evidence-Gated Loop Kernel v1.
7. Crash-Safe Startup Convergence v1.
8. Already-merged GitHub Actions and frontend dependency maintenance.

The immutable `v0.1.6` release remains unchanged. The merged implementation PRs and exact commits are implementation evidence; they do not prove that `v0.1.7` already exists.

## 3. Selected architecture

### Phase A — Release-lineage compatibility bridge

Before changing the current version:

- Preserve the exact `strict-citation-consumer@1` argument vector and profile binding.
- Correct its `v0.1.6` selector so it validates the immutable historical `v0.1.6` release record rather than requiring the mutable repository root to remain version `0.1.6`.
- Freeze the `v0.1.6` release-note identity and historical changelog boundary.
- Add a negative control proving that altered historical release-note bytes fail.
- Replace current public wording such as “verifies current release metadata” with “verifies the immutable v0.1.6 release record.”
- Regenerate Loop registry/report projections only where that public non-claim changes.
- Keep every canonical case, episode, diagnosis, candidate identity, consumer proof, verdict, and `release_disposition` unchanged.
- Do not change `PROFILE_REGISTRY`, `STRICT_ARGV`, runtime code, API, database, migration, dependencies, `VERSION`, frontend version, or any consumer repository.

Phase A must be a separate reviewed PR and must reach exact-head hosted CI success before Phase B begins. This prevents the `v0.1.7` candidate from modifying its own release verifier.

This correction is classified as compatible verifier maintenance, not a new profile contract. It removes an accidental dependency on mutable repository-root release identity from a selector whose intended subject is the immutable v0.1.6 release record. The profile ID/version, argument vector, timeout, coverage, failure code, episode binding, strict-consumer invariant, and canonical case bytes remain unchanged; the repository commit continues to distinguish the exact implementation.

This classification is narrow. Any later change to the intended invariant, profile ID/version, argument vector, timeout, coverage, failure code, episode binding, or case meaning requires the versioned profile/case review defined by the Loop reference. The separate Phase A merge is mandatory so the v0.1.7 candidate cannot modify the verifier that judges it.

### Phase B — `v0.1.7` release preparation

After Phase A is merged:

- Set `VERSION`, frontend package version, and lockfile root version to `0.1.7`.
- Create `docs/releases/v0.1.7.md`.
- Move the completed `[Unreleased]` capability entries into a dated `[0.1.7]` section.
- Add the currently omitted Context Reliability entry.
- Update current-truth surfaces: `README.md`, `README_CN.md`, `SECURITY.md`, `docs/README.md`, and current recovery/reference documentation that still says “unreleased” or “No published v0.1.7”.
- Add a dedicated `v0.1.7` release metadata contract.
- Preserve all historical release notes and historical spec/plan statements byte-for-byte unless a live current-truth test proves that a document is not historical.
- Make no runtime, schema, dependency-pin, migration, or canonical evidence change.

## 4. Loop release semantics

The canonical Loop report currently records `release_disposition=hold`. This remains valid historical evidence.

That value means the candidate was held pending a later, separate release review. It does not permanently prohibit repository publication. The Kernel ADR already assigns release authority to human review, not to the verifier.

Publishing `v0.1.7` therefore:

- must not rewrite historical episodes;
- must not change historical `hold` verdicts to `eligible`;
- must not imply that the Kernel autonomously approved publication;
- records a later, independent human decision that the accumulated main delta now forms a coherent bounded release pack.

## 5. Compatibility and migration

### Existing consumers

- `dra.downstream-consumer.v1` remains byte-compatible.
- Literal `generic` behavior remains unchanged.
- `generic-strict-citation@1` remains opt-in.
- Existing independent consumer proof remains pinned to its exact commit-based producer tuple.
- Publication of `v0.1.7` does not silently reinterpret that proof as acceptance of a new tag-based tuple.
- No consumer repository modification or re-pin is included.

### Observation consumers

Raw observation `args`, `result`, and `error` content changed in place to privacy-safe descriptors and stable codes.

Consumers needing substantive content must use canonical tool inputs, persisted results/artifacts, or terminal result authority. Release notes must describe this migration explicitly rather than calling the observation stream raw-content compatible.

### Recovery and database

`v0.1.7` includes migration `010_run_execution_recovery`, startup-only convergence, and authenticated one-hop replacement.

Upgrade requires:

- stopped writers;
- normal migration backup creation and preservation;
- exactly one active writer during startup;
- no manual owner-row or migration-marker edits.

Replacement creates a new run. It is not resume, checkpoint replay, or exactly-once external-effect recovery.

### Dependencies

Python pins remain unchanged. Frontend dependency maintenance already merged into main is included.

The known `ragflow-sdk 0.13.0` metadata declaration requiring `pytest<9` remains a diagnostic-only incompatibility against the deliberate `pytest==9.0.3` no-deps lock. Release documentation must not claim that package metadata is fully conflict-free. Any additional incompatibility blocks the release.

## 6. Verification authority

Both phases require RED→GREEN evidence, targeted tests, and full retained verification.

The final release candidate must pass:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_execution_recovery_proof.py check
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py --root .
```

Frontend verification:

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
```

Required boundaries:

- no provider, model, or tool request;
- no credential read;
- no `observe-live`;
- no additional governed provider attempt;
- no remote LangSmith tracing;
- Docker uses explicit task ownership, inventory, bounded resources, and cleanup;
- all current exact-head CI and CodeQL checks must succeed.

## 7. Release artifact and publication gates

The supported artifact remains the source repository and container configuration. This project does not claim a Python wheel or hosted service.

Publication sequence:

1. Phase A exact-head review, PR, CI, and merge.
2. Phase B release-preparation review, PR, CI, and merge.
3. Fresh merge-SHA CI and CodeQL verification.
4. Provider-free local archive smoke against the exact merge commit.
5. Separate explicit authorization for annotated tag `v0.1.7` and GitHub Release.
6. Push the tag without force.
7. Publish the tracked `docs/releases/v0.1.7.md` body.
8. Read back the annotated tag object, peeled commit, commit tree, GitHub Release target, body, draft/prerelease state, and auto-generated source archive availability.
9. Run a bounded post-publication source-archive observation using the pinned environment.

The immutable producer identity is the repository, annotated tag, peeled commit, and tree. A GitHub-generated archive checksum is an observed transport artifact, not the primary immutable identity.

No custom binary asset, deployment, or hosted service is added.

## 8. Rollback

### Before publication

Any failing required gate stops publication. No tag or Release is created.

### After publication

A published tag must never be force-moved or silently deleted. If a defect is found:

- stop recommending the release;
- retain diagnostic evidence;
- use a separately authorized correction or patch release;
- mark or deprecate the Release only through an explicit public-action decision.

### Application rollback

If migration `010` has not been applied, an operator may restore a previously approved source/dependency pin after stopping services.

If migration `010` has been applied:

1. stop all writers;
2. preserve the post-010 database diagnostically;
3. obtain explicit approval for post-backup data loss;
4. restore the complete pre-010 backup;
5. verify it using exact old revision `bfd744a5611c7673d9385a45bed0131d6cb47655`;
6. resume writes only after isolated verification succeeds.

The existing proof validates rollback to that exact pre-recovery revision. It does not prove an unrestricted downgrade of a migrated database directly to the `v0.1.6` tag.

Consumer rollback remains an independent decision to retain or restore an already approved immutable producer pin.

## 9. Stop conditions

Stop and return to authority review if:

- Phase A requires changing a canonical case, episode, verdict, or profile argument vector;
- Phase A changes the intended strict-consumer invariant, timeout, coverage, failure code, episode binding, or case meaning while retaining profile version 1;
- the release candidate modifies runtime, API, migration, database, or dependency pins;
- a new metadata incompatibility appears;
- any retained proof, Docker gate, frontend gate, hosted check, or CodeQL check fails;
- current and historical documentation cannot be separated without rewriting evidence;
- the tag, commit, tree, or Release target disagree;
- publication would require force-push, tag movement, or deletion;
- a consumer re-pin or provider attempt is proposed.

## 10. Non-claims

`v0.1.7` must not claim:

- autonomous or continuous self-improvement;
- runtime self-modification;
- automatic diagnosis, candidate generation, release, or rollback;
- arbitrary historical-candidate execution;
- live-provider strict success;
- exact resume or exactly-once external effects;
- multi-instance high availability;
- hosted production, SLA, or deployment;
- real-user adoption or business impact;
- source truth, universal research quality, or universal Agent quality;
- independent consumer acceptance of the `v0.1.7` tag;
- “Graph Engineering” merely because the project contains workflows or multiple review phases.

## 11. Completion

The phase is complete only when:

- both PRs are merged with exact reviewed-tree equality;
- merge-SHA hosted checks succeed;
- annotated `v0.1.7` tag and GitHub Release are read back coherently;
- provider-free archive observation passes;
- repository main is clean and task resources are closed;
- verified public claims are synchronized only from actual release evidence;
- DRA returns to a zero-code freeze.
