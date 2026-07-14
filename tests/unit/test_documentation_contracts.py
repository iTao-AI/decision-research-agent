from __future__ import annotations

from pathlib import Path
import subprocess


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
    assert (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.2"

    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    old_proof = "python scripts/run_creation_idempotency_proof.py check"
    new_proof = "python scripts/run_dispatch_reconciliation_proof.py check"
    pytest_step = "python -m pytest -q"
    assert workflow.count(new_proof) == 1
    assert workflow.index(old_proof) < workflow.index(new_proof)
    assert workflow.index(new_proof) < workflow.index(pytest_step)
