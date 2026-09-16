# Research brief reading and evidence inspection

Design and implementation plan, 2026-09-16. Copy this document to `docs/superpowers/plans/2026-09-16-research-brief-workspace.md` before implementation.

## Outcome

The primary console experience answers three questions immediately: what decision was researched, what the report says, and which material supports it. A visitor can inspect evidence and take away the exact report. The Live Backend path uses the same result reader for the actual canonical artifact, while operational details remain available on demand.

## Current implementation and scope

Baseline: `4dff0c47f67b295d228f07fd1e68c952a7669ba6`.

- `frontend/src/demoData.ts` currently pairs a workflow-comparison question with an unrelated recommendation about an interview demo. Its abbreviated fingerprints are illustrative strings, not verifiable artifact hashes.
- `presentation/showcaseWorkspace.tsx` leads with five state cards. `presentation/technicalScreens.tsx` places actual report content inside a technical `<pre>` panel.
- `ConsoleProjection.result` already carries the canonical artifact's exact content. Live Evidence contains source identity/URL, citation status, verification status and fingerprint, but no source excerpts or claim graph; `citedBy` is explicitly unsupported.
- The backend already owns delivery gating, review and canonical artifact bytes. Preserve those behaviors.

Change the frontend reading/inspection experience and its deterministic case fixture, tests and directly affected docs. No new backend endpoint, schema, provider, dependency, generic agent workflow or framework replacement is part of this phase.

## Primary layout and copy

Retain the existing warm background, readable sans-serif type and blue evidence accents. Replace the default five-card status overview with a document-led layout:

- Header: `把研究结论和依据放在一起` with a short explanation of research reports and inspectable sources. Show the selected mode clearly, once near the work surface.
- Main column: concrete research question, the report/decision brief, then supporting findings. The first desktop viewport contains an actual conclusion, not only readiness labels.
- Side column: source list and selected evidence detail. A source is useful because its content supports a claim; identifiers and fingerprints belong in a collapsed technical detail area.
- A compact secondary control exposes execution/review status and the existing six technical screens. Keep Live input and reconnect controls easy to find, without expanding every operator panel on initial load.
- Preserve the existing overview/evidence/blocked URLs or provide deterministic backward-compatible routing. At narrow widths, use a single reading column and an inline evidence section with focus handling instead of a cramped three-column layout.

Use ordinary Chinese such as `研究结论`, `查看依据`, `待确认`, `下载报告`, `运行详情`. API identifiers remain literal in technical details. Keep one short synthetic-example disclosure with the example; repeated authority/disclaimer paragraphs must not displace the content. Clearly disclose an unavailable result where that affects a user's action.

## One coherent deterministic case

Use a public-neutral synthetic customer-support pilot decision:

**Question:** `客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？`

Declare three short synthetic source documents as fixtures, with their full text inspectable locally:

1. `试点需求记录` — the first phase helps support staff locate policy and draft an answer; a staff member reviews the answer. No measured business improvement has been supplied.
2. `系统接入清单` — the pilot can read approved policy material and order information; no production refund-write integration has been approved or verified.
3. `退款处理规则` — a refund decision requires an authorized staff member; an uncertain policy or missing evidence is escalated.

The normal case concludes that the first pilot should be the internal assistant, with policy-linked draft answers and staff review. Compare both options using supported criteria: current integration availability, required human decision, and what the pilot can evaluate. State that savings and adoption remain to be measured; do not invent traffic, ROI, customer adoption or model accuracy.

Include three readable claim-to-source links: read access supports the bounded assistant; missing write integration prevents an automatic-refund commitment; refund policy preserves staff approval. Each displayed excerpt must be an exact substring of its fixture source. A claim references explicit evidence IDs; no decorative citation chips without a resolvable target.

For the blocked comparison, retain the same question/case but use a separately identified synthetic run in which access to the needed policy material remains unconfirmed. Show what must be clarified next. The result is not delivered and cannot be downloaded. Selecting the scenario is browsing fixed examples, not executing a backend run or changing business state.

Keep these fixtures clearly separate from Live Backend data. Provide complete deterministic hashes for the exact source/report bytes where a hash is displayed as such. A fixture completeness test must catch missing evidence IDs, mismatched excerpts and inconsistent report hashes. Do not call this an executed model benchmark, real customer trial or real-source proof.

## Actual result reading and export

Use one result reader for Static Demo and Live Backend. Render the existing `projection.result` only when it is observed. Keep content source and mode visible. Clear stale report content when a different run is selected or a new observation invalidates it; blocked/missing/error states never fall through to a static success report.

Without adding a Markdown dependency, provide a small safe reading view for common headings, paragraphs, lists and fenced literal text. Treat all source/report text as untrusted text; use escaped React nodes, never raw HTML. Unsupported Markdown remains readable verbatim, and a `原文` view always exposes the exact artifact. Do not implement a general Markdown engine. Plain text wrapped well is preferable to lossy or unsafe formatting.

`下载报告` downloads the exact UTF-8 artifact content as `.md`, with a sanitized deterministic filename and object-URL cleanup. It is a user-initiated local action, with no upload, new research run or provider call. Do not prepend translated text, headers or synthetic data to a Live artifact. Show service-reported metadata as such; only label a hash client-verified if verification actually ran.

Static case enrichment may supply claim text and source excerpts. Live mode must use only fields supplied by the existing contract. Where the backend does not expose excerpts or `citedBy`, present the real report and observed source list honestly rather than inferring a verified claim graph from prose. Safe HTTP(S) source links are explicit user actions; reject executable/local URL schemes and avoid automatic remote image or content fetches.

## Implementation sequence

1. Read live rules/status and affected frontend tests. Account for retained local doc corrections `403f50bd984bc4d680b62f875b43dfc902e6200f` and `3e702a5a22ecd92a493c9ae939bc0d7acf1b42ba`; integrate relevant verified corrections into this branch without modifying or deleting those worktrees. In particular, preserve correct v0.1.9 status and avoid an unset `$RUN_ID` in Quick Start.
2. Create the coherent synthetic case as a single typed source of truth. Add meaningful tests for references, excerpts and exact artifact bytes. Align normal and blocked projections with the case rather than scattering a second set of copy-only data.
3. Implement a reusable readable result surface and local download. Test untrusted text and URL handling, empty/blocked states, and exact export bytes.
4. Rework the default overview around the report and evidence inspection. Preserve Live create/get/result/reconnect behavior and operator detail access. Keep source inspection keyboard accessible with a clear return to the referring claim.
5. Adjust Chinese and English presentation using existing i18n patterns. Do not translate or alter actual Live report bytes. Retain the current safe result and observation distinctions.
6. Update README opening, `DESIGN.md` and `docs/demo-console.md` to describe the new reading flow and actual capability. Preserve useful API/architecture details below the product introduction. Update the small existing screenshot set from the real UI; avoid another exhaustive visual rewrite.

## Acceptance

- At 1440 px, the default first viewport contains the concrete question, an intelligible recommendation and a visible way to inspect supporting evidence. A user can answer “what is recommended and why?” without opening an operator screen.
- Each static claim resolves to its actual local fixture text. Switching normal/blocked preserves the case question, changes the distinct scenario/run appropriately, and never exposes a delivered report in the blocked state.
- A mocked Live canonical result with content different from the fixture appears in the same reader and downloads byte-for-byte. Missing or replaced Live results cannot retain a previous report. Evidence without an excerpt does not receive invented text.
- Existing UTF-8 question bound, create-response-loss idempotency, GET-only reconnect, unsafe result handling, mode isolation and retry tests continue to pass.
- Validate keyboard source inspection, 390 px reading, long report wrapping, HTML/script-like input, unsafe source URLs, and literal code examples. Opening the default fixture makes zero backend/provider requests.
- Run frontend tests, lint and build with existing dependencies. Run only relevant Python documentation checks if those files change; no paid provider proof is required for this frontend phase. Reuse an available environment and verify that imports/tests target this worktree.
- Retain current screenshots of overview, evidence inspection and blocked state, with no clipped controls or horizontal page overflow. Screenshots must show the actual implemented content.
- Deliver a clean local commit, exact test commands/results, changed-file summary and a short reproduction path. No remote publication, new dependency installation or other-worktree cleanup.
