# Agent Evaluation Regression Gate

The Agent evaluation regression gate is a deterministic, credential-free proof
for fixed public-safe inputs. It checks the current generic result contract,
normalized tool trajectory, run-level Evidence integrity, terminal state,
declared safety policy, and fixture-defined efficiency observations. It does
not invoke an Agent, provider, network tool, runtime collector, or hosted
evaluation service.

Run the required baseline check:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
```

Build explicit candidates for review:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py build \
  --json-output /tmp/dra-agent-evaluation-candidate.json \
  --markdown-output /tmp/dra-agent-evaluation-candidate.md
```

`build` never accepts a committed baseline as an output path and has no
automatic baseline-accept mode. Review scenario, evaluator, JSON, Markdown,
and documentation changes together before replacing either committed artifact.

## Versioned Contracts

- Dataset: `dra.agent-evaluation-cases.v1`
- Report: `dra.agent-evaluation-report.v1`
- Comparison: `dra.agent-evaluation-comparison.v1`

The eight ordered cases are `canonical_success`, `fallback_blocked`,
`review_required`, `failed_terminal`, `evidence_missing`, `prohibited_tool`,
`untrusted_instruction_action`, and `cross_run_reference`.

The six ordered evaluators are:

| Evaluator | Boundary |
|---|---|
| `result_contract` | Reuses the existing downstream projection and distinguishes canonical, fallback, and invalid result contracts. |
| `trajectory_policy` | Checks allowlisted tools, call/result pairing, terminal ordering, and run isolation using metadata only. |
| `evidence_integrity` | Checks required run-level Evidence identity and explicitly typed references without reading report prose. |
| `terminal_state` | Checks review-required and failed terminal paths without inventing an unpersisted cause. |
| `safety_boundary` | Checks declared trust signals and prohibited actions after an untrusted instruction. |
| `efficiency_observation` | Checks fixture-defined counts and records missing token data as observational. |

The gate must not parse Markdown into typed findings, claims, limitations,
conflicts, or Evidence references. Generic Markdown remains an artifact, not a
second structured authority.

## Structural And Policy Ownership

Pydantic owns structural schemas: exact fields, strict types, enums, bounds,
and JSON-compatible canonical model dumps. Project evaluators own DRA
cross-field and policy semantics. Project code also retains bounded byte reads,
`json.loads`, public-safety scanning, hashing, deterministic serialization,
stable CLI mapping, and baseline path protection.

AgentEvals trajectory matching is deferred because its message-equivalence
model and adapter dependency do not match the normalized DRA metadata policy.
DeepAgents live evaluation and live observation are deferred because real Agent/model execution,
credentials, and hosted diagnostics are incompatible with required CI. A live
observation path requires a separate approved design. LangSmith remains
privacy-first diagnostics and is not release or business authority.

## Reports And Baselines

The canonical JSON report contains dataset and evaluator identity, summary
counts, ordered case results, fixture metrics, and limits. The Markdown report
is rendered only from validated JSON. Committed artifacts are:

- `docs/evidence/agent-evaluation-regression-v1.json`
- `docs/evidence/agent-evaluation-regression-v1.md`

`check` regenerates both forms and emits only a bounded comparison envelope.
It exits zero only when the bytes match the reviewed baseline and the candidate
has no expectation mismatch or blocking regression. Coherent drift is a valid
evaluation outcome with exit 1, comparison-only stdout, and empty stderr.

## Stable Errors

Invalid input or output writes one bounded JSON line to stderr and nothing to
stdout. Stable codes are:

- `evaluation_manifest_invalid`
- `evaluation_schema_unsupported`
- `evaluation_case_invalid`
- `evaluation_registry_invalid`
- `evaluation_metrics_invalid`
- `evaluation_baseline_invalid`
- `evaluation_output_invalid`
- `evaluation_public_output_unsafe`
- `evaluation_internal_error`

Raw Pydantic errors, paths, tracebacks, prompts, tool payloads, Evidence
snippets, and provider responses are not public error content.

## Limits And Authority

The gate is contract regression evidence. It does not verify answer truth
automatically and is not answer-quality judgment, production monitoring, or release approval. Token and
cost values are fixed fixture observations. `cost_estimate` is labeled with
`estimate=true`, currency, and pricing basis; it is not billed or invoiced
provider usage.

The application database remains business authority for ResearchRun,
EvidenceLedger, review, verification, publication, and delivery. DeepAgents
remains the research harness, LangGraph remains workflow runtime/checkpoint
position, and LangSmith remains diagnostics. This offline report owns none of
those runtime decisions.
