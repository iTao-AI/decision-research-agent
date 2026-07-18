# Decision Research Agent Documentation

Decision Research Agent is a backend-and-CLI research service with a separately
built Agent Research Operations Console. LangChain is the Agent Framework, DeepAgents is the
research harness, LangGraph is the durable workflow runtime, LangSmith is
privacy-first tracing/evaluation, and the application database is business
authority.

Use the repository README for a 30-second overview, the Architecture Deep Dive
for 3-minute technical depth, and the Demo Console or demo videos for fast
external evaluation of the public contract surface.

## Tutorial

- [Getting Started](getting-started.md) — create a Python 3.11 environment,
  start the backend, verify health, run the Tool Client, and open Static Demo.

## How-to And Operations

- [Agent Integration](AGENT_INTEGRATION.md) — use the first-party Tool Client.
- [Demo Console](demo-console.md) — run Static Demo, consume service-owned Live
  state, reconcile the same create intent, resume known runs with GET only, and
  understand the video demo boundary.
- [Observability](observability.md) — configure privacy-first LangSmith traces.
- [Secure Local Runtime](operations/secure-local-runtime.md) — operate the
  source-loopback and authenticated Compose launch boundaries, verify health
  and security settings, and preserve existing volumes during rollback.
- [Controlled Review](operations/controlled-review-workflow.md) — operate the review queue.
- [Durable HITL Feasibility](operations/durable-hitl-feasibility.md) — enable and verify the bounded workflow.
- [Evidence Verification](operations/evidence-verification-workflow.md) — operate append-only verification.
- [Real-Source Proof](operations/real-source-proof-workflow.md) — reproduce the bounded proof workflow.

## Reference

- [API Contract](reference/api-contract.md) — REST, WebSocket, authentication,
  errors, and the additive durable run failure-cause status projection.
- [Downstream Consumer Contract](reference/downstream-consumer-contract.md) — deterministic status, result, Evidence, fallback, and failure-handling proof.
- [Agent Evaluation Regression Gate](reference/agent-evaluation-regression-gate.md) — deterministic eight-case, six-evaluator release gate and baseline workflow.
- [Data Models](reference/data-models.md) — run, Evidence, artifact, review, and publication records.
- [State Machines](reference/state-machines.md) — execution, delivery, review, and verification transitions.
- [Tool Registry](reference/tool-registry.md) — server-owned tool and Skill boundaries.
- [External Services](reference/external-services.md) — provider and storage dependencies.

## Explanation And Decisions

- [Architecture Deep Dive](architecture.md) — runtime layers, authority boundaries, verification, and deployment separation.
- [Demo Console Design](../DESIGN.md) — operator-console visual and authority boundaries.
- [Product Requirements](prd.md) — product intent and current scope.
- [Framework And Runtime Boundaries](decisions/framework-runtime-boundaries.md) — framework ownership.
- [Run Identity Boundaries](decisions/run-identity-boundaries.md) — identity scopes.
- [Evidence Verification Authority](decisions/evidence-verification-authority.md) — immutable Evidence decisions.
- [Product Naming](decisions/product-naming.md) — canonical identity.
- [AI-Assisted Engineering](development/ai-assisted-engineering.md) — governed implementation workflow.
- [Superpowers Lifecycle](superpowers/README.md), the
  [Console Live Authority Closure design](superpowers/specs/2026-07-16-console-live-authority-closure-design.md),
  and its [implementation plan](superpowers/plans/2026-07-16-console-live-authority-closure-implementation.md)
  — approved public-neutral implementation record.
- [Live Demo design](superpowers/specs/2026-06-30-react-demo-console-live-flow-design.md)
  and its [implementation plan](superpowers/plans/2026-06-30-react-demo-console-live-flow-implementation.md)
  — earlier Console flow implementation record.

## Evidence

- [Talent Hiring Signal Benchmark v1](../benchmarks/talent-hiring-signal-v1/README.md)
  — bounded profile and renderer gates.
- [Evidence Index](evidence/README.md) — current bounded evidence.
- [Run Creation Idempotency Proof](evidence/run-creation-idempotency-v1.md) — deterministic lost-response identity reconciliation and limits.
- [Run Dispatch Reconciliation Proof](evidence/run-dispatch-reconciliation-v1.md) — deterministic committed pre-start recovery, migration safety, and explicit non-claims.
- [Durable Run Failure Cause Proof](evidence/run-failure-cause-v1.md) and
  [JSON report](evidence/run-failure-cause-v1.json) — deterministic 16-case
  production-path contract proof for the bounded terminal-cause projection.
- [Secure Local Runtime v1 Proof](evidence/secure-local-runtime-v1.md) and
  [JSON report](evidence/secure-local-runtime-v1.json) — deterministic 16-case
  production-path access and container-configuration evidence; real Docker
  runtime remains a separate required lane.
- [Agent Evaluation Report](evidence/agent-evaluation-regression-v1.md) and
  [JSON baseline](evidence/agent-evaluation-regression-v1.json) — deterministic
  contract regression evidence and limits.
- [Durable HITL Gate Report](evidence/durable-hitl-gate-report.json) — 13-gate result artifact.
- [Real-Source Proof](evidence/real-source-proof.md) and
  [JSON report](evidence/real-source-proof.json) — bounded proof and limitations.

## Release

- [v0.1.4 Release Notes](releases/v0.1.4.md) — current supported surface,
  including durable run failure causes and Console live authority closure,
  compatibility, rollback, verification, and explicit limits.
- [v0.1.3 Release Notes](releases/v0.1.3.md) — historical durable run
  dispatch reconciliation surface,
  including single-node durable run dispatch reconciliation, compatibility,
  rollback, verification, and explicit limits.
- [v0.1.2 Release Notes](releases/v0.1.2.md) — historical run-creation
  reliability and optional idempotency contract.
- [v0.1.1 Release Notes](releases/v0.1.1.md) — historical console,
  downstream-consumer and Agent evaluation contract gates.
- [v0.1.0 Release Notes](releases/v0.1.0.md) — migration, rollback, and release gates.
- [Contributing](../CONTRIBUTING.md) — contributor setup and verification.

Completed implementation history is retained in Git. Current contracts live in
code, tests, ADRs, and the reference documentation above.
