# Agent Research Operations Console

The React-based research run demonstration console explains Decision Research
Agent as an operations system rather than a chatbot. Its primary surface is a
research brief: a concrete synthetic question, a recommended decision, the
comparison criteria, supporting findings, and the exact source material behind
each claim. It can create a ResearchRun, observe its lifecycle, and retrieve
the canonical result without owning business authority. It has two modes:

- **Static Demo** renders a deterministic bundled snapshot and requires no
  backend, provider, or credentials. The default case asks `客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？`, recommends an internal knowledge assistant, and exposes three local full-text sources with exact claim-to-excerpt links.
- **Live Backend** accepts one bounded user-authored research question. Generic
  research remains the default; **结构化证据研究 / Structured evidence research**
  explicitly selects `generic-evidence-report@1` with one `q1`. The console
  creates the selected ResearchRun against a local backend, polls bounded
  status, and renders the canonical Markdown result returned by
  `GET /api/runs/{run_id}/result`. It also allows a retained known `run_id` to
  be re-entered after a page refresh for health-gated GET-only observation.
  Ready runs whose observed profile is `generic-evidence-report` additionally
  read `GET /api/runs/{run_id}/findings`; attached runs use their actual observed
  profile, rather than the currently selected creation mode.

Delivered results in either mode use the existing report reader. An observed
result can be read as safe formatted Markdown, switched to an opt-in raw-text
view, and downloaded with the exact UTF-8 content bytes. A blocked Static Demo
run uses the same case and source boundary with policy access unconfirmed; it
remains `review_required`/`not_delivered` and offers no report or download
action.

The console is a consumer of service-owned state. It does not write review or
verification decisions, create database authority, or bypass result gates.
The question draft and temporary create intent are browser-session-only; the
service-owned status and result authority remain outside the browser. The
bounded Live Backend research question input is included in the released
`v0.1.9`; stable `v0.1.8` remains unchanged as a historical release.

## Structured Live Reader

Select **真实后端 / Live Backend**, check health, then explicitly choose
**结构化证据研究 / Structured evidence research** in **研究模式 / Research mode**.
Enter a research question and select **运行并获取结果 / Run and fetch result**.
The browser submits the exact original query and an immutable nested
`{questions: [{question_id: "q1", text: query}]}` scope. The API also supports
1–5 questions for other consumers; the console does not invent questions for
attached runs. Accepted question text shown in the report is service-owned
and may reflect server scope normalization.

Only an observed ready run of the structured profile triggers `/findings`.
The reader presents accepted questions, source-bound candidate findings, exact
excerpts, and **查看完整持久化片段 / Inspect full persisted snippet** controls.
Opening inspection focuses the full snippet region; **返回引用片段 / Return to
excerpt** restores focus. The region scrolls and wraps long Unicode text on
narrow screens. These are persisted snippets, not complete webpages or new
source fetches. All candidate/source/contradiction strings render as text;
unsafe or credential-bearing URLs have no actionable link.

Unresolved question reasons, limitations, and model-reported contradictions
remain visible. Source binding locates material in an observed source snippet;
it does not prove truth or entailment, and model-reported contradictions have
not been independently reviewed. The existing canonical Markdown reader, raw
view, and exact UTF-8 download remain available after both reads succeed.

The selected-field parser requires canonical run/profile/version/artifact
identity, coherent question dispositions and exact unique excerpt offsets.
String limits and offsets count Unicode code points using `Array.from`;
canonical JSON is bounded to 1 MiB of UTF-8 bytes. An excerpt allows up to
1000 code points. A persisted snippet has no extra fixed character bound
beyond the artifact limit. The backend remains the Evidence/hash/delivery
authority; the browser does not perform independent Evidence verification.

A completed but blocked run does not fetch findings or Markdown and exposes
only optional bounded service diagnostic codes and counts. Counts represent
question coverage, unresolved dispositions, and reference binding failures,
not answer accuracy. Missing diagnostics are not a readiness signal. Findings
read failures clear both reader presentations and show a bounded client error.
Switching profile, backend URL, or static/live mode clears the active run and
invalidates stale responses. Ambiguous create retry preserves the original
query, profile, scope, and key.

The structured live surface is implemented in the current local change. The
tracked Static Demo screenshots below remain synthetic fixtures and do not
prove the structured live path, real-provider quality, or semantic accuracy.
Desktop/narrow browser inspection is a separate integrated acceptance step;
component keyboard/Unicode checks do not substitute for rendered observations.

## Showcase Frames

The public Static Demo has three deterministic capture states under
[`docs/assets/console-showcase`](assets/console-showcase/):

- [`research-workspace-overview.png`](assets/console-showcase/research-workspace-overview.png)
  shows the compact brand header, research question, recommendation,
  comparison, supporting findings, and related sources.
- [`research-evidence-review.png`](assets/console-showcase/research-evidence-review.png)
  opens on the second linked finding and source, with the selected source and
  its supporting conclusion highlighted for review.
- [`research-blocked-recovery.png`](assets/console-showcase/research-blocked-recovery.png)
  names the unconfirmed policy access, confirms that no report was delivered,
  and shows the next human confirmation without a report or download action.

The blocked case displays `tool_failed` as its first failing lifecycle step,
`execution / execution_error` as the persisted failure-cause observation, and
`review_required / not_delivered` as the service-owned disposition. The first
displayed failing step is not a proven root cause. The failed run remains
immutable; the UI does not resume it, retry automatically, or create a
replacement run.

On the overview and evidence routes, **Conclusion and comparison** focuses the
recommendation, **View supporting evidence** moves to the currently selected
source details, and **Read the full report** opens the existing report reader.
Each finding can open its linked source and return focus to the finding. The
evidence route begins with the second linked finding/source selected. The
blocked route has no report shortcuts and never retries automatically. At
desktop widths of 1100 px or more, the report and source panel use two columns;
narrower layouts stack them in page order. The six operator screens remain in
the collapsed technical console, and the five-stage rail remains a Live
Backend control.

Open the corresponding deterministic routes in Static Demo:

```text
/?showcase=overview
/?showcase=evidence
/?showcase=blocked
```

These are synthetic/demo fixtures, not live provider research recordings or
production data. The [manifest](assets/console-showcase/manifest.json) records
the source implementation commit/tree, route/state, `zh-CN` locale,
1600x1000 viewport, disclosure, and SHA-256 values. Its tracked frontend
capture fingerprint canonicalizes only the release `version` fields in
`package.json` and `package-lock.json`; dependency, build configuration, source,
and public-asset changes still require a new capture fingerprint and provenance.

## Demo Video Boundary

Public demo videos for Decision Research Agent are deterministic loopback contract demos.
They show the console and canonical result contract in a repeatable local
demonstration path. They are not live provider research recordings, not public
production service recordings, and not evidence of an online multi-user
deployment.

## Prerequisites

- Node.js `22.22.2` or later within `22.x`, or `24.15.0` or later within `24.x`
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
send a network request to the Decision Research Agent backend. Browse the
overview, evidence, and blocked states at the deterministic routes above; no
API key, backend, provider, or credentials are needed.

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
to open the Vite development server. CORS and Origin checks are not
authentication.

### 2. Start the backend on loopback

From the repository root with the Python environment active:

```bash
python api/server.py
```

The source launcher uses `127.0.0.1`, reload disabled, and Uvicorn
warning-level logging. In credential-free mode, the direct peer and literal
Host must both be loopback.

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
3. Keep the default generic mode or explicitly select Structured evidence
   research, then enter one nonblank research question in the editable multiline field. The
   Console accepts at most 4096 UTF-8 bytes and shows the current byte count.
4. Select **运行并获取结果 / Run and fetch result**.
5. Inspect the returned `run_id`, terminal state, and canonical artifact.

The client waits for at most ten minutes. A client timeout stops browser
polling but does not cancel the server-side ResearchRun. Switching back to
Static Demo prevents stale in-flight responses from replacing the static view.

## Run Data And Recovery Contract

Static Demo and Live Backend run data are mutually exclusive. Switching modes
clears the previous mode's run projection, and the inactive mode's run-specific
data is never rendered. Live Backend shows explicit not-observed,
not-applicable, unsupported, and observed-empty states instead of substituting
Static Demo values.

Idempotency-Key is header-only and browser-session scoped. Each new-run action
keeps one temporary keyed request in memory. The question is sent exactly as
entered; the Console does not trim, normalize, translate, case-fold, or rewrite
it. If the create acknowledgement is ambiguous, use **重试同一请求 / Retry
same request** to resend the same key and byte-equivalent request, including
the exact submitted question, selected profile, and nested scope, or explicitly
discard it. Do not start a
replacement request while reconciliation is pending. A page refresh discards
the in-memory reconciliation capability; the draft is browser-session-only and
the console does not claim durable browser intent.

Once `run_id` is known, the separate **已知 run_id / Known run_id** field can
reattach the current page after refresh. The health-gated **观察已知运行 /
Observe known run** action accepts the exact syntax
`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (128 characters maximum), is
browser-session-only, and uses GET only; it does not create a new run. A
retained known `run_id` can be re-entered after a page refresh. Use **仅 GET
恢复观察 / Resume observation (GET only)** after an interrupted status or
result observation. The canonical Markdown artifact comes only from
/api/runs/{run_id}/result; structured findings come from the separate canonical
/api/runs/{run_id}/findings reader. A terminal non-ready state is an observed run
outcome, not a connection failure, and the console does not request a result
for that state. The console does not add run list/history or browser
persistence and does not reconstruct an ambiguous POST after refresh.

Failure-cause availability is not inferred:

- failure-cause property absent means unsupported;
- failure-cause null means not applicable;
- failure-cause not_observed means no cause was observed; and
- failure-cause observed renders only its bounded public projection.

This path remains loopback-only, does not accept or store API credentials, and
does not own review or verification authority. It does not prove durable
browser intent. It does not prove production deployment. It does not prove
exactly-once execution. It does not prove live-provider quality, public access,
or service-side business correctness.

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

WebSocket credentials are header-only, and query credentials are rejected.
The current console does not use WebSocket, store `X-API-Key`, or bypass the
runtime access policy.

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
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_demo_console_contracts.py -q
```
