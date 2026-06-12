# Product Naming

## Decision

- Public English product name: **Decision Research Agent**
- Repository and compatibility identifier: `deep-search-agent`

`Decision Research Agent` describes the intended product value: an agent that gathers
source-backed research and turns it into decision-ready briefs.

## Current Evidence Boundary

The name is supported by the implemented agent runtime, Evidence lifecycle,
EvidenceLedger, ResearchRun identity model, and deterministic DecisionBrief contracts.
It does not claim that every source is verified or that the system makes decisions for
users.

The Talent Hiring Signal value gate, end-to-end restricted Talent agent, P0B2 isolation,
and durable HITL remain incomplete. Public descriptions must not imply otherwise.

## Compatibility Boundary

Keep these identifiers unchanged until a separately approved migration:

- Repository and local directory name: `deep-search-agent`
- Health contract: `"service": "deep-search-agent"`
- Environment variables such as `DEEP_SEARCH_AGENT_URL`
- Existing API paths, Docker resources, LangSmith project names, and historical docs

This phase changes presentation-layer branding only.
