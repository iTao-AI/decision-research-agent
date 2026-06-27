# v0.1.0 Release Presentation Cleanup Plan

## Goal

Prepare the repository for the `v0.1.0` release by consolidating current
documentation, removing obsolete public history and retired-frontend CI
residue, eliminating the Starlette TestClient warning, and adding a repeatable
presentation audit. This plan does not add product capability or change the
Agent business architecture.

## Execution Boundary

- Execute Tasks 0 through 9 sequentially in an isolated worktree.
- Use Python 3.11 with the complete release lock for authoritative tests.
- Use TDD for behavior changes and retain RED/GREEN evidence.
- Commit each task or coherent phase separately.
- Stop after Task 9 on a clean local branch.
- Do not push, create a pull request, merge, tag, publish a release, deploy, or
  change GitHub settings without separate authorization.
- Do not perform post-merge cleanup of ignored local files in this change.

## Task 0: Establish The Worktree And Plan

- Confirm the reviewed base, clean primary checkout, and existing worktrees.
- Create `codex/v0-1-0-release-presentation-cleanup` in a new isolated
  worktree without modifying or reusing another worktree.
- Record baseline Git state, tracked Markdown count, Python version, and the
  focused canonical-identity test including its warning count.
- Add this plan and the Superpowers lifecycle policy as the first commit.

## Task 1: Define The Presentation Audit Contract

- Add `scripts/final_presentation_audit.py` and focused unit tests.
- Require the release documentation surface and reject obsolete tracked trees.
- Allow only the lifecycle README and Markdown specs/plans beneath the curated
  Superpowers workspace.
- Scan every tracked Markdown file for canonical identity violations, private
  path/process leakage, explicit private presentation motivation, and false
  claims about removed runtime, API, or frontend surfaces.
- Keep legitimate hiring and job-search product terminology valid. Add positive
  and negative regression cases proving that distinction.
- Check all local Markdown links and expose a JSON CLI that exits non-zero on
  any violation.
- Run the focused suite and commit the intentionally RED contract before
  implementation cleanup makes it green.

## Task 2: Distill Durable Decisions

- Add an ADR for framework/runtime ownership and a concise explanation of
  AI-assisted engineering.
- Preserve the durable LangChain, DeepAgents, LangGraph, LangSmith, application
  database, evidence, identity, review, publication, and delivery boundaries.
- Record trade-offs and rejected alternatives without implementation history,
  private rationale, prompts, credentials, or unsupported metrics.
- Update the current evidence-authority and run-identity ADRs, then commit the
  durable documentation before deleting source history.

## Task 3: Consolidate Technical Documentation

- Move the six current technical specifications into `docs/` and
  `docs/reference/`; remove the redundant specification index.
- Rewrite `docs/README.md` around tutorial, how-to/operations, reference,
  explanation/decisions, evidence, and release sections.
- Update architecture and all current links without retaining compatibility
  placeholders.
- Document the active artifact and profile endpoints from route code and tests.
- Keep every current document reachable within two clicks of the root README.
- Run documentation and route-focused tests plus `git diff --check`, then
  commit.

## Task 4: Add First-Run And Contributor Guides

- Add a copy-pasteable Python 3.11 tutorial with a visible `/health` result by
  step three, followed by Tool Client doctor, run, and result flows.
- State provider configuration and secret-handling boundaries and cover common
  terminal, review, authentication, and artifact failures.
- Add contributor setup, test tiers, TDD, documentation synchronization,
  security, and pull-request verification guidance.
- Link the tutorial and contributor material from both READMEs and the docs
  index, verify non-provider commands where practical, then commit.

## Task 5: Remove Completed History And Stale Evidence

- Confirm durable contracts are represented in current code, tests, ADRs, or
  references before removal.
- Remove all pre-cleanup Superpowers execution/spec/plan files while retaining
  only the lifecycle README and this release plan.
- Remove the OpenSpec tree, stale evidence prose/assets/task JSON, and the old
  root specification tree after its current documents have moved.
- Limit the evidence index to the durable HITL report and bounded real-source
  proof reports.
- Update repository instructions, READMEs, canonical-identity checks, and all
  active links for the final source-priority and evidence boundaries.
- Require both presentation and canonical-identity audits to return zero
  violations, then commit the mechanical cleanup separately.

## Task 6: Unify Agent Instruction Entrypoints

- Preserve the ignored legacy local instruction file outside the tracked tree.
- Stop ignoring `CLAUDE.md` and add a minimal pointer to `AGENTS.md` as the sole
  full repository rule source.
- Verify a fresh worktree receives both tracked instruction files and no local
  state is committed, then commit.

## Task 7: Remove The Starlette Test Warning

- Reproduce the warning as an error in a disposable Python 3.11 environment.
- Add the supported direct test dependency and only its required exact lock
  entries; retain the existing HTTP client unless full dependency analysis
  proves it unused.
- Install the complete release lock and run the warning-as-error focused test
  and full backend suite without warning suppression.
- Stop if TestClient behavior changes or the dependency scope expands beyond
  the approved additions. Commit the bounded dependency change.

## Task 8: Remove Retired-Frontend CI Residue

- Preserve backend tests proving frontend source, container, proxy, Compose,
  and npm Dependabot surfaces remain absent.
- Remove only the test requiring the obsolete CI status and remove the matching
  workflow job.
- Run the focused test and parse the workflow as YAML, then commit.
- Do not change branch protection; that remains a separately authorized
  external action.

## Task 9: Run Local Release And Presentation Gates

- Run the focused release/documentation tests with the Starlette warning
  promoted to an error.
- Run the presentation and canonical-identity audit CLIs.
- Run the full Python 3.11 release-lock pytest suite with no warning summary.
- Run the 13-item durable HITL gate and the real-source proof checker.
- Validate Compose configuration, build and start MySQL/backend, verify
  `/health`, and clean containers and volumes.
- Run `git diff --check`, inspect the complete branch diff and tracked file
  statistics, and scan for generated environments, databases, caches, output,
  screenshots, secrets, private paths, and unrelated dependency changes.
- Perform a light pre-review and leave the local branch clean.

## Verification Commands

```bash
python -m pytest tests/unit/test_final_presentation_audit.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_canonical_identity.py \
  tests/unit/test_frontend_retirement.py -q \
  -W error::starlette.exceptions.StarletteDeprecationWarning
python scripts/final_presentation_audit.py --root .
python scripts/check_canonical_identity.py --root .
python -m pytest -q \
  -W error::starlette.exceptions.StarletteDeprecationWarning
python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json
python scripts/real_source_proof.py check-report \
  --report docs/evidence/p2a-real-source-proof.json
docker compose config --quiet
docker compose build backend
docker compose up -d mysql backend
curl --fail --silent http://127.0.0.1:8000/health
docker compose down -v
git diff --check
```

## Stop Conditions

Stop and request review if:

- historical material contains a still-active contract absent from current
  code, tests, ADRs, or reference docs;
- removing a Superpowers file would remove an approved active task without an
  active public-neutral project-local plan;
- moving the old specification paths reveals an external consumer;
- the supported TestClient dependency changes behavior or requires broader
  dependency churn;
- the retired CI job contains the only frontend-absence coverage;
- the audit can pass only by excluding another tracked documentation subtree;
- the full suite, durable gate, proof checker, or Docker health check fails;
- progress requires weakening unrelated GitHub protection or performing an
  unauthorized publication action.

## Acceptance Criteria

1. Current human documentation is organized under `docs/`; the old root
   specification and OpenSpec trees are absent.
2. The Superpowers workspace retains only its lifecycle README and this active
   release plan after durable decisions are promoted.
3. `AGENTS.md` remains the complete rule source and tracked `CLAUDE.md` is only
   a pointer.
4. Legitimate product-domain language remains intact while private/process
   leakage and stale product claims fail closed.
5. Focused and full Python 3.11 tests pass without the Starlette warning.
6. Presentation and canonical-identity audits report zero violations.
7. Durable HITL reports 13/13, the real-source proof validates, and Docker
   build/start/health/cleanup succeeds.
8. The branch is clean and remains local; GitHub state and release publication
   are unchanged pending separate authorization.
