from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

import pytest

from scripts.release_publication_contract import (
    CHANGELOG_PATH,
    changelog_release_section_bytes,
    MUTABLE_ENTRYPOINTS,
    PLAN_PATH,
    PREPARATION_ENTRYPOINT_MARKERS,
    PREPARATION_RECORD,
    PUBLICATION_RECORD_REQUIRED_FIELDS,
    PUBLISHED_ENTRYPOINT_MARKERS,
    RELEASE_NOTES_PATH,
    STALE_ENTRYPOINT_MARKERS,
    check_release_publication,
    validate_publication_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _copy_surface(root: Path) -> None:
    relative_paths = (
        PLAN_PATH,
        RELEASE_NOTES_PATH,
        CHANGELOG_PATH,
        *MUTABLE_ENTRYPOINTS,
    )
    for relative_path in relative_paths:
        source = PROJECT_ROOT / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _replace_terminal_record(root: Path, record: dict[str, object]) -> None:
    path = root / PLAN_PATH
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Terminal Publication Record\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    replacement = (
        "## Terminal Publication Record\n\n"
        "Publication status: published.\n\n"
        "```json\n"
        f"{json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True)}\n"
        "```\n\n"
    )
    path.write_text(
        text[: match.start()] + replacement + text[match.end() :],
        encoding="utf-8",
    )


def _replace_preparation_record(root: Path) -> None:
    path = root / PLAN_PATH
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"^## Terminal Publication Record\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    replacement = (
        "## Terminal Publication Record\n\n"
        "Publication status: preparation.\n\n"
        "No terminal publication facts exist in this preparation state.\n\n"
        "```json\n"
        f"{json.dumps(PREPARATION_RECORD, ensure_ascii=True, indent=2, sort_keys=True)}\n"
        "```\n\n"
    )
    path.write_text(
        text[: match.start()] + replacement + text[match.end() :],
        encoding="utf-8",
    )


def _prepare_surface(root: Path) -> None:
    _replace_preparation_record(root)
    for relative_path, marker in PREPARATION_ENTRYPOINT_MARKERS.items():
        path = root / relative_path
        text = path.read_text(encoding="utf-8")
        published_marker = PUBLISHED_ENTRYPOINT_MARKERS[relative_path]
        text = text.replace(published_marker, marker)
        if marker not in text:
            text = f"{text.rstrip()}\n\n{marker}\n"
        path.write_text(text, encoding="utf-8")


def _valid_terminal_record() -> dict[str, object]:
    merge_commit = "a" * 40
    return {
        "schema_version": "dra.v0.1.9-publication-record.v1",
        "state": "published",
        "release_prep_pr_number": 201,
        "release_prep_pr_url": "https://github.com/iTao-AI/decision-research-agent/pull/201",
        "release_prep_reviewed_head": "b" * 40,
        "release_prep_reviewed_tree": "c" * 40,
        "release_prep_merge_commit": merge_commit,
        "release_prep_merge_tree": "c" * 40,
        "tag_name": "v0.1.9",
        "tag_object": "1" * 40,
        "peeled_commit": merge_commit,
        "tag_tree": "c" * 40,
        "release_id": 1901,
        "release_url": "https://github.com/iTao-AI/decision-research-agent/releases/tag/v0.1.9",
        "release_published_at": "2026-09-02T12:34:56Z",
        "release_state": "published",
        "release_is_draft": False,
        "release_is_prerelease": False,
        "release_body_sha256": "3" * 64,
        "tag_release_note_sha256": "3" * 64,
        "tag_changelog_section_sha256": "4" * 64,
        "archive_filename": "decision-research-agent-0.1.9.tar.gz",
        "archive_bytes": 123456,
        "archive_sha256": "5" * 64,
        "archive_safe_extraction": True,
        "archive_git_free_smoke": True,
        "reviewed_head_hosted_checks": [
            {
                "name": "ci",
                "run_id": 9000,
                "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/9000",
                "head_sha": "b" * 40,
                "status": "success",
            }
        ],
        "exact_main_hosted_checks": [
            {
                "name": "ci",
                "run_id": 9001,
                "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/9001",
                "head_sha": merge_commit,
                "status": "success",
            }
        ],
        "non_claims": [
            "No real-provider research or business-impact claim is made.",
        ],
    }


def test_current_published_state_is_valid() -> None:
    result = check_release_publication(PROJECT_ROOT)

    assert result["status"] == "valid"
    assert result["state"] == "published"
    assert result["tag_release_note_sha256"] == (
        "c704c3aced1c46d6ae75fc4ac9c036e53821f297d0535c3f29ec3a6b6f2c2a37"
    )
    assert result["tag_changelog_section_sha256"] == (
        "2325ba03f2f66aec3c4371c9fafd34b1b5b56b71e377bcdb59c18419feff7f14"
    )


def test_preparation_state_rejects_a_premature_publication_claim(tmp_path: Path) -> None:
    _copy_surface(tmp_path)
    _prepare_surface(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nDecision Research Agent v0.1.9 is published.\n",
        encoding="utf-8",
    )
    readme_cn = tmp_path / "README_CN.md"
    readme_cn.write_text(
        readme_cn.read_text(encoding="utf-8") + "\n`v0.1.9` 已发布。\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="release_publication_premature_claim"):
        check_release_publication(tmp_path)


def test_terminal_publication_record_requires_all_readback_fields() -> None:
    record = _valid_terminal_record()
    assert set(record) == PUBLICATION_RECORD_REQUIRED_FIELDS
    for self_referential_field in (
        "post_publication_pr_number",
        "post_publication_pr_url",
        "post_publication_reviewed_head",
        "post_publication_merge_commit",
        "post_publication_merge_tree",
        "cleanup",
    ):
        assert self_referential_field not in record
    validate_publication_record(record)

    missing = dict(record)
    missing.pop("archive_sha256")
    with pytest.raises(ValueError, match="release_publication_record_keys_invalid"):
        validate_publication_record(missing)

    placeholder = dict(record)
    placeholder["release_url"] = "TBD"
    with pytest.raises(ValueError, match="release_publication_record_value_invalid"):
        validate_publication_record(placeholder)


def test_terminal_record_binds_reviewed_tree_and_both_hosted_check_groups() -> None:
    record = _valid_terminal_record()
    validate_publication_record(record)

    reviewed_tree_mismatch = dict(record)
    reviewed_tree_mismatch["release_prep_reviewed_tree"] = "6" * 40
    with pytest.raises(ValueError, match="release_publication_record_identity_invalid"):
        validate_publication_record(reviewed_tree_mismatch)

    for check_group in ("reviewed_head_hosted_checks", "exact_main_hosted_checks"):
        invalid_checks = dict(record)
        invalid_checks[check_group] = [
            {
                **record[check_group][0],
                "head_sha": "6" * 40,
            }
        ]
        with pytest.raises(ValueError, match="release_publication_record_checks_invalid"):
            validate_publication_record(invalid_checks)


def test_terminal_state_requires_published_mutable_entrypoints_and_frozen_bytes(
    tmp_path: Path,
) -> None:
    _copy_surface(tmp_path)
    record = _valid_terminal_record()
    release_note_sha256 = sha256(
        (tmp_path / RELEASE_NOTES_PATH).read_bytes()
    ).hexdigest()
    record["release_body_sha256"] = release_note_sha256
    record["tag_release_note_sha256"] = release_note_sha256
    record["tag_changelog_section_sha256"] = sha256(
        changelog_release_section_bytes(tmp_path)
    ).hexdigest()
    _replace_terminal_record(tmp_path, record)

    for relative_path, marker in PUBLISHED_ENTRYPOINT_MARKERS.items():
        path = tmp_path / relative_path
        text = path.read_text(encoding="utf-8")
        for stale_marker in STALE_ENTRYPOINT_MARKERS[relative_path]:
            text = text.replace(stale_marker, "")
        path.write_text(f"{text.rstrip()}\n\n{marker}\n", encoding="utf-8")

    result = check_release_publication(tmp_path)

    assert result["status"] == "valid"
    assert result["state"] == "published"


def test_terminal_state_rejects_stale_mutable_entrypoints(tmp_path: Path) -> None:
    _copy_surface(tmp_path)
    record = _valid_terminal_record()
    release_note_sha256 = sha256(
        (tmp_path / RELEASE_NOTES_PATH).read_bytes()
    ).hexdigest()
    record["release_body_sha256"] = release_note_sha256
    record["tag_release_note_sha256"] = release_note_sha256
    record["tag_changelog_section_sha256"] = sha256(
        changelog_release_section_bytes(tmp_path)
    ).hexdigest()
    _replace_terminal_record(tmp_path, record)
    for relative_path, marker in PUBLISHED_ENTRYPOINT_MARKERS.items():
        path = tmp_path / relative_path
        stale_marker = STALE_ENTRYPOINT_MARKERS[relative_path][0]
        path.write_text(
            f"{path.read_text(encoding='utf-8').rstrip()}\n\n{marker}\n\n{stale_marker}\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="release_publication_published_surface_stale"):
        check_release_publication(tmp_path)
