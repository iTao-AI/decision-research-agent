"""Real subprocess/HTTP positive proof; declared DB/HTTP negative controls."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from urllib import error, request

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/decision_research_agent_tool.py"
CONSUMER = ROOT / "scripts/research_findings_consumer.py"
PRODUCER = ROOT / "scripts/research_evidence_delivery_proof.py"
CASES = [
    ("complete", "run_6bc0b688d0ac536eb2d612086d406868", 1, 0, 1, 0),
    ("partial", "run_e4383ba9ee7353e89f6cc82563dd1470", 2, 1, 1, 0),
    ("contradictory", "run_558e4f7a1d965b018568e8669dd6f2be", 1, 0, 2, 1),
]


def child_env():
    env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "LANGSMITH_TRACING": "false",
           "LANGCHAIN_TRACING_V2": "false", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "ascii"}
    for key in ("DECISION_RESEARCH_AGENT_URL", "DECISION_RESEARCH_AGENT_API_KEY", "DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS"):
        env.pop(key, None)
    return env


def invoke(script, args, *, env=None):
    return subprocess.run([sys.executable, str(script), *args], cwd=ROOT, env=env or child_env(),
                          capture_output=True, timeout=25)


def public_json(base, path, *, authenticated=False):
    headers = {"X-API-Key": "test-integration-key"} if authenticated else {}
    with request.urlopen(request.Request(base + path, headers=headers), timeout=2) as response:
        return json.load(response)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(base, process=None):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            public_json(base, "/health")
            return
        except (OSError, error.URLError):
            if process is not None:
                assert process.poll() is None, "native fixture server exited before readiness"
            time.sleep(.05)
    pytest.fail("local reader server did not become ready")


@pytest.fixture(scope="module")
def native_server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("findings-native-server")
    port = free_port()
    env = child_env()
    env["TMPDIR"] = str(directory)
    with (directory / "server.stdout").open("wb") as stdout, (directory / "server.stderr").open("wb") as stderr:
        process = subprocess.Popen([sys.executable, str(PRODUCER), "serve", "--origin", "http://127.0.0.1:5175",
                                    "--port", str(port), "--seconds", "180"], cwd=ROOT, env=env,
                                   stdout=stdout, stderr=stderr)
        base = f"http://127.0.0.1:{port}"
        try:
            wait_ready(base, process)
            yield base
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize("case_id,run_id,questions,unresolved,refs,contradictions", CASES)
def test_real_native_cli_and_separate_consumer_preserve_declared_outcomes(
    native_server, tmp_path, case_id, run_id, questions, unresolved, refs, contradictions
):
    base = native_server
    status = public_json(base, f"/api/runs/{run_id}")
    authoritative = public_json(base, f"/api/runs/{run_id}/findings")
    cli = invoke(TOOL, ["--base-url", base, "--timeout", "2", "findings", "--run-id", run_id])
    assert cli.returncode == 0, cli.stderr
    value = json.loads(cli.stdout.decode("utf-8"))
    assert {key: value[key] for key in authoritative} == authoritative
    assert value["evidence"] == status["evidence"]
    markdown = invoke(TOOL, ["--base-url", base, "--timeout", "2", "findings", "--run-id", run_id, "--format", "markdown"])
    stored = public_json(base, f"/api/runs/{run_id}/result")["artifact"]
    assert markdown.returncode == 0, markdown.stderr
    assert markdown.stdout == stored["content"].encode("utf-8")
    assert hashlib.sha256(markdown.stdout).hexdigest() == stored["content_hash"]
    target = tmp_path / f"{case_id}.json"
    consumed = invoke(CONSUMER, ["--base-url", base, "--timeout", "2", "--run-id", run_id, "--output", str(target)])
    assert consumed.returncode == 0, consumed.stdout + consumed.stderr
    receipt = json.loads(target.read_bytes())
    assert json.loads(consumed.stdout) == receipt
    assert receipt["run_id"] == run_id
    assert receipt["profile_id"] == "generic-evidence-report" and receipt["profile_version"] == "1"
    assert receipt["execution_status"] == "completed" and receipt["delivery_status"] == "ready"
    assert len(receipt["questions"]) == questions
    assert sum(row["status"] == "unresolved" for row in receipt["questions"]) == unresolved
    assert len(receipt["references"]) == refs
    assert len(receipt["reported_contradictions"]) == contradictions
    assert [row["verification_status"] for row in receipt["references"]] == ["unverified"] * refs
    if case_id == "partial":
        unresolved_row = next(row for row in receipt["questions"] if row["status"] == "unresolved")
        assert unresolved_row["reason"] == authoritative["report"]["dispositions"][1]["reason"]
        assert unresolved_row["finding_ids"] == []
    assert receipt["artifact"]["content_hash"] == authoritative["artifact"]["content_hash"]
    assert all(receipt["checks"].values())
    assert public_json(base, f"/api/runs/{run_id}") == status


@pytest.mark.parametrize("run_id,code", [("run_d057d451d4785220aa34d5887f3e061d", "run_delivery_blocked"),
                                       ("run_missing", "run_not_found")])
def test_actual_blocked_and_missing_runs_have_error_exit_and_no_receipt(native_server, tmp_path, run_id, code):
    for output_format in ("json", "markdown"):
        cli = invoke(TOOL, ["--base-url", native_server, "findings", "--run-id", run_id, "--format", output_format])
        assert cli.returncode == 1
        assert json.loads(cli.stdout)["code"] == code
    target = tmp_path / "failed-receipt.json"
    consumed = invoke(CONSUMER, ["--base-url", native_server, "--run-id", run_id, "--output", str(target)])
    assert consumed.returncode == 1 and json.loads(consumed.stdout)["code"] == code
    assert not target.exists()


@pytest.fixture
def controlled_reader(tmp_path, monkeypatch, authenticated_runtime_access):
    # Manually built runs are NEGATIVE/authority controls, never the native
    # producer or separate-consumer success proof above.
    from agent.research import EvidenceEntry
    from agent.research_findings_contracts import validate_research_findings_scope
    from api.research_findings import build_research_findings_artifacts
    from api.run_repository import create_run, finalize_run_transaction
    from api.server import app
    import uvicorn
    db = str(tmp_path / "controlled.db")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", db)
    scope = validate_research_findings_scope({}, query="Synthetic question")
    created = create_run(thread_id="controlled", query="Synthetic question", profile_id="generic-evidence-report",
                         profile_version="1", scope=scope.model_dump(mode="json"), db_path=db)
    candidate = {"schema_version": "dra.research-findings-candidate.v1", "findings": [{"question_id": "q1",
        "statement": "Synthetic candidate", "references": [{"source_url": "https://example.com/source", "excerpt": "observed"}]}],
        "dispositions": [{"question_id": "q1", "status": "candidate_findings"}]}
    built = build_research_findings_artifacts(run_id=created["run_id"], scope=scope,
        candidate_content=json.dumps(candidate), evidence_entries=[EvidenceEntry(thread_id="controlled", query_text="Synthetic question",
        subagent_name="network_search", tool_name="internet_search", source_url="https://example.com/source", snippet="A 🧪 observed material.")])
    assert finalize_run_transaction(run_id=created["run_id"], segment_id=created["segment_id"], expected_state_version=0,
        allowed_previous_statuses={"pending"}, execution_status="completed", delivery_status="ready",
        evidence_entries=built.evidence_entries, artifacts=built.artifacts, db_path=db)
    base = f"http://127.0.0.1:{free_port()}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=int(base.rsplit(":", 1)[1]),
                                          log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        wait_ready(base)
        yield base, db, created["run_id"], built
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("tamper", ["foreign_ref", "offset", "unsafe_source", "rehash_markdown", "hash", "missing_artifact"])
def test_real_reader_rejects_tampering_through_cli_and_consumer(controlled_reader, tmp_path, tamper):
    base, db, run_id, built = controlled_reader
    artifact_id, content = "research-findings.json", built.artifacts[0]["content"]
    report = json.loads(content)
    if tamper == "foreign_ref": report["findings"][0]["references"][0]["evidence_id"] = "ev_other_run_fake"
    elif tamper == "offset": report["findings"][0]["references"][0]["excerpt_start"] += 1
    elif tamper == "unsafe_source": report["findings"][0]["references"][0]["source_url"] = "javascript:alert(1)"
    elif tamper == "rehash_markdown": artifact_id, content = "research-report.md", "# Rehashed arbitrary report"
    if tamper in {"foreign_ref", "offset", "unsafe_source"}: content = json.dumps(report)
    with sqlite3.connect(db) as conn:
        if tamper == "missing_artifact":
            conn.execute("DELETE FROM run_artifacts_v2 WHERE run_id=? AND artifact_id=?", (run_id, artifact_id))
        else:
            digest = "0" * 64 if tamper == "hash" else hashlib.sha256(content.encode()).hexdigest()
            conn.execute("UPDATE run_artifacts_v2 SET content=?,content_hash=? WHERE run_id=? AND artifact_id=?",
                         (content, digest, run_id, artifact_id))
    env = child_env()
    env["DECISION_RESEARCH_AGENT_API_KEY"] = "test-integration-key"
    for output_format in ("json", "markdown"):
        cli = invoke(TOOL, ["--base-url", base, "findings", "--run-id", run_id, "--format", output_format], env=env)
        assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == "run_result_unavailable"
    target = tmp_path / "tampered.json"
    consumed = invoke(CONSUMER, ["--base-url", base, "--run-id", run_id, "--output", str(target)], env=env)
    assert consumed.returncode == 1 and json.loads(consumed.stdout)["code"] == "run_result_unavailable"
    assert not target.exists()


def test_actual_approval_projection_keeps_unverified_evidence(controlled_reader, tmp_path):
    base, db, run_id, _ = controlled_reader
    # Declared state projection control, not a new review/approval workflow.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_runs_v2 SET review_status='resolved' WHERE run_id=?", (run_id,))
        conn.execute("INSERT INTO review_bundles_v2 VALUES (?,?,1,'approved','{}','2026-10-05')", ("synthetic-review", run_id))
        conn.execute("INSERT INTO review_decisions_v2 VALUES (?,?,?,1,'approve',NULL,?,?,1,'2026-10-05')",
                     ("synthetic-decision", run_id, "synthetic-review", "0" * 64, "1" * 64))
    observed = public_json(base, f"/api/runs/{run_id}", authenticated=True)
    assert observed["review_decision"]["action"] == "approve"
    assert observed["evidence"][0]["verification_status"] == "unverified"
    env = child_env()
    env["DECISION_RESEARCH_AGENT_API_KEY"] = "test-integration-key"
    target = tmp_path / "approved.json"
    consumed = invoke(CONSUMER, ["--base-url", base, "--run-id", run_id, "--output", str(target)], env=env)
    assert consumed.returncode == 0, consumed.stdout + consumed.stderr
    receipt = json.loads(target.read_bytes())
    assert receipt["review_decision_action"] == "approve"
    assert receipt["references"][0]["verification_status"] == "unverified"


@pytest.mark.parametrize("state,code", [("pending", "run_not_terminal"), ("generic", "run_result_unavailable"),
                                       ("unauthenticated", "api_key_invalid")])
def test_actual_other_state_or_unauthenticated_run_has_no_consumer_receipt(controlled_reader, tmp_path, state, code):
    base, db, run_id, _ = controlled_reader
    if state in {"pending", "generic"}:
        with sqlite3.connect(db) as conn:
            if state == "pending": conn.execute("UPDATE research_runs_v2 SET execution_status='pending' WHERE run_id=?", (run_id,))
            else: conn.execute("UPDATE research_runs_v2 SET profile_id='generic' WHERE run_id=?", (run_id,))
    env = child_env()
    if state != "unauthenticated": env["DECISION_RESEARCH_AGENT_API_KEY"] = "test-integration-key"
    target = tmp_path / "other.json"
    consumed = invoke(CONSUMER, ["--base-url", base, "--run-id", run_id, "--output", str(target)], env=env)
    assert consumed.returncode == 1 and json.loads(consumed.stdout)["code"] == code
    assert not target.exists()


@pytest.mark.parametrize("mode,code", [("slow", "request_timeout"), ("trickle", "request_timeout"),
    ("utf8", "invalid_json_response"), ("huge", "response_too_large"), ("redirect", "http_302")])
def test_actual_bad_transport_has_bounded_cli_failure(tmp_path, mode, code):
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            try:
                if mode == "slow": time.sleep(.5)
                self.send_response(302 if mode == "redirect" else 200)
                if mode == "redirect": self.send_header("Location", "/must-not-follow")
                self.end_headers()
                if mode == "trickle":
                    for _ in range(30):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(.03)
                else: self.wfile.write(b"\xff" if mode == "utf8" else b"x" * (4 * 1024 * 1024 + 65537) if mode == "huge" else b"{}")
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = time.monotonic()
        timeout = ".1" if mode in {"slow", "trickle"} else "2"
        cli = invoke(TOOL, ["--base-url", f"http://127.0.0.1:{server.server_port}", "--timeout", timeout,
                            "findings", "--run-id", "run_fixture"])
        assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == code
        assert time.monotonic() - started < 3
        assert paths == ["/api/runs/run_fixture/findings"]
        assert b"Traceback" not in cli.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
