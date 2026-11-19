"""Exercise the experiment through the native graph and a scripted wire transport."""
import asyncio
import json

import httpx
import pytest

from scripts.findings_quality_live import capture_experiment, replay_capture
from scripts.findings_quality_replay import write_report
from scripts.findings_quality_transport import BoundedChat, ChatBudget, MODEL

SOURCE = "https://sqlite.org/foreignkeys.html"
PASSAGE = (
    "Foreign key constraints are disabled by default (for backwards compatibility), "
    "so must be enabled separately for each database connection."
)


def candidate():
    return {
        "schema_version": "dra.research-findings-candidate.v1",
        "findings": [{"question_id": "q1", "statement": "The guide says enforcement is disabled by default "
                      "and enabled separately per database connection.",
                      "references": [{"source_url": SOURCE, "excerpt": PASSAGE}]}],
        "dispositions": [
            {"question_id": "q1", "status": "candidate_findings"},
            {"question_id": "q2", "status": "unresolved",
             "reason": "The application connection's live foreign-key setting is missing."},
        ],
    }


def response(assistant, finish_reason, *, tier="default"):
    return httpx.Response(200, json={"object": "chat.completion", "model": MODEL, "id": "rehearsal-call",
                                      "service_tier": tier, "choices": [
        {"index": 0, "message": {"role": "assistant", "refusal": None, **assistant}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600}})


def run_scripted(output, handler):
    async def execute():
        approval = "a" * 64
        budget = ChatBudget(12, 480_000, 24_576, 40_000, 2_048, 120, 480_000)
        async with BoundedChat(opt_in=True, approval_id=approval, proposal_sha256=approval,
                               budget=budget, receipt_dir=output / "receipts", transport=httpx.MockTransport(handler),
                               key_loader=lambda: "scripted") as chat:
            return await capture_experiment(chat, output)
    return asyncio.run(execute())


def scripted_generation():
    return response({"content": None, "tool_calls": [
        {"id": "rehearsal-write", "type": "function",
         "function": {"name": "write_file", "arguments": json.dumps(
             {"file_path": "/workspace/research-findings.json", "content": json.dumps(candidate())})}},
    ]}, "tool_calls")


def test_partial_capture_keeps_native_binding_diagnostics_after_provider_failure(tmp_path):
    calls = []
    def reply(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return scripted_generation()
        return httpx.Response(503, json={"provider_private_detail": "excluded from receipts"})
    assert run_scripted(tmp_path, reply) == "provider_failure"
    assert len(calls) == 2
    report = replay_capture(tmp_path)
    pair, = report["generation"]["pairs"]
    assert pair["A"]["outcome"] == "delivered"
    assert pair["A"]["passed"] is None
    assert pair["B"]["outcome"] == "provider_failure"
    assert pair["B"]["resources"]["input_tokens"] is None
    assert report["generation"]["counts"] == {
        "planned": 2, "started": 2, "delivered": 1, "scorable": 0, "unscored": 2, "comparable": 0}
    assert report["native_comparison"]["arms"]["B"]["visible_source"]["passage"] == PASSAGE
    assert report["native_comparison"]["arms"]["A"]["run_id"] != report["native_comparison"]["arms"]["B"]["run_id"]
    assert len(report["generation_review_sheet"]) == 1
    assert "provider_private_detail" not in json.dumps(report)


def supported_reply(request):
    payload = json.loads(request.content)
    if payload.get("tools"):
        return scripted_generation()
    blind = json.loads(payload["messages"][1]["content"])
    assert set(blind) == {"question", "statement", "citations"}
    matched = [ref["reference_id"] for ref in blind["citations"]]
    return response({"content": json.dumps({
        "verdict": "supported", "matched_reference_ids": matched,
        "rationale": "Scripted demonstration verdict.",
        "parts": [{"assertion": "Reported assertion", "reference_ids": matched,
                   "rationale": "Scripted citation lookup."}],
    })}, "stop")


def covered_generation(report):
    sheet, = report["generation_review_sheet"]
    assert "run_id" not in sheet and "arm" not in sheet
    return {"review_id": sheet["review_id"], "reviewer": "Scripted reviewer", "review_date": "2026-11-19",
            "blind": True, "claims": [{"finding_id": "f1", "covered_points": ["connection-scope", "guide-default"],
                                      "new_material": False, "forbidden_matches": []}],
            "unresolved": [{"question_id": "q2", "justified": True}]}


def test_full_scripted_capture_replays_blind_and_counts_real_interface_calls(tmp_path):
    calls = []
    def reply(request):
        calls.append(request)
        return supported_reply(request)

    assert run_scripted(tmp_path, reply) == "completed"
    assert len(calls) == 11  # two generator calls, eight fixed calibration inputs, one deduplicated claim
    report = replay_capture(tmp_path)
    assert report["native_comparison"]["parity"] == "matched_native_envelopes"
    assert report["generation"]["counts"]["delivered"] == 2
    assert report["case_origins"] == {"synthetic_control": 10}
    assert report["calibration"]["selected"] == 8
    assert report["calibration"]["compared"] == 0
    assert report["evaluator_resources"]["calls"]["total"] == 9
    assert report["generation"]["resources"]["calls"]["total"] == 2
    assert report["decision"]["status"] == "insufficient_evidence"
    assessed = replay_capture(tmp_path, generation_reviews=[covered_generation(report)])
    assert assessed["generation"]["pair_counts"]["both_pass"] == 1
    assert assessed["decision"]["status"] == "insufficient_evidence"
    write_report(tmp_path / "report", assessed)
    assert (tmp_path / "report/generation-review-sheet.json").is_file()


@pytest.mark.parametrize(("mutation", "proof_status"), [
    ("instruction", "mismatch"),
    ("source_offset", "mismatch"),
    ("native_digest", "mismatch"),
    ("transport_digest", "mismatch"),
    ("swapped_input", "mismatch"),
    ("missing_input", "missing"),
])
def test_capture_replay_requires_reconstructible_native_pair(tmp_path, mutation, proof_status):
    assert run_scripted(tmp_path, supported_reply) == "completed"
    original = replay_capture(tmp_path)
    review = covered_generation(original)
    assert original["native_comparison"]["parity"] == "matched_native_envelopes"

    path = tmp_path / "generation-B.json"
    captured = json.loads(path.read_text())
    if mutation == "instruction":
        captured["receipt"]["qualification_instruction_sha256"] = "0" * 64
        path.write_text(json.dumps(captured))
    elif mutation == "source_offset":
        for arm in ("A", "B"):
            location = tmp_path / f"generation-{arm}.json"
            record = json.loads(location.read_text())
            for key in ("start", "end"):
                record["receipt"]["visible_source"][key] += 1
            location.write_text(json.dumps(record))
    elif mutation == "native_digest":
        captured["receipt"]["request_sha256"] = "0" * 64
        path.write_text(json.dumps(captured))
    elif mutation == "transport_digest":
        for suffix in ("started", "result"):
            location = tmp_path / "receipts" / f"0002-{suffix}.json"
            request = json.loads(location.read_text())
            assert request["request_id"] == captured["receipt"]["model_request_id"]
            request["request_sha256"] = "0" * 64
            location.write_text(json.dumps(request))
    elif mutation == "swapped_input":
        (tmp_path / "generation-input-B.json").write_bytes((tmp_path / "generation-input-A.json").read_bytes())
    else:
        (tmp_path / "generation-input-B.json").unlink()

    result = replay_capture(tmp_path, generation_reviews=[review])
    assert result["native_comparison"]["parity"] == "standalone_prompt_experiment"
    assert result["native_comparison"]["arm_proofs"]["B"] == proof_status
    assert result["generation"]["counts"]["delivered"] == 2
    assert result["generation"]["counts"]["scorable"] == 2
    assert result["generation"]["counts"]["comparable"] == 0
    assert result["generation"]["pairs"][0]["comparison"] is None
    assert result["generation"]["regressions"] == result["generation"]["fixes"] == []


def test_capture_replay_rejects_a_different_rehashed_report_for_the_same_run(tmp_path):
    import hashlib

    from scripts.findings_quality_io import QualityError
    from scripts.research_findings_consumer import validate_delivery

    replies = iter([scripted_generation(), httpx.Response(503)])
    assert run_scripted(tmp_path, lambda request: next(replies)) == "provider_failure"
    path = tmp_path / "generation-A.json"
    capture = json.loads(path.read_text())
    delivery = capture["delivery"]
    delivery["report"]["findings"][0]["statement"] = "The bound passage proves enforcement is always enabled."
    raw = json.dumps(delivery["report"], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    delivery["artifact"]["content"] = raw
    delivery["artifact"]["content_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    validate_delivery(delivery, delivery["run_id"])
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(QualityError, match="delivery hash"):
        replay_capture(tmp_path)
    capture["receipt"]["delivery_sha256"] = delivery["artifact"]["content_hash"]
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(QualityError, match="rebound candidate"):
        replay_capture(tmp_path)


def test_successful_model_candidate_survives_a_local_finalization_failure(tmp_path, monkeypatch):
    from scripts import findings_quality_native

    def unavailable(**_):
        raise RuntimeError("local finalization interrupted")

    monkeypatch.setattr(findings_quality_native, "finalize_run_transaction", unavailable)
    calls = []
    def reply(request):
        calls.append(request.url)
        return scripted_generation()

    assert run_scripted(tmp_path, reply) == "local_experiment_failure"
    assert len(calls) == 1
    retained = json.loads((tmp_path / "candidate-A.json").read_text())
    assert json.loads(retained["candidate_content"]) == candidate()
    result = replay_capture(tmp_path)
    pair, = result["generation"]["pairs"]
    assert pair["A"]["outcome"] == "local_experiment_failure"
    assert pair["A"]["candidate_retained"] is True
    assert pair["A"]["resources"]["calls"] == 1
    assert pair["B"]["outcome"] == "not_started"


def test_native_capture_initializes_an_isolated_database_with_publication_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION", "true")
    replies = iter([scripted_generation(), httpx.Response(503)])
    assert run_scripted(tmp_path, lambda request: next(replies)) == "provider_failure"
    report = replay_capture(tmp_path)
    pair, = report["generation"]["pairs"]
    assert pair["A"]["outcome"] == "delivered"
    assert pair["B"]["outcome"] == "provider_failure"
