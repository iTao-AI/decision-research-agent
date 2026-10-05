# Research findings with inspectable evidence

`generic-evidence-report@1` is an implemented opt-in research profile. It reuses
the generic graph and produces source-bound candidate findings, accepted
questions, honest unresolved dispositions, limitations and model-reported
contradictions. The application binds exact excerpts to frozen same-run Evidence,
persists canonical JSON and deterministic Markdown in the fenced transaction,
and owns delivery readiness. Generic and strict-citation profiles retain their
existing Markdown behavior. Static Demo remains a separate synthetic snapshot.

A bound excerpt locates candidate material inside an observed stored snippet.
It does not prove truth, entailment, answer accuracy or human value. Evidence
remains unverified unless the separate human verification workflow records a
decision. Approval permits delivery and does not verify Evidence. Reported
contradictions remain model-reported.

## Read an existing run through the CLI

```bash
python tools/decision_research_agent_tool.py findings --run-id "$RUN_ID"
python tools/decision_research_agent_tool.py findings --run-id "$RUN_ID" --format markdown
mkdir -p output
python scripts/research_findings_consumer.py --run-id "$RUN_ID" \
  --output output/findings-receipt.json
```

Use the configured existing backend; `--base-url` and `--timeout` precede the
Tool Client subcommand. JSON preserves the report and adds actual public
Evidence/review states. Markdown returns the canonical stored bytes. The
independent stdlib consumer launches the real CLI subprocess, checks same-run
binding/hash/offset/coverage and publishes a small receipt without overwriting
an existing file. None of these reads creates or retries research, waits,
approves, verifies, fetches sources or calls a model.

The [CLI and consumer reference](../reference/research-findings-cli.md) provides
configuration, exact response/errors, limits and the actual separate-process
HTTP proof. Partial/unresolved and model-reported contradictory outcomes stay
visible. Completed/blocked runs return the existing error and no receipt.
Receipt checks are structural and cannot turn approval into Evidence verification.

## Provider-free native check

Use the existing Python 3.11 development environment with the locked project
and test dependencies. No provider credentials, Docker, installation or paid
call is needed. Run from the repository root:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  python scripts/research_evidence_delivery_proof.py check
```

The check creates a temporary application database, creates four real runs
through `POST /api/runs`, enters the installed DeepAgents graph using a
synthetic tool-calling model, calls the named `network_search` researcher and
`internet_search` source fixture, writes `/workspace/research-findings.json`
through native `write_file`, captures actual stream output, and runs
`ResearchExecutionService` plus server dispatch/fenced finalization. It then
reads persisted status, findings and Markdown through HTTP consumers. It does
not manually insert completed runs or call a stand-alone artifact builder as a
replacement for runtime execution.

The fixture and independently declared outcomes live in
`tests/fixtures/research-evidence-delivery/cases.json` and `expected.json`.
Observed counts and HTTP outcomes are compared with those declarations.

| Case | Requested / candidate-covered / unresolved | Delivery | Findings / Markdown HTTP | Binding failures |
| --- | --- | --- | --- | --- |
| complete | 1 / 1 / 0 | ready | 200 / 200 | 0 |
| partial | 2 / 1 / 1 | ready | 200 / 200 | 0 |
| contradictory | 1 / 1 / 0 | ready | 200 / 200 | 0 |
| insufficient-evidence | 1 / 0 / 1 | blocked | 409 / 409 | 0 |

All four executions complete. The contradictory case has two bound references
and one model-reported contradiction. The insufficient case honestly has no
finding, retains diagnostics, and cannot satisfy ready delivery. These counts
are structural coverage, not answer accuracy. Negative binding, invalid/absent
candidate, failed source/file tool, foreign references, stale fences and
artifact tampering are covered by the dedicated native/API/resolver regressions;
the four-case receipt does not claim to contain all those controls.

`check` writes only [native JSON](../evidence/research-evidence-delivery-v1.json)
and [native Markdown](../evidence/research-evidence-delivery-v1.md).
`--output-dir <directory>` redirects those two files. Repeated checks have stable
IDs assigned at actual run creation and byte-identical receipts, including the
actual own-byte hashes of the returned artifacts. They never post-normalize
artifact content or overwrite a separate UI observation receipt.

The CLI lazily imports runtime modules. It disables dotenv/tracing, prevents
provider initialization, replaces named source responses, denies database and
knowledge-base tool execution, and guards non-loopback DNS/socket transports.
There is no implicit real-provider or real-search fallback. These guards are
local proof infrastructure, not a new production sandbox or paid-budget layer.
The temporary database, workspaces and server resources are released on exit.

## Temporary API for actual reader observation

Start a bounded API using the explicit frontend Origin. For an already running
frontend at `http://127.0.0.1:5175`:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  python scripts/research_evidence_delivery_proof.py serve \
  --origin http://127.0.0.1:5175 --port 8876 --seconds 900
```

The API binds only `127.0.0.1`, accepts that one browser Origin, and runs for at
most 1800 seconds. Ctrl-C ends it earlier. It seeds the same four runs through
the native production path, prints their query/run IDs, then serves the actual
API. Unknown queries or other profiles are rejected before run creation. This
is a temporary fixture-only backend; it is not the ordinary live launcher.

In the console select **真实后端 / Live Backend**, set the API base to
`http://127.0.0.1:8876`, and check health. Attach these seeded runs for all four
cases; attachment uses the service-observed profile:

| Case | Run ID | Exact fixture query |
| --- | --- | --- |
| complete | `run_6bc0b688d0ac536eb2d612086d406868` | `research-evidence-proof:complete` |
| partial | `run_e4383ba9ee7353e89f6cc82563dd1470` | `research-evidence-proof:partial` |
| contradictory | `run_558e4f7a1d965b018568e8669dd6f2be` | `research-evidence-proof:contradictory` |
| insufficient-evidence | `run_d057d451d4785220aa34d5887f3e061d` | `research-evidence-proof:insufficient-evidence` |

To observe creation, explicitly select **结构化证据研究 / Structured evidence
research** and enter the complete, contradictory or insufficient fixture query.
The default form creates one `q1` whose text equals that query. The console
also supports 1–5 explicit questions, but this four-case proof launcher matches
the exact fixture query to its declared candidate. The partial fixture's two
accepted texts differ from that query, so attach its seeded run to reproduce
this existing case without changing the declaration. Additional created runs
have fresh deterministic creation identities within this server lifetime.

For ordinary structured creation, use **研究范围 / Research scope** to add,
remove and edit explicit questions. IDs remain stable after editing/removing
rows; the first current row supplies the exact query. All questions are
submitted in one immutable scope and ambiguous create retries reuse that
complete scope and the original key. The fixture launcher remains limited to
its declared synthetic cases and is not an arbitrary research backend.

Ready structured runs show candidate statements, all bound source URLs,
verbatim excerpts, full persisted snippets, unresolved questions, limitations,
and model-reported contradictions. **查看完整持久化片段 / Inspect full persisted
snippet** moves keyboard focus to the snippet; **返回引用片段 / Return to excerpt**
restores trigger focus. The original Markdown reader, raw text view and exact
UTF-8 download remain available. The insufficient run shows completed/blocked
and bounded diagnostics, with no deliverable findings or Markdown.

The [browser observation receipt](../evidence/research-evidence-delivery-reader-v1.md)
retains actual desktop/narrow geometry, keyboard inspection and screenshots.
The native receipt proves HTTP consumption only and never invents browser observations.
[Demo Console](../demo-console.md) describes reader and existing create/recovery
controls. Frontend parsing and focus tests supplement actual browser observation.

## Bounds and navigation

Evidence intake collapses whitespace and stores at most 1000 Unicode code
points per observed snippet. An exact excerpt must have one unique contiguous
occurrence within that stored snippet; arbitrary later passages of a full page
cannot bind. Offsets are zero-based, half-open Unicode code-point offsets, not
UTF-8 byte or JavaScript UTF-16 positions. Candidate JSON is at most 256 KiB;
canonical JSON and Markdown are each at most 1 MiB. Exceeding the package bound
blocks the whole package. Ready requires at least one source-bound candidate;
remaining questions may be explicitly unresolved.

- `agent/deepagents_harness.py::DeepAgentsHarness.execute` owns the server
  envelope and native graph entry; `agent/profile_middleware.py` owns one
  bounded completion correction.
- `agent/harness_contracts.py::capture_findings_candidate` and
  `agent/run_result.py::process_stream_chunk` capture native candidate/Evidence.
- `api/research_findings.py::build_research_findings_artifacts` resolves frozen
  references and renders deterministic canonical artifacts.
- `api/server.py::_run_dispatched_with_persistence` and
  `api/run_repository.py::finalize_run_transaction` own dispatch and finalization.
- `api/research_findings_service.py::resolve_run_findings` independently rechecks
  delivery, own-byte hashes and persisted Evidence; the original
  `api/run_result_service.py::resolve_run_result` supplies Markdown.
- `frontend/src/researchFindings.ts::parseResearchFindings`,
  `frontend/src/useLiveRun.ts` and `frontend/src/presentation/researchFindingsReader.tsx`
  validate selected projections, observe the profile and present inspectable text.
- `scripts/research_evidence_native_fixture.py` is the shared test/proof model,
  source fixture and harness builder; production never selects it.
- `tests/integration/test_research_evidence_delivery_proof.py`,
  `test_research_findings_native.py`, `test_research_findings_api.py` and
  `tests/unit/test_research_findings.py` expose the proof/control boundaries.

[Delivery ADR](../decisions/research-findings-delivery-authority.md),
[API Contract](../reference/api-contract.md), [Data Models](../reference/data-models.md)
and [Architecture](../architecture.md) remain the authority navigation.

## Separate proposed paid-provider gate

No paid call is performed or authorized by this local proof. The following is a
concrete proposal requiring separate authorization and satisfied prerequisites.
Use `generic-evidence-report@1`, the repository's configured baseline DeepSeek
`deepseek-v4-pro` primary and `deepseek-v4-flash` fallback. These names are verified
from `agent/llm.py` and `.env.example`; they are not a claim about current external
pricing, provider availability or newest models.

Proposed question set: run A accepts `q1: Which backend stores DeepAgents virtual
workspace files?` and `q2: Which LangGraph documentation explains checkpoint
persistence?`; run B accepts `q1: What limitations distinguish checkpoints from
application-owned research delivery authority?`. Use only the named
`network_search` / `internet_search` tool against `docs.langchain.com`,
`reference.langchain.com` and `github.com` under the `langchain-ai/deepagents` or
`langchain-ai/langgraph` repository paths. No database, knowledge-base, uploads
or arbitrary URL intake is part of this proposed observation.

Aggregate stop ceilings across both runs, retries and fallback attempts: **2
research runs, 24 model request attempts, 8 search request attempts, 100000 input
tokens, 12000 output tokens, 12 minutes elapsed time and US$5 total provider plus
search spend**, whichever is reached first. Failure to obtain trustworthy usage
or cost accounting stops further calls. Retrying beyond this plan needs new
authorization; a fallback attempt consumes the same aggregate limits.

Prerequisites: confirm provider/model availability and current model/search
prices from official sources; obtain explicit authorization for the exact
questions, source scope and ceilings; ensure required credentials are supplied
without logging them; and provide verified aggregate call/token/time/spend and
source-domain/path admission enforcement **before the paid run**. Existing
role-local call limits and generic search admission do not implement this
cross-run aggregate budget or the proposed generic domain/path allowlist.
Those enforcement prerequisites are unimplemented in this batch, so these
ceilings are a proposed authorization boundary, not a current runtime guarantee.

Retain separate public-neutral receipts with actual model/fallback identity,
run IDs, attempted calls, provider usage, elapsed time, prices/cost reconciliation,
observed source URLs and stored excerpts, native candidate/finalization results,
HTTP reader observations, and explicit failures. Keep credentials and raw private
request/exception material out of public artifacts. Human review must separately
inspect source truth, claim entailment and research usefulness. Provider
instruction adherence and that review cannot be inferred from these synthetic
fixtures or from structural ready status. Historical release and evidence
artifacts retain their original scope.
