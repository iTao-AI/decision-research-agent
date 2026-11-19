# Findings quality loop

This local benchmark checks the support for delivered findings and compares
one change to the coordinator's candidate-generation instruction. The
application still owns report delivery and Evidence state. Use the comparison
to decide whether a prompt change merits another evaluation.

Use the [evaluation standard](evaluation-standard.md) to design a case, choose
scoring denominators, and decide whether a paired change warrants adoption.

The [scoped inference report](scoped-inference/report.md) records a separate controlled Codex comparison of the default and the Ruff-specific instruction. Its public fixtures, retained candidates and frozen assessments replay through the native DRA binder without model calls.

## Replay and inspect

From the repository root, use Python 3.11. The frozen replay and intake use
the standard library. Native generation and transport tests use the
[repository lock](../../constraints.txt).

```sh
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  python scripts/findings_quality.py replay \
  --dataset benchmarks/findings-quality-v1 --output-dir output/findings-quality-v1
```

Open `report.md` to trace a task and arm to the question, statement, source,
version and exact excerpt. `report.json` preserves the complete frozen snippets
and code-point offsets, execution and scoring outcomes, and separate resource
counts for generation and judging. Use a fresh output directory for changed
inputs. Replaying identical inputs yields byte-identical files.

- The normal `binding-support-limit` control paraphrases the source's scope
  limit and receives the scripted verdict `supported`.
- `control-entailment-flip` cites the same genuine passage and inverts its
  meaning. The scripted verdict is `contradicted`. The earliest recorded
  deviation is deliberate construction of the false statement at generation.
  `delivery-owner-broken-reference` exercises the separate structural path.
- The scripted comparisons plan 12 arms, start 11 and deliver 10. Five pairs
  are comparable. Both pass once, only A passes once, only B passes twice and
  neither passes once. Two wrong refusals appear in reports with another
  valid finding. One report is absent and another arm never starts.
- The replay includes 18 synthetic claims and three dated historical
  pointers. Sixteen scripted verdicts complete, one Judge timeout stays
  unscored and one reference fails structural checks. Eight claims are
  available for optional human calibration, with zero human labels recorded.
  The result is `insufficient_evidence`.

The [corpus provenance](provenance.md) records source pins, licensing, the old
pilot rows and the development and holdout split. The two inverted controls
are development fixtures. Keep all variants of one family and source in a
single split. Retire a holdout after using it to tune the candidate. A dated
history entry with unavailable report bytes stays outside claim replay and
calibration.

## Register a suspect finding

Save the Tool Client's delivery JSON for an existing ready run. Use the
[findings reader](../../docs/reference/research-findings-cli.md) for capture
and independent structural checks. The following exercises intake on the
shipped synthetic delivery. For an observed local run use its saved delivery,
question and finding IDs, and the default `actual_local_run` origin.

```sh
python scripts/findings_quality.py intake \
  --delivery benchmarks/findings-quality-v1/demo-delivery.json \
  --question-id q1 --finding-id f1 --origin synthetic_control \
  --reason 'The statement reverses the cited limitation.' \
  --expected-behavior 'Describe what binding establishes and its limits.' \
  --output output/findings-quality-v1/suspect.json

python scripts/findings_quality.py replay \
  --dataset benchmarks/findings-quality-v1 \
  --case output/findings-quality-v1/suspect.json \
  --output-dir output/findings-quality-intake
```

Intake validates artifact bytes and same-run Evidence and retains all selected
references and accepted dispositions. Omit `--finding-id` for an unresolved
question. The same run, question, finding and report hash yield the same
case ID. An identical write is safe to repeat. Use another explicit path to
keep a different observation, and keep private input and output under an
ignored directory. A report revision receives a distinct case ID.

To attach selected local receipt observations, pass `--observation FILE`.
An observation includes `case_id`, `run_id`, a `source_calls` object and
`steps`. Use `{"state":"unobserved","count":null}` when source calls could
not be measured, or `{"state":"completed","count":0,"locator":"receipt#calls"}`
when a completed observation found zero calls. Each measured step names
`stage`, `result` (`normal` or `deviation`), `basis` and `locator`.
Valid stages in order are `source_retrieval`, `capture`,
`coordinator_transfer`, `generation`, `application_binding` and `evaluator`.
Use `primary_artifact_available: false` for a receipt without a delivered
case. The report identifies the earliest evidenced deviation and records
reviewer disagreement, missed answerable points and broken evidence as
triage signals.

## Score with a blind Judge

Use an LLM for the first pass on every structurally scorable claim. Give the
Judge only the question, statement, exact cited excerpts and source versions.
Apply the same citation-support rubric and Judge to both generation arms.
The standard blind sheet is the smaller sample for optional human calibration.
To export the full set of scorable claim inputs from a replay, run this from
the repository root and direct stdout to a fresh local file.

```sh
python - output/findings-quality-v1/report.json <<'PYTHON'
import sys
from pathlib import Path
from scripts.findings_quality_io import json_bytes, read_json
from scripts.findings_quality_replay import judge_input

inputs = {}
for case in read_json(Path(sys.argv[1]))["cases"]:
    identity = case.get("judge_input_sha256")
    if identity:
        inputs[identity] = {"review_id": identity, **judge_input(case)}
sys.stdout.buffer.write(json_bytes([inputs[key] for key in sorted(inputs)]))
PYTHON
```

Match retained model receipts by exact input digest and the Judge and rubric
identity when available. Reuse matching scores and send only uncovered
inputs to the Judge. Keep the model verdict, matched citation IDs and
rationale beside the original input digest in local output. Preserve
structural errors and missing predictions as separate outcomes.

When a disagreement could change the decision, check the fixed-version
source first. Use a runnable check or a second blinded Judge when either
can settle it. Record insufficient evidence if the technical question
remains unsettled. Ask the operator about tradeoffs that need their
judgment, such as acceptable costs or regressions in their use case.

On 2026-11-19 an independent Codex pass scored all eight frozen blind-sheet
claims. The eight verdicts agreed with the synthetic expectations. This
measures agreement on that fixture set. Keep that receipt in local output
under its model provenance. The human calibration denominator remains zero.
Evaluating a change in generation quality requires comparable observed outputs
from both A and B.

## Optionally calibrate against human reviews

Open only `blind-review.md` or `blind-review.json` before reviewing. Each
group contains the question, statement, every cited excerpt, source versions
and an opaque review ID. Save a JSON array with one row per completed human review.

```json
[
  {
    "review_id": "copy the opaque review ID from the sheet",
    "verdict": "supported",
    "reviewer": "reviewer name or ID",
    "review_date": "2026-11-19",
    "rationale": "My reason based on the cited material.",
    "blind": true
  }
]
```

Replay human labels with `--reviews FILE` and a fresh output directory.
The four-class calibration counts only independently human-reviewed rows
paired with completed model predictions. Report synthetic expectation
agreement and model-to-model agreement separately. The calibration report
shows unsupported claims passed as supported, supported claims failed,
unavailable predictions and uncovered classes.

## Rehearse and run the bounded comparison

The rehearsal uses the same DeepAgents coordinator graph, scoped tool
definitions, candidate file writer, frozen-ledger binder and application
readback. It freezes a short public passage from the SQLite guide and a local
research-tool history. A uses the normal coordinator envelope. B adds one
instruction to preserve the object, version and conditions and name missing
support. The scripted transport exercises both the generator and Judge
interfaces, including stopping and preserving partial output. A native
parity test independently compares A with an ordinary graph run on the same
fixed input.

```sh
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  python -m pytest -q tests/integration/test_findings_quality_capture.py \
  tests/integration/test_findings_quality_native.py tests/unit/test_findings_quality_transport.py
```

The [live proposal](budget-proposal.json) is ready for a separate authorization
decision. It binds the exact public inputs, candidate code, Judge rubric,
environment, model and request budget. Live setup snapshots the approved Skill
files before generation and rejects any extra discovered Skill file. Use `run-live` only after approval of
the exact proposal digest. The adapter reads `FINDINGS_QUALITY_OPENAI_API_KEY`
when the first request passes its preflight limits. Use an ignored local path
for output and supply the approved digest as `PROPOSAL_SHA256`.

```sh
python scripts/findings_quality.py run-live --allow-live \
  --approval "$PROPOSAL_SHA256" --output-dir output/findings-quality-live
python scripts/findings_quality.py replay --recorded-live output/findings-quality-live \
  --output-dir output/findings-quality-live-review
```

The capture journals candidate bytes before the native write and binder, then
stores validated delivery when available, allowlisted receipts and the
archived proposal. Replay rebinds the captured candidate against the frozen
same-run passage and compares the canonical artifact bytes. The native source
locator records start and end offsets in the model-facing tool message.
Decoding the JSON string fragment at that span recovers the exact passage,
including quotes and backslashes. Replaying the capture
makes zero requests and preserves stopped and unstarted rows. If native
parity cannot be established, the report identifies a standalone prompt
experiment. Inspect every regression and changed material assertion in the
comparison. Give every blind input in `generation-review-sheet.json` to
the same Judge for task coverage, including required points, justified
unresolved questions and overclaims. Import the assessments with
`--generation-reviews FILE`. Record the model identity in `reviewer` for a
model assessment and preserve its local receipt. Each row has the sheet's
`review_id`, `reviewer`, `review_date`, `blind: true`, a `claims` array with one
`{finding_id, covered_points, forbidden_matches, new_material}` per finding,
and an `unresolved` array with one `{question_id, justified}` per unresolved
question. Use rubric point IDs and exact forbidden-claim labels. A missing
assessment leaves coverage pending.

An adoption decision requires an observed traceable content failure that
B repairs, reviewed controls, acceptable coverage and budget. The frozen
SQLite rehearsal establishes the interface and isolates the instruction.
An observed model comparison and independently reviewed semantic outcomes
are pending. Promotion to production is a separate decision.

Verified on 2026-11-19 with Python 3.11 and the 97 exact lock distributions.
The frozen replay and scripted capture provide the local completion signals.
[SQLite Foreign Key Support](https://sqlite.org/foreignkeys.html)
