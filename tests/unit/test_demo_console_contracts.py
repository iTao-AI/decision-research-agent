import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
README_CN = ROOT / "README_CN.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
DESIGN = ROOT / "DESIGN.md"
OPERATIONS = ROOT / "docs" / "demo-console.md"
APP = ROOT / "frontend" / "src" / "App.tsx"
API_CLIENT = ROOT / "frontend" / "src" / "apiClient.ts"
LIVE_RUN = ROOT / "frontend" / "src" / "useLiveRun.ts"
MODULE_SPECIFIER = re.compile(
    r'(?:\bfrom\s+|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)["\']([^"\']+)["\']'
)
AGENT_FRAMEWORKS = ("langchain", "langgraph", "deepagents", "langsmith")
BACKEND_ROOTS = (ROOT / "api", ROOT / "backend")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _public_contract() -> str:
    return re.sub(r"\s+", " ", f"{_read(DESIGN)}\n{_read(OPERATIONS)}")


def _production_typescript_sources(source_root: Path) -> list[Path]:
    sources = set(source_root.rglob("*.ts")) | set(source_root.rglob("*.tsx"))
    return sorted(
        source
        for source in sources
        if ".test." not in source.name
        and not {"test", "tests", "__tests__"}.intersection(
            source.relative_to(source_root).parts
        )
    )


def _forbidden_module_specifiers(source: Path, source_text: str) -> list[str]:
    forbidden: list[str] = []
    for specifier in MODULE_SPECIFIER.findall(source_text):
        normalized = specifier.lower()
        segments = {segment for segment in normalized.split("/") if segment}
        resolved = (
            (source.parent / specifier).resolve()
            if specifier.startswith((".", "/"))
            else None
        )
        imports_agent_framework = any(
            framework in normalized for framework in AGENT_FRAMEWORKS
        )
        imports_backend = bool({"api", "backend"}.intersection(segments)) or (
            resolved is not None
            and any(resolved.is_relative_to(root.resolve()) for root in BACKEND_ROOTS)
        )
        if imports_agent_framework or imports_backend:
            forbidden.append(specifier)
    return forbidden


def test_static_and_live_run_data_are_mutually_exclusive():
    contract = _public_contract()
    app = _read(APP)

    assert "Static Demo and Live Backend run data are mutually exclusive" in contract
    assert "inactive mode's run-specific data is never rendered" in contract
    assert 'liveRun.state.mode === "static"' in app
    assert "buildStaticConsoleProjection()" in app
    assert "buildLiveConsoleProjection({" in app
    assert "demoRun" not in app
    assert "architectureNodes" not in app


def test_create_intent_is_header_only_session_scoped_and_reconcilable():
    contract = _public_contract()
    client = _read(API_CLIENT)

    assert "Idempotency-Key is header-only and browser-session scoped" in contract
    assert "same key and byte-equivalent request" in contract
    assert "page refresh discards the in-memory reconciliation capability" in contract
    assert '"Idempotency-Key": intent.idempotencyKey' in client
    assert "JSON.stringify(intent.payload)" in client


def test_known_run_recovery_and_canonical_result_authority_are_explicit():
    contract = _public_contract()
    live_run = _read(LIVE_RUN)
    resume = live_run.split("const resumeObservation", maxsplit=1)[1].split(
        "const startNewRun", maxsplit=1
    )[0]

    assert "known run observation resumes with GET only" in contract
    assert "canonical artifact comes only from /api/runs/{run_id}/result" in contract
    assert (
        "terminal non-ready state is an observed run outcome, not a connection failure"
        in contract
    )
    assert "observeRun" in resume
    assert "startRun" not in resume


def test_failure_cause_availability_states_remain_distinct():
    contract = _public_contract()

    assert "failure-cause property absent means unsupported" in contract
    assert "failure-cause null means not applicable" in contract
    assert "failure-cause not_observed means no cause was observed" in contract
    assert "failure-cause observed renders only its bounded public projection" in contract


def test_shared_discovery_publishes_console_live_authority_closure():
    readme = re.sub(r"\s+", " ", _read(README))
    readme_cn = re.sub(r"\s+", " ", _read(README_CN))
    changelog = re.sub(r"\s+", " ", _read(CHANGELOG))
    docs_index = re.sub(r"\s+", " ", _read(DOCS_INDEX))
    unreleased, historical = changelog.split("## [0.1.3]", maxsplit=1)

    assert "renders only real service-owned state" in readme
    assert "same key and byte-equivalent request" in readme
    assert "observation resume is GET-only" in readme
    assert "does not own review, verification, publication, or delivery authority" in readme

    assert "只渲染真实的 service-owned state" in readme_cn
    assert "same key 和 byte-equivalent request" in readme_cn
    assert "observation resume 仅使用 GET" in readme_cn
    assert "不拥有 review、verification、publication 或 delivery authority" in readme_cn

    assert "### Console live authority closure" in unreleased
    assert "same key and byte-equivalent request" in unreleased
    assert "GET-only observation resume" in unreleased
    assert "does not claim durable browser intent" in unreleased
    assert "Console live authority closure" not in historical

    assert "[Demo Console](demo-console.md)" in docs_index
    assert (
        "[Console Live Authority Closure design]"
        "(superpowers/specs/2026-07-16-console-live-authority-closure-design.md)"
        in docs_index
    )
    assert (
        "[implementation plan]"
        "(superpowers/plans/2026-07-16-console-live-authority-closure-implementation.md)"
        in docs_index
    )


def test_console_security_authority_and_nonclaims_are_public():
    contract = _public_contract()

    assert "loopback-only" in contract
    assert "does not accept or store API credentials" in contract
    assert "does not own review or verification authority" in contract
    assert "does not prove durable browser intent" in contract
    assert "does not prove production deployment" in contract
    assert "does not prove exactly-once execution" in contract
    assert "does not prove live-provider quality" in contract


def test_console_documents_runtime_access_without_becoming_auth_authority():
    contract = _public_contract()

    assert "CORS and Origin checks are not authentication" in contract
    assert "direct peer and literal Host must both be loopback" in contract
    assert "WebSocket credentials are header-only" in contract
    assert "query credentials are rejected" in contract
    assert "Use the first-party Tool Client" in contract


def test_frontend_implementation_does_not_import_runtime_or_backend_modules():
    for source in _production_typescript_sources(ROOT / "frontend" / "src"):
        assert _forbidden_module_specifiers(source, _read(source)) == []


def test_forbidden_import_audit_handles_real_import_forms():
    source = ROOT / "frontend" / "src" / "nested" / "consumer.tsx"
    cases = {
        "@langchain/core": 'import "@langchain/core";',
        "langgraph/prebuilt": 'import graph from "langgraph/prebuilt";',
        "deepagents": 'const agents = import("deepagents");',
        "langsmith": 'export { Client } from "langsmith";',
        "../../../api/server": 'import "../../../api/server";',
        "../../../backend/runtime": 'const runtime = import("../../../backend/runtime");',
    }

    for specifier, source_text in cases.items():
        assert specifier in _forbidden_module_specifiers(source, source_text)

    assert _forbidden_module_specifiers(source, 'import api from "../apiClient";') == []


def test_production_typescript_source_discovery_is_recursive(tmp_path: Path):
    nested_source = tmp_path / "nested" / "consumer.tsx"
    nested_source.parent.mkdir()
    nested_source.write_text("export {};", encoding="utf-8")
    test_source = tmp_path / "nested" / "consumer.test.ts"
    test_source.write_text("export {};", encoding="utf-8")

    discovered = _production_typescript_sources(tmp_path)

    assert nested_source in discovered
    assert test_source not in discovered
