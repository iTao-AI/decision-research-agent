<!-- /autoplan restore point: /Users/mac/.gstack/projects/iTao-AI-decision-research-agent/codex-technical-identifier-migration-autoplan-restore-20260618-123418.md -->
# Decision Research Agent Technical Identifier Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `decision-research-agent` the canonical technical identity for new configuration and tooling while preserving bounded compatibility for existing `deep-search-agent` consumers.

**Architecture:** Introduce one canonical-first environment resolver for server runtime modules, keep a small equivalent resolver inside the standalone Tool Client, and move Tool Client implementation to the canonical module while retaining a thin legacy shim. Preserve REST/WebSocket routes, persisted identities, Docker resources, and the complete `/health` response; publish the canonical identity through configuration, tooling, API title, and current documentation.

**Tech Stack:** Python 3.11, FastAPI, pytest, argparse, Docker Compose, LangSmith environment configuration, Markdown.

**Source Spec:** `docs/superpowers/specs/2026-06-18-technical-identifier-migration-design.md`

---

## Delivery Boundaries

**In scope:** canonical environment variables, legacy aliases with value-free `FutureWarning`, canonical Tool Client module plus shim, exact health-contract preservation, current documentation, LangSmith default project, rollback instructions, focused regression tests.

**Not in scope:** route renames, SQLite/table/ID changes, Docker service or volume renames, benchmark/profile ID changes, historical artifact rewrites, output-template work, P1B HITL, Skills, Async Subagent, UI changes, changing any `/health` response field, production usage telemetry, or legacy-alias removal.

## File Structure

| Responsibility | Files |
|---|---|
| Shared runtime env compatibility | Create `agent/runtime_env.py`; modify `agent/main_agent.py`, `agent/talent_runtime.py`, `tools/provided_aggregate.py` |
| Benchmark process-state isolation | Modify `scripts/talent_value_gate_runner.py` |
| Canonical Tool Client and legacy shim | Create `tools/decision_research_agent_tool.py`; replace `tools/deep_search_agent_tool.py` with shim |
| Exact runtime identity compatibility | Verify `api/server.py`; retain the exact response assertion in `tests/unit/test_health_endpoint.py` |
| Contract tests | Create `tests/unit/test_runtime_env.py`, `tests/unit/test_decision_research_agent_tool.py`; modify `tests/unit/test_deep_search_agent_tool.py`, `tests/unit/test_provided_aggregate.py`, `tests/unit/test_profile_registry.py`, `tests/unit/test_talent_value_gate_runner.py` |
| Current documentation and examples | Modify only files with active stale identifiers plus the source spec corrected by this review: `.env.example`, `README.md`, `README_CN.md`, `CHANGELOG.md`, `docs/README.md`, `docs/AGENT_INTEGRATION.md`, `docs/observability.md`, `docs/decisions/product-naming.md`, `docs/superpowers/specs/2026-06-18-technical-identifier-migration-design.md`, `spec/api-contract.md` |

### Task 1: Add Canonical-First Runtime Environment Resolution

**Files:**
- Create: `agent/runtime_env.py`
- Create: `tests/unit/test_runtime_env.py`

- [x] **Step 1: Write failing precedence and warning tests**

```python
from concurrent.futures import ThreadPoolExecutor
import warnings

from agent import runtime_env


def test_canonical_value_wins_even_when_empty(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_API_KEY", "legacy-secret")

    assert runtime_env.resolve_env(
        "DECISION_RESEARCH_AGENT_API_KEY",
        "DEEP_SEARCH_AGENT_API_KEY",
    ) == ""


def test_canonical_value_warns_when_legacy_key_is_also_present(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_URL", "https://canonical.invalid")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL"
        )

    assert value == "https://canonical.invalid"
    assert len(caught) == 1
    assert "ignored" in str(caught[0].message)
    assert "canonical.invalid" not in str(caught[0].message)
    assert "legacy.invalid" not in str(caught[0].message)


def test_legacy_value_warns_once_without_value(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL"
        )
        second = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL"
        )

    assert first == second == "https://legacy.example.invalid"
    assert len(caught) == 1
    assert "DEEP_SEARCH_AGENT_URL" in str(caught[0].message)
    assert "DECISION_RESEARCH_AGENT_URL" in str(caught[0].message)
    assert "legacy.example.invalid" not in str(caught[0].message)


def test_warning_filter_cannot_break_legacy_resolution(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        assert runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL"
        ) == "https://legacy.example.invalid"


def test_concurrent_legacy_resolution_warns_once(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(
                pool.map(
                    lambda _: runtime_env.resolve_env(
                        "DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL"
                    ),
                    range(32),
                )
            )

    assert set(values) == {"https://legacy.example.invalid"}
    assert len(caught) == 1
```

- [x] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/unit/test_runtime_env.py -q`

Expected: FAIL because `agent.runtime_env` does not exist.

- [x] **Step 3: Implement the thread-safe resolver**

```python
"""Canonical-first environment compatibility for runtime configuration."""
from __future__ import annotations

import os
from threading import RLock
import warnings

_MISSING = object()
_WARNED_LEGACY_KEYS: set[str] = set()
_WARNING_LOCK = RLock()


def resolve_env(
    canonical_key: str,
    legacy_key: str,
    *,
    default: str | None = None,
) -> str | None:
    canonical = os.environ.get(canonical_key, _MISSING)
    if canonical is not _MISSING:
        if legacy_key in os.environ:
            _warn_once(
                legacy_key,
                f"{legacy_key} is deprecated and ignored because {canonical_key} is set",
            )
        return canonical

    legacy = os.environ.get(legacy_key, _MISSING)
    if legacy is _MISSING:
        return default

    _warn_once(legacy_key, f"{legacy_key} is deprecated; use {canonical_key}")
    return legacy


def _warn_once(legacy_key: str, message: str) -> None:
    with _WARNING_LOCK:
        if legacy_key in _WARNED_LEGACY_KEYS:
            return
        try:
            warnings.warn(message, FutureWarning, stacklevel=3)
        except FutureWarning:
            # Deprecation visibility must not turn legacy configuration into
            # a startup failure under PYTHONWARNINGS=error.
            pass
        finally:
            _WARNED_LEGACY_KEYS.add(legacy_key)


def _reset_warning_state_for_tests() -> None:
    """Test-only reset; production code must never call this helper."""
    with _WARNING_LOCK:
        _WARNED_LEGACY_KEYS.clear()
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/unit/test_runtime_env.py -q`

Expected: PASS with canonical precedence, empty-value protection, default fallback, a visible warning when a legacy key is used or ignored, and at most one value-free warning per legacy key per resolver boundary. The server resolver and standalone Tool Client resolver do not promise cross-module deduplication if imported into the same process.

- [x] **Step 5: Commit the resolver**

```bash
git add agent/runtime_env.py tests/unit/test_runtime_env.py
git commit -m "feat(config): add canonical runtime env resolver"
```

### Task 2: Migrate Runtime Consumers Without Changing Safe Defaults

**Files:**
- Modify: `agent/main_agent.py:146-154`
- Modify: `agent/talent_runtime.py:1-20`
- Modify: `tools/provided_aggregate.py:24-31`
- Modify: `tests/unit/test_provided_aggregate.py`
- Modify: `tests/unit/test_profile_registry.py`
- Modify: `tests/integration/test_evidence_lifecycle.py`
- Test: `tests/unit/test_runtime_env.py`

- [x] **Step 1: Add failing consumer tests**

Add tests proving:

```python
def test_canonical_fixture_flag_overrides_legacy_false(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "true")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "false")
    # Invoke the declared aggregate with the existing context setup.
    # Assert the provider reaches fixture validation instead of returning
    # provided_aggregate_disabled.


def test_canonical_talent_recursion_limit_overrides_legacy(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT", "41")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")

    from agent.talent_runtime import talent_recursion_limit

    assert talent_recursion_limit() == 41
```

Also parameterize invalid canonical recursion values (`""`, `"invalid"`, `"0"`, `"-1"`) and assert `DEFAULT_TALENT_RECURSION_LIMIT`; a conflicting valid legacy value must not be consulted.

Convert one existing Talent fixture subprocess in `tests/integration/test_evidence_lifecycle.py` to the canonical fixture key so the full preload path proves canonical operation. Keep at least one existing subprocess on the legacy key as an end-to-end compatibility regression; do not mechanically migrate every test fixture.

Lock the per-consumer empty-value contract:

| Setting | Empty canonical value | Invalid canonical value | Legacy consulted? |
|---|---|---|---|
| API key | Explicit tombstone; no auth header | N/A | No |
| URL | Use `ToolConfig.base_url` | Empty/whitespace uses default | No |
| Timeout | Use `ToolConfig.timeout_seconds` | Non-numeric or non-positive uses default | No |
| Benchmark fixture flag | Disabled because only `true` enables it | Disabled | No |
| Talent recursion limit | Use `DEFAULT_TALENT_RECURSION_LIMIT` | Non-numeric or non-positive uses default | No |

- [x] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/unit/test_runtime_env.py tests/unit/test_provided_aggregate.py tests/unit/test_profile_registry.py -q`

Expected: FAIL because consumers still read only `DEEP_SEARCH_AGENT_*`.

- [x] **Step 3: Route runtime reads through `resolve_env`**

Use these exact key pairs:

```python
resolve_env(
    "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
    "DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
    default="",
)

resolve_env(
    "DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT",
    "DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT",
)
```

Keep the existing boolean comparison (`.lower() == "true"`) and recursion parsing. Invalid canonical numeric values continue to use the safe default and never fall through to the legacy value.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m pytest tests/unit/test_runtime_env.py tests/unit/test_provided_aggregate.py tests/unit/test_profile_registry.py tests/integration/test_evidence_lifecycle.py -q`

Expected: PASS; legacy-only tests emit `FutureWarning` without exposing values.

- [x] **Step 5: Commit runtime consumers**

```bash
git add agent/main_agent.py agent/talent_runtime.py tools/provided_aggregate.py tests/unit/test_runtime_env.py tests/unit/test_provided_aggregate.py tests/unit/test_profile_registry.py tests/integration/test_evidence_lifecycle.py
git commit -m "feat(config): migrate runtime identifiers with aliases"
```

### Task 3: Isolate the Canonical Benchmark Fixture Override

**Files:**
- Modify: `scripts/talent_value_gate_runner.py:493-596`
- Modify: `tests/unit/test_talent_value_gate_runner.py:665-692`

- [x] **Step 1: Write failing restoration tests**

```python
def test_run_value_gate_restores_canonical_fixture_setting_after_success(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "false")
    # Run one pair with the existing fake agent runner.
    # Assert generic observes "false", Talent observes "true", and the process
    # environment is restored to "false" afterward.


def test_run_value_gate_removes_temporary_canonical_fixture_setting_after_failure(monkeypatch):
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", raising=False
    )
    # Make the Talent fake runner raise RuntimeError.
    # Assert the bundle records runner_exception and the canonical key is absent.
```

- [x] **Step 2: Run the runner tests and verify RED**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: FAIL because the runner mutates only `DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES`.

- [x] **Step 3: Switch the temporary override to the canonical key**

Define one module constant:

```python
_BENCHMARK_FIXTURE_ENV = "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"
```

Capture the prior canonical value before each profile, set it to `"true"` only for Talent, and restore or remove it in the existing inner `finally`. Do not modify the legacy key. This ensures the canonical override wins during Talent execution and no process state leaks after success, timeout, or exception.

Keep the operational contract explicit: `run_value_gate()` is process-global and must not be invoked concurrently in the same process because `os.environ` cannot provide run-scoped isolation. Do not add a lock or process manager in this migration PR; document exclusive execution and keep the CLI sequential.

- [x] **Step 4: Run the runner tests and verify GREEN**

Run: `python -m pytest tests/unit/test_talent_value_gate_runner.py -q`

Expected: PASS, including both restoration paths and existing timeout continuation behavior.

- [x] **Step 5: Commit benchmark isolation**

```bash
git add scripts/talent_value_gate_runner.py tests/unit/test_talent_value_gate_runner.py
git commit -m "fix(benchmark): isolate canonical fixture override"
```

### Task 4: Move the Tool Client to the Canonical Module

**Files:**
- Create: `tools/decision_research_agent_tool.py`
- Modify: `tools/deep_search_agent_tool.py`
- Create: `tests/unit/test_decision_research_agent_tool.py`
- Modify: `tests/unit/test_deep_search_agent_tool.py`

- [x] **Step 1: Move existing behavior tests to the canonical import**

Copy the behavioral coverage from `tests/unit/test_deep_search_agent_tool.py` into `tests/unit/test_decision_research_agent_tool.py` and change the import to:

```python
from tools import decision_research_agent_tool as tool
```

Add canonical/legacy precedence tests for URL, API key, and timeout. For the API key test, set canonical to an empty string and legacy to `"legacy-secret"`; assert `ToolConfig.api_key == ""` and no output or warning contains the secret.

Also test the variable-specific empty semantics from Task 2 and assert that canonical plus legacy emits a value-free warning stating that the legacy key is ignored.

Retain the existing `doctor` coverage and add an exact assertion that `result["checks"]["server"]["service"] == "deep-search-agent"`. This is the expected compatibility identity, not evidence of a failed migration.

- [x] **Step 2: Add a failing legacy shim contract test**

Replace the old test module with focused compatibility checks:

```python
from tools import decision_research_agent_tool as canonical
from tools import deep_search_agent_tool as legacy


def test_legacy_module_reexports_canonical_public_contract():
    assert legacy.ToolClientError is canonical.ToolClientError
    assert legacy.ToolConfig is canonical.ToolConfig
    assert legacy.healthcheck is canonical.healthcheck
    assert legacy.main is canonical.main
```

Add subprocess tests invoking both script paths with `--help` and asserting exit code `0` plus the same `Decision Research Agent integration tool` description. Run each path once from the repository root and once from a temporary non-repository working directory by using an absolute script path.

- [x] **Step 3: Run the client tests and verify RED**

Run: `python -m pytest tests/unit/test_decision_research_agent_tool.py tests/unit/test_deep_search_agent_tool.py -q`

Expected: FAIL because the canonical module and shim do not exist yet.

- [x] **Step 4: Create the canonical implementation**

Move the current implementation to `tools/decision_research_agent_tool.py`. Add a private, lock-protected canonical-first resolver local to this file so direct script execution does not depend on repository-root package imports. `config_from_env()` must resolve:

```python
("DECISION_RESEARCH_AGENT_URL", "DEEP_SEARCH_AGENT_URL")
("DECISION_RESEARCH_AGENT_API_KEY", "DEEP_SEARCH_AGENT_API_KEY")
("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", "DEEP_SEARCH_AGENT_TIMEOUT_SECONDS")
```

Command-line `--base-url` and `--timeout` keep highest precedence. Invalid or non-positive timeout uses `ToolConfig.timeout_seconds`; an invalid canonical timeout must not read a valid legacy timeout.

Mirror the server resolver's fail-open warning behavior and provide a clearly documented `_reset_warning_state_for_tests()` private helper for test isolation. The server and Tool Client warning registries are intentionally independent; tests assert each resolver boundary separately rather than promising global cross-module deduplication.

- [x] **Step 5: Replace the legacy file with an explicit dual-mode shim**

Use explicit re-exports with two import modes: package import first (`tools.decision_research_agent_tool`), then a guarded sibling-module fallback (`decision_research_agent_tool`) only when direct script execution cannot resolve the `tools` package. Re-raise unrelated `ModuleNotFoundError` exceptions. Do not duplicate HTTP or CLI logic in the shim.

Add a cross-reference comment in the canonical Tool Client resolver and `agent/runtime_env.py` stating that warning and precedence semantics must stay aligned.

- [x] **Step 6: Run client tests and CLI smoke checks**

Run:

```bash
python -m pytest tests/unit/test_decision_research_agent_tool.py tests/unit/test_deep_search_agent_tool.py -q
python tools/decision_research_agent_tool.py --help
python tools/deep_search_agent_tool.py --help
(cd /tmp && python "$OLDPWD/tools/decision_research_agent_tool.py" --help)
(cd /tmp && python "$OLDPWD/tools/deep_search_agent_tool.py" --help)
```

Expected: tests PASS; all four commands exit `0` with the same public product description.

- [x] **Step 7: Commit the Tool Client migration**

```bash
git add tools/decision_research_agent_tool.py tools/deep_search_agent_tool.py tests/unit/test_decision_research_agent_tool.py tests/unit/test_deep_search_agent_tool.py
git commit -m "feat(client): add canonical tool entrypoint"
```

### Task 5: Update Current Configuration and Documentation

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `docs/observability.md`
- Modify: `docs/decisions/product-naming.md`
- Modify: `docs/superpowers/specs/2026-06-18-technical-identifier-migration-design.md`
- Modify: `spec/api-contract.md`

- [x] **Step 1: Publish canonical configuration examples**

In `.env.example`, replace the fixture flag with `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES=false` and set `LANGSMITH_PROJECT=decision-research-agent-dev`. Preserve `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`. Do not add secrets or edit an untracked `.env`.

- [x] **Step 2: Update current Tool Client and health references**

Use `tools/decision_research_agent_tool.py` and `DECISION_RESEARCH_AGENT_URL`, `DECISION_RESEARCH_AGENT_API_KEY`, and `DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS` in active examples. Document the legacy module and variables in one compatibility section, including value-free `FutureWarning` behavior and canonical precedence.

Document that `/health` remains an exact compatibility contract and is not the canonical product-discovery mechanism:

```json
{
  "status": "ok",
  "service": "deep-search-agent"
}
```

Document the per-variable empty-value table, canonical-plus-legacy ignored-key warning, and the benchmark runner's same-process exclusivity constraint.

- [x] **Step 3: Update current product and repository labels**

Change active root-tree labels and canonical repository URLs to `decision-research-agent`. Keep generic-profile architecture descriptions intact. Structurally rewrite `docs/decisions/product-naming.md` because its “presentation-only” premise has been superseded, and add an `Unreleased` compatibility entry to `CHANGELOG.md`.

- [x] **Step 4: Update LangSmith operator instructions**

Use `decision-research-agent-dev` for new trace commands. State that `deep-search-agent-dev` retains historical traces, no trace migration occurs, and LangSmith remains diagnostics only rather than the ResearchRun/EvidenceLedger authority.

- [x] **Step 5: Publish upgrade, rollback, and alias-removal gates**

In `docs/AGENT_INTEGRATION.md`, cover three operator paths: new canonical-only setup, existing deployment adding canonical keys while temporarily retaining matching legacy keys, and rollback to a legacy-only runtime. State that code rollback requires legacy keys to remain populated or to be restored; canonical-only configuration is not understood by pre-migration code.

Make the existing-deployment golden path copy-pasteable and bounded to three steps:

```bash
# 1. Add canonical keys without removing rollback-compatible legacy keys.
export DECISION_RESEARCH_AGENT_URL="$DEEP_SEARCH_AGENT_URL"
export DECISION_RESEARCH_AGENT_API_KEY="$DEEP_SEARCH_AGENT_API_KEY"
export DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS="$DEEP_SEARCH_AGENT_TIMEOUT_SECONDS"

# 2. Verify through the canonical entrypoint.
python tools/decision_research_agent_tool.py healthcheck

# 3. Keep legacy keys through the rollback window; remove them only after the
#    documented release gate is satisfied.
```

Show the exact expected health JSON. State that deprecation warnings go to stderr and command JSON remains on stdout for automation. New installations use only canonical keys; rollback to pre-migration code requires legacy keys before the process starts.

State explicitly that both `healthcheck` and `doctor` continue to report `service=deep-search-agent` by contract even when canonical configuration is active. The successful canonical signal is the canonical script/env path plus a passing response, not a changed health identifier.

Keep Tool Client URL/API key/timeout examples in `docs/AGENT_INTEGRATION.md`, not `.env.example`: the standalone client does not load the repository `.env`, while the backend does. Do not publish configuration in a file that the intended consumer never reads.

Define a process-based removal gate rather than an unsupported calendar date: legacy aliases remain for at least two tagged releases after this migration, and removal requires a separate approved breaking-change plan, a first-party consumer inventory, no active legacy usage outside shims/tests/compatibility docs, and release-note migration instructions. The repository currently has no tags, so this PR does not start a false countdown.

Update the source spec in the same commit so it preserves the exact health payload, states the rollback constraint, uses the same empty-value semantics, and records the process-based removal gate. Do not leave the implementation plan and source design in conflict.

- [x] **Step 6: Verify current docs, infrastructure, and protected history**

Run:

```bash
rg -n 'tools/deep_search_agent_tool.py|DEEP_SEARCH_AGENT_(URL|API_KEY|TIMEOUT_SECONDS)|LANGSMITH_PROJECT=deep-search-agent-dev' README.md README_CN.md .env.example docs/AGENT_INTEGRATION.md docs/observability.md spec/api-contract.md
rg -n 'deep-search-agent|DEEP_SEARCH_AGENT|deep_search_agent' Dockerfile.backend Dockerfile.frontend docker-compose.yml .github 2>/dev/null || true
git diff --name-only origin/main -- docs/evidence openspec/changes/archive benchmarks docs/superpowers/plans docs/superpowers/specs
```

Expected: the first command reports only explicitly labeled legacy compatibility references; the infrastructure scan finds no stale active identifier requiring migration; the protected-history command reports only this newly created plan file and the already committed 2026-06-18 design spec, never older historical files.

- [x] **Step 7: Commit documentation and configuration**

```bash
git add .env.example README.md README_CN.md CHANGELOG.md docs/README.md docs/AGENT_INTEGRATION.md docs/observability.md docs/decisions/product-naming.md docs/superpowers/specs/2026-06-18-technical-identifier-migration-design.md spec/api-contract.md
git commit -m "docs: publish canonical technical identifiers"
```

### Task 6: Run the Compatibility Release Gate

**Files:**
- Verify all files changed by Tasks 1-5
- Update: `docs/superpowers/plans/2026-06-18-technical-identifier-migration.md` checkboxes only after observed command success

- [x] **Step 1: Run focused migration tests**

Run:

```bash
python -m pytest \
  tests/unit/test_runtime_env.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/unit/test_deep_search_agent_tool.py \
  tests/unit/test_health_endpoint.py \
  tests/unit/test_provided_aggregate.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_talent_value_gate_runner.py -q
```

Expected: all focused tests PASS. Warnings may name legacy keys but must not include values.

- [x] **Step 2: Run the full backend suite**

Run: `python -m pytest -q`

Expected: the full suite passes with no new failures.

- [x] **Step 3: Run the frontend build**

Run: `npm run build`

Working directory: `frontend/`

Expected: Vue TypeScript check and Vite production build PASS.

- [x] **Step 4: Run CLI and static contract checks**

Run:

```bash
python tools/decision_research_agent_tool.py --help
python tools/deep_search_agent_tool.py --help
(cd /tmp && python "$OLDPWD/tools/decision_research_agent_tool.py" --help)
(cd /tmp && python "$OLDPWD/tools/deep_search_agent_tool.py" --help)
rg -n 'deep-search-agent|DEEP_SEARCH_AGENT|deep_search_agent' \
  --glob '!docs/evidence/**' \
  --glob '!docs/superpowers/plans/2026-06-0*.md' \
  --glob '!docs/superpowers/specs/2026-06-0*.md' \
  --glob '!openspec/changes/archive/**' \
  --glob '!benchmarks/**'
git diff --check
```

Expected: all four CLI commands exit `0`; remaining old identifiers are bounded compatibility references, tests, or historical filenames; `git diff --check` emits no output.

- [x] **Step 5: Review the complete branch diff**

Run:

```bash
git status --short
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- agent api tools scripts tests .env.example AGENTS.md README.md README_CN.md CHANGELOG.md docs spec
```

Expected: no runtime feature work, health payload change, route rename, persistence rename, secret, historical artifact rewrite, or unrelated formatting churn.

- [x] **Step 6: Commit plan completion evidence**

```bash
git add docs/superpowers/plans/2026-06-18-technical-identifier-migration.md
git commit -m "docs(plan): record identifier migration verification"
```

### Observed Verification

- Focused migration suite: `76 passed, 3 warnings in 0.78s`.
- Full backend suite: `498 passed, 3 warnings in 56.24s`.
- Frontend: `npm ci` restored lockfile-defined dependencies; `npm run build`
  completed successfully with Vite in `373ms`.
- CLI: canonical and legacy entrypoints returned help successfully from the
  repository root and `/tmp`.
- Warning safety: legacy Tool Client resolution remained functional under
  `PYTHONWARNINGS=error`, and warning text did not contain the configured API
  key value.
- Static checks: `git diff --check` passed; Docker, Compose, and GitHub workflow
  files contained no active identifier requiring migration; protected
  evidence, archive, and benchmark paths were unchanged.
- Dependency note: `npm ci` reported one existing high-severity audit finding;
  dependency remediation is outside this identifier-migration PR.

## Acceptance Gate

- New integrations use `decision-research-agent`, canonical Tool Client path, and `DECISION_RESEARCH_AGENT_*` variables.
- Legacy environment aliases and `tools/deep_search_agent_tool.py` continue to work with bounded, value-free deprecation warnings.
- The complete `/health` JSON remains `{"status":"ok","service":"deep-search-agent"}`; canonical identity discovery uses the API title, repository, Tool Client, and documentation.
- New LangSmith examples use `decision-research-agent-dev`; historical traces stay in `deep-search-agent-dev`.
- API paths, persisted state, Docker resources, profile IDs, benchmark IDs, and historical evidence remain unchanged.
- Upgrade and rollback instructions cover canonical-only setup, dual-key transition, and rollback to legacy-only code; aliases have an explicit process-based removal gate but no fabricated date.
- Focused tests, full backend tests, frontend build, CLI smoke checks, protected-history diff, and `git diff --check` all pass before push or PR creation.

## Autoplan Review

### Phase 1: CEO Review Step 0

#### 0A. Premise Challenge

| Premise | Evidence examined | Assessment |
|---|---|---|
| The remaining problem is technical identity drift, not product positioning | Repository and local directory are already `decision-research-agent`, while current runtime and docs still contain active `DEEP_SEARCH_AGENT_*`, `tools/deep_search_agent_tool.py`, and `service=deep-search-agent` contracts | Valid. The plan targets the remaining compatibility surface rather than reopening the product-name decision. |
| New integrations should stop copying legacy identifiers now | Active `.env.example`, Tool Client docs, benchmark runner, and runtime modules still publish or read legacy names | Valid. Doing nothing increases the future migration population on every new setup. |
| Existing callers may depend on legacy names even without a consumer inventory | The stable Tool Client, env names, and exact health payload have shipped; no repository-local inventory can prove that external consumers do not compare them | Valid and deliberately conservative. Compatibility aliases are cheaper than a speculative breaking release. |
| Canonical-first alias resolution is the right migration mechanism | Existing consumers use process environment configuration and a standalone Python script; both can preserve behavior without route or persistence changes | Valid, with an explicit rollback constraint: pre-migration code does not understand canonical keys, so operators must retain or restore legacy keys before code rollback. |
| One compatibility PR is reviewable | Runtime changes are small and an evidence scan found active stale identifiers in nine current config/documentation entrypoints | Valid with a constraint: implementation must stay in independently testable commits and protected-history checks must prevent a broad search/replace. |
| Historical evidence must remain unchanged | Historical plans, benchmark artifacts, archived OpenSpec changes, and evidence records describe the old identity at the time of execution | Valid. Rewriting them would weaken provenance rather than improve current DX. |

**Premise conclusion:** solve canonical adoption and bounded compatibility together. Do not use this PR to remove aliases, rename routes, change persistence, or advance P1B.

#### 0B. What Already Exists

| Sub-problem | Existing code or contract to reuse | Plan delta |
|---|---|---|
| Runtime fixture flag | Direct reads in `agent/main_agent.py` and `tools/provided_aggregate.py` | Route both through one `agent/runtime_env.py` resolver. |
| Talent recursion limit | Existing safe parser in `agent/talent_runtime.py` | Keep parsing and default behavior; replace only raw env lookup. |
| Benchmark env restoration | Existing nested `try/finally` in `scripts/talent_value_gate_runner.py` | Switch the temporary key to canonical; preserve success/timeout/exception restoration. |
| HTTP/CLI Tool Client | Complete implementation in `tools/deep_search_agent_tool.py` with unit coverage | Move implementation once; make legacy module an explicit re-export/CLI shim. |
| Health compatibility | Exact payload in `api/server.py` and exact-object assertion in `tests/unit/test_health_endpoint.py` | Preserve the complete response byte-for-byte; use existing API title and documentation for canonical discovery. |
| Privacy-first tracing | `.env.example` and `docs/observability.md` already hide inputs and outputs | Change only the default project and explain historical trace split. |
| Active docs vs history | Current entrypoints are listed in the source spec; historical directories are explicitly named | Update allowlisted current files and verify protected paths via diff. |

#### 0C. Dream State

```text
CURRENT
repo and public name are canonical
but active setup paths still teach legacy identifiers
        |
        v
THIS PLAN
new integrations use decision-research-agent
legacy env/module consumers keep working with visible deprecation;
the exact health payload remains unchanged
        |
        v
12-MONTH IDEAL
consumer inventory exists, two tagged releases have shipped,
legacy aliases can be removed in an explicit breaking release,
and historical evidence remains immutable
```

**Dream-state delta:** this plan creates the compatibility boundary, migration signal, rollback path, and process-based removal gate. It intentionally does not claim a calendar removal date because no consumer inventory or release cadence exists yet.

#### 0C-bis. Implementation Alternatives

| Approach | Completeness | Effort | Risk | Pros | Cons | Reuses |
|---|---:|---|---|---|---|---|
| A. Presentation-only minimum | 3/10 | S | Medium | Small diff; no runtime behavior change | New integrations keep accumulating legacy config; repo and tooling remain inconsistent | Existing README branding only |
| B. Staged compatibility migration | 10/10 | M | Low-Medium | Canonical path for every new integration; legacy callers survive; each boundary is testable | Touches many active docs and requires careful warning/precedence tests | Existing parsers, Tool Client, health route, benchmark `finally` |
| C. Big-bang technical rename | 7/10 | M | High | Removes old vocabulary immediately | Breaks unknown callers, invalidates exact health comparisons, and makes rollback ambiguous | Little compatibility leverage |

**Auto-decision:** choose Approach B. It is the only option that completes the current migration without trading away compatibility. Approach A leaves the actual problem unsolved; Approach C creates avoidable breakage.

#### 0D. SELECTIVE EXPANSION Analysis

The plan touches more than 15 files, but most are contract documentation and focused tests. Runtime structure adds one shared resolver and one canonical client module; it does not introduce new infrastructure, persistence, routes, or Agent behavior. Splitting runtime and docs into separate PRs would create an interval where code and published integration guidance disagree, so one compatibility PR remains the cleaner unit.

Expansion scan:

| Candidate | Decision | Reason |
|---|---|---|
| Automated repository-wide ban on all legacy strings | Reject for this PR | Legacy compatibility tests, shim, health contract, and historical filenames require intentional old strings; a broad ban would create brittle exceptions. |
| Runtime telemetry counting legacy alias use | Defer | It would help future removal, but adds an observability/data-policy surface beyond the current value-free warning contract. |
| Hard deprecation/removal date | Reject; add process gate instead | No consumer inventory or release cadence supports a credible date. Require two tagged releases, inventory, release notes, and a separate breaking-change approval before removal. |
| Rename REST/WebSocket routes | Reject | It provides no user value here and directly violates the compatibility objective. |
| Rename Docker volumes/database defaults | Reject | It risks empty replacement stores and is unrelated to new integration discoverability. |

#### 0E. Temporal Interrogation

| Implementation window | Decision that must already be explicit |
|---|---|
| Hour 1 human / 5-10 min agent | Resolver semantics: canonical presence wins even when empty; warnings contain key names only and deduplicate under concurrent calls. |
| Hours 2-3 human / 10-20 min agent | Invalid canonical numeric input uses the safe default and never falls through to a conflicting legacy value. |
| Hours 4-5 human / 10-20 min agent | Standalone Tool Client cannot depend on repository-root imports; the legacy file contains no duplicated HTTP/CLI implementation. |
| Hour 6+ human / 15-30 min agent | Protected-history diff, focused compatibility tests, full backend suite, frontend build, and both CLI paths from repository and non-repository working directories form the release gate. |

#### 0F. Mode Selection

**Auto-decision:** `SELECTIVE EXPANSION`, using Approach B. The existing scope is the baseline; only direct compatibility hardening belongs in this PR. Adjacent observability and final alias removal remain deferred until evidence supports them.

### NOT in Scope

- P1B durable HITL, Skills, Async Subagent, output-template optimization, or UI work.
- REST/WebSocket, SQLite table, persisted ID, benchmark ID, or profile ID renames.
- Docker service, volume, database default, or any `/health` response changes.
- Historical plan, evidence, archived OpenSpec, benchmark artifact, merged PR URL, or old LangSmith trace rewrites.
- Legacy alias removal or a promised removal date without consumer evidence.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO Step 0 | Use staged compatibility migration | Mechanical | Completeness + explicitness | It solves canonical adoption and preserves shipped contracts | Presentation-only and big-bang rename |
| 2 | CEO Step 0 | Keep one compatibility PR with task-level commits | Mechanical | Pragmatic | Runtime and current docs must agree at release time | Split code/docs PRs |
| 3 | CEO Step 0 | Keep historical artifacts immutable | Mechanical | Explicit over clever | Historical old names are provenance, not stale current guidance | Bulk replacement |
| 4 | CEO Step 0 | Defer production telemetry; replace a hard date with a process-based removal gate | Mechanical | Pragmatic + explicitness | This project lacks deployment telemetry and tags today, but aliases still need an exit criterion | Runtime metrics and fabricated calendar deadline |

### Phase 1: CEO Review Sections 1-10

#### Outside Voice Consensus

| Topic | Claude | Codex | Decision |
|---|---|---|---|
| Core strategy | Approve staged compatibility | Approve staged compatibility | Keep canonical-first aliases and a thin legacy shim. |
| Health identity | Initially accepted additive `product` | Flagged exact-object compatibility break | Preserve the complete existing payload; do not add `product`. |
| Deprecation horizon | Requested a date plus usage metrics | Requested a release/process gate without new telemetry | No fabricated date or production metrics; require two tagged releases, inventory, release notes, and separate breaking-change approval. |
| Rollback | Flagged missing operator guidance | Demonstrated canonical-only config breaks on old code | Add a three-scenario upgrade/rollback runbook. |
| Tool Client | Flagged duplicated resolver maintenance | Flagged direct-script import risk | Keep the standalone resolver, cross-reference semantics, and test both working-directory modes. |
| Documentation | Requested upgrade guide and CI/infrastructure scan | Requested evidence-based allowlist | Limit edits to active stale files, structurally rewrite the naming ADR, and scan infrastructure/protected history. |

#### Section 1: Architecture Review

**Findings:** four issues were found and incorporated: exact health compatibility, rollback coupling, direct-script import behavior, and excessive documentation scope.

```text
                         CURRENT PROCESS ENVIRONMENT
                                   |
                     +-------------+-------------+
                     |                           |
                     v                           v
          agent/runtime_env.py         Tool Client local resolver
          canonical -> legacy          canonical -> legacy
          value-free warning           value-free warning
             |       |       |                   |
             v       v       v                   v
        main_agent  Talent  provided      decision_research_agent_tool.py
                    runtime aggregate              ^
                                                  |
                                      deep_search_agent_tool.py
                                      import/CLI compatibility shim

  /health --------------------------------> exact legacy payload unchanged
  active docs/config ---------------------> canonical identifiers
  historical evidence -------------------> immutable
  LangSmith ------------------------------> diagnostics only, new project name
```

The only intentional duplication is the small resolver inside the standalone Tool Client. It avoids importing the repository package during direct execution. Cross-reference comments and mirrored contract tests bound the maintenance risk.

Stateful warning behavior:

```text
UNSEEN(legacy key)
   | legacy-only resolution              | canonical + legacy
   v                                     v
WARNED_FALLBACK ----------------------> WARNED (absorbing)
   ^                                     ^
   +------------- repeated calls --------+

Invalid transition: WARNED -> emit value or emit again
Prevented by: lock-protected key registry and value-free messages
```

At 10x and 100x call volume, environment lookup remains O(1); the warning registry is bounded by five legacy keys. No database, network, or Agent graph load is added. The main operational single point is configuration correctness, mitigated by deterministic precedence, explicit defaults, tests, and rollback documentation.

#### Section 2: Error & Rescue Map

| Method/codepath | What can go wrong | Exception/failure class | Rescued? | Rescue action | User/operator sees |
|---|---|---|---|---|---|
| `resolve_env` | Neither key exists | Missing value | Yes | Return declared default | Existing default behavior |
| `resolve_env` | Warning filter promotes `FutureWarning` to error | `FutureWarning` | Yes | Catch warning exception, mark key warned, return selected value | Runtime continues |
| fixture flag consumer | Empty or invalid text | Invalid boolean text | Yes | Anything except `true` is disabled | Fixture remains closed |
| `talent_recursion_limit` | Empty, non-numeric, zero, negative | `ValueError` / invalid range | Yes | Existing safe default | Run uses default limit |
| Tool Client timeout | Empty, non-numeric, non-positive | `ValueError` / invalid range | Yes | Existing `10.0` default | Client remains usable |
| legacy CLI shim | `tools` package unavailable during direct execution | `ModuleNotFoundError(name="tools")` | Yes | Guarded sibling import | CLI works outside repo cwd |
| legacy CLI shim | Canonical module has a real missing dependency | Other `ModuleNotFoundError` | No, intentionally | Re-raise original exception | Actionable traceback |
| benchmark fixture override | Talent run times out or raises | Existing timeout/exception paths | Yes | Existing `finally` restores/removes canonical key | Bundle records failure; process env restored |
| protected-history scan | Historical file changed | Verification failure | Yes | Stop release; inspect diff | PR not presented |

Error flow:

```text
read canonical? --yes--> parse consumer value --invalid--> safe default
      | no                                      |
      v                                         v
read legacy? ---no----> existing default      no legacy fallback
      | yes
      v
emit warning --warnings=error--> catch FutureWarning --> return legacy value
```

No LLM call, external service call, persistence mutation, or catch-all exception handler is introduced.

#### Section 3: Security & Threat Model

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| API key value leaks through warnings | Low | High | Messages contain key names only; tests use a sentinel secret and scan warning/output text. |
| Empty canonical API key falls through to legacy secret | Medium | High | Presence-based precedence treats empty canonical secret as a tombstone. |
| Malicious environment value reaches URL/timeout parsing | Low | Medium | Existing URL construction and numeric safe defaults remain; no shell interpolation is added. |
| Shim catches an unrelated import failure | Low | Medium | Fallback only when `exc.name == "tools"`; all other import errors re-raise. |

No endpoint, authorization path, dependency, database query, user-controlled file path, or data classification boundary changes. Security review found zero unmitigated High-severity issues.

#### Section 4: Data Flow & Interaction Edge Cases

```text
ENV INPUT -> PRESENCE SELECT -> CONSUMER PARSE -> RUNTIME VALUE
    |              |                 |                |
    | missing      | both set        | invalid        | selected
    v              v                 v                v
 default      canonical + warn   safe default    no persistence

    | empty canonical
    +--> API key: tombstone
    +--> URL/timeout/recursion: safe default
    +--> fixture flag: disabled
```

```text
LEGACY CLI PATH -> package import available? -> canonical main -> output
       | no
       v
 guarded sibling import -> canonical main -> output
       |
       +-- unrelated missing module --> re-raise, never mask defect
```

```text
BENCHMARK PAIR -> save canonical env -> generic run -> Talent override
       |                                            |
       | exception/timeout                          v
       +---------------------------------------> finally restore
                                                    |
                                                    v
                                             next pair / return
```

Concurrent `run_value_gate()` calls in one process remain unsupported because `os.environ` is process-global. The CLI is sequential and documentation states exclusive execution; this PR does not add infrastructure for a non-goal.

#### Section 5: Code Quality Review

- `agent/runtime_env.py` is the shared server boundary; consumers retain their existing parsing and defaults.
- The Tool Client resolver intentionally duplicates only selection/warning semantics to preserve standalone execution. Cross-reference comments and mirrored tests are required.
- The legacy file contains imports and `main()` dispatch only; HTTP and argparse code must not be duplicated.
- No method needs more than five behavioral branches. If implementation exceeds that, split warning emission from value selection as shown in Task 1.
- A repository-wide legacy-string ban remains rejected because compatibility fixtures, shims, tests, and historical evidence intentionally retain old identifiers.

#### Section 6: Test Review

```text
NEW USER-VISIBLE FLOWS
  canonical env setup; legacy warning; canonical CLI; legacy CLI shim;
  upgrade/rollback instructions; new LangSmith project example

NEW DATA FLOWS
  canonical/legacy env -> resolver -> existing consumers
  legacy script -> canonical Tool Client implementation

NEW CODEPATHS
  canonical-only; legacy-only; both-present; missing; empty; invalid;
  warning-as-error; repeated/concurrent warning; package/direct shim import

NEW ASYNC/BACKGROUND WORK
  none

NEW EXTERNAL CALLS
  none

NEW RESCUE PATHS
  warning filter fail-open; guarded direct-script import; benchmark env restore
```

| Test layer | Required coverage |
|---|---|
| Unit | Resolver precedence, missing/empty/invalid values, no secret leakage, warning dedupe, concurrent warning, warnings-as-errors. |
| Unit | Each runtime consumer preserves its current default and never falls through from invalid canonical to legacy. |
| Unit | Canonical Tool Client config precedence and public API identity re-export. |
| Subprocess | Both CLI paths from repo root and non-repo cwd. |
| Integration | Evidence lifecycle with legacy aliases; exact `/health` payload; existing routes unchanged. |
| Regression | Full backend suite and frontend build. |
| Static | Active-doc allowlist, infrastructure scan, protected-history diff, `git diff --check`. |

Friday-at-2am test: canonical and legacy keys both populated with different secret sentinels, strict warning mode enabled, then focused tests plus both CLI subprocess modes pass without exposing either value. Hostile QA test: empty canonical secret plus populated legacy secret never creates `X-API-Key`. Chaos test: Talent runner raises mid-pair and the canonical fixture key is restored before the next profile.

No prompt or LLM behavior changes, so no model eval or Talent benchmark rerun is required for this migration.

#### Section 7: Performance Review

No material performance issue found. The resolver adds constant-time dictionary lookups and a lock acquired at most until each of five legacy keys has warned. No query, cache, external request, background job, or connection pool is added. CLI and server request latency remain dominated by existing work.

#### Section 8: Observability & Debuggability Review

The migration signal is a bounded, value-free `FutureWarning`; canonical-plus-legacy warns that the old key is ignored. Production usage counters, dashboards, and LangSmith-based business decisions are explicitly rejected for this project scale and privacy posture. Debuggability comes from deterministic precedence, exact tests, the operator runbook, and the active-doc scan. LangSmith continues to diagnose Agent runs only and is not the ResearchRun/EvidenceLedger authority.

#### Section 9: Deployment & Rollout Review

Deployment sequence:

```text
1. Ship resolver + canonical Tool Client + legacy shim
2. Ship current docs/config in the same PR
3. Run focused/full/build/static gates
4. Deploy code while retaining legacy keys on existing installations
5. Add matching canonical keys and verify warning/health/CLI behavior
6. Remove legacy keys only after local verification; keep them if rollback is required
```

Rollback flow:

```text
Need code rollback?
    |
    +-- legacy keys still populated --> revert code --> verify old CLI + /health
    |
    +-- canonical-only config --------> restore/copy legacy keys
                                         |
                                         v
                                      revert code
                                         |
                                         v
                                verify old CLI + /health
```

There is no DB migration or mixed-schema window. Existing deployments should temporarily configure both key families with matching values; new installations use canonical keys only. A revert of canonical-only code is not configuration-independent, so the runbook is a release blocker.

#### Section 10: Long-Term Trajectory Review

Reversibility is **4/5**: code and docs can be reverted, but canonical-only deployments must restore legacy keys before reverting. The intentional debt is a five-key alias table, a thin legacy script, and two small resolver implementations. The process-based removal gate prevents permanent accidental dual-stack support without inventing telemetry or dates. In twelve months, a maintainer should see one canonical path, one compatibility boundary, immutable historical evidence, and an explicit breaking-release checklist.

The accepted selective expansions were rollback documentation, dual-key ignored warnings, source-spec correction, non-repo CLI smoke tests, and an infrastructure scan. Production telemetry and a calendar deadline remain rejected because they are not load-bearing for safe adoption.

### CEO Required Registries

#### Failure Modes Registry

| Codepath | Failure mode | Rescued? | Test? | User sees? | Logged/warned? |
|---|---|---|---|---|---|
| Runtime resolver | Canonical missing, legacy present | Yes | Yes | Existing behavior | Value-free warning |
| Runtime resolver | Both present | Yes | Yes | Canonical behavior | Legacy ignored warning |
| Runtime resolver | Warning promoted to exception | Yes | Yes | Existing behavior | Warning may be suppressed by strict filter |
| Runtime parser | Invalid canonical numeric | Yes | Yes | Safe default | No value logged |
| Runtime fixture flag | Empty/invalid canonical | Yes | Yes | Disabled | No value logged |
| Tool Client | Empty canonical secret with legacy secret | Yes | Yes | Unauthenticated request | No secret logged |
| Legacy shim | Non-repo working directory | Yes | Yes | Normal CLI help/command | N/A |
| Legacy shim | Real missing dependency | No, intentional | Yes | Traceback | Original exception |
| Benchmark runner | Run timeout/exception | Yes | Yes | Failed run in bundle | Existing diagnostic |
| Documentation | Stale active legacy example | Yes | Static gate | PR blocked | `rg` output |
| Protected history | Old evidence rewritten | Yes | Static gate | PR blocked | `git diff` output |

No row has `Rescued=No`, `Test=No`, and silent user impact.

#### Scope Expansion Decisions

- Accepted: exact health preservation, variable-specific empty semantics, dual-key ignored warnings, strict-warning fail-open behavior, rollback guide, non-repo CLI tests, process-based removal gate, infrastructure scan.
- Deferred: production legacy-use telemetry until a real multi-deployment need exists.
- Skipped: calendar removal date, route/resource renames, broad legacy-string lint rule, runtime locking for concurrent benchmark invocations.

#### Stale Diagram Audit

| Touched file | Existing diagram/code-block impact | Decision |
|---|---|---|
| `README.md` | Product overview and architecture flow remain accurate; project tree root is stale | Change only root label to `decision-research-agent/`. |
| `README_CN.md` | Same as English README | Change only root label. |
| `docs/AGENT_INTEGRATION.md` | Command and JSON blocks use legacy client/config | Update examples and retain an explicit compatibility block. |
| `docs/observability.md` | Command blocks use old LangSmith project | Update new-run examples; retain historical-project note. |
| `spec/api-contract.md` | Exact health JSON and Tool Client env contract | Keep health JSON unchanged; update canonical env contract. |

No architecture diagram requires redraw because runtime Agent topology is unchanged.

#### CEO Implementation Tasks

- [x] **CEO-T1 (P1, human: ~1h / CC: ~10min)** — Compatibility contract — Preserve exact health response and correct the source spec
  - Surfaced by: Architecture review — additive `product` breaks exact-object consumers.
  - Files: `api/server.py`, `tests/unit/test_health_endpoint.py`, `docs/superpowers/specs/2026-06-18-technical-identifier-migration-design.md`
  - Verify: `python -m pytest tests/unit/test_health_endpoint.py -q`
- [x] **CEO-T2 (P1, human: ~2h / CC: ~20min)** — Runtime configuration — Implement canonical-first, value-free, fail-open warning semantics
  - Surfaced by: Error/security review — strict warning filters and secret leakage must not break compatibility.
  - Files: `agent/runtime_env.py`, runtime consumers, `tests/unit/test_runtime_env.py`
  - Verify: focused resolver and consumer tests.
- [x] **CEO-T3 (P1, human: ~2h / CC: ~20min)** — Tool Client — Make canonical implementation and legacy shim work in both import modes
  - Surfaced by: Architecture/data-flow review — direct scripts do not always have repository root on `sys.path`.
  - Files: `tools/decision_research_agent_tool.py`, `tools/deep_search_agent_tool.py`, client tests.
  - Verify: four CLI subprocess smoke checks plus unit tests.
- [x] **CEO-T4 (P1, human: ~1h / CC: ~15min)** — Operations — Publish upgrade, rollback, and process-based alias-removal gates
  - Surfaced by: Deployment review — canonical-only config cannot survive rollback to legacy-only code.
  - Files: `docs/AGENT_INTEGRATION.md`, `CHANGELOG.md`, `docs/decisions/product-naming.md`.
  - Verify: documentation review and active identifier scan.
- [x] **CEO-T5 (P2, human: ~30min / CC: ~5min)** — Benchmark — State and test process-global fixture restoration boundaries
  - Surfaced by: Data-flow review — `os.environ` restoration is not concurrent run isolation.
  - Files: `scripts/talent_value_gate_runner.py`, runner tests, integration docs.
  - Verify: timeout/exception restoration tests.

#### CEO Completion Summary

```text
+====================================================================+
|            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
+====================================================================+
| Mode selected        | SELECTIVE EXPANSION                         |
| System Audit         | identity drift confirmed; health exactness  |
| Step 0               | staged compatibility; history immutable     |
| Section 1  (Arch)    | 4 issues found and resolved in plan         |
| Section 2  (Errors)  | 9 error paths mapped, 0 open gaps           |
| Section 3  (Security)| 4 threats mapped, 0 unmitigated High        |
| Section 4  (Data/UX) | 3 flows mapped, 0 unhandled in-scope edges  |
| Section 5  (Quality) | 2 duplication/scope risks bounded           |
| Section 6  (Tests)   | diagram produced, 4 test additions          |
| Section 7  (Perf)    | 0 material issues                           |
| Section 8  (Observ)  | warning signal + runbook; metrics rejected  |
| Section 9  (Deploy)  | 2 risks resolved: rollback and mixed config |
| Section 10 (Future)  | Reversibility 4/5, 3 bounded debt items     |
| Section 11 (Design)  | SKIPPED (no UI scope)                       |
+--------------------------------------------------------------------+
| NOT in scope         | written (10 items)                          |
| What already exists  | written                                    |
| Dream state delta    | written                                    |
| Error/rescue registry| 9 paths, 0 critical gaps                    |
| Failure modes        | 11 total, 0 critical gaps                   |
| TODOS.md updates     | 0 items proposed                            |
| Scope proposals      | 12 considered, 8 accepted                   |
| Outside voice        | Claude and Codex both ran                   |
| Lake Score           | staged compatibility selected              |
| Diagrams produced    | architecture, state, data, error, deploy,   |
|                      | rollback                                    |
| Stale diagrams found | 5 touched blocks; all bounded               |
| Unresolved decisions | 0                                           |
+====================================================================+
```

**Phase 1 result:** approved for engineering review after the above corrections. No unresolved CEO decisions.

### Phase 2: Engineering Review

#### Step 0: Scope Challenge

Scope is accepted after reduction from the original draft. Actual stale-identifier scanning limits current documentation edits to nine entrypoints plus the current source spec. Runtime changes remain five environment key pairs, one canonical Tool Client move, one legacy shim, and benchmark override restoration. No API response, persistence, Agent behavior, dependency, or UI change is required.

Independent engineering review status:

- Claude review: completed; approved with three test/documentation gaps.
- Codex engineering outside voice: unavailable because the local Codex CLI hit its usage limit after the CEO review. No finding was inferred from the failed run.
- Auto-decision: accept executable concurrent-test and test-only-helper recommendations; partially accept integration-test advice by converting one end-to-end fixture path to canonical while preserving legacy paths as intentional regression coverage.

#### 1. Architecture Review

Verified current boundaries:

| Boundary | Current evidence | Planned change |
|---|---|---|
| Aggregate preload | `agent/main_agent.py:153` reads legacy fixture env directly | Shared resolver; behavior otherwise unchanged. |
| Talent recursion | `agent/talent_runtime.py:11-19` parses legacy env with safe defaults | Resolve canonical/legacy first; retain parser. |
| Fixture provider | `tools/provided_aggregate.py:27` gates on legacy env | Shared resolver; fail-closed gate retained. |
| Tool Client | `tools/deep_search_agent_tool.py:177-189` owns env parsing and full implementation | Move once to canonical module; leave import/CLI shim. |
| Benchmark override | `scripts/talent_value_gate_runner.py:521-551` uses nested `try/finally` | Change temporary key only; preserve restoration structure. |
| Health | `api/server.py:131` plus exact assertion at `tests/unit/test_health_endpoint.py:13` | No runtime change. |

```text
Task 1 resolver
    |
    +--> Task 2 server consumers --> Task 3 benchmark override
    |
    +--> semantic contract mirrored by Task 4 Tool Client resolver
                                      |
                                      v
                              legacy shim subprocess tests

Tasks 1-4 complete --> Task 5 docs/spec --> Task 6 release gate
```

Distribution architecture is unchanged: no package or binary is published. The repository script remains the distribution unit, CI continues to run `python -m pytest -q` and the frontend build, and the canonical script path is documented in-repo.

Production failure scenario: an operator deploys canonical-only configuration and then reverts to pre-migration code. The old runtime ignores canonical keys. The plan now blocks release until the runbook tells existing deployments to retain matching legacy keys through the rollback window.

Architecture findings: **0 open issues** after CEO corrections.

#### 2. Code Quality Review

1. **[P1] (confidence: 9/10) `tools/deep_search_agent_tool.py:177-189` — standalone import constraints require a guarded dual-mode shim.** The file is directly executable and `tools/` has no `__init__.py`; package imports are not guaranteed when invoked by absolute path outside the repository. Task 4 now requires package-first plus sibling fallback and four subprocess checks.
2. **[P1] (confidence: 9/10) `tests/unit/test_health_endpoint.py:13` — exact-object compatibility forbids adding fields.** Task 5 was removed and the source spec must be corrected in the documentation commit.
3. **[P2] (confidence: 8/10) duplicated resolver semantics can drift.** The standalone constraint justifies duplication; mirrored tests, cross-reference comments, and an explicit “per resolver boundary” warning-dedupe contract contain it.
4. **[P2] (confidence: 8/10) test-state reset helpers could become accidental production APIs.** Both modules must keep `_reset_warning_state_for_tests()` private and document it as test-only.

No catch-all exception, new dependency, broad refactor, or method with excessive branching is planned. Existing legacy integration setup is retained intentionally instead of mechanically renamed.

#### 3. Test Review

Framework detection: Python `pytest` is authoritative through `.github/workflows/ci.yml`; frontend verification uses `npm run build`. There is no prompt/LLM file change, so no eval is required.

```text
CODE PATHS                                             OPERATOR FLOWS
[+] agent/runtime_env.py                               [+] New installation
  +-- [PLANNED ★★★] canonical only                       +-- canonical keys only
  +-- [PLANNED ★★★] legacy only + warning              [+] Existing installation
  +-- [PLANNED ★★★] both + ignored warning               +-- retain legacy, add canonical
  +-- [PLANNED ★★★] missing -> default                 [+] Rollback
  +-- [PLANNED ★★★] empty/invalid -> consumer default    +-- restore/retain legacy first
  +-- [PLANNED ★★★] warnings=error fail-open           [+] Tool Client
  +-- [PLANNED ★★★] 32 concurrent calls -> 1 warning     +-- canonical and legacy paths

[+] server consumers                                  [+] Benchmark
  +-- [PLANNED ★★★] canonical fixture end-to-end         +-- success restores env
  +-- [EXISTING ★★★] legacy fixture end-to-end            +-- timeout restores env
  +-- [PLANNED ★★★] canonical recursion                  +-- exception restores env
  +-- [EXISTING ★★★] legacy recursion

[+] Tool Client/shim                                  [+] Compatibility endpoint
  +-- [PLANNED ★★★] env precedence/empty/invalid         +-- exact /health JSON unchanged
  +-- [PLANNED ★★★] package import identity
  +-- [PLANNED ★★★] repo-root direct CLI
  +-- [PLANNED ★★★] non-repo direct CLI
  +-- [PLANNED ★★★] unrelated import error re-raised

E2E/EVAL: no browser E2E and no LLM eval required.
COVERAGE TARGET: every new branch above has a named unit, integration, or
subprocess check before implementation is accepted.
```

Regression requirements:

- Preserve at least one full legacy fixture flow in `tests/integration/test_evidence_lifecycle.py`; it proves existing callers still work.
- Convert one existing fixture flow to the canonical key; it proves canonical selection through real preload/provider boundaries.
- Keep the exact health equality test unchanged.
- Test canonical plus legacy with secret sentinel values and assert no warning/output contains values.
- Test strict warning mode and concurrent deduplication, not only sequential calls.
- Test both script paths from both working-directory contexts.

Test plan artifact: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/mac-codex-technical-identifier-migration-eng-review-test-plan-20260618-130004.md`.

Test gaps after plan revision: **0 open**.

#### 4. Performance Review

No material issue found. `resolve_env` performs O(1) environment lookups. Legacy or dual-key resolution acquires one short lock per call, and the registry is bounded by five keys. This is negligible compared with Agent execution and HTTP work. No query, allocation proportional to user data, cache, background job, or connection is introduced.

#### Engineering Failure Modes

| Codepath | Realistic failure | Test | Handling | Operator impact |
|---|---|---|---|---|
| Shared resolver | strict warning filter raises | Unit | Catch `FutureWarning`, return selected value | No startup failure |
| Shared resolver | concurrent calls race warning registry | Threaded unit | `RLock` + dedupe set | At most one warning |
| Runtime parser | invalid canonical numeric plus valid legacy | Unit | Safe default, no legacy fallback | Deterministic default |
| Fixture provider | canonical empty while legacy true | Unit | Canonical disables provider | Fail closed |
| Benchmark override | timeout/exception before outcome | Unit | Existing `finally` restores env | Next run not polluted |
| Canonical CLI | launched outside repository cwd | Subprocess | No repo package dependency | Normal CLI operation |
| Legacy shim | package import unavailable | Subprocess | Guarded sibling import | Normal CLI operation |
| Legacy shim | canonical module has missing dependency | Unit | Re-raise unrelated import error | Clear traceback |
| Health | extra response field added accidentally | Unit/integration | Exact equality regression | Release blocked |
| Docs/history | bulk replacement rewrites evidence | Static check | Protected-history diff | Release blocked |

No critical silent failure remains without both handling and a planned test.

#### Worktree Parallelization Strategy

| Step | Modules touched | Depends on |
|---|---|---|
| Resolver and runtime consumers | `agent/`, `tools/`, `tests/` | - |
| Benchmark override | `scripts/`, `tests/` | Resolver semantics |
| Tool Client and shim | `tools/`, `tests/` | Resolver contract |
| Documentation/spec | `docs/`, `spec/`, root docs | Final runtime contracts |
| Release gate | whole repository | All prior steps |

Potentially independent Tool Client work still shares `tools/` and `tests/` with runtime consumer work, and both must mirror the same warning contract. **Recommendation: sequential implementation in one isolated worktree.** Parallel worktrees would save little time and increase semantic/merge drift.

#### Engineering Implementation Tasks

- [x] **ENG-T1 (P1, human: ~2h / CC: ~20min)** — Configuration — Implement and exhaustively test resolver semantics
  - Surfaced by: code/test review — strict warning filters, dual keys, empty values, and concurrent calls are distinct branches.
  - Files: `agent/runtime_env.py`, `tests/unit/test_runtime_env.py`.
  - Verify: `python -m pytest tests/unit/test_runtime_env.py -q`.
- [x] **ENG-T2 (P1, human: ~2h / CC: ~20min)** — Runtime integration — Prove canonical and legacy fixture paths end to end
  - Surfaced by: test review — unit selection alone does not prove preload/provider wiring.
  - Files: runtime consumers and `tests/integration/test_evidence_lifecycle.py`.
  - Verify: focused consumer and evidence lifecycle tests.
- [x] **ENG-T3 (P1, human: ~2h / CC: ~20min)** — Tool Client — Test package and direct-script execution from two working directories
  - Surfaced by: architecture review — namespace-package resolution differs by entry mode.
  - Files: canonical client, legacy shim, client tests.
  - Verify: client unit tests plus four CLI smoke commands.
- [x] **ENG-T4 (P1, human: ~1h / CC: ~10min)** — Release safety — Keep health exact and block protected-history drift
  - Surfaced by: regression review — both are shipped compatibility contracts.
  - Files: health regression test, source spec, release commands.
  - Verify: health tests, infrastructure scan, protected-history diff, `git diff --check`.

#### Engineering Completion Summary

- Step 0: scope reduced to evidence-backed runtime and documentation surfaces.
- Architecture Review: 0 open issues; one explicit rollback dependency.
- Code Quality Review: 4 findings, all represented in tasks/tests.
- Test Review: branch diagram produced, 0 remaining gaps.
- Performance Review: 0 material issues.
- NOT in scope: retained and tightened.
- What already exists: direct reads, safe parsers, `finally` restoration, client implementation, exact health test all reused.
- TODOS.md updates: 0 proposed.
- Failure modes: 10 mapped, 0 critical silent gaps.
- Outside voice: Claude completed; Codex unavailable due usage limit.
- Parallelization: sequential recommended; no useful parallel lanes.
- Lake Score: 4/4 engineering recommendations use the complete option.
- Unresolved engineering decisions: 0.

**Phase 2 result:** approved for DX review.

### Phase 3.5: Developer Experience Review

#### Developer Persona Card

```text
TARGET DEVELOPER PERSONA
========================
Who:       Backend or automation engineer integrating the service through
           environment variables and the repository Python Tool Client.
Context:   Existing local/self-hosted deployment or a fresh clone that must adopt
           the renamed technical identity without interrupting automation.
Tolerance: Five minutes and at most three migration steps before inspecting source.
Expects:   Copy-paste commands, stable JSON, value-safe warnings, deterministic
           precedence, CI-safe scripts, and an explicit rollback path.
```

Primary product type: **API/Service + CLI Tool + Documentation**. This is an enhancement to an existing developer-facing project, so the auto-selected mode is **DX POLISH**, not DX expansion.

#### Developer Empathy Narrative

I arrive because the repository is now `decision-research-agent`, but the README still tells me the compatibility identifier is `deep-search-agent`. I open `docs/AGENT_INTEGRATION.md` and find only `tools/deep_search_agent_tool.py` and `DEEP_SEARCH_AGENT_*`. I can make the old client work, but I cannot tell whether adopting the new name is supported or cosmetic. I do not want to inspect `os.getenv()` calls across the repository or risk replacing every string and losing persisted data.

The reviewed plan gives me one canonical path. I keep my legacy keys, export matching `DECISION_RESEARCH_AGENT_*` values, and run `python tools/decision_research_agent_tool.py healthcheck`. The response still says `service=deep-search-agent`; the guide explicitly tells me this is the expected compatibility contract, not a failed migration. If both key families exist, stderr tells me the old key is ignored without exposing its value, while stdout remains valid JSON for automation. I can run `doctor` for the same confirmation and know why it still shows the old service ID.

Most importantly, the guide tells me what happens if I revert code. A pre-migration runtime cannot read canonical-only keys, so an existing deployment keeps legacy keys through the rollback window and a fresh installation must recreate them before rollback. I finish without guessing which routes, database names, Docker volumes, or historical traces were renamed, because the guide states they were not.

#### Competitive DX Benchmark

Live web search was attempted but returned HTTP 403, so no current external timing claim is used. The comparison below uses the local gstack DX reference patterns only.

| Reference pattern | Migration/onboarding choice | Standard applied here |
|---|---|---|
| Stripe API versioning | Preserve old contracts and make upgrades explicit | Keep exact health JSON and legacy aliases. |
| Next.js codemods | Automate broad repetitive migrations | Not justified for five environment aliases; provide a three-step shell path. |
| Vercel single-command verification | Immediate visible success signal | Canonical `healthcheck` is the first verification command. |
| This plan | Three steps, expected JSON, rollback note | Target migration TTHW: 2-5 minutes. |

Current migration discoverability is effectively **8-12 minutes** because canonical runtime support is absent and users must inspect source. The reviewed target is **2-5 minutes** for an existing running deployment.

#### Magical Moment Specification

The moment is: **the operator invokes the canonical Tool Client while old configuration remains present, receives the unchanged healthy JSON, and sees only a value-free ignored-legacy warning on stderr.** Delivery vehicle: copy-paste terminal commands in `docs/AGENT_INTEGRATION.md` with expected output. No playground, hosted demo, video, or new UI is warranted.

#### Developer Journey Map

| Stage | Current friction | Reviewed plan resolution |
|---|---|---|
| Discover | Repo name and active technical identifiers disagree | README states canonical identity and links migration guide. |
| Evaluate | Unknown blast radius | Compatibility table lists changed and unchanged contracts. |
| Install | Existing setup works only under legacy names | Runtime accepts canonical and legacy names. |
| Configure | Precedence and empty values are ambiguous | Variable mapping and per-setting empty semantics are explicit. |
| Hello World | No canonical verification command | Canonical `healthcheck` plus exact expected JSON. |
| Integrate | Legacy CLI path appears authoritative | Canonical implementation documented; legacy path labeled shim. |
| Debug | Old service ID looks like failed migration | `healthcheck`/`doctor` compatibility identity explained. |
| Upgrade | Removing old keys may harm rollback | Existing installs retain both sets through rollback window. |
| Rollback | Canonical-only config is ignored by old code | Fresh/existing rollback instructions restore legacy keys first. |

#### First-Time Developer Confusion Report

| Confusion | Evidence | Resolution |
|---|---|---|
| “Did the repo really rename?” | README currently says compatibility identifier remains old | Replace stale current statement; retain one migration section. |
| “Which env key wins?” | Current code reads only legacy names | Canonical presence always wins; both-present warns. |
| “Why does health still say old name?” | Exact response at `api/server.py:131` | Explain compatibility contract in integration guide. |
| “Can I remove old keys immediately?” | No current migration guide | Keep through rollback window; process-based removal gate. |
| “Will warnings break JSON automation?” | Python warnings use stderr by default | Document stderr/stdout split and test no value leakage. |
| “Can I use `python -m`?” | Project distributes repository scripts, not a Python package | Do not imply an unsupported package entrypoint. |
| “Should Tool Client vars go in `.env`?” | Client does not call `load_dotenv`; backend does | Keep client vars in integration docs, not `.env.example`. |

#### Pass 1: Getting Started Experience - 8/10

Ideal existing-deployment path:

```text
T+0:00  Export canonical keys from retained legacy values.
T+1:00  Run canonical `healthcheck`.
T+1:10  Match exact healthy JSON and read the compatibility-ID note.
T+2:00  Keep legacy values through rollback window; migration complete.
```

The plan meets the three-step, 2-5 minute target for migration. Full first-time project installation still requires Python, Node, and external API keys; changing that is outside this identifier migration.

#### Pass 2: API/CLI/SDK Design - 8/10

Canonical names are guessable and flags retain current precedence. The script path is the supported distribution surface; adding `python -m` would imply package semantics the repository does not provide. The legacy shim preserves imports and commands, while the canonical module owns all logic. Existing API endpoints remain complete and unchanged.

#### Pass 3: Error Messages and Debugging - 7/10

| Path | Current operator view | Reviewed target |
|---|---|---|
| Legacy key used | No migration signal | `OLD_KEY is deprecated; use NEW_KEY`, values omitted. |
| Both keys set | No precedence signal | `OLD_KEY is deprecated and ignored because NEW_KEY is set`. |
| Health/doctor returns old service | Looks like migration failed | Guide states this exact value is success under compatibility contract. |

The pre-existing connection error remains generic JSON (`<urlopen error ...>`), but changing the client error taxonomy is unrelated to identifier migration. Strict warning filters fail open so a migration notice cannot become an outage.

#### Pass 4: Documentation and Learning - 8/10

The migration guide becomes the single current reference for mapping, precedence, empty values, upgrade, verification, and rollback. README and docs index link to it; the naming decision and source spec agree. Historical filenames stay unchanged and clearly remain provenance rather than current examples.

#### Pass 5: Upgrade and Migration Path - 9/10

Backward compatibility is explicit, warnings are actionable, the existing-install path retains rollback keys, and fresh-install rollback is called out. A codemod would be disproportionate for five aliases. Removal is gated by releases, inventory, migration notes, and separate approval rather than an unsupported date.

#### Pass 6: Developer Environment and Tooling - 8/10

Both direct script paths are tested on repository and non-repository working directories. GitHub Actions already runs the full backend suite and frontend build; a dedicated migration workflow would duplicate CI and weaken the “full suite must pass” gate. Focused tests remain a local diagnostic command.

#### Pass 7: Community and Ecosystem - 6/10

The repository is public and includes runnable docs, but this migration does not add community channels, package distribution, or extension ecosystems. Those are product-level choices and are not blockers for a compatibility rename.

#### Pass 8: DX Measurement and Feedback Loops - 7/10

The plan measures deterministic signals: focused tests, full CI, four CLI smoke checks, active-doc scans, and protected-history checks. Production adoption telemetry is intentionally absent because this project has no deployment fleet or data policy requiring it. The process-based removal review is the future feedback checkpoint.

#### DX Outside Voice Resolution

| Outside-voice proposal | Decision | Evidence |
|---|---|---|
| Explain legacy `service` in `doctor` | Accept as docs + exact test, not a new server field | `doctor()` currently projects `health.service`; exact health must remain unchanged. |
| Add `python -m` entrypoints | Reject | Repository script is the distribution contract; `tools/` is not a packaged module. |
| Add Tool Client vars to `.env.example` | Reject | Tool Client does not load `.env`; backend does. Integration docs are the truthful location. |
| Add dedicated migration CI workflow | Reject | Existing CI already runs the full backend suite; focused command is diagnostic. |
| Add fresh-install rollback callout | Accept | Canonical-only config is unreadable by pre-migration code. |
| Replace `rg` or add fallback | Reject for project implementation plan | `rg` is the established repository/agent search tool; this is a maintainer gate, not end-user runtime. |

Codex DX voice was unavailable after the CLI hit its usage limit. Claude supplied the independent DX voice; no cross-model consensus is claimed for this phase.

#### DX Not in Scope

- One-command full project installation: unrelated to identifier compatibility and external service prerequisites.
- Python package publishing or `python -m` support: no package distribution contract exists.
- New client error taxonomy/docs URLs: pre-existing behavior, not caused by migration.
- Dedicated migration CI workflow: duplicates the full-suite job.
- Hosted playground, demo UI, or video: disproportionate for a configuration migration.
- Community channels, SDK languages, or plugin ecosystem: product-level work outside this PR.
- Production adoption analytics: no deployment fleet or approved data policy.

#### DX What Already Exists

- README Quick Start and API endpoint list provide the base onboarding structure.
- `docs/AGENT_INTEGRATION.md` already documents every Tool Client command and security behavior.
- `healthcheck` and `doctor` provide immediate verification without new endpoints.
- Tool Client prints JSON to stdout and failures as non-zero JSON responses.
- `CHANGELOG.md` provides a release-note home.
- GitHub Actions runs backend and frontend verification non-interactively.

#### DX Scorecard

```text
+====================================================================+
|              DX PLAN REVIEW — SCORECARD                            |
+====================================================================+
| Dimension            | Score  | Current | Trend                    |
|----------------------|--------|---------|--------------------------|
| Getting Started      | 8/10   | 5/10    | +3                       |
| API/CLI/SDK          | 8/10   | 6/10    | +2                       |
| Error Messages       | 7/10   | 5/10    | +2                       |
| Documentation        | 8/10   | 5/10    | +3                       |
| Upgrade Path         | 9/10   | 2/10    | +7                       |
| Dev Environment      | 8/10   | 7/10    | +1                       |
| Community            | 6/10   | 6/10    |  0                       |
| DX Measurement       | 7/10   | 5/10    | +2                       |
+--------------------------------------------------------------------+
| Migration TTHW       | 2-5 min target; current discovery 8-12 min |
| Competitive Rank     | Competitive for a compatibility migration  |
| Magical Moment       | designed via canonical healthcheck         |
| Product Type         | API/Service + CLI Tool + Documentation     |
| Mode                 | DX POLISH                                   |
| Overall DX           | 7.9/10 | 5.1/10 | +2.8                     |
+====================================================================+
```

#### DX Implementation Checklist

```text
DX IMPLEMENTATION CHECKLIST
============================
[ ] Migration time to healthy verification is under 5 minutes
[ ] Existing-deployment path is three copy-pasteable steps
[ ] Canonical healthcheck produces meaningful expected JSON
[ ] Legacy and both-present warnings have problem + cause + fix
[ ] Warnings omit values and stay on stderr; JSON stays on stdout
[ ] CLI naming is guessable and canonical examples lead
[ ] Empty and invalid configuration behavior is documented
[ ] `doctor` compatibility service identity is explained and tested
[ ] Upgrade and fresh/existing rollback paths are documented
[ ] Both script paths work in CI-safe non-interactive mode
[ ] Changelog and naming decision describe the compatibility window
[ ] Historical evidence and trace projects remain discoverable and unchanged
```

#### DX Implementation Tasks

- [x] **DX-T1 (P1, human: ~1h / CC: ~15min)** — Migration guide — Publish the three-step canonical adoption and rollback path
  - Surfaced by: Getting Started and Upgrade passes — current docs expose only legacy identifiers.
  - Files: `docs/AGENT_INTEGRATION.md`, `README.md`, `README_CN.md`, `CHANGELOG.md`.
  - Verify: follow commands against a running local backend and compare exact JSON.
- [x] **DX-T2 (P1, human: ~30min / CC: ~5min)** — CLI trust — Explain and test the compatibility service identity
  - Surfaced by: Error Messages pass — `doctor` returning the old service name can look like failed migration.
  - Files: canonical client tests and `docs/AGENT_INTEGRATION.md`.
  - Verify: canonical `healthcheck` and `doctor` both succeed with `service=deep-search-agent`.
- [x] **DX-T3 (P2, human: ~30min / CC: ~5min)** — Documentation IA — Keep canonical examples primary and legacy aliases in one compatibility section
  - Surfaced by: Documentation pass — scattering old names recreates migration ambiguity.
  - Files: active README/docs/spec allowlist.
  - Verify: active identifier scan reports old names only in the compatibility section.

#### DX Completion Summary

- All eight DX passes evaluated; lowest score is 6/10 for community, intentionally unchanged by this migration.
- Developer persona, empathy narrative, benchmark, magical moment, nine-stage journey, confusion report, scorecard, and checklist are written.
- Migration TTHW improves from source-inspection-level 8-12 minutes to a 2-5 minute target.
- Three DX tasks are in scope; zero TODO.md items proposed.
- Independent Claude voice ran; Codex DX voice unavailable due usage limit.
- Unresolved DX decisions: 0.

**Phase 3.5 result:** approved for the final gate.

### Cross-Phase Themes

| Theme | Phases | Consolidated decision |
|---|---|---|
| Compatibility must be exact, not approximate | CEO, Eng, DX | Preserve complete health JSON, routes, persistence, and old CLI behavior. |
| Rollback is configuration-dependent | CEO, Eng, DX | Existing deployments retain legacy keys; fresh installs restore them before old-code rollback. |
| Standalone script behavior is a first-class contract | CEO, Eng, DX | Keep a local resolver and test canonical/legacy scripts from two working directories. |
| Evidence-backed scope beats broad renaming | CEO, Eng, DX | Edit active stale entrypoints only; protect historical files and reject unrelated infrastructure. |
| Migration signals must not leak or interrupt | CEO, Eng, DX | Value-free stderr warnings, strict-mode fail-open behavior, deterministic precedence. |

### Additional Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 5 | CEO | Preserve exact `/health` response | Mechanical | Compatibility first | Exact-object test proves an additive field can break consumers | Add `health.product` |
| 6 | CEO | Define empty semantics per variable | Mechanical | Explicit over clever | Secret tombstone and numeric/default behavior are not interchangeable | One generic empty rule |
| 7 | CEO | Use a release/process alias-removal gate | Taste | Pragmatic | No tags, inventory, fleet telemetry, or credible calendar date exists | Fixed date plus production metrics |
| 8 | CEO | Use guarded dual-mode legacy shim | Mechanical | Completeness | Package import and direct script execution have different `sys.path` behavior | One absolute import |
| 9 | Eng | Keep legacy integration coverage and add one canonical full path | Mechanical | Regression safety | Both new and old contracts need end-to-end proof | Rename every test fixture |
| 10 | Eng | Treat warning dedupe as per resolver boundary | Mechanical | Explicitness | Server and standalone client maintain independent registries | False global dedupe promise |
| 11 | DX | Keep direct script as the only documented Tool Client entrypoint | Mechanical | Truthful docs | Project is not distributed as a Python package | Add unsupported `python -m` contract |
| 12 | DX | Keep Tool Client variables out of `.env.example` | Mechanical | Fight uncertainty | The standalone client never loads repository `.env` | Publish inert configuration |
| 13 | DX | Reuse full CI instead of adding migration workflow | Mechanical | Minimal sufficient scope | Full tests are the release gate; focused tests diagnose failures | Duplicate CI job |
| 14 | DX | Explain old `service` in healthcheck and doctor | Mechanical | Fight uncertainty | Correct compatibility output otherwise looks like failed migration | Change server response |

## GSTACK REVIEW REPORT

Status: **READY FOR USER APPROVAL**

| Review | Result |
|---|---|
| CEO | SELECTIVE EXPANSION complete; exact compatibility and rollback corrected; 0 unresolved decisions. |
| Design | Skipped correctly; no UI scope detected. |
| Engineering | Full architecture/code/test/performance review complete; 0 open test gaps; sequential execution recommended. |
| DX | DX POLISH complete; 7.9/10 overall; migration TTHW target 2-5 minutes. |
| Outside voices | Claude completed CEO, Eng, and DX reviews; Codex completed CEO review, then became unavailable due usage limit. |
| Implementation tasks | 12 aggregated tasks across CEO, Eng, and DX artifacts; implementation plan consolidates them into six ordered tasks. |
| User challenges | None. |
| Taste decisions | One: process-based alias-removal gate instead of a fabricated date plus production telemetry. |

Key corrections made by review:

1. Preserve the complete `/health` payload instead of adding `product`.
2. Define empty/invalid semantics per environment setting and keep warnings fail-open under strict filters.
3. Test canonical and legacy runtime paths, concurrent warning deduplication, and both CLI working-directory modes.
4. Publish exact upgrade, rollback, `doctor`, and alias-removal guidance.
5. Limit documentation edits to active stale entrypoints and protect historical evidence.
6. Keep production telemetry, route/resource renames, package publishing, dedicated migration CI, and unrelated Agent work out of scope.

Artifacts:

- CEO tasks: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/tasks-ceo-review-20260618-125612.jsonl`
- Engineering tasks: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/tasks-eng-review-20260618-130139.jsonl`
- DX tasks: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/tasks-devex-review-20260618-130730.jsonl`
- Engineering test plan: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/mac-codex-technical-identifier-migration-eng-review-test-plan-20260618-130004.md`
- Restore point: `/Users/mac/.gstack/projects/iTao-AI-decision-research-agent/codex-technical-identifier-migration-autoplan-restore-20260618-123418.md`

Pre-gate verification: required sections present, 78 balanced Markdown fences, no unresolved placeholders, and `git diff --check` clean. No runtime code was modified during planning.

NO UNRESOLVED DECISIONS
