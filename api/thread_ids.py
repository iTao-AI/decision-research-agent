import re
from pathlib import Path


_THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_thread_id(thread_id: str) -> str:
    if not _THREAD_ID_PATTERN.fullmatch(thread_id):
        raise ValueError("thread_id must use 1-128 letters, digits, dots, underscores, or hyphens")
    return thread_id


def safe_session_dir(root: Path, thread_id: str) -> Path:
    validated = validate_thread_id(thread_id)
    resolved_root = root.resolve()
    session_dir = (resolved_root / f"session_{validated}").resolve()
    if not session_dir.is_relative_to(resolved_root):
        raise ValueError("thread_id resolves outside session root")
    return session_dir
