import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from agent.research import EvidenceEntry
from agent.research_findings_contracts import validate_research_findings_scope
from api.research_findings import build_research_findings_artifacts
from api.run_repository import create_run, finalize_run_transaction
from api.server import app

PROFILE = 'generic-evidence-report'
AUTH_HEADERS = {'X-API-Key': 'test-integration-key'}
pytestmark = pytest.mark.usefixtures('authenticated_runtime_access')


def candidate():
    return {'schema_version': 'dra.research-findings-candidate.v1', 'findings': [{'question_id': 'q1', 'statement': 'Candidate claim', 'references': [{'source_url': 'https://example.com/source', 'excerpt': 'observed'}]}], 'dispositions': [{'question_id': 'q1', 'status': 'candidate_findings'}]}


def seed(tmp_path, monkeypatch, content=None):
    db = str(tmp_path / 'tasks.db')
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', db)
    scope = validate_research_findings_scope({}, query='question')
    created = create_run(thread_id='thread-findings', query='question', profile_id=PROFILE, profile_version='1', scope=scope.model_dump(mode='json'), db_path=db)
    entries = [EvidenceEntry(thread_id='thread-findings', query_text='question', subagent_name='network_search', tool_name='internet_search', source_url='https://example.com/source', snippet='The observed material.')]
    result = build_research_findings_artifacts(run_id=created['run_id'], scope=scope, candidate_content=json.dumps(candidate()) if content is None else content, evidence_entries=entries)
    assert finalize_run_transaction(run_id=created['run_id'], segment_id=created['segment_id'], expected_state_version=0, allowed_previous_statuses={'pending'}, execution_status='completed', delivery_status=result.delivery_status, evidence_entries=result.evidence_entries, artifacts=result.artifacts, db_path=db)
    return db, created, result


def test_findings_and_markdown_read_persisted_same_run_package(tmp_path, monkeypatch):
    _, created, built = seed(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get(f"/api/runs/{created['run_id']}/findings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()['report'] == built.report.model_dump(mode='json')
    assert response.json()['artifact'] == built.artifacts[0]
    result = client.get(f"/api/runs/{created['run_id']}/result", headers=AUTH_HEADERS)
    assert result.status_code == 200
    assert result.json()['artifact'] == built.artifacts[1]
    status = client.get(f"/api/runs/{created['run_id']}", headers=AUTH_HEADERS).json()
    assert status['findings_issues'] == []
    assert status['findings_outcome'] == {'requested_question_count': 1, 'covered_question_count': 1, 'unresolved_question_count': 0, 'reference_binding_failure_count': 0}


@pytest.mark.parametrize('tamper', ['hash', 'foreign_ref', 'offset', 'markdown', 'duplicate_key', 'nonfinite', 'missing_json', 'unsafe_source', 'scope', 'version', 'wrong_kind', 'oversized_json', 'oversized_markdown', 'surrogate', 'deep_scope'])
def test_independent_reader_rejects_tampering_even_when_rehashed(tmp_path, monkeypatch, tamper):
    db, created, built = seed(tmp_path, monkeypatch)
    artifact_id = 'research-findings.json'
    content = built.artifacts[0]['content']
    raw = json.loads(content)
    if tamper == 'foreign_ref':
        raw['findings'][0]['references'][0]['evidence_id'] = 'ev_other_run_fake'
    elif tamper == 'offset':
        raw['findings'][0]['references'][0]['excerpt_start'] += 1
    elif tamper == 'unsafe_source':
        raw['findings'][0]['references'][0]['source_url'] = 'javascript:alert(1)'
    elif tamper == 'markdown':
        artifact_id, content = 'research-report.md', '# Arbitrary rehashed markdown'
    elif tamper == 'duplicate_key':
        content = content[:-1] + ',"run_id":"other"}'
    elif tamper == 'nonfinite':
        content = content[:-1] + ',"arbitrary":NaN}'
    if tamper == 'oversized_json':
        content += ' ' * (1024 * 1024)
    elif tamper == 'oversized_markdown':
        artifact_id, content = 'research-report.md', 'x' * (1024 * 1024 + 1)
    elif tamper == 'surrogate':
        content = content.replace('Candidate claim', r'Candidate \ud800')
    if tamper in {'foreign_ref', 'offset', 'unsafe_source'}:
        content = json.dumps(raw)
    with sqlite3.connect(db) as conn:
        if tamper == 'missing_json':
            conn.execute('DELETE FROM run_artifacts_v2 WHERE run_id=? AND artifact_id=?', (created['run_id'], artifact_id))
        elif tamper == 'scope':
            conn.execute('UPDATE research_runs_v2 SET scope_json=? WHERE run_id=?', ('{"questions":[{"question_id":"q1","text":"changed"}]}', created['run_id']))
        elif tamper == 'deep_scope':
            conn.execute('UPDATE research_runs_v2 SET scope_json=? WHERE run_id=?', ('[' * 10000 + '0' + ']' * 10000, created['run_id']))
        elif tamper == 'version':
            conn.execute('UPDATE research_runs_v2 SET profile_version=? WHERE run_id=?', ('2', created['run_id']))
        elif tamper == 'wrong_kind':
            # Wrong artifact kind cannot satisfy canonical delivery.
            conn.execute('UPDATE run_artifacts_v2 SET kind=? WHERE run_id=? AND artifact_id=?', ('research_report_markdown', created['run_id'], artifact_id))
        else:
            digest = '0' * 64 if tamper == 'hash' else hashlib.sha256(content.encode()).hexdigest()
            conn.execute('UPDATE run_artifacts_v2 SET content=?, content_hash=? WHERE run_id=? AND artifact_id=?', (content, digest, created['run_id'], artifact_id))
    client = TestClient(app)
    for route in ('findings', 'result'):
        response = client.get(f"/api/runs/{created['run_id']}/{route}", headers=AUTH_HEADERS)
        assert response.status_code == 409
        assert response.json()['code'] == 'run_result_unavailable'


def test_blocked_diagnostics_are_bounded_and_corrupt_diagnostics_fail_closed(tmp_path, monkeypatch):
    db, created, _ = seed(tmp_path, monkeypatch, content='{')
    client = TestClient(app)
    url = f"/api/runs/{created['run_id']}"
    assert client.get(url, headers=AUTH_HEADERS).json()['findings_issues'] == ['candidate_invalid_json']
    assert client.get(url + '/findings', headers=AUTH_HEADERS).json()['code'] == 'run_delivery_blocked'
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE run_artifacts_v2 SET content=? WHERE run_id=?", ('private exception /Users/private', created['run_id']))
    response = client.get(url, headers=AUTH_HEADERS)
    assert 'findings_issues' not in response.json()
    assert 'private exception' not in response.text


def test_missing_findings_run_matches_existing_error(tmp_path, monkeypatch):
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', str(tmp_path / 'tasks.db'))
    response = TestClient(app).get('/api/runs/run_missing/findings', headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert response.json()['code'] == 'run_not_found'


def test_stale_finalizer_cannot_replace_delivered_findings(tmp_path, monkeypatch):
    db, created, built = seed(tmp_path, monkeypatch)
    assert not finalize_run_transaction(run_id=created['run_id'], segment_id=created['segment_id'], expected_state_version=0, allowed_previous_statuses={'pending'}, execution_status='completed', delivery_status='blocked', evidence_entries=[], artifacts=[], db_path=db)
    response = TestClient(app).get(f"/api/runs/{created['run_id']}/findings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()['artifact']['content_hash'] == built.artifacts[0]['content_hash']


def test_keyed_replay_normalizes_default_question_before_creation(tmp_path, monkeypatch):
    from api.run_repository import get_run
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', str(tmp_path / 'tasks.db'))
    class RecordedDispatch:
        calls = []
        async def dispatch_run(self, run_id):
            self.calls.append(run_id)
            return False
        def wake(self):
            pass
    worker = RecordedDispatch()
    monkeypatch.setattr(app.state, 'run_dispatch_worker', worker, raising=False)
    client = TestClient(app)
    headers = {**AUTH_HEADERS, 'Idempotency-Key': 'findings-keyed-default-12345'}
    first = client.post('/api/runs', json={'query': 'question', 'profile_id': PROFILE}, headers=headers)
    second = client.post('/api/runs', json={'query': 'question', 'profile_id': PROFILE, 'scope': {'questions': [{'question_id': 'q1', 'text': 'question'}]}}, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()['run_id'] == second.json()['run_id']
    assert second.json()['idempotent_replay'] is True
    assert get_run(run_id=first.json()['run_id'])['scope'] == {'questions': [{'question_id': 'q1', 'text': 'question'}]}
    conflict = client.post('/api/runs', json={'query': 'question', 'profile_id': PROFILE, 'scope': {'questions': [{'question_id': 'q1', 'text': 'changed'}]}}, headers=headers)
    assert conflict.status_code == 409


def test_pending_and_wrong_profile_runs_have_no_findings_delivery(tmp_path, monkeypatch):
    db = str(tmp_path / 'tasks.db')
    monkeypatch.setenv('DECISION_RESEARCH_AGENT_DB_PATH', db)
    created = create_run(thread_id='legacy', query='q', db_path=db)
    client = TestClient(app)
    url = f"/api/runs/{created['run_id']}/findings"
    assert client.get(url, headers=AUTH_HEADERS).json()['code'] == 'run_not_terminal'
    text = '# legacy fallback'
    artifact = {'artifact_id': 'research-report.md', 'kind': 'research_report_fallback_markdown', 'media_type': 'text/markdown', 'content': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest()}
    assert finalize_run_transaction(run_id=created['run_id'], segment_id=created['segment_id'], expected_state_version=0, allowed_previous_statuses={'pending'}, execution_status='completed', delivery_status='ready', evidence_entries=[], artifacts=[artifact], db_path=db)
    assert client.get(url, headers=AUTH_HEADERS).json()['code'] == 'run_result_unavailable'
    result = client.get(f"/api/runs/{created['run_id']}/result", headers=AUTH_HEADERS)
    assert result.status_code == 200
    assert result.json()['artifact']['content'] == text
    assert 'findings_issues' not in client.get(f"/api/runs/{created['run_id']}", headers=AUTH_HEADERS).json()


@pytest.mark.parametrize('execution,delivery,code', [('failed', 'failed', 'run_failed'), ('completed', 'review_required', 'run_review_required'), ('completed', 'pending', 'run_result_unavailable')])
def test_findings_reader_matches_shared_terminal_errors(monkeypatch, execution, delivery, code):
    import api.research_findings_service as service
    from api.run_result_service import RunResultUnavailable
    monkeypatch.setattr(service, 'get_run_delivery_snapshot', lambda **kwargs: {'execution_status': execution, 'delivery_status': delivery})
    with pytest.raises(RunResultUnavailable) as error:
        service.resolve_run_findings(run_id='run-test')
    assert error.value.code == code


def test_current_publication_pointer_cannot_select_stale_artifacts(tmp_path, monkeypatch):
    from api.run_repository import get_run_delivery_snapshot
    import api.research_findings_service as service
    from api.run_result_service import RunResultUnavailable
    db, created, _ = seed(tmp_path, monkeypatch)
    snapshot = get_run_delivery_snapshot(run_id=created['run_id'], db_path=db)
    snapshot['current_artifact_ids'] = ('other-revision.json', 'other-revision.md')
    monkeypatch.setattr(service, 'get_run_delivery_snapshot', lambda **kwargs: snapshot)
    with pytest.raises(RunResultUnavailable):
        service.resolve_run_findings(run_id=created['run_id'])
