from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "dra.v0.1.9-publication-record.v1"
PLAN_PATH = "docs/superpowers/plans/2026-09-01-v0-1-9-bounded-release-implementation-plan.md"
RELEASE_NOTES_PATH = "docs/releases/v0.1.9.md"
CHANGELOG_PATH = "CHANGELOG.md"
MUTABLE_ENTRYPOINTS = (
    "README.md",
    "README_CN.md",
    "docs/README.md",
    "SECURITY.md",
    "docs/superpowers/README.md",
)
PREPARATION_RECORD = {"state": "preparation"}
PUBLISHED_ENTRYPOINT_MARKERS = {
    "README.md": "Decision Research Agent v0.1.9 is the current published stable release.",
    "README_CN.md": "Decision Research Agent v0.1.9 是当前已发布的 stable release。",
    "docs/README.md": "The current published stable release is `v0.1.9`.",
    "SECURITY.md": "Decision Research Agent v0.1.9 is the current published stable release.",
    "docs/superpowers/README.md": "The current published stable release is `v0.1.9`.",
}
STALE_ENTRYPOINT_MARKERS = {
    "README.md": ("v0.1.9 release preparation",),
    "README_CN.md": ("v0.1.9 release preparation",),
    "docs/README.md": (
        "The immutable stable `v0.1.8` Release Notes describe the last published stable release.",
        "The current `v0.1.9` release preparation records",
        "current provider-free release preparation",
    ),
    "SECURITY.md": ("v0.1.9 release preparation",),
    "docs/superpowers/README.md": (
        "The v0.1.9 record is provider-free and public-neutral.",
    ),
}
PREPARATION_ENTRYPOINT_MARKERS = {
    "README.md": "[v0.1.9 release preparation]",
    "README_CN.md": "[v0.1.9 release preparation]",
    "docs/README.md": "The current `v0.1.9` release preparation records",
    "SECURITY.md": "Decision Research Agent v0.1.9 release preparation includes",
    "docs/superpowers/README.md": "The v0.1.9 record is provider-free and public-neutral.",
}
PUBLICATION_RECORD_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "release_prep_pr_number",
        "release_prep_pr_url",
        "release_prep_reviewed_head",
        "release_prep_merge_commit",
        "release_prep_merge_tree",
        "post_publication_pr_number",
        "post_publication_pr_url",
        "post_publication_reviewed_head",
        "post_publication_merge_commit",
        "post_publication_merge_tree",
        "tag_name",
        "tag_object",
        "peeled_commit",
        "tag_tree",
        "release_id",
        "release_url",
        "release_published_at",
        "release_state",
        "release_is_draft",
        "release_is_prerelease",
        "release_body_sha256",
        "tag_release_note_sha256",
        "tag_changelog_section_sha256",
        "archive_filename",
        "archive_bytes",
        "archive_sha256",
        "archive_safe_extraction",
        "archive_git_free_smoke",
        "exact_main_hosted_checks",
        "non_claims",
        "cleanup",
    }
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_JSON_FENCE = re.compile(r"^```json\n(?P<body>.*?)\n```\n?", re.MULTILINE | re.DOTALL)
_PREMATURE_PUBLICATION_PATTERNS = (
    re.compile(r"`?v0\.1\.9`? is (?:now )?published\b", re.IGNORECASE),
    re.compile(
        r"`?v0\.1\.9`? (?:tag|release) (?:has been |was )?(?:created|published)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bGitHub Release (?:has been |was )?published\b", re.IGNORECASE),
    re.compile(
        r"\b(?:deployment|archive smoke) (?:has been |was )?(?:completed|passed)\b",
        re.IGNORECASE,
    ),
    re.compile(r"`?v0\.1\.9`?\s*(?:已发布|已创建)", re.IGNORECASE),
)
_PLACEHOLDER_VALUES = frozenset(
    {
        "n/a",
        "not recorded",
        "not yet recorded",
        "pending",
        "replace me",
        "tbd",
        "todo",
    }
)


def _fail(code: str) -> None:
    raise ValueError(code)


def _read_bytes(root: Path, relative_path: str) -> bytes:
    try:
        return (root / relative_path).read_bytes()
    except OSError:
        _fail("release_publication_file_unreadable")


def _read_text(root: Path, relative_path: str) -> str:
    try:
        return _read_bytes(root, relative_path).decode("utf-8")
    except UnicodeDecodeError:
        _fail("release_publication_file_invalid")


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^{re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        _fail("release_publication_section_missing")
    return match.group("body")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def changelog_release_section_bytes(root: Path) -> bytes:
    text = _read_text(root, CHANGELOG_PATH)
    heading = "## [0.1.9] - 2026-09-01"
    start = text.find(f"{heading}\n")
    if start < 0:
        _fail("release_publication_changelog_section_missing")
    end = text.find("\n## ", start + len(heading) + 1)
    if end < 0:
        end = len(text)
    return text[start:end].encode("utf-8")


def load_terminal_record(root: Path) -> dict[str, Any]:
    plan = _read_text(root, PLAN_PATH)
    body = _section(plan, "## Terminal Publication Record")
    match = _JSON_FENCE.search(body)
    if match is None:
        _fail("release_publication_record_missing")
    try:
        record = json.loads(match.group("body"))
    except json.JSONDecodeError:
        _fail("release_publication_record_invalid")
    if not isinstance(record, dict):
        _fail("release_publication_record_invalid")
    return record


def _require_string(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail("release_publication_record_value_invalid")
    normalized = value.strip().casefold()
    if normalized in _PLACEHOLDER_VALUES or (
        normalized.startswith("<") and normalized.endswith(">")
    ):
        _fail("release_publication_record_value_invalid")
    return value


def _require_positive_int(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("release_publication_record_value_invalid")
    return value


def _require_sha(record: Mapping[str, Any], key: str, pattern: re.Pattern[str]) -> str:
    value = _require_string(record, key)
    if pattern.fullmatch(value) is None:
        _fail("release_publication_record_identity_invalid")
    return value


def _require_github_url(record: Mapping[str, Any], key: str) -> str:
    value = _require_string(record, key)
    if not value.startswith("https://github.com/iTao-AI/decision-research-agent/"):
        _fail("release_publication_record_url_invalid")
    return value


def _require_pr_url(record: Mapping[str, Any], key: str) -> str:
    value = _require_github_url(record, key)
    match = re.search(r"/pull/(\d+)(?:[?#].*)?$", value)
    number_key = key.replace("_url", "_number")
    if match is None or int(match.group(1)) != record[number_key]:
        _fail("release_publication_record_url_invalid")
    return value


def validate_publication_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        _fail("release_publication_record_invalid")
    if set(record) != PUBLICATION_RECORD_REQUIRED_FIELDS:
        _fail("release_publication_record_keys_invalid")
    if record.get("schema_version") != SCHEMA_VERSION or record.get("state") != "published":
        _fail("release_publication_record_state_invalid")

    for key in (
        "release_prep_pr_url",
        "post_publication_pr_url",
        "release_url",
    ):
        if key.endswith("pr_url"):
            _require_pr_url(record, key)
        else:
            _require_github_url(record, key)
    for key in (
        "release_prep_pr_number",
        "post_publication_pr_number",
        "release_id",
        "archive_bytes",
    ):
        _require_positive_int(record, key)

    for key in (
        "release_prep_reviewed_head",
        "release_prep_merge_commit",
        "release_prep_merge_tree",
        "post_publication_reviewed_head",
        "post_publication_merge_commit",
        "post_publication_merge_tree",
        "tag_object",
        "peeled_commit",
        "tag_tree",
    ):
        _require_sha(record, key, _HEX_40)
    for key in (
        "release_body_sha256",
        "tag_release_note_sha256",
        "tag_changelog_section_sha256",
        "archive_sha256",
    ):
        _require_sha(record, key, _HEX_64)

    if record["tag_name"] != "v0.1.9":
        _fail("release_publication_record_identity_invalid")
    if record["release_url"].rstrip("/") != (
        "https://github.com/iTao-AI/decision-research-agent/releases/tag/v0.1.9"
    ):
        _fail("release_publication_record_url_invalid")
    if record["peeled_commit"] != record["release_prep_merge_commit"]:
        _fail("release_publication_record_identity_invalid")
    if record["tag_tree"] != record["release_prep_merge_tree"]:
        _fail("release_publication_record_identity_invalid")
    if record["release_body_sha256"] != record["tag_release_note_sha256"]:
        _fail("release_publication_record_body_mismatch")

    published_at = _require_string(record, "release_published_at")
    try:
        parsed_published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        _fail("release_publication_record_time_invalid")
    if parsed_published_at.tzinfo is None:
        _fail("release_publication_record_time_invalid")

    if record["release_state"] != "published":
        _fail("release_publication_record_state_invalid")
    if record["release_is_draft"] is not False or record["release_is_prerelease"] is not False:
        _fail("release_publication_record_state_invalid")

    archive_filename = _require_string(record, "archive_filename")
    if (
        "/" in archive_filename
        or "\\" in archive_filename
        or not archive_filename.endswith(".tar.gz")
        or "0.1.9" not in archive_filename
    ):
        _fail("release_publication_record_archive_invalid")
    if record["archive_safe_extraction"] is not True or record["archive_git_free_smoke"] is not True:
        _fail("release_publication_record_archive_invalid")

    checks = record["exact_main_hosted_checks"]
    if not isinstance(checks, list) or not checks:
        _fail("release_publication_record_checks_invalid")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "run_id", "url", "head_sha", "status"}:
            _fail("release_publication_record_checks_invalid")
        if not isinstance(check["name"], str) or not check["name"].strip():
            _fail("release_publication_record_checks_invalid")
        if isinstance(check["run_id"], bool) or not isinstance(check["run_id"], int) or check["run_id"] <= 0:
            _fail("release_publication_record_checks_invalid")
        if not check["url"].startswith("https://github.com/iTao-AI/decision-research-agent/"):
            _fail("release_publication_record_checks_invalid")
        if check["head_sha"] != record["release_prep_merge_commit"] or check["status"] != "success":
            _fail("release_publication_record_checks_invalid")

    non_claims = record["non_claims"]
    if (
        not isinstance(non_claims, list)
        or not non_claims
        or any(
            not isinstance(item, str)
            or not item.strip()
            or item.strip().casefold() in _PLACEHOLDER_VALUES
            for item in non_claims
        )
    ):
        _fail("release_publication_record_non_claims_invalid")
    cleanup = record["cleanup"]
    if (
        not isinstance(cleanup, dict)
        or cleanup.get("status") != "clean"
        or cleanup.get("task_owned_resources") != "removed"
        or cleanup.get("worktrees_unchanged") is not True
    ):
        _fail("release_publication_record_cleanup_invalid")
    return dict(record)


def _surface_texts(root: Path) -> dict[str, str]:
    paths = (*MUTABLE_ENTRYPOINTS, PLAN_PATH, RELEASE_NOTES_PATH)
    texts = {relative_path: _read_text(root, relative_path) for relative_path in paths}
    texts[CHANGELOG_PATH] = _section(
        _read_text(root, CHANGELOG_PATH),
        "## [0.1.9] - 2026-09-01",
    )
    return texts


def _validate_no_premature_claims(texts: Mapping[str, str]) -> None:
    for relative_path, text in texts.items():
        for pattern in _PREMATURE_PUBLICATION_PATTERNS:
            if pattern.search(text):
                _fail("release_publication_premature_claim")


def validate_preparation_state(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    if dict(record) != PREPARATION_RECORD:
        _fail("release_publication_record_preparation_invalid")
    texts = _surface_texts(root)
    for relative_path, marker in PREPARATION_ENTRYPOINT_MARKERS.items():
        if marker not in texts[relative_path]:
            _fail("release_publication_preparation_surface_invalid")
    for marker in (
        "Publication status: preparation.",
        "No terminal publication facts exist in this preparation state.",
    ):
        if marker not in texts[PLAN_PATH]:
            _fail("release_publication_preparation_record_invalid")
    if "does not claim that a `v0.1.9` tag" not in _normalized(texts[RELEASE_NOTES_PATH]):
        _fail("release_publication_preparation_surface_invalid")
    if "does not itself claim publication." not in _normalized(texts[CHANGELOG_PATH]):
        _fail("release_publication_preparation_surface_invalid")
    _validate_no_premature_claims(texts)
    return {"status": "valid", "state": "preparation"}


def validate_published_state(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_publication_record(record)
    texts = _surface_texts(root)
    plan = texts[PLAN_PATH]
    if "Publication status: published." not in plan:
        _fail("release_publication_terminal_record_invalid")
    if "No terminal publication facts exist in this preparation state." in plan:
        _fail("release_publication_terminal_record_invalid")
    for relative_path, marker in PUBLISHED_ENTRYPOINT_MARKERS.items():
        if marker not in texts[relative_path]:
            _fail("release_publication_published_surface_invalid")
        if any(
            stale_marker in texts[relative_path]
            for stale_marker in STALE_ENTRYPOINT_MARKERS[relative_path]
        ):
            _fail("release_publication_published_surface_stale")

    release_note_sha256 = hashlib.sha256(_read_bytes(root, RELEASE_NOTES_PATH)).hexdigest()
    changelog_sha256 = hashlib.sha256(changelog_release_section_bytes(root)).hexdigest()
    if "does not claim that a `v0.1.9` tag" not in _normalized(texts[RELEASE_NOTES_PATH]):
        _fail("release_publication_frozen_surface_invalid")
    if "does not itself claim publication." not in _normalized(texts[CHANGELOG_PATH]):
        _fail("release_publication_frozen_surface_invalid")
    if release_note_sha256 != validated["tag_release_note_sha256"]:
        _fail("release_publication_frozen_release_note_changed")
    if changelog_sha256 != validated["tag_changelog_section_sha256"]:
        _fail("release_publication_frozen_changelog_changed")
    return {
        "status": "valid",
        "state": "published",
        "tag_release_note_sha256": release_note_sha256,
        "tag_changelog_section_sha256": changelog_sha256,
    }


def check_release_publication(root: Path) -> dict[str, Any]:
    record = load_terminal_record(root)
    state = record.get("state")
    if state == "preparation":
        return validate_preparation_state(root, record)
    if state == "published":
        return validate_published_state(root, record)
    _fail("release_publication_state_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the v0.1.9 preparation or terminal publication record."
    )
    parser.add_argument("check", nargs="?", choices=("check",), default="check")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = check_release_publication(args.root.resolve())
    except ValueError as exc:
        print(json.dumps({"status": "invalid", "code": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
