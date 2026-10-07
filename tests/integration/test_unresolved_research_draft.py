"""Actual public service/persistence with a scripted producer, never model-quality proof.

The bounded loopback server is also usable for manual/browser draft acceptance.
It reuses the existing external-transport guard; production server code is intact.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILE = "generic-evidence-report"
SOURCE_URL = "https://example.com/declared-draft-source"
SNIPPET = "Declared fixed material: 🧪 independent research boundary."
ORIGINAL_SCOPE = {"questions": [
    {"question_id": "original_answered", "text": "Which fixed source was declared?"},
    {"question_id": "original_unknown", "text": "哪些条件仍需要补充证据？😀"},
    {"question_id": "original_other", "text": "Which other limits need further evidence?"},
]}


@contextmanager
def scripted_service(directory, origin=None, reject_browser_create=False):
    """Scripted outcome only; real create, dispatch, finalizer and readers remain."""
    from scripts.research_evidence_delivery_proof import guarded_runtime
    with guarded_runtime(directory, origin) as (server, patch, attempted):
        from agent.harness_contracts import FindingsCandidate, FINDINGS_CANDIDATE_PATH
        from agent.research import EvidenceEntry
        from agent.run_result import ExecutionOutcome
        from starlette.middleware import Middleware
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        requests, executions = [], []

        async def record_requests(request, call_next):
            if request.method == "POST" and request.url.path == "/api/runs":
                body = await request.body()
                payload = json.loads(body)
                row = {"payload": payload, "key": request.headers.get("Idempotency-Key")}
                requests.append(row)
                with (directory / "requests.jsonl").open("a", encoding="utf-8") as output:
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                if reject_browser_create and len(requests) == 2:
                    return JSONResponse({"code": "service_unavailable", "problem": "Declared fixture rejection",
                        "cause": "Rejected before service admission", "fix": "Check backend and confirm a new intent",
                        "retryable": False}, status_code=503)
            return await call_next(request)

        patch.setattr(server.app, "user_middleware", [
            *server.app.user_middleware, Middleware(BaseHTTPMiddleware, dispatch=record_requests)])
        patch.setattr(server.app, "middleware_stack", None)

        async def execute(query, thread_id, **kwargs):
            if kwargs["profile_id"] != PROFILE:
                raise ValueError("scripted_draft_fixture_profile_required")
            executions.append(kwargs["run_id"])
            questions = kwargs["scope"]["questions"]
            empty = query == "All unresolved fixture"
            candidate = {
                "schema_version": "dra.research-findings-candidate.v1",
                "findings": [] if empty else [{"question_id": questions[0]["question_id"],
                    "statement": "Declared scripted candidate; no autonomous quality measurement.",
                    "references": [{"source_url": SOURCE_URL, "excerpt": "🧪 independent research"}]}],
                "dispositions": [{"question_id": row["question_id"], "status": "unresolved",
                    "reason": "Declared unresolved fixture: additional evidence was not supplied."}
                    if empty or index else {"question_id": row["question_id"], "status": "candidate_findings"}
                    for index, row in enumerate(questions)],
                "limitations": ["Scripted producer/source fixture; truth and entailment are not measured."],
            }
            session_dir = directory / "sessions" / kwargs["run_id"]
            session_dir.mkdir(parents=True)
            outcome = ExecutionOutcome(thread_id=thread_id, query=query, session_dir=session_dir,
                profile_id=PROFILE, run_id=kwargs["run_id"], segment_id=kwargs["segment_id"],
                evidence_entries=[] if empty else [EvidenceEntry(thread_id=thread_id, query_text=query,
                    subagent_name="network_search", tool_name="internet_search", source_url=SOURCE_URL, snippet=SNIPPET)],
                findings_candidate=FindingsCandidate(FINDINGS_CANDIDATE_PATH, json.dumps(candidate, ensure_ascii=False)))
            kwargs["outcome_box"].publish(outcome)
            return outcome

        patch.setattr(server, "run_deep_agent", execute)
        yield server.app, requests, executions, attempted


def create_and_read(client, payload, key):
    from scripts.research_evidence_delivery_proof import wait_terminal
    response = client.post("/api/runs", json=payload, headers={"Idempotency-Key": key})
    assert response.status_code == 200, response.text
    created = response.json()
    client.portal.call(wait_terminal, created["run_id"])
    return created, read_package(client, created["run_id"])


def read_package(client, run_id):
    responses = [client.get(f"/api/runs/{run_id}{suffix}") for suffix in ("", "/findings", "/result")]
    assert all(response.status_code == 200 for response in responses)
    package = [response.json() for response in responses]
    for response in package[1:]:
        artifact = response["artifact"]
        assert hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest() == artifact["content_hash"]
    return package


@pytest.mark.parametrize("question_count", [1, 5])
def test_new_draft_public_creation_and_reconciliation_leave_original_package_unchanged(tmp_path, question_count):
    from fastapi.testclient import TestClient
    from api.run_repository import get_run
    with scripted_service(tmp_path) as (app, requests, executions, attempted):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            old_payload = {"query": ORIGINAL_SCOPE["questions"][0]["text"], "thread_id": "demo-console-old-intent",
                           "profile_id": PROFILE, "scope": ORIGINAL_SCOPE}
            old, original = create_and_read(client, old_payload, "run-create-console-old-intent")
            assert original[1]["report"]["dispositions"][1]["status"] == "unresolved"
            new_questions = [{"question_id": f"q{index + 1}", "text": f"补充证据条件 {index + 1} 😀"}
                             for index in range(question_count)]
            payload = {"query": new_questions[0]["text"], "thread_id": "demo-console-new-intent",
                       "profile_id": PROFILE, "scope": {"questions": new_questions}}
            new, package = create_and_read(client, payload, "run-create-console-new-intent")
            assert new["run_id"] != old["run_id"] and new["segment_id"] != old["segment_id"]
            assert new["thread_id"] != old["thread_id"]
            stored = get_run(run_id=new["run_id"], db_path=str(tmp_path / "runs.db"))
            assert stored["query"] == payload["query"]
            assert stored["scope"] == payload["scope"]
            assert package[1]["report"]["questions"] == new_questions
            assert package[0]["review_decision"] is None and package[0]["review_workflow"] is None
            old_ids = {row["evidence_id"] for row in original[0]["evidence"]}
            new_ids = {row["evidence_id"] for row in package[0]["evidence"]}
            assert old_ids and new_ids and old_ids.isdisjoint(new_ids)
            assert all(row["verification_status"] == "unverified" for row in package[0]["evidence"])
            assert all(row.startswith(f"ev_{new['run_id']}_") for row in new_ids)
            replay = client.post("/api/runs", json=payload, headers={"Idempotency-Key": "run-create-console-new-intent"})
            assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
            assert replay.json()["run_id"] == new["run_id"]
            assert read_package(client, old["run_id"]) == original
            assert read_package(client, new["run_id"]) == package
            assert requests[1] == requests[2] and requests[0]["key"] != requests[1]["key"]
            assert requests[1]["payload"] == payload
            assert len(executions) == 2 and attempted == []


def test_public_all_unresolved_fixture_remains_blocked_without_a_report(tmp_path):
    from fastapi.testclient import TestClient
    from scripts.research_evidence_delivery_proof import wait_terminal
    with scripted_service(tmp_path) as (app, _, _, attempted):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            created = client.post("/api/runs", json={"query": "All unresolved fixture", "profile_id": PROFILE,
                "scope": {"questions": [{"question_id": "q1", "text": "All unresolved fixture"}]}}).json()
            client.portal.call(wait_terminal, created["run_id"])
            status = client.get(f"/api/runs/{created['run_id']}").json()
            assert status["delivery_status"] == "blocked" and "empty_research_output" in status["findings_issues"]
            for suffix in ("findings", "result"):
                response = client.get(f"/api/runs/{created['run_id']}/{suffix}")
                assert response.status_code == 409 and response.json()["code"] == "run_delivery_blocked"
            assert attempted == []


def test_explicit_fixture_rejection_creates_no_run_and_later_fresh_intent_succeeds(tmp_path):
    from fastapi.testclient import TestClient
    with scripted_service(tmp_path, origin="http://127.0.0.1:5179", reject_browser_create=True) as (app, requests, executions, attempted):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            old, original = create_and_read(client, {"query": ORIGINAL_SCOPE["questions"][0]["text"],
                "profile_id": PROFILE, "scope": ORIGINAL_SCOPE}, "fixture-source-key")
            payload = {"query": "Edited after a definite rejection", "thread_id": "fixture-recovered-thread",
                       "profile_id": PROFILE, "scope": {"questions": [{"question_id": "q1", "text": "Edited after a definite rejection"}]}}
            rejected = client.post("/api/runs", json=payload, headers={"Idempotency-Key": "fixture-rejected-key",
                                                                     "Origin": "http://127.0.0.1:5179"})
            assert rejected.status_code == 503 and rejected.json()["code"] == "service_unavailable"
            assert rejected.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5179"
            assert executions == [old["run_id"]] and read_package(client, old["run_id"]) == original
            recovered, package = create_and_read(client, payload, "fixture-recovered-key")
            assert recovered["run_id"] != old["run_id"] and package[0]["scope"] == payload["scope"]
            assert len(executions) == 2 and len(requests) == 3 and attempted == []
            assert read_package(client, old["run_id"]) == original


def serve(directory, origin, port, seconds, reject_browser_create=False):
    """Bounded actual HTTP fixture for the browser; source run created via POST."""
    from fastapi.testclient import TestClient
    from scripts.research_evidence_delivery_proof import loopback
    from urllib.parse import urlsplit
    import threading
    import uvicorn
    parsed = urlsplit(origin)
    if (parsed.scheme != "http" or not loopback(parsed.hostname) or parsed.port is None
            or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("draft_fixture_origin_invalid")
    directory.mkdir(parents=True, exist_ok=True)
    with scripted_service(directory, origin, reject_browser_create) as (app, requests, executions, attempted):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            source, original = create_and_read(client, {"query": ORIGINAL_SCOPE["questions"][0]["text"],
                "thread_id": "draft-fixture-source", "profile_id": PROFILE, "scope": ORIGINAL_SCOPE}, "draft-fixture-source-key")
        snapshot = {"source_run": source, "original_package": original,
            "producer": "scripted outcome and declared source; actual public service/persistence", "model_calls": 0,
            "reject_first_browser_create": reject_browser_create}
        (directory / "source-package.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"api": f"http://127.0.0.1:{port}", "origin": origin, "source_run_id": source["run_id"],
                          "producer": snapshot["producer"], "expires_after_seconds": seconds}), flush=True)
        api = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        timer = threading.Timer(seconds, lambda: setattr(api, "should_exit", True))
        timer.start()
        try:
            api.run()
        finally:
            timer.cancel()
            (directory / "service-summary.json").write_text(json.dumps({"requests": requests,
                "executions": executions, "external_attempts": attempted, "model_calls": 0}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve"])
    parser.add_argument("--origin", required=True)
    parser.add_argument("--port", type=int, default=8019)
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--reject-first-browser-create", action="store_true",
                        help="Declare one 503 before admission, then allow ordinary creates for input-recovery acceptance")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 1 <= args.seconds <= 1800:
        parser.error("fixture port must be 1024–65535 and duration 1–1800 seconds")
    serve(args.directory, args.origin, args.port, args.seconds, args.reject_first_browser_create)
