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

The first shell has six required screens:

1. Command Center
2. Run Lifecycle
3. Evidence Ledger
4. Review / Verification
5. Canonical Result
6. Architecture Explain Mode

The screen set is intentionally operational. Chat bubbles, prompt-first
layouts, and message input boxes are not part of the primary interaction model.

## Layout Rules

- Desktop-first, because the primary use case is a live technical demo.
- Three-column shell: left navigation, center run canvas, right inspector.
- The right inspector carries persistent authority notes, CLI golden path, and
  explicit UI boundaries.
- Mobile only needs to remain readable; it is not the primary experience.
- Cards are used only for repeated state records, metrics, and inspection
  panels. Page sections remain unframed inside the shell.

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
| Dark Panel | `#111827` | CLI and Markdown preview |
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
- Use tabular, stable-looking ID treatment for run, evidence, decision,
  publication, and artifact identifiers.

## Components

- `RunStatusPill`: stable state code and semantic color.
- `RunSpine`: lifecycle sequence from creation to delivery.
- `EvidenceRefChip`: evidence reference treatment; clickable drill-down can be
  added only if it consumes an existing API contract.
- `AuthorityBadge`: distinguishes Application DB, LangGraph checkpoint,
  LangSmith diagnostics, and canonical result endpoint authority.
- `BoundaryCallout`: states what the demo console does not do.
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
- Live Backend mode may call `/health`, `POST /api/runs`,
  `/api/runs/{run_id}`, and `/api/runs/{run_id}/result`.
- Live Backend is local-only in the current slice. It uses one explicit CORS
  origin and a loopback-bound backend with `API_SECRET` unset because the
  console does not accept or store API credentials.
- Telemetry, token usage, and WebSocket endpoints are not part of the current
  UI flow.
- `GET /api/runs/{run_id}/result` remains the canonical result contract.
- UI fixtures must not imply that review approval verifies Evidence.
- `cited` and `verified` remain separate concepts.

## Explicit Non-Goals

- No backend API changes.
- No database changes.
- No feature flags.
- No login, RBAC, multi-tenancy, public online research runner, or PDF export.
- No frontend-defined business authority.
