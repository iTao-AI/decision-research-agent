# Agent Tool Client Design

## Context

Deep Search Agent already exposes a FastAPI API for asynchronous research tasks:

- `POST /api/task`
- `GET /api/tasks/{thread_id}`
- `GET /api/token-usage/{thread_id}`

Agents and automation scripts can call those endpoints directly, but direct usage requires each caller to know endpoint paths, authentication headers, timeout handling, and response shapes. A small tool client gives upper-layer agents a stable integration boundary.

## Goal

Add a neutral Python tool client that can:

- check API service health;
- start a research task;
- fetch persisted task status;
- optionally fetch token usage;
- pass `X-API-Key` without printing it;
- read API keys only from the environment, never command-line arguments;
- encode thread IDs in URL path segments;
- return machine-readable JSON from a CLI.

Also add a lightweight `GET /health` endpoint so callers can verify service readiness without starting a task.

## Non-Goals

- No changes to agent planning logic.
- No frontend changes.
- No new background worker model.
- No API key storage or secret printing.
- No benchmark or production deployment claims.

## API Additions

Add:

- `GET /health`
  - Returns `{"status":"ok","service":"deep-search-agent"}`.
  - Bypasses API key middleware like docs endpoints.

## Tool Client

Create `tools/deep_search_agent_tool.py`.

Configuration:

- `DEEP_SEARCH_AGENT_URL`, default `http://127.0.0.1:8000`
- `DEEP_SEARCH_AGENT_API_KEY`, optional
- `DEEP_SEARCH_AGENT_TIMEOUT_SECONDS`, default `10`

Commands:

- `healthcheck`
- `start-task --query <text> [--thread-id <id>]`
- `get-task --thread-id <id>`
- `token-usage --thread-id <id>`

All commands print JSON and exit non-zero on structured failures.

## Error Handling

- Connection errors, timeouts, non-2xx HTTP responses, and malformed JSON return `{"status":"failed","error":"..."}`.
- The client sends but never prints API keys.
- The CLI rejects API-key command-line arguments.
- The server validates caller-provided thread IDs before using them in filesystem paths.

## Testing

Add tests that mock HTTP calls and verify:

- healthcheck reads `/health`;
- start-task posts query and thread id;
- get-task and token-usage call the expected endpoints;
- thread IDs are URL-encoded and unsafe IDs are rejected server-side;
- API key is sent in headers but absent from printed or returned payloads;
- HTTP failure returns a structured client error.

Add API test coverage for `GET /health`.
