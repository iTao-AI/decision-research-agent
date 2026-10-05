# Multi-question structured research console

Status: approved implementation brief; local delivery only.
Starting point: remote main `db6bb55d24014636b4281719a258fd6b1be020c0`.
Delivery owner: the current repository owner, including in-scope implementation,
integration and final local acceptance.

## Outcome

The existing Live Backend structured research creation path accepts 1–5
explicit questions in a compact scope editor. Users can edit, add and remove
questions, then submit one complete scope to the existing `POST /api/runs`.
The existing findings reader presents the service's accepted questions,
candidate/unresolved dispositions, source references and model-reported
contradictions. Generic research remains the default; Static Demo remains an
explicit synthetic presentation.

## Request and draft behavior

- Default structured scope remains one `q1`. IDs are generated once when a
  draft row is added; editing or removing other rows never renumbers them.
- Question count is 1–5. IDs use the existing ASCII letter plus up to 63 ASCII
  letters/digits/underscores/hyphens contract; duplicate IDs fail before HTTP.
- Every question has nonblank text of at most 4096 Unicode code points.
- The first current question supplies the exact `query`, preserving the
  existing console bound of 4096 UTF-8 bytes. Text is not trimmed, translated
  or normalized by the browser; the server owns accepted scope normalization.
- Generic submission uses only that query and an empty scope. Structured
  submission sends the complete ordered question array, including stable IDs.
- A create intent copies and deeply freezes the entire payload before HTTP.
  A lost-response retry uses the original key and byte-equivalent payload,
  independent of subsequent draft references. Same-key same-scope replay and
  different-scope conflict remain server decisions.
- Editing/add/remove is disabled during creation, observation and pending
  reconciliation. Discard, profile/base/mode changes and GET-only known-run
  recovery preserve the existing lifecycle and authority boundaries.

## Presentation and accessibility

The compact editor retains a single-question default, associated labels,
validation feedback and visible keyboard focus. Add focuses the new question;
remove focuses a surviving question. Removal cannot empty the scope; addition
cannot exceed five. Chinese and English labels describe the same behavior.
Narrow screens wrap without document overflow. Stable technical question IDs
are retained in requests rather than made a primary user-facing control.

The findings reader uses observed report dispositions, not form drafts or
inferred truth. Candidate/source-bound coverage does not mean verified.
Unresolved reasons remain attached to their accepted questions. Contradictions
remain report-level model statements because the existing API does not assign
them to question IDs. References and snippet inspection use the existing
same-run parser and safe-link/text behavior.

## Acceptance

1. One and five questions submit exact complete immutable scopes.
2. Zero/six questions, blank text, duplicate/invalid IDs and oversize text fail
   before request creation; Unicode limits use the existing units.
3. Editing/deleting/re-adding preserves surviving IDs and never reuses a
   removed ID in that browser draft. Reordering supplied arrays keeps IDs.
4. Lost-response reconciliation keeps the complete original payload/key;
   the existing API accepts replay and rejects a changed full scope.
5. Multi-question observed reports show dispositions, unresolved reasons,
   contradictions and exact same-run references. Single-question and generic
   flows, attached-run identity and Static Demo do not regress.
6. Frontend tests/lint/build, focused API consumer checks and actual
   desktop/narrow/keyboard browser observations pass with declared synthetic
   native fixtures. Browser results do not prove autonomous research quality.

## Scope and authorization

Local implementation, exact-lock isolated dependency setup, verification,
documentation, one independent review and semantic commits are authorized.
No new dependency/lock changes, extra tool installation, real/paid provider,
push, PR, merge, tag, Release or deployment is included. No backend scope,
Evidence, runtime, review/verification authority, browser review writes,
automatic research, history management or next-stage work is included.

The existing API contract and framework/runtime implementation are reused;
this change adds a consumer input path, not a new server contract or authority.
