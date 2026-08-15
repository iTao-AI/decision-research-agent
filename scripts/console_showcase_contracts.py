from __future__ import annotations

import argparse
from collections.abc import Callable
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
# Browser input discovery includes tracked frontend source, public assets, and
# build/runtime configuration. Only clearly non-rendering test/generated/type
# declaration paths are excluded; output PNGs, manifest metadata, docs, and
# tests are never fingerprint inputs.
NON_RENDERING_FRONTEND_DIRS = frozenset(
    {
        ".vite",
        "__tests__",
        "coverage",
        "dist",
        "node_modules",
        "playwright-report",
        "test-results",
        "test",
    }
)
NON_RENDERING_FRONTEND_SUFFIXES = (".d.ts",)
NON_RENDERING_TEST_MARKERS = (".spec.", ".test.")
CAPTURE_INPUT_FINGERPRINT_ALGORITHM = "sha256"
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


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _fail("git_identity_unavailable")
    return completed.stdout


def _source_commit_is_reachable(root: Path, source_commit: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{source_commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1 and not completed.stderr:
        return False
    _fail("git_identity_unavailable")


def _is_rendering_frontend_path(relative_path: str) -> bool:
    path = Path(relative_path)
    if path.parts[0] != "frontend":
        return False
    if any(part in NON_RENDERING_FRONTEND_DIRS for part in path.parts[1:]):
        return False
    if path.name.endswith(NON_RENDERING_FRONTEND_SUFFIXES):
        return False
    return not any(marker in path.name for marker in NON_RENDERING_TEST_MARKERS)


def _decode_git_paths(raw: bytes) -> tuple[str, ...]:
    paths = {
        path.decode("utf-8")
        for path in raw.split(b"\0")
        if path and _is_rendering_frontend_path(path.decode("utf-8"))
    }
    if not paths:
        _fail("showcase_capture_input_set_empty")
    return tuple(sorted(paths))


def discover_capture_input_paths(root: Path) -> tuple[str, ...]:
    return _decode_git_paths(_git_bytes(root, "ls-files", "-z", "--", "frontend"))


def _discover_tree_capture_input_paths(root: Path, source_tree: str) -> tuple[str, ...]:
    return _decode_git_paths(
        _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", source_tree, "--", "frontend")
    )


def _fingerprint_from_reader(
    reader: Callable[[str], bytes], input_paths: tuple[str, ...]
) -> str:
    entries = [
        {
            "path": relative_path,
            "sha256": hashlib.sha256(reader(relative_path)).hexdigest(),
        }
        for relative_path in input_paths
    ]
    canonical_entries = json.dumps(
        entries,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_entries).hexdigest()


def compute_capture_input_fingerprint(root: Path) -> str:
    input_paths = discover_capture_input_paths(root)

    def read_input(relative_path: str) -> bytes:
        try:
            return (root / relative_path).read_bytes()
        except OSError:
            _fail("showcase_capture_input_unreadable")

    return _fingerprint_from_reader(read_input, input_paths)


def _compute_tree_capture_input_fingerprint(
    root: Path,
    source_tree: str,
    input_paths: tuple[str, ...],
) -> str:
    return _fingerprint_from_reader(
        lambda relative_path: _git_bytes(root, "show", f"{source_tree}:{relative_path}"),
        input_paths,
    )


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

    capture_input = capture.get("capture_input_fingerprint")
    if not isinstance(capture_input, dict):
        _fail("showcase_capture_input_fingerprint_invalid")
    if capture_input.get("algorithm") != CAPTURE_INPUT_FINGERPRINT_ALGORITHM:
        _fail("showcase_capture_input_algorithm_invalid")
    discovered_input_paths = discover_capture_input_paths(root)
    if capture_input.get("paths") != list(discovered_input_paths):
        _fail("showcase_capture_input_paths_mismatch")
    declared_capture_input_fingerprint = _require_text(
        capture_input.get("value"),
        "showcase_capture_input_fingerprint_invalid",
    )
    if not _HEX_64.fullmatch(declared_capture_input_fingerprint):
        _fail("showcase_capture_input_fingerprint_invalid")
    if compute_capture_input_fingerprint(root) != declared_capture_input_fingerprint:
        _fail("showcase_capture_input_fingerprint_mismatch")

    current_head = _git(root, "rev-parse", "HEAD")
    if source_commit == current_head:
        _fail("showcase_manifest_self_reference")
    if _source_commit_is_reachable(root, source_commit):
        if _git(root, "show", "-s", "--format=%T", source_commit) != source_tree:
            _fail("showcase_source_tree_mismatch")
        source_files = _git(root, "ls-tree", "-r", "--name-only", source_tree).splitlines()
        if any(path.startswith(f"{ASSET_RELATIVE_DIR.as_posix()}/") for path in source_files):
            _fail("showcase_source_tree_contains_assets")
        source_input_paths = _discover_tree_capture_input_paths(root, source_tree)
        if source_input_paths != discovered_input_paths:
            _fail("showcase_source_capture_input_paths_mismatch")
        if (
            _compute_tree_capture_input_fingerprint(root, source_tree, discovered_input_paths)
            != declared_capture_input_fingerprint
        ):
            _fail("showcase_source_capture_input_fingerprint_mismatch")
        provenance_verification = "historic_source_identity"
    else:
        provenance_verification = "capture_input_fingerprint_unreachable_source"

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
        "provenance_verification": provenance_verification,
        "capture_input_fingerprint": declared_capture_input_fingerprint,
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
