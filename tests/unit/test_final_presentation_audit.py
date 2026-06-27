from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_product_domain_language_is_allowed() -> None:
    from scripts.final_presentation_audit import presentation_violations

    text = "帮助求职者调研岗位、比较招聘信号并识别面试重点。"

    assert presentation_violations(text) == []


def test_private_presentation_motivation_is_rejected() -> None:
    from scripts.final_presentation_audit import presentation_violations

    text = "这个功能用于简历包装，并作为主力项目给面试官展示。"

    assert presentation_violations(text)


def test_release_documentation_paths_are_present() -> None:
    from scripts.final_presentation_audit import REQUIRED_PATHS

    missing = sorted(path for path in REQUIRED_PATHS if not (ROOT / path).is_file())

    assert missing == []


def test_obsolete_public_trees_are_absent() -> None:
    from scripts.final_presentation_audit import FORBIDDEN_PREFIXES, tracked_paths

    violations = [
        path
        for path in tracked_paths(ROOT)
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
    ]

    assert violations == []


def test_superpowers_workspace_is_curated() -> None:
    from scripts.final_presentation_audit import superpowers_path_violations

    assert superpowers_path_violations(ROOT) == []


def test_all_tracked_markdown_is_public_neutral() -> None:
    from scripts.final_presentation_audit import markdown_content_violations

    assert markdown_content_violations(ROOT) == []


def test_all_relative_markdown_links_resolve() -> None:
    from scripts.final_presentation_audit import relative_markdown_link_violations

    assert relative_markdown_link_violations(ROOT) == []


def test_cli_emits_json_and_fails_closed(capsys) -> None:
    from scripts.final_presentation_audit import main

    exit_code = main(["--root", str(ROOT)])
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == ("ok" if exit_code == 0 else "failed")
    assert isinstance(payload["violations"], list)
    assert exit_code == (0 if not payload["violations"] else 1)
