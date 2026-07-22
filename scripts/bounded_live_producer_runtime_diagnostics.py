"""Closed in-container reader for bounded-producer limiter diagnostics."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator


CALL_BUDGET_SIDECAR_SCHEMA_VERSION = "dra.call-budget-origin-sidecar.v1"
CALL_BUDGET_SIDECAR_BYTES_MAX = 4096
_COUNT_MAX = 1_000_000
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)


class RuntimeDiagnosticReadError(Exception):
    """Stable failure for an absent or unsafe runtime diagnostic."""

    def __init__(self) -> None:
        super().__init__("runtime_diagnostic_invalid")
        self.code = "runtime_diagnostic_invalid"


class CallBudgetLimiter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    limiter_kind: Literal["model", "tool"]
    tool_scope: Literal["not_applicable", "all_tools", "task"]
    run_count: StrictInt
    run_limit: StrictInt
    thread_count: StrictInt
    thread_limit: StrictInt | None
    agent_role: Literal["not_observed"]

    @model_validator(mode="after")
    def validate_closed_semantics(self) -> "CallBudgetLimiter":
        counts = (self.run_count, self.thread_count)
        limits = (self.run_limit, self.thread_limit)
        if any(value < 0 or value > _COUNT_MAX for value in counts):
            raise ValueError("call_budget_counter_invalid")
        if any(
            value is not None and (value < 1 or value > _COUNT_MAX)
            for value in limits
        ):
            raise ValueError("call_budget_limit_invalid")
        if self.limiter_kind == "model" and self.tool_scope != "not_applicable":
            raise ValueError("call_budget_scope_invalid")
        if self.limiter_kind == "tool" and self.tool_scope == "not_applicable":
            raise ValueError("call_budget_scope_invalid")
        return self


class CallBudgetOriginSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[CALL_BUDGET_SIDECAR_SCHEMA_VERSION]
    limiter: CallBudgetLimiter


def parse_call_budget_sidecar(
    value: Mapping[str, object] | bytes,
) -> CallBudgetOriginSidecar:
    if isinstance(value, bytes):
        return CallBudgetOriginSidecar.model_validate_json(value, strict=True)
    return CallBudgetOriginSidecar.model_validate(value, strict=True)


def serialize_call_budget_sidecar(value: CallBudgetOriginSidecar) -> bytes:
    raw = (
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    if len(raw) > CALL_BUDGET_SIDECAR_BYTES_MAX:
        raise ValueError("runtime_diagnostic_invalid")
    return raw


def _open_directory(name: str, *, directory_fd: int) -> int:
    return os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=directory_fd,
    )


def read_call_budget_sidecar(
    run_id: str,
    *,
    output_root: Path = Path("/app/output"),
) -> CallBudgetOriginSidecar:
    descriptors: list[int] = []
    try:
        if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
            raise RuntimeDiagnosticReadError()
        root_fd = os.open(output_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root_fd)
        current = root_fd
        for component in ("operator-diagnostics", run_id):
            current = _open_directory(component, directory_fd=current)
            descriptors.append(current)
        file_fd = os.open(
            "call-budget-v1.json",
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=current,
        )
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size > CALL_BUDGET_SIDECAR_BYTES_MAX
        ):
            raise RuntimeDiagnosticReadError()
        raw = os.read(file_fd, CALL_BUDGET_SIDECAR_BYTES_MAX + 1)
        if len(raw) > CALL_BUDGET_SIDECAR_BYTES_MAX or os.read(file_fd, 1):
            raise RuntimeDiagnosticReadError()
        parsed = parse_call_budget_sidecar(raw)
        if serialize_call_budget_sidecar(parsed) != raw:
            raise RuntimeDiagnosticReadError()
        after = os.fstat(file_fd)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mode,
            value.st_uid,
            value.st_nlink,
        )
        if identity(before) != identity(after):
            raise RuntimeDiagnosticReadError()
        return parsed
    except RuntimeDiagnosticReadError:
        raise
    except Exception as exc:
        raise RuntimeDiagnosticReadError() from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 3 or arguments[:2] != ["read", "--run-id"]:
            raise RuntimeDiagnosticReadError()
        value = read_call_budget_sidecar(arguments[2])
        sys.stdout.buffer.write(serialize_call_budget_sidecar(value))
        return 0
    except Exception:
        sys.stderr.write('{"code":"runtime_diagnostic_invalid"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
