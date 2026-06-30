# Agent Research Operations Console

The React-based research run demonstration console explains Decision Research
Agent as an operations system rather than a chatbot. It can create a
ResearchRun, observe its lifecycle, and retrieve the canonical result without
owning business authority. It has two modes:

- **Static Demo** renders a deterministic bundled snapshot and requires no
  backend, provider, or credentials.
- **Live Backend** creates one generic ResearchRun against a local backend,
  polls its bounded status, and renders the canonical result returned by
  `GET /api/runs/{run_id}/result`.

The console is a consumer of service-owned state. It does not write review or
verification decisions, create database authority, or bypass result gates.

## Prerequisites

- Node.js `20.19+`, `22.12+`, or `24+`
- npm
- Python 3.11 and provider configuration for Live Backend only

## Run Static Demo

From the repository root:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Static Demo is selected by default. It does not
send a network request to the Decision Research Agent backend.

## Run Live Backend Locally

Live Backend is a local demonstration path, not a public deployment mode. The
current console does not accept or store API credentials. Use an
unauthenticated backend only when it is explicitly bound to the loopback
interface; do not expose this setup to a LAN or public network.

### 1. Configure the exact browser origin

In the repository-root `.env`, keep provider configuration for the selected
model and set:

```dotenv
API_SECRET=
DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN=http://127.0.0.1:5173
```

CORS is deny-by-default. The configured origin must exactly match the URL used
to open the Vite development server.

### 2. Start the backend on loopback

From the repository root with the Python environment active:

```bash
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

Verify the service identity:

```bash
curl --fail --silent http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"decision-research-agent"}
```

### 3. Start the console

In a second terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`, select **Live Backend**, keep Backend base URL as
`http://127.0.0.1:8000`, and run these actions in order:

1. Select **检查后端 / Check backend**.
2. Confirm the service reports ready.
3. Select **运行并获取结果 / Run and fetch result**.
4. Inspect the returned `run_id`, terminal state, and canonical artifact.

The client waits for at most ten minutes. A client timeout stops browser
polling but does not cancel the server-side ResearchRun. Switching back to
Static Demo prevents stale in-flight responses from replacing the static view.

The editable backend endpoint accepts only `http://127.0.0.1:<port>`. The
console rejects other hosts, HTTPS, missing ports, credentials, paths, query
strings, and fragments before sending a network request. Health is ready only
for the exact `{"status":"ok","service":"decision-research-agent"}` identity.

## Authentication Boundary

When `API_SECRET` is non-empty, REST requests require `X-API-Key`. The current
console intentionally has no credential input or browser credential storage,
so authenticated backends return `401`. Use the first-party Tool Client for an
authenticated environment. Do not place an API key in the backend base URL,
query string, source code, or Vite build variables.

## Troubleshooting

### `connection_failed`

Confirm that the backend is running on `127.0.0.1:8000` and that the console
base URL uses the same host rather than mixing `localhost` and `127.0.0.1`.

### Browser CORS failure

Set `DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN` to the exact console origin,
restart the backend, and retry the health check.

### `401 Unauthorized`

The backend has `API_SECRET` configured. Return to Static Demo or use the Tool
Client. Do not weaken authentication on a backend reachable outside loopback.

### Run or result failure

The console renders the bounded service error and preserves a safe `run_id`
when one exists. Provider failures, review-required results, and unavailable
artifacts remain backend-owned states; the console does not override them.

## Contributor Verification

```bash
cd frontend
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
```

Also run the backend-side frontend boundary contract:

```bash
python -m pytest tests/unit/test_frontend_retirement.py \
  tests/unit/test_documentation_contracts.py -q
```
