import json

import httpx
import pytest
from fastapi.testclient import TestClient

from fieldwork.analysis import DeepSeekAnalysis, ReplayAnalysis
from fieldwork.artifact import validate_offline_html
from fieldwork.web import create_app


@pytest.mark.parametrize("markup", [
    '<script>alert(1)</script>', '<img src="https://example.com">',
    '<a href="javascript:alert(1)">open</a>', '<p onclick="alert(1)">x</p>',
    '<style>@import "https://example.com";</style>', '<meta http-equiv="refresh" content="0;url=x">',
    '<iframe srcdoc="x"></iframe>', '<style>p { background: uRl(x); }</style>',
])
def test_offline_artifact_rejects_active_content(markup):
    with pytest.raises(ValueError):
        validate_offline_html(f'<!doctype html><html><body>{markup}</body></html>'.encode())


def test_offline_artifact_keeps_local_anchor_and_details():
    validate_offline_html(b'<!doctype html><html><body><a href="#source">Open</a>'
                          b'<details id="source"><summary>Source</summary>Text</details></body></html>')


def test_model_is_bounded_and_only_sees_verified_context():
    seen = []

    def reply(request):
        seen.append(request)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"headline":"实测"}'}}],
            "model": "deepseek-flash", "usage": {"prompt_tokens": 18, "completion_tokens": 5},
        })

    model = DeepSeekAnalysis("test-key", max_calls=1, transport=httpx.MockTransport(reply))
    project = {"id": "northstar", "stage": "现场调查", "sample_prepared": False,
               "confirmed": {"items": []}, "path": "/private/scratch"}
    result = model(project, [{"id": "ref", "title": "IT 回函", "text": "来源原文", "page_start": 1, "producer_run_id": "ingest-proof"}])
    assert result["usage"]["prompt_tokens"] == 18
    sent = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.deepseek.com/chat/completions"
    assert sent["model"] == "deepseek-flash" and sent["thinking"] == {"type": "disabled"}
    assert sent["max_tokens"] == 1600 and "tools" not in sent
    user_input = json.loads(sent["messages"][1]["content"])
    assert user_input["evidence"][0]["text"] == "来源原文"
    assert "/private/scratch" not in seen[0].content.decode()
    with pytest.raises(ValueError, match="model_call_budget_exhausted"):
        model(project, [])
    assert len(seen) == 1


def test_replay_uses_permissions_and_actual_progress():
    passages = [
        {"id": "terms", "producer_run_id": "seed", "text": "现场访谈可独立推进。"},
        {"id": "letter", "text": "允许使用脱敏导出样本进行周三客户演示。实时告警接口仍未获批。"},
    ]
    analyzer = ReplayAnalysis()
    first = analyzer({"sample_prepared": False}, passages)
    ready = analyzer({"sample_prepared": True}, passages)
    assert first["items"][0]["action"] == "准备脱敏演示样本"
    assert ready["items"][0]["action"] == "走查周三演示流程"
    assert first["items"][1]["state"] == "waiting"
    assert first["items"][2]["state"] == "proceed"


def test_web_rejects_foreign_origin_and_unsafe_body(tmp_path):
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1:7195")
    path = "/api/fieldwork/projects/northstar"
    assert client.get(path).json()["stage"] == "现场调查"
    assert client.post(path + "/progress", headers={"Origin": "https://example.com"},
                       json={"sample_prepared": True}).status_code == 403
    assert client.get(path, headers={"Host": "example.com"}).status_code == 403
    assert client.post(path + "/analysis", json={"material_id": "../not-a-material",
                       "db": "/outside"}).status_code == 400
    assert client.post(path + "/materials?title=回函", content=b"not a PDF",
                       headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post(path + "/materials?title=回函", content=b"%PDF-1.4",
                       headers={"Content-Type": "application/pdf",
                                "Content-Length": str(8 * 1024 * 1024 + 1)}).status_code == 413


def test_provider_settings_reuse_only_official_deepseek_credentials():
    from fieldwork.web import _deepseek_key

    assert _deepseek_key({"DEEPSEEK_API_KEY": "configured"}) == "configured"
    assert _deepseek_key({
        "OPENAI_BASE_URL": "https://api.deepseek.com/v1/",
        "OPENAI_API_KEY": "official-alias",
    }) == "official-alias"
    for settings in ({"OPENAI_API_KEY": "wrong-provider"},
                     {"OPENAI_API_KEY": "wrong-provider", "OPENAI_BASE_URL": "https://example.com"},
                     {"DEEPSEEK_API_KEY": "other-destination", "DEEPSEEK_API_BASE": "https://example.com"}):
        with pytest.raises(ValueError, match="model_configuration_invalid"):
            _deepseek_key(settings)


def test_truncated_model_output_retains_metered_attempt():
    from fieldwork.analysis import ModelFailure

    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
        "choices": [{"finish_reason": "length", "message": {"content": '{"partial":'}}],
        "model": "deepseek-flash",
        "usage": {"prompt_tokens": 379, "completion_tokens": 1_600, "total_tokens": 1_979},
    }))
    model = DeepSeekAnalysis("fixture", transport=transport)
    with pytest.raises(ModelFailure) as raised:
        model({"stage": "现场调查", "sample_prepared": False}, [])
    assert raised.value.code == "model_incomplete"
    assert raised.value.receipt["usage"]["total_tokens"] == 1_979
    assert raised.value.receipt["usage"]["provider_requests"] == 1
    assert raised.value.receipt["finish_reason"] == "length"
    assert raised.value.receipt["output"] == '{"partial":'


def test_offline_artifact_must_identify_current_confirmed_snapshot():
    from fieldwork.artifact import snapshot_fingerprint

    snapshot = {"version": 2, "headline": "确认安排"}
    digest = snapshot_fingerprint(snapshot)
    markup = f'<!doctype html><html><head><meta name="fieldwork-snapshot-sha256" content="{digest}"></head><body></body></html>'.encode()
    validate_offline_html(markup, snapshot=snapshot)
    with pytest.raises(ValueError):
        validate_offline_html(markup, snapshot={**snapshot, "version": 1})
    with pytest.raises(ValueError):
        validate_offline_html(b"<!doctype html><html><body></body></html>", snapshot=snapshot)
