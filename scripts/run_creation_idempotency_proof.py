#!/usr/bin/env python3
"""Deterministic proof for durable run-creation identity reconciliation."""
from __future__ import annotations

import argparse
import concurrent.futures
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_SCHEMA_VERSION = "dra.run-creation-idempotency-proof.v1"
MAX_REPORT_BYTES = 128_000
BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/run-creation-idempotency-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/run-creation-idempotency-v1.md"
CASE_IDS = (
    "lost_response_replay",
    "request_conflict",
    "concurrent_duplicate_serialization",
    "durable_restart_lookup",
    "unkeyed_independence",
    "raw_key_non_persistence",
    "tool_client_key_recovery",
)
BOUNDARIES = {
    "client_response_loss_after_scheduling": "proven",
    "durable_identity_lookup_after_restart": "proven",
    "crash_before_schedule_recovery": "not_proven",
    "exactly_once_execution": "not_claimed",
}
LIMITS = [
    "Deterministic local contract proof, not a provider or production measurement.",
    "Response loss is simulated only after current-process scheduling completes.",
    "Process or handler failure before scheduling is not recovered by this design.",
]


def _case(case_id: str, **observations: bool | int) -> dict[str, Any]:
    if case_id not in CASE_IDS:
        raise ValueError("run_idempotency_proof_case_invalid")
    if not all(isinstance(value, (bool, int)) for value in observations.values()):
        raise ValueError("run_idempotency_proof_observation_invalid")
    return {"case_id": case_id, "status": "passed", "observations": observations}


def _row_count(db_path: str, table: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


def _build_api_cases(db_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from fastapi.testclient import TestClient

    with patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "proof-local-placeholder"},
        clear=False,
    ):
        import api.server as server

    scheduled: list[str] = []

    def capture_task(coroutine, task_id, **kwargs):
        scheduled.append(task_id)
        coroutine.close()

    environment = {
        "DECISION_RESEARCH_AGENT_DB_PATH": db_path,
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "false",
        "API_SECRET": "proof-only-api-secret",
    }
    headers = {
        "X-API-Key": "proof-only-api-secret",
        "Idempotency-Key": "proof-key-response-loss-0001",
    }
    body = {"query": "fixed query", "profile_id": "generic", "scope": {}}
    with patch.dict(os.environ, environment, clear=False), patch.object(
        server, "create_tracked_task", capture_task
    ):
        client = TestClient(server.app)
        first = client.post("/api/runs", json=body, headers=headers)
        first_identity = {
            key: first.json()[key]
            for key in ("run_id", "thread_id", "segment_id")
        }
        replay = client.post("/api/runs", json=body, headers=headers)
        replay_identity = {
            key: replay.json()[key]
            for key in ("run_id", "thread_id", "segment_id")
        }
        conflict = client.post(
            "/api/runs",
            json={**body, "query": "changed query"},
            headers=headers,
        )
    lost = _case(
        "lost_response_replay",
        same_identity=first_identity == replay_identity,
        replay_marked=replay.json()["idempotent_replay"] is True,
        schedule_count=len(scheduled),
        persisted_run_count=_row_count(db_path, "research_runs_v2"),
    )
    conflict_case = _case(
        "request_conflict",
        status_is_409=conflict.status_code == 409,
        stable_code=conflict.json().get("code") == "run_idempotency_conflict",
        identity_hidden=conflict.json().get("run_id") is None,
        schedule_count=len(scheduled),
    )
    return lost, conflict_case


def _build_repository_cases(root: Path) -> list[dict[str, Any]]:
    from api.run_repository import create_or_replay_run, create_run

    race_db = str(root / "race.db")
    race_kwargs = dict(
        db_path=race_db,
        idempotency_key="proof-key-race-0001",
        thread_id=None,
        query="fixed query",
        scope={},
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        accepted = list(pool.map(lambda _: create_or_replay_run(**race_kwargs), range(6)))
    race = _case(
        "concurrent_duplicate_serialization",
        new_count=sum(not item.idempotent_replay for item in accepted),
        replay_count=sum(item.idempotent_replay for item in accepted),
        persisted_run_count=_row_count(race_db, "research_runs_v2"),
        ledger_count=_row_count(race_db, "run_create_idempotency_v1"),
    )

    restart_db = str(root / "restart.db")
    restart_kwargs = dict(
        db_path=restart_db,
        idempotency_key="proof-key-restart-0001",
        thread_id=None,
        query="fixed query",
        scope={},
    )
    first = create_or_replay_run(**restart_kwargs)
    code = (
        "import json; from api.run_repository import create_or_replay_run; "
        "value=create_or_replay_run(**json.loads(sys.argv[1])); "
        "print(json.dumps(value.model_dump(mode='json'), sort_keys=True))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import sys; " + code, json.dumps(restart_kwargs)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    restarted = json.loads(completed.stdout)
    restart = _case(
        "durable_restart_lookup",
        same_identity=(
            restarted["run_id"] == first.run_id
            and restarted["thread_id"] == first.thread_id
            and restarted["segment_id"] == first.segment_id
        ),
        replay_marked=restarted["idempotent_replay"] is True,
    )

    unkeyed_db = str(root / "unkeyed.db")
    unkeyed_first = create_run(
        db_path=unkeyed_db,
        thread_id="shared-thread",
        query="fixed query",
    )
    unkeyed_second = create_run(
        db_path=unkeyed_db,
        thread_id="shared-thread",
        query="fixed query",
    )
    unkeyed = _case(
        "unkeyed_independence",
        distinct_runs=unkeyed_first["run_id"] != unkeyed_second["run_id"],
        persisted_run_count=_row_count(unkeyed_db, "research_runs_v2"),
    )

    raw_db = root / "raw-key.db"
    raw_key = "proof-key-not-persisted-0001"
    create_or_replay_run(
        db_path=str(raw_db),
        idempotency_key=raw_key,
        thread_id=None,
        query="fixed query",
        scope={},
    )
    connection = sqlite3.connect(raw_db)
    try:
        row = connection.execute(
            "SELECT key_hash, request_hash FROM run_create_idempotency_v1"
        ).fetchone()
    finally:
        connection.close()
    raw = _case(
        "raw_key_non_persistence",
        raw_key_absent=raw_key.encode("utf-8") not in raw_db.read_bytes(),
        hashes_present=len(row[0]) == len(row[1]) == 64,
    )
    return [race, restart, unkeyed, raw]


def _build_tool_case() -> dict[str, Any]:
    from tools import decision_research_agent_tool as tool

    captured_headers: list[str | None] = []

    def timeout(req, timeout):
        captured_headers.append(req.get_header("Idempotency-key"))
        raise TimeoutError("bounded")

    output = io.StringIO()
    with patch.object(tool.request, "urlopen", timeout), redirect_stdout(output):
        exit_code = tool.main(["run", "--query", "fixed query"])
    payload = json.loads(output.getvalue())
    key = payload["idempotency_key"]

    def success(req, timeout):
        captured_headers.append(req.get_header("Idempotency-key"))
        return _FakeResponse({"status": "started", "run_id": "normalized"})

    with patch.object(tool.request, "urlopen", success):
        tool.start_run(
            query="fixed query",
            thread_id=None,
            profile_id="generic",
            scope={},
            idempotency_key=key,
            config=tool.ToolConfig(),
        )
    return _case(
        "tool_client_key_recovery",
        ambiguous_failure=exit_code == 1,
        reusable_key_present=isinstance(key, str) and key.startswith("run-create-"),
        exact_header_reused=captured_headers == [key, key],
    )


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def getcode(self) -> int:
        return 200


def build_report() -> dict[str, Any]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        lost, conflict = _build_api_cases(str(root / "api.db"))
        repository_cases = _build_repository_cases(root)
        tool_case = _build_tool_case()
    cases = [lost, conflict, *repository_cases, tool_case]
    if [case["case_id"] for case in cases] != list(CASE_IDS):
        raise ValueError("run_idempotency_proof_case_order_invalid")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "valid",
        "source": "deterministic_local",
        "cases": cases,
        "boundaries": dict(BOUNDARIES),
        "limits": list(LIMITS),
    }


def serialize_report(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Run Creation Idempotency v1 Proof",
        "",
        "Status: valid deterministic local contract proof.",
        "",
        "| Case | Status |",
        "|---|---|",
    ]
    lines.extend(f"| `{case['case_id']}` | {case['status']} |" for case in report["cases"])
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- `{key}: {value}`" for key, value in report["boundaries"].items())
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {value}" for value in report["limits"])
    return "\n".join(lines) + "\n"


def _bounded_read(path: Path) -> bytes:
    with path.open("rb") as handle:
        value = handle.read(MAX_REPORT_BYTES + 1)
    if len(value) > MAX_REPORT_BYTES:
        raise ValueError("run_idempotency_proof_baseline_invalid")
    return value


def _check() -> bool:
    report = build_report()
    return (
        _bounded_read(BASELINE_JSON_PATH) == serialize_report(report)
        and _bounded_read(BASELINE_MARKDOWN_PATH) == render_markdown(report).encode("utf-8")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("json", "markdown", "check"))
    args = parser.parse_args(argv)
    try:
        report = build_report()
        if args.command == "json":
            sys.stdout.buffer.write(serialize_report(report))
        elif args.command == "markdown":
            sys.stdout.write(render_markdown(report))
        else:
            match = (
                _bounded_read(BASELINE_JSON_PATH) == serialize_report(report)
                and _bounded_read(BASELINE_MARKDOWN_PATH)
                == render_markdown(report).encode("utf-8")
            )
            if not match:
                raise ValueError("run_idempotency_proof_baseline_invalid")
            print(json.dumps({"status": "valid", "match": True}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        print(
            json.dumps(
                {"status": "invalid", "code": "run_idempotency_proof_baseline_invalid"},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
