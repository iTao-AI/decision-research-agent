# Agent Research Operations Console Design

The React research workspace lets users submit a question to a local Decision
Research Agent service, observe a run, and read its canonical report with
linked evidence. The application database remains authoritative for runs,
Evidence, and review. The UI consumes service-owned status and result authority
through the existing [API contract](docs/reference/api-contract.md). The
[console guide](docs/demo-console.md) covers local setup and operator recovery.

## Routes and interaction

| Entry | Surface |
| --- | --- |
| `/` | Blank research draft, with Evidence research selected. The workspace checks local service identity on entry. Drafting works while the service is offline. |
| Find existing research | A separate, health-gated run ID dialog opens a GET-only reading context. Returning to the workspace restores the draft or current run view. |
| Settings | Select Simplified Chinese (the initial language) or English and edit the loopback endpoint. Saving a different endpoint clears the previous run views and rechecks the service. The address is locked during creation, reconciliation, and polling. |
| Example report | Opens `/?showcase=overview` in a separate tab. `/?showcase=evidence` and `/?showcase=blocked` are additional offline fixture entry points. |

A sticky header and status strip keep the current phase and the relevant action
in reach. Run events come from the create receipt and status responses. Run
details retain the copyable identifier, observed execution and delivery fields,
and bounded diagnostics. Architecture and CLI instructions are secondary.

The workspace uses a quiet document layout with a gray-green canvas
(`#F5F6F2`), ink (`#1E302C`), and pine-green action color (`#18584A`).
System sans fonts support UI and body text, with a system serif stack for
headings. The layout puts the question and start action in the first desktop
and mobile viewports. On wide screens an opened source can sit beside the
report. On narrow screens it stays in the report flow. Dialogs support
keyboard use, Escape, and focus restoration. The status strip announces phase
changes, and report, question, and source navigation moves focus to the target.

## Draft and run lifecycle

- Evidence research explicitly submits `generic-evidence-report`, with one to
  five ordered questions. A blank draft begins with `q1`. Add and remove
  preserve surviving question IDs. Each structured question allows up to
  4096 Unicode code points, and the first question supplies the query with a
  separate 4096 UTF-8 bytes limit. General research accepts one bounded
  user-authored research question. CLI and backend defaults follow their
  existing contracts.
- The browser sends exact input. It does not trim, normalize, translate,
  case-fold, or rewrite it. The structured single-question scope is
  `{questions: [{question_id: "q1", text: query}]}`. The example fill is an
  explicit draft action. Submission is an explicit create action.
- Idempotency-Key is header-only and browser-session scoped. A create stores
  one temporary frozen intent. With ambiguous acknowledgement, retry uses the
  same key and byte-equivalent request, including the exact submitted question,
  selected profile, and deeply frozen scope. Discarding that intent releases
  it locally. A page refresh discards the in-memory reconciliation capability.
  Drafts and intents are browser-session-only.
- After acknowledgement, known run observation resumes with GET only. Known run
  lookup accepts `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (128 characters
  maximum). Status and report read interruptions have distinct recovery
  messages. Terminal execution failure uses the observed service reason where
  available and can show retained evidence. A terminal non-ready state is an
  observed run outcome, not a connection failure. Rechecking the delivery
  disposition is a read.
- When execution is completed (including fallback), delivery is ready, and
  the required reads succeed, the report appears inline. Attached runs select
  the reader from the observed profile. General research uses safe Markdown.
  Evidence research uses the canonical findings projection in accepted
  question order, with candidate findings, unresolved reasons, and global
  limitations and model-reported contradictions. A failed findings read
  withholds both reader presentations. The canonical Markdown bytes are
  available in a raw disclosure and exact UTF-8 download after delivery.
  The canonical Markdown artifact comes only from /api/runs/{run_id}/result;
  structured findings come from the separate canonical
  /api/runs/{run_id}/findings reader.
- An evidence citation opens the bound excerpt and permits inspection of the
  full persisted snippet. The UI returns focus to the citation or excerpt
  control when closing the relevant view. Safe HTTP(S) source links are
  actionable. A binding identifies source material. Evidence verification
  remains service-owned, with truth and entailment outside this browser check.
- An accepted report with unresolved questions can prepare a separately
  editable draft. The original run and unresolved reasons remain local
  references. Preparation and cancellation preserve the report and ordinary
  draft. Explicit submission creates a fresh intent and independent run with
  the edited questions.

## Showcase and authority boundaries

Static Demo and Live Backend run data are mutually exclusive. The inactive
mode's run-specific data is never rendered. Showcase views load bundled
fixtures without backend calls. Their synthetic support case compares an
internal knowledge assistant with automated refunds using three local
full-text sources. Overview opens on the recommendation, evidence opens on
the second linked finding, and blocked shows unconfirmed policy access and
`review_required / not_delivered`. Blocked exposes no report or download.
The six technical showcase screens remain in the collapsible disclosure.

The local workspace consumes `/health`, `POST /api/runs`,
`GET /api/runs/{run_id}`, and ready result and findings endpoints. The
console uses one explicit CORS origin and a loopback backend with
`API_SECRET` unset. The Tool Client handles authenticated environments. Telemetry, token usage,
and WebSocket endpoints are outside the workspace flow. The console scope
covers local research and offline examples. Public hosting, multi-tenancy,
account management and PDF export are outside this scope.
Review, publication, delivery and verification decisions remain with the
service. Approval can permit delivery. Verification is a separate evidence
state. See the [approved workspace design and acceptance criteria](docs/superpowers/specs/2026-11-20-research-workspace.md)
and the [historical showcase captures](docs/demo-console.md#showcase-frames).
