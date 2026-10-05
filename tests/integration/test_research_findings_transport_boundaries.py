"""Real network/process regressions for the independent review findings."""
import importlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/decision_research_agent_tool.py"


def invoke(base, *, timeout=".1", env=None, run_id="run_fixture"):
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "PYTHONIOENCODING": "ascii"}
    environment.pop("DECISION_RESEARCH_AGENT_API_KEY", None)
    environment.pop("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", None)
    environment.update(env or {})
    return subprocess.run([sys.executable, str(TOOL), "--base-url", base,
                           "--timeout", timeout, "findings", "--run-id", run_id],
                          env=environment, capture_output=True, timeout=15)


@pytest.fixture
def raw_server():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(5)
    threads = []
    def start(operation, *, connections=1):
        def serve():
            for _ in range(connections):
                try:
                    conn, _ = listener.accept()
                except OSError:
                    return
                with conn:
                    conn.settimeout(5)
                    conn.recv(4096)
                    operation(conn)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        threads.append(thread)
        return f"http://127.0.0.1:{listener.getsockname()[1]}"
    yield start
    try:
        listener.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    listener.close()
    for thread in threads:
        thread.join(timeout=4)
        assert not thread.is_alive()


def test_header_trickle_is_terminated_before_headers_complete(raw_server):
    observed = {"disconnected": False}
    def trickle(conn):
        started = time.monotonic()
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            for _ in range(80):
                conn.sendall(b"x")
                time.sleep(.03)
            conn.sendall(b"\r\nContent-Length: 2\r\n\r\n{}")
        except OSError:
            observed.update(disconnected=True, elapsed=time.monotonic() - started)
    base = raw_server(trickle)
    cli = invoke(base)
    assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == "request_timeout"
    deadline = time.monotonic() + 1
    while not observed["disconnected"] and time.monotonic() < deadline:
        time.sleep(.02)
    assert observed["disconnected"], "request kept reading headers past its absolute deadline"
    assert observed["elapsed"] < .8


@pytest.mark.parametrize("response", [b"NOT HTTP\r\n\r\n", b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabc"])
def test_broken_http_framing_returns_json_instead_of_traceback(raw_server, response):
    base = raw_server(lambda conn: conn.sendall(response))
    cli = invoke(base, timeout="2")
    assert cli.returncode == 1
    assert json.loads(cli.stdout)["code"] == "invalid_http_response"
    assert b"Traceback" not in cli.stderr


@pytest.mark.parametrize("endpoint", ["http://localhost%0a", "\nhttp://127.0.0.1:1", "http://127.0.0.1:1 "])
def test_raw_invalid_endpoint_never_reaches_transport(endpoint):
    cli = invoke(endpoint)
    assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == "findings_config_invalid"
    assert b"Traceback" not in cli.stderr


def test_invalid_utf8_run_argument_is_a_configuration_error():
    cli = invoke("http://127.0.0.1:1", run_id=b"run_\xff")
    assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == "findings_config_invalid"
    assert b"Traceback" not in cli.stderr


def test_consumer_stops_collecting_oversized_child_before_child_finishes(tmp_path, monkeypatch):
    consumer = importlib.import_module("scripts.research_findings_consumer")
    # This is an invalid-child negative control, not a positive native proof.
    marker = tmp_path / "child-completed"
    emitter = tmp_path / "invalid-child.py"
    emitter.write_text("import pathlib,sys\nsys.stdout.buffer.write(b'x' * (9 * 1024 * 1024))\n"
                       + f"pathlib.Path({str(marker)!r}).write_text('completed')\n", encoding="utf-8")
    monkeypatch.setattr(consumer, "TOOL", emitter)
    args = type("Args", (), {"timeout": "2", "base_url": "http://127.0.0.1:1", "run_id": "run_fixture"})()
    with pytest.raises(consumer.ConsumerError) as error:
        consumer.consume(args)
    assert error.value.code == "consumer_response_invalid"
    assert not marker.exists(), "consumer buffered the complete oversized child output"


@pytest.mark.parametrize("close_stdout", [False, True])
def test_collector_deadline_covers_silent_child_and_wait_after_stdout_eof(tmp_path, close_stdout):
    consumer = importlib.import_module("scripts.research_findings_consumer")
    emitter = tmp_path / "stalled-child.py"
    emitter.write_text("import os,time\n" + ("os.close(1)\n" if close_stdout else "") + "time.sleep(2)\n")
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        consumer._run_tool([sys.executable, str(emitter)], timeout=.1)
    assert time.monotonic() - started < 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
def test_collector_timeout_stops_descendant_after_parent_exits(tmp_path):
    consumer = importlib.import_module("scripts.research_findings_consumer")
    marker = tmp_path / "descendant-completed"
    started = tmp_path / "descendant-started"
    descendant = (f"import pathlib,time; pathlib.Path({str(started)!r}).touch(); "
                  f"time.sleep(.5); pathlib.Path({str(marker)!r}).touch()")
    parent = tmp_path / "exited-parent.py"
    parent.write_text(f"import os,subprocess,sys\nsubprocess.Popen([sys.executable, '-c', {descendant!r}])\nos._exit(0)\n")
    with pytest.raises(subprocess.TimeoutExpired):
        consumer._run_tool([sys.executable, str(parent)], timeout=.2)
    assert started.exists(), "negative control did not start its descendant"
    time.sleep(.5)
    assert not marker.exists(), "timed-out descendant outlived the CLI collector"


@pytest.mark.parametrize("depth", [300, 600])
def test_deep_http_extras_cannot_expand_cli_stdout_past_its_limit(raw_server, depth):
    # Synthetic HTTP is an output-expansion negative control only.
    report = {"schema_version": "dra.research-findings.v1", "run_id": "run_fixture",
              "profile_id": "generic-evidence-report", "profile_version": "1",
              "questions": [], "findings": []}
    content = json.dumps(report)
    package = {"run_id": "run_fixture", "execution_status": "completed", "delivery_status": "ready",
               "profile_id": "generic-evidence-report", "profile_version": "1", "scope": {"questions": []},
               "review_status": "not_required", "review_decision": None, "evidence": [], "report": report,
               "artifact": {"artifact_id": "research-findings.json", "kind": "research_findings_json",
                            "media_type": "application/json", "content": content,
                            "content_hash": hashlib.sha256(content.encode()).hexdigest()}}
    extra = ["x"] * 16000
    for _ in range(depth):
        extra = {"next": extra}
    package["extra"] = extra
    body = json.dumps(package, separators=(",", ":")).encode()
    assert len(body) < 100000
    response = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    cli = invoke(raw_server(lambda conn: conn.sendall(response), connections=2), timeout="2")
    assert cli.returncode == 1 and json.loads(cli.stdout)["code"] == "response_too_large"
    assert len(cli.stdout) < 1000 and b"Traceback" not in cli.stderr
