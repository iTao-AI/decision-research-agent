from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from typing import Any


SCHEMA_VERSION = "dra.console-showcase-manifest.v1"
ASSET_RELATIVE_DIR = Path("docs/assets/console-showcase")
MANIFEST_NAME = "manifest.json"
EXPECTED_ASSETS = (
    "research-blocked-recovery.png",
    "research-evidence-review.png",
    "research-workspace-overview.png",
)
EXPECTED_FRAMES = {
    "research-workspace-overview.png": {
        "route": "/?showcase=overview",
        "state": "normal_delivered",
    },
    "research-evidence-review.png": {
        "route": "/?showcase=evidence",
        "state": "evidence_review",
    },
    "research-blocked-recovery.png": {
        "route": "/?showcase=blocked",
        "state": "review_required_not_delivered",
    },
}
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _fail(code: str) -> None:
    raise ValueError(code)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _fail("git_identity_unavailable")
    return completed.stdout.strip()


def load_showcase_manifest(root: Path) -> dict[str, Any]:
    path = root / ASSET_RELATIVE_DIR / MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        _fail("showcase_manifest_invalid")
    if not isinstance(payload, dict):
        _fail("showcase_manifest_invalid")
    return payload


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("showcase_asset_unreadable")
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE:
        _fail("showcase_asset_not_png")
    if raw[12:16] != b"IHDR":
        _fail("showcase_asset_header_invalid")
    width, height = struct.unpack(">II", raw[16:24])
    return width, height


def _require_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def verify_showcase_assets(root: Path) -> dict[str, Any]:
    asset_dir = root / ASSET_RELATIVE_DIR
    manifest = load_showcase_manifest(root)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        _fail("showcase_manifest_schema_invalid")

    capture = manifest.get("capture")
    if not isinstance(capture, dict):
        _fail("showcase_capture_invalid")
    source_commit = _require_text(capture.get("source_commit"), "showcase_source_commit_invalid")
    source_tree = _require_text(capture.get("source_tree"), "showcase_source_tree_invalid")
    if not _HEX_40.fullmatch(source_commit) or not _HEX_40.fullmatch(source_tree):
        _fail("showcase_source_identity_invalid")
    viewport = capture.get("viewport")
    if viewport != {"width": 1600, "height": 1000}:
        _fail("showcase_viewport_invalid")
    if capture.get("locale") != "zh-CN":
        _fail("showcase_locale_invalid")
    _require_text(capture.get("synthetic_demo_disclosure"), "showcase_disclosure_missing")

    current_head = _git(root, "rev-parse", "HEAD")
    if source_commit == current_head:
        _fail("showcase_manifest_self_reference")
    if _git(root, "show", "-s", "--format=%T", source_commit) != source_tree:
        _fail("showcase_source_tree_mismatch")
    source_files = _git(root, "ls-tree", "-r", "--name-only", source_tree).splitlines()
    if any(path.startswith(f"{ASSET_RELATIVE_DIR.as_posix()}/") for path in source_files):
        _fail("showcase_source_tree_contains_assets")

    actual_assets = tuple(sorted(path.name for path in asset_dir.glob("*.png")))
    if actual_assets != EXPECTED_ASSETS:
        _fail("showcase_asset_set_invalid")

    frames = manifest.get("frames")
    if not isinstance(frames, dict) or set(frames) != set(EXPECTED_FRAMES):
        _fail("showcase_frame_set_invalid")
    hashes: dict[str, str] = {}
    for asset_name in EXPECTED_ASSETS:
        frame = frames.get(asset_name)
        if not isinstance(frame, dict):
            _fail("showcase_frame_invalid")
        expected = EXPECTED_FRAMES[asset_name]
        if frame.get("route") != expected["route"] or frame.get("state") != expected["state"]:
            _fail("showcase_frame_state_invalid")
        if frame.get("locale") != "zh-CN":
            _fail("showcase_frame_locale_invalid")
        declared_hash = _require_text(frame.get("sha256"), "showcase_frame_hash_missing")
        if not _HEX_64.fullmatch(declared_hash):
            _fail("showcase_frame_hash_invalid")
        path = asset_dir / asset_name
        if _png_dimensions(path) != (1600, 1000):
            _fail("showcase_asset_dimensions_invalid")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if declared_hash != actual_hash:
            _fail("showcase_frame_hash_mismatch")
        hashes[asset_name] = actual_hash

    return {
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "asset_names": list(actual_assets),
        "viewport": viewport,
        "locale": capture["locale"],
        "source_commit": source_commit,
        "source_tree": source_tree,
        "sha256": hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deterministic console showcase assets.")
    parser.add_argument("check", nargs="?", choices=("check",), default="check")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = verify_showcase_assets(args.root.resolve())
    except ValueError as exc:
        print(json.dumps({"status": "error", "code": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
