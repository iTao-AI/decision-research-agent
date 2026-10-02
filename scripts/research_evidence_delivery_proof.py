"""Bounded provider-free native proof; runtime imports are lazy for --help."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/research-evidence-delivery'
STEM = 'research-evidence-delivery-v1'

class ProofError(RuntimeError):
    """Fixed public-safe proof error."""

def deny(*args, **kwargs):
    raise ProofError('research_evidence_proof_external_path_denied')

def loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False

def declarations():
    fixtures = json.loads((FIXTURES / 'cases.json').read_text(encoding='utf-8'))
    expected = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))['cases']
    required = {'complete', 'partial', 'contradictory', 'insufficient-evidence'}
    cases = fixtures['cases']
    if fixtures.get('synthetic') is not True or len(cases) != 4 or {c['case_id'] for c in cases} != required or set(expected) != required:
        raise ProofError('research_evidence_proof_dataset_invalid')
    return cases, expected

@contextmanager
def guarded_runtime(directory, origin=None):
    """Deny external transports before server import; never fake terminal runs.

    Only model/source responses are fixtures. Real writer/dispatch/finalizer and
    HTTP readers remain intact. A fallback attempt invalidates the receipt.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from pytest import MonkeyPatch
    with MonkeyPatch.context() as patch:
        for key, value in {
            'PYTHON_DOTENV_DISABLED':'1', 'LANGSMITH_TRACING':'false',
            'LANGCHAIN_TRACING_V2':'false', 'LANGCHAIN_TRACING':'false',
            'DECISION_RESEARCH_AGENT_DB_PATH':str(directory / 'runs.db'),
            'DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN':origin or '',
            'DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL':'false',
            'DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION':'false',
        }.items():
            patch.setenv(key, value)
        for key in ('API_SECRET','OPENAI_API_KEY','DEEPSEEK_API_KEY','LLM_API_KEY','TAVILY_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY','RAGFLOW_API_KEY','MYSQL_PASSWORD'):
            patch.delenv(key, raising=False)
        attempted = []
        def deny_external(*args, **kwargs):
            attempted.append('external_provider_or_source_path')
            deny()
        connect, connect_ex, resolve, sendto = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.socket.sendto
        def ensure_local(address):
            if not isinstance(address, tuple) or not loopback(address[0]):
                attempted.append('external_transport')
                deny()
        def local_connect(sock, address):
            if sock.family != socket.AF_UNIX:
                ensure_local(address)
            return connect(sock, address)
        def local_connect_ex(sock, address):
            if sock.family != socket.AF_UNIX:
                ensure_local(address)
            return connect_ex(sock, address)
        def local_resolve(host, *args, **kwargs):
            if host is not None and not loopback(host):
                attempted.append('external_resolution')
                deny()
            return resolve(host, *args, **kwargs)
        def local_sendto(sock, data, *args):
            if sock.family != socket.AF_UNIX:
                ensure_local(args[-1])
            return sendto(sock, data, *args)
        patch.setattr(socket.socket, 'connect', local_connect)
        patch.setattr(socket.socket, 'connect_ex', local_connect_ex)
        patch.setattr(socket.socket, 'sendto', local_sendto)
        patch.setattr(socket, 'getaddrinfo', local_resolve)
        # main_agent normally initializes provider models on import.
        stub = ModuleType('agent.main_agent')
        stub.run_deep_agent = deny_external
        patch.setitem(sys.modules, 'agent.main_agent', stub)
        import agent
        patch.setattr(agent, 'main_agent', stub, raising=False)
        llm = ModuleType('agent.llm')
        llm.create_llm_model = llm._create_leaf_model = deny_external
        llm.model = None
        patch.setitem(sys.modules, 'agent.llm', llm)
        patch.setattr(agent, 'llm', llm, raising=False)
        import langsmith
        patch.setattr(langsmith, 'Client', deny_external)
        import tools.tavily_tools as tavily
        import tools.mysql_tools as mysql
        import tools.ragflow_tools as ragflow
        patch.setattr(tavily, '_tavily_search', deny_external)
        patch.setattr(mysql, 'initialize_mysql_runtime', lambda: None)
        for tool in (mysql.list_sql_tables, mysql.get_table_data, mysql.execute_sql_query, ragflow.get_assistant_list, ragflow.create_ask_delete):
            patch.setattr(tool, 'func', deny_external)
        import api.server as server
        from api.runtime_access import load_runtime_access_policy
        from api.cors_config import load_cors_configuration
        from fastapi.middleware.cors import CORSMiddleware
        patch.setattr(server, 'initialize_mysql_runtime', lambda: None)
        patch.setattr(server, 'output_dir', directory / 'output')
        patch.setattr(server.app.state, 'runtime_access_policy', load_runtime_access_policy({}))
        cors = load_cors_configuration(access_policy=server.app.state.runtime_access_policy)
        patch.setattr(server.app.state, 'cors_configuration', cors)
        for middleware in server.app.user_middleware:
            if middleware.cls is CORSMiddleware:
                patch.setitem(middleware.kwargs, 'allow_origins', cors.allowed_origins)
        patch.setattr(server.app, 'middleware_stack', None)
        yield server, patch, attempted

async def wait_terminal(run_id):
    from api.run_repository import get_run
    async with asyncio.timeout(10):
        while True:
            status = await asyncio.to_thread(get_run, run_id=run_id)
            if status and status['execution_status'] in {'completed','failed'}:
                return status
            await asyncio.sleep(.02)

def install_execution(server, patch, directory, cases):
    from api.research_execution_service import ResearchExecutionService
    from scripts.research_evidence_native_fixture import build_native_findings_fixture
    import api.run_repository as repository
    outcomes, recorders = {}, {}
    by_query = {case['query']: case for case in cases}
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    async def fixture_only(request, call_next):
        if request.method == 'POST' and request.url.path == '/api/runs':
            body = await request.body()
            try:
                payload = json.loads(body) if len(body) <= 16384 else None
            except (ValueError, UnicodeError):
                payload = None
            if (not isinstance(payload, dict) or payload.get('query') not in by_query
                    or payload.get('profile_id') != 'generic-evidence-report'):
                return JSONResponse({'code':'research_evidence_proof_fixture_only'}, status_code=422)
        return await call_next(request)
    patch.setattr(server.app, 'user_middleware', [
        Middleware(BaseHTTPMiddleware, dispatch=fixture_only), *server.app.user_middleware])
    patch.setattr(server.app, 'middleware_stack', None)
    execution_lock = asyncio.Lock()
    counter = iter(range(1, 1001))
    # Stable IDs at REAL SQL creation, never rewrite report bytes or hashes.
    patch.setattr(repository, 'uuid', SimpleNamespace(uuid4=lambda: uuid.uuid5(uuid.NAMESPACE_URL, f'dra:research-evidence-proof:v1:{next(counter)}')))
    async def execute(query, thread_id, **kwargs):
        case = by_query.get(query)
        if case is None or kwargs.get('profile_id') != 'generic-evidence-report':
            raise ProofError('research_evidence_proof_fixture_only')
        # Source function replacement is fixture-global; serialize local runs so
        # concurrent UI requests cannot observe another case's source response.
        async with execution_lock:
            harness, recorder = build_native_findings_fixture(patch, candidate=case['candidate'], sources=case['sources'])
            service = ResearchExecutionService(harness=harness, project_root=directory)
            outcome = await service.execute(query, thread_id, **kwargs)
            outcomes[kwargs['run_id']], recorders[kwargs['run_id']] = outcome, recorder
            return outcome
    patch.setattr(server, 'run_deep_agent', execute)
    return outcomes, recorders

def observe(client, case, expected, outcomes, recorders, attempted):
    creation = client.post('/api/runs', json={'query':case['query'],'thread_id':f"proof-{case['case_id']}",'profile_id':'generic-evidence-report','scope':{'questions':case['questions']}})
    if creation.status_code != 200:
        raise ProofError('research_evidence_proof_creation_failed')
    run_id = creation.json()['run_id']
    client.portal.call(wait_terminal, run_id)
    status_response = client.get(f'/api/runs/{run_id}')
    findings_response = client.get(f'/api/runs/{run_id}/findings')
    markdown_response = client.get(f'/api/runs/{run_id}/result')
    if status_response.status_code != 200:
        raise ProofError('research_evidence_proof_status_unavailable')
    status = status_response.json()
    diagnostics = status.get('findings_outcome') or {}
    report = findings_response.json().get('report', {}) if findings_response.status_code == 200 else {}
    refs = [ref for finding in report.get('findings',[]) for ref in finding['references']]
    observed = {'execution_status':status['execution_status'],'delivery_status':status['delivery_status'],
        **{key:diagnostics.get(key) for key in ('requested_question_count','covered_question_count','unresolved_question_count','reference_binding_failure_count')},
        'bound_reference_count':len(refs),'reported_contradiction_count':len(report.get('reported_contradictions',[])),
        'evidence_count':len(status['evidence']),'issue_codes':status.get('findings_issues',[]),
        'findings_http_status':findings_response.status_code,'markdown_http_status':markdown_response.status_code}
    artifacts = []
    for response in (findings_response, markdown_response):
        if response.status_code == 200:
            payload = response.json()
            digest = hashlib.sha256(payload['artifact']['content'].encode('utf-8')).hexdigest()
            artifacts.append({'artifact_id':payload['artifact']['artifact_id'],'sha256':payload['artifact']['content_hash'],'own_byte_hash_validated':digest == payload['artifact']['content_hash']})
    outcome, recorder = outcomes[run_id], recorders[run_id]
    rows = {row['evidence_id']:row for row in status['evidence']}
    exact = all(ref['snippet'][ref['excerpt_start']:ref['excerpt_end']] == ref['excerpt'] and ref['snippet'].count(ref['excerpt']) == 1 for ref in refs)
    bound = all(ref['evidence_id'] in rows and all(ref[key] == rows[ref['evidence_id']][key]
        for key in ('snippet', 'source_url', 'source_identity', 'evidence_fingerprint')) for ref in refs)
    checkpoints = {
        'api_creation':creation.status_code == 200,
        'installed_graph_named_source_tool':recorder.get('source_tool_status') == 'success' and recorder.get('search_calls') == ['native fixed source'],
        'native_write_file':'write_file' in recorder.get('tool_calls',[]) and bool(recorder.get('file_tool_messages')),
        'actual_stream_candidate_capture':outcome.findings_candidate is not None,
        'application_execution_evidence':len(outcome.evidence_entries) == observed['evidence_count'],
        'fenced_database_terminal':status['execution_status'] == 'completed' and status['delivery_status'] == expected['delivery_status'],
        'http_status_reader':status_response.status_code == 200,
        'canonical_json_projection_agrees_or_delivery_blocked':
            json.loads(findings_response.json()['artifact']['content']) == report if findings_response.status_code == 200 else status['delivery_status'] == 'blocked',
        'http_findings_and_markdown_readers':findings_response.status_code == expected['findings_http_status'] and markdown_response.status_code == expected['markdown_http_status'],
        'returned_artifact_hashes_match_or_delivery_blocked':all(row['own_byte_hash_validated'] for row in artifacts) and (bool(artifacts) or status['delivery_status'] == 'blocked'),
        'returned_references_match_frozen_rows_or_no_findings':exact and bound, 'no_external_transport_attempt':not attempted}
    def error_code(response):
        return response.json().get('code') if response.status_code != 200 else None
    return {'case_id':case['case_id'],'query':case['query'],'run_id':run_id,'expected':expected,'observed':observed,
        'passed':observed == expected and all(checkpoints.values()),'checkpoints':checkpoints,
        'runtime':{'model_calls':len(recorder['calls']),'model_roles':recorder['calls'],'tool_calls':recorder['tool_calls'],'source_tool_status':recorder['source_tool_status']},
        'http_reader':{'artifacts':artifacts,'evidence_verification_states':sorted({row['verification_status'] for row in status['evidence']}),
            'findings_error_code':error_code(findings_response),'markdown_error_code':error_code(markdown_response)}}

def make_report(observations):
    return {'schema':'dra.research-evidence-delivery-proof.v1','synthetic':True,
        'producer_scope':'installed graph + deterministic model + declared named source-tool fixture',
        'consumer_scope':'persisted HTTP status, findings JSON and Markdown result readers',
        'fixture_file':'tests/fixtures/research-evidence-delivery/cases.json','expectations_file':'tests/fixtures/research-evidence-delivery/expected.json',
        'measurements':{key:'not_measured' for key in ('truth','entailment','provider_instruction_obedience','production_research_quality')},
        'cases':observations,'passed':all(row['passed'] for row in observations),
        'browser_receipt':'Separate parent-owned UI observation receipt; native check never writes it.'}

def seed(server, directory, patch, attempted):
    from fastapi.testclient import TestClient
    cases, expected = declarations()
    outcomes, recorders = install_execution(server, patch, directory, cases)
    with TestClient(server.app, base_url='http://127.0.0.1', client=('127.0.0.1',50000)) as client:
        return make_report([observe(client, case, expected[case['case_id']], outcomes, recorders, attempted) for case in cases])

def render_markdown(report):
    lines = ['# Research evidence delivery native proof v1','','Declared synthetic model/source fixtures traverse the installed graph, native file tools, stream capture,','application execution, fenced database finalization and persisted HTTP consumers.','','Truth, entailment, provider instruction obedience and production research quality are not measured.','Evidence remains unverified; contradictions remain model-reported.','','[Operations walkthrough](../operations/research-evidence-delivery.md) · [JSON receipt](research-evidence-delivery-v1.json)','','| Case | Execution / delivery | Requested / covered / unresolved | Binding failures | HTTP findings / Markdown | Independent expectation matched |','| --- | --- | --- | --- | --- | --- |']
    for case in report['cases']:
        o=case['observed']
        lines.append(f"| {case['case_id']} | {o['execution_status']} / {o['delivery_status']} | {o['requested_question_count']} / {o['covered_question_count']} / {o['unresolved_question_count']} | {o['reference_binding_failure_count']} | {o['findings_http_status']} / {o['markdown_http_status']} | {case['passed']} |")
    lines += ['','Expectations are declared independently in `tests/fixtures/research-evidence-delivery/expected.json`.','Each case records actual runtime calls/checkpoints, persisted run IDs and own-byte HTTP artifact hashes.','IDs originate deterministically at real run creation; artifact content and hashes are never post-normalized.','Insufficient evidence honestly completes with blocked delivery; no binding failure is invented.','','Native check writes only this Markdown and its JSON. Actual desktop/narrow/keyboard observations belong','in a separate parent-owned linked UI receipt; this native report does not claim browser observations.','']
    return '\n'.join(lines)

def write_report(report, output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/f'{STEM}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (output_dir/f'{STEM}.md').write_text(render_markdown(report),encoding='utf-8')

def serve(directory, origin, port, seconds):
    from urllib.parse import urlsplit
    parsed=urlsplit(origin)
    if parsed.scheme != 'http' or not loopback(parsed.hostname) or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'} or parsed.port is None:
        raise ProofError('research_evidence_proof_origin_invalid')
    with guarded_runtime(directory,origin) as (server,patch,attempted):
        report=seed(server,directory,patch,attempted)
        if not report['passed']:
            raise ProofError('research_evidence_proof_expectation_mismatch')
        print(json.dumps({'api':f'http://127.0.0.1:{port}','origin':origin,'expires_after_seconds':seconds,'cases':[{key:row[key] for key in ('case_id','query','run_id')} for row in report['cases']]}),flush=True)
        import uvicorn
        api=uvicorn.Server(uvicorn.Config(server.app,host='127.0.0.1',port=port,log_level='warning'))
        timer = threading.Timer(seconds, lambda: setattr(api, 'should_exit', True))
        timer.start()
        try:
            api.run()
        finally:
            timer.cancel()

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    check=sub.add_parser('check',help='run four native cases and independent HTTP observations')
    check.add_argument('--output-dir',type=Path,default=ROOT/'docs/evidence')
    serving=sub.add_parser('serve',help='temporary fixture-only loopback API')
    serving.add_argument('--origin',required=True,help='explicit frontend Origin, e.g. http://127.0.0.1:5175')
    serving.add_argument('--port',type=int,default=8876)
    serving.add_argument('--seconds',type=int,default=900)
    args=parser.parse_args(argv)
    if args.command == 'serve' and (not 1024 <= args.port <= 65535 or not 1 <= args.seconds <= 1800):
        parser.error('serve port must be 1024–65535 and seconds 1–1800')
    try:
        with tempfile.TemporaryDirectory(prefix='dra-research-evidence-proof-') as directory:
            if args.command == 'check':
                with guarded_runtime(Path(directory)) as (server,patch,attempted):
                    report=seed(server,Path(directory),patch,attempted)
                write_report(report,args.output_dir)
                print(json.dumps({'passed':report['passed'],'cases':len(report['cases'])}))
                return 0 if report['passed'] else 1
            serve(Path(directory),args.origin,args.port,args.seconds)
        return 0
    except KeyboardInterrupt:
        # Uvicorn propagates SIGINT after shutdown; all runtime contexts above
        # have unwound before reporting the expected operator stop.
        print('research_evidence_proof_interrupted', file=sys.stderr)
        return 130
    except Exception:
        print('research_evidence_proof_failed',file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
