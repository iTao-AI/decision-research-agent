"""Live Judge wiring with a real bounded adapter and no-network transport."""
import json

import httpx
import pytest


@pytest.mark.asyncio
async def test_invalid_judge_prediction_stops_transport_and_preserves_prior_result(tmp_path):
    from scripts.findings_quality_io import digest
    from scripts.findings_quality_live import record_judgment
    from scripts.findings_quality_transport import BoundedChat, ChatBudget, LiveCallError, MODEL

    called = []
    citation = {"reference_id": "R1", "source_url": "https://example.com/release", "source_version": "2",
                "excerpt": "Release 2 is required."}
    blind = {"question": "Which release?", "statement": "Release 2 is a prerequisite.", "citations": [citation]}

    def reply(request):
        payload = json.loads(request.content)
        assert json.loads(payload["messages"][1]["content"]) == blind
        called.append(request.url)
        ref = "R1" if len(called) == 1 else "invented"
        judgment = {"verdict": "supported", "matched_reference_ids": [ref], "rationale": "Exact citation.",
                    "parts": [{"assertion": "release", "reference_ids": [ref], "rationale": "Release 2."}]}
        return httpx.Response(200, json={
            "object": "chat.completion", "model": MODEL, "id": "scripted-response",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                         "content": json.dumps(judgment), "refusal": None}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160},
        })

    approval = "a" * 64
    budget = ChatBudget(3, 15_000, 600, 5_000, 200, 30, 10_000)
    async with BoundedChat(opt_in=True, approval_id=approval, proposal_sha256=approval,
                           budget=budget, receipt_dir=tmp_path / "receipts",
                           transport=httpx.MockTransport(reply), key_loader=lambda: "scripted") as chat:
        results = tmp_path / "judge"
        results.mkdir()
        await record_judgment(chat, blind, results / "first.json", request_id="first", basis="scripted_fixture")
        with pytest.raises(LiveCallError, match="invalid_response"):
            await record_judgment(chat, blind, results / "second.json", request_id="second", basis="scripted_fixture")
        with pytest.raises(LiveCallError, match="run_stopped"):
            await record_judgment(chat, blind, results / "third.json", request_id="third", basis="scripted_fixture")

    assert len(called) == 2
    prior = json.loads((results / "first.json").read_text())
    assert prior["judgment"]["verdict"] == "supported"
    assert prior["input_sha256"] == digest(blind)
    invalid = json.loads((results / "second.json").read_text())
    assert invalid["judgment"] is None
    assert invalid["outcome"] == "invalid_response"
    assert "invented" not in (results / "second.json").read_text()


def test_capture_replay_leaves_unstarted_arms_and_calibration_visible(tmp_path):
    from scripts.findings_quality_io import json_bytes
    from scripts.findings_quality_live import MODEL, RUBRIC_VERSION, _calibration_inputs, replay_capture

    calibration = _calibration_inputs()
    manifest = {"schema_version": "dra.findings-quality.captured-live.v1", "execution_mode": "scripted",
                "proposal_sha256": "a" * 64, "model": MODEL, "rubric_version": RUBRIC_VERSION,
                "calibration_inputs": sorted(calibration), "planned_arms": ["A", "B"]}
    (tmp_path / "manifest.json").write_bytes(json_bytes(manifest))
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "run.json").write_bytes(json_bytes({"execution_mode": "scripted", "model": MODEL,
                                                    "proposal_sha256": "a" * 64}))
    report = replay_capture(tmp_path)
    assert report["generation"]["counts"] == {
        "planned": 2, "started": 0, "delivered": 0, "scorable": 0, "unscored": 2, "comparable": 0}
    assert report["calibration"]["selected"] == 8
    assert report["calibration"]["reviewed"] == 0
    assert report["case_outcomes"] == {"judge_unobserved": 8}
    assert report["native_comparison"]["parity"] == "unobserved"


def test_approved_skill_snapshot_rejects_extra_discoverable_skills_and_freezes_bytes(tmp_path, monkeypatch):
    import hashlib
    from scripts import findings_quality_live as capture
    from scripts.findings_quality_io import QualityError

    root = tmp_path / "repo"
    monkeypatch.setattr(capture, "ROOT", root)
    approved = root / "skills/reporting/SKILL.md"
    approved.parent.mkdir(parents=True)
    approved.write_text("Approved bytes.", encoding="utf-8")
    paths = {"skills/reporting/SKILL.md": hashlib.sha256(approved.read_bytes()).hexdigest()}
    extra = root / "skills/untracked/SKILL.md"
    extra.parent.mkdir()
    extra.write_text("Unapproved text.", encoding="utf-8")
    with pytest.raises(QualityError, match="skill inventory"):
        capture._freeze_live_skills(paths, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
    extra.unlink()
    extra.parent.rmdir()
    snapshot = capture._freeze_live_skills(paths, tmp_path / "approved")
    approved.write_text("Later local edit.", encoding="utf-8")
    assert (snapshot / "reporting/SKILL.md").read_text() == "Approved bytes."
