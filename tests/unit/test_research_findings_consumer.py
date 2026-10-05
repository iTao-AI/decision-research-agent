"""Independent delivery validation and failed-child/output controls."""
import copy
import hashlib
import importlib
import json
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def consumer():
    return importlib.import_module("scripts.research_findings_consumer")


def package():
    url, snippet = "https://example.com/source", "A 🧪 observed material."
    fingerprint = hashlib.sha256(f"{url}\n{snippet}".encode()).hexdigest()
    ref = {"evidence_id": f"ev_run_fixture_{fingerprint}", "evidence_fingerprint": fingerprint,
           "source_url": url, "source_identity": url, "snippet": snippet,
           "excerpt": "observed", "excerpt_start": 4, "excerpt_end": 12}
    report = {"schema_version": "dra.research-findings.v1", "run_id": "run_fixture",
              "profile_id": "generic-evidence-report", "profile_version": "1",
              "questions": [{"question_id": "q1", "text": "Question?"}],
              "findings": [{"finding_id": "f1", "question_id": "q1",
                            "statement": "Candidate", "references": [ref]}],
              "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
              "reported_contradictions": [], "limitations": []}
    value = {"run_id": "run_fixture", "execution_status": "completed", "delivery_status": "ready",
             "review_status": "resolved", "review_decision": {"run_id": "run_fixture", "action": "approve"},
             "report": report, "artifact": {"artifact_id": "research-findings.json",
                 "kind": "research_findings_json", "media_type": "application/json"},
             "evidence": [{**{key: ref[key] for key in ("evidence_id", "evidence_fingerprint",
                 "source_url", "source_identity", "snippet")}, "run_id": "run_fixture",
                 "verification_status": "unverified", "citation_status": "cited"}]}
    rehash(value)
    return value


def rehash(value):
    content = json.dumps(value["report"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    value["artifact"].update(content=content, content_hash=hashlib.sha256(content.encode()).hexdigest())


def test_receipt_keeps_approval_and_actual_verification_separate(consumer):
    value = package()
    receipt = consumer.validate_delivery(value, "run_fixture")
    assert receipt["schema_version"] == "dra.research-findings-consumption.v1"
    assert receipt["review_decision_action"] == "approve"
    assert receipt["references"][0]["verification_status"] == "unverified"
    assert receipt["references"][0]["citation_status"] == "cited"
    assert receipt["questions"] == [{"question_id": "q1", "status": "candidate_findings", "finding_ids": ["f1"]}]
    assert receipt["checks"] == {"artifact_hash": True, "report_matches_artifact": True,
        "run_profile_identity": True, "question_dispositions": True,
        "same_run_evidence_binding": True, "unicode_excerpt_offsets": True, "public_source_urls": True}
    assert "Candidate" not in json.dumps(receipt)
    assert "observed material" not in json.dumps(receipt)
    value["evidence"][0]["verification_status"] = "verified"
    assert consumer.validate_delivery(value, "run_fixture")["references"][0]["verification_status"] == "verified"


@pytest.mark.parametrize("tamper", ["foreign_run", "profile", "hash", "missing_disposition",
    "unknown_question", "empty_references", "foreign_ref", "offset", "bool_offset", "source",
    "private_source", "fragment_source", "escaped_control_source", "duplicate_finding",
    "unknown_verification", "missing_verification", "fingerprint", "snippet", "report_mismatch"])
def test_rehashed_invalid_bindings_or_coverage_do_not_pass(consumer, tamper):
    value = package()
    report, row = value["report"], value["evidence"][0]
    ref = report["findings"][0]["references"][0]
    if tamper == "foreign_run": value["run_id"] = "other"
    elif tamper == "profile": report["profile_id"] = "generic"
    elif tamper == "missing_disposition": report["dispositions"] = []
    elif tamper == "unknown_question": report["findings"][0]["question_id"] = "q2"
    elif tamper == "empty_references": report["findings"][0]["references"] = []
    elif tamper == "foreign_ref": ref["evidence_id"] = "ev_other_run"
    elif tamper == "offset": ref["excerpt_start"] = 5
    elif tamper == "bool_offset": ref["excerpt_start"] = True
    elif tamper in {"source", "private_source", "fragment_source", "escaped_control_source"}:
        url = {"source": "javascript:alert(1)", "private_source": "https://127.0.0.1/source",
               "fragment_source": "https://example.com/source#secret",
               "escaped_control_source": "https://example.com/%0Asecret"}[tamper]
        ref["source_url"] = row["source_url"] = url
    elif tamper == "duplicate_finding": report["findings"].append(copy.deepcopy(report["findings"][0]))
    elif tamper == "unknown_verification": row["verification_status"] = "approved"
    elif tamper == "missing_verification": row.pop("verification_status")
    elif tamper == "fingerprint": row["evidence_fingerprint"] = "0" * 64
    elif tamper == "snippet": row["snippet"] = "different observed material"
    rehash(value)
    if tamper == "hash": value["artifact"]["content_hash"] = "0" * 64
    elif tamper == "report_mismatch": report["limitations"] = ["Not in stored JSON"]
    with pytest.raises(consumer.ConsumerError) as error:
        consumer.validate_delivery(value, "run_fixture")
    assert error.value.code == "consumer_delivery_invalid"


@pytest.mark.parametrize("child,code", [
    (SimpleNamespace(returncode=1, stdout=b""), "consumer_process_failed"),
    (SimpleNamespace(returncode=0, stdout=b"\xff"), "consumer_response_invalid"),
    (SimpleNamespace(returncode=0, stdout=b'{"x":1,"x":2}'), "consumer_response_invalid"),
    (SimpleNamespace(returncode=0, stdout=b'{"x":NaN}'), "consumer_response_invalid"),
    (SimpleNamespace(returncode=1, stdout=b'{"code":"run_not_terminal","retryable":false}'), "run_not_terminal"),
    (SimpleNamespace(returncode=2, stdout=b""), "consumer_process_failed"),
])
def test_child_failure_never_writes_a_receipt(consumer, monkeypatch, tmp_path, capsys, child, code):
    monkeypatch.setattr(consumer.subprocess, "run", lambda *args, **kwargs: child)
    target = tmp_path / "receipt.json"
    assert consumer.main(["--run-id", "run_fixture", "--output", str(target)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == code
    assert not target.exists()


def test_child_timeout_is_bounded_and_not_reported_as_success(consumer, monkeypatch, tmp_path, capsys):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(consumer.subprocess, "run", timeout)
    target = tmp_path / "receipt.json"
    assert consumer.main(["--run-id", "run_fixture", "--output", str(target)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "consumer_timeout"
    assert not target.exists()


def test_existing_receipt_is_preserved_before_starting_a_child(consumer, monkeypatch, tmp_path, capsys):
    target = tmp_path / "receipt.json"
    target.write_bytes(b"owned by another invocation")
    def unexpected(*args, **kwargs):
        pytest.fail("existing receipt started a child")
    monkeypatch.setattr(consumer.subprocess, "run", unexpected)
    assert consumer.main(["--run-id", "run_fixture", "--output", str(target)]) == 1
    assert target.read_bytes() == b"owned by another invocation"
    assert json.loads(capsys.readouterr().out)["code"] == "consumer_output_failed"


def test_receipt_write_failure_leaves_no_partial_file(consumer, tmp_path):
    target = tmp_path / "missing-parent" / "receipt.json"
    with pytest.raises(consumer.ConsumerError) as error:
        consumer.write_receipt(target, consumer.validate_delivery(package(), "run_fixture"))
    assert error.value.code == "consumer_output_failed"
    assert not target.exists()


def test_exclusive_publication_cannot_overwrite_a_racing_output(consumer, tmp_path):
    target = tmp_path / "receipt.json"
    target.write_bytes(b"existing receipt")
    with pytest.raises(consumer.ConsumerError) as error:
        consumer.write_receipt(target, consumer.validate_delivery(package(), "run_fixture"))
    assert error.value.code == "consumer_output_failed"
    assert target.read_bytes() == b"existing receipt"
    assert list(tmp_path.iterdir()) == [target]


def test_oversized_child_output_has_no_receipt(consumer, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(consumer.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=b" " * (8 * 1024 * 1024 + 1)))
    target = tmp_path / "oversized.json"
    assert consumer.main(["--run-id", "run_fixture", "--output", str(target)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "consumer_response_invalid"
    assert not target.exists()
