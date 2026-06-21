# Agent Integration

Decision Research Agent exposes a small Python Tool Client for upper-layer
agents and automation scripts. The canonical entrypoint is:

```bash
tools/decision_research_agent_tool.py
```

The legacy `tools/deep_search_agent_tool.py` entrypoint remains a thin
compatibility shim. Both entrypoints call the same implementation.

The client wraps the existing HTTP API. It does not store API keys, start the
backend, manage frontend sessions, or run benchmark jobs.

## Canonical Configuration

| Variable | Purpose | Empty or invalid canonical value |
|---|---|---|
| `DECISION_RESEARCH_AGENT_URL` | API base URL | Empty or whitespace uses `http://127.0.0.1:8000` |
| `DECISION_RESEARCH_AGENT_API_KEY` | Optional `X-API-Key` | Empty explicitly disables the auth header |
| `DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS` | Request timeout | Empty, non-numeric, or non-positive uses `10` |
| `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES` | Server-bundled benchmark fixtures | Only `true` enables the provider |
| `DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT` | Talent graph recursion budget | Empty, non-numeric, or non-positive uses the safe default |

Command-line `--base-url` and `--timeout` override environment defaults. API
keys are accepted only through environment variables, not CLI arguments.

Canonical keys win whenever they are present, including when empty. A
conflicting legacy value is never consulted. Legacy-only configurations remain
supported:

| Canonical | Legacy alias |
|---|---|
| `DECISION_RESEARCH_AGENT_URL` | `DEEP_SEARCH_AGENT_URL` |
| `DECISION_RESEARCH_AGENT_API_KEY` | `DEEP_SEARCH_AGENT_API_KEY` |
| `DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS` | `DEEP_SEARCH_AGENT_TIMEOUT_SECONDS` |
| `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES` | `DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES` |
| `DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT` | `DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT` |

Legacy-only use, or a legacy key ignored because its canonical key is present,
emits a value-free `FutureWarning` on stderr. Command JSON remains on stdout, so
automation can parse it without mixing deprecation text into the payload.

## Healthcheck And Doctor

```bash
python tools/decision_research_agent_tool.py healthcheck
python tools/decision_research_agent_tool.py doctor
```

The exact health response remains:

```json
{
  "status": "ok",
  "service": "deep-search-agent"
}
```

Both commands continue to report `service=deep-search-agent` by contract. A
successful canonical migration is demonstrated by using the canonical script
and environment keys and receiving a passing response; the compatibility
service ID is not product discovery.

`doctor` also checks the controlled durable review runtime. When the feature is
disabled, the durable review check reports `disabled` and the overall command
can still succeed. When enabled, worker, schema, checkpoint compatibility, and
the recorded gate report must be ready.

## Common Commands

```bash
python tools/decision_research_agent_tool.py start-task \
  --query "Research question" \
  --thread-id "demo-thread-001"

python tools/decision_research_agent_tool.py get-task \
  --thread-id "demo-thread-001"

python tools/decision_research_agent_tool.py token-usage \
  --thread-id "demo-thread-001"

python tools/decision_research_agent_tool.py research-run \
  --thread-id "demo-thread-001"

python tools/decision_research_agent_tool.py research-runs --limit 20
```

Terminal task statuses are `completed`, `completed_with_fallback`, and
`failed`. ResearchRun responses include task status, token usage, quality gate
output, diagnostics, and EvidenceLedger entries.

## Controlled Review Commands

The backend requires its controlled review configuration separately. The Tool
Client reads only canonical connection settings:

```bash
export DECISION_RESEARCH_AGENT_URL
export DECISION_RESEARCH_AGENT_API_KEY
export DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS
```

Do not pass an API key on the command line.

```bash
python tools/decision_research_agent_tool.py review list \
  --status waiting_decision \
  --limit 20

python tools/decision_research_agent_tool.py review show \
  --run-id "$RUN_ID"

python tools/decision_research_agent_tool.py review approve \
  --run-id "$RUN_ID" \
  --wait

python tools/decision_research_agent_tool.py review reject \
  --run-id "$RUN_ID" \
  --reason-file "$REJECTION_REASON_FILE" \
  --wait

python tools/decision_research_agent_tool.py review wait \
  --run-id "$RUN_ID" \
  --poll-seconds 1 \
  --wait-timeout-seconds 120

python tools/decision_research_agent_tool.py result \
  --run-id "$RUN_ID"
```

`review show`, `review approve`, `review reject`, and `review wait` accept an
optional `--review-id`. When omitted, the client resolves the current review ID
from the run projection. `review reject` accepts exactly one of
`--reason-file` or `--reason-stdin`; there is no plain `--reason` argument.
`approve` and `reject` derive a deterministic decision ID unless
`--decision-id` is provided.

## Existing Deployment Upgrade

Keep matching legacy keys during the rollback window:

```bash
# 1. Add canonical keys without removing rollback-compatible legacy keys.
export DECISION_RESEARCH_AGENT_URL="$DEEP_SEARCH_AGENT_URL"
export DECISION_RESEARCH_AGENT_API_KEY="$DEEP_SEARCH_AGENT_API_KEY"
export DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS="$DEEP_SEARCH_AGENT_TIMEOUT_SECONDS"

# 2. Verify through the canonical entrypoint.
python tools/decision_research_agent_tool.py healthcheck

# 3. Keep legacy keys through the rollback window; remove them only after the
#    documented release gate is satisfied.
```

New installations should use canonical keys only.

## Rollback

Pre-migration code does not understand `DECISION_RESEARCH_AGENT_*`. Before
rolling code back, ensure the matching `DEEP_SEARCH_AGENT_*` keys remain
populated or restore them before the process starts. A canonical-only
installation cannot be rolled back safely without that configuration step.

Legacy aliases remain for at least two tagged releases after this migration.
Removal requires a separate approved breaking-change plan, a first-party
consumer inventory, no active first-party legacy use outside shims, tests, and
compatibility documentation, plus release-note migration instructions. This
repository currently has no tags, so this migration does not start a fabricated
date-based countdown.

## Benchmark Process Boundary

`scripts/talent_value_gate_runner.py` temporarily sets the canonical fixture
flag in `os.environ`. It runs profiles sequentially and must not be invoked
concurrently in the same process. The runner restores or removes the temporary
value after success, timeout, or exception.

## Error And Security Behavior

The client exits non-zero and prints structured JSON for connection errors,
timeouts, non-2xx responses, malformed JSON, `manual_recovery`, and review wait
timeouts. Structured server error envelopes retain their stable `code`,
`problem`, `fix`, and `retryable` fields.

- The API key is never printed.
- The CLI rejects API keys on the command line.
- Rejection reasons are read only from a file or standard input and are not
  echoed by the immediate decision response.
- Actor fingerprints, lease owners, checkpoint paths, and raw tracebacks are
  not printed.
- Use loopback binding unless remote access is intentional.
- The standalone Tool Client reads process environment variables directly; it
  does not load the repository `.env`.
