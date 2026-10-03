"""Independent read-only validation of application-owned findings artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from agent.research_findings_contracts import ResearchFindingsDiagnostics, ResearchFindingsReport, ResearchFindingsScope
from api.research_findings import (
    MAX_FINDINGS_ARTIFACT_BYTES, RESEARCH_FINDINGS_PROFILE_ID, RESEARCH_FINDINGS_PROFILE_VERSION,
    render_research_findings_markdown, validate_research_findings_report,
)
from api.run_repository import get_run_delivery_snapshot, RunDeliverySnapshotConflict
from api.run_result_service import _require_ready_delivery, _unavailable


@dataclass(frozen=True)
class ResolvedRunFindings:
    run_id: str
    execution_status: str
    delivery_status: str
    artifact: dict[str, str]
    report: ResearchFindingsReport


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('invalid JSON numeric constant')


def _strict_json(content: str):
    raw = json.loads(content, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    json.dumps(raw, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return raw


def _valid_bytes(artifact, *, artifact_id, kind, media_type, max_bytes=MAX_FINDINGS_ARTIFACT_BYTES):
    if not isinstance(artifact, dict):
        return False
    if (artifact.get('artifact_id') != artifact_id or artifact.get('kind') != kind
            or artifact.get('media_type') != media_type):
        return False
    content = artifact.get('content')
    if type(content) is not str or not content.strip():
        return False
    try:
        encoded = content.encode('utf-8')
        return len(encoded) <= max_bytes and hashlib.sha256(encoded).hexdigest() == artifact.get('content_hash')
    except UnicodeError:
        return False


def _public_artifact(row):
    return {key: row[key] for key in ('artifact_id', 'kind', 'media_type', 'content', 'content_hash')}


def validate_findings_snapshot(run: dict[str, Any]):
    """Rebind frozen rows and compare deterministic Markdown, even after rehashing."""
    try:
        if (run['profile_id'] != RESEARCH_FINDINGS_PROFILE_ID or run.get('profile_version') != RESEARCH_FINDINGS_PROFILE_VERSION
                or run['execution_status'] != 'completed' or run['delivery_status'] != 'ready'):
            raise ValueError('invalid delivery authority')
        rows = {row['artifact_id']: row for row in run['artifacts']}
        ids = ('research-findings.json', 'research-report.md')
        if run['current_artifact_ids'] and any(artifact_id not in run['current_artifact_ids'] for artifact_id in ids):
            raise ValueError('stale artifact')
        json_row, markdown = (rows.get(artifact_id) for artifact_id in ids)
        if not _valid_bytes(json_row, artifact_id=ids[0], kind='research_findings_json', media_type='application/json'):
            raise ValueError('invalid JSON artifact')
        if not _valid_bytes(markdown, artifact_id=ids[1], kind='research_findings_markdown', media_type='text/markdown'):
            raise ValueError('invalid Markdown artifact')
        report = ResearchFindingsReport.model_validate(_strict_json(json_row['content']))
        scope = ResearchFindingsScope.model_validate(run['scope'])
        if not validate_research_findings_report(report, run_id=run['run_id'], scope=scope, evidence_rows=run['evidence_rows']):
            raise ValueError('invalid Evidence binding')
        if markdown['content'] != render_research_findings_markdown(report):
            raise ValueError('noncanonical Markdown')
        return report, _public_artifact(json_row), _public_artifact(markdown)
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError) as exc:
        raise _unavailable() from exc


def project_findings_diagnostics(*, run_id: str, profile_version: str, delivery_status: str, scope: dict, artifact):
    """Closed, bounded status projection; corruption cannot leak model/private text."""
    try:
        if profile_version != RESEARCH_FINDINGS_PROFILE_VERSION or delivery_status not in {'ready', 'blocked'}:
            return {}
        if not _valid_bytes(artifact, artifact_id='research-findings-diagnostics.json', kind='research_findings_diagnostics_json', media_type='application/json', max_bytes=4096):
            return {}
        diagnostics = ResearchFindingsDiagnostics.model_validate(_strict_json(artifact['content']))
        accepted = ResearchFindingsScope.model_validate(scope)
        if (diagnostics.run_id != run_id or diagnostics.requested_question_count != len(accepted.questions)
                or diagnostics.covered_question_count + diagnostics.unresolved_question_count > len(accepted.questions)
                or (delivery_status == 'ready' and (diagnostics.issue_codes or diagnostics.covered_question_count < 1))
                or (delivery_status == 'blocked' and not diagnostics.issue_codes)):
            return {}
        values = diagnostics.model_dump(mode='json')
        return {'findings_issues': values['issue_codes'], 'findings_outcome': {key: values[key] for key in ('requested_question_count', 'covered_question_count', 'unresolved_question_count', 'reference_binding_failure_count')}}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {}


def resolve_run_findings(*, run_id: str, db_path: str | None = None) -> ResolvedRunFindings:
    try:
        run = get_run_delivery_snapshot(run_id=run_id, db_path=db_path)
    except RunDeliverySnapshotConflict as exc:
        raise _unavailable() from exc
    _require_ready_delivery(run, run_id=run_id)
    report, artifact, _ = validate_findings_snapshot(run)
    return ResolvedRunFindings(run_id, run['execution_status'], run['delivery_status'], artifact, report)
