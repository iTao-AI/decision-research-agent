# Agent Integration

Deep Search Agent exposes a small Python tool client for upper-layer agents and automation scripts.

The client wraps the existing HTTP API:

- `GET /health`
- `POST /api/task`
- `GET /api/tasks/{thread_id}`
- `GET /api/token-usage/{thread_id}`
- `GET /api/research/runs/{thread_id}`
- `GET /api/research/runs`

It does not store API keys, start the backend server, manage frontend sessions, or run benchmark jobs.

## Location

```bash
tools/deep_search_agent_tool.py
```

## Configuration

Set defaults with environment variables:

| Variable | Purpose |
|---|---|
| `DEEP_SEARCH_AGENT_URL` | API base URL, default `http://127.0.0.1:8000` |
| `DEEP_SEARCH_AGENT_API_KEY` | Optional API key sent as `X-API-Key` |
| `DEEP_SEARCH_AGENT_TIMEOUT_SECONDS` | Request timeout, default `10` |

Command-line flags override non-secret environment defaults. API keys are accepted only through `DEEP_SEARCH_AGENT_API_KEY`, not command-line arguments.

## Healthcheck

```bash
python tools/deep_search_agent_tool.py healthcheck
```

Expected output:

```json
{
  "status": "ok",
  "service": "deep-search-agent"
}
```

## Start A Research Task

```bash
python tools/deep_search_agent_tool.py start-task \
  --query "Research question" \
  --thread-id "demo-thread-001"
```

The command returns the API response, including `thread_id`.

## Poll Task Status

```bash
python tools/deep_search_agent_tool.py get-task \
  --thread-id "demo-thread-001"
```

Terminal statuses come from the API persistence layer:

- `completed`
- `completed_with_fallback`
- `failed`

## Token Usage

```bash
python tools/deep_search_agent_tool.py token-usage \
  --thread-id "demo-thread-001"
```

## ResearchRun And EvidenceLedger

After a task reaches a terminal state, fetch the auditable research run:

```bash
python tools/deep_search_agent_tool.py research-run \
  --thread-id "demo-thread-001"
```

The response includes task status, token usage, quality gate output, diagnostics,
and evidence entries extracted from tool messages. Evidence entries start as
`unverified`; they are marked `cited` when their source URL appears in the final
Markdown report.

List recent research runs:

```bash
python tools/deep_search_agent_tool.py research-runs --limit 20
```

## Error Behavior

The client exits non-zero and prints:

```json
{
  "status": "failed",
  "error": "..."
}
```

Failures include connection errors, timeouts, non-2xx HTTP responses, and malformed JSON.

## Security Notes

- The client sends `DEEP_SEARCH_AGENT_API_KEY` as `X-API-Key` when configured.
- The client never prints the API key.
- The CLI does not accept API keys as command-line arguments, avoiding shell-history and process-list exposure.
- Thread IDs are restricted to 1-128 letters, digits, dots, underscores, or hyphens.
- Use loopback binding for local agent orchestration unless remote access is intentionally configured.
