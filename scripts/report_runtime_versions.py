from __future__ import annotations

import json
import platform
from importlib.metadata import version


RUNTIME_PACKAGES = (
    "deepagents",
    "langchain",
    "langchain-core",
    "langgraph",
    "langgraph-checkpoint-sqlite",
    "langsmith",
    "fastapi",
    "pydantic",
)


def build_runtime_version_report() -> dict[str, str]:
    report = {"python": platform.python_version()}
    for package_name in RUNTIME_PACKAGES:
        report[package_name] = version(package_name)
    return report


def main() -> int:
    print(json.dumps(build_runtime_version_report(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
