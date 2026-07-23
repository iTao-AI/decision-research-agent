from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
import subprocess

import pytest

from api.run_failure_cause_models import RUN_FAILURE_CAUSE_CODES


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
    PROJECT_ROOT / "docs" / "operations" / "secure-local-runtime.md",
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


def test_deepseek_provider_protocol_documentation_matches_runtime():
    env_example = (
        PROJECT_ROOT / ".env.example"
    ).read_text(encoding="utf-8")
    reference = (
        PROJECT_ROOT / "docs/reference/external-services.md"
    ).read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY=" in env_example
    assert "DEEPSEEK_API_BASE=https://api.deepseek.com" in env_example
    assert "DEEPSEEK_API_KEY" in reference
    assert "DEEPSEEK_API_BASE" in reference
    assert "OPENAI_API_KEY" in reference
    assert "OPENAI_BASE_URL" in reference
    assert "official LangChain DeepSeek integration" in reference
    assert "reasoning_content" in reference
    assert "provider protocol state" in reference
    assert "not Evidence" in reference
    assert "does not prove a live provider result" in reference
    assert "## Optional LangSmith Diagnostics" in reference
    assert "deepseek_provider_selected" in reference
    assert "deepseek_reasoning_protocol_validated" in reference
    assert "deepseek_reasoning_protocol_rejected" in reference
    assert "model_fallback_activated" in reference
    assert "LANGSMITH_TRACING=false" in reference
    assert "LANGSMITH_HIDE_INPUTS=true" in reference
    assert "LANGSMITH_HIDE_OUTPUTS=true" in reference
    assert "bounded-live" in reference
    assert "separate operator authorization" in reference
    assert "`LLM_THINKING_MODE`" in reference
    assert "`enabled` or `disabled`" in reference
    assert "省略 `tool_choice`" in reference
    assert "`timeout=120`" in reference
    assert "# LLM_QWEN_MAX=deepseek-v4-pro" in env_example
    assert "# LLM_QWEN_MAX=deepseek-chat" not in env_example
    assert "`deepseek-chat`" in reference
    assert "`deepseek-reasoner`" in reference
    assert "2026-07-24 15:59 UTC" in reference


V015_RELEASE_H2_ORDER = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)


def _v0_1_5_release_sections(notes: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", notes, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == V015_RELEASE_H2_ORDER
    return {
        match.group(1): notes[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(notes)
        ]
        for index, match in enumerate(matches)
    }


def _assert_v0_1_5_release_documentation_contract() -> None:
    release_notes_path = PROJECT_ROOT / "docs" / "releases" / "v0.1.5.md"
    release_notes = release_notes_path.read_text(encoding="utf-8")
    sections = _v0_1_5_release_sections(release_notes)
    normalized_sections = {
        heading: _collapsed(body) for heading, body in sections.items()
    }
    verification = normalized_sections["Required Verification"]
    known_limits = normalized_sections["Known Limits"]

    assert (
        "The deterministic proof, required Docker lane, and post-publication "
        "archive smoke are separate evidence boundaries."
        in verification
    )
    assert "python scripts/secure_local_runtime_proof.py check" in verification
    assert "npm audit --audit-level=moderate" in verification

    for complete_non_claim in (
        "This preparation document does not claim that a `v0.1.5` tag, GitHub "
        "Release, post-publication archive smoke, deployment, or live research "
        "has completed.",
        "This release does not provide TLS, caller identity, per-user "
        "authorization, RBAC, rate limiting, trusted-proxy handling, hosted "
        "production, or production deployment.",
        "No live-provider research or provider-quality claim is made by the "
        "deterministic proof, required Docker lane, or this release preparation.",
    ):
        assert complete_non_claim in known_limits
        for heading, body in normalized_sections.items():
            if heading != "Known Limits":
                assert complete_non_claim not in body

    for verification_owned in (
        "python scripts/secure_local_runtime_proof.py check",
        "npm audit --audit-level=moderate",
        "The deterministic proof, required Docker lane, and post-publication "
        "archive smoke are separate evidence boundaries.",
    ):
        for heading, body in normalized_sections.items():
            if heading != "Required Verification":
                assert verification_owned not in body

    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    health_contract = (
        "MySQL health gates backend startup; the backend declares an exact "
        "process/service health check."
    )
    assert health_contract in _collapsed(changelog)
    assert health_contract in _collapsed(sections["Changes"])

    public_corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "README_CN.md",
            PROJECT_ROOT / "SECURITY.md",
            PROJECT_ROOT / "docs" / "README.md",
            release_notes_path,
        )
    ).lower()
    for premature_claim in (
        "v0.1.5 is published",
        "v0.1.5 tag created",
        "release tag created",
        "github release published",
        "archive smoke passed",
        "deployment completed",
        "live-provider research completed",
        "the live-provider research and provider-quality claims are made",
        "this release provides tls",
    ):
        assert premature_claim not in public_corpus


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


def _assert_final_pr_body_reconciliation_contract() -> None:
    governance = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contributing = (PROJECT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    for text in (governance, contributing):
        assert "pending merge gates use `[ ]`" in text
        assert "satisfied merge gates must be updated to `[x]`" in text
        assert "final PR-body reconciliation" in text
        assert "persisted PR body" in text
        assert "completed CI" in text
        assert "merge authorization" in text
        assert "mergeability" in text
        assert "review blockers" in text
        assert "cleanup" in text
        assert "remaining risk" in text
        assert "non-claims" in text
        assert "must not report the PR as fully closed" in text


def test_contributor_governance_requires_final_pr_body_reconciliation() -> None:
    _assert_final_pr_body_reconciliation_contract()


def test_pr_body_contract_rejects_satisfied_gate_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=PROJECT_ROOT / "AGENTS.md",
        replacements=(("updated to `[x]`", "updated to `[ ]`"),),
        contract=_assert_final_pr_body_reconciliation_contract,
    )


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
        "python api/server.py",
        "does not accept or store API credentials",
        "Static Demo",
        "Live Backend",
        "http://127.0.0.1:<port>",
        '{"status":"ok","service":"decision-research-agent"}',
    ]

    for phrase in required:
        assert phrase in guide


def test_secure_local_runtime_access_boundary_is_public() -> None:
    paths = [
        PROJECT_ROOT / "docs" / "reference" / "api-contract.md",
        PROJECT_ROOT / "docs" / "architecture.md",
        PROJECT_ROOT / "docs" / "getting-started.md",
        PROJECT_ROOT / "docs" / "AGENT_INTEGRATION.md",
        PROJECT_ROOT / "SECURITY.md",
    ]
    contract = _collapsed("\n".join(path.read_text(encoding="utf-8") for path in paths))

    required = [
        "direct peer and literal Host must both be loopback",
        "X-API-Key",
        "DECISION_RESEARCH_AGENT_API_KEY",
        "127.0.0.1",
        "reload disabled",
        "Uvicorn warning-level logging",
        "CORS and Origin checks are not authentication",
        "WebSocket credentials are header-only",
        "query credentials are rejected",
        "operator-owned TLS",
        "not a supported hosted deployment",
        "independent feature-owned gates",
        "API_SECRET=",
        "no sentinel value is accepted",
    ]
    for phrase in required:
        assert phrase in contract

def test_public_docs_do_not_claim_unshipped_compose_log_hardening() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    container_command = json.loads(
        next(
            line.removeprefix("CMD ")
            for line in dockerfile.splitlines()
            if line.startswith("CMD [")
        )
    )
    public_docs = _collapsed(
        "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                PROJECT_ROOT / "SECURITY.md",
                PROJECT_ROOT / "docs" / "architecture.md",
                PROJECT_ROOT / "docs" / "reference" / "api-contract.md",
            )
        )
    )
    implementation_plan = (
        PROJECT_ROOT
        / "docs"
        / "superpowers"
        / "plans"
        / "2026-07-18-secure-local-runtime-implementation.md"
    ).read_text(encoding="utf-8")

    compose_has_warning_logging = "--log-level=warning" in container_command or any(
        current == "--log-level" and following == "warning"
        for current, following in zip(container_command, container_command[1:])
    )
    if not compose_has_warning_logging:
        assert "Compose warning-level hardening is deferred to PR B" in public_docs
        assert "source and Compose launchers" not in public_docs
        assert "source/Compose launchers keep Uvicorn at warning level" not in (
            implementation_plan
        )
    else:
        assert (
            "source and Compose launchers use Uvicorn warning-level logging"
            in public_docs
        )
        assert "Compose warning-level hardening is deferred to PR B" not in public_docs
        assert "Compose warning-level hardening is not delivered" not in public_docs


def test_secure_local_container_delivery_is_public_and_bounded() -> None:
    operations_path = (
        PROJECT_ROOT / "docs" / "operations" / "secure-local-runtime.md"
    )
    assert operations_path.is_file()
    operations = _collapsed(operations_path.read_text(encoding="utf-8"))
    combined = _collapsed(
        "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                PROJECT_ROOT / "README.md",
                PROJECT_ROOT / "README_CN.md",
                PROJECT_ROOT / "docs" / "README.md",
                PROJECT_ROOT / "docs" / "architecture.md",
                PROJECT_ROOT / "docs" / "getting-started.md",
                PROJECT_ROOT / "SECURITY.md",
                PROJECT_ROOT / "docs" / "evidence" / "README.md",
                operations_path,
            )
        )
    )

    for phrase in (
        "API_SECRET",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_PASSWORD",
        "127.0.0.1:8000:8000",
        "127.0.0.1:3306:3306",
        "0.0.0.0",
        "cap_drop:",
        "- ALL",
        "no-new-privileges:true",
        "root UID is intentionally retained",
        "DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE",
        "default repository `.env`",
        "does not create a second runtime mode",
        "docker compose config --quiet",
        "docker compose up -d --build backend",
        "secrets.token_urlsafe",
        "0o600",
        "## Migration And Existing Volumes",
        "## Rollback",
        "no database migration",
        "Existing named",
        "deterministic proof",
        "required Docker lane",
        "tag-archive smoke",
    ):
        assert phrase in operations

    for phrase in (
        "CORS and Origin checks are not authentication",
        "shared API key",
        "TLS",
        "identity",
        "authorization",
        "RBAC",
        "process/service identity",
        "database, provider, model, tool, or research readiness",
        "source launcher",
        "Compose",
        "container-internal",
        "host publication",
        "no provider, model, or tool request was observed",
        "not a supported hosted deployment",
    ):
        assert phrase in combined

    assert "Compose warning-level hardening is deferred to PR B" not in combined
    assert "Compose warning-level hardening is not delivered" not in combined
    assert "runs as a non-root user" not in combined
    assert "production-ready hosted service" not in combined


def test_secure_local_runtime_docs_and_evidence_are_discoverable() -> None:
    discovery = {
        PROJECT_ROOT / "README.md": (
            "[Secure Local Runtime Operations]"
            "(docs/operations/secure-local-runtime.md)",
            "[Secure Local Runtime v1 Proof]"
            "(docs/evidence/secure-local-runtime-v1.md)",
        ),
        PROJECT_ROOT / "README_CN.md": (
            "[Secure Local Runtime Operations]"
            "(docs/operations/secure-local-runtime.md)",
            "[Secure Local Runtime v1 Proof]"
            "(docs/evidence/secure-local-runtime-v1.md)",
        ),
        PROJECT_ROOT / "docs" / "README.md": (
            "[Secure Local Runtime]"
            "(operations/secure-local-runtime.md)",
            "[Secure Local Runtime v1 Proof]"
            "(evidence/secure-local-runtime-v1.md)",
            "[JSON report](evidence/secure-local-runtime-v1.json)",
        ),
        PROJECT_ROOT / "docs" / "evidence" / "README.md": (
            "[secure-local-runtime-v1.json](secure-local-runtime-v1.json)",
            "[secure-local-runtime-v1.md](secure-local-runtime-v1.md)",
        ),
    }
    for path, links in discovery.items():
        text = path.read_text(encoding="utf-8")
        for link in links:
            assert link in text

    evidence_index = (
        PROJECT_ROOT / "docs" / "evidence" / "README.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "dra.secure-local-runtime.v1",
        "deterministic 16-case",
        "container-configuration",
        "real image build",
        "required Docker lane",
    ):
        assert phrase in evidence_index


def test_v0_1_5_release_prep_documents_secure_local_runtime_boundaries() -> None:
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "v0.1.5.md"
    ).read_text(encoding="utf-8")
    current_discovery = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "README_CN.md",
            PROJECT_ROOT / "docs" / "README.md",
            PROJECT_ROOT / "SECURITY.md",
        )
    )
    normalized_notes = _collapsed(release_notes)
    _assert_v0_1_5_release_documentation_contract()

    for phrase in (
        "empty `API_SECRET`",
        "direct peer and literal Host must both be loopback",
        "Compose requires explicit non-empty `API_SECRET`, `MYSQL_ROOT_PASSWORD`, "
        "and `MYSQL_PASSWORD`",
        "loopback-only host publication",
        "WebSocket credentials are header-only",
        "deterministic proof",
        "required Docker lane",
        "post-publication archive smoke",
        "backend container retains its root UID",
    ):
        assert phrase in normalized_notes

    for phrase in (
        "does not provide TLS",
        "caller identity",
        "RBAC",
        "hosted production",
        "production deployment",
        "live-provider research",
    ):
        assert phrase in normalized_notes

    assert "v0.1.5 Release Notes" in current_discovery
    assert "Decision Research Agent v0.1.5" in current_discovery


@pytest.mark.parametrize(
    ("path", "replacements"),
    (
        (
            PROJECT_ROOT / "docs" / "releases" / "v0.1.5.md",
            (
                (
                    "No live-provider research or provider-quality claim is made by the\n"
                    "  deterministic proof, required Docker lane, or this release preparation.",
                    "The live-provider research and provider-quality claims are made by the\n"
                    "  deterministic proof, required Docker lane, and this release preparation.",
                ),
            ),
        ),
        (
            PROJECT_ROOT / "SECURITY.md",
            (
                (
                    "that are not part of v0.1.5.",
                    "that are not part of v0.1.5.\n\nGitHub Release published.",
                ),
            ),
        ),
    ),
    ids=("positive-provider-claim", "security-publication-claim"),
)
def test_v0_1_5_documentation_contract_rejects_claim_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    replacements: tuple[tuple[str, str], ...],
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=replacements,
        contract=_assert_v0_1_5_release_documentation_contract,
    )


def test_v0_1_5_documentation_contract_rejects_swapped_section_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = PROJECT_ROOT / "docs" / "releases" / "v0.1.5.md"
    read_text = Path.read_text
    mutated = read_text(path, encoding="utf-8")
    mutated = mutated.replace("## Required Verification", "## __TEMP__", 1)
    mutated = mutated.replace("## Known Limits", "## Required Verification", 1)
    mutated = mutated.replace("## __TEMP__", "## Known Limits", 1)

    def mutated_read_text(self: Path, *args, **kwargs) -> str:
        if self == path:
            return mutated
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mutated_read_text)
    with pytest.raises(AssertionError):
        _assert_v0_1_5_release_documentation_contract()


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


def test_nested_evidence_capture_documentation_preserves_authority_boundary() -> None:
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    framework_boundary = (
        PROJECT_ROOT / "docs" / "decisions" / "framework-runtime-boundaries.md"
    ).read_text(encoding="utf-8")
    state_machines = (
        PROJECT_ROOT / "docs" / "reference" / "state-machines.md"
    ).read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "nested `internet_search` `ToolMessage`" in _collapsed(architecture)
    assert "not subagent summaries" in _collapsed(architecture)
    assert "`subgraphs=True`" in _collapsed(framework_boundary)
    assert "fails closed" in _collapsed(framework_boundary)
    assert "existing Evidence extractor" in _collapsed(framework_boundary)
    assert "deterministic deduplication" in _collapsed(state_machines)
    assert "exact public HTTPS source URLs" in _collapsed(state_machines)
    assert (
        "does not replace tool-result Evidence authority"
        in _collapsed(state_machines)
    )
    assert "nested subgraph source-tool results" in _collapsed(changelog)


def test_evidence_source_admission_closure_is_documented() -> None:
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-24-evidence-source-admission-closure-design.md"
    )
    plan_path = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-24-evidence-source-admission-closure-implementation.md"
    )
    state_machines = _collapsed(
        (
            PROJECT_ROOT / "docs/reference/state-machines.md"
        ).read_text(encoding="utf-8")
    )
    bounded_live = _collapsed(
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
        ).read_text(encoding="utf-8")
    )

    assert design_path.exists()
    assert plan_path.exists()
    design = design_path.read_text(encoding="utf-8")
    plan = plan_path.read_text(encoding="utf-8")
    assert len(design.splitlines()) <= 250
    assert len(plan.splitlines()) <= 350
    collapsed_design = _collapsed(design)
    for phrase in (
        "producer-admitted URL implies downstream and Evidence receipt acceptance",
        "drop the complete result row without rewriting its URL",
        "`network_search` / `internet_search`",
        "provided_aggregate",
        "No new public error or diagnostic receipt",
    ):
        assert phrase in collapsed_design
    for phrase in (
        "RED",
        "GREEN",
        "provider-free",
        "required Docker authority",
        "No `observe-live`",
    ):
        assert phrase in plan
    assert (
        "Only the exact `network_search` / `internet_search` pair creates "
        "generic source Evidence"
    ) in state_machines
    assert (
        "Search-result admission is a strict producer subset of the "
        "downstream compatibility surface"
    ) in bounded_live


def test_demo_console_docs_state_deterministic_video_boundary() -> None:
    guide = (PROJECT_ROOT / "docs" / "demo-console.md").read_text(encoding="utf-8")

    assert "Demo Video Boundary" in guide
    assert "Portfolio Demo Boundary" not in guide
    assert "deterministic loopback contract demos" in guide
    assert "not live provider research recordings" in guide


def test_operations_docs_cover_release_recovery_boundaries() -> None:
    docs = _combined_docs()
    collapsed_docs = _collapsed(docs)

    required_phrases = [
        "canonical DB migration",
        "rollback",
        "legacy table archive/drop",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=false",
        "privacy-first trace defaults",
        "run_result_unavailable",
    ]

    for phrase in required_phrases:
        assert phrase in docs

    assert (
        "The current Console does not expose review controls and does not own review authority."
        in collapsed_docs
    )
    assert (
        "The current Console does not expose verification controls and does not own verification authority."
        in collapsed_docs
    )


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
    assert (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.5"

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


def test_artifact_delivery_contract_is_canonical_and_snapshot_consistent() -> None:
    api = (PROJECT_ROOT / "docs" / "reference" / "api-contract.md").read_text(
        encoding="utf-8"
    )
    artifact_section = _section_between(
        api,
        "### GET /api/runs/{run_id}/artifacts/{artifact_id}",
        "### GET /api/profiles/{profile_id}",
    )

    for phrase in (
        "current canonical deliverable",
        "same SQLite request snapshot",
        "ready fallback artifact",
        "does not expose historical artifact content",
        '`404 {"detail":"Artifact 不存在"}`',
    ):
        assert phrase in artifact_section
    for code in (
        "run_not_found",
        "run_not_terminal",
        "run_failed",
        "run_review_required",
        "run_delivery_blocked",
        "run_result_unavailable",
    ):
        assert code in artifact_section


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


def test_bounded_live_producer_reference_is_discoverable_without_live_evidence() -> None:
    reference_path = (
        PROJECT_ROOT
        / "docs"
        / "reference"
        / "bounded-live-producer-evaluation.md"
    )
    assert reference_path.is_file()
    reference = reference_path.read_text(encoding="utf-8")
    normalized_reference = " ".join(reference.split())
    for phrase in (
        "python scripts/bounded_live_producer_proof.py check",
        "python scripts/bounded_live_producer_proof.py observe-live",
        "3,450 seconds",
        "supported",
        "accept_draft",
        "estimate-only",
        "No provider-backed observation claim",
        "not exactly-once execution",
        "not a billing record",
        "not a hosted deployment",
        "regular single-link non-symlink file",
        "one private in-memory snapshot",
        "owner-read-only, single-link ephemeral file",
        "revalidates its inode and exact bytes after the command",
        "verifies the original pathname's directory identity before and after",
        "descriptor-based directory identity",
        "keeps failed removal authority for a close retry",
        "observed command-local replacement or mutation fails closed",
        "do not claim kernel-level pathname immutability",
        "same Git repository",
        "Every raw Evidence row must match the accepted `run_id` and `segment_id`",
        "`cost_estimate` remains `not_observed`",
        "exact per-call model and rate",
        "outer deadline starts before input and credential validation",
        "publication use only time left after cleanup",
        "Markdown is linked first",
        "JSON machine authority is linked last",
        "A JSON path alone is never authority",
        "unremovable Markdown-only residue is non-authoritative",
        "closed on every path after successful validation",
        "Before project cleanup takes ownership",
        "recorded before the mutation that can leave it behind",
        "Successful exact resource inventories",
        "not a failed inspection exit status",
        "final directory `fsync`",
        "`credential_source_invalid` in the `input` phase",
        "exact locked backend image after build and before any service or provider activity",
        "provider-free fixture and separately authorized live paths use this same precheck authority",
    ):
        assert phrase in normalized_reference

    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "host production dependency graph" in changelog
    assert "exact locked backend image" in changelog

    plan = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    ).read_text(encoding="utf-8")
    normalized_plan = " ".join(plan.split())
    assert (
        "Execute the existing `scripts/secure_local_runtime_proof.py check` inside the exact "
        "locked backend image after build and before any service starts"
        in normalized_plan
    )

    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    design = design_path.read_text(encoding="utf-8")
    normalized_design = " ".join(design.split())
    ordered_lifecycle = (
        "6. build the backend image from the tracked snapshot;",
        "7. execute `scripts/secure_local_runtime_proof.py check` inside the exact locked backend "
        "image and require it to pass before any MySQL, backend, or provider activity;",
        "8. start MySQL and backend under the unique project;",
    )
    for step in ordered_lifecycle:
        assert step in normalized_design
    lifecycle_positions = tuple(
        normalized_design.index(step) for step in ordered_lifecycle
    )
    assert lifecycle_positions == tuple(sorted(lifecycle_positions))

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_cn = (PROJECT_ROOT / "README_CN.md").read_text(encoding="utf-8")
    docs_index = (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    integration = (PROJECT_ROOT / "docs/AGENT_INTEGRATION.md").read_text(
        encoding="utf-8"
    )
    evidence_index = (PROJECT_ROOT / "docs/evidence/README.md").read_text(
        encoding="utf-8"
    )
    root_link = (
        "[Bounded Live Producer Evaluation]"
        "(docs/reference/bounded-live-producer-evaluation.md)"
    )
    docs_link = (
        "[Bounded Live Producer Evaluation]"
        "(reference/bounded-live-producer-evaluation.md)"
    )
    evidence_link = (
        "[Bounded Live Producer Evaluation]"
        "(../reference/bounded-live-producer-evaluation.md)"
    )
    assert root_link in readme
    assert root_link in readme_cn
    assert docs_link in docs_index
    assert docs_link in integration
    assert evidence_link in evidence_index

    json_evidence = PROJECT_ROOT / "docs/evidence/bounded-live-producer-v1.json"
    markdown_evidence = PROJECT_ROOT / "docs/evidence/bounded-live-producer-v1.md"
    assert not json_evidence.exists()
    assert not markdown_evidence.exists()
    assert "No live report is committed" in readme
    assert "未提交 live report" in readme_cn
    assert "No live report is committed" in evidence_index


@pytest.mark.parametrize(
    "replacement",
    (
        "7. continue directly from the build to service startup;",
        "7. start MySQL and backend under the unique project;\n"
        "8. execute `scripts/secure_local_runtime_proof.py check` inside the exact locked "
        "backend image after service startup;",
    ),
    ids=("missing-locked-image-precheck", "precheck-after-service-start"),
)
def test_bounded_live_producer_design_rejects_precheck_order_mutation(
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=design_path,
        replacements=(
            (
                "7. execute `scripts/secure_local_runtime_proof.py check` inside the exact locked "
                "backend image and\n   require it to pass before any MySQL, backend, or provider "
                "activity;",
                replacement,
            ),
        ),
        contract=test_bounded_live_producer_reference_is_discoverable_without_live_evidence,
    )


def test_bounded_result_diagnostic_receipt_is_scoped_and_discoverable() -> None:
    reference_path = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    )
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    plan_path = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    )
    reference = " ".join(reference_path.read_text(encoding="utf-8").split())
    design = " ".join(design_path.read_text(encoding="utf-8").split())
    plan = " ".join(plan_path.read_text(encoding="utf-8").split())
    for text in (design, plan):
        assert "### Post-Observation Result Diagnostic Amendment" in text
        assert "the only exception to Change 1's prohibition on output-path options" in text
        assert "does not permit an arbitrary filename or general output root" in text
    for phrase in (
        "dra.bounded-live-producer-result-diagnostic.v1",
        "--diagnostic-dir",
        "bounded-live-producer-result-diagnostic-v1.json",
        "existing public error envelope remains unchanged",
        "not live evidence",
        "does not authorize a retry",
        "fixed basename",
        "after cleanup",
        "4 KiB",
        "owner-only repo-external directory",
        "invoking UID may modify the operator-owned file during or after publication",
        "Every consumer must strictly validate the receipt before use",
        "does not claim same-UID pathname immutability",
    ):
        assert phrase in reference
    for stage in (
        "connection",
        "response_status",
        "response_body",
        "response_json",
        "response_identity",
        "consumer_contract",
        "projection_disposition",
    ):
        assert f"`{stage}`" in reference
    for exact_row in (
        "| `connection` | `connection_failed` |",
        "| `response_status` | `response_status_invalid` |",
        "| `response_body` | `response_read_failed`, `response_size_exceeded` |",
        "| `response_json` | `response_utf8_invalid`, `response_json_invalid`, `response_not_object` |",
        "| `response_identity` | `run_identity_mismatch` |",
        "| `consumer_contract` | `contract_result_invalid`, `contract_schema_invalid` |",
        "| `projection_disposition` | `projection_disposition_invalid` |",
    ):
        assert exact_row in reference
    for forbidden in (
        "raw response is retained",
        "automatically retries",
        "new REST error contract",
        "diagnostic receipt is canonical",
        "permits an arbitrary filename",
    ):
        assert forbidden not in " ".join((reference, design, plan))


@pytest.mark.parametrize(
    ("path", "old", "new"),
    (
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md",
            "### Post-Observation Result Diagnostic Amendment",
            "### Removed Result Diagnostic Amendment",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "--diagnostic-dir",
            "--diagnostic-file",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md",
            "does not permit an arbitrary filename or general output root",
            "permits an arbitrary filename",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "| `response_json` | `response_utf8_invalid`, `response_json_invalid`, `response_not_object` |",
            "| `response_json` | invalid JSON |",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "does not claim same-UID pathname immutability",
            "prevents same-UID concurrent replacement",
        ),
    ),
    ids=(
        "missing-amendment",
        "arbitrary-filename-option",
        "scope-expanded",
        "reason-registry-collapsed",
        "same-uid-boundary-overclaimed",
    ),
)
def test_bounded_result_diagnostic_receipt_rejects_documentation_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=((old, new),),
        contract=test_bounded_result_diagnostic_receipt_is_scoped_and_discoverable,
    )


def test_bounded_run_failure_diagnostic_receipt_is_scoped_and_discoverable() -> None:
    reference_path = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    )
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    raw_reference = reference_path.read_text(encoding="utf-8")
    reference = " ".join(raw_reference.split())
    design = " ".join(design_path.read_text(encoding="utf-8").split())
    run_failure_section = _collapsed(
        _section_between(
            raw_reference,
            "### Run Failure Diagnostic Receipt v1",
            "### Evidence Diagnostic Receipt v1",
        )
    )

    for phrase in (
        "dra.bounded-live-producer-run-failure-diagnostic.v1",
        "bounded-live-producer-run-failure-diagnostic-v1.json",
        "status-before-result",
        "No failed, fallback, delivery-blocked, or malformed terminal state requests `/result`",
        "`cleanup_status` is exactly `succeeded` or `failed`",
        "preflight rejects the directory if any fixed filename already exists",
        "at most one receipt",
        "Result Diagnostic Receipt v1 remains byte- and behavior-compatible",
        "application-owned `RUN_FAILURE_CAUSE_CODES` matrix",
        "non-authoritative operator diagnostic",
        "strictly validate",
        "separately authorized one-shot live observation",
        "no API, database, Agent runtime, canonical result, Evidence, dependency, VERSION, or release change",
    ):
        assert phrase in reference

    for phase, codes in RUN_FAILURE_CAUSE_CODES.items():
        rendered_codes = ", ".join(f"`{code}`" for code in sorted(codes))
        assert f"| `{phase}` | {rendered_codes} |" in reference

    assert "`cleanup_status` is exactly `succeeded` or `failed`" in run_failure_section

    for exact_row in (
        "| `consumer_projection_invalid / result` | Result Diagnostic Receipt v1 | `bounded-live-producer-result-diagnostic-v1.json` |",
        "| other typed `run_failed / observe` | Run Failure Diagnostic Receipt v1 | `bounded-live-producer-run-failure-diagnostic-v1.json` |",
    ):
        assert exact_row in reference

    for omitted in (
        "raw body or content",
        "run, thread, or segment identity",
        "timestamp",
        "HTTP status or byte count",
        "provider or model identity",
        "path, log, trace, or credential material",
    ):
        assert omitted in reference

    assert "### Post-Observation Run Failure Diagnostic Amendment" in design
    assert "status-before-result" in design
    assert "sibling run-failure receipt" in design
    assert "no live-success claim or evidence publication" in design


@pytest.mark.parametrize(
    ("path", "old", "new"),
    (
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "`run_dispatch_lease_expired`",
            "`run_dispatch_unknown`",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "| `finalization` | `cancelled`, `run_finalization_failed`, `run_timeout` |",
            "| `execution` | `cancelled`, `run_finalization_failed`, `run_timeout` |",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "| other typed `run_failed / observe` | Run Failure Diagnostic Receipt v1 | `bounded-live-producer-run-failure-diagnostic-v1.json` |",
            "| other typed `run_failed / observe` | Run Failure Diagnostic Receipt v1 | `bounded-live-producer-result-diagnostic-v1.json` |",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "`cleanup_status` is exactly `succeeded` or `failed`",
            "`cleanup_status` may also be `not_started`",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "bounded-live-producer-result-diagnostic-v1.json",
            "bounded-live-producer-result-receipt-v1.json",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "at most one receipt",
            "both receipts",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md",
            "no live-success claim or evidence publication",
            "records a successful live observation",
        ),
    ),
    ids=(
        "missing-failure-code",
        "cross-phase-code",
        "swapped-filename",
        "widened-cleanup-status",
        "changed-result-filename",
        "both-receipts-claim",
        "live-success-overclaim",
    ),
)
def test_bounded_run_failure_diagnostic_rejects_documentation_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=((old, new),),
        contract=test_bounded_run_failure_diagnostic_receipt_is_scoped_and_discoverable,
    )


def test_canonical_report_completion_and_fallback_failure_contracts_are_current() -> None:
    state_machines = (PROJECT_ROOT / "docs/reference/state-machines.md").read_text(
        encoding="utf-8"
    )
    normalized_state_machines = " ".join(state_machines.split())
    for phrase in (
        "one run-scoped correction",
        "native `write_file` tool",
        "registered before the existing call-limit middleware",
        "reverse `after_model` execution accounts for the completed call",
        "does not enlarge the existing model, tool, or recursion budgets",
        "does not promote chat text or fallback content",
    ):
        assert phrase in normalized_state_machines

    failure_rows = (
        (
            PROJECT_ROOT
            / "docs/reference/bounded-live-producer-evaluation.md"
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
        ),
    )
    expected_result_row = (
        "`run_fallback_rejected`, `consumer_projection_invalid`, "
        "`artifact_invalid`, `artifact_hash_mismatch`"
    )
    for path in failure_rows:
        normalized = " ".join(path.read_text(encoding="utf-8").split())
        assert expected_result_row in normalized

    reference = " ".join(failure_rows[0].read_text(encoding="utf-8").split())
    assert (
        "A structurally valid fallback result maps to `run_fallback_rejected` "
        "in the `result` phase"
    ) in reference
    assert (
        "Malformed result or consumer projection data remains "
        "`consumer_projection_invalid`"
    ) in reference
    assert (
        "Only an exact canonical `409` `run_result_unavailable` envelope with "
        "bounded keys and types, `retryable=true`, and the requested `run_id` "
        "maps to `artifact_invalid`"
    ) in reference
    assert (
        "`contract_artifact_invalid` maps to `artifact_invalid` in the `result` "
        "phase, while defensive `contract_state_invalid` maps to "
        "`run_state_invalid` in the `observe` phase"
    ) in reference


def test_bounded_live_targeted_runtime_repair_amendment_is_scoped() -> None:
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    plan_path = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    )
    common_phrases = (
        "### Post-Observation Targeted Runtime Repair Amendment",
        "separately authorized after a bounded observation exposed a runtime closure defect",
        "generic coordinator canonical completion middleware and precise fallback failure classification",
        "native LangChain `after_model` hook with `jump_to=\"model\"` and the "
        "DeepAgents `write_file` tool",
        "registered before the existing call-limit middleware",
        "reverse `after_model` execution",
        "remains within the existing model, tool, and recursion budgets",
        "No live-success claim is made and no live evidence is published.",
        "does not change REST/OpenAPI, database, canonical result or Evidence authority, the "
        "provider contract, VERSION, dependencies, CI, or release metadata",
    )
    for path in (design_path, plan_path):
        normalized = " ".join(path.read_text(encoding="utf-8").split())
        for phrase in common_phrases:
            assert phrase in normalized

    design = " ".join(design_path.read_text(encoding="utf-8").split())
    assert "For Change 1, this stage does not add or claim:" in design
    assert "in Change 1, no profile or middleware change" in design
    assert "Add LangChain or DeepAgents middleware to the Change 1 proof" in design

    plan = " ".join(plan_path.read_text(encoding="utf-8").split())
    assert "For Change 1 only, do not modify REST/OpenAPI paths or payloads" in plan
    assert "For the Change 1 implementation commits, no diff in" in plan


@pytest.mark.parametrize(
    ("path", "old", "new"),
    (
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md",
            "The correction remains within the existing model, tool, and recursion\nbudgets",
            "The correction may exceed the existing model, tool, and recursion\nbudgets",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md",
            "The correction remains within the existing model, tool, and recursion\nbudgets",
            "The correction may exceed the existing model, tool, and recursion\nbudgets",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md",
            "For Change 1, this stage does not add or claim:",
            "This stage does not add or claim:",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md",
            "For Change 1 only, do not modify REST/OpenAPI paths or payloads",
            "Do not modify REST/OpenAPI paths or payloads",
        ),
    ),
    ids=(
        "design-budget-expansion",
        "plan-budget-expansion",
        "design-change1-scope-removed",
        "plan-change1-scope-removed",
    ),
)
def test_bounded_live_targeted_runtime_repair_amendment_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=((old, new),),
        contract=test_bounded_live_targeted_runtime_repair_amendment_is_scoped,
    )


def _assert_limiter_diagnostic_sidecar_contract() -> None:
    reference = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    ).read_text(encoding="utf-8")
    design = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    ).read_text(encoding="utf-8")
    plan = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    ).read_text(encoding="utf-8")
    required_reference = (
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_LIMITER_DIAGNOSTICS=true",
        "dra.call-budget-origin-sidecar.v1",
        "dra.bounded-live-producer-call-budget-diagnostic.v1",
        "/app/output/operator-diagnostics/<run_id>/call-budget-v1.json",
        "python /app/scripts/bounded_live_producer_runtime_diagnostics.py read --run-id <run_id>",
        "limiter_kind",
        "tool_scope",
        "run_count",
        "run_limit",
        "thread_count",
        "thread_limit",
        "agent_role",
        "after final cleanup",
        "no API, database, or public failure contract change",
        "no model or budget change",
        "no role inference",
        "no LangSmith authority",
        "no successful live-provider evidence claim",
        "does not authorize an automatic retry",
    )
    assert all(value in reference for value in required_reference)
    collapsed_reference = _collapsed(reference)
    assert (
        "these seven closed limiter fields: `limiter_kind`, `tool_scope`, "
        "`run_count`, `run_limit`, `thread_count`, `thread_limit`, and "
        "`agent_role`."
    ) in collapsed_reference
    assert (
        "tool limits use only `all_tools` or `task`. Unknown tool names "
        "produce no diagnostic."
    ) in collapsed_reference
    amendment = "### Post-Observation Limiter Diagnostic Amendment"
    for historical in (design, plan):
        assert amendment in historical
        section = historical.split(amendment, 1)[1]
        for value in (
            "historical Change 1 boundaries",
            "structured native-exception projection",
            "operator-only transport",
            "default-disabled",
            "no budget",
            "no model",
            "no API, database, canonical result, or Evidence change",
            "no live-success claim",
        ):
            assert value in section
    assert "neither the sidecar nor the receipt authorizes automatic retry" in design
    assert "does not authorize automatic retry" in plan


def test_limiter_diagnostic_sidecar_contract_is_closed_and_non_authoritative() -> None:
    _assert_limiter_diagnostic_sidecar_contract()


@pytest.mark.parametrize(
    ("path", "old", "new"),
    (
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "`run_count`, `run_limit`, `thread_count`, `thread_limit`, and `agent_role`.",
            "`run_count`, `run_limit`, `thread_count`, and `agent_role`.",
        ),
        (
            PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
            "`all_tools` or `task`. Unknown tool names produce\nno diagnostic.",
            "`all_tools`, `task`, or an arbitrary tool name.",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md",
            "operator-only transport",
            "application-authoritative transport",
        ),
        (
            PROJECT_ROOT
            / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md",
            "does not authorize automatic retry",
            "authorizes automatic retry",
        ),
    ),
    ids=(
        "closed-field-removed",
        "arbitrary-tool-name",
        "authority-claim",
        "automatic-retry",
    ),
)
def test_limiter_diagnostic_sidecar_contract_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=path,
        replacements=((old, new),),
        contract=_assert_limiter_diagnostic_sidecar_contract,
    )


EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS = (
    "| `status_projection` | `row_count_exceeded`, `row_shape_invalid`, `ownership_invalid` |",
    "| `consumer_contract` | `required_fields_invalid`, `evidence_id_invalid`, `evidence_id_duplicate`, `source_identity_invalid`, `source_url_invalid`, `retrieved_at_invalid`, `citation_status_invalid`, `verification_status_invalid` |",
    "| `receipt_contract` | `source_url_required`, `source_url_policy_invalid`, `source_identity_too_long`, `retrieved_at_too_long` |",
)


def _assert_evidence_diagnostic_receipt_contract() -> None:
    reference_path = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    )
    design_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-18-bounded-live-producer-evaluation-design.md"
    )
    plan_path = (
        PROJECT_ROOT
        / "docs/superpowers/plans/2026-07-18-bounded-live-producer-evaluation-implementation.md"
    )
    reference = reference_path.read_text(encoding="utf-8")
    design = design_path.read_text(encoding="utf-8")
    plan = plan_path.read_text(encoding="utf-8")
    collapsed_reference = _collapsed(reference)

    for phrase in (
        "dra.bounded-live-producer-evidence-diagnostic.v1",
        "bounded-live-producer-evidence-diagnostic-v1.json",
        "Exactly one of Result, Call Budget, Run Failure, or Evidence Diagnostic Receipt v1",
        "at most one receipt",
        "after final cleanup",
        "`cleanup_status` is exactly `succeeded` or `failed`",
        "`row_count_exceeded` exposes no count",
        "all other reasons expose no rejected value",
        "unknown, missing, multiple distinct recognized reasons, or cross-stage reason publishes no Evidence receipt",
        "contains no IDs, URLs, timestamps, counts, field lengths, content, exception text, paths, credentials, raw input, logs, or traces",
        "non-authoritative operator diagnostic",
        "does not authorize a retry",
        "does not change the public error, API, database, Agent runtime, canonical result, Evidence, or downstream authority",
        "does not run a provider, create live evidence, change `VERSION`, or make a release claim",
    ):
        assert phrase in collapsed_reference

    evidence_section = _section_between(
        reference,
        "### Evidence Diagnostic Receipt v1",
        "## Source, Lifecycle, And Deadlines",
    )
    observed_rows = tuple(
        line
        for line in evidence_section.splitlines()
        if line.startswith("| `")
    )
    assert observed_rows == EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS
    collapsed_evidence_section = _collapsed(evidence_section)
    for sentence in (
        "The Evidence receipt contains no IDs, URLs, timestamps, counts, field lengths, content, exception text, paths, credentials, raw input, logs, or traces.",
        "The Evidence receipt remains a non-authoritative operator diagnostic.",
        "The Evidence receipt does not authorize a retry.",
    ):
        assert sentence in collapsed_evidence_section

    receipt_rows = (
        "| `consumer_projection_invalid / result` | Result Diagnostic Receipt v1 | `bounded-live-producer-result-diagnostic-v1.json` |",
        "| exact `run_failed / observe` call-budget failure with a valid sidecar | Call Budget Diagnostic Receipt v1 | `bounded-live-producer-call-budget-diagnostic-v1.json` |",
        "| other typed `run_failed / observe` | Run Failure Diagnostic Receipt v1 | `bounded-live-producer-run-failure-diagnostic-v1.json` |",
        "| typed `evidence_invalid / evidence` | Evidence Diagnostic Receipt v1 | `bounded-live-producer-evidence-diagnostic-v1.json` |",
    )
    for row in receipt_rows:
        assert row in reference

    assert "### Post-Observation Evidence Diagnostic Amendment" in design
    assert "## Post-Observation Evidence Diagnostic Receipt Implementation Amendment" in plan
    for historical in (design, plan):
        for phrase in (
            "dra.bounded-live-producer-evidence-diagnostic.v1",
            "row_count_exceeded",
            "verification_status_invalid",
            "source_url_required",
            "retrieved_at_too_long",
            "unknown",
            "no receipt",
        ):
            assert phrase in historical


def test_evidence_diagnostic_receipt_contract_is_closed_and_non_authoritative() -> None:
    _assert_evidence_diagnostic_receipt_contract()


def test_evidence_finalization_contract_is_documented() -> None:
    data_models = (
        PROJECT_ROOT / "docs/reference/data-models.md"
    ).read_text(encoding="utf-8")
    state_machines = (
        PROJECT_ROOT / "docs/reference/state-machines.md"
    ).read_text(encoding="utf-8")
    bounded_reference = (
        PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md"
    ).read_text(encoding="utf-8")
    collapsed_data_models = _collapsed(data_models)
    collapsed_state_machines = _collapsed(state_machines)
    collapsed_bounded_reference = _collapsed(bounded_reference)

    assert "one timezone-aware UTC `retrieved_at`" in collapsed_data_models
    assert (
        "all Evidence rows extracted from that response share it"
        in collapsed_data_models
    )
    assert "not source publication or source-as-of time" in collapsed_data_models
    assert "application-owned citation finalization" in collapsed_state_machines
    assert (
        "does not mutate the frozen Execution Outcome"
        in collapsed_state_machines
    )
    assert "failure, cancellation, and timeout paths" in collapsed_state_machines
    assert (
        "Repeated instances of one recognized reason remain eligible"
        in collapsed_bounded_reference
    )
    assert "multiple distinct recognized reasons" in collapsed_bounded_reference


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS[0],
            "| `status_projection` | `row_shape_invalid`, `ownership_invalid` |",
        ),
        (
            EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS[2],
            "| `consumer_contract` | `source_url_required`, `source_url_policy_invalid`, `source_identity_too_long`, `retrieved_at_too_long` |",
        ),
        (
            EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS[2],
            EVIDENCE_DIAGNOSTIC_REFERENCE_ROWS[2]
            + "\n| `receipt_contract` | `other` |",
        ),
        (
            "The Evidence receipt contains no IDs, URLs, timestamps, counts, field lengths, content, exception text, paths, credentials, raw input, logs, or traces.",
            "The Evidence receipt contains raw Evidence values.",
        ),
        (
            "The Evidence receipt remains a non-authoritative operator diagnostic.",
            "The Evidence receipt is authoritative Evidence.",
        ),
        (
            "The Evidence receipt does not authorize a retry.",
            "The Evidence receipt automatically retries the observation.",
        ),
    ),
    ids=(
        "reason-removed",
        "reason-moved-stage",
        "catch-all-added",
        "raw-detail-claimed",
        "authority-promoted",
        "automatic-retry-implied",
    ),
)
def test_evidence_diagnostic_receipt_rejects_documentation_mutation(
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
) -> None:
    _assert_contract_rejects_mutation(
        monkeypatch,
        path=PROJECT_ROOT / "docs/reference/bounded-live-producer-evaluation.md",
        replacements=((old, new),),
        contract=_assert_evidence_diagnostic_receipt_contract,
    )
