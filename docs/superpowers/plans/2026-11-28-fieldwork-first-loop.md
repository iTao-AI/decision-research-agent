# DRA Fieldwork Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for this plan. Steps use checkbox syntax for tracking.

**Goal:** Deliver a restart-safe PDF-to-reviewed-decision journey at the Fieldwork site investigation stage.

**Architecture:** Keep the local opt-in Fieldwork web entry point alongside the existing console. Use a DRA SQLite ledger, an independently invoked MKE CLI, a bounded model adapter, and immutable confirmed snapshots for exports.

**Tech stack:** Python, SQLite, FastAPI, React, Vite, the existing project HTTP transport, and the MKE CLI.

**Spec:** `docs/superpowers/specs/2026-11-28-fieldwork-first-loop.md`

## Shared contracts

The initial project is `northstar`. Service calls are same-origin at `/api/fieldwork/projects/northstar`.
The server chooses all local paths. Maximum PDF bytes are 8 MiB. Document text remains data.
The Fieldwork service has no route to invoke arbitrary tools or update existing research evidence.
JSON keys use snake_case. The application chooses IDs, defaults, and error codes.

- A material is `{id,title,sha256,source_id,publication_id,revision,producer_run_id,active}`.
- An evidence item carries `{id,material_id,title,source_id,publication_id,revision,producer_run_id,consumer_run_id,page_start,page_end,text,sha256,byte_start,byte_end}`. Its `id` is the exact MKE evidence identity. Frozen item and model input use the same text.
- A proposal contains `headline`, `summary` and `items`. Each item contains `area` (`demo`, `live_access`, `interview`), `state` (`proceed`, `waiting`), `priority` (`high`, `normal`), `action`, `owner`, `reason`, `question` (empty when none), and `evidence_ids`. The service adds `id,status,basis_revision,material_id,evidence,mode,feedback`.
- Project view has `id,title,stage,revision,sample_prepared,mode,confirmed,proposal,materials,deliverables`. `confirmed` has `version,headline,summary,items,evidence`. `deliverables` lists `{version,sha256}` for registered HTML versions.

## Review focus

Wrong producer run or mixed Publication, malformed multibyte continuation, duplicate ingest after a crashed response, replacement racing confirmation, and unsafe HTML in an old or new export. Give each an executable regression at its ownership boundary.

### 1. Verified MKE adapter

- [ ] Add failing adapter tests for truncated, overlapping or mixed UTF-8 readback, scoped selection, and recovery from the catalog after the subprocess response was lost.
- [ ] Implement `fieldwork/mke.py`. Entry point `MkeEvidence(executable, project_dir)`. Expose `ingest(path, sha256) -> dict` and `select(material, query, consumer_run_id) -> list[dict]` with the shared shapes above. Material id/title can be set by the caller. Provide `reread(material, evidence_id, consumer_run_id) -> dict` for live exact reads. A producer uses the directory's fixed database and a filesystem lock. Return JSON-safe fields and a typed safe error. Source commands may accept only service-owned identities.
- [ ] Run adapter tests and compare with a real credential-free text-layer PDF. Review independently and commit.

### 2. Decision, state and HTTP boundary

- [ ] Add failing tests for stale/repeated review, interrupted intake, bad reference IDs, current state changing next action, return with feedback, and restart.
- [ ] Implement `fieldwork/store.py` and `fieldwork/web.py` for the DRA ledger, FastAPI router and opt-in loopback entry point. `GET /api/fieldwork/projects/northstar` returns the project view. `POST /materials?title=&replace=` accepts raw PDF bytes and returns the project view. `POST /analysis` accepts `{material_id}` and returns that view. `POST /review` accepts `{proposal_id,decision,feedback}` with decision `accept` or `return`. `POST /progress` accepts `{sample_prepared: true}`. `GET /proposals/{id}` returns historical items. `GET /proposals/{id}/evidence/{id}/live` compares the frozen item to MKE. Structured HTTP detail uses a stable code and user-safe message.
- [ ] Implement `fieldwork/analysis.py` with `analyze(project, evidence) -> dict` adapters for credential-free replay and a bounded opt-in real provider. Record the actual input, output, usage, and basis for contract and semantic review. Replay uses the same service entry point.
- [ ] Provide `GET /exports/{version}.{format}` with `json`, `md`, or registered `html` and `GET /history` with confirmed snapshot summaries and proposal IDs. Export version content comes from the immutable snapshot. Operator registration runs outside the browser and records bytes/digest by version.
- [ ] Test each state transition, authorization boundary and export. Review independently and commit.

### 3. Workbench and acceptance

- [ ] Add frontend tests for upload, judging/review, opening exact evidence and error/recovery states.
- [ ] Implement `frontend/src/fieldwork/` and the `/fieldwork` entry. Keep the console available at `/`. Reuse the approved visuals. Browser actions use the documented API and focusable controls. Serve the build from the local Fieldwork service for same-origin operation.
- [ ] Freeze the fictional PDFs and case assertions without embedding them in the real inference code. Provide the standalone `operator-skills/decision-html/SKILL.md` and use it to generate offline HTML with its snapshot Markdown/JSON. Validate download and sandbox behavior.
- [ ] Verify the real and replay paths at desktop and narrow widths. Run deterministic cases, project regression and frontend build. Include a verified README screen and a three-minute walkthrough. Review the integrated branch and record the exact verification and remaining limits.
