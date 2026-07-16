from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CURRENT_DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "README_CN.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "docs" / "README.md",
    PROJECT_ROOT / "docs" / "demo-console.md",
    PROJECT_ROOT / "docs" / "prd.md",
    PROJECT_ROOT / "docs" / "observability.md",
    PROJECT_ROOT / "docs" / "AGENT_INTEGRATION.md",
    PROJECT_ROOT / "docs" / "operations" / "controlled-review-workflow.md",
    PROJECT_ROOT / "docs" / "operations" / "durable-hitl-feasibility.md",
    PROJECT_ROOT / "docs" / "operations" / "evidence-verification-workflow.md",
    PROJECT_ROOT / "docs" / "operations" / "real-source-proof-workflow.md",
    PROJECT_ROOT / "docs" / "architecture.md",
    PROJECT_ROOT / "docs" / "reference" / "api-contract.md",
    PROJECT_ROOT / "docs" / "reference" / "data-models.md",
    PROJECT_ROOT / "docs" / "reference" / "state-machines.md",
    PROJECT_ROOT / "docs" / "reference" / "tool-registry.md",
]

def _combined_docs() -> str:
    return "\n\n".join(path.read_text(encoding="utf-8") for path in CURRENT_DOCS)


def _section_between(text: str, start: str, end: str) -> str:
    assert start in text
    assert end in text
    return text.split(start, 1)[1].split(end, 1)[0]


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _markdown_table_rows(
    text: str,
    *,
    header: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    lines = text.splitlines()
    header_line = "| " + " | ".join(header) + " |"
    assert lines.count(header_line) == 1
    header_index = lines.index(header_line)
    assert lines[header_index + 1] == "|" + "---|" * len(header)

    rows = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        assert len(cells) == len(header)
        rows.append(cells)
    return tuple(rows)


def _inline_code_value(value: str) -> str:
    assert value.startswith("`") and value.endswith("`")
    return value[1:-1]


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1
    return text.replace(old, new, 1)


def _assert_contract_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    path: Path,
    replacements: tuple[tuple[str, str], ...],
    contract: Callable[[], None],
) -> None:
    read_text = Path.read_text
    mutated_text = read_text(path, encoding="utf-8")
    for old, new in replacements:
        mutated_text = _replace_once(mutated_text, old, new)

    def mutated_read_text(self: Path, *args, **kwargs) -> str:
        if self == path:
            return mutated_text
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mutated_read_text)
    with pytest.raises(AssertionError):
        contract()


def test_current_docs_state_framework_authority_contracts() -> None:
    docs = _combined_docs()

    required_phrases = [
        "LangChain = Agent Framework",
        "DeepAgents = research harness",
        "LangGraph = durable workflow runtime",
        "LangSmith = privacy-first tracing/evaluation",
        "Application DB = business authority",
        "ResearchExecutionService -> AgentHarness -> DeepAgentsHarness",
        "backend-and-CLI release",
        "Static Demo",
        "Live Backend",
        "Agent Research Operations Console",
        "Markdown-only delivery",
    ]

    for phrase in required_phrases:
        assert phrase in docs


def test_current_docs_do_not_advertise_removed_or_legacy_surfaces() -> None:
    docs = _combined_docs()

    forbidden_phrases = [
        "deep-" "search-agent",
        "DEEP_" "SEARCH_AGENT_",
        "service=deep-" "search-agent",
        "/api/" "task",
        "/api/" "tasks",
        "tools/" "deep_" "search_" "agent_tool.py",
        "Vue",
        "convert_md_to_pdf",
        "PDF Agent",
        "persistent Agent memory",
        "generic research kill-9 resume",
        "read-only operator console",
        "只读运行控制台",
    ]

    for phrase in forbidden_phrases:
        assert phrase not in docs


def test_all_tracked_markdown_uses_public_neutral_presentation() -> None:
    from scripts.final_presentation_audit import presentation_violations

    completed = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z", "*.md"],
        capture_output=True,
        check=True,
    )
    violations = []
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = raw_path.decode("utf-8")
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for rule in presentation_violations(text):
            violations.append({"path": relative_path, "rule": rule})

    assert violations == []


def test_docs_index_links_curated_project_planning_workspace() -> None:
    docs_index = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "superpowers/README.md" in docs_index
    assert "superpowers/specs/2026-06-30-react-demo-console-live-flow-design.md" in docs_index
    assert "superpowers/plans/2026-06-30-react-demo-console-live-flow-implementation.md" in docs_index


def test_demo_console_docs_define_a_safe_copy_pasteable_local_flow() -> None:
    guide = (PROJECT_ROOT / "docs" / "demo-console.md").read_text(encoding="utf-8")

    required = [
        "npm ci",
        "npm run dev -- --host 127.0.0.1",
        "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN=http://127.0.0.1:5173",
        "API_SECRET=",
        "python -m uvicorn api.server:app --host 127.0.0.1 --port 8000",
        "does not accept or store API credentials",
        "Static Demo",
        "Live Backend",
        "http://127.0.0.1:<port>",
        '{"status":"ok","service":"decision-research-agent"}',
    ]

    for phrase in required:
        assert phrase in guide


def test_demo_console_docs_track_frontend_node_requirements() -> None:
    docs = "\n\n".join(
        [
            (PROJECT_ROOT / "docs" / "demo-console.md").read_text(encoding="utf-8"),
            (PROJECT_ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8"),
        ]
    )

    assert "20.19+" in docs
    assert "22.13+" in docs
    assert "24+" in docs
    assert "22.12+" not in docs


def test_readme_first_run_flow_is_canonical_and_copy_pasteable() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    expected_flow = [
        "git clone",
        "cp .env.example .env",
        "pip install --no-deps -r constraints.txt",
        "python api/server.py",
        "curl --fail --silent http://127.0.0.1:8000/health",
        "python tools/decision_research_agent_tool.py doctor",
        "python tools/decision_research_agent_tool.py run",
        "python tools/decision_research_agent_tool.py result",
    ]

    positions = []
    for command in expected_flow:
        position = readme.find(command)
        assert position != -1, command
        positions.append(position)
    assert positions == sorted(positions)


def test_public_readmes_surface_engineering_depth_and_golden_path() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_cn = (PROJECT_ROOT / "README_CN.md").read_text(encoding="utf-8")
    canonical_demo_route = (
        "https://itao-ai.github.io/my-website/#/projects/decision-research-agent"
    )

    assert "## Engineering Depth" in readme
    assert "[Architecture Deep Dive](docs/architecture.md)" in readme
    assert canonical_demo_route in readme
    assert canonical_demo_route in readme_cn
    assert "#project/decision-research-agent" not in readme
    assert "#project/decision-research-agent" not in readme_cn
    assert "--wait \\\n  --result" in readme_cn
    assert "`--wait --result`" in readme_cn


def test_architecture_deep_dive_preserves_authority_boundaries() -> None:
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )

    assert "Application DB = business authority" in architecture
    assert "Application DB" in architecture
    assert "ResearchRun" in architecture
    assert "EvidenceLedger" in architecture
    assert "LangSmith" in architecture
    assert "diagnostics only" in architecture or "diagnostic-only" in architecture
    assert "not business ledgers" in architecture


def test_demo_console_docs_state_deterministic_video_boundary() -> None:
    guide = (PROJECT_ROOT / "docs" / "demo-console.md").read_text(encoding="utf-8")

    assert "Demo Video Boundary" in guide
    assert "Portfolio Demo Boundary" not in guide
    assert "deterministic loopback contract demos" in guide
    assert "not live provider research recordings" in guide


def test_operations_docs_cover_release_recovery_boundaries() -> None:
    docs = _combined_docs()

    required_phrases = [
        "canonical DB migration",
        "rollback",
        "legacy table archive/drop",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false",
        "privacy-first trace defaults",
        "run_result_unavailable",
        "no frontend service",
    ]

    for phrase in required_phrases:
        assert phrase in docs


def test_downstream_consumer_contract_is_indexed_and_bounded():
    reference = Path(
        "docs/reference/downstream-consumer-contract.md"
    ).read_text(encoding="utf-8")
    evidence_index = Path("docs/evidence/README.md").read_text(encoding="utf-8")
    integration = Path("docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")
    docs_index = Path("docs/README.md").read_text(encoding="utf-8")

    assert "dra.downstream-consumer.v1" in reference
    assert "supported" in reference
    assert "partial" in reference
    assert "unknown" in reference
    assert "block_fallback" in reference
    assert "must not parse Markdown" in reference
    assert "contract_schema_invalid" in reference
    assert "downstream-consumer-contract-v1.json" in evidence_index
    assert "downstream-consumer-contract.md" in integration
    assert "downstream-consumer-contract.md" in docs_index


def test_agent_evaluation_regression_gate_is_documented_and_required_in_ci():
    paths = [
        PROJECT_ROOT / "docs/reference/agent-evaluation-regression-gate.md",
        PROJECT_ROOT / "docs/evidence/README.md",
        PROJECT_ROOT / "docs/README.md",
        PROJECT_ROOT / "docs/AGENT_INTEGRATION.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "README_CN.md",
        PROJECT_ROOT / "CHANGELOG.md",
    ]
    docs = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    required = (
        "dra.agent-evaluation-cases.v1",
        "dra.agent-evaluation-report.v1",
        "dra.agent-evaluation-comparison.v1",
        "agent_evaluation_gate.py check",
        "cost_estimate",
        "estimate",
        "LangSmith",
        "diagnostics",
        "must not parse Markdown",
        "Claim-level Evidence remains `not_observed`",
    )
    for phrase in required:
        assert phrase in docs
    assert "agent-evaluation-regression-v1.json" in docs
    assert "agent-evaluation-regression-v1.md" in docs
    assert "live observation" in docs.lower()
    assert "deferred" in docs.lower()
    assert "Pydantic owns structural schemas" in docs
    assert "project evaluators own DRA" in docs
    assert "AgentEvals" in docs
    assert "DeepAgents live evaluation" in docs

    forbidden = (
        "billed cost",
        "automatic truth evaluation",
        "v0.1.1 is published",
        "evaluation report is runtime authority",
    )
    for phrase in forbidden:
        assert phrase not in docs

    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    install = workflow.index("pip install --no-deps -r constraints.txt")
    gate = workflow.index("python scripts/agent_evaluation_gate.py check")
    pytest_step = workflow.index("python -m pytest -q")
    assert install < gate < pytest_step
    assert "PYTHON_DOTENV_DISABLED: '1'" in workflow


def test_run_creation_idempotency_contract_is_public_and_bounded():
    api = (PROJECT_ROOT / "docs/reference/api-contract.md").read_text(encoding="utf-8")
    integration = (PROJECT_ROOT / "docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")
    data_models = (PROJECT_ROOT / "docs/reference/data-models.md").read_text(encoding="utf-8")
    identity = (PROJECT_ROOT / "docs/decisions/run-identity-boundaries.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    evidence = (PROJECT_ROOT / "docs/evidence/README.md").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_cn = (PROJECT_ROOT / "README_CN.md").read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for phrase in (
        "Idempotency-Key",
        "[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",
        "run_idempotency_conflict",
        "run_idempotency_key_invalid",
        "run_idempotency_unavailable",
        "idempotent_replay",
        "service-wide",
        "GET /api/runs/{run_id}",
    ):
        assert phrase in api
    for phrase in (
        "--idempotency-key",
        "no automatic retry",
        "same query/profile/thread/scope",
        "request_timeout",
        "connection_failed",
    ):
        assert phrase in integration
    for phrase in (
        "run_create_idempotency_v1",
        "request_schema_version",
        "request_hash",
        "ON DELETE CASCADE",
        "no TTL",
    ):
        assert phrase in data_models
    assert "same-thread independent runs" in identity
    assert "LangGraph" in architecture and "LangSmith" in architecture
    assert "run-creation-idempotency-v1.json" in evidence
    assert "run-creation-idempotency-v1.md" in evidence
    assert "crash_before_schedule_recovery: not_proven" in evidence
    assert "lost-response run identity reconciliation" in readme
    assert "丢失响应后的 run identity reconciliation" in readme_cn
    assert "### Run creation reliability" in changelog
    assert "v0.1.2" not in changelog

    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    proof = "python scripts/run_creation_idempotency_proof.py check"
    assert workflow.count(proof) == 1
    assert workflow.index("python scripts/agent_evaluation_gate.py check") < workflow.index(proof)
    assert workflow.index(proof) < workflow.index("python -m pytest -q")


def test_run_dispatch_reconciliation_contract_is_public_and_bounded():
    paths = [
        PROJECT_ROOT / "docs" / "architecture.md",
        PROJECT_ROOT / "docs" / "decisions" / "framework-runtime-boundaries.md",
        PROJECT_ROOT / "docs" / "reference" / "api-contract.md",
        PROJECT_ROOT / "docs" / "reference" / "data-models.md",
        PROJECT_ROOT / "docs" / "reference" / "state-machines.md",
        PROJECT_ROOT / "docs" / "AGENT_INTEGRATION.md",
        PROJECT_ROOT / "docs" / "README.md",
        PROJECT_ROOT / "docs" / "evidence" / "README.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "README_CN.md",
        PROJECT_ROOT / "CHANGELOG.md",
    ]
    docs = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    required = (
        "run_dispatches_v1",
        "008_run_dispatch_reconciliation",
        "status: started",
        "acceptance acknowledgement",
        "run_dispatch_schedule_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
        "atomic timeout reconciliation",
        "production lifespan, worker, scheduler",
        "three attempts",
        "no backfill",
        ".pre-run-dispatch.bak",
        "run-dispatch-reconciliation-v1.json",
        "run-dispatch-reconciliation-v1.md",
        "commit_before_execution_start_recovery: proven",
        "crash_before_schedule_recovery: proven",
        "exactly_once_execution: not_claimed",
        "running_execution_recovery: not_proven",
        "provider_tool_side_effect_exactly_once: not_claimed",
        "multi_instance_high_availability: not_proven",
        "live_provider_result: not_observed",
    )
    for phrase in required:
        assert phrase in docs

    api = (PROJECT_ROOT / "docs" / "reference" / "api-contract.md").read_text(
        encoding="utf-8"
    )
    assert "HTTP 200" in api
    assert "existing response shape" in api
    assert "asynchronous" in api

    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "application dispatch authority" in architecture
    assert "before Agent invocation" in architecture
    assert "Agent middleware" in architecture

    old_evidence = (
        PROJECT_ROOT / "docs" / "evidence" / "run-creation-idempotency-v1.md"
    ).read_text(encoding="utf-8")
    new_evidence = (
        PROJECT_ROOT / "docs" / "evidence" / "run-dispatch-reconciliation-v1.md"
    ).read_text(encoding="utf-8")
    assert "crash_before_schedule_recovery: not_proven" in old_evidence
    assert "crash_before_schedule_recovery: proven" in new_evidence
    assert (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.3"

    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    old_proof = "python scripts/run_creation_idempotency_proof.py check"
    new_proof = "python scripts/run_dispatch_reconciliation_proof.py check"
    pytest_step = "python -m pytest -q"
    assert workflow.count(new_proof) == 1
    assert workflow.index(old_proof) < workflow.index(new_proof)
    assert workflow.index(new_proof) < workflow.index(pytest_step)


def test_run_failure_cause_status_contract_is_public_and_additive() -> None:
    api = (PROJECT_ROOT / "docs" / "reference" / "api-contract.md").read_text(
        encoding="utf-8"
    )
    status = _section_between(
        api,
        "### GET /api/runs/{run_id}",
        "### GET /api/runs/{run_id}/result",
    )
    result = _section_between(
        api,
        "### GET /api/runs/{run_id}/result",
        "### GET /api/runs/{run_id}/artifacts/{artifact_id}",
    )
    normalized_status = _collapsed(status)

    projections = (
        '{"failure_cause":{"schema_version":"dra.run-failure-cause.v1",'
        '"observation_status":"observed","phase":"execution",'
        '"code":"call_budget_exceeded",'
        '"recorded_at":"2026-07-16T00:00:00+00:00"}}',
        '{"failure_cause":{"schema_version":"dra.run-failure-cause.v1",'
        '"observation_status":"not_observed"}}',
        '{"failure_cause":null}',
    )
    for projection in projections:
        assert projection in status

    for phrase in (
        "exactly one additive top-level field",
        "winning application terminal-transaction time",
        "extra-allow",
        "documentation metadata",
        "not a response filter",
    ):
        assert phrase in normalized_status

    safety_boundary = (
        "The object never exposes `terminal_state_version`, raw exception class "
        "or text, traceback, query, provider payload, retry count, lease or "
        "checkpoint identity, database path, local path, credential, or trace ID."
    )
    assert safety_boundary in normalized_status
    for forbidden in (
        "The object exposes `terminal_state_version`",
        "The object may expose `terminal_state_version`",
        "The object can expose `terminal_state_version`",
    ):
        assert forbidden not in normalized_status

    for phrase in (
        "response, error envelope, and OpenAPI operation remain unchanged",
        "`409 run_failed` does not include `failure_cause`",
        "read the status endpoint",
    ):
        assert phrase in _collapsed(result)

    for path in (PROJECT_ROOT / "README.md", PROJECT_ROOT / "README_CN.md"):
        readme = path.read_text(encoding="utf-8")
        assert "failure_cause" in readme
        assert "docs/reference/api-contract.md" in readme


def test_run_failure_cause_ledger_schema_and_migration_are_public() -> None:
    data_models = (
        PROJECT_ROOT / "docs" / "reference" / "data-models.md"
    ).read_text(encoding="utf-8")
    ledger = _section_between(
        data_models,
        "## Durable run failure cause ledger",
        "## Evidence Entry",
    )
    normalized_ledger = _collapsed(ledger)

    for phrase in (
        "dra.run-failure-cause.v1",
        "009_run_failure_cause_v1",
        "run-failure-cause-v1",
        "run_failure_causes_v1",
    ):
        assert phrase in normalized_ledger

    storage_rows = _markdown_table_rows(
        ledger,
        header=("Column", "Contract"),
    )
    storage_columns = tuple(_inline_code_value(row[0]) for row in storage_rows)
    expected_storage_columns = (
        "run_id",
        "observation_status",
        "terminal_state_version",
        "phase",
        "code",
        "recorded_at",
    )
    assert len(storage_rows) == 6
    assert len(set(storage_columns)) == 6
    assert storage_columns == expected_storage_columns

    taxonomy_rows = _markdown_table_rows(
        ledger,
        header=("Phase", "Code"),
    )
    taxonomy = tuple(
        (_inline_code_value(row[0]), _inline_code_value(row[1]))
        for row in taxonomy_rows
    )
    expected_taxonomy = (
        ("dispatch", "run_dispatch_schedule_failed"),
        ("dispatch", "run_dispatch_start_failed"),
        ("dispatch", "run_dispatch_start_timeout"),
        ("dispatch", "run_dispatch_lease_expired"),
        ("execution", "call_budget_exceeded"),
        ("execution", "recursion_limit_exceeded"),
        ("execution", "invalid_research_packet"),
        ("execution", "missing_research_packet"),
        ("execution", "run_timeout"),
        ("execution", "cancelled"),
        ("execution", "execution_error"),
        ("finalization", "run_timeout"),
        ("finalization", "cancelled"),
        ("finalization", "run_finalization_failed"),
    )
    assert len(taxonomy_rows) == 14
    assert len(set(taxonomy)) == 14
    assert taxonomy == expected_taxonomy

    for phrase in (
        "positive `terminal_state_version` equal to the winning failed run `state_version`",
        "`recorded_at` equals the failed run and segment `updated_at`",
        "Historical `not_observed` rows",
        "without an inferred diagnosis",
        "Nonfailed runs have no cause row",
        "fail closed",
        "marker is present",
        "verification only",
        "never inserts, infers, or repairs",
        "<configured-db>.pre-run-failure-cause.bak",
        "stop the service and all application writers",
        "preserve the failed database for diagnosis",
        "restore the complete dedicated pre-009 backup",
        "must not delete only the table or marker from a live database",
    ):
        assert phrase in normalized_ledger


def test_run_failure_cause_authority_and_framework_reuse_are_public() -> None:
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    decision = (
        PROJECT_ROOT / "docs" / "decisions" / "framework-runtime-boundaries.md"
    ).read_text(encoding="utf-8")
    authority = _section_between(
        decision,
        "## Durability And Authority",
        "## Trade-offs",
    )
    normalized_authority = _collapsed(authority)

    for phrase in (
        "Durable Failure-Cause Authority",
        "application database",
        "terminal transaction",
        "exact dispatch fence",
        "status-only projection",
        "result endpoint remains unchanged",
        "not exactly-once execution",
        "not hard preemption",
        "not provider diagnosis",
        "not multi-instance high availability",
        "not a billing record",
    ):
        assert phrase in _collapsed(architecture)

    for phrase in (
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "GraphRecursionError",
        "Pydantic",
        "FastAPI",
        "asyncio",
        "SQLite",
    ):
        assert phrase in normalized_authority

    for required_boundary in (
        "Only the winning application transaction converts an allowed signal "
        "into a durable public code; framework error text and trace metadata are "
        "not persisted as the cause.",
        "The feature adds no new Agent middleware or DeepAgents middleware.",
        "LangGraph `TimeoutPolicy` is rejected because it limits a graph node "
        "attempt rather than the whole application run.",
        "LangGraph checkpoint/store and LangSmith trace data are also rejected "
        "as failure-cause business authority because they cannot join the run, "
        "segment, Evidence, and cause in the same application transaction.",
    ):
        assert required_boundary in normalized_authority

    for forbidden in (
        "framework error text and trace metadata are persisted as the cause",
        "The feature adds new Agent middleware",
        "LangGraph `TimeoutPolicy` is accepted",
        "LangGraph checkpoint/store and LangSmith trace data are accepted as "
        "failure-cause business authority",
        "LangGraph checkpoint/store and LangSmith trace data are failure-cause "
        "business authority",
    ):
        assert forbidden not in normalized_authority


def test_run_failure_cause_timeout_cancel_and_dispatch_boundaries_are_public() -> None:
    state_machines = (
        PROJECT_ROOT / "docs" / "reference" / "state-machines.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "`unset` to `timeout` or `cancelled`",
        "first transition wins",
        "timeout is claimed before the inner task receives cancellation",
        "attempts one and two",
        "no canonical cause",
        "exact third attempt",
        "run_dispatch_schedule_failed",
        "run_dispatch_start_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
        "pre-start infrastructure cancellation",
        "attempt four is never created",
        "cooperative deadline",
        "not hard wall-clock preemption",
        "`failed` is execution-terminal",
        "review or publication writer",
    ):
        assert phrase in _collapsed(state_machines)


def test_run_failure_cause_consumer_compatibility_is_explicit() -> None:
    downstream = (
        PROJECT_ROOT / "docs" / "reference" / "downstream-consumer-contract.md"
    ).read_text(encoding="utf-8")
    integration = (PROJECT_ROOT / "docs" / "AGENT_INTEGRATION.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "frozen `dra.downstream-consumer.v1` projection",
        "ignores the additive upstream `failure_cause` field",
        "persistent failure cause remains `unknown` inside v1",
        "fixture bytes and checksum remain unchanged",
        "`409 run_failed` remains unchanged",
    ):
        assert phrase in _collapsed(downstream)

    for phrase in (
        "raw terminal status projection",
        "may carry `failure_cause`",
        "`result --run-id` and `run --wait --result` remain on the unchanged result contract",
        "`run_wait_timeout` is a client polling deadline",
        "application-owned terminal `execution/run_timeout` or `finalization/run_timeout`",
        "No new Tool Client command or model is required",
    ):
        assert phrase in _collapsed(integration)


def test_run_failure_cause_proof_is_indexed_and_bounded() -> None:
    json_path = PROJECT_ROOT / "docs" / "evidence" / "run-failure-cause-v1.json"
    markdown_path = PROJECT_ROOT / "docs" / "evidence" / "run-failure-cause-v1.md"
    assert json_path.is_file()
    assert markdown_path.is_file()

    docs_index = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    evidence_index = (PROJECT_ROOT / "docs" / "evidence" / "README.md").read_text(
        encoding="utf-8"
    )
    for link in (
        "[Durable Run Failure Cause Proof](evidence/run-failure-cause-v1.md)",
        "[JSON report](evidence/run-failure-cause-v1.json)",
    ):
        assert link in docs_index
    for link in (
        "[run-failure-cause-v1.json](run-failure-cause-v1.json)",
        "[run-failure-cause-v1.md](run-failure-cause-v1.md)",
    ):
        assert link in evidence_index
    for phrase in (
        "dra.run-failure-cause-proof.v1",
        "fixed 16-case",
        "offline",
        "provider-free",
        "network-free",
        "credential-free",
        "byte-identical",
    ):
        assert phrase in evidence_index

    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    install = "pip install --no-deps -r constraints.txt"
    proof = "python scripts/run_failure_cause_proof.py check"
    broad_suite = "python -m pytest -q"
    assert workflow.count(proof) == 1
    assert (
        workflow.index(install)
        < workflow.index(proof)
        < workflow.index(broad_suite)
    )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            "| `recorded_at` | timezone-aware UTC terminal timestamp for "
            "observed rows; otherwise null |\n",
            "| `recorded_at` | timezone-aware UTC terminal timestamp for "
            "observed rows; otherwise null |\n"
            "| `provider` | forbidden seventh public storage column |\n",
        ),
        (
            "| `finalization` | `run_finalization_failed` |\n",
            "| `finalization` | `run_finalization_failed` |\n"
            "| `execution` | `provider_error` |\n",
        ),
        (
            "| `dispatch` | `run_dispatch_schedule_failed` |\n",
            "| `dispatch` | `run_dispatch_schedule_failed` |\n"
            "| `dispatch` | `run_dispatch_schedule_failed` |\n",
        ),
    ),
    ids=("seventh-column", "fifteenth-code", "duplicate-phase-code"),
)
def test_run_failure_cause_ledger_rejects_deliberate_mutation(
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=PROJECT_ROOT / "docs" / "reference" / "data-models.md",
        replacements=((old, new),),
        contract=test_run_failure_cause_ledger_schema_and_migration_are_public,
    )


@pytest.mark.parametrize(
    ("path", "old", "new", "contract"),
    (
        (
            PROJECT_ROOT / "docs" / "reference" / "api-contract.md",
            "The object never exposes `terminal_state_version`, raw\n"
            "exception class or text, traceback, query, provider payload, "
            "retry count, lease\n"
            "or checkpoint identity, database path, local path, credential, "
            "or trace ID.",
            "The object exposes `terminal_state_version`, raw\n"
            "exception class or text, traceback, query, provider payload, "
            "retry count, lease\n"
            "or checkpoint identity, database path, local path, credential, "
            "or trace ID.",
            test_run_failure_cause_status_contract_is_public_and_additive,
        ),
        (
            PROJECT_ROOT
            / "docs"
            / "decisions"
            / "framework-runtime-boundaries.md",
            "LangGraph checkpoint/store and LangSmith trace data\n"
            "are also rejected as failure-cause business authority because "
            "they cannot join",
            "LangGraph checkpoint/store and LangSmith trace data\n"
            "are accepted as failure-cause business authority because "
            "they can join",
            test_run_failure_cause_authority_and_framework_reuse_are_public,
        ),
    ),
    ids=("status-exposes-private-fields", "framework-becomes-authority"),
)
def test_run_failure_cause_safety_rejects_deliberate_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
    contract: Callable[[], None],
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=((old, new),),
        contract=contract,
    )


@pytest.mark.parametrize(
    ("path", "replacements"),
    (
        (
            PROJECT_ROOT / "docs" / "README.md",
            (
                (
                    "[Durable Run Failure Cause Proof]"
                    "(evidence/run-failure-cause-v1.md)",
                    "Durable Run Failure Cause Proof: "
                    "evidence/run-failure-cause-v1.md",
                ),
                (
                    "[JSON report](evidence/run-failure-cause-v1.json)",
                    "JSON report: evidence/run-failure-cause-v1.json",
                ),
            ),
        ),
        (
            PROJECT_ROOT / "docs" / "evidence" / "README.md",
            (
                (
                    "[run-failure-cause-v1.json](run-failure-cause-v1.json)",
                    "run-failure-cause-v1.json",
                ),
                (
                    "[run-failure-cause-v1.md](run-failure-cause-v1.md)",
                    "run-failure-cause-v1.md",
                ),
            ),
        ),
    ),
    ids=("docs-index-plain-filenames", "evidence-index-plain-filenames"),
)
def test_run_failure_cause_links_reject_deliberate_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    replacements: tuple[tuple[str, str], ...],
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=replacements,
        contract=test_run_failure_cause_proof_is_indexed_and_bounded,
    )
