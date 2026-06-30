# Decision Research Agent Documentation

Decision Research Agent is a backend-and-CLI research service with a separately
built Agent Research Operations Console. LangChain is the Agent Framework, DeepAgents is the
research harness, LangGraph is the durable workflow runtime, LangSmith is
privacy-first tracing/evaluation, and the application database is business
authority.

## Tutorial

- [Getting Started](getting-started.md) — create a Python 3.11 environment,
  start the backend, verify health, run the Tool Client, and open Static Demo.

## How-to And Operations

- [Agent Integration](AGENT_INTEGRATION.md) — use the first-party Tool Client.
- [Demo Console](demo-console.md) — run Static Demo or the bounded local Live Backend flow.
- [Observability](observability.md) — configure privacy-first LangSmith traces.
- [Controlled Review](operations/controlled-review-workflow.md) — operate the review queue.
- [Durable HITL Feasibility](operations/durable-hitl-feasibility.md) — enable and verify the bounded workflow.
- [Evidence Verification](operations/evidence-verification-workflow.md) — operate append-only verification.
- [Real-Source Proof](operations/real-source-proof-workflow.md) — reproduce the bounded proof workflow.

## Reference

- [API Contract](reference/api-contract.md) — REST, WebSocket, authentication, and errors.
- [Data Models](reference/data-models.md) — run, Evidence, artifact, review, and publication records.
- [State Machines](reference/state-machines.md) — execution, delivery, review, and verification transitions.
- [Tool Registry](reference/tool-registry.md) — server-owned tool and Skill boundaries.
- [External Services](reference/external-services.md) — provider and storage dependencies.

## Explanation And Decisions

- [Architecture](architecture.md) — runtime layers, data flow, and deployment boundary.
- [Demo Console Design](../DESIGN.md) — operator-console visual and authority boundaries.
- [Product Requirements](prd.md) — product intent and current scope.
- [Framework And Runtime Boundaries](decisions/framework-runtime-boundaries.md) — framework ownership.
- [Run Identity Boundaries](decisions/run-identity-boundaries.md) — identity scopes.
- [Evidence Verification Authority](decisions/evidence-verification-authority.md) — immutable Evidence decisions.
- [Product Naming](decisions/product-naming.md) — canonical identity.
- [AI-Assisted Engineering](development/ai-assisted-engineering.md) — governed implementation workflow.
- [Superpowers Lifecycle](superpowers/README.md), the
  [Live Demo design](superpowers/specs/2026-06-30-react-demo-console-live-flow-design.md),
  and its [implementation plan](superpowers/plans/2026-06-30-react-demo-console-live-flow-implementation.md)
  — active public-neutral project planning.

## Evidence

- [Talent Hiring Signal Benchmark v1](../benchmarks/talent-hiring-signal-v1/README.md)
  — bounded profile and renderer gates.
- [Evidence Index](evidence/README.md) — current bounded evidence.
- [Durable HITL Gate Report](evidence/durable-hitl-gate-report.json) — 13-gate result artifact.
- [Real-Source Proof](evidence/real-source-proof.md) and
  [JSON report](evidence/real-source-proof.json) — bounded proof and limitations.

## Release

- [v0.1.0 Release Notes](releases/v0.1.0.md) — migration, rollback, and release gates.
- [Contributing](../CONTRIBUTING.md) — contributor setup and verification.

Completed implementation history is retained in Git. Current contracts live in
code, tests, ADRs, and the reference documentation above.
