# DRA findings evaluation standard

Use this standard to decide whether a change improves report findings and
which part of the workflow to repair. The
[operator guide](README.md) gives the commands. The
[findings quality design](../../docs/superpowers/specs/2026-11-18-findings-quality-loop.md)
defines the existing contracts.

## Build and maintain the evaluation set

1. State one observable hypothesis before running a candidate. For a scope
   instruction, the hypothesis is that it preserves a material condition
   already present in the generator's input. Pair the target problem with a
   nearby successful case that would expose an unnecessary refusal or new
   unsupported claim.
2. Record a stable case ID, task family and source version. Freeze the
   question, source passages, accepted scope and scoring criteria. For an
   observed output, retain its run, question and finding IDs, report hash,
   exact statement and citations. Retain a locator and the relevant portion
   of the input actually visible at the stage being evaluated when available
   and allowed. Keep private raw captures local.
3. Record origin, scoring authority and diagnostic confidence independently.

   | Dimension | What to record |
   | --- | --- |
   | Sample origin | Actual local observation, retained historical review or synthetic control. A controlled new run records the behavior observed in that experiment. |
   | Reproduction evidence | Exact report and bound evidence where available. A historical record with missing inputs helps triage. Isolate the suspected stage when its visible inputs can be reconstructed and verified. |
   | Label authority | Deterministic check, synthetic expectation, model judgment or independent human judgment. Record the Judge model and rubric revision for a model judgment. |
   | Diagnostic confidence | Confirmed observation, hypothesis or unobserved. Link the earliest visible divergence to its evidence. Confirming a later symptom can leave the cause open. |

4. Freeze the development and holdout split by source and task family before
   tuning. Keep close variants in one split. Retain known regressions and
   normal controls. Move used holdout cases into development when their
   results guide tuning.

## Define the pass criteria before seeing outputs

Write short, independently checkable points per question. State what the
answer must cover, what would be a material overclaim, and what information
is missing when an unresolved disposition is expected. Accept equivalent
wording. Keep the rubric on the assessment side.

| Check | DRA practice |
| --- | --- |
| Structure and binding | The application verifies exact excerpts, same-run Evidence and the delivery artifact. Keep the structural error and its location when validation fails. |
| Support for each material claim | A blind Judge reads the question, statement, cited excerpts and source versions. Verdicts are supported, contradicted, insufficient evidence and conflicting evidence. A statement that accurately describes a documented conflict can be supported. Keep matched citation IDs and a rationale. |
| Coverage and abstention | Award a required point when a supported finding covers it. For an expected unresolved question, check that the stated reason identifies the missing information. Flag an unresolved answerable question as a wrongful abstention. |
| Task pass | Require a validated delivery, all necessary answerable points, justified expected unresolved dispositions, and freedom from material unsupported claims, forbidden overclaims and wrongful abstentions. Preserve unavailable assessments explicitly. |

The default is model judgment for the first semantic pass. Use the same model
and rubric across the paired outputs and hide arm identity and expected
verdicts. Reuse judgments with matching input hashes and scorer identity.
With a consequential technical disagreement, verify the pinned source or run
a discriminating check. Use another blinded Judge where it helps. Record
insufficient evidence when the dispute remains open. Human calibration is
optional. Its denominator counts independent human reviews with a completed
model prediction. Track agreement with synthetic expectations separately.

## Report with explicit denominators

| Metric | Calculation or breakdown |
| --- | --- |
| Delivery and scoring availability | Count planned, started, delivered and scorable arms. Show delivered/planned and scorable/planned when useful. Keep missing delivery, binding errors and unavailable scoring distinct. |
| Semantic support | Count each of the four verdicts among scorable claims. If showing a support rate, divide supported claims by all scored claims. Track structural exclusions and score failures alongside it. |
| Required-point coverage | Divide supported points by assessed required points. Show planned and delivered required points as well so missing results remain visible. |
| Wrongful abstention | Count unresolved questions that have required answerable points. For a rate, divide by delivered questions with required answerable points. Count justified unresolved dispositions separately. |
| Paired change | Report both pass, A only, B only and neither pass among scorable pairs. List new regressions and fixes individually and disclose incomplete pairs. |
| Resources | Report observed calls, tokens, elapsed time and cost for generation and judging separately when available. Keep unobserved values unknown. |

A zero denominator is unavailable. Lead with counts for a small set. Use
individual paired outcomes to choose what to investigate. Broader claims need
coverage across relevant task families and repetitions to assess run-to-run
variation.

## Diagnose and decide what to change

Follow the evidence in order through retrieval, capture, handoff, generation,
binding and judging. Compare the original passage, what reached the candidate
generator and the output claim. A qualifier seen in the generator input and
missing in the report is a candidate for a generation fix. When the first
captured summary already omits it, investigate source selection and summarizing
before attributing the issue to the final instruction.

Run A and B on the same frozen task, model, source bytes, tooling and budget
with isolated runs. Vary one declared input. Retain the actual outputs and use
the same application binder and rubric. Read any regression and newly added
material claim against its source. Preserve whether the evidence came from a
controlled prompt experiment or the intended deployment configuration.

- Consider adopting B when it fixes an observed, traceable failure and the
  reviewed controls show adequate coverage, acceptable resource use and no
  new serious errors or wrongful abstentions.
- Retain A on a material observed regression that the operator declines to
  accept. Record insufficient evidence if there is no demonstrated repair or a
  decisive observation is missing.
- The operator decides business tradeoffs, paid usage and changes to the
  deployed default. The evaluator handles evidence checks and routine grading.

## First application

**Target case for the next controlled run.** Ask how CPython 3.13.0
free-threaded Python can be installed through the official installers or
built from source. Require both points below, without forcing a particular
wording.

| Rubric point | Evidence to require |
| --- | --- |
| `official-installer-option` | Official macOS and Windows installers offer an optional free-threaded build. |
| `source-build-option` | Scope the `--disable-gil` configure option to building from source. |
| Forbidden overclaim | All users must compile their own interpreter or enable the option when using the official installer. |

Freeze the relevant installation passages from the pinned CPython source
before generating. Keep the existing SQLite foreign-key task alongside it as
a normal control. It checks both database-connection scope and a justified
unresolved question. [CPython v3.13.0 Installation](https://github.com/python/cpython/blob/v3.13.0/Doc/howto/free-threading-python.rst#L23-L34)
· [SQLite rubric](native-rubric.json)

A historical CPython fallback has the installation omission in the retained
tool summary. Its original webpage bytes and complete coordinator input are
unobserved, so the historical diagnosis stays at the captured summary.
The new controlled case can establish what a model does with the exact
installation passages in view. The existing SQLite pair passed in both
arms in the Codex experiment. These observations support retaining the
baseline pending evidence of a repair.
