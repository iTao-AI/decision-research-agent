# Agent Research Operations Console Design

## Purpose

The Agent Research Operations Console is the React demonstration surface for
Decision Research Agent. It is built for stable technical demos of run-scoped
execution, EvidenceLedger authority, human review, evidence verification, and
canonical result delivery.

It is not a chatbot, public research product, login surface, RBAC surface,
multi-tenant console, backend state machine, or result authority.

## Product Positioning

- Agent-first: upper-layer agents, the Tool Client, automation, or REST callers
  invoke DRA.
- Evidence-governed: findings and claims point to run-scoped evidence
  references.
- Human-governed: review, verification, publication, and delivery are
  service-owned states.
- Operations-capable, not authoritative: the UI presents static demo fixtures
  by default and can create a ResearchRun, observe its lifecycle, and retrieve
  the canonical result in Live Backend mode. It does not create business truth
  or own service state.

## Information Architecture

Static Demo opens as a readable decision brief, not a workflow navigator. Its
compact header names Decision Research Agent and describes the product as
turning research questions into reviewable reports. The report presents the
question and delivery state, the recommendation, a comparison of options, and
supporting findings. A related-source panel shows readable source names,
source status, supported findings, matching excerpts, and full source text.
Internal Evidence and claim IDs stay in technical details.

Three report shortcuts navigate to the recommendation and comparison, the
currently selected source details, and the full report. The full-report
shortcut opens the existing reader disclosure before moving focus. Selecting a
finding opens its linked source; the return action restores focus to that
finding. Repeating either action repeats the focus and scroll navigation.

The normal Static Demo opens on a concrete synthetic customer-support
question: `客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？`
The decision brief recommends an internal knowledge assistant, compares it
with automated refund handling, and exposes three local full-text source
fixtures. Its overview route opens on the recommendation; the evidence route
selects the second linked finding and source. The blocked route names the
unconfirmed policy access, states that no report was delivered, and gives the
next human confirmation. It has no report or download action and does not
retry automatically.

Live Backend retains the existing stage rail, technical screen navigation,
and report reader. It continues to render only observed service-owned state.

The technical disclosure retains the six operator screens:

1. Command Center
2. Run Lifecycle
3. Evidence Ledger
4. Review / Verification
5. Canonical Result
6. Architecture Explain Mode

The screen set is intentionally operational. Chat bubbles, prompt-first
layouts, and message input boxes are not part of the primary interaction model.
Runtime mode, internal IDs, framework details, and diagnostic traces remain
available in the secondary technical disclosure rather than competing with the
research path.

## Layout Rules

- The header is compact (about 80 px on desktop) and keeps the language toggle.
  Chinese copy may wrap naturally on narrow screens.
- Static Demo uses two columns from 1100 px upward. The source panel is about
  340–360 px wide; below that breakpoint, the report and source panel stack in
  document order.
- Static Demo does not show the five-stage rail. Its six operator screens stay
  inside the collapsed technical console disclosure. Live Backend retains its
  stage rail and existing controls.
- Put the full recommendation and the comparison entry in the first desktop
  viewport at 1440×900. On narrow screens, report shortcuts and source details
  must remain reachable by normal page scrolling.
- Use 15–16 px body text and a 26–30 px main question. Use cards for repeated
  records and inspection panels; keep report sections unframed.
- The source panel prioritizes readable names and source content. Review,
  gate, and authority summaries sit in a collapsed run-details disclosure.

## Visual System

The aesthetic is industrial, utilitarian, and evidence-control-room oriented.
It should feel closer to a runbook, audit console, and service dashboard than a
consumer AI assistant.

Color tokens:

| Token | Hex | Use |
|---|---|---|
| Canvas | `#F7F5EF` | Warm page background |
| Ink | `#15171A` | Primary text |
| Muted | `#6B7280` | Secondary text |
| Hairline | `#D8D2C4` | Borders |
| Panel | `#FFFDF8` | Panels and cards |
| Dark Panel | `#111827` | CLI and raw report view |
| Accent Blue | `#2563EB` | Selection and links |
| Evidence Cyan | `#0891B2` | Evidence refs |
| Review Amber | `#D97706` | Review required / unavailable |
| Verified Green | `#15803D` | Verified / ready |
| Blocked Red | `#B91C1C` | Failed / blocked |

Colors represent state, not decoration.

## Typography

- UI text: Geist or IBM Plex Sans when available, with system sans fallbacks.
- Chinese fallback: `PingFang SC`, `Noto Sans SC`, `Microsoft YaHei`,
  `sans-serif`.
- Code, IDs, state codes, artifact names, and command snippets:
  `JetBrains Mono`, `SFMono-Regular`, `Consolas`, `monospace`.
- Do not set the entire app in monospace.
- Keep stable technical IDs in the technical console and run-details
  disclosures; do not place internal IDs in the reader-facing source list.

## Components

- `RunStatusPill`: stable state code and semantic color.
- `RunSpine`: lifecycle sequence from creation to delivery.
- `EvidenceRefChip`: evidence reference treatment; clickable drill-down can be
  added only if it consumes an existing API contract.
- `AuthorityBadge`: distinguishes Application DB, LangGraph checkpoint,
  LangSmith diagnostics, and canonical result endpoint authority.
- `BoundaryCallout`: states what the demo console does not do.
- `ResultReader`: one report-first reader for Static Demo and observed Live
  Backend results, with safe formatted Markdown, opt-in raw text, and exact
  UTF-8 download.
- `EvidenceSourcePanel`: keeps local fixture source details and claim excerpts
  linked in Static Demo, while Live Backend renders only observed source fields
  and safe HTTP(S) links.
- `CommandSnippet`: shows the CLI golden path:

```bash
python tools/decision_research_agent_tool.py run \
  --query "Compare the evidence behind the proposed decision" \
  --wait \
  --result
```

- `InspectorPanel`: persistent right-side explanation area.

## I18n Rules

- Default language is Simplified Chinese.
- The top bar provides `中文 / English`.
- API paths, status codes, artifact names, CLI flags, evidence IDs, and
  framework names remain English.
- Copy must stay public-neutral. It should not mention private job-search
  motivation or local Career paths.

## Data Rules

- Static Demo mode uses local demo data only.
- Showcase routes `/?showcase=overview`, `/?showcase=evidence`, and
  `/?showcase=blocked` select deterministic presentation fixtures only; they do
  not add backend or API states.
- The normal fixture is a synthetic refund-automation case with three local
  full-text sources, exact claim-to-excerpt references, and a report hash
  validated from the displayed UTF-8 bytes.
- The blocked fixture keeps the same case question and source boundary while
  marking policy access unconfirmed. It stays at `review_required` and
  `not_delivered`; it never fabricates a canonical result or download.
- Static source text is labeled as local fixture material. Live source details
  render only observed identity, verification, fingerprint, citation, and safe
  HTTP(S) links; the UI does not infer excerpts or claim links from report text.
- Live Backend mode may call `/health`, `POST /api/runs`,
  `/api/runs/{run_id}`, and `/api/runs/{run_id}/result`.
- Live Backend accepts one bounded user-authored generic research question. The
  question must be nonblank and no more than 4096 UTF-8 bytes; this is a
  browser consumer bound, not a backend schema change.
- Live Backend is local-only in the current slice. It uses one explicit CORS
  origin and a loopback-bound backend with `API_SECRET` unset because the
  console does not accept or store API credentials.
- Telemetry, token usage, and WebSocket endpoints are not part of the current
  UI flow.
- `GET /api/runs/{run_id}/result` remains the canonical result contract.
- A retained known `run_id` can be re-entered after a page refresh through the
  health-gated GET-only observation control. Its exact syntax is
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (128 characters maximum).
- UI fixtures must not imply that review approval verifies Evidence.
- `cited` and `verified` remain separate concepts.

## Mode And Live Authority Contract

Static Demo and Live Backend run data are mutually exclusive. The selected
mode supplies one complete console projection, and the inactive mode's
run-specific data is never rendered. Static fixtures cannot fill gaps in a
Live projection; missing, not-applicable, unsupported, and observed-empty
values remain explicit.

Live Backend accepts one bounded user-authored generic research question. The
initial example is editable, but the submitted question must be nonblank and
at most 4096 UTF-8 bytes. The Console sends the string exactly as entered,
including surrounding spaces and line breaks; it does not trim, normalize,
translate, case-fold, or rewrite it. The draft and its temporary create intent
are browser-session-only. Service-owned status and result authority remain
outside the browser.

Idempotency-Key is header-only and browser-session scoped. A new-run action
creates one in-memory intent before transport begins. If its create response is
ambiguous, the operator may retry the same key and byte-equivalent request,
including the exact submitted question, or discard that pending intent. The key
is never rendered, placed in the URL or request body, or stored in browser
persistence. A page refresh discards the in-memory reconciliation capability.

After a valid acknowledgement exposes `run_id`, known run observation resumes
with GET only. Status and result recovery do not create a replacement run. The
canonical artifact comes only from /api/runs/{run_id}/result. A terminal
non-ready state is an observed run outcome, not a connection failure, and does
not trigger a result request.

A retained known `run_id` can be re-entered after a page refresh in the separate
Live Backend control. This health-gated GET-only observation uses the exact
syntax `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`; it does not add run list/history or
browser persistence. It does not reconstruct an ambiguous POST after refresh.
The input is browser-session-only, and a corrected identity is always an
explicit operator choice rather than auto-discovery or automatic replacement.

The optional additive failure-cause field preserves four availability states:

- failure-cause property absent means unsupported;
- failure-cause null means not applicable;
- failure-cause not_observed means no cause was observed; and
- failure-cause observed renders only its bounded public projection.

Live Backend remains loopback-only and does not accept or store API
credentials. The console does not own review or verification authority and
does not prove durable browser intent, production deployment, exactly-once
execution, or live-provider quality. It consumes bounded service contracts and
does not become a business authority. The bounded Live Backend research
question input is included in the released `v0.1.9`; stable `v0.1.8` remains
unchanged as a historical release.

## Explicit Non-Goals

- No backend API changes.
- No database changes.
- No feature flags.
- No login, RBAC, multi-tenancy, public online research runner, or PDF export.
- No frontend-defined business authority.
