"""Controlled CLI composition tests; native HTTP acceptance is separate."""
import copy
import hashlib
import io
import json
import time

import pytest

from tools import decision_research_agent_tool as tool


def delivery():
    run_id = "run_fixture"
    url, snippet = "https://example.com/source", "A 🧪 observed material."
    fingerprint = hashlib.sha256(f"{url}\n{snippet}".encode()).hexdigest()
    evidence_id = f"ev_{run_id}_{fingerprint}"
    ref = {"evidence_id": evidence_id, "evidence_fingerprint": fingerprint,
           "source_url": url, "source_identity": url, "snippet": snippet,
           "excerpt": "observed", "excerpt_start": 4, "excerpt_end": 12}
    report = {"schema_version": "dra.research-findings.v1", "run_id": run_id,
              "profile_id": "generic-evidence-report", "profile_version": "1",
              "questions": [{"question_id": "q1", "text": "Question?"}],
              "findings": [{"finding_id": "f1", "question_id": "q1",
                            "statement": "Candidate", "references": [ref]}],
              "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
              "reported_contradictions": [], "limitations": []}
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    package = {"run_id": run_id, "execution_status": "completed", "delivery_status": "ready",
               "report": report, "artifact": {"artifact_id": "research-findings.json",
                   "kind": "research_findings_json", "media_type": "application/json",
                   "content": content, "content_hash": hashlib.sha256(content.encode()).hexdigest()}}
    status = {"run_id": run_id, "profile_id": "generic-evidence-report", "profile_version": "1",
              "scope": {"questions": copy.deepcopy(report["questions"])},
              "execution_status": "completed", "delivery_status": "ready",
              "review_status": "not_required", "review_decision": None,
              "evidence": [{**{key: ref[key] for key in ("evidence_id", "evidence_fingerprint",
                              "source_url", "source_identity", "snippet")},
                            "run_id": run_id, "citation_status": "cited", "verification_status": "unverified"}]}
    markdown = "# Stored report\n\n🧪 Exact bytes"
    result = {"run_id": run_id, "execution_status": "completed", "delivery_status": "ready",
              "artifact": {"artifact_id": "research-report.md", "kind": "research_findings_markdown",
                           "media_type": "text/markdown", "content": markdown,
                           "content_hash": hashlib.sha256(markdown.encode()).hexdigest()}}
    return package, status, result


def install_reads(monkeypatch, package, status, result):
    calls = []
    def read(path, *, config):
        calls.append(path)
        values = {"/api/runs/run_fixture/findings": package,
                  "/api/runs/run_fixture": status, "/api/runs/run_fixture/result": result}
        return copy.deepcopy(values[path])
    monkeypatch.setattr(tool, "_findings_get_json", read, raising=False)
    return calls


def test_json_retains_report_and_observed_verification_without_approval_upgrade(monkeypatch, capsys):
    package, status, result = delivery()
    status["review_status"] = "resolved"
    status["review_decision"] = {"run_id": "run_fixture", "action": "approve"}
    calls = install_reads(monkeypatch, package, status, result)
    assert tool.main(["findings", "--run-id", "run_fixture"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert {key: value[key] for key in package} == package
    assert value["evidence"] == status["evidence"]
    assert value["review_decision"]["action"] == "approve"
    assert value["evidence"][0]["verification_status"] == "unverified"
    assert calls == ["/api/runs/run_fixture/findings", "/api/runs/run_fixture"]


def test_markdown_emits_canonical_bytes_without_adding_a_newline(monkeypatch, capsys):
    package, status, result = delivery()
    calls = install_reads(monkeypatch, package, status, result)
    assert tool.main(["findings", "--run-id", "run_fixture", "--format", "markdown"]) == 0
    assert capsys.readouterr().out == "# Stored report\n\n🧪 Exact bytes"
    assert calls == ["/api/runs/run_fixture/findings", "/api/runs/run_fixture/result"]


@pytest.mark.parametrize("code,status", [("run_not_found", 404), ("run_not_terminal", 409),
    ("run_failed", 409), ("run_review_required", 409), ("run_delivery_blocked", 409),
    ("run_result_unavailable", 409), ("api_key_required", 401)])
@pytest.mark.parametrize("output_format", ["json", "markdown"])
def test_delivery_errors_do_not_read_status_or_fallback_result(monkeypatch, capsys, code, status, output_format):
    calls = []
    def denied(path, *, config):
        calls.append(path)
        raise tool.ToolClientHTTPError(status, {"code": code})
    monkeypatch.setattr(tool, "_findings_get_json", denied, raising=False)
    assert tool.main(["findings", "--run-id", "run_fixture", "--format", output_format]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == code
    assert calls == ["/api/runs/run_fixture/findings"]


@pytest.mark.parametrize("args", [[f"--timeout={value}"] for value in
    ("nan", "inf", "-inf", "0", "-1", "61", "invalid")] + [
    ["--base-url", "file:///private/service"], ["--base-url", "http://user:secret@localhost"],
    ["--base-url", "http://localhost/?secret=value"], ["--base-url", "http://localhost/#fragment"],
    ["--base-url", "http://localhost?"], ["--base-url", "http://localhost#"],
    ["--base-url", "http://localhost:invalid"], ["--base-url", "http://local host"],
    ["--base-url", "http://localhost/\nprivate"]])
def test_invalid_findings_configuration_fails_before_read(monkeypatch, capsys, args):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid configuration performed network access")
    monkeypatch.setattr(tool, "_findings_get_json", unexpected, raising=False)
    assert tool.main([*args, "findings", "--run-id", "run_fixture"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "findings_config_invalid"


@pytest.mark.parametrize("tamper", ["hash", "report", "run", "profile", "state", "scope",
                                   "foreign_evidence", "verification", "markdown_kind", "markdown_hash"])
def test_inconsistent_deliveries_never_become_success(monkeypatch, capsys, tamper):
    package, status, result = delivery()
    output_format = "markdown" if tamper.startswith("markdown") else "json"
    if tamper == "hash":
        package["artifact"]["content_hash"] = "0" * 64
    elif tamper == "report":
        package["report"]["limitations"] = ["unpersisted"]
    elif tamper == "run":
        package["run_id"] = "other"
    elif tamper == "profile":
        package["report"]["profile_id"] = "generic"
    elif tamper == "state":
        status["delivery_status"] = "blocked"
    elif tamper == "scope":
        status["scope"]["questions"][0]["text"] = "Different accepted question"
    elif tamper == "foreign_evidence":
        status["evidence"][0]["run_id"] = "other"
    elif tamper == "verification":
        status["evidence"][0]["verification_status"] = "invented"
    elif tamper == "markdown_kind":
        result["artifact"]["kind"] = "research_report_fallback_markdown"
    elif tamper == "markdown_hash":
        result["artifact"]["content_hash"] = "0" * 64
    install_reads(monkeypatch, package, status, result)
    assert tool.main(["findings", "--run-id", "run_fixture", "--format", output_format]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "findings_response_invalid"


@pytest.mark.parametrize("body,limit,code", [(b"\xff", 20, "invalid_json_response"),
    (b'{"x":1,"x":2}', 50, "invalid_json_response"), (b'{"x":NaN}', 50, "invalid_json_response"),
    (b'[]', 50, "json_response_not_object"), (b'{}          ', 8, "response_too_large"),
    (b'{"x":"\\ud800"}', 50, "invalid_json_response")])
def test_bounded_parser_rejects_unusable_bytes(body, limit, code):
    with pytest.raises(tool.ToolClientError) as error:
        tool._read_findings_json(io.BytesIO(body), max_bytes=limit, deadline=time.monotonic() + 5)
    assert error.value.payload["code"] == code


def test_pretty_print_expansion_fails_before_writing_partial_success(monkeypatch, capsys):
    package, status, result = delivery()
    extra = ["x"] * 16000
    for _ in range(300):
        extra = {"next": extra}
    package["extra"] = extra
    assert len(json.dumps(package).encode()) < 100000
    install_reads(monkeypatch, package, status, result)
    assert tool.main(["findings", "--run-id", "run_fixture"]) == 1
    value = json.loads(capsys.readouterr().out)
    assert value["code"] == "response_too_large" and "report" not in value
