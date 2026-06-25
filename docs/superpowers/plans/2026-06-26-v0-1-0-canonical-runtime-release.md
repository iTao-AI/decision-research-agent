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
