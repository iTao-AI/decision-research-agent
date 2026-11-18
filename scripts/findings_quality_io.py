"""Local-only JSON intake and exclusive artifact publication."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from scripts.research_findings_consumer import MAX_CHILD_BYTES, strict_json


class QualityError(ValueError):
    """An evaluation input or output failed a local contract."""


def read_json(path: Path):
    with path.open("rb") as source:
        raw = source.read(MAX_CHILD_BYTES + 1)
    if len(raw) > MAX_CHILD_BYTES:
        raise QualityError("evaluation input exceeds file limit")
    return strict_json(raw.decode("utf-8"))


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def write_new(path: Path, content: bytes, *, idempotent: bool = False) -> None:
    """Publish a complete file exclusively, checking equality after a concurrent write."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".findings-quality-") as temporary:
        temporary.write(content)
        temporary.flush()
        try:
            os.link(temporary.name, path)
        except FileExistsError:
            if idempotent and not path.is_symlink():
                with path.open("rb") as existing:
                    if existing.read(len(content) + 1) == content:
                        return
            raise QualityError("output already holds another record") from None
