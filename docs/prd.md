# PRD: Decision Research Agent

## Product Overview

Decision Research Agent is a long-running, evidence-driven research agent built
on LangChain, LangGraph, DeepAgents, and LangSmith diagnostics. It turns
open-ended research questions into auditable runs, source-backed evidence,
controlled review decisions, and canonical delivery artifacts.

The v0.1.0 release surface remains backend-first: HTTP API, WebSocket
monitoring, Python Tool Client, operator scripts, tests, and documentation.
The current repository also includes a separately built Agent Research
Operations Console with a deterministic Static Demo and bounded local Live
Backend mode.

## Target Users

- Agent and LLM application engineers who need a reference implementation for
  evidence-governed long-task research.
- Operators or first-party automation that need run-scoped research execution
  and bounded result retrieval.
- HR or hiring-intelligence workflows that need traceable capability signals
  from declared evidence.

## Core Value

1. **Evidence-governed delivery**: findings, claims, review bundles, and
   DecisionBrief outputs bind to persisted evidence snapshots instead of raw
   prompt text.
2. **Framework-native execution**: DeepAgents handles harness behavior, skills,
   middleware, runtime context, and tool filtering while the service layer owns
   business state.
3. **Auditable run lifecycle**: `ResearchRun`, evidence, review, verification,
   publication, and canonical result state are persisted in the application DB.
4. **Operator-safe gates**: durable HITL and evidence verification are
   default-disabled and require explicit readiness checks before use.

## Core Capabilities

| Capability | Description | Status |
|---|---|---|
| Canonical run execution | `POST /api/runs` creates a run-scoped execution with `thread_id`, `run_id`, and `segment_id` | Implemented |
| Canonical result delivery | `GET /api/runs/{run_id}/result` returns bounded deliverable artifacts only when ready | Implemented |
| Generic research profile | DeepAgents-native generic harness with read-only skills and approved tools | Implemented |
| Talent Hiring Signal profile | Restricted profile, declared evidence scope, deterministic review bundle and DecisionBrief | Implemented |
| Evidence preservation | Timeout, cancellation, and completion paths preserve frozen evidence through fenced finalization | Implemented |
| Durable HITL feasibility | Single-node SQLite review gate, disabled by default, with 13-gate safety report | Implemented |
| Evidence verification authority | Append-only human verification decisions and revisioned publications | Implemented |
| Tool Client integration | Canonical Python client for health, run, result, review, and evidence commands | Implemented |
| Agent Research Operations Console | Static operational snapshot plus bounded local `health -> run -> result` API consumption | Implemented |

## Success Criteria

- Backend test suite passes on clean checkout.
- Active files use the canonical technical identifier
  `decision-research-agent`.
- Canonical identity scanner returns no violations.
- `docker compose config --quiet` succeeds with a generated `.env`.
- Durable review and evidence verification remain disabled by default.
- API and Tool Client docs describe only active public contracts.
- Frontend test, type/lint, build, and dependency audit gates pass.

## Technical Constraints

- Agent framework: LangChain.
- Runtime foundation: LangGraph.
- Research harness: DeepAgents.
- Trace diagnostics: LangSmith, privacy-first, not a business ledger.
- Business ledger: application SQLite database through service-owned
  repositories.
- Deployment target: backend Docker service plus optional MySQL dependency.
- UI: the separately built Agent Research Operations Console can create a
  ResearchRun and consume canonical API/result contracts, but never becomes
  business authority.

## Current Non-Goals

- Multi-tenant deployment, RBAC, Postgres, or multi-replica coordination.
- Runtime Async Subagents beyond the approved profile architecture.
- LLM-based evidence verification authority.
- Browser automation or automatic real-source proof fetching.
- Public hosted research execution or authenticated browser access.
- Frontend-owned review, verification, publication, or delivery state.
- Chat, multi-turn interruption, run cancellation, or task editing.
- Legacy task/thread API compatibility.

## Change Log

| Date | Change |
|---|---|
| 2026-05-19 | Initial PRD created |
| 2026-06-26 | Rewritten for v0.1.0 canonical backend, DeepAgents-native harness, and legacy runtime removal |
| 2026-06-30 | Added the separately built Agent Research Operations Console and bounded local Live Backend consumer flow |
