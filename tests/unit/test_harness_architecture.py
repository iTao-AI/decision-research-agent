from pathlib import Path


def test_active_python_has_no_superseded_harness_symbols():
    root = Path(__file__).parents[2]
    forbidden = (
        "agent.shared_context",
        "tools.shared_context_tools",
        "generate_markdown",
        "convert_md_to_pdf",
        "read_file_content",
        "BaseAgent",
        "AgentConfig",
        "_resolve_subagent",
    )
    violations = []
    for directory in ("agent", "api", "tools"):
        for path in (root / directory).rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for symbol in forbidden:
                if symbol in content:
                    violations.append(
                        f"{path.relative_to(root)}:{symbol}"
                    )

    assert violations == []
