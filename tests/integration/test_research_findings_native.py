"""Provider-free proof using installed generic harness and HTTP delivery consumers."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from api.research_execution_service import ResearchExecutionService
from api.server import app
from scripts.research_evidence_native_fixture import (
    PROFILE, SOURCE_URL, SNIPPET, AUTH_HEADERS, native_candidate,
    NativeFindingsModel, build_native_findings_fixture,
)

pytestmark = pytest.mark.usefixtures('authenticated_runtime_access')


async def wait_terminal(run_id):
    from api.run_repository import get_run
    for _ in range(200):
        status = await asyncio.to_thread(get_run, run_id=run_id)
        if status['execution_status'] in {'completed', 'failed'}:
            return status
        await asyncio.sleep(.02)
    raise AssertionError('native dispatched run did not terminate')


def execute_native_http(tmp_path, monkeypatch, *, mode='success'):
    import api.server as server
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', str(tmp_path / 'tasks.db'))
    monkeypatch.setattr(server, 'output_dir', tmp_path / 'output')
    monkeypatch.setattr(server, 'initialize_mysql_runtime', lambda: None)
    harness, recorder = build_native_findings_fixture(monkeypatch, mode=mode)
    service = ResearchExecutionService(harness=harness, project_root=tmp_path)
    outcomes = []
    async def execute(query, thread_id, **kwargs):
        outcome = await service.execute(query, thread_id, **kwargs)
        outcomes.append(outcome)
        return outcome
    monkeypatch.setattr(server, 'run_deep_agent', execute)
    with TestClient(app) as client:
        creation = client.post('/api/runs', json={'query': 'question', 'profile_id': PROFILE}, headers=AUTH_HEADERS)
        assert creation.status_code == 200, creation.text
        run_id = creation.json()['run_id']
        status = client.portal.call(wait_terminal, run_id)
        findings = client.get(f'/api/runs/{run_id}/findings', headers=AUTH_HEADERS)
        result = client.get(f'/api/runs/{run_id}/result', headers=AUTH_HEADERS)
        status_response = client.get(f'/api/runs/{run_id}', headers=AUTH_HEADERS)
    return status, findings, result, status_response, outcomes[0], recorder


def test_native_harness_dispatch_fenced_delivery_and_http_readers(tmp_path, monkeypatch):
    status, findings, result, status_response, outcome, recorder = execute_native_http(tmp_path, monkeypatch)
    assert status['execution_status'] == 'completed'
    assert status['delivery_status'] == 'ready'
    assert findings.status_code == result.status_code == 200
    assert outcome.findings_candidate is not None
    assert len(outcome.evidence_entries) == 1
    assert recorder['search_calls'][0] == 'native fixed source'
    assert recorder['source_tool_status'] == 'success'
    assert recorder['tool_calls'][:3] == ['task', 'internet_search', 'write_file']
    assert 'dra.research-findings-candidate.v1' in recorder['envelope']
    assert 'questions' in recorder['envelope']
    reference = findings.json()['report']['findings'][0]['references'][0]
    assert reference['snippet'][reference['excerpt_start']:reference['excerpt_end']] == '🧪 durable finding'
    assert reference['evidence_id'].startswith(f"ev_{status['run_id']}_")
    assert status_response.json()['findings_outcome']['covered_question_count'] == 1
    assert status_response.json()['evidence'][0]['verification_status'] == 'unverified'
    assert result.json()['artifact']['kind'] == 'research_findings_markdown'


@pytest.mark.parametrize('mode,issue', [('file_failure', 'candidate_missing'), ('missing', 'candidate_missing'), ('source_failure', 'source_not_observed'), ('invalid', 'candidate_invalid_json'), ('empty', 'empty_research_output')])
def test_native_negative_controls_complete_with_blocked_delivery(tmp_path, monkeypatch, mode, issue):
    status, findings, result, status_response, outcome, recorder = execute_native_http(tmp_path, monkeypatch, mode=mode)
    assert status['execution_status'] == 'completed'
    assert status['delivery_status'] == 'blocked'
    assert findings.status_code == result.status_code == 409
    assert issue in status_response.json()['findings_issues']
    assert [row['artifact_id'] for row in status['artifacts']] == ['research-findings-diagnostics.json']
    if mode == 'source_failure':
        assert recorder['source_tool_status'] == 'error'
        assert outcome.evidence_entries == []
    if mode == 'missing':
        assert recorder['calls'].count('coordinator') == 3  # task, final, one bounded correction
    if mode == 'file_failure':
        assert outcome.findings_candidate is None
        assert any('denied' in str(message).lower() for message in recorder['file_tool_messages'])


@pytest.mark.parametrize('scope', [{'questions': []}, {'questions': [{'question_id': 'q1', 'text': 'x'}, {'question_id': 'q1', 'text': 'y'}]}, {'questions': [{'question_id': 'q1', 'text': 'private ' * 1000}]}])
def test_scope_rejected_before_dispatch_and_key_creation(tmp_path, monkeypatch, scope):
    import api.server as server
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', str(tmp_path / 'tasks.db'))
    class NoDispatch:
        async def dispatch_run(self, run_id):
            raise AssertionError('invalid scope must not dispatch')
    monkeypatch.setattr(app.state, 'run_dispatch_worker', NoDispatch(), raising=False)
    response = TestClient(app).post('/api/runs', json={'query': 'query', 'profile_id': PROFILE, 'scope': scope}, headers={**AUTH_HEADERS, 'Idempotency-Key': 'invalid-scope-key-12345'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_research_scope'
    assert 'private ' not in response.text
