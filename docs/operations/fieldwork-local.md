# Run Fieldwork locally

The Fieldwork workbench is a local single-operator workflow for the fictional
Northstar Equipment pilot. It starts at site investigation. The existing
research console remains at `/`. Run the normal DRA backend separately if
you want to submit a new general research task from that console.

## Start the credential-free replay

Install the repository's locked Python and frontend dependencies, then run
from the repository root. Use a new state directory for a fresh project.

```sh
npm --prefix frontend ci
npm --prefix frontend run build
PYTHON_DOTENV_DISABLED=1 python -m fieldwork.web --root output/fieldwork-demo
```

Open [Fieldwork](http://127.0.0.1:7195/fieldwork). This mode uses stored exact
readbacks for the three fictional PDFs shipped under `examples/fieldwork/`
and scripted suggestions. Each browser operation still goes through the
local service and durable project database.

### Three-minute walkthrough

1. **0:00–0:45** Review the initial recommendation and the frozen interview
   and pilot commitments. In **变更收件箱**, submit the PDF from
   `examples/fieldwork/A/` as new material.
2. **0:45–1:30** Analyze the submitted material. In **阶段评审**, compare the
   prior arrangement to the proposal. Open the demo decision's citation and
   confirm the quoted words and page. Confirm the proposed changes.
3. **1:30–2:15** Reload the workbench, open **交付成果** and download V2 JSON
   and Markdown. The workbench still shows **现场调查**.
4. **2:15–3:00** Submit the identically named PDF from `examples/fieldwork/B/`
   as a replacement. The next proposal distinguishes internal rehearsal from
   customer display. Review the previous evidence in the history. Use the C
   document to see an acknowledgement leave a concrete question for IT.

Before starting another workflow, use a fresh state directory or build on the
recorded history. Closing the page and restarting the service preserve state.

## Use a real MKE library

Use the independently installed MKE CLI compatible with the v1 catalog,
scoped search and exact evidence read contracts. Pass its executable path
on the server command line. The workbench chooses the project database.

```sh
python -m fieldwork.web --mode mke-replay --mke /path/to/mke --root output/fieldwork-mke
```

`mke-replay` uses real PDF intake, scoped search, bounded browse and exact
read, with scripted suggestions. A local text-layer PDF is kept under its
content digest. Reuse the same state directory for replaying a response that
may have been lost. The browser does not configure paths.

An explicit `--mode live` uses the configured `DEEPSEEK_API_KEY` and the
official `deepseek-flash` endpoint. The operator can pass `--env-file` for
their private service configuration. By default the service permits one
model request per process, with a 12,000-byte input cap and 1,600 output
tokens. It sends the verified passages and project context, with zero
external search or tools. Inspect the source provenance and semantic support
before accepting. Use isolated state for replay and live exercise runs.

## Build and register a confirmed HTML brief

Save the desired confirmed JSON version from **交付成果**. Review which
material is approved for sharing, then follow the
[decision-html skill](../../skills/decision-html/SKILL.md). For the fictional
demo, a local operator can use:

```sh
python skills/decision-html/scripts/render_brief.py confirmed-v2.json fieldwork-v2.html --fictional
python -m fieldwork.web --root output/fieldwork-demo --register-html 2 fieldwork-v2.html
```

The service verifies that the HTML identifies V2's snapshot and registers the HTML bytes and SHA-256. A registered version
can be opened or downloaded from the workbench. Old versions can be revisited.
Inspect the downloaded file offline and use the evidence disclosures to
check the selected excerpts.

## Local interface

The opt-in service binds to IPv4 loopback. It rejects cross-origin writes and
hosts other than loopback. It owns all storage paths and accepts an explicit
replacement ID, which belongs to the current version of that material.
Select a PDF with an extractable text layer on every page. A failed or
unsupported PDF leaves the previous confirmed plan and unaffected work intact.

All routes below are relative to `/api/fieldwork/projects/northstar`.

| Method and resource | Contract |
| --- | --- |
| `GET /` (project path with no suffix) | Project stage, current practice mode, confirmed plan, optional intake or proposal, material versions and registered HTML fingerprints |
| `POST /materials?title=&replace=` | Raw `application/pdf`, up to 8 MiB. Omit `replace` to add a new document. Retry the same bytes and replacement target if a receipt was lost. |
| `POST /analysis` | JSON `{material_id}`. Select the current material. The response contains the resulting proposal and its frozen evidence. |
| `POST /review` | JSON `{proposal_id, decision, feedback}`, with `accept` or `return`. Return requires feedback. Stale proposals receive HTTP 409. |
| `POST /progress` | JSON `{sample_prepared: true}`. Records the completed step and invalidates older, unconfirmed proposals. |
| `GET /history` and `GET /proposals/{id}` | Read the published revisions and past proposals, including their original quotations. |
| `GET /proposals/{id}/evidence/{id}/live` | Compare that frozen reference against an exact current read. Explicitly reports unavailable evidence, while preserving the frozen quotation. |
| `GET /exports/{version}.{format}` | Read a confirmed snapshot as JSON or Markdown, or serve the independently registered HTML. Add `?download=true` to download the HTML. |

Fieldwork errors use `detail.code` and `detail.message`. The analysis audit
lives in the local project database. Its inputs show the exact admitted passages,
their source and publication identity, page and UTF-8 byte offsets. Live results
also record the request fingerprint and the provider usage when available.
