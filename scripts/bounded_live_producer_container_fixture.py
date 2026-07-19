"""Provider-free container fixture for the bounded producer Docker gate."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from agent.harness_contracts import ReportCandidate
from agent.research import EvidenceEntry
from agent.run_result import ExecutionOutcome
from api.run_dispatch_models import RunDispatchClaim
from api.run_dispatch_repository import start_run_dispatch
from api.run_dispatch_worker import RunDispatchWorker
from api.run_repository import finalize_run_transaction
from api.run_result_service import build_generic_result_artifact


FIXTURE_FLAG = "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE"
_FIXTURE_TIMESTAMP = "2026-07-18T00:00:00+00:00"
_agent_calls = 0


def _enabled() -> bool:
    return os.environ.get(FIXTURE_FLAG) == "true"


def _fixture_evidence(claim: RunDispatchClaim) -> list[EvidenceEntry]:
    return [
        EvidenceEntry(
            thread_id=claim.thread_id,
            query_text=claim.query,
            subagent_name="bounded-container-fixture",
            tool_name="provider-free-fixture",
            source_url="https://docs.python.org/3/howto/free-threading-python.html",
            snippet="Official Python documentation fixture citation.",
            retrieved_at=_FIXTURE_TIMESTAMP,
            tool_call_id="fixture-docs-python",
            citation_status="cited",
            verification_status="unverified",
            created_at="2026-07-18T00:00:00+00:00",
        ),
        EvidenceEntry(
            thread_id=claim.thread_id,
            query_text=claim.query,
            subagent_name="bounded-container-fixture",
            tool_name="provider-free-fixture",
            source_url="https://peps.python.org/pep-0703/",
            snippet="Python Enhancement Proposal fixture citation.",
            retrieved_at=_FIXTURE_TIMESTAMP,
            tool_call_id="fixture-pep-703",
            citation_status="cited",
            verification_status="unverified",
            created_at="2026-07-18T00:00:01+00:00",
        ),
    ]


def finalize_fixture_claim(db_path: str, claim: RunDispatchClaim) -> None:
    """Cross the production start fence and finalize one deterministic result."""

    if not _enabled():
        raise RuntimeError("fixture_disabled")
    started = start_run_dispatch(db_path=db_path, claim=claim)
    if started is not True:
        raise RuntimeError("fixture_start_fence_failed")
    evidence = _fixture_evidence(claim)
    evidence_ids = [
        f"ev_{claim.run_id}_{entry.evidence_fingerprint}" for entry in evidence
    ]
    content = (
        "# Provider-free container fixture brief\n\n"
        "This deterministic result validates the application persistence path; "
        "it is not provider-backed research.\n\n"
        f"- Python documentation citation: [{evidence_ids[0]}]\n"
        f"- PEP citation: [{evidence_ids[1]}]\n"
    )
    outcome = ExecutionOutcome(
        thread_id=claim.thread_id,
        query=claim.query,
        session_dir=Path("."),
        profile_id=claim.profile_id,
        run_id=claim.run_id,
        segment_id=claim.segment_id,
        state_version=1,
        evidence_entries=evidence,
        report_candidate=ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content=content,
        ),
    )
    artifact = build_generic_result_artifact(outcome)
    finalized = finalize_run_transaction(
        db_path=db_path,
        run_id=claim.run_id,
        segment_id=claim.segment_id,
        expected_state_version=1,
        allowed_previous_statuses={"running"},
        execution_status="completed",
        review_status="not_required",
        delivery_status="ready",
        evidence_entries=evidence,
        artifacts=[artifact],
    )
    if finalized is not True:
        raise RuntimeError("fixture_finalization_failed")
    if _agent_calls != 0:
        raise RuntimeError("fixture_agent_path_called")


def create_fixture_worker(db_path: str | Path) -> RunDispatchWorker:
    if not _enabled():
        raise RuntimeError("fixture_disabled")
    normalized = str(db_path)
    return RunDispatchWorker(
        db_path=normalized,
        scheduler=lambda claim: finalize_fixture_claim(normalized, claim),
    )


async def _forbid_agent_path(*_args: object, **_kwargs: object) -> None:
    global _agent_calls
    _agent_calls += 1
    raise RuntimeError("fixture_agent_path_forbidden")


def serve() -> int:
    if not _enabled():
        return 1
    import api.server as server
    import uvicorn

    server.create_run_dispatch_worker = create_fixture_worker
    server.run_deep_agent = _forbid_agent_path
    uvicorn.run(
        server.app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
        access_log=False,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments != ["serve"]:
        sys.stderr.write('{"code":"fixture_command_invalid"}\n')
        return 1
    if not _enabled():
        sys.stderr.write('{"code":"fixture_disabled"}\n')
        return 1
    try:
        return serve()
    except Exception:
        sys.stderr.write('{"code":"fixture_start_failed"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
