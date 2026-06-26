# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- No unreleased changes.

## [0.1.0] - 2026-06-26

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
