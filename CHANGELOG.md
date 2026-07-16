# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.1.4] - 2026-07-16

### Durable run failure causes

- Added immutable application-database `run_failure_causes_v1` through
  `009_run_failure_cause_v1`; historical failed runs report `not_observed`
  without inferred diagnosis, while new terminal failures atomically persist
  bounded dispatch, execution, or finalization causes.
- Added an additive `failure_cause` field only to
  `GET /api/runs/{run_id}` and a deterministic 16-case proof.
  `GET /api/runs/{run_id}/result`, `409 run_failed`, and the frozen
  `dra.downstream-consumer.v1` fixture remain unchanged.
- The contract does not claim exactly-once execution, hard preemption,
  provider diagnosis, multi-instance high availability, or a billing record.

### Console live authority closure

- Live Backend now renders only real service-owned run status and canonical
  result observations while Static Demo remains isolated.
- Ambiguous create reconciliation reuses the same key and byte-equivalent
  request, and a known `run_id` enables GET-only observation resume without a
  replacement create.
- The loopback-only Console still accepts no credentials and owns no review,
  verification, publication, or delivery authority. It does not claim durable
  browser intent, production deployment, exactly-once execution, or
  live-provider quality.

## [0.1.3] - 2026-07-14

### Durable run dispatch

- Added atomic `run_dispatches_v1` intent creation and migration
  `008_run_dispatch_reconciliation`, with exact verification, no backfill, and
  isolated `.pre-run-dispatch.bak` restore protection.
- Added single-node pre-execution reconciliation, exact start fencing, bounded
  asynchronous retry through three attempts, and deterministic public proof
  artifacts. `status: started` remains an acceptance acknowledgement; the
  contract does not claim exactly-once or running-execution recovery.

## [0.1.2] - 2026-07-14

### Run creation reliability

- Added optional durable `Idempotency-Key` handling for run creation, including
  atomic replay/conflict behavior, concurrent duplicate serialization, and
  Tool Client recovery after a lost response.
- Added a deterministic public reconciliation proof while explicitly excluding
  crash-before-schedule recovery and exactly-once execution claims.

## [0.1.1] - 2026-07-13

### Tool Client

- Added a structured Tool Client golden flow for creating a run, waiting with
  a bounded client deadline, and retrieving the canonical result through
  `--wait --result`.
- Added bounded structured errors for connection, polling, review-required,
  invalid-response, and result-delivery failures.

### Agent Research Operations Console

- Added the React-based Agent Research Operations Console with deterministic
  Static Demo and a bounded loopback-only Live Backend flow for
  `health -> run -> canonical result`.
- Added visual and accessibility QA plus public architecture, setup, and demo
  documentation. The console does not accept credentials or own business
  authority.

### Deterministic contract proof

- Added a deterministic downstream consumer fixture and validator proof for
  status, canonical result, Evidence, fallback, and failure boundaries.

- Added a credential-free deterministic regression gate with eight fixed cases,
  six policy evaluators, reviewed JSON/Markdown baselines, bounded comparison
  output, and stable public error codes.
- Reused Pydantic for structural contracts while keeping DRA policy evaluation,
  deterministic serialization, and authority boundaries project-owned.

### Maintenance

- Completed scoped frontend and CI maintenance for `actions/setup-node`,
  `jsdom`, Vite, and Vitest, with Node compatibility documentation and the demo
  route kept current.

## [0.1.0] - 2026-06-28

### Backend-and-CLI release

- Established Decision Research Agent as the canonical backend service, REST
  API, Tool Client, Docker, and health identity.
- Reworked execution around a DeepAgents-native generic harness, LangChain
  Agent Framework integration, LangGraph runtime configuration, and
  privacy-first LangSmith diagnostics.
- Added canonical run-scoped execution and result delivery through
  `POST /api/runs` and `GET /api/runs/{run_id}/result`.
- Persisted generic Markdown result artifacts and Talent DecisionBrief /
  publication artifacts through service-owned application database contracts.
- Added controlled durable review and controlled evidence verification
  workflows behind explicit disabled-by-default feature flags.

### Verification and evidence

- Added deterministic runtime version reporting for DeepAgents, LangChain,
  LangGraph, LangSmith, FastAPI, Pydantic, and Python.
- Added document contract tests for current framework terminology, canonical
  first-run flow, Markdown-only delivery, and removed surface checks.
- Preserved existing real-source proof, durable review, evidence verification,
  canonical identity, and migration test coverage.

### Breaking Changes

- Pre-v0.1.0 compatibility aliases and task/thread routes were removed from the
  active product surface.
- Pre-v0.1.0 Tool Client shims were removed; use
  `tools/decision_research_agent_tool.py`.
- The repository no longer ships a frontend service.
- File upload/download and in-agent PDF generation are not part of v0.1.0.
- Canonical delivery is Markdown-only delivery through the result endpoint.

### Migration

- Set canonical `DECISION_RESEARCH_AGENT_*` environment variables before
  starting the service.
- Run `python scripts/run_identity_migration.py --db "$DECISION_RESEARCH_AGENT_DB_PATH" --backup "$BACKUP_DB"` for explicit database migration when upgrading an
  existing database outside normal startup.
- Run `python scripts/retire_legacy_database.py --database "$DECISION_RESEARCH_AGENT_DB_PATH" --backup "$BACKUP_DB" --archive "$ARCHIVE_DB"` to archive pre-v0.1.0
  tables; add `--drop-legacy-tables` only during an operator-reviewed cleanup
  window.

## [0.0.1.0] - 2026-06-02

### Added

- Added API key protection for REST API routes and WebSocket connections, with
  development-mode passthrough when `API_SECRET` is unset.
- Added SQLite-backed task persistence so task status can be queried after
  server restarts.
- Added GitHub Actions CI for backend tests and frontend production builds.
- Added Phase 8 production-readiness spec, implementation plan, and public
  evidence documentation.

### Changed

- Switched example LLM configuration toward DeepSeek defaults while keeping
  OpenAI-compatible environment variables.
- Wired frontend API calls to send `X-API-Key`, and WebSocket connections to
  pass `api_key` where browser APIs cannot set custom headers.
- Reduced duplicate Tavily calls by routing the real internet search tool
  through per-session search de-duplication.
- Restored prompt execution-order instructions and normalized prompt config
  line endings.

### Fixed

- Fixed CORS preflight handling so browser requests still work when API key
  auth is enabled.
- Fixed repeated frontend submissions by resetting existing SQLite task rows
  instead of failing on duplicate caller identity.
- Fixed WebSocket auth failures retrying forever by surfacing a clear
  client-side error.
- Fixed evidence docs so benchmark and E2E follow-up status no longer claim
  unsupported token before/after conclusions.
