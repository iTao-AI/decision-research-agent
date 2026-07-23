# Framework And Runtime Boundaries

## Decision

Decision Research Agent uses a layered runtime with an application-owned port:

```text
FastAPI
  -> ResearchExecutionService
  -> AgentHarness
  -> DeepAgentsHarness
  -> ExecutionOutcome
  -> application finalization and repositories
```

The layers have distinct responsibilities:

| Layer | Responsibility |
|---|---|
| LangChain | Agent construction, model abstraction, tools, Middleware, and structured output |
| DeepAgents | Research harness behavior, coordinator planning, named researcher delegation, run-scoped VFS, read-only Skills, tool filtering, and context management |
| LangGraph | Graph execution, streaming, checkpoint-compatible execution, interrupt, and resume |
| LangSmith | Privacy-first diagnostics and evaluation |
| Application services and repositories | ResearchRun lifecycle, EvidenceLedger, artifacts, review, verification, publication, and delivery authority |

`ResearchExecutionService` depends on the `AgentHarness` protocol rather than
DeepAgents graph state. `HarnessRequest`, `ResearchRuntimeContext`, and
`ExecutionOutcome` are application-owned contracts. Framework messages,
checkpoint payloads, virtual paths, and internal node names are not public or
database contracts.

## Harness And Filesystem Boundary

The generic profile uses a DeepAgents coordinator, three named compiled
researchers, a state-backed virtual workspace, and two checked-in read-only
Skills. The server owns the profile policy, permissions, tool allowlists, and
call budgets. Request data cannot widen them.

The Talent profile is deliberately narrower. It has no Skills, filesystem
tools, arbitrary host access, or delegation. Its findings and claims must bind
to current-run Evidence validated by application services.

VFS content is working context, not Evidence or business state. Only bounded
source tools can publish candidate Evidence into the application accumulator,
and only fenced finalization can persist it. Canonical artifacts are selected
by application policy rather than filenames, timestamps, or graph state.

## Durability And Authority

The application database is authoritative for run state, frozen Evidence,
artifacts, review decisions, verification decisions, publication revisions,
and delivery state. The separate LangGraph checkpoint database records only
the controlled review gate's execution position.

Generic research supports asynchronous bounded execution and durable terminal
results, but it does not promise exact model/tool-call resume after process
death. Controlled review is the current checkpoint-resumable path. Extending
durability to main research requires a separate design for idempotency,
side-effect replay, and tool re-execution.

Pre-execution dispatch reconciliation remains application-owned because the
commit-to-schedule gap occurs before DeepAgents, LangChain, or LangGraph is
invoked. The application database stores `run_dispatches_v1`, a core worker
claims private leases, and an atomic start fence advances dispatch, ResearchRun,
and initial segment together. Agent middleware was rejected for this role: it
cannot recover work that has not reached Agent invocation. LangGraph checkpoint
and LangSmith tracing likewise remain workflow-position and diagnostics
facilities, not application dispatch authority.

Durable failure causes reuse native bounded signals without moving authority.
The existing LangChain `ModelCallLimitMiddleware` and
`ToolCallLimitMiddleware` typed exceptions, LangGraph `GraphRecursionError`,
strict Pydantic models, FastAPI lifecycle, asyncio task ordering, and SQLite
transactions/fences remain the implementation primitives. Only the winning
application transaction converts an allowed signal into a durable public code;
framework error text and trace metadata are not persisted as the cause.

The feature adds no new Agent middleware or DeepAgents middleware. LangGraph
`TimeoutPolicy` is rejected because it limits a graph node attempt rather than
the whole application run. LangGraph checkpoint/store and LangSmith trace data
are also rejected as failure-cause business authority because they cannot join
the run, segment, Evidence, and cause in the same application transaction.

LangSmith receives bounded metadata with inputs and outputs hidden by default.
Trace availability never changes business readiness, Evidence authority,
review resolution, publication, or delivery.

The classic LangGraph stream adapter opts into `subgraphs=True` and validates
the locked namespace/payload tuple shape before dispatch. Unknown or malformed
nested output fails closed. Only completed `internet_search` `ToolMessage`
objects from an identified `network_search` subgraph reach the existing
Evidence extractor; other tool output, model text, reasoning, and summaries do
not acquire Evidence authority.

## Trade-offs

- An application-owned port adds an adapter boundary, but prevents framework
  state from leaking into persistence and public APIs.
- A run-scoped VFS supports planning and synthesis without making host paths or
  autonomous file writes part of the product contract.
- Named synchronous researchers constrain cost and operations at the expense
  of background parallelism.
- Separate application and checkpoint databases require reconciliation logic,
  but keep business facts independent of workflow position.
- Read-only Skills improve planning consistency but cannot define or override
  public contracts.

## Rejected Alternatives

- A hand-written shared context store was removed because DeepAgents task
  results and VFS cover working context while Evidence remains application
  owned.
- LangSmith as a ledger was rejected because diagnostics are neither durable
  business authority nor an acceptance gate.
- Unbounded runtime Skills were rejected because model-readable instructions
  must not widen tools, permissions, Evidence semantics, or delivery policy.
- First-version asynchronous subagents were deferred because they add remote
  graph operations and parallel model cost without a release requirement.
- UI-owned runtime behavior was rejected because future clients must consume
  canonical run, result, review, and verification contracts rather than define
  backend state.

## Consequences

Framework upgrades must preserve the harness compatibility tests, profile
boundaries, application-owned outcome contract, and release gates. Any change
that moves business authority into a framework store, trace, Skill, VFS, or UI
requires an explicit decision update.
