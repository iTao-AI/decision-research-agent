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

LangSmith receives bounded metadata with inputs and outputs hidden by default.
Trace availability never changes business readiness, Evidence authority,
review resolution, publication, or delivery.

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
