"""Exercise the experiment through the native graph and a scripted wire transport."""
import asyncio
import json

import httpx

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


def test_full_scripted_capture_replays_blind_and_counts_real_interface_calls(tmp_path):
    calls = []
    def reply(request):
        payload = json.loads(request.content)
        calls.append(payload)
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
    sheet, = report["generation_review_sheet"]
    assert "run_id" not in sheet and "arm" not in sheet
    review = {"review_id": sheet["review_id"], "reviewer": "Scripted reviewer", "review_date": "2026-11-19",
              "blind": True, "claims": [{"finding_id": "f1", "covered_points": ["connection-scope", "guide-default"],
                                        "new_material": False, "forbidden_matches": []}],
              "unresolved": [{"question_id": "q2", "justified": True}]}
    assessed = replay_capture(tmp_path, generation_reviews=[review])
    assert assessed["generation"]["pair_counts"]["both_pass"] == 1
    assert assessed["decision"]["status"] == "insufficient_evidence"
    write_report(tmp_path / "report", assessed)
    assert (tmp_path / "report/generation-review-sheet.json").is_file()
