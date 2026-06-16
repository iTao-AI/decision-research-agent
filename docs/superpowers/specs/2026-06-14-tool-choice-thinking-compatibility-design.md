<!-- /autoplan restore point: /Users/mac/.gstack/projects/iTao-AI-deep-search-agent/codex-tool-choice-thinking-compat-autoplan-restore-20260614-195617.md -->
# Tool Choice And Thinking Compatibility Design

## Goal

Prevent provider capability conflicts when a structured-output or tool-bound
call requires an explicit `tool_choice`, while preserving thinking mode for
ordinary model calls.

The fix belongs in the shared model capability layer. It is not specific to the
Talent profile or benchmark runner.

## Current Failure

The default DeepSeek v4 primary and fallback models are initialized with:

```python
extra_body={"thinking": {"type": "enabled"}}
```

Deep Agents uses an explicit `tool_choice` when a subagent has a structured
`response_format`. The current `FallbackChatModel.bind_tools()` forwards that
`tool_choice` unchanged to both models. The provider rejects the combination:

```text
Thinking mode does not support this tool_choice
```

This failure blocks every capability that combines the current provider's
thinking mode with forced tool selection. It is not caused by the Talent
profile's scope, tools, or artifact contracts.

## Chosen Approach

Use a shared/leaf model capability boundary. Every model returned from
`create_llm_model()` must pass through the same capability policy, including:

- default primary + fallback;
- fallback disabled via `LLM_FALLBACK_MODEL=none`;
- fallback configured to the same model as primary.

The concrete implementation should add a small `CapabilityAwareChatModel`
wrapper around leaf `BaseChatModel` instances. The wrapper preserves ordinary
model behavior and intercepts only `bind_tools()`. When a proven-conflict model
family receives a forced `tool_choice`, the wrapper binds tools against an
independent compatible model variant with thinking disabled. Non-forced choices
and ordinary calls keep the configured thinking mode.

`FallbackChatModel` remains responsible for primary/fallback execution. It
should not be the only place where capability adaptation happens, because some
valid configurations return a single raw model today.

The original model instances remain unchanged in both paths, so subsequent
free-form calls continue using the configured thinking mode.

Runtime inspection against the currently installed `ChatOpenAI` confirmed that
`model_copy(update={"extra_body": {"thinking": {"type": "disabled"}}})` creates
a distinct model instance and does not mutate the source instance. Tests remain
the contract for this behavior because model copying is an implementation
detail rather than a documented cross-provider LangChain guarantee.

## Rejected Alternatives

### Disable Thinking Globally

Setting `LLM_THINKING_MODE=disabled` would avoid the immediate error but would
change every call, including free-form research and synthesis. It hides the
capability conflict instead of adapting only the incompatible call.

### Remove Or Ignore `tool_choice`

Dropping the forced choice could allow the provider call to succeed, but it
would weaken structured-output enforcement. Deep Agents' structured
`response_format` path must retain its explicit tool selection contract.

### Special-Case The Talent Profile

Handling the conflict in `profile_agents.py` would unblock the current
benchmark but leave future structured-output profiles exposed to the same
provider error. The conflict is between model capabilities, not profile policy.

## Architecture

`agent/llm.py` remains the only production file changed for runtime behavior.

Add focused helpers that:

1. Classify `tool_choice` into forced vs non-forced semantics.
2. Detect the proven-conflict DeepSeek V4 model family.
3. Build an independent tool-binding-compatible model variant when needed.
4. Preserve unrelated `extra_body` keys and callbacks when constructing the
   variant.

`create_llm_model()` wraps every initialized leaf model with
`CapabilityAwareChatModel` before returning it directly or placing it inside
`FallbackChatModel`. `FallbackChatModel.bind_tools()` forwards the original
`tool_choice` type and value to primary and fallback; the wrapped leaf models
decide whether adaptation is required.

```text
create_llm_model()
  -> init primary leaf
  -> wrap primary leaf with CapabilityAwareChatModel
  -> if fallback configured:
       init fallback leaf
       wrap fallback leaf with CapabilityAwareChatModel
       return FallbackChatModel(primary=wrapped_primary, fallback=wrapped_fallback)
     else:
       return wrapped_primary

CapabilityAwareChatModel.bind_tools(tools, tool_choice=<non-forced>)
  -> bind original leaf
  -> thinking preserved

CapabilityAwareChatModel.bind_tools(tools, tool_choice=<forced>)
  -> if model family conflicts with thinking + forced tool choice:
       bind independent compatible leaf copy
       thinking disabled only on copy
     else:
       bind original leaf
  -> forced tool_choice preserved
```

## Configuration Semantics

The compatibility helper must be conservative:

- It only changes calls with explicit `tool_choice`.
- It only adapts forced tool choices: `True`, `"any"`, `"required"`, a
  specific tool-name string, or a tool-selection dict.
- It does not adapt `None`, `False`, `"none"`, or `"auto"`.
- It only changes proven-conflict DeepSeek V4 models whose
  `extra_body.thinking.type` is enabled.
- It must not mutate original models or shared nested dictionaries.
- It must preserve unrelated provider-specific `extra_body` fields.
- It applies equally to primary and fallback models.
- It does not add a new environment variable or provider registry.

Models without `model_copy()` support are outside the current initialized model
contract. If such a model reaches the helper with an incompatible forced choice,
the helper must fail clearly rather than silently remove `tool_choice`.

## Failure Handling

- Copy or binding failures propagate through the existing call path.
- The helper must not silently fall back to an unmodified thinking-enabled model
  for a forced choice.
- Primary invocation failures after successful binding continue to use
  `FallbackRunnable` and its existing warning log.
- No provider errors, prompts, or model payloads are persisted by this change.

## Files

- Modify `agent/llm.py`: add the capability-aware leaf wrapper, exact forced
  tool-choice classifier, compatible variant helper, and safe binding-level log.
- Modify `tests/unit/test_llm_config.py`: verify forced-choice adaptation,
  ordinary binding behavior, single-model coverage, configuration preservation,
  copy isolation, and fallback behavior.
- Modify `spec/external-services.md`: document the DeepSeek thinking +
  forced-tool-choice compatibility rule and emergency-only global rollback.
- Update `docs/evidence/run-log.md` only after a real post-fix benchmark run,
  recording the actual result without claiming the value gate passed unless the
  generated bundle supports that claim.

No profile policy, Deep Agents graph, API, persistence schema, fixture provider,
or benchmark input changes are in scope.

## Test Matrix

| Scenario | Expected result |
|---|---|
| `tool_choice=None`, thinking enabled | Original models bind tools; thinking remains enabled |
| `tool_choice=False`, `"none"`, or `"auto"` | Original models bind tools; thinking remains enabled |
| `tool_choice=True`, `"any"`, `"required"`, tool name, or dict | Compatible variants bind tools for proven-conflict models |
| Forced `tool_choice`, thinking enabled | Independent copies bind tools with thinking disabled |
| Forced `tool_choice`, thinking already disabled or absent | Original models bind without unnecessary copying |
| Forced `tool_choice`, unrelated `extra_body` fields present | Unrelated fields remain unchanged on compatible copies |
| Fallback disabled | Returned single model still applies the same capability policy |
| Forced `tool_choice`, primary bound invocation fails | Existing fallback path invokes compatible fallback copy |
| Any binding path | Original primary/fallback configurations remain unchanged |

## Acceptance Criteria

1. Focused tests demonstrate that explicit `tool_choice` is still forwarded to
   both bound models.
2. Focused tests demonstrate that thinking is disabled only on independent
   copies used for forced tool selection.
3. Focused tests demonstrate that ordinary calls and ordinary tool binding
   preserve the configured thinking mode.
4. Focused tests demonstrate fallback-disabled and primary-equals-fallback
   configurations still apply the capability policy.
5. Existing primary/fallback invocation behavior remains intact.
6. `tests/unit/test_llm_config.py` and the full backend test suite pass.
7. A one-repetition diagnostic benchmark produces
   `benchmark_status=ready_for_human_review` and
   `completion.ready_for_human_review=true`.
8. The full 3x2 Talent value gate is rerun only after the diagnostic succeeds;
   its result remains evidence, not an automatic value claim.

## AUTOPLAN REVIEW

### Phase 1: CEO Review

#### Premise Challenge

| Premise | Assessment | Decision |
|---|---|---|
| The failure is a capability conflict, not a Talent profile bug | Confirmed by the repeated provider error before any Talent evidence or artifact is produced | Keep |
| A shared capability-layer fix is preferable to a profile special case | Sound, because future structured-output profiles can hit the same class of conflict | Keep |
| `FallbackChatModel.bind_tools()` is the shared capability layer | False when fallback is disabled or configured to the primary model; `create_llm_model()` returns the raw model in those paths | User Challenge accepted: implement shared/leaf capability boundary |
| Every non-`None` `tool_choice` conflicts with thinking | Unproven; `auto`, `none`, `required`, a tool name, a dict, and a bool may have different provider semantics | Replace with an explicit conflict predicate |
| Setting only `extra_body.thinking.type=disabled` creates a compatible request | Plausible but not proven while `reasoning_effort=max` remains configured | Verify with a real one-run diagnostic before the full benchmark |
| Removing the provider error is sufficient diagnostic success | False; the capability is restored only when a schema-valid `ResearchPacket` and artifacts are produced | Strengthen the diagnostic gate |

The user already confirmed the main premise before `/autoplan`: this is a
capability conflict and should not be special-cased in the Talent profile.

#### What Already Exists

| Sub-problem | Existing code to reuse |
|---|---|
| Model construction and provider-specific configuration | `agent/llm.py::_model_kwargs()` and `create_llm_model()` |
| Primary/fallback invocation behavior | `agent/llm.py::FallbackChatModel` and `FallbackRunnable` |
| Structured-output trigger | `agent/profile_agents.py` with `response_format=ResearchPacket` |
| Focused configuration tests | `tests/unit/test_llm_config.py` |
| Dependency compatibility baseline | `tests/unit/test_deployment_preflight.py` and `constraints.txt` |
| Real diagnostic and 3x2 execution | `scripts/talent_value_gate_runner.py` |
| Evidence wording boundary | `docs/evidence/run-log.md` |

#### Dream State Delta

```text
CURRENT
  configured thinking + structured tool choice
  -> provider rejects request
  -> Talent produces no ResearchPacket

THIS FIX
  explicit model capability policy
  -> incompatible forced choice gets a compatible model variant
  -> ordinary calls retain configured thinking
  -> adaptation is observable
  -> structured output succeeds or fails with an actionable reason

12-MONTH IDEAL
  provider/model capability matrix backed by benchmark evidence
  -> task-level model selection and reasoning policy
  -> no silent capability downgrade
  -> quality/cost tradeoffs are measurable
```

The 12-month ideal is not in scope for this bugfix. This change should leave an
explicit extension point without building a provider registry.

#### Implementation Alternatives

| Approach | Effort | Risk | Decision |
|---|---:|---:|---|
| Keep adaptation only inside `FallbackChatModel.bind_tools()` | Low | High: fallback-disabled paths bypass it | Rejected after user challenge |
| Add a small capability-aware model wrapper used for both single-model and fallback paths | Medium | Medium: one additional wrapper contract | Accepted |
| Reconstruct explicit provider-specific model variants at initialization time | Medium | Medium: duplicates some construction/configuration logic | Viable alternative if model-copy binding cannot be proven |
| Add a full provider capability registry | High | High: premature abstraction | Reject for this PR |
| Add a separate structured-output model or two-stage formatter | High | High: changes runtime and benchmark semantics | Defer until benchmark evidence justifies it |
| Disable thinking globally | Low | High: changes all calls | Reject |

#### Error And Rescue Registry

| Failure | Detection | Rescue | User-visible effect |
|---|---|---|---|
| Capability adapter is bypassed | Single-model/fallback-disabled focused test | Route every initialized model path through the chosen capability boundary | Prevent repeated provider 400 |
| Wrong `tool_choice` values trigger adaptation | Parameterized tests for explicit choice kinds | Apply an explicit conflict predicate and preserve the original value/type | Avoid unnecessary quality downgrade |
| Compatible variant still sends contradictory reasoning settings | Real one-run diagnostic | Treat the model variant as incompatible and stop before full 3x2 | No misleading value-gate result |
| Copy or reconstruction mutates the original model | Identity and nested-config isolation tests | Fail closed; ordinary model remains untouched | Ordinary calls keep configured behavior |
| Adaptation silently changes benchmark semantics | Non-sensitive adaptation metadata | Report effective mode/adaptation count with benchmark evidence | Reviewers can interpret results |
| Provider error disappears but structured output remains broken | Diagnostic requires valid packet and artifacts | Keep value gate blocked | No false-positive completion claim |

#### Failure Modes Registry

| Failure mode | Severity | Current coverage | Decision |
|---|---:|---|---|
| Fallback-disabled path bypasses adaptation | Critical | Missing | Accepted shared-boundary fix |
| `tool_choice is not None` over-adapts compatible choices | High | Missing | Add exact classification tests |
| `reasoning_effort=max` remains incompatible with thinking disabled | High | Missing real diagnostic | Add diagnostic stop gate |
| No valid `ResearchPacket` after error disappears | High | Weak acceptance criterion | Strengthen acceptance |
| Silent adaptation makes benchmark results hard to explain | Medium | Missing | Add non-sensitive observability |
| LangChain copy semantics change after dependency upgrade | Medium | Only manual inspection | Add real `ChatOpenAI` no-network smoke |

#### NOT In Scope

- Building a general provider registry.
- Selecting a dedicated structured-output model.
- Two-stage reason-then-format orchestration.
- Proving whether thinking improves every research task.
- Changing Talent scope, tools, artifact contracts, or benchmark inputs.
- Claiming the Talent value gate passed.

#### CEO Dual Voices Consensus

| Dimension | Independent reviewer | Codex voice | Consensus |
|---|---|---|---|
| Premises valid? | Partial: capability conflict valid, implementation boundary false | Partial: configuration is being treated as capability | Confirmed concern |
| Right problem to solve? | Yes, but fix must cover single-model paths | Yes, but do not overgeneralize one provider error | Confirmed with boundary correction |
| Scope calibration correct? | Missing shared wrapper path and observability | Missing capability policy and benchmark interpretability | Confirmed concern |
| Alternatives sufficiently explored? | No: shared wrapper and real-model smoke missing | No: explicit variants and task-level policy underexplored | Confirmed concern |
| Competitive/market risks covered? | Not applicable to this internal bugfix | Not applicable; runtime quality risk matters instead | Confirmed N/A |
| Six-month trajectory sound? | No if provider patches stay in fallback wrapper | No if silent downgrade and undocumented copy behavior persist | Confirmed concern |

#### Phase 1 Completion Summary

- Mode: `SELECTIVE EXPANSION`.
- Premise gate: passed by the user's prior capability-layer decision.
- Confirmed direction: keep the fix in the model capability layer.
- User Challenge accepted on 2026-06-15: replace the fallback-only insertion
  point with a capability-aware boundary covering single-model and fallback
  paths.
- Auto-decided hardening: exact conflict predicate, non-sensitive adaptation
  metadata, real-model no-network smoke, and stronger diagnostic completion.
- Design review: skipped because there is no UI scope.

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO | Keep capability-layer ownership | Mechanical | DRY | The provider conflict is independent of Talent policy | Talent special case |
| 2 | CEO | Challenge fallback-only insertion point | User Challenge | Completeness | Raw single-model paths bypass `FallbackChatModel` | Silent scope reduction |
| 3 | CEO | Add exact conflict predicate and preserve `tool_choice` type/value | Auto-decided | Explicit over clever | `non-None` is not a capability definition | Broad implicit downgrade |
| 4 | CEO | Add non-sensitive adaptation observability | Auto-decided | Completeness | Benchmark results must expose effective runtime mode | Silent downgrade |
| 5 | CEO | Strengthen diagnostic to require valid packet and artifacts | Auto-decided | Completeness | Error disappearance alone is a false-positive gate | Error-string-only acceptance |
| 6 | CEO | Add real `ChatOpenAI` no-network smoke | Auto-decided | Pragmatic | Protects against undocumented copy/binding changes | Fake-only coverage |
| 7 | CEO | Defer provider registry and alternate formatter/model | Auto-decided | Pragmatic | They exceed the direct bug blast radius | Premature architecture expansion |
| 18 | Final Gate | Accept shared/leaf `CapabilityAwareChatModel` boundary | User Challenge resolved | Completeness | User selected option A on 2026-06-15; fallback-only would not cover raw model return paths | Fallback-only implementation |

### Phase 3: Engineering Review

#### Scope Challenge

The direct blast radius is larger than the original two-file statement but
remains bounded:

- `agent/llm.py` owns model construction, capability classification, adaptation,
  and fallback composition.
- `tests/unit/test_llm_config.py` owns the focused behavioral contract.
- `scripts/talent_value_gate_runner.py` and its tests need changes only if the
  approved design requires the exported bundle to describe effective capability
  policy. Binding-event logs alone do not require runner changes.
- `docs/evidence/run-log.md` changes only after a real diagnostic or benchmark.

No profile, API, persistence, tool, or artifact-contract changes are needed.

#### Architecture Review

```text
                          create_llm_model()
                                 |
                   +-------------+-------------+
                   |                           |
             raw primary model            raw fallback model
                   |                           |
          explicit capability policy  explicit capability policy
                   |                           |
          compatible leaf boundary    compatible leaf boundary
                   |                           |
                   +-------------+-------------+
                                 |
                    optional FallbackChatModel
                                 |
                       Deep Agents / LangChain
                                 |
              bind_tools(..., tool_choice="any")
                                 |
             conflict predicate + compatible variant
                                 |
                ChatOpenAI normalizes "any" -> "required"
```

The approved implementation must ensure both single-model and fallback-enabled
construction paths pass through the capability boundary. If a wrapper is used,
it must preserve model identity, callbacks, and the capability/profile fields
LangChain uses to select structured-output strategy.

The first implementation must not build a provider registry. A small explicit
predicate should identify only the proven DeepSeek v4 conflict.

#### Exact Tool Choice Contract

LangChain's installed `ChatOpenAI.bind_tools()` accepts
`dict | str | bool | None`. The installed LangChain `ToolStrategy` sends
`tool_choice="any"` when structured output tools exist, and `ChatOpenAI`
normalizes `"any"` to `"required"`.

| Input choice | Forced? | Adapt thinking for proven-conflict models? |
|---|---:|---:|
| `None`, `False`, `"none"`, `"auto"` | No | No |
| `True`, `"any"`, `"required"` | Yes | Yes |
| Specific tool-name string | Yes | Yes |
| Tool-selection dict | Yes | Yes |
| Unsupported type | Unknown | Let underlying `bind_tools()` fail clearly |

The adapter must forward the original type and value. It must not normalize or
drop the choice itself.

#### Configuration And Compatibility Rules

- The capability predicate must require both:
  - a model family proven to reject thinking with forced tool choice; and
  - a forced tool choice from the table above.
- A compatible variant must preserve unrelated `extra_body` fields.
- A compatible variant must not mutate the original model or shared nested
  dictionaries.
- The initial variant disables `extra_body.thinking`.
- The real one-repetition diagnostic determines whether retaining
  `reasoning_effort=max` is compatible.
- If the provider still rejects the request, implementation stops and the
  variant is revised before any full 3x2 run. No automatic global thinking
  disable is allowed.
- If primary or fallback cannot be adapted or bound, binding fails closed.
  The fallback path must not silently omit a configured fallback model.

#### Observability Semantics And Safety

First-version observability is a binding-level structured log, not run-scoped
telemetry. This avoids falsely associating graph/model binding events with a
concurrent `ResearchRun`.

Allowed fields:

- `event=model_capability_adaptation`
- `reason=thinking_forced_tool_choice_conflict`
- `model_family=deepseek-v4`
- `model_role=primary|fallback|single`
- `tool_choice_kind=required|tool_name|tool_dict`
- `configured_thinking_mode=enabled`
- `effective_thinking_mode=disabled`

Forbidden fields:

- prompts, messages, tool schemas, raw tool-choice dicts, provider request
  bodies, `extra_body`, bind kwargs, credentials, and full exceptions.

Run-scoped adaptation telemetry and benchmark-bundle adaptation counts are
deferred because they require a separate lifecycle/data-contract design.

#### Code Quality Review

1. Keep the conflict classifier and compatible-variant constructor as focused
   helpers in `agent/llm.py`; do not mix profile names into either helper.
2. Preserve `FallbackRunnable` and its current logging behavior.
3. Update `FallbackChatModel.bind_tools()` annotation to the actual LangChain
   contract: `dict | str | bool | None`.
4. Avoid caching mutable model variants in a global dict. Shallow copying is
   acceptable for this bounded change if nested provider configuration is
   rebuilt explicitly and measured by tests.
5. Do not duplicate `_model_kwargs()` construction logic unless the real
   diagnostic proves copy-based variants cannot produce a compatible request.

#### Test Diagram

```text
model construction
  +-- default primary + fallback ---------- unit configuration test
  +-- fallback disabled ------------------- unit construction/adaptation test
  +-- fallback equals primary ------------- unit construction/adaptation test

tool choice classification
  +-- any / required / True --------------- parameterized forced-choice test
  +-- tool name / tool dict --------------- parameterized forced-choice test
  +-- auto / none / False / None ---------- parameterized non-forced test
  +-- unsupported type -------------------- underlying clear-failure test

compatible variant
  +-- original object unchanged ----------- unit isolation test
  +-- nested extra_body unchanged --------- unit isolation test
  +-- unrelated provider fields kept ------ unit preservation test
  +-- callbacks / model identity kept ----- real ChatOpenAI no-network smoke
  +-- reasoning_effort behavior ----------- smoke + real diagnostic

fallback behavior
  +-- compatible primary invocation ------- focused unit test
  +-- compatible primary failure ---------- focused fallback test
  +-- fallback bind/adaptation failure ----- fail-closed unit test

structured output
  +-- installed LangChain sends any -------- no-network integration smoke
  +-- ChatOpenAI normalizes to required ----- real ChatOpenAI no-network smoke
  +-- Talent produces valid packet/artifacts real one-repetition diagnostic
  +-- same 3x2 benchmark ------------------- post-diagnostic evidence run
```

#### Performance Review

`bind_tools()` may run repeatedly during a long agent execution. The first
implementation may use shallow `model_copy()` per forced binding because model
copies contain configuration, not request data, and the change avoids a
concurrent mutable cache. Tests must prove nested configuration isolation.

Do not add a cache until profiling shows this copy path is material. The full
3x2 benchmark should report elapsed time as evidence but does not need a new
performance threshold for this bugfix.

#### Security Review

The change does not add an external input or permission surface. Its main
security concern is accidental logging of provider payloads or tool schemas.
The allowlist above is mandatory. Existing privacy-first LangSmith behavior
remains unchanged.

#### Engineering Failure Modes Registry

| Failure | Severity | Required prevention |
|---|---:|---|
| Single-model path bypasses adaptation | Critical | Capability boundary covers every `create_llm_model()` return path |
| Wrapper changes LangChain structured-output strategy | High | Preserve model capability/profile fields and test strategy behavior |
| Non-forced choices disable thinking | High | Exact classifier table and parameterized tests |
| Compatible variant remains provider-incompatible | High | One-run diagnostic stop gate, including `reasoning_effort` decision |
| Error disappears but no valid packet/artifacts | High | Require `ready_for_human_review=true` for one-repetition bundle |
| Primary/fallback capability asymmetry breaks binding | Medium | Fail-closed tests for both model roles |
| Repeated model copies add hidden cost | Medium | Keep shallow/immutable; measure before caching |
| Adaptation logs leak provider payload | Medium | Fixed field allowlist |

#### Engineering Completion Summary

- Architecture sound with the accepted shared-boundary implementation.
- Critical gaps: `0` after accepting the shared/leaf capability boundary.
- High issues folded into the reviewed plan: exact choice classification,
  wrapper/profile preservation, reasoning-setting diagnostic, stronger
  acceptance, observability lifecycle.
- Performance risk is bounded; no cache should be added in the first version.
- Security surface is unchanged if structured logs use the fixed allowlist.
- Design review remains skipped: no UI files or user interaction flows change.

#### Eng Dual Voices Consensus

| Dimension | Independent reviewer | Codex voice | Consensus |
|---|---|---|---|
| Architecture sound? | Leaf/shared boundary required and now accepted | Same | Confirmed concern resolved |
| Test coverage sufficient? | Missing single-model, choice matrix, real model, diagnostic | Same | Confirmed concern |
| Performance risks addressed? | Repeated shallow copy needs explicit acceptance | Repeated binding/copy needs bounded policy | Confirmed, non-blocking |
| Security threats covered? | Logging allowlist required | Logging allowlist required | Confirmed |
| Error paths handled? | Reasoning settings and asymmetric fallback unspecified | Same | Confirmed concern |
| Deployment risk manageable? | Yes after diagnostic stop gate | Yes after formal plan revision | Confirmed |

#### Additional Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 8 | Eng | Define explicit forced-choice classification table | Auto-decided | Explicit over clever | Installed LangChain supports several distinct choice semantics | `tool_choice is not None` |
| 9 | Eng | Limit first-version observability to binding-level safe logs | Auto-decided | Pragmatic | Run attribution is not reliable at model/graph binding lifecycle | Fake run-scoped telemetry |
| 10 | Eng | Require one-repetition bundle to be `ready_for_human_review` | Auto-decided | Completeness | Reuses the runner's packet/artifact fail-closed contract | Error-string-only gate |
| 11 | Eng | Fail closed when configured primary/fallback cannot adapt or bind | Auto-decided | Explicit over clever | Silently dropping fallback changes configured runtime behavior | Partial silent composition |
| 12 | Eng | Accept shallow per-binding copies before profiling | Auto-decided | Pragmatic | Avoids mutable concurrency cache and premature optimization | Global variant cache |
| 13 | Eng | Defer run-scoped adaptation telemetry | Auto-decided | Pragmatic | Requires separate lifecycle and data-contract changes | Scope expansion into ResearchRun |

### Phase 3.5: DX Review

#### DX Scope Assessment

This plan has developer-facing scope even though it does not add a public API.
The affected developer is the repo maintainer implementing future profile and
structured-output work. Their path crosses model configuration, LangChain
binding semantics, benchmark execution, and evidence documentation.

| Item | Assessment |
|---|---|
| Product type | Internal AI service / model capability layer / benchmark CLI |
| Primary persona | Maintainer adding or debugging structured-output agent profiles |
| Mode | DX POLISH |
| Current TTHW | Unit-level verification: under 1 minute; real diagnostic: API-key dependent and likely 10-20 minutes |
| Target TTHW | Under 5 minutes for local confidence; one documented command for the real diagnostic |
| External voices | Degraded: Claude subagent and Codex outside voice were unavailable due local usage limit |
| Hall-of-Fame reference | Degraded: `dx-hall-of-fame.md` was not present in the installed gstack skill tree |

#### Evidence Read For DX

| Source | Finding |
|---|---|
| `README.md` | Quick Start documents service startup, run-scoped APIs, and benchmark fixtures, but not this model capability conflict |
| `spec/external-services.md` | Lists `LLM_THINKING_MODE` and `LLM_REASONING_EFFORT`, but does not describe forced tool-choice compatibility |
| `agent/llm.py` | The current fallback wrapper forwards `tool_choice`; fallback-disabled paths return the raw model |
| `agent/profile_agents.py` | Talent researcher uses `response_format=ResearchPacket`, which triggers structured-output binding |
| `scripts/talent_value_gate_runner.py` | The runner already exposes `benchmark_status` and `completion.ready_for_human_review` as the correct success gate |
| `tests/unit/test_llm_config.py` | Existing tests cover config and fallback behavior, but not capability adaptation |
| `docs/AGENT_INTEGRATION.md` | Documents compatibility identifiers and env vars; no impact from this fix |

#### Developer Persona Card

| Field | Persona |
|---|---|
| Who | Maintainer of the Decision Research Agent codebase |
| Context | Adds a new structured-output profile or debugs a provider failure during benchmark execution |
| Tolerance | Will inspect code and run tests, but should not need to reverse-engineer LangChain provider internals |
| Expects | Local unit tests, clear capability policy, safe diagnostics, and one obvious rollback path |

#### Developer Empathy Narrative

I am adding a profile that returns a structured object. The repository README
shows how to run the service and mentions Talent benchmark fixtures, so I look
for the model configuration and find `spec/external-services.md`. It tells me
DeepSeek V4 defaults to thinking mode enabled and `reasoning_effort=max`, but it
does not tell me that structured output may force `tool_choice`. I then inspect
`agent/profile_agents.py` and see `response_format=ResearchPacket`; the failure
looks like a model/provider problem, not a profile contract problem. Without
this plan's extra tests and diagnostic gate, my fastest path is trial and error:
disable thinking globally, rerun the benchmark, and risk changing free-form
research quality. The intended developer experience is different: the local
unit tests should show the exact compatibility rule, the logs should say a safe
model capability adaptation happened, and the benchmark runner should make it
obvious whether the run produced a valid `ResearchPacket`, review bundle, and
canonical artifacts.

#### Competitive DX Benchmark

Search was not used for this internal maintenance task. Reference benchmark is
against common mature developer tooling:

| Tool pattern | TTHW | Relevant DX choice |
|---|---:|---|
| Mature CLI/library local unit path | < 1 min | Fail fast without network |
| Provider integration diagnostic | 5-20 min | One command plus explicit pass/fail fields |
| This plan before DX fixes | 10-20 min | Requires reading source and interpreting benchmark JSON |
| This plan after DX fixes | < 5 min local confidence, one real diagnostic command | Exact predicate tests, safe logs, documented success fields |

#### Magical Moment

The maintainer's magical moment is not a UI effect. It is seeing a structured
Talent diagnostic finish with:

```json
{
  "benchmark_status": "ready_for_human_review",
  "completion": {
    "ready_for_human_review": true,
    "schema_failure_count": 0,
    "artifact_failure_count": 0
  }
}
```

That proves the provider error was not merely hidden. It proves structured
output, packet validation, review bundle creation, artifact generation, and
identity isolation still work.

#### Developer Journey Map

| Stage | Developer does | Current friction | Required plan resolution |
|---|---|---|---|
| Discover | Reads README and existing plan | Conflict is not in README or service docs | Keep this spec as implementation guide |
| Configure | Checks `LLM_*` env vars | `LLM_THINKING_MODE` escape hatch exists but is not framed as emergency-only | Update `spec/external-services.md` |
| Implement | Opens `agent/llm.py` | Fallback-only insertion point is misleading | Implement accepted shared-boundary design |
| Unit test | Runs `tests/unit/test_llm_config.py` | No tests for forced tool-choice adaptation | Add choice matrix and copy-isolation tests |
| No-network smoke | Exercises real `ChatOpenAI.bind_tools()` | Provider adapter semantics are implicit | Add smoke for `any` -> `required` and preserved fields |
| Real diagnostic | Runs one repetition | Success could be misread as no exception | Require `ready_for_human_review=true` |
| Full benchmark | Runs 3x2 | Talent may use thinking-disabled structured path while Generic keeps thinking | Record this fairness caveat in output/evidence |
| Document | Updates evidence docs | Risk of claiming value gate too early | Only update run log with actual bundle results |
| Rollback | Needs to unblock work | Global thinking disable is tempting | Document `LLM_THINKING_MODE=disabled` as emergency diagnostic only |

#### First-Time Developer Confusion Report

```text
T+0:00  I read the plan and see the original implementation says FallbackChatModel.bind_tools().
T+0:30  I check create_llm_model() and realize fallback-disabled deployments return a raw ChatOpenAI.
T+1:30  I inspect LangChain binding behavior and see tool_choice can be bool, string, dict, or None.
T+2:30  I discover "non-None" would disable thinking for "auto" and "none", which are not forced calls.
T+4:00  I need a local test to prove the model copy keeps callbacks/profile fields and does not mutate extra_body.
T+6:00  I need the real diagnostic to tell me if keeping reasoning_effort=max is still incompatible.
Final  I can implement safely only if the plan explicitly resolves the shared boundary and stop gate.
```

#### DX Pass Scores

| Dimension | Score | Reason | Required improvement |
|---|---:|---|---|
| Getting Started | 7/10 | Unit path is fast; real diagnostic command is not yet written into docs | Add exact local and real diagnostic commands |
| API/CLI/SDK | 8/10 | The runner's success fields are clear; model adaptation helpers need guessable names | Use explicit helper names and preserve LangChain signatures |
| Error Messages | 6/10 | Provider failure is recognizable, but adaptation failure message is not specified | Add problem/cause/fix exception/log wording |
| Documentation | 6/10 | External service doc lists env vars but not compatibility semantics | Update `spec/external-services.md` |
| Upgrade Path | 7/10 | No public breaking API; future profiles benefit automatically if boundary is shared | Add compatibility note for new structured-output profiles |
| Dev Environment | 8/10 | Existing pytest setup works; real diagnostic still depends on configured API key | Keep network-free tests as the primary gate |
| Community/Ecosystem | 7/10 | Internal repo, but public-neutral spec is readable | Avoid private Career/GStack context in repo docs |
| DX Measurement | 7/10 | Benchmark bundle has success fields; no explicit adaptation count | Defer run-scoped telemetry; use safe binding logs now |

Overall DX: `7/10` now, `8.5/10` after docs, actionable errors, and exact commands.

#### DX Implementation Checklist

- [ ] `tests/unit/test_llm_config.py` covers forced and non-forced `tool_choice`
- [ ] Single-model and fallback-disabled paths use the same capability policy
- [ ] Compatible variants preserve callbacks, model identity fields, and unrelated provider config
- [ ] Adaptation logs use only the approved allowlist
- [ ] Error messages include problem, cause, and fix
- [ ] `spec/external-services.md` documents the conflict and emergency fallback
- [ ] One-repetition diagnostic command is documented before full 3x2 benchmark
- [ ] Evidence docs are updated only with actual post-fix benchmark output

#### DX NOT In Scope

- Hosted playground, UI dashboard, or frontend DX changes.
- Public rename of env vars, API paths, health service ID, or LangSmith project.
- Run-scoped adaptation telemetry or benchmark-bundle adaptation counts.
- Provider registry, task-level reasoning router, or dedicated formatter model.

#### DX What Already Exists

- `README.md` has Quick Start, API list, and Talent fixture notes.
- `scripts/talent_value_gate_runner.py` already prints a completion object and
  writes a bundle with `benchmark_status`.
- `tests/unit/test_talent_value_gate_runner.py` already covers failure and
  secret-sanitization paths.
- `spec/external-services.md` is the right place for provider compatibility notes.

#### DX Dual Voices Consensus

| Dimension | Claude subagent | Codex voice | Consensus |
|---|---|---|---|
| Getting started < 5 min? | Unavailable: usage limit | Unavailable: usage limit | N/A, local review says partial |
| API/CLI naming guessable? | Unavailable | Unavailable | N/A, local review says mostly yes |
| Error messages actionable? | Unavailable | Unavailable | N/A, local review says gap |
| Docs findable and complete? | Unavailable | Unavailable | N/A, local review says gap |
| Upgrade path safe? | Unavailable | Unavailable | N/A, local review says safe if documented |
| Dev environment friction-free? | Unavailable | Unavailable | N/A, local review says acceptable |

#### DX Implementation Tasks

- [ ] **DX-T1 (P2, human: ~30min / CC: ~10min)** — Provider docs — Document forced tool-choice compatibility
  - Surfaced by: DX documentation pass — maintainers need to know when thinking is disabled and why
  - Files: `spec/external-services.md`
  - Verify: documentation diff contains no private Career or GStack context
- [ ] **DX-T2 (P2, human: ~30min / CC: ~10min)** — Error handling — Add actionable adaptation failure wording
  - Surfaced by: DX error-message pass — copy/adaptation failure should explain problem, cause, fix
  - Files: `agent/llm.py`, `tests/unit/test_llm_config.py`
  - Verify: focused unit test asserts safe message shape without provider payloads
- [ ] **DX-T3 (P2, human: ~20min / CC: ~5min)** — Benchmark docs — Document diagnostic success criteria
  - Surfaced by: DX measurement pass — success is `ready_for_human_review`, not absence of exception
  - Files: `README.md` or `docs/evidence/run-log.md` after actual run
  - Verify: docs name `benchmark_status` and `completion.ready_for_human_review`

#### DX Additional Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 14 | DX | Update provider docs for the compatibility rule | Auto-decided | Fight uncertainty | Maintainers should not reverse-engineer this from LangChain errors | Code-only fix |
| 15 | DX | Require actionable adaptation failure messages | Auto-decided | Completeness | A failed copy/bind path should tell the maintainer what to change | Raw provider/internal exception only |
| 16 | DX | Treat `LLM_THINKING_MODE=disabled` as emergency diagnostic only | Auto-decided | Preserve quality | Global disable unblocks but changes unrelated calls | Default global disable |
| 17 | DX | Document benchmark readiness fields | Auto-decided | Measurement | The runner already exposes exact success fields | Human interpretation of error disappearance |

### Cross-Phase Themes

| Theme | Phases | Confidence | Resolution |
|---|---|---:|---|
| Fallback-only is not the shared capability boundary | CEO, Eng | High | Resolved: implement shared/leaf capability boundary |
| Tool-choice semantics must be exact | CEO, Eng | High | Forced-choice predicate and matrix tests |
| Diagnostic success must prove artifacts, not just no error | CEO, Eng, DX | High | Require `ready_for_human_review=true` |
| Observability must not leak provider payloads | CEO, Eng, DX | High | Binding-level safe allowlist only |
| Documentation matters because this is provider-specific maintenance DX | Eng, DX | Medium | Update `spec/external-services.md` |

### Final Gate Summary

The user accepted option A on 2026-06-15. The implementation baseline is now the
shared/leaf `CapabilityAwareChatModel` boundary: all `create_llm_model()` return
paths must expose the same capability policy, including fallback-disabled and
primary-equals-fallback configurations.

The fallback-only approach is rejected. This plan may claim future
structured-output profiles are protected only after tests prove the shared
boundary covers every model construction path.

### Final Implementation Tasks

- [x] **T1 (P1, human: ~2h / CC: ~30min)** — LLM capability boundary — Resolve and implement shared adaptation boundary
  - Surfaced by: CEO + Eng — fallback-disabled paths bypass `FallbackChatModel`
  - Files: `agent/llm.py`, `tests/unit/test_llm_config.py`
  - Verify: single-model, fallback-disabled, and fallback-enabled paths all adapt forced choices
- [x] **T2 (P1, human: ~1h / CC: ~20min)** — Tool-choice semantics — Add exact forced-choice classifier
  - Surfaced by: CEO + Eng — `tool_choice is not None` disables thinking for non-forced choices
  - Files: `agent/llm.py`, `tests/unit/test_llm_config.py`
  - Verify: parameterized matrix for `None`, `False`, `"none"`, `"auto"`, `True`, `"any"`, `"required"`, tool name, and dict
- [x] **T3 (P1, human: ~1h / CC: ~20min)** — Compatible model variant — Disable only incompatible thinking fields without mutating originals
  - Surfaced by: Eng — nested provider config and callbacks must be preserved
  - Files: `agent/llm.py`, `tests/unit/test_llm_config.py`
  - Verify: copy-isolation and real `ChatOpenAI` no-network smoke
- [x] **T4 (P1, human: ~1h / CC: ~20min)** — Diagnostic gate — Run one-repetition Talent benchmark before 3x2
  - Surfaced by: CEO + Eng + DX — error disappearance is insufficient
  - Files: no code file required unless diagnostic fails
  - Verify: output has `benchmark_status=ready_for_human_review` and `completion.ready_for_human_review=true`
- [x] **T5 (P2, human: ~30min / CC: ~10min)** — Provider documentation — Explain compatibility behavior and emergency rollback
  - Surfaced by: DX — maintainers need problem/cause/fix in docs
  - Files: `spec/external-services.md`
  - Verify: docs mention forced tool choice, thinking mode, and `LLM_THINKING_MODE=disabled` as emergency-only
- [x] **T6 (P2, human: ~30min / CC: ~10min)** — Safe observability — Add binding-level adaptation log with allowlisted fields
  - Surfaced by: CEO + Eng — adaptation should be visible without leaking payloads
  - Files: `agent/llm.py`, `tests/unit/test_llm_config.py`
  - Verify: caplog test asserts event fields and absence of prompt/tool schema/provider payloads

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | clean | User Challenge accepted: use shared/leaf capability boundary |
| Codex Review | `/codex review` | Independent 2nd opinion | 2 | degraded | CEO and Eng Codex voices ran; DX Codex voice unavailable due usage limit |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | clean | Critical gap resolved by accepted shared-boundary baseline; test plan written |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | No UI or visual surface in this plan |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | clean | Local DX review completed; docs and error-message tasks remain implementation tasks |

- **CODEX:** CEO and Eng outside voices agreed that fallback-only implementation is too narrow and that diagnostic success must require valid artifacts.
- **CROSS-MODEL:** Independent reviewers converged on one architectural challenge: the fix must cover raw model return paths, not only `FallbackChatModel`.
- **VERDICT:** CEO + ENG + DX cleared for implementation with the accepted shared/leaf capability boundary.

NO UNRESOLVED DECISIONS
