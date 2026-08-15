from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.console_showcase_contracts import (
    EXPECTED_ASSETS,
    compute_capture_input_fingerprint,
    discover_capture_input_paths,
    load_showcase_manifest,
    verify_showcase_assets,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_INPUT_PATHS = discover_capture_input_paths(PROJECT_ROOT)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_git_fixture(root: Path) -> None:
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "showcase-contract@example.invalid")
    _git(root, "config", "user.name", "Showcase Contract")


def _copy_capture_inputs(root: Path) -> None:
    for relative_path in CAPTURE_INPUT_PATHS:
        source = PROJECT_ROOT / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _copy_assets(root: Path) -> None:
    asset_dir = root / "docs/assets/console-showcase"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_dir = PROJECT_ROOT / "docs/assets/console-showcase"
    for asset_name in EXPECTED_ASSETS:
        shutil.copyfile(source_dir / asset_name, asset_dir / asset_name)


def _write_fixture_manifest(
    root: Path,
    source_commit: str,
    source_tree: str,
) -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "docs/assets/console-showcase/manifest.json").read_text(encoding="utf-8")
    )
    capture = manifest["capture"]
    capture["source_commit"] = source_commit
    capture["source_tree"] = source_tree
    capture["capture_input_fingerprint"] = {
        "algorithm": "sha256",
        "paths": list(CAPTURE_INPUT_PATHS),
        "value": compute_capture_input_fingerprint(root),
    }
    manifest_path = root / "docs/assets/console-showcase/manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepare_git_fixture(
    root: Path,
    *,
    source_identity: tuple[str, str] | None = None,
    capture_commit_message: str = "capture inputs",
) -> tuple[str, str]:
    _init_git_fixture(root)
    _copy_capture_inputs(root)
    _git(root, "add", *CAPTURE_INPUT_PATHS)
    _git(
        root,
        "-c",
        "user.name=Showcase Contract",
        "-c",
        "user.email=showcase-contract@example.invalid",
        "commit",
        "--quiet",
        "-m",
        capture_commit_message,
    )
    actual_source_commit = _git(root, "rev-parse", "HEAD")
    actual_source_tree = _git(root, "rev-parse", "HEAD^{tree}")

    _copy_assets(root)
    manifest_source_commit, manifest_source_tree = source_identity or (
        actual_source_commit,
        actual_source_tree,
    )
    _write_fixture_manifest(root, manifest_source_commit, manifest_source_tree)
    _git(root, "add", "docs/assets/console-showcase")
    _git(
        root,
        "-c",
        "user.name=Showcase Contract",
        "-c",
        "user.email=showcase-contract@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "showcase assets",
    )
    return actual_source_commit, actual_source_tree


def _prepare_tree_mismatch_fixture(root: Path) -> tuple[str, str]:
    _init_git_fixture(root)
    _copy_capture_inputs(root)
    _git(root, "add", *CAPTURE_INPUT_PATHS)
    _git(
        root,
        "-c",
        "user.name=Showcase Contract",
        "-c",
        "user.email=showcase-contract@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "capture inputs",
    )
    source_commit = _git(root, "rev-parse", "HEAD")

    changed_input = root / CAPTURE_INPUT_PATHS[0]
    changed_input.write_bytes(changed_input.read_bytes() + b"\n")
    _git(root, "add", CAPTURE_INPUT_PATHS[0])
    _git(
        root,
        "-c",
        "user.name=Showcase Contract",
        "-c",
        "user.email=showcase-contract@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "change capture input",
    )
    mismatched_tree = _git(root, "rev-parse", "HEAD^{tree}")

    _copy_assets(root)
    _write_fixture_manifest(root, source_commit, mismatched_tree)
    _git(root, "add", "docs/assets/console-showcase")
    _git(
        root,
        "-c",
        "user.name=Showcase Contract",
        "-c",
        "user.email=showcase-contract@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "showcase assets",
    )
    return source_commit, mismatched_tree


def test_showcase_manifest_verifies_exact_assets_and_capture_identity() -> None:
    result = verify_showcase_assets(PROJECT_ROOT)

    assert result["status"] == "ok"
    assert result["viewport"] == {"width": 1600, "height": 1000}
    assert result["locale"] == "zh-CN"
    assert result["asset_names"] == [
        "research-blocked-recovery.png",
        "research-evidence-review.png",
        "research-workspace-overview.png",
    ]
    assert result["provenance_verification"] == "historic_source_identity"


def test_reachable_historic_identity_is_cross_checked_against_capture_inputs(tmp_path: Path) -> None:
    fixture = tmp_path / "reachable"

    _prepare_git_fixture(fixture)

    result = verify_showcase_assets(fixture)

    assert result["provenance_verification"] == "historic_source_identity"
    assert result["capture_input_fingerprint"] == compute_capture_input_fingerprint(fixture)


def test_new_tracked_production_frontend_input_requires_manifest_update(tmp_path: Path) -> None:
    fixture = tmp_path / "new-production-input"
    _prepare_git_fixture(fixture)
    new_module = fixture / "frontend/src/newProductionModule.ts"
    new_module.write_text("export const newProductionInput = true;\n", encoding="utf-8")
    _git(fixture, "add", "frontend/src/newProductionModule.ts")

    with pytest.raises(ValueError, match="showcase_capture_input_paths_mismatch"):
        verify_showcase_assets(fixture)


def test_unreachable_historic_identity_uses_truthful_capture_fingerprint_mode(tmp_path: Path) -> None:
    source_fixture = tmp_path / "source"
    source_commit, source_tree = _prepare_git_fixture(source_fixture)
    fresh_fixture = tmp_path / "fresh-main"

    _prepare_git_fixture(
        fresh_fixture,
        source_identity=(source_commit, source_tree),
        capture_commit_message="fresh main capture inputs",
    )
    result = verify_showcase_assets(fresh_fixture)

    assert result["provenance_verification"] == "capture_input_fingerprint_unreachable_source"


def test_tampered_capture_fingerprint_fails_closed(tmp_path: Path) -> None:
    fixture = tmp_path / "tampered"
    _prepare_git_fixture(fixture)
    manifest_path = fixture / "docs/assets/console-showcase/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capture"]["capture_input_fingerprint"]["value"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="showcase_capture_input_fingerprint_mismatch"):
        verify_showcase_assets(fixture)


def test_reachable_source_tree_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = tmp_path / "tree-mismatch"
    _prepare_tree_mismatch_fixture(fixture)

    with pytest.raises(ValueError, match="showcase_source_tree_mismatch"):
        verify_showcase_assets(fixture)


def test_showcase_manifest_maps_normal_and_blocked_states_to_public_routes() -> None:
    from scripts.console_showcase_contracts import load_showcase_manifest

    manifest = load_showcase_manifest(PROJECT_ROOT)
    frames = manifest["frames"]

    assert frames["research-workspace-overview.png"]["route"] == "/?showcase=overview"
    assert frames["research-evidence-review.png"]["route"] == "/?showcase=evidence"
    assert frames["research-blocked-recovery.png"]["route"] == "/?showcase=blocked"
    assert frames["research-blocked-recovery.png"]["state"] == "review_required_not_delivered"
    assert manifest["synthetic_demo_disclosure"]


def test_readmes_lead_with_the_showcase_delivery_flow() -> None:
    english_sections = [
        "## What It Does",
        "## Research Delivery Flow",
        "## Showcase Frames",
        "## Engineering Judgments",
        "## Quick Start",
        "## Authority And Runtime",
        "## Architecture",
        "## Verification",
    ]
    chinese_sections = [
        "## 当前能力",
        "## Research Delivery Flow",
        "## Showcase Frames",
        "## 三个工程判断",
        "## 快速开始",
        "## Authority And Runtime",
        "## 架构",
        "## 验证",
    ]

    for path, required_sections in (
        (PROJECT_ROOT / "README.md", english_sections),
        (PROJECT_ROOT / "README_CN.md", chinese_sections),
    ):
        text = path.read_text(encoding="utf-8")
        positions = [text.index(section) for section in required_sections]
        assert positions == sorted(positions), path
        assert "research-workspace-overview.png" in text
        assert "research-evidence-review.png" in text
        assert "research-blocked-recovery.png" in text
