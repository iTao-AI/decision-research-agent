# DeepSeek Provider Protocol Closure Design

**Status:** Approved public-neutral design source for mechanical landing and
implementation planning.

## Summary

Decision Research Agent currently configures its default DeepSeek models through
LangChain's generic OpenAI provider path. That path can send requests to an
OpenAI-compatible endpoint, but it does not own DeepSeek's thinking-mode
tool-call protocol.

DeepSeek requires the `reasoning_content` returned with an assistant tool call
to be sent back with that assistant message in the next model request. The
current generic path does not preserve this round trip. The official
`langchain-deepseek` integration parses `reasoning_content` from normal and
streamed responses, but the inspected `1.1.0` release does not yet serialize
that field back into subsequent request messages.

The selected change is therefore:

1. add and pin the official `langchain-deepseek` integration;
2. route DeepSeek model identifiers through `ChatDeepSeek`, not
   `model_provider="openai"`;
3. add one narrow project-owned subclass that restores only the missing
   `reasoning_content` request round trip;
4. preserve the existing capability wrapper, primary/fallback behavior,
   budgets, prompts, tools, Agent harness, and application authority; and
5. verify the real `model -> tool -> model -> canonical finish` path without a
   live provider call.

This is a provider protocol correction, not a model-quality claim. It does not
prove that prior live failures had one exclusive cause, and it does not
authorize another provider-backed observation.

## Inspected Baseline

This design was finalized against:

- `main == origin/main == 7ffd6bdfddea53d2d0b3d4c4041bc0929b1ea464`;
- a clean primary checkout;
- a separate clean bounded-live evidence worktree at the same commit with no
  unique commits;
- `VERSION=0.1.5`;
- LangChain `1.3.10`, DeepAgents `0.6.11`, LangGraph `1.2.6`, and
  `langchain-openai` `1.3.2` in the locked dependency set;
- no `langchain-deepseek` dependency;
- default primary and fallback model identifiers
  `deepseek-v4-pro` and `deepseek-v4-flash`;
- `agent/llm.py::_model_kwargs` setting
  `model_provider="openai"` for every model;
- DeepSeek requests currently receiving credentials and endpoint configuration
  from `OPENAI_API_KEY` and `OPENAI_BASE_URL`;
- the existing `CapabilityAwareChatModel` preserving thinking for automatic
  tool selection and disabling thinking on an independent model copy when a
  forced tool choice is incompatible; and
- no committed bounded-live provider evidence.

The existing application authority remains coherent:

- LangChain owns model abstraction, tool binding, and middleware;
- DeepAgents owns the research harness and delegated researcher execution;
- LangGraph owns graph execution;
- LangSmith is optional diagnostic tracing; and
- application services and the application database own ResearchRun, Evidence,
  artifacts, failure cause, review, publication, and delivery.

This change does not move any of those boundaries.

## Framework And Provider Findings

### The generic OpenAI path is the wrong owner for DeepSeek-only semantics

LangChain documents `ChatOpenAI` for the official OpenAI API and recommends a
provider-specific integration when a provider exposes non-standard response or
request fields. DeepSeek thinking mode uses the non-standard
`reasoning_content` field.

The generic path is useful for OpenAI-compatible providers whose behavior fits
the OpenAI message contract. It must remain available for non-DeepSeek model
identifiers. It must not be the default implementation for DeepSeek models.

### The official DeepSeek integration is necessary but not sufficient

`langchain-deepseek` `1.1.0` provides `ChatDeepSeek` with native support for:

- synchronous and asynchronous invocation;
- streaming;
- tool calling;
- structured output; and
- extraction of `reasoning_content` from full and streamed responses into
  LangChain message metadata.

The inspected request serialization path does not put that metadata back into
the outgoing assistant message. Multiple upstream proposals have discussed
this gap, but it is not closed in the selected release.

Using `ChatDeepSeek` without a project-owned round-trip adapter would therefore
improve provider ownership while leaving the demonstrated multi-turn tool
protocol incomplete.

### The missing field is protocol state, not business authority

`reasoning_content` is provider conversation state required to continue a
thinking-mode tool-call exchange. It is not:

- Evidence;
- a canonical artifact;
- an application failure cause;
- a review decision;
- a publication fact;
- a delivery gate; or
- a public diagnostic payload.

The adapter may transport the field between model turns. It must not persist,
log, publish, hash, evaluate, or promote it into application authority.

## Goals

The implementation must:

1. route every configured DeepSeek model through the official
   `ChatDeepSeek` integration;
2. preserve the exact `reasoning_content` associated with every historical
   thinking-mode assistant tool-call message;
3. inject that value into the corresponding serialized assistant message
   before transport;
4. fail closed before transport when a thinking-mode assistant tool-call
   message is missing a valid non-empty `reasoning_content`;
5. support synchronous, asynchronous, streaming, and non-streaming message
   histories;
6. preserve automatic tool selection with thinking enabled;
7. preserve the existing forced-tool-choice compatibility behavior that
   disables thinking on a copied model;
8. route both the default primary and fallback DeepSeek models through the
   same provider protocol implementation;
9. retain the existing non-DeepSeek OpenAI-compatible path;
10. retain callback, model-role, structured-output, fallback, and DeepAgents
    integration behavior;
11. keep credentials and endpoint aliases backward compatible; and
12. make the provider choice and protocol behavior executable through
    provider-free tests.

## Non-Goals

This change does not:

- change prompts, researcher roles, search policy, or domain behavior;
- increase model, tool, task, recursion, or wall-clock budgets;
- change primary or fallback model identifiers;
- change provider retry policy;
- add a live provider run;
- publish live evidence;
- modify the REST API, database, ResearchRun, Evidence, artifact, review,
  publication, or delivery contracts;
- change the application failure taxonomy or operator diagnostic receipt
  schemas;
- make LangSmith an authority or require LangSmith for correctness;
- remove the existing `OPENAI_API_KEY` or `OPENAI_BASE_URL` aliases;
- migrate secrets automatically;
- change `VERSION`, release metadata, or release claims;
- change hosted CI workflow definitions unless a dependency-install issue
  proves a narrowly necessary update; or
- claim that the official integration or this adapter proves provider quality,
  cost, correctness, or production readiness.

## Selected Architecture

```text
create_llm_model
  |
  +-- DeepSeek model identifier
  |     |
  |     +-- DeepSeekThinkingChatModel
  |           |
  |           +-- ChatDeepSeek
  |           +-- reasoning_content request round trip only
  |
  +-- non-DeepSeek model identifier
        |
        +-- existing OpenAI-compatible initialization

leaf model
  -> CapabilityAwareChatModel
  -> FallbackChatModel when configured
  -> DeepAgents / LangChain Agent runtime
```

The provider-specific leaf model owns DeepSeek protocol compatibility. The
capability wrapper continues to own the already-approved
thinking-versus-forced-tool-choice adaptation. The fallback wrapper continues
to own primary/fallback invocation behavior.

Provider logic must not move into profile prompts, researcher definitions,
tool implementations, Evidence projection, result finalization, or the public
API.

## Dependency Decision

Add the official integration as a direct dependency and exact locked
constraint:

```text
langchain-deepseek>=1.1.0
langchain-deepseek==1.1.0
```

The implementation must follow the repository's existing distinction between
direct requirements and exact constraints.

The inspected `1.1.0` wheel has SHA-256:

```text
14813cb413a97a5cce95118da253cfd64dce50537b7381b7c5d0ecf11d2a7032
```

Its declared compatibility with `langchain-core` and `langchain-openai` fits
the current locked dependency family. The implementation must still run the
repository's dependency and locked-environment gates; this design does not
substitute metadata inspection for an installed verification.

## Provider Selection

### DeepSeek model detection

The provider path is selected from the configured model identifier, not from a
credential variable or endpoint hostname.

At minimum, the current DeepSeek family includes identifiers beginning with:

```text
deepseek-
```

The implementation may use a small explicit helper for this detection. It must
not inspect secrets, perform network discovery, or infer provider identity from
an arbitrary base URL.

Both the primary and fallback are selected independently. A DeepSeek primary
and DeepSeek fallback must each use the official integration and the same
protocol adapter. A non-DeepSeek override must continue to use the existing
OpenAI-compatible path.

### No silent compatibility fallback

If the official DeepSeek integration cannot be imported or initialized for a
DeepSeek identifier, initialization fails. The code must not silently reroute
that DeepSeek model through `ChatOpenAI`.

Application-level primary-to-fallback behavior remains unchanged after both
leaf models initialize.

## Configuration Contract

DeepSeek models use the following precedence:

| Setting | Preferred | Backward-compatible fallback |
|---|---|---|
| API key | `DEEPSEEK_API_KEY` | `OPENAI_API_KEY` |
| Base URL | `DEEPSEEK_API_BASE` | `OPENAI_BASE_URL` |

Rules:

1. a non-empty DeepSeek-specific value wins;
2. if it is absent, the existing OpenAI-compatible alias is accepted;
3. values are passed directly to the official integration using its supported
   constructor fields;
4. no value is logged, hashed, copied into public artifacts, or persisted;
5. `.env.example` and provider documentation describe both the preferred names
   and the compatibility aliases; and
6. non-DeepSeek models continue to use `OPENAI_API_KEY` and
   `OPENAI_BASE_URL`.

This precedence allows existing local installations to continue working while
making the provider-specific contract explicit. Removing the compatibility
aliases requires a later migration with its own release decision.

## DeepSeek Thinking Adapter

### Ownership

Add one small module, expected to be:

```text
agent/deepseek_chat_model.py
```

The module defines a narrow subclass, expected to be named:

```text
DeepSeekThinkingChatModel
```

It subclasses `langchain_deepseek.ChatDeepSeek`. It must not reimplement the
HTTP client, response parsing, streaming, tool binding, structured output, or
async behavior already owned by `ChatDeepSeek`.

### Request serialization

The subclass overrides only the narrow request-payload boundary needed for the
missing round trip.

Conceptually:

1. call the official superclass request serializer;
2. obtain the original ordered LangChain message history used for that
   request;
3. align original assistant messages with the serialized assistant messages;
4. determine whether thinking is enabled for the effective model instance;
5. for each historical assistant message that contains tool calls:
   - read `additional_kwargs["reasoning_content"]`;
   - require it to be a non-empty string when thinking is enabled; and
   - inject the exact value as top-level `reasoning_content` on the matching
     serialized assistant message;
6. return the otherwise unchanged official payload.

The adapter must preserve every qualifying historical assistant tool-call
message, not only the most recent one.

### Alignment invariants

The adapter must fail closed before transport if it cannot prove a one-to-one,
order-preserving mapping between a qualifying original assistant message and
its serialized assistant message.

It must not:

- match messages by reasoning text;
- infer a missing field from content;
- reuse one message's reasoning for another;
- inject an empty string as synthetic protocol state;
- mutate the caller's original message objects;
- mutate a shared model instance during request preparation; or
- alter non-assistant messages, assistant messages without tool calls, tool
  results, tool arguments, or normal content.

### Thinking-disabled behavior

When thinking is disabled on the effective leaf model, the adapter does not
require or inject `reasoning_content`.

This preserves the current `CapabilityAwareChatModel` behavior:

- `tool_choice=None`, `auto`, or equivalent automatic selection keeps thinking
  enabled;
- forced tool selection creates an independent model copy with thinking
  disabled; and
- the original model configuration remains unchanged for concurrent or later
  calls.

### Streaming

The official integration remains responsible for extracting
`reasoning_content` from streamed chunks and aggregating the assistant message.
The adapter is responsible only for recognizing the aggregated message's
metadata when it later appears in request history.

No separate streaming transport implementation is approved.

## Failure Behavior

Introduce a stable internal exception or validation error for a missing or
invalid thinking round trip. It must:

- occur before the HTTP transport is called;
- identify only a bounded protocol category;
- avoid including raw reasoning, message content, tool arguments, serialized
  payload, endpoint credentials, or secrets; and
- remain an internal provider-adapter failure unless an existing application
  boundary maps it to an already-approved public cause.

This design does not add a public error code or database field.

The existing primary/fallback wrapper may invoke the configured fallback after
a primary invocation failure according to current behavior. A fallback
DeepSeek model uses the same strict protocol validation and must not weaken the
failure boundary.

## Observability And Privacy

Permitted logs and trace metadata are limited to bounded facts such as:

- provider family;
- model role;
- thinking enabled or disabled;
- protocol validation category; and
- existing invocation/fallback metadata.

Prohibited observability includes:

- raw `reasoning_content`;
- message content;
- serialized request bodies;
- tool arguments or tool results;
- credentials or secret-derived values; and
- unbounded exception text containing provider payloads.

LangSmith remains optional and privacy-first. Trace availability cannot change
model routing, protocol validation, application state, Evidence, review,
publication, or delivery.

## Compatibility

### Preserved behavior

- default model identifiers remain unchanged;
- primary/fallback structure remains unchanged;
- callbacks remain attached to both leaf models and wrappers;
- `model_role` remains available;
- structured output remains framework-native;
- automatic tool selection retains thinking mode;
- forced tool selection retains the existing thinking-disabled copy;
- non-DeepSeek model overrides retain the OpenAI-compatible path;
- existing OpenAI-compatible credential names remain accepted for DeepSeek;
- application authority and public contracts remain unchanged; and
- provider-free CI remains credential-free and network-free during tests.

### Intentional behavior change

- a DeepSeek model identifier no longer initializes as `ChatOpenAI`;
- thinking-mode assistant tool calls without valid `reasoning_content` fail
  before the next provider request;
- valid reasoning metadata is restored to the exact serialized assistant
  message; and
- installing the locked backend environment includes
  `langchain-deepseek==1.1.0`.

## TDD And Acceptance Tests

### Required RED evidence

Before implementation, tests must demonstrate the current gaps:

1. default DeepSeek primary and fallback resolve through the OpenAI provider;
2. a non-streamed DeepSeek assistant tool-call response contains parsed
   `reasoning_content`, but the next request omits it;
3. an aggregated streamed response contains parsed reasoning metadata, but the
   next request omits it;
4. multiple historical assistant tool-call messages do not all regain their
   own reasoning values;
5. a thinking-enabled assistant tool-call message with missing or invalid
   reasoning reaches or would reach transport; and
6. provider identity is not independently enforced for primary and fallback.

### Required GREEN matrix

The completed change must cover:

#### Provider selection

- default primary is an official DeepSeek leaf;
- default fallback is an official DeepSeek leaf;
- each leaf is wrapped by the existing capability wrapper;
- the existing fallback wrapper is retained;
- a non-DeepSeek override remains on the OpenAI-compatible path; and
- a missing official integration fails rather than silently choosing OpenAI.

#### Configuration

- `DEEPSEEK_API_KEY` wins over `OPENAI_API_KEY`;
- `DEEPSEEK_API_BASE` wins over `OPENAI_BASE_URL`;
- each compatibility alias still works when its preferred variable is absent;
- no configured secret appears in logs or exceptions; and
- primary and fallback receive equivalent provider configuration.

#### Non-streamed protocol

- one assistant tool-call message restores exact reasoning;
- two or more historical assistant tool-call messages each restore their own
  exact reasoning;
- assistant content, tool calls, tool results, and other payload fields remain
  unchanged;
- the original LangChain messages remain unchanged;
- missing, empty, or non-string reasoning fails before transport; and
- thinking-disabled requests do not require or inject the field.

#### Streamed protocol

- streamed reasoning chunks aggregate through the official integration;
- the aggregated assistant tool-call message restores exact reasoning on the
  next request;
- asynchronous streaming follows the same contract; and
- streaming tests do not replace the official streaming implementation.

#### Tool binding and wrappers

- automatic tool choice preserves thinking;
- forced tool choice disables thinking only on an independent copy;
- the original model remains thinking-enabled;
- callbacks, model role, profile metadata, and structured output remain
  available;
- a primary invocation failure still reaches the configured fallback; and
- fallback protocol validation remains strict.

#### Real framework composition

Using the locked LangChain and DeepAgents versions with a fake transport, a
real `create_deep_agent` composition must complete:

```text
model response with tool call and reasoning
  -> tool result
  -> next model request containing exact reasoning_content
  -> canonical completion
```

The test must cover at least one synchronous path and one asynchronous or
streaming path. It must not use a live provider or credential.

#### Privacy

- log capture contains no reasoning text;
- log capture contains no tool argument or result payload;
- exception text contains no serialized request or secret; and
- provider-free tests do not read a production credential source.

## Expected Implementation Surface

Expected files include:

- `agent/deepseek_chat_model.py`;
- `agent/llm.py`;
- `requirements.txt`;
- `constraints.txt`;
- `tests/unit/test_deepseek_chat_model.py`;
- `tests/unit/test_llm_config.py`;
- one existing DeepAgents/harness integration test module;
- `.env.example`;
- the directly affected provider/reference documentation;
- `CHANGELOG.md`; and
- documentation or dependency contract tests required by existing repository
  policy.

This is an expected surface, not permission for unrelated cleanup. If the
implementation requires API, database, Evidence, delivery, migration, CI,
frontend, version, release, prompt, tool-policy, or broad harness changes, it
must stop and report the discovered expansion before editing those areas.

## Verification

Implementation verification must include:

1. the focused DeepSeek adapter and LLM configuration tests;
2. the locked Python `3.11` provider/profile/harness matrix;
3. the complete provider-free backend suite in the repository-authoritative
   environment;
4. the real fake-transport DeepAgents composition tests;
5. dependency resolution, exact constraint, and package-integrity checks;
6. the required Docker authority lane because the backend dependency set
   changes;
7. current deterministic Agent evaluation, downstream consumer, canonical
   identity, presentation, and provider-free proof gates;
8. `git diff --check`;
9. private-marker, credential-value, raw-reasoning, and unfinished-marker
   scans; and
10. a prohibited-diff audit for API, database, Evidence, delivery, migrations,
    frontend, CI, `VERSION`, release metadata, and live evidence.

Frontend tests are required only if an existing shared contract forces a
frontend change. This design does not expect one.

No live provider, credential, model, search, cost, or evidence publication is
part of this verification.

## Delivery Sequence

### PR A — DeepSeek provider protocol closure

Implement this design as one reviewable provider-boundary change:

- official integration and dependency pin;
- explicit provider selection;
- credential/base-URL precedence;
- narrow reasoning round-trip subclass;
- wrapper and DeepAgents compatibility tests;
- public-neutral provider documentation; and
- full provider-free and Docker verification.

The implementation is primarily serial because provider creation, request
serialization, wrapper behavior, dependency metadata, and framework
integration share the same contract. Parallel write lanes are not required.
The execution window may use one bounded, read-only targeted reviewer after
implementation if the integrated diff justifies it.

### PR B — Generic research domain and search policy

A later separately approved change may review generic researcher prompts,
source-selection policy, search behavior, and stopping criteria. It must not be
folded into PR A.

PR B is required before another bounded live observation only if its approved
review finds a concrete runtime behavior blocker. Provider protocol closure
must land first so later behavior is evaluated through the correct provider
integration.

### Live observation

Another bounded live observation requires:

1. PR A merged and closed out;
2. any separately approved prerequisite PR B merged and closed out;
3. fresh provider-free and Docker verification;
4. a clean exact main commit;
5. explicit credential and one-shot provider authorization; and
6. the existing bounded cleanup, diagnostic, Evidence, and non-claim gates.

No live attempt is authorized by this design.

## Rollback And Upstream Removal

### Operational rollback

If thinking-mode tool calling remains incompatible after this change, the
existing configuration can explicitly disable thinking for the affected run.
That is a capability reduction, not proof of protocol correctness, and must be
reported as such.

DeepSeek identifiers must not be silently routed back through the generic
OpenAI provider as a rollback.

### Removing the project-owned subclass

The subclass may be removed only after a future locked
`langchain-deepseek` release is shown through source inspection and executable
tests to:

- serialize `reasoning_content` for historical assistant tool-call messages;
- preserve streamed and non-streamed behavior;
- fail safely on incomplete thinking-mode history; and
- pass the same DeepAgents composition matrix.

At that point, DRA should prefer the complete official behavior and delete the
redundant override in a focused dependency upgrade. Until then, the adapter is
an explicit compatibility boundary, not a permanent fork of the provider
integration.

## Public Claims And Non-Claims

After implementation, the repository may state that:

- DeepSeek model identifiers use the official LangChain DeepSeek integration;
- DRA preserves DeepSeek thinking-mode reasoning state across tool-call turns
  through a bounded compatibility adapter;
- the behavior is covered by provider-free framework composition tests; and
- application authority remains outside provider and framework message state.

It must not state that:

- a live provider evaluation passed;
- the provider returned high-quality or correct research;
- a consumer accepted live evidence;
- the change reduced cost or latency;
- the change alone resolved every prior live failure;
- the project is production deployed;
- reasoning content is Evidence or an application fact; or
- a version containing this change has been released before the corresponding
  tag and public Release exist.

## References

- LangChain DeepSeek integration:
  <https://docs.langchain.com/oss/python/integrations/chat/deepseek>
- LangChain chat model and provider integration guidance:
  <https://docs.langchain.com/oss/python/integrations/chat>
- DeepSeek thinking-mode tool-call protocol:
  <https://api-docs.deepseek.com/guides/thinking_mode/>
- `langchain-deepseek` package:
  <https://pypi.org/project/langchain-deepseek/>
- LangChain upstream discussion of reasoning-content request serialization:
  <https://github.com/langchain-ai/langchain/pull/34177>
  <https://github.com/langchain-ai/langchain/pull/34438>
  <https://github.com/langchain-ai/langchain/pull/34516>
  <https://github.com/langchain-ai/langchain/pull/35094>
