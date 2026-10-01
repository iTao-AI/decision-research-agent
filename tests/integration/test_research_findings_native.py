"""Provider-free proof using installed generic harness and HTTP delivery consumers."""
import asyncio
import json
from typing import Any
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import ToolException
from pydantic import Field

from agent.deepagents_harness import build_generic_harness
from api.research_execution_service import ResearchExecutionService
from api.server import app

PROFILE = 'generic-evidence-report'
SOURCE_URL = 'https://example.com/native-findings-source'
SNIPPET = 'Observed native source: 🧪 durable finding material.'
AUTH_HEADERS = {'X-API-Key': 'test-integration-key'}
pytestmark = pytest.mark.usefixtures('authenticated_runtime_access')


def native_candidate():
    return {'schema_version': 'dra.research-findings-candidate.v1', 'findings': [{'question_id': 'q1', 'statement': 'Synthetic source-bound candidate.', 'references': [{'source_url': SOURCE_URL, 'excerpt': '🧪 durable finding'}]}], 'dispositions': [{'question_id': 'q1', 'status': 'candidate_findings'}], 'limitations': ['Synthetic fixture; no truth or entailment evaluation.']}


class NativeFindingsModel(BaseChatModel):
    """Deterministic tool-calling fixture; copies retain one observable recorder."""
    profile: dict[str, Any] | None = {'max_input_tokens': 32768}
    mode: str = 'success'
    recorder: dict = Field(default_factory=dict)
    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self):
        return 'native-findings-fixture'

    def bind_tools(self, tools: Sequence, **kwargs):
        return self.model_copy(update={'bound_tool_names': tuple(tool.get('name', '') if isinstance(tool, dict) else tool.name for tool in tools)})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        researcher = 'internet_search' in self.bound_tool_names
        role = 'researcher' if researcher else 'coordinator'
        self.recorder.setdefault('calls', []).append(role)
        tool_messages = [item for item in messages if isinstance(item, ToolMessage)]
        if researcher and not tool_messages:
            tool_name, args = 'internet_search', {'query': 'native fixed source'}
        elif researcher:
            self.recorder['source_tool_status'] = tool_messages[-1].status
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Source observed; use exact frozen excerpt.'))])
        elif not any(item.name == 'task' for item in tool_messages):
            self.recorder['envelope'] = next(item.content for item in messages if isinstance(item, HumanMessage))
            tool_name, args = 'task', {'description': 'Observe one fixed public fixture source.', 'subagent_type': 'network_search'}
        elif not any(item.name == 'write_file' for item in tool_messages) and self.mode != 'missing':
            content = json.dumps(native_candidate(), ensure_ascii=False)
            if self.mode == 'invalid':
                content = '{'
            elif self.mode == 'empty':
                content = json.dumps({'schema_version': 'dra.research-findings-candidate.v1', 'findings': [], 'dispositions': [{'question_id': 'q1', 'status': 'unresolved', 'reason': 'No candidate found.'}]})
            args = {'file_path': '/skills/forbidden.json' if self.mode == 'file_failure' else '/workspace/research-findings.json', 'content': content}
            tool_name = 'write_file'
        else:
            self.recorder['file_tool_messages'] = [item.content for item in tool_messages if item.name == 'write_file']
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Finished fixture research.'))])
        self.recorder.setdefault('tool_calls', []).append(tool_name)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[{'name': tool_name, 'args': args, 'id': f'call-{role}-{len(self.recorder["calls"])}', 'type': 'tool_call'}]))])


def build_native_findings_fixture(monkeypatch, *, mode='success'):
    """Reusable test helper: actual builder/search/cache/stream, no remote provider."""
    import tools.tavily_tools as tavily
    recorder = {}
    def search(query, **kwargs):
        recorder.setdefault('search_calls', []).append(query)
        payload = json.dumps({'results': [{'url': SOURCE_URL, 'content': SNIPPET}]}, ensure_ascii=False)
        if mode == 'source_failure':
            raise ToolException(payload)
        return payload
    monkeypatch.setattr(tavily, '_internet_search_impl', search)
    if mode == 'source_failure':
        monkeypatch.setattr(tavily.internet_search, 'handle_tool_error', True)
    model = NativeFindingsModel(mode=mode, recorder=recorder)
    recorder = model.recorder
    harness = build_generic_harness(model=model)
    return harness, recorder


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
