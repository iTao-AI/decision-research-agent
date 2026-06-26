# v0.1.0 Canonical Runtime Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement the linked plans task-by-task.
> Coding subagents are disabled by repository policy. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Deliver a backend-and-CLI `v0.1.0` with one run-scoped execution
model, a DeepAgents-native harness, no active legacy product/runtime contracts,
and reproducible release evidence.

**Architecture:** Preserve the application-owned ResearchRun, Evidence, review,
verification, publication, and delivery layers. Replace only the Agent harness
behind `AgentHarness`, complete canonical result delivery, then remove the old
task/Vue stack and harden the first release.

**Tech Stack:** Python 3.11, FastAPI, LangChain 1.3.10, DeepAgents 0.6.11,
LangGraph 1.2.6, LangSmith 0.8.18, SQLite WAL, MySQL 8, pytest, Docker Compose.

---

## Source Spec

Implement only the approved design:

`docs/superpowers/specs/2026-06-25-v0-1-0-canonical-runtime-release-design.md`

If implementation reveals a conflict with the spec, stop that PR and update
the spec in the planning window. Do not silently preserve a legacy contract or
expand into React, persistent memory, Async Subagents, ContextSeek, OceanBase,
AgentSeek, or public deployment.

## Ordered PRs

| Order | Plan | Required base | Terminal condition |
|---|---|---|---|
| PR1 | `2026-06-26-v0-1-0-pr1-deepagents-native-harness.md` | current `main` after this design lands | Agent execution uses `AgentHarness`; generic harness is DeepAgents-native; public API/schema unchanged |
| PR2 | `2026-06-26-v0-1-0-pr2-canonical-run-delivery.md` | merged PR1 | generic runs persist canonical result artifacts; Tool Client and first-party consumer use run/result |
| PR3 | `2026-06-26-v0-1-0-pr3-legacy-runtime-removal.md` | merged PR2 plus successful consumer smoke | task/thread runtime, old identifiers, Vue, aliases, and active compatibility code are absent |
| PR4 | `2026-06-26-v0-1-0-pr4-release-hardening.md` | merged PR3 | clean install, full gates, current docs, `VERSION=0.1.0`, release-ready repository |

Do not stack implementation branches. Each PR starts from the updated `main`
after the prior PR is reviewed, merged, and cleaned up.

## Cross-PR Invariants

Every PR must preserve:

1. application database authority for ResearchRun, Evidence, review,
   verification, publication, and delivery;
2. timeout/cancellation Evidence freezing and fenced terminal transitions;
3. Talent profile restrictions and deterministic artifacts;
4. durable HITL default `false` and the existing single-node boundary;
5. LangSmith privacy defaults and diagnostic-only authority;
6. no secrets, private paths, Career context, or raw GStack artifacts;
7. no implementation subagents;
8. no new external runtime dependency without returning to design review.

## Branch and Worktree Policy

For each PR:

```bash
git fetch origin
git switch main
git pull --ff-only
git worktree add \
  .worktrees/<short-name> \
  -b codex/<short-name> \
  main
```

Use the repository `.venv` when available:

```bash
../../.venv/bin/python -m pytest -q
```

If the relative path differs, resolve the main checkout with
`git worktree list` and use its `.venv/bin/python`. Do not fall back to an
unverified global Python after an import error.

## Review and Landing Policy

For each PR:

1. execute TDD task-by-task in its isolated worktree;
2. run focused tests after each task;
3. run the PR-specific final verification;
4. leave a clean local branch and return evidence to the planning window;
5. run one pre-PR `gstack-review` in the planning window;
6. fix only verified findings in the execution window;
7. run targeted re-review;
8. push/create PR only after explicit authorization;
9. merge only after CI and review comments are clean;
10. remove the feature branch/worktree before starting the next PR.

Do not run a second full `autoplan` for individual PRs unless scope or
architecture changes. Use lightweight `gstack-review` before each PR.

## Release Stop Conditions

Stop the release sequence and return to design if any PR requires:

- DeepAgents graph state in an API or repository contract;
- Skills, VFS, LangSmith, or checkpoints to write business authority;
- a legacy alias, forwarding endpoint, or hidden feature flag to keep tests
  passing;
- a second writable database for main research state;
- persistent long-term memory;
- Async Subagents or deployed graph IDs;
- React implementation;
- multi-instance or tenancy infrastructure;
- weakening Talent filesystem, source, Evidence-ref, or review boundaries.

## Final Acceptance

PR4 may prepare, but must not create, the tag or GitHub Release. The final
release action requires separate user authorization after:

```bash
python -m pytest -q
python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json
python scripts/real_source_proof.py check-report \
  --report docs/evidence/p2a-real-source-proof.json
git diff --check
```

Additional required evidence:

- clean constraints installation;
- Docker backend build and canonical `/health`;
- durable Docker compatibility and Evidence verification canary;
- Tool Client `doctor`;
- first-party consumer run/result smoke;
- documentation link check;
- canonical-identity scan;
- GitHub CI and CodeQL.

---

## CEO Review — Auto-Decided Findings

### Premise Assessment
All four premises (dual-runtime merge, DeepAgents-native over custom, Vue retirement without migration, four-PR sequencing) are verified against current repository code. No premise challenge needed.

### Architecture Review (Section 1)

**Finding CEO-1 [MEDIUM]: `AgentHarness` boundary incomplete.** The spec defines `HarnessRequest` with query/thread/run/segment/profile/scope fields only. But `agent/main_agent.py:339-347` currently passes `metadata` and `callbacks` in the LangChain `config` dict. The plan is silent on whether these LangGraph-configuration concerns route through `HarnessRequest` or through adapter-owned compilation.

Fix: Add `tracing_config: Mapping[str, Any]` to `HarnessRequest`, or document that the adapter constructs the LangChain `config` dict independently from application-owned request data.

**Finding CEO-2 [LOW]: Missing `session_dir` access test in legacy finalizer.** PR1 Task 4 Step 5 says "Do not scan `session_dir`" but has no RED test asserting this.

Fix: Add a RED test in PR1 Task 4 Step 1 asserting the legacy finalizer never calls `os.scandir` or `Path.iterdir`.

### Error & Rescue Registry (Section 2)

Two gaps identified:
- **GAP-1 [HIGH] `CompositeBackend` init failure crashes app.** If `FilesystemBackend(root_dir=..., virtual_mode=True)` raises (missing/unreadable `skills/` dir), the adapter fails at startup with no graceful degradation. Fix: Add RED test for graceful startup without Skills directory.
- **GAP-2 [MEDIUM] Finalization race mechanism unspecified.** PR2 Task 2 says "stale writer writes neither" but doesn't name the fenced-write mechanism. Fix: Add concrete RED test with SQL-level expectations for `finalize_run_transaction`.

### Security Review (Section 3)
No HIGH findings. Attack surface net-reduced (9 endpoints removed). Host filesystem access eliminated via `CompositeBackend` with explicit permission boundaries. LLM prompt injection surface unchanged.

### Other Sections (4-10)
- Section 4 (Data Flow): No findings. Async run→poll→result cycle is well-defined.
- Section 5 (Code Quality): No findings. DRY violations eliminated by replacing custom wrappers.
- Section 6 (Tests): **Finding CEO-3 [MEDIUM]:** No boundary test for unknown profile ID. Fix: Add `test_unknown_profile_raises_bounded_error` to `AgentFactory`.
- Section 7 (Performance): No findings. Conservative call limits set.
- Section 8 (Observability): No findings. LangSmith + per-run telemetry preserved.
- Section 9 (Deployment): No findings. Backward-compatible until PR3; explicit retire command.
- Section 10 (Trajectory): Reversibility 3/5. Well-documented framework layering.
- Section 11 (Design): SKIPPED — no UI scope.

---

## Engineering Review — Auto-Decided Findings

### Scope Challenge (Step 0)

**Complexity check:** 30+ files across 4 PRs. NOT triggered — complexity is intentional, bounded per-PR.

**Existing code leverage:** Strong. `ExecutionOutcome`, `AgentRunAccumulator`, `AgentFactory`, `run_repository.py`, `research_runs_v2`, `run_artifacts_v2` — all reused. Only the harness plumbing is replaced.

**Minimum set:** The plan IS the minimum. It explicitly rejects compatibility code, tombstone endpoints, and hidden feature flags.

### Architecture (Section 1)

**Finding ENG-1 [HIGH]: `profile_registry.py` policy migration is underspecified.** Current `GENERIC_POLICY` (line 36-38) uses `allowed_tools=("generate_markdown", "convert_md_to_pdf", "read_file_content")` and `subagents=("knowledge_base", "database_query", "network_search", "general-purpose")`. The spec says disable `general-purpose` and replace host tools with VFS tools. But the plan only lists the NEW policy values — it doesn't specify the migration path for tests that reference old tool names.

Fix: Add a RED test in PR1 Task 2 that asserts old tool names (`generate_markdown`, `read_file_content`) are absent from the new generic profile manifest.

**Finding ENG-2 [MEDIUM]: `CompositeBackend` permissions order is security-critical but not validated in tests.** The spec specifies first-match-wins: (1) deny writes `/skills/**`, (2) allow reads `/skills/**`, (3) allow r/w `/workspace/**`, (4) deny `/**`. If DeepAgents `FilesystemMiddleware` evaluates these in a different order, the lock opens.

Fix: Add an adversarial test that attempts `write_file("/skills/research-planning/SKILL.md")` and asserts failure, then attempts `write_file("/workspace/test.md")` and asserts success.

### Tests (Section 3)

**Test Coverage Map:**

```
NEW CODE PATHS:
[+] agent/harness_contracts.py
  ├── HarnessRequest (frozen, immutable)            [TESTED in PR1 T1]
  ├── ReportCandidate (PurePosixPath only)          [TESTED in PR1 T1]
  └── ResearchRuntimeContext (tuple normalization)  [TESTED in PR1 T1]

[+] agent/deepagents_harness.py
  ├── CompositeBackend routing                      [TESTED in PR1 T3]
  ├── Skills loading (both skills present)          [TESTED in PR1 T3]
  └── Permission boundary (read/write deny)         [GAP — see ENG-2]

[+] api/run_result_service.py
  ├── build_generic_result_artifact (happy)         [TESTED in PR2 T1]
  ├── build_generic_result_artifact (absent)        [TESTED in PR2 T1]
  ├── build_generic_result_artifact (>1MiB)         [TESTED in PR2 T1]
  └── build_generic_result_artifact (empty)         [TESTED in PR2 T1]

[+] api/research_execution_service.py
  ├── Evidence frozen before cleanup                [TESTED in PR1 T4]
  ├── timeout/cancellation publishes outcome        [TESTED in PR1 T4]
  └── call_budget_exceeded stable                   [TESTED in PR1 T4]

[-] agent/main_agent.py (deleted imports)
  └── Architecture absence scan                     [TESTED in PR1 T5]

[-] frontend/ directory
  └── Repository absence check                      [TESTED in PR3 T5]

COVERAGE: Plan-specified test coverage is strong. The plan uses RED/GREEN TDD per task.
GAPS: 2 (see ENG-1, ENG-2 above). No eval tests needed — no prompt changes.
```

### Performance (Section 4)
No findings. SQLite WAL + fenced transactions. Conservative budget defaults (40 model calls, 40 tool calls). No N+1 query risk — single-run scope.

---

## DX Review — Auto-Decided Findings

### Product Type: API Service + CLI Tool

Primary developer persona: **AI agentic worker** (Claude Code with `superpowers:executing-plans`) and **external integration developer** (first-party consumer). The plan is a backend-and-CLI release — no browser UI.

### DX Scorecard

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Getting Started | 6/10 | README.md rewrite planned in PR4. Current `docs/AGENT_INTEGRATION.md` exists. Gap: no pre-built getting-started verification in CI. |
| API/CLI Design | 7/10 | Canonical `run`/`result` commands are guessable. Legacy commands removed. Gap: `result` requires `run_id` — no `result --latest` convenience. |
| Error Messages | 7/10 | Result endpoint has explicit error codes (7 states mapped to HTTP + code). Gap: Tool Client errors currently just raise `ToolClientError` without structured problem/cause/fix. |
| Documentation | 6/10 | PR4 rewrites README, architecture, API docs. Gap: no interactive examples (curl | jq patterns planned but not in spec). |
| Upgrade Path | 8/10 | Breaking migration guide planned. `retire_legacy_database.py` provides safe archival. Gap: no codemod for consumer env var migration. |
| Dev Environment | 7/10 | `.venv` + `constraints.txt` + Docker Compose. Gap: no `make doctor` or automated env verification in CI. |
| Community | 2/10 | Public repo but no community channels, contributing guide, or examples beyond README. Not a release blocker for v0.1.0. |
| DX Measurement | 2/10 | No TTHW tracking, no analytics, no friction audits. Not a release blocker for v0.1.0. |

**Overall DX: 6.2/10.** Adequate for an internal/agentic developer tool. The main gaps (community, measurement) are deferred.

### DX Findings

**Finding DX-1 [MEDIUM]: No `result --latest` convenience command.** After `run --wait`, the developer must copy the run_id and run `result --run-id <id>`. A `--latest` flag or combined `run --wait --result` would cut two steps.

Auto-decision: DEFER to TODOS.md. The `run`/`result` separation is by design (run creates, result retrieves). Adding convenience commands is polish, not blocking.

**Finding DX-2 [LOW]: Tool Client error messages lack structure.** `ToolClientHTTPError` (tools/decision_research_agent_tool.py:27-33) captures `status` and `payload` but doesn't format them into problem/cause/fix language.

Auto-decision: DEFER to TODOS.md. Current error handling is functional. Improvement can be batched with future CLI redesign.

**Finding DX-3 [MEDIUM]: No automated getting-started verification.** PR4 plans `docker compose build backend` and `curl /health`, but no CI step that verifies a clean install from scratch following the README.

Auto-decision: INCLUDE. Add to PR4 Task 4 (Release Gate) as a "clean install smoke" step.

**Finding DX-4 [LOW]: `AGENT_INTEGRATION.md` examples should be copy-paste-complete.** The spec says examples must be copy-paste complete (PR4 Task 2), which is correct. The plan already addresses this.

Auto-decision: No change needed — plan already covers this.

---

## Cross-Phase Themes

No concerns appeared independently across phases. Each phase's findings were distinct:
- CEO: Architecture boundary completeness, error rescue gaps
- Eng: Policy migration specificity, permission testing
- DX: CLI convenience, error message structure

---

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | Mode: SELECTIVE EXPANSION | Mechanical | P6 | Default for autoplan | — |
| 2 | CEO | Finding CEO-1: Add tracing_config to HarnessRequest | Mechanical | P5 | Explicit over clever — named fields > implicit dict merge | — |
| 3 | CEO | Finding CEO-2: Add session_dir absence test | Mechanical | P1 | Completeness — test the "don't scan" contract | — |
| 4 | CEO | GAP-1: Graceful CompositeBackend degradation | Mechanical | P1 | Completeness — startup failure is a P1 gap | — |
| 5 | CEO | GAP-2: Specify fenced-write mechanism in test | Mechanical | P5 | Explicit over clever — name the SQL mechanism | — |
| 6 | CEO | Finding CEO-3: Unknown profile boundary test | Mechanical | P1 | Completeness — boundary test | — |
| 7 | CEO | Section 11 (Design): Skip | Mechanical | N/A | No UI scope per user instructions | — |
| 8 | Eng | Finding ENG-1: Old tool absence assertion | Mechanical | P5 | Explicit — assert old tool names gone | — |
| 9 | Eng | Finding ENG-2: Permission order adversarial test | Mechanical | P1 | Completeness — security boundary must be tested | — |
| 10 | DX | Finding DX-1: result --latest | Taste | P3 | Pragmatic — convenience, not blocking | Defer to TODOS.md |
| 11 | DX | Finding DX-2: Error message structure | Taste | P3 | Pragmatic — functional, not broken | Defer to TODOS.md |
| 12 | DX | Finding DX-3: Clean install smoke in CI | Mechanical | P1 | Completeness — verify what docs claim | Include |
| 13 | DX | Finding DX-4: Copy-paste examples | Mechanical | — | Already covered by plan | — |

---

## NOT in Scope (confirmed or deferred)

| Item | Rationale |
|------|-----------|
| React frontend | Explicit non-goal for v0.1.0 |
| Persistent long-term Agent memory | Requires separate authority and privacy design |
| Async Subagents | Adds operations surface; deferred per spec |
| ContextSeek / OceanBase / AgentSeek | References only; not dependencies |
| Public deployment / RBAC / tenancy | Future release scope |
| result --latest CLI convenience | Deferred to TODOS.md — polish, not blocking |
| Structured error messages in Tool Client | Deferred to TODOS.md — functional, not broken |
| Community channels / DX measurement | Not release blockers for v0.1.0 |

## What Already Exists (reused)

| Component | File | Reuse Status |
|-----------|------|-------------|
| ExecutionOutcome | agent/run_result.py | Extended with report_candidate; session_dir removed |
| AgentRunAccumulator | agent/run_result.py | Kept; moved to ResearchExecutionService |
| EvidenceEntry + ledger | agent/research.py | Kept; snapshot migrated from SharedContext to adapter |
| AgentFactory | agent/profile_registry.py | Kept; policies rewritten for DeepAgents-native |
| research_runs_v2 schema | api/run_repository.py | Kept; artifacts added atomically |
| Tool Client core | tools/decision_research_agent_tool.py | Kept; result() added; legacy commands removed |
| LangGraph durable gate | api/review_gate.py | Unchanged |
| Review/verification API | api/review_api.py, api/evidence_verification_api.py | Unchanged |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` via `/autoplan` | Scope & strategy | 1 | issues_open | 3 findings, 2 critical error gaps |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | unavailable | Formal outside-voice invocation was unavailable because of model routing; the local Codex binary exists |
| Eng Review | `/plan-eng-review` via `/autoplan` | Architecture & tests (required) | 1 | issues_open | 2 findings (1 HIGH, 1 MEDIUM), no critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | UI scope explicitly out of scope (React deferred, Vue deleted) |
| DX Review | `/plan-devex-review` via `/autoplan` | Developer experience gaps | 1 | issues_open | 3 findings (2 MEDIUM, 1 LOW), 1 deferred to scope |

**CODEX:** Formal outside-voice review was unavailable because of model
routing. The local Codex binary exists, but this autoplan run did not produce
an independent Codex review.

**CROSS-MODEL:** N/A — dual voices unavailable due to platform model routing mismatch.

**VERDICT:** CEO + ENG + DX review complete via single-model. Plan is sound with 8 findings (1 HIGH, 5 MEDIUM, 2 LOW). Zero blocking issues. Ready for implementation with findings addressed per-PR.

NO UNRESOLVED DECISIONS

---

## Planning-Window Resolution

The planning window verified the generated findings against the repository and
applied the following corrections to the executable PR plans:

1. `HarnessRequest` receives only bounded `trace_metadata`. An
   application-owned `ExecutionObserver` owns stream/error hooks, and the
   DeepAgents adapter constructs LangChain callback/config objects. Framework
   objects do not cross the application contract.
2. Legacy finalization receives an explicit regression test that fails if it
   scans `session_dir`.
3. Required Skills are release assets. Missing, unreadable, or incomplete
   Skills fail closed with `harness_assets_missing`; the service must not
   silently degrade to a different harness or prompt contract.
4. PR2 names and tests the existing SQLite `state_version` fenced transaction
   with two stale writers against the same WAL database.
5. PR1 adds unknown-profile, removed-host-tool, removed-`general-purpose`, and
   adversarial filesystem-permission tests.
6. PR4 adds a clean-install CI smoke that does not reuse a developer virtual
   environment or prebuilt image.
7. `result --latest` and structured Tool Client error rendering remain
   post-v0.1.0 DX work in `TODOS.md`; they do not expand the release-critical
   path.

Resolution status: all accepted findings are represented in the linked PR
plans. The only rejected recommendation is graceful Skills degradation,
because it would make the declared harness configuration non-deterministic.
