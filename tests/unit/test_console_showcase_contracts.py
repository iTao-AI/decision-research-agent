from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_showcase_manifest_verifies_exact_assets_and_capture_identity() -> None:
    from scripts.console_showcase_contracts import verify_showcase_assets

    result = verify_showcase_assets(PROJECT_ROOT)

    assert result["status"] == "ok"
    assert result["viewport"] == {"width": 1600, "height": 1000}
    assert result["locale"] == "zh-CN"
    assert result["asset_names"] == [
        "research-blocked-recovery.png",
        "research-evidence-review.png",
        "research-workspace-overview.png",
    ]


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
