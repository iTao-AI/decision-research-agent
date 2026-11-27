import hashlib
import json
from pathlib import Path

import pytest

from agent.research import EvidenceEntry
from scripts.findings_quality_io import digest, json_bytes
from scripts.findings_quality_replay import load_replay


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_prepare_keeps_coverage_and_withheld_sources_out_of_generation():
    from scripts.chinese_report_quality import prepare

    book_url = "https://example.com/handbook"
    sources = {
        "sources": [
            {
                "id": key,
                "title": "手册",
                "source_url": book_url,
                "version": "v1",
                "anchor": key,
                "snippet": text,
                "snippet_sha256": sha256(text),
                "excerpts": [
                    {"excerpt": text, "excerpt_start": 0, "excerpt_end": len(text), "excerpt_sha256": sha256(text)}
                ],
                "evaluation_note": "judge-only",
            }
            for key, text in (("method", "先查看日志。"), ("authority", "资源负责人审批。"))
        ]
    }
    cases = {
        "cases": [{
            "id": "troubleshooting",
            "entry": "controlled-materials",
            "report_language": "zh-CN",
            "prompt": ["谁可以批准重启？"],
            "coverage": [{"id": "approver", "requirement": "never tell the generator", "required": True}],
            "material_conditions": {
                "complete": {"source_ids": ["method", "authority"]},
                "withheld": {"source_ids": ["method"], "generation_instruction": "只看所给材料。"},
            },
        }]
    }

    payload = prepare(cases, sources)
    rows = payload["cases"]
    assert [row["condition"] for row in rows] == ["complete", "withheld"]
    assert rows[1]["questions"] == [{"question_id": "q1", "text": "谁可以批准重启？"}]
    assert [source["id"] for source in rows[1]["sources"]] == ["method"]
    assert rows[1]["additional_instruction"] == "只看所给材料。"
    assert "never tell the generator" not in str(payload)
    assert "judge-only" not in str(payload)

    sources["sources"][0]["snippet"] = "不同的原文。"
    with pytest.raises(ValueError, match="snippet hash"):
        prepare(cases, sources)


def test_binding_distinguishes_markdown_audit_from_delivery_and_excludes_blocked_candidates():
    from scripts.chinese_report_quality import bind

    url_a = "https://example.com/a"
    url_b = "https://example.com/b"
    materials = {"judge_rubric": {"coverage": "exact requirements"}, "cases": []}
    batch = {"cases": []}
    candidates = {"cases": []}
    for ident, entry, second_ref in (
        ("linked", "web-evidence-research", "必须先保存。"),
        ("broken", "web-evidence-research", "引文被改写。"),
        ("markdown", "web-general-markdown", "必须先保存。"),
    ):
        materials["cases"].append({
            "id": ident,
            "coverage": [{"id": "required", "requirement": "说明重试条件", "evidence_ids": [], "required": True}],
            "critical_errors": ["把失败当成未知"],
            "material_conditions": {"fixed": {"source_ids": ["a", "b"]}},
        })
        batch["cases"].append({
            "id": ident, "condition": "fixed", "entry": entry, "report_language": "zh-CN",
            "questions": [{"question_id": "q1", "text": "怎样重试？"}],
            "sources": [
                {"id": "a", "source_url": url_a, "snippet": "先看回执。", "version": "a-1"},
                {"id": "b", "source_url": url_b, "snippet": "必须先保存。", "version": "b-1"},
            ],
        })
        references = [{"source_url": url_a, "excerpt": "先看回执。"}, {"source_url": url_b, "excerpt": second_ref}]
        if entry == "web-general-markdown":
            references[0]["excerpt"] = "引文被改写。"
            candidate = {"markdown": "先确认是否已经完成。[2][99]", "citations": references}
        else:
            candidate = {
                "schema_version": "dra.research-findings-candidate.v1",
                "findings": [{"question_id": "q1", "statement": "先确认是否已经完成。", "references": references}],
                "dispositions": [{"question_id": "q1", "status": "candidate_findings"}],
            }
        candidates["cases"].append({"id": ident, "condition": "fixed", "candidate": candidate})

    binding, blind = bind(batch, candidates, materials)
    linked, broken, markdown = binding["cases"]
    assert (linked["outcome"], linked["references_bound"], linked["reference_binding_failures"]) == ("ready", 2, 0)
    assert broken["outcome"] == "blocked"
    assert broken["issues"] == ["excerpt_not_found"]
    assert broken["semantic"] == "unscorable"
    assert markdown["binding"] == "receipt_check_only"
    assert markdown["outcome"] == "markdown_available"
    linked_review, markdown_review = blind["cases"]
    assert [row["source_version"] for row in linked_review["input"]["claims"][0]["citations"]] == ["a-1", "b-1"]
    assert markdown_review["input"]["markdown"] == "先确认是否已经完成。[2][99]"
    assert markdown["reference_binding_failures"] == 1
    assert markdown["issues"] == ["excerpt_not_found", "unresolved_markdown_citation_marker"]
    assert [ref["reference_id"] for ref in markdown_review["input"]["claims"][0]["citations"]] == ["R2"]
    assert digest(linked_review["input"]) == linked_review["input_sha256"]
    assert "broken" not in {row["id"] for row in blind["cases"]}

    candidates["cases"].pop()
    with pytest.raises(ValueError, match="exactly match"):
        bind(batch, candidates, materials)


def test_read_materials_verifies_against_an_independent_manifest(tmp_path):
    from scripts.chinese_report_quality import read_materials

    data = '{"cases":[]}'
    source_data = '{"sources":[{"snippet":"书摘","snippet_sha256":"' + sha256("书摘") + '"}]}'
    (tmp_path / "cases.json").write_text(data, encoding="utf-8")
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(source_data, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(json_bytes({
        "case_file_sha256": sha256(data),
        "packet_sha256": sha256(source_data),
    }))

    assert read_materials(tmp_path, manifest)[1]["sources"][0]["snippet"] == "书摘"
    altered = source_data.replace("书摘", "替换").replace(sha256("书摘"), sha256("替换"))
    sources_file.write_text(altered, encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash differs for sources.json"):
        read_materials(tmp_path, manifest)


def test_record_rejects_receipts_with_the_wrong_input_hash_or_impossible_labels():
    from scripts.chinese_report_quality import record

    blind_input = {
        "coverage": [{"id": "retry", "required": True}],
        "critical_errors": ["误把 24 小时当作有保障"],
        "claims": [{"finding_id": "f1", "citations": [{"reference_id": "R1"}]}],
    }
    input_hash = digest(blind_input)
    identity = {"id": "a", "condition": "complete", "input_sha256": input_hash}
    blind = {"cases": [{**identity, "identity_sha256": digest(identity), "input": blind_input}]}
    row = {
        "input_sha256": input_hash,
        "verdicts": [{
            "finding_id": "f1", "verdict": "supported", "matched_reference_ids": ["R1"], "rationale": "原文支持。",
            "parts": [{"assertion": "只在窗口内重试。", "reference_ids": ["R1"], "rationale": "原文写明窗口。"}],
        }],
        "coverage": [{"id": "retry", "score": 1, "reason": "区分了两个窗口。"}],
        "readability": {"score": 2, "reason": "适用条件清楚。"},
        "critical_errors": [],
    }
    receipts = {"judge": {"model": "example-independent-judge", "prompt_version": "v1"}, "cases": [row]}
    result = record(blind, receipts)
    assert result["cases"][0]["coverage"] == {"satisfied": 1, "required": 1, "unscorable": 0}
    assert result["cases"][0]["semantic_verdict_counts"] == {"supported": 1}
    assert result["cases"][0]["review"]["verdicts"][0]["rationale"] == "原文支持。"
    blind["cases"][0]["condition"] = "withheld"
    with pytest.raises(ValueError, match="identity hash"):
        record(blind, receipts)
    blind["cases"][0]["condition"] = "complete"
    row["verdicts"][0]["matched_reference_ids"] = ["R2"]
    with pytest.raises(ValueError, match="reference"):
        record(blind, receipts)
    row["verdicts"][0]["matched_reference_ids"] = ["R1"]
    row["input_sha256"] = "wrong"
    with pytest.raises(ValueError, match="exactly match"):
        record(blind, receipts)


def test_historical_ledger_replay_stays_execution_only(tmp_path):
    from scripts.chinese_report_quality import main, replay_history

    run_id = "run-saved"
    url = "https://example.com/release"
    rows = []
    for snippet in ("共有片段。唯一原句。", "共有片段。另一个观察。"):
        entry = EvidenceEntry(thread_id="thread-a", query_text="问题", subagent_name="search", tool_name="search",
                              source_url=url, snippet=snippet)
        rows.append({**entry.to_dict(), "run_id": run_id})
    diag = {
        "schema_version": "dra.research-findings-diagnostics.v1",
        "run_id": run_id, "issue_codes": ["excerpt_not_found", "ambiguous_reference"],
        "reference_binding_failure_count": 3, "requested_question_count": 1, "covered_question_count": 1,
        "unresolved_question_count": 0,
    }
    diagnostics_bytes = json.dumps(diag).encode()
    artifact_hash = hashlib.sha256(diagnostics_bytes).hexdigest()
    archive = tmp_path / "archive"
    archive.mkdir()
    status = {
        "run_id": run_id, "thread_id": "thread-a", "execution_status": "completed", "delivery_status": "blocked",
        "evidence": rows, "findings_issues": diag["issue_codes"],
        "findings_outcome": {key: value for key, value in diag.items() if key.endswith("_count")},
        "artifacts": [{"artifact_id": "research-findings-diagnostics.json", "content_hash": artifact_hash}],
    }
    blocked = {"code": "run_delivery_blocked", "run_id": run_id}
    for name, payload in {
        "run-status": status, "result": blocked, "findings": blocked,
        "tool-telemetry": [{"run_id": run_id, "tool_name": "tavily_search", "status": "success"}],
        "citation-replay": {"run_id": run_id, "cases": [
            {"source_url": url, "excerpt": phrase, "matching_snippets": count, "result": expected, "case": expected}
            for phrase, count, expected in (
                ("不在快照。", 0, "excerpt_not_found"),
                ("唯一原句。", 1, "bound"),
                ("共有片段。", 2, "ambiguous_reference"),
            )
        ]},
    }.items():
        (archive / f"{name}.json").write_bytes(json_bytes(payload))
    (archive / "research-findings-diagnostics.json").write_bytes(diagnostics_bytes)

    observation, diagnostics = replay_history(archive, run_id)
    assert observation["source_calls"]["count"] == 1
    assert observation["primary_artifact_available"] is False
    assert diagnostics["reference_binding_failures"] == 3
    assert [row["matching_snippets"] for row in diagnostics["probes"]] == [0, 1, 2]
    assert diagnostics["semantic"] == "unscorable"

    output = tmp_path / "history"
    assert main(["history", "--archive", str(archive), "--output-dir", str(output)]) == 0
    assert json.loads((output / "binding-probes.json").read_bytes())["run_id"] == run_id

    path = tmp_path / "observation.json"
    path.write_bytes(json_bytes(observation))
    report = load_replay(Path("benchmarks/findings-quality-v1"), observation_paths=[path])
    assert report["execution_only"][0]["diagnosis"]["earliest_stage"] == "application_binding"
    assert not any(row.get("run_id") == run_id for row in report["cases"])

    (archive / "research-findings-diagnostics.json").write_bytes(diagnostics_bytes + b" ")
    with pytest.raises(ValueError, match="artifact hash"):
        replay_history(archive, run_id)


def test_public_citation_replay_binds_both_quotes_and_preserves_fixed_scope_verdicts(tmp_path, monkeypatch):
    import socket

    from scripts.chinese_report_quality import main

    def unexpected_network(*args, **kwargs):
        pytest.fail("public citation replay opened a network connection")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_network)
    monkeypatch.setattr(socket.socket, "connect", unexpected_network)
    destination = tmp_path / "citation-replay.json"
    command = ["public-citation-replay", "--output", str(destination)]
    assert main(command) == 0
    original = destination.read_bytes()
    assert main(command) == 0
    assert destination.read_bytes() == original
    result = json.loads(original)
    assert result["evaluation_basis"] == "frozen_materials_and_fixed_manual_labels"

    positive, negative = result["cases"]
    assert positive["question"] == negative["question"]
    assert positive["conclusion"] == negative["conclusion"]
    assert positive["claim_operation"] == negative["claim_operation"] == {
        "method": "POST", "path": "/open-apis/im/v1/messages",
    }
    for row in (positive, negative):
        assert row["binding"] == {
            "producer": "dra_application", "outcome": "ready",
            "references_bound": 1, "reference_binding_failures": 0,
        }
        assert row["semantic"]["reason"]
        assert row["citation"]["source_body_sha256"]
    assert positive["citation"]["operation"] == positive["claim_operation"]
    assert positive["citation"]["excerpt"] == "持有相同 uuid 的请求，在 1 小时内至多成功发送一条消息。"
    assert positive["semantic"]["verdict"] == "supported"
    assert negative["citation"]["operation"] == {
        "method": "POST", "path": "/open-apis/im/v1/messages/:message_id/reply",
    }
    assert negative["citation"]["excerpt"] == "持有相同 uuid 的请求，在 1 小时内至多成功回复一条消息。"
    assert negative["semantic"]["verdict"] == "insufficient_evidence"


def test_public_fixed_label_rejects_a_changed_claim():
    from scripts.chinese_report_quality import PUBLIC_CITATION_FIXTURE, replay_public_citations

    fixture = json.loads(PUBLIC_CITATION_FIXTURE.read_bytes())
    fixture["conclusion"] += "该保证同样适用于 24 小时后。"
    with pytest.raises(ValueError, match="fixed semantic label input has changed"):
        replay_public_citations(fixture)
