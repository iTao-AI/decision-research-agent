# AGENTS.md

This file defines the execution rules for Codex in this repository.

## Project Purpose

Decision Research Agent is an evidence-driven research service built on
LangGraph and DeepAgents. It turns open-ended questions into source-backed
findings, auditable research runs, and deterministic decision briefs.

Current verified slices include:

- Run-scoped execution using `thread_id`, `run_id`, and `segment_id`.
- Evidence preservation across completion, timeout, and cancellation paths.
- Application-owned `ResearchRun` and `EvidenceLedger` persistence.
- Optional idempotent run creation with key reuse and lost-response
  reconciliation.
- Durable pre-start run dispatch with persisted intent, bounded leases, and
  reconciliation.
- A stable terminal failure-cause contract for machine-readable failure phase
  and cause reporting.
- A restricted `talent-hiring-signal` profile with deterministic artifacts.
- A fixed-sample Talent benchmark that can become
  ready for separate human value review when structural checks pass.
- The benchmark producer keeps `value_gate.passed=false`; the repository
  does not record a passed human value gate.
- A default-disabled single-node SQLite durable HITL feasibility path whose
  13 durability and safety gates passed.
- An Agent Research Operations Console with deterministic Static Demo and
  bounded local Live Backend modes, including keyed live create/status/result
  flows that render only service-owned state without owning business
  authority.

The canonical repository and technical identifier are
`decision-research-agent`. Runtime configuration, Tool Client usage, Docker
defaults, and `/health` service identity use that canonical identifier.

## Source Of Truth

Use this priority order:

1. Actual code, tests, migrations, configuration, and command output.
2. Accepted decisions in `docs/decisions/`.
3. Current reference contracts in `docs/reference/` and `docs/architecture.md`.
4. Active approved public-neutral specs/plans in `docs/superpowers/` and the
   current release record in `docs/releases/`.
5. Operations and evidence documents.
6. Issues, PR descriptions, historical plans, and external artifacts.

If sources conflict, report the conflict and follow current implementation
unless the task explicitly changes it. Do not silently apply an older plan.

Completed plans are implementation records, not current contract authority.
Each retained evidence artifact defines its own scope and limits. A cited
Evidence entry is not independently verified unless its verification state
explicitly says so.

## Read Only What The Change Needs

Start with `AGENTS.md`, `git status`, the affected code, and relevant tests.
Then read the smallest applicable set:

| Change | Additional reading |
|---|---|
| LangGraph, DeepAgents, model binding, structured output | `agent/main_agent.py`, `agent/profile_agents.py`, `agent/llm.py`, `langchain-dev-guide`, current official docs through Context7 |
| Run identity, persistence, concurrency | `docs/decisions/run-identity-boundaries.md` and affected repositories/tests |
| Architecture or framework ownership | `docs/architecture.md`, `docs/decisions/framework-runtime-boundaries.md`, and affected harness tests |
| Evidence or finalization | `agent/run_result.py`, `api/run_repository.py`, `api/run_result_service.py`, lifecycle tests |
| Talent profile or benchmark | profile/contracts/artifact/review modules and benchmark tests |
| Durable review or HITL | `docs/operations/durable-hitl-feasibility.md`, gate report, affected review modules/tests |
| REST, WebSocket, Tool Client | `docs/reference/api-contract.md`, `docs/AGENT_INTEGRATION.md`, contract tests |
| Data or state contract | `docs/reference/data-models.md`, `docs/reference/state-machines.md`, and affected repository tests |
| Agent Research Operations Console or API consumer | `DESIGN.md`, `docs/demo-console.md`, affected API contract, frontend tests |
| Public metric or claim | producing command/artifact and its evidence boundary |

Do not load every listed document for an unrelated or local change. If a
document is missing or stale, inspect implementation and tests instead.

## Framework Reuse And Project-Owned Logic

- Before implementing work involving LangChain, DeepAgents, LangGraph,
  LangSmith, or Pydantic, verify the project's installed versions, current
  usage, relevant source code, and official documentation through Context7.
- Prefer framework-native capabilities when they satisfy the approved
  contract, deterministic testing, security, authority separation,
  compatibility, and maintenance-cost requirements.
- Do not force framework usage for keyword visibility or merely to avoid a
  small amount of clear project-owned code.
- Retain project-owned implementations when a framework approach introduces
  unnecessary dependencies, hosted-service coupling, runtime side effects,
  semantic mismatch, migration risk, or higher adaptation cost.
- Runtime, tracing, and checkpoint facilities do not automatically own
  business authority.
- For non-obvious choices, briefly record the reason for reusing or rejecting
  framework capabilities in the applicable spec, plan, or review. Do not
  create documentation solely for that record.

## Architecture Boundaries

- The application database is authoritative for research runs, evidence,
  review workflow, decisions, leases, resolution state, and artifact metadata.
- The LangGraph checkpointer stores review-gate execution position. It is not
  the business ledger.
- LangSmith is privacy-first diagnostic tracing. It does not decide business
  readiness, Evidence authority, or delivery.
- `thread_id` groups caller conversation and remains a compatibility identity.
  `run_id` owns one isolated execution. Do not mechanically rename them.
- Run-scoped workspace, runtime context, tokens, telemetry, monitor routing, and
  search cache must not leak across concurrent runs.
- Timeout, cancellation, completion, and stale writers must use fenced atomic
  finalization without losing frozen Evidence.
- Talent execution stays limited to approved tools and declared Evidence. It
  must not gain upload or arbitrary filesystem access.
- Talent findings and claims require non-empty Evidence references resolving
  to the current run. Missing or invented references fail closed.
- Canonical Talent artifacts remain deterministic for equivalent accepted
  inputs.
- Durable HITL remains disabled by default. The current gate proves bounded
  single-node SQLite feasibility, not production readiness.
- Approval permits delivery but does not verify Evidence. Rejection blocks
  delivery and does not automatically start new research.
- Do not treat LangSmith as a ledger, add new runtime Skills beyond the
  approved generic read-only skills, add Async Subagents, make the frontend a
  business authority, add frontend-specific backend aliases, or expand to
  public online or multi-tenant infrastructure unless the task explicitly
  approves that scope.
- Do not rename compatibility identifiers, API paths, persisted identities,
  profile IDs, or benchmark IDs as incidental cleanup.

Changing these boundaries requires an ADR or an explicit update to an existing
decision document in the same PR.

## Risk-Based Execution

Use the lightest workflow that gives enough confidence.

### Level 1: Local Change

Examples: wording, comments, narrow tests, dependency metadata, local refactor
with no behavior change.

- Inspect the affected files.
- Make the smallest change.
- Run focused checks and `git diff --check`.
- No worktree, design document, TDD cycle, full suite, Autoplan, or GStack
  review is required unless the change reveals wider risk.

### Level 2: Behavior Change

Examples: bug fix, API behavior, persistence logic, Agent/tool behavior.

- Add a failing regression or behavior test first.
- Implement the smallest fix.
- Run focused tests, then broader tests matching the blast radius.
- Update affected documentation in the same change.
- Use an isolated worktree when the change is substantial or the checkout is
  not clean.

### Level 3: Contract Or Architecture Change

Examples: public API/schema, identity model, evidence lifecycle, durable HITL,
cross-module behavior, multiple planned PRs.

- Confirm or write an approved spec/plan.
- Use an isolated worktree and TDD.
- Update ADRs or public contracts.
- Run full relevant verification.
- Use `gstack-workflows:autoplan`, `gstack-workflows:review`, documentation audit, or an independent second
  view only when their expected value justifies their cost or the user requests
  them.

Do not force small work through Level 3. If scope grows, explicitly raise the
level instead of silently expanding the process.

## Subagent Policy

Subagents are optional. Use a bounded agent when independent context or review
has a clear benefit. Parallel work additionally requires independently scoped
units, clear file ownership, separate verification boundaries, and enough
benefit to exceed coordination cost.

- The parent Agent owns shared contracts and files, the final integrated branch
  state, cross-lane integration, full relevant verification, and the
  consolidated terminal report. Bounded child or lane commits are allowed.
- Keep highly coupled work serial, including shared authority files,
  migrations, public contracts, and changes with ordering dependencies.
- Do not delegate merely because a task can be split. Prefer focused serial
  execution when ownership or verification boundaries are unclear.
- Do not automatically request a second-model review.

This policy governs development workflow. It does not remove the product's
existing runtime research sub-agent architecture.

## Skills And Phase Ownership

- Use the official `gstack-workflows` plugin primarily for design, plan challenge,
  review, QA, and release audits.
- Use Superpowers primarily for brainstorming, TDD, systematic debugging, plan
  execution, review-finding resolution, and completion verification.
- Read the current Skill instructions before use. Handoffs include the relevant
  Skill names and entry points; each worker loads the Skills needed for its task.
  Briefly identify the chosen method in the existing progress or return.
- Assign one primary workflow controller per phase. Do not stack Skills with
  overlapping control responsibilities or make every available Skill a
  mandatory gate.
- Apply specialized security, performance, documentation, or independent
  review Skills only when the risk-based execution level or task evidence
  justifies their cost.

### Approved Design To Implementation

- Accept a public-neutral brief or approved repository spec with scope,
  constraints, observable acceptance, Git starting point, delivery owner, and
  authorization. Follow the persistence rules below; small work needs only a brief.
- Verify current rules and Git state, reuse the approved design, and use
  `superpowers:writing-plans` only to fill implementation gaps. The delivery owner
  decides in-scope details; changes to goals, key design, acceptance, or authorization
  return to the owner of the approved design.
- Check the rules in the actual execution worktree; another checkout's update does
  not update this one. Route unresolved approvals to the designated coordinating
  owner when present, and reuse existing authorization within its scope.
- Choose direct execution for small work, or one plan route:
  `superpowers:executing-plans` for self-implementation, or
  `superpowers:subagent-driven-development` for managed implementation and review.
  Do not restart the full manager workflow inside a task worker.
- Return the exact HEAD, diff and acceptance evidence, plus remaining work.
  Distinguish local completion from hosted delivery; missing remote authorization
  does not prevent preparing a reviewable local result.

## Working Rules

- Codex owns planning, implementation, testing, documentation, PR preparation,
  and final verification.
- Complete safe, obvious steps without asking the user to remember the process.
- Ask only when missing information creates meaningful implementation risk or
  an action requires authorization.
- Investigate root cause before fixing unexplained failures.
- Do not over-plan or continue expanding after acceptance criteria are met.
- Do not overwrite, revert, or delete unrelated user changes.
- Never claim a test, review, benchmark, build, push, PR, merge, or deployment
  without actual evidence.

## Execution Handoff And Waiting

- At completion or a defined stop condition, report the result, branch, worktree,
  exact HEAD, actual verification and remaining work once. State labels are
  optional; distinguish local results, hosted delivery and an unmet acceptance goal.
- Return once on completion or when a decision is needed. Prefer native results
  and event waits; do independent work while waiting and avoid unchanged polling
  or duplicate progress reports.

## Testing And Verification

- Behavior changes require TDD; bug fixes require a regression test.
- Use unit tests for deterministic behavior, contract tests for schemas, and
  integration tests for persistence, concurrency, API, and worker boundaries.
- Mock remote providers in required CI. Keep real-provider and benchmark runs
  explicit and separate.
- Run focused tests during implementation. Run the full suite when shared
  behavior or multiple modules are affected.
- Reuse verification when its inputs have not changed; documentation-only edits
  do not require repeating runtime checks. A live or costly failure needs a
  supported root cause and working diagnostics before another authorized run;
  changing the harness does not reset repeated failure of the same goal.
- After a second substantive failure of the same real/costly acceptance goal,
  stop those runs and return to the coordinating owner for a route decision.
  An explicitly frozen stage requires an explicit instruction to resume.
- Scripted provider tests prove their programmed flow, not autonomous model
  behavior or research quality. Report an unmet goal even when a local fix passes.
- `.github/workflows/ci.yml` is the current authority for required hosted
  gates. The commands below are common local entry points only; do not infer or
  invent hosted check names or passing status from this file.

Common commands:

```bash
python -m pytest -q

cd frontend
npm ci
npm run test
npm run lint
npm run build
cd ..

python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json

git diff --check
```

The Agent Research Operations Console is built and tested independently from
the backend runtime. Run its checks when frontend code or frontend
documentation changes.
Run the durable HITL gate only when that contract is affected and Docker is
available. If a check cannot run, state the exact reason.

## Documentation

Ship documentation with the behavior it describes:

- Public API, Tool Client, configuration, or errors: update reference docs and
  contract tests.
- Architecture, identity, Evidence, or review lifecycle: update the relevant
  decision and explanation.
- Benchmark or public metric: update the evidence source and limits.
- Installation or operator workflow: update the relevant guide.
- Internal refactor with no behavior change: record `No documentation impact`
  in the PR.

Persist Superpowers specs and plans only for architecture, public contracts,
multi-module work, or multiple PRs. Use the Issue or PR body for small changes.
Long-lived architecture belongs in `docs/decisions/`.

Do not commit raw GStack artifacts, private planning notes, personal paths, or
private job-search motivation/presentation context.

## Git, Security, And Completion

- Inspect `git status` before editing.
- Use a short `codex/<scope>-<slug>` branch and route intended changes through
  a PR.
- Stage only intentional files; do not use `git add -A` or `git add .`.
- Do not push, create a PR, merge, release, deploy, install tools, or publish
  without explicit authorization, including a valid user delegation. Tool-required
  user confirmation remains binding.
- Never commit secrets, tokens, cookies, `.env`, private configuration, or
  private source material.
- Keep raw sessions, execution receipts, temporary screenshots and tool state in
  ignored directories. Preserve useful public specs/plans, ADRs, test fixtures and
  selected presentation assets; ignore rules do not untrack existing files or
  replace package, archive and container inventory checks.
- Treat uploads, model output, tool output, and external responses as
  untrusted.
- Do not expose absolute paths, credentials, raw exceptions, or stack traces in
  public responses.
- Public claims require repository-visible tests, benchmarks, or referenced
  evidence.
- Merge only with explicit user authorization and the required hosted checks
  satisfied. Confirm that the PR head still matches the reviewed HEAD before
  merging.
- After a squash merge, verify that the merge commit tree equals the reviewed
  head tree before fast-forwarding the primary `main` checkout.
- Clean up only task-owned, clean, inactive worktrees and branches with no open
  PR or active task. Before deletion, prove that intended unique changes are
  retained in a merged commit, tag, or explicit archive. Abandoning unique
  commits requires explicit authorization; preserve anything with unclear
  ownership or state. Prune stale worktree metadata, confirm other worktrees
  are unchanged, and do not touch unrelated branches.

A task is complete when the requested behavior matches scope, appropriate
verification actually passed, required documentation is current, the diff is
clean and intentional, and remaining risks or skipped checks are reported.

PR descriptions default to Simplified Chinese with technical literals retained.
Explain the problem, resulting behavior, actual verification and material limits;
scale detail to the change. Headings and checkbox style are not extra merge gates.
After creating or updating a PR, read back its actual identity and content. Correct
materially stale claims when delivery changes them; a documentation update failure
is reported as remaining work, separately from the verified code and CI result.
