# DRA Fieldwork first business loop

The local Fieldwork workbench starts at the site investigation stage of a fictional
industrial service pilot. It records a new or replacement PDF, proposes changes
from verified material and current project state, and preserves the operator's
decision and deliverables across restart. The Chinese interface follows the
approved prototype's navigation, judgement card, impact map, action list and
evidence views. The general research console remains available.

## Service and evidence

Run the opt-in Fieldwork service on loopback with a single explicit state root.
The browser sends a bounded text-layer PDF and a logical material key or title.
The server maps each project to an MKE database and records original bytes under
their SHA-256. Duplicate submission and a lost response can be retried without
re-ingesting resolved bytes. A replacement is admitted against its intended
predecessor. Each producer operation for one library is serialized. The MKE CLI
is a separate dependency with no library-path input from the browser or model.
Use ingest-run and catalog identity, scoped Source/Publication search, bounded
short-document browse, and complete evidence read. Verify MKE lineage, coverage,
byte offsets, terminal pagination and SHA-256 before the model sees any text.

Freeze every consumed excerpt with its publisher version, source, page, producer
run, consumer run, digest and byte offsets. Model references select from that
run's actual verified inputs. Material and project state revisions are part of
the decision's compare-and-set basis. Historical artifacts preserve the original
quotes after an MKE revision changes. A live reread must clearly show whether
that exact identity remains available. Public research evidence contracts,
RAGFlow, and existing API and CLI behavior continue alongside Fieldwork.

## Decision and delivery

A bounded analysis reads the stage, confirmed plan, completed steps, dependencies
and supplied excerpts. It produces a headline and proposals by affected area,
including priority, reason, responsible role, what can continue, what is blocked,
and which question must be asked of whom. A decision includes citations for each
affected area. Approval and return with feedback are server-owned, transactional
and idempotent. Changing material or project state supersedes an outstanding
proposal. Revisiting the original snapshot remains possible. Failure to ingest,
read, analyze or approve preserves previously valid decisions and independent
investigation work. A decision does not advance the stage on its own.

Download a confirmed version as JSON or Markdown. Build an interactive Chinese
HTML brief with the standalone decision-html skill using the selected confirmed
snapshot. Register its version and SHA-256 with a local operator command. Serve
the original HTML as sandboxed, offline, read-only output and keep older versions.
Show live, controlled, prototype and planned functionality as such.

## Acceptance

Frozen fictional case A permits a Wednesday customer demo using anonymized export
samples and leaves live access awaiting customer IT. The proposal must prioritize
preparation, leave live reading blocked, and continue interviews. Case B is a
same-name replacement that permits internal rehearsal only. Case C acknowledges
receipt without granting permission. A again with sample preparation already
recorded must propose a useful different next step. A stale review after B
becomes applicable must fail atomically and keep A's evidence readable. The cases
use the same service path and settings. Frozen readbacks and scripted responses
are marked accordingly. At least one A run uses the real MKE CLI and a real
model from normal browser input, reads source versions and exact quotations,
confirms, restarts and opens a registered offline deliverable. Inspect the actual
model inputs and evaluate the recommendations against them.

Provide a credential-free replay, desktop and narrow-screen checks, a real
README screenshot, and a short guided demo. This is a single-operator local
workflow using fictional records. Additional stages and wider adoption remain
at their observed levels of implementation and verification.
