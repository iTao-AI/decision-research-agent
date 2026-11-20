# Agent Research Operations Console

Open the React console at `/` to draft a research question, start a run
against a local service, and read the delivered report in the same workspace.
The initial form is blank and selects **证据研究 / Evidence research**
(`generic-evidence-report@1`). **通用研究 / General research** is available
for a single question. **填入示例 / Use an example** fills the empty draft
for editing. Only **开始研究 / Start research** submits it.

**查看已有研究 / Find existing research** opens a separate read-only view
by run ID. **设置 / Settings** holds the local backend address and interface
language. **示例报告 / Example report** opens a deterministic, offline Static
Demo in a separate tab. The service owns the run lifecycle, Evidence, review,
and delivery. The draft and temporary create intent live in browser memory.
The bounded Live Backend question input first shipped in `v0.1.9`;
stable `v0.1.8` remains unchanged as a historical release.

For a provider-free native backend and four declared cases, follow the
[research evidence delivery walkthrough](operations/research-evidence-delivery.md).
Its HTTP proof remains separate from actual browser observations and paid runs.

## Structured Live Reader

With the local service connected, keep **证据研究 / Evidence research**
selected. Enter 1–5 questions, using **新增问题 / Add question** to
extend the scope. The draft starts with one `q1`. Edits and removals retain
the IDs of surviving rows, and newly added rows receive new IDs. Every row
must be nonblank and at most 4096 Unicode code points. The first row supplies
the exact query and also has a 4096 UTF-8 byte limit.

Select **开始研究 / Start research** to submit the complete ordered scope.
The browser freezes every question ID and text before HTTP. The draft gives
way to the run view during creation, observation, and reconciliation.
The single-question request remains
`{questions: [{question_id: "q1", text: query}]}`. The console does not invent
questions for attached runs. Accepted question text and candidate/unresolved
dispositions shown in the report are service-owned and may reflect server
scope normalization. Editing a new draft does not change an observed report.

Only an observed ready run of the structured profile triggers `/findings`.
Expand **问题目录 / Question directory** to see the accepted questions in report
order with their original candidate/unresolved dispositions. Use Tab
to reach an entry and Enter or Space to scroll to and focus that question's
reading region. Repeating a selection repeats the navigation. Every region
stays visible and contains the full accepted question plus all of its existing
candidate findings and bound sources, or its existing unresolved reason.
The directory's two-line text preview does not truncate the full question.
It never reads the editable scope draft to fill report facts.

Select a finding's citation to open its bound excerpt and source. Use
**查看完整持久化片段 / Inspect full persisted snippet** to inspect the longer
stored snippet. The source panel sits beside the report where space permits
and in the reading flow on narrower screens. Return from the snippet to its
excerpt, then from the source to the triggering citation. Snippets are
service-persisted material. Candidate, source, and contradiction content
renders as text, with actionable source links limited to safe HTTP(S) URLs.

Unresolved reasons stay within their question regions. Limitations and
model-reported contradictions remain globally visible after the questions;
the UI does not assign a report-level contradiction to a particular question.
Source binding locates material in an observed source snippet;
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
not answer accuracy. In particular, an all-unresolved zero-findings run remains
blocked as `empty_research_output`, with no reader or download; the console
does not invent missing question reasons or deliver a substitute report.
A findings read failure withholds both reader presentations and shows a
bounded client error. **恢复查看 / Resume viewing** retries observation of
the same run. Changing the backend URL clears both run views and invalidates
old responses. Ambiguous create retry preserves the original query, profile,
scope, and key.

The tracked Static Demo screenshots below document the historical synthetic
showcase. They provide no browser evidence for the current workspace, the
structured live path, or live-provider research quality.

## Prepare A New Research From Unresolved Questions

Read an accepted `generic-evidence-report@1` with unresolved questions. In each
unresolved question region, use **选择未解决问题 / Select unresolved question**,
then **准备新研究草稿 / Prepare new research draft**. The independent **新研究草稿 /
New research draft** contains only the selected original question text. Edit it
into a more specific question, or add/remove questions within the same 1–5 and
length bounds. Preparation and editing do not send a create request or start
research. The ordinary editor's existing edits remain intact.

The source run and original unresolved reasons remain in **来源报告参照 / Source
report reference**. They are local reading references, not new Evidence,
verification, approval or backend lineage. The old structured report and its
canonical Markdown download remain readable until submission. Preparing again
shows **替换当前草稿 / Replace current draft** and **保留当前草稿 / Keep current draft**;
replacement happens only after that explicit choice. **取消新研究草稿 / Cancel new
research draft** restores focus to preparation, or a source checkbox if nothing
is selected, and leaves the ordinary editor and old report intact.

Only **确认并运行新研究 / Confirm and run new research** creates an independent
structured run through the normal create-intent endpoint. It uses a fresh key,
caller thread and run with only the new query/profile/scope; it never replays
the source request or copies its findings, Evidence or review state. An attached
structured report can prepare this draft while the ordinary generic form stays
selected. The draft clearly states its own structured mode. A lost response
uses the existing exact-new-intent retry; known-run observation remains GET-only.
The source report can still be read later by its retained run ID.

Changing the endpoint, source run, or accepted artifact clears the local
follow-up draft and selection. Busy/recovery/error states lock editing
and confirmation; late responses cannot restore an expired draft. Invalid,
blocked, generic and rejected all-unresolved reports gain no continuation action.
With no unresolved questions, the action is absent.

Successful health rechecks unlock existing edits. Before a new create is
acknowledged, its input draft stays in browser memory and the previous reader
is hidden. A definite create rejection retains the inputs but keeps them locked
until health succeeds; the user can edit and explicitly create a fresh intent.
The input cache is not a new accepted report or Evidence. An ambiguous response
still requires the original frozen intent's exact retry or explicit discard.
Acknowledgement and context changes clear the old draft. If the source reader
is absent, cancellation returns focus to the existing-research control.

The draft is browser-session-only. Deterministic service fixtures and browser
observations demonstrate creation/persistence and interaction separately; they
do not prove autonomous research quality, source truth, entailment or a passed
human value gate. No model settings, backend workflow or lineage is added.

### Deterministic Local Acceptance Fixture

Verified on 2026-10-07, the fixture below exercises the real public service,
dispatch, finalizer and SQLite readers while scripting only the producer's
outcome and declared source material. It strips provider credentials and
rejects external transports. It does not execute the installed research graph
or establish autonomous research quality.

With the project's existing Python and frontend dependencies available, run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q \
  tests/integration/test_unresolved_research_draft.py

PYTHON_DOTENV_DISABLED=1 python tests/integration/test_unresolved_research_draft.py serve \
  --origin http://127.0.0.1:5179 --port 8019 --seconds 900 \
  --directory output/unresolved-research-draft/local-session
```

Use a fresh, task-owned ignored directory for each session. In another terminal
from `frontend/`, run `npm run dev -- --host 127.0.0.1 --port 5179 --strictPort`.
Open the workspace and save `http://127.0.0.1:8019` in Settings. Once connected,
open the source run ID printed by the fixture using Find existing research.
Its accepted report has one candidate question and two unresolved questions.

Check selection/preparation/editing/replacement/cancellation before submitting;
`requests.jsonl` must gain no create entry for those actions. Each explicit
submission must add one new create intent with an edited scope, new key/thread/run
and independently owned Evidence. Reread the original status/findings/result and
compare the canonical Markdown bytes against `source-package.json`. The server
stops after the bounded duration or Ctrl-C and writes `service-summary.json`;
retain only task-owned ignored receipts and stop the frontend when finished.
These observations establish service persistence and rendered interaction only.
For a declared HTTP rejection before service admission, add
`--reject-first-browser-create`. The first browser create returns a fixed 503,
creates no run, and preserves the input-recovery scenario; later creates follow
the normal service path. This fault injection is test-only and does not claim
that a rejected request produced a persisted run. The injected response must
traverse the existing CORS middleware; otherwise the browser observes an
ambiguous network failure and correctly requires exact-intent reconciliation.

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
the collapsed technical console.

Open the corresponding deterministic routes:

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
and public-asset changes still require a new capture fingerprint and provenance
to establish current-render parity. The retained PNGs and manifest remain
historical captures from the manifest's declared capture inputs.

```bash
git fetch --no-tags origin cdd7b07e427b30596f6434a82bfafc1624e3cba5
python scripts/console_showcase_contracts.py check --root . --allow-historical
```

The fetch obtains the manifest's exact original capture commit from the existing
repository remote. A fresh PR/default-branch checkout may not otherwise contain
this historical object; the backend CI explicitly fetches it before validation.
This makes the original source available without rewriting capture identity,
fingerprint or images. If the source cannot be obtained, historical mode still
requires current matching and fails on drift.

Explicit historical mode admits current input drift only when the declared
commit is reachable and its true tree, independently discovered historical
frontend path set, exact fingerprint and all PNG bytes/hash/dimensions/route/locale/
disclosure checks pass. It reports `current_capture_inputs_match` separately
from `provenance_verification`; historical success may have current match false.
Omitting `--allow-historical` retains strict current paths/fingerprint matching.
If the declared source is unreachable, current matching remains required even
with the flag. A new honest capture/manifest is required to assert current-render
parity after drift; neither this flag nor the separate
[structured Live browser receipt](evidence/research-evidence-delivery-reader-v1.md)
creates a new Static Demo capture.

<a id="demo-video-boundary"></a>

## Public Showcase And Demo Video Boundary

The linked public project showcase currently presents selected screenshots and
source/release links. Run Static Demo locally for interactive exploration.
Demonstration recordings, where retained as evidence, remain deterministic loopback contract demos.
They are not live provider research recordings, public production service
recordings, or evidence of an online multi-user deployment. The external page
does not establish current local-render parity or research quality.

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

Open `http://127.0.0.1:5173/?showcase=overview`, or use the evidence and
blocked routes listed above. These explicit routes require only the bundled
fixture. They send zero requests to the Decision Research Agent backend.

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

Open `http://127.0.0.1:5173/`. The workspace checks
`http://127.0.0.1:8000/health` on entry. Open **设置 / Settings** to change
the port, or use **重新连接 / Reconnect** after starting the backend.

1. Write a question. Keep **证据研究 / Evidence research** for citation
   reading and up to five questions, or switch to **通用研究 / General
   research** for a single question.
2. Once connected, select **开始研究 / Start research**. Keep the run ID
   from **运行详情 / Run details** if you want to reopen it later.
3. When **报告已就绪 / Report ready** appears, use **阅读报告 / Read report**
   to focus the inline report. Inspect linked sources when available, view
   the raw artifact, or use **下载 Markdown / Download Markdown** for the
   exact canonical UTF-8 bytes.

The client waits for at most ten minutes per observation. A client timeout
stops browser polling while the server-side ResearchRun keeps its own state.

## Run Data And Recovery Contract

The workspace uses observed service responses for state and report content.
Showcase fixtures are available only through their explicit routes.

Idempotency-Key is header-only and browser-session scoped. Each new-run action
keeps one temporary keyed request in memory. The question is sent exactly as
entered; the Console does not trim, normalize, translate, case-fold, or rewrite
it. If the create acknowledgement is ambiguous, use **重试同一请求 / Retry
same request** to resend the same key and byte-equivalent request, including
the exact submitted query, selected profile, and complete nested scope with
every stable question ID and text in order. **放弃待确认请求 / Discard pending
request** clears the pending intent. A page refresh discards
the in-memory reconciliation capability; the draft is browser-session-only and
the console does not claim durable browser intent.

Use **查看已有研究 / Find existing research**, then **打开研究 / Open
research**, to open a known ID. A retained known `run_id` can be re-entered
after a page refresh for health-gated GET-only observation. The dialog accepts
the exact syntax `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (128 characters maximum).
Lookup validation and GET requests stay in their own reading context.
**返回工作台 / Back to workspace** returns to the original draft or current
research. After starting a follow-up from an existing report, use
**继续查看已有研究 / Return to existing research** to return to the same
follow-up, including after the receipt or report arrives. To recover after a status or report read interruption, use
**恢复查看 / Resume viewing** for the same run. The console does not add run
list/history or browser persistence and does not reconstruct an ambiguous POST
after refresh.

A delivered run provides canonical Markdown through `/api/runs/{run_id}/result`.
A ready structured run provides its accepted findings through
`/api/runs/{run_id}/findings`. The workspace waits for both required reads
before exposing a structured report and download. Failed runs can expose
the observed failure reason and retained evidence in run details. A known
submitted question can seed a new editable draft after failure. Review,
blocked, and pending-delivery states offer **查看状态 / Check status**, a
read-only refresh. Explicit submission is required for every new run.

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

The backend has `API_SECRET` configured. Open an explicit showcase route or use the Tool Client. Do not weaken authentication on a backend reachable outside loopback.

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

The Python contract suite also owns presentation structure gates, including
`App.tsx <= 500` lines and direct presentation-module ownership. Run it for
frontend composition changes; the npm checks alone do not cover these gates.

For optional scripted browser smoke checks, use an already installed CLI and
a task-owned named session (`-s=your-task`). Verified on 2026-10-30 with
`playwright-cli` 0.1.20: navigation can return a `[Snapshot](...yml)` file link,
while `snapshot` can return fenced inline YAML. Accept either output before
reading element refs, and refresh the snapshot after a DOM change. Quote URLs
with query strings or pass them as argument arrays to avoid shell globbing.
Completion means checking overview/evidence/blocked, the report/download gates,
and the absence of Static Demo backend requests; a parsed snapshot alone is
not a successful smoke check.
