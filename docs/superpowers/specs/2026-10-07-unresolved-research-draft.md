# Unresolved Questions To A New Research Draft

Approved scope: a frontend continuation of the existing structured report reader
and normal independent run creation. Starting point:
`fe4c9704149830d7fc1d620bf188000f65eacf00`. Implementation, local tests,
documentation and semantic commits are permitted; hosted delivery is a separate
decision. The implementation owner may decide details within these boundaries.

## User Flow

An accepted current `generic-evidence-report@1` with mixed candidate findings
and unresolved questions lets the user select unresolved questions. Preparing
a draft copies only their original question text into an independent editable
scope. The old unresolved reasons and source run remain a local reading
reference. Preparation, selection, editing and cancellation make no POST and
do not execute a model.

The user explicitly confirms creation through the existing `startNewRun`
intent/transport/observation path. This is ordinary structured research with a
new create intent, idempotency key, caller thread and independent run. The new
request contains only the existing query/profile/scope contract. It does not
use the retry/lineage endpoint or copy old findings, Evidence, verification,
approval or artifacts.

## Interaction And Context

- The draft is independent of the normal creation editor, preserving its
  existing edits. The current report and its canonical download remain readable
  until manual submission. Cancelling restores focus to the prepare action.
- Repeated preparation never overwrites an existing draft. A visible replace
  confirmation or keep-current action resolves it explicitly.
- The draft uses the source report's structured profile, including when an
  attached structured run was read with the ordinary generic form selected.
  Its confirm action supplies that explicit profile to the existing creation
  function; the ordinary form's selected profile does not change silently.
- Mode, endpoint, ordinary form profile, source run or accepted artifact
  changes unmount the local draft/selection context. Existing request-version
  fencing remains responsible for ignoring late HTTP responses.
- Checking, creating, polling, reconciliation, interrupted observation and
  known-run errors lock preparation, draft edits and submission according to
  the existing gates. Duplicate confirmation cannot create a second intent.
- Only unresolved questions from an accepted current response are selectable.
  Generic runs, invalid/blocked findings and rejected all-unresolved packages
  gain no accepted report or continuation action. With no unresolved questions,
  no continuation action is offered.

## Scope And Accessibility

Reuse the normal 1–5-question validator and editor: each question is nonblank
and at most 4096 Unicode code points; the first query also observes the existing
4096 UTF-8 byte limit. New question IDs are local fresh scope IDs. Original
question IDs remain reading references only. Users can add/remove/edit within
the same bounds. Separate editors have unique field/hint IDs and clear labels.

Chinese and English labels describe selection, the old report reference,
replacement, cancellation and explicit creation. Keyboard selection,
preparation, editing, add/remove, replacement and cancellation retain sensible
focus. At 1440px and 390px the draft fields/actions remain readable and usable.

## Acceptance And Evidence Boundary

React tests cover mixed reports, selection, edits, manual creation with a fresh
identity, repeated preparation/clicks, cancellation, context changes, stale
responses, recovery/error gates, invalid/blocked/no-unresolved reports and
unchanged normal creation/download. Run all frontend tests, lint and build.

A local deterministic fixture traverses the actual public create/status/
findings/result service and application persistence. Compare the new request
and persisted scope/identity and reread the original canonical result/Evidence
after creation. Scripted producer and UI observations must be labelled
separately; neither proves autonomous research quality, source truth or
entailment. Perform actual Chinese/English browser flows at 1440px and 390px,
including keyboard/error feedback and an observed absence of preparation POSTs.

No backend lineage/state-machine/model configuration, dependencies, provider
runs, Docker gate, paused quality candidate, release/tag/deployment or old
resource cleanup is included.
