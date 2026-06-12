# Decision Research Agent Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt `Decision Research Agent` as the public product name without breaking existing repository, API, deployment, or environment-variable integrations.

**Architecture:** Treat the new name as a presentation-layer brand. Keep `deep-search-agent` as the compatibility identifier until a separately approved migration changes repository paths, health contracts, environment variables, deployment resources, and historical references.

**Tech Stack:** Markdown, FastAPI, Python argparse, pytest

---

### Task 1: Lock the Naming Boundary

**Files:**
- Create: `docs/decisions/product-naming.md`

- [x] Record the public English name, Chinese interview description, compatibility identifiers, and deferred migration scope.
- [x] Verify the decision contains no claim that Talent Profile or durable HITL is complete.

### Task 2: Update Public Presentation Surfaces

**Files:**
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/README.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `api/server.py`
- Modify: `tools/deep_search_agent_tool.py`

- [x] Change visible titles and descriptions to `Decision Research Agent`.
- [x] Preserve `deep-search-agent` in the health `service` field, repository paths, environment variables, and historical documents.

### Task 3: Add Compatibility Regression Tests

**Files:**
- Modify: `tests/integration/test_api_endpoints.py`
- Modify: `tests/unit/test_deep_search_agent_tool.py`

- [x] Assert the OpenAPI/FastAPI title is `Decision Research Agent API`.
- [x] Assert CLI help uses `Decision Research Agent`.
- [x] Assert the health service identifier remains `deep-search-agent`.
- [x] Run focused tests, then the full backend suite and `git diff --check`.
