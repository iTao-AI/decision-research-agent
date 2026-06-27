from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED_PATHS = {
    "README.md",
    "README_CN.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/getting-started.md",
    "docs/architecture.md",
    "docs/development/ai-assisted-engineering.md",
    "docs/reference/api-contract.md",
    "docs/superpowers/README.md",
    "docs/superpowers/plans/2026-06-27-v0-1-0-release-presentation-cleanup.md",
}

FORBIDDEN_PREFIXES = (
    "docs/superpowers/executions/",
    "openspec/",
    "spec/",
)

ALLOWED_SUPERPOWERS_PREFIXES = (
    "docs/superpowers/specs/",
    "docs/superpowers/plans/",
)

FORBIDDEN_PRIVATE_MARKERS = (
    "Deep Search Agent",
    "deep-search-agent",
    "deep_search_agent",
    "DEEP_SEARCH_AGENT_",
    "/Users/mac",
    "Developer/Career",
    ".gstack/projects",
    "/autoplan restore point",
)

FORBIDDEN_PROCESS_PHRASES = (
    "为了面试包装",
    "用于简历包装",
    "求职主线",
    "简历加分",
    "主力项目",
    "给面试官展示",
    "Career 方案窗口",
    "执行窗口汇报",
)

_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def tracked_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return sorted(
            raw.decode("utf-8")
            for raw in completed.stdout.split(b"\0")
            if raw
        )
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def presentation_violations(text: str) -> list[str]:
    violations = [
        f"private-marker-{index}"
        for index, marker in enumerate(FORBIDDEN_PRIVATE_MARKERS, start=1)
        if marker in text
    ]
    violations.extend(
        f"private-process-{index}"
        for index, phrase in enumerate(FORBIDDEN_PROCESS_PHRASES, start=1)
        if phrase in text
    )
    return violations


def superpowers_path_violations(root: Path) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for path in tracked_paths(root):
        if not path.startswith("docs/superpowers/"):
            continue
        if path == "docs/superpowers/README.md":
            continue
        if path.endswith(".md") and path.startswith(ALLOWED_SUPERPOWERS_PREFIXES):
            continue
        violations.append({"path": path, "rule": "superpowers-path"})
    return violations


def markdown_content_violations(root: Path) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for relative_path in tracked_paths(root):
        if not relative_path.endswith(".md"):
            continue
        text = (root / relative_path).read_text(encoding="utf-8")
        for rule in presentation_violations(text):
            violations.append({"path": relative_path, "rule": rule})
    return violations


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def relative_markdown_link_violations(root: Path) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for relative_path in tracked_paths(root):
        if not relative_path.endswith(".md"):
            continue
        source = root / relative_path
        text = source.read_text(encoding="utf-8")
        for match in _MARKDOWN_LINK.finditer(text):
            target = _link_target(match.group(1))
            parsed = urlsplit(target)
            if (
                not target
                or target.startswith("#")
                or target.startswith("//")
                or parsed.scheme in {"http", "https", "mailto", "data"}
            ):
                continue
            path_part = unquote(parsed.path)
            if not path_part:
                continue
            destination = (
                root / path_part.lstrip("/")
                if path_part.startswith("/")
                else source.parent / path_part
            )
            if not destination.resolve().exists():
                violations.append(
                    {
                        "path": relative_path,
                        "rule": "missing-relative-link",
                        "target": target,
                    }
                )
    return violations


def repository_violations(root: Path) -> list[dict[str, str]]:
    paths = tracked_paths(root)
    violations: list[dict[str, str]] = [
        {"path": path, "rule": "required-path-missing"}
        for path in sorted(REQUIRED_PATHS)
        if not (root / path).is_file()
    ]
    violations.extend(
        {"path": path, "rule": "forbidden-prefix"}
        for path in paths
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
    )
    violations.extend(superpowers_path_violations(root))
    violations.extend(markdown_content_violations(root))
    violations.extend(relative_markdown_link_violations(root))
    return violations


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the tracked repository presentation surface."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    violations = repository_violations(args.root.resolve())
    result = {
        "status": "ok" if not violations else "failed",
        "violations": violations,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
