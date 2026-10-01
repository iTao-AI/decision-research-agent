"""Proof contract: real native results must match independent declarations."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/research_evidence_delivery_proof.py"


def invoke(*args):
    env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false", "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_native_proof_four_cases_match_independent_expectations_and_reader_checkpoints(tmp_path):
    result = invoke("check", "--output-dir", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "research-evidence-delivery-v1.json").read_text())
    expected = json.loads((ROOT / "tests/fixtures/research-evidence-delivery/expected.json").read_text())["cases"]
    assert {item["case_id"] for item in report["cases"]} == set(expected)
    for item in report["cases"]:
        assert item["expected"] == expected[item["case_id"]]
        assert item["observed"] == item["expected"]
        assert item["passed"] is True
        assert all(item["checkpoints"].values())
        assert item["runtime"]["tool_calls"][:3] == ["task", "internet_search", "write_file"]
        assert item["runtime"]["source_tool_status"] == "success"
        assert item["runtime"]["model_calls"] == 5
        assert item["http_reader"]["evidence_verification_states"] == (["unverified"] if item["observed"]["evidence_count"] else [])
        for artifact in item["http_reader"]["artifacts"]:
            assert artifact["own_byte_hash_validated"] is True
    assert report["measurements"]["truth"] == "not_measured"
    assert report["measurements"]["entailment"] == "not_measured"
    assert report["measurements"]["provider_instruction_obedience"] == "not_measured"
    assert report["measurements"]["production_research_quality"] == "not_measured"
    assert "browser" not in report["consumer_scope"]
    assert "/Users/" not in json.dumps(report)


def test_native_check_is_reproducible_without_replacing_artifact_hashes_or_ui_receipts(tmp_path):
    receipt = tmp_path / "research-evidence-delivery-ui-v1.json"
    receipt.write_text('{"parent_receipt": true}')
    first = invoke("check", "--output-dir", str(tmp_path))
    assert first.returncode == 0, first.stdout + first.stderr
    content = (tmp_path / "research-evidence-delivery-v1.json").read_bytes()
    second = invoke("check", "--output-dir", str(tmp_path))
    assert second.returncode == 0, second.stdout + second.stderr
    assert (tmp_path / "research-evidence-delivery-v1.json").read_bytes() == content
    assert receipt.read_text() == '{"parent_receipt": true}'


def test_help_avoids_provider_startup():
    result = invoke("--help")
    assert result.returncode == 0
    assert "check" in result.stdout and "serve" in result.stdout
    assert "LLM" not in result.stderr


def test_fixture_server_rejects_unknown_intent_before_native_dispatch_and_has_explicit_cors(tmp_path):
    # This catches the proof server accepting arbitrary live research despite
    # declaring a fixture-only boundary, and browser Origin scope drifting.
    from scripts.research_evidence_delivery_proof import guarded_runtime, seed
    from fastapi.testclient import TestClient
    with guarded_runtime(tmp_path, 'http://127.0.0.1:5175') as (server, patch, attempted):
        report = seed(server, tmp_path, patch, attempted)
        with TestClient(server.app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
            response = client.post('/api/runs', json={'query': 'arbitrary public web question', 'profile_id': 'generic-evidence-report'})
            assert response.status_code == 422
            assert response.json()['code'] == 'research_evidence_proof_fixture_only'
            assert 'run_id' not in response.json()
            allowed = client.get('/health', headers={'Origin': 'http://127.0.0.1:5175'})
            assert allowed.status_code == 200
            assert allowed.headers['access-control-allow-origin'] == 'http://127.0.0.1:5175'
            denied = client.get(f"/api/runs/{report['cases'][0]['run_id']}", headers={'Origin': 'http://127.0.0.1:5176'})
            assert denied.status_code == 403
            for case in report['cases']:
                assert client.get(f"/api/runs/{case['run_id']}").status_code == 200


def test_guard_blocks_actual_provider_source_and_external_socket_paths(tmp_path):
    from scripts.research_evidence_delivery_proof import guarded_runtime, ProofError
    import socket
    import pytest
    with guarded_runtime(tmp_path) as (_, _, attempted):
        import agent.llm as llm
        import tools.tavily_tools as tavily
        import tools.mysql_tools as mysql
        import tools.ragflow_tools as ragflow
        import langsmith
        for operation in (llm.create_llm_model, tavily._tavily_search, mysql.list_sql_tables.func,
                          ragflow.get_assistant_list.func, langsmith.Client):
            with pytest.raises(ProofError):
                operation()
        with pytest.raises(ProofError):
            socket.getaddrinfo('example.com', 443)
        with socket.socket() as sock:
            with pytest.raises(ProofError):
                sock.connect(('203.0.113.1', 443))
        assert attempted == ['external_provider_or_source_path'] * 5 + ['external_resolution', 'external_transport']


def test_serve_actual_loopback_http_readers_and_bounded_cleanup(tmp_path):
    import socket
    import time
    import urllib.request
    import urllib.error
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {**os.environ, 'TMPDIR': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1',
           'LANGSMITH_TRACING': 'false', 'LANGCHAIN_TRACING_V2': 'false', 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, str(SCRIPT), 'serve', '--origin',
        'http://127.0.0.1:5175', '--port', str(port), '--seconds', '3'], cwd=ROOT,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.5) as response:
                    assert response.status == 200
                break
            except urllib.error.URLError:
                assert time.monotonic() < deadline, 'fixture server never became ready'
                time.sleep(.05)
        for run_id, want in [('run_6bc0b688d0ac536eb2d612086d406868', 200),
                             ('run_d057d451d4785220aa34d5887f3e061d', 409)]:
            request = urllib.request.Request(f'http://127.0.0.1:{port}/api/runs/{run_id}/findings',
                                             headers={'Origin': 'http://127.0.0.1:5175'})
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    assert response.status == want
                    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5175'
                    assert json.load(response)['report']['run_id'] == run_id
            except urllib.error.HTTPError as error:
                assert error.code == want
                assert json.load(error)['code'] == 'run_delivery_blocked'
        stdout, stderr = process.communicate(timeout=7)
        assert process.returncode == 0, stdout + stderr
        assert '"expires_after_seconds": 3' in stdout
        assert not list(tmp_path.glob('dra-research-evidence-proof-*'))
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


def test_serve_sigint_has_bounded_exit_and_cleans_actual_native_runtime(tmp_path):
    import signal
    import socket
    import time
    import urllib.request
    import urllib.error
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {**os.environ, 'TMPDIR': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1',
           'LANGSMITH_TRACING': 'false', 'LANGCHAIN_TRACING_V2': 'false', 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, str(SCRIPT), 'serve', '--origin',
        'http://127.0.0.1:5175', '--port', str(port), '--seconds', '60'], cwd=ROOT,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.5) as response:
                    assert response.status == 200
                break
            except urllib.error.URLError:
                assert time.monotonic() < deadline, 'fixture server never became ready'
                time.sleep(.05)
        runtime_dirs = list(tmp_path.glob('dra-research-evidence-proof-*'))
        assert len(runtime_dirs) == 1
        assert (runtime_dirs[0] / 'runs.db').is_file()
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=7)
        assert process.returncode == 130, stderr
        assert stderr.splitlines()[-1] == 'research_evidence_proof_interrupted'
        assert 'Traceback' not in stderr and 'KeyboardInterrupt' not in stderr
        assert str(ROOT) not in stdout + stderr
        assert str(runtime_dirs[0]) not in stdout + stderr
        assert not runtime_dirs[0].exists()
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


def test_serve_invalid_origin_retains_bounded_failure_exit():
    result = invoke('serve', '--origin', 'https://example.com:5175', '--seconds', '1')
    assert result.returncode == 1
    assert result.stderr.strip() == 'research_evidence_proof_failed'
