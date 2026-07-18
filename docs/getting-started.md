# Getting Started

This tutorial starts the Python 3.11 backend, verifies the service, uses the
first-party Tool Client to retrieve one canonical research run, and opens the
React console in deterministic Static Demo mode.

## Prerequisites

- Python 3.11
- Git
- Provider credentials for a real research run
- Node.js `20.19+`, `22.13+`, or `24+` for the optional demo console

Keep credentials in `.env`. Do not pass API keys on the command line or commit
the environment file.

## 1. Create The Environment

From the repository root:

```bash
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps -r constraints.txt
```

Edit `.env`. At minimum, configure the selected model provider. Configure
`TAVILY_API_KEY` when the run needs public web search. If `API_SECRET` is set,
also export the same value for the Tool Client:

```bash
read -r -s DECISION_RESEARCH_AGENT_API_KEY
export DECISION_RESEARCH_AGENT_API_KEY
```

Paste the matching value at the silent prompt and press Enter. This keeps the
credential out of command arguments and shell history.

The checked-in source template uses `API_SECRET=`. Empty means the bounded
credential-free source mode; no sentinel value is accepted as a secret. In
that mode, the direct peer and literal Host must both be loopback. When a real
secret is configured, the Tool Client sends it as `X-API-Key` from
`DECISION_RESEARCH_AGENT_API_KEY`.

## 2. Start The Backend

```bash
python api/server.py
```

This supported source launcher passes the already-constructed app to Uvicorn
on `127.0.0.1` with reload disabled and warning-level logging. Leave this
terminal running.

CORS and Origin checks are not authentication. WebSocket credentials are
header-only, and query credentials are rejected. Non-loopback direct use
requires a configured key and operator-owned TLS and is not a supported hosted
deployment.

### Authenticated Compose alternative

Compose is a separate authenticated launch form, not the empty-secret source
mode. It requires non-empty `API_SECRET`, `MYSQL_ROOT_PASSWORD`, and
`MYSQL_PASSWORD` values before configuration succeeds:

```bash
docker compose config --quiet
docker compose up -d --build backend
```

The backend still listens on container-internal `0.0.0.0:8000`, while Compose
publishes backend/MySQL only on host `127.0.0.1`. Health-gated startup,
warning-level logging, privilege settings, safe value generation, optional
`DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE` isolation, existing-volume
compatibility, and rollback are documented in
[Secure Local Runtime Operations](operations/secure-local-runtime.md).

## 3. Verify Health

In a second terminal with the virtual environment active:

```bash
curl --fail --silent http://127.0.0.1:8000/health
```

Expected result:

```json
{"status":"ok","service":"decision-research-agent"}
```

This exact response proves process/service identity only. It does not establish
database, provider, model, tool, or research readiness.

## 4. Check Integration Readiness

```bash
python tools/decision_research_agent_tool.py doctor
```

`doctor` returns structured JSON. Required failures include a bounded cause and
fix; optional disabled workflows do not block a generic run.

## 5. Create A Canonical Run

```bash
python tools/decision_research_agent_tool.py run \
  --query "Compare the documented trade-offs of two implementation options" \
  --thread-id "getting-started" \
  --wait
```

The JSON response includes a generated `run_id`, terminal execution state, and
delivery state. Copy the returned identifier:

```bash
export RUN_ID="run_replace_with_returned_id"
```

## 6. Retrieve The Result

```bash
python tools/decision_research_agent_tool.py result --run-id "$RUN_ID"
```

A ready generic run returns the persisted Markdown artifact with its ID, kind,
media type, content hash, and content. The command does not read a local output
path or framework checkpoint.

## 7. Open Static Demo

Static Demo does not call the backend and remains available when provider or
service configuration is unavailable:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. The console starts in Static Demo mode and shows
the run lifecycle, evidence, review, verification, canonical result, and
architecture boundaries without creating a ResearchRun.

To connect the console to the local backend, follow the bounded setup in the
[Demo Console guide](demo-console.md). Live Backend requires an exact CORS
origin and a loopback-only unauthenticated backend because the console does not
accept or store API credentials.

## Troubleshooting

### Provider configuration is missing

Set the provider URL, model name, and API key in `.env`, then restart the
backend. Use `doctor` to distinguish provider configuration from optional
review or verification flags.

### Authentication returns 401

When `API_SECRET` is set on the backend, set
`DECISION_RESEARCH_AGENT_API_KEY` to the same local secret before running the
Tool Client. Do not put it in shell history as a command argument.

### The run is not terminal

`run_not_terminal` means execution is still pending or running. Re-run the
`run --wait` flow or poll `GET /api/runs/{run_id}` before requesting the
result.

### The result requires review

`run_review_required` means the current Talent publication is not deliverable
until the default-disabled controlled review workflow resolves it. Follow the
[Controlled Review](operations/controlled-review-workflow.md) runbook in an
authorized environment; approval permits delivery but does not verify
Evidence.

### The artifact is unavailable

`run_result_unavailable` indicates a missing, empty, unsafe, oversized, or
hash-mismatched persisted artifact. Preserve the run identifier and inspect
bounded service diagnostics. Do not bypass result selection by reading runtime
files or checkpoint state.

### Live Backend reports a connection or CORS error

Static Demo remains usable. For Live Backend, start both processes on
`127.0.0.1`, configure the exact browser origin, and follow
[Demo Console troubleshooting](demo-console.md#troubleshooting).
