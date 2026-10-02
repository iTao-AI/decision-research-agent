"""Synthetic native producer shared by tests and the local proof CLI.

This is test/proof infrastructure, never a production model or completed-run seeder.
The installed DeepAgents graph and native file/stream mechanics remain real.
"""
import json
from typing import Any
from collections.abc import Sequence
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import ToolException
from pydantic import Field
from agent.deepagents_harness import build_generic_harness

PROFILE = 'generic-evidence-report'
SOURCE_URL = 'https://example.com/native-findings-source'
SNIPPET = 'Observed native source: 🧪 durable finding material.'
AUTH_HEADERS = {'X-API-Key': 'test-integration-key'}


def native_candidate():
    return {'schema_version': 'dra.research-findings-candidate.v1', 'findings': [{'question_id': 'q1', 'statement': 'Synthetic source-bound candidate.', 'references': [{'source_url': SOURCE_URL, 'excerpt': '🧪 durable finding'}]}], 'dispositions': [{'question_id': 'q1', 'status': 'candidate_findings'}], 'limitations': ['Synthetic fixture; no truth or entailment evaluation.']}


class NativeFindingsModel(BaseChatModel):
    """Deterministic tool-calling fixture; copies retain one observable recorder."""
    profile: dict[str, Any] | None = {'max_input_tokens': 32768}
    mode: str = 'success'
    recorder: dict = Field(default_factory=dict)
    bound_tool_names: tuple[str, ...] = ()
    candidate_payload: dict | None = None

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
            content = json.dumps(self.candidate_payload if self.candidate_payload is not None else native_candidate(), ensure_ascii=False)
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


def build_native_findings_fixture(monkeypatch, *, mode='success', candidate=None, sources=None):
    """Reusable test helper: actual builder/search/cache/stream, no remote provider."""
    import tools.tavily_tools as tavily
    recorder = {}
    def search(query, **kwargs):
        recorder.setdefault('search_calls', []).append(query)
        payload = json.dumps({'results': sources if sources is not None else [{'url': SOURCE_URL, 'content': SNIPPET}]}, ensure_ascii=False)
        if mode == 'source_failure':
            raise ToolException(payload)
        return payload
    monkeypatch.setattr(tavily, '_internet_search_impl', search)
    if mode == 'source_failure':
        monkeypatch.setattr(tavily.internet_search, 'handle_tool_error', True)
    model = NativeFindingsModel(mode=mode, recorder=recorder, candidate_payload=candidate)
    recorder = model.recorder
    harness = build_generic_harness(model=model)
    return harness, recorder
