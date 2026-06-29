import argparse
import io
import json
from pathlib import Path
import re

import pytest

from tools import decision_research_agent_tool as tool


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def getcode(self):
        return self.status


def assert_error_envelope(payload, *, code):
    assert payload["code"] == code
    assert isinstance(payload["problem"], str) and payload["problem"]
    assert isinstance(payload["cause"], str) and payload["cause"]
    assert isinstance(payload["fix"], str) and payload["fix"]
    assert isinstance(payload["retryable"], bool)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_cli_help_uses_public_product_name(capsys):
    with pytest.raises(SystemExit):
        tool._build_parser().parse_args(["--help"])

    output = re.sub(r"\s+", " ", capsys.readouterr().out)
    assert "Decision Research Agent integration tool" in output


def test_healthcheck_calls_health_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        return FakeResponse({"status": "ok", "service": "decision-research-agent"})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    result = tool.healthcheck(tool.ToolConfig(base_url="http://127.0.0.1:9000", timeout_seconds=2))

    assert result["status"] == "ok"
    assert captured == {"url": "http://127.0.0.1:9000/health", "timeout": 2}


@pytest.mark.parametrize(
    "argv",
    [
        ["start-task", "--query", "research"],
        ["get-task", "--thread-id", "thread-1"],
        ["token-usage", "--thread-id", "thread-1"],
        ["research-run", "--thread-id", "thread-1"],
        ["research-runs"],
    ],
)
def test_legacy_commands_are_rejected(argv):
    with pytest.raises(SystemExit):
        tool._build_parser().parse_args(argv)


def test_public_docs_describe_cli_golden_path_and_error_contract():
    readme = Path("README.md").read_text(encoding="utf-8")
    integration = Path("docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")

    assert "--wait --result" in readme
    assert "--wait-timeout-seconds" in integration
    assert "run_wait_timeout" in integration
    for field in ("code", "problem", "cause", "fix", "retryable"):
        assert f"`{field}`" in integration


def test_http_failure_raises_structured_error(monkeypatch):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: FakeResponse({"detail": "bad request"}, status=400),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.healthcheck(tool.ToolConfig())

    assert captured.value.status == 400
    assert_error_envelope(captured.value.payload, code="http_400")


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (tool.error.URLError("https://secret.example/path"), "connection_failed"),
        (TimeoutError("provider token leaked"), "request_timeout"),
    ],
)
def test_transport_failures_are_structured_and_private(
    monkeypatch, capsys, raised, code
):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(raised),
    )

    exit_code = tool.main(["healthcheck"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert_error_envelope(payload, code=code)
    rendered = json.dumps(payload)
    assert "secret.example" not in rendered
    assert "provider token" not in rendered


def test_invalid_json_response_is_structured_and_private(monkeypatch, capsys):
    class InvalidJSONResponse(FakeResponse):
        def read(self):
            return b'{"secret": invalid}'

    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: InvalidJSONResponse({}),
    )

    assert tool.main(["healthcheck"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="invalid_json_response")
    assert "secret" not in json.dumps(payload)


def test_non_object_json_response_is_structured(monkeypatch, capsys):
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: FakeResponse(["unexpected"]),
    )

    assert tool.main(["healthcheck"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="json_response_not_object",
    )


def test_structured_http_error_fills_minimum_fields(monkeypatch):
    body = io.BytesIO(
        json.dumps({"code": "run_review_required", "problem": "Review required."}).encode()
    )
    http_error = tool.error.HTTPError(
        "https://secret.example/result", 409, "Conflict", {}, body
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.result("run_1", tool.ToolConfig())

    assert captured.value.status == 409
    assert_error_envelope(captured.value.payload, code="run_review_required")


def test_http_error_preserves_structured_review_envelope(monkeypatch):
    body = io.BytesIO(
        json.dumps(
            {
                "code": "durable_hitl_disabled",
                "problem": "Durable review is disabled.",
                "retryable": False,
            }
        ).encode("utf-8")
    )
    http_error = tool.error.HTTPError(
        "http://127.0.0.1:8000/api/reviews",
        404,
        "Not Found",
        {},
        body,
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.list_reviews(tool.ToolConfig())

    assert captured.value.status == 404
    assert captured.value.payload["code"] == "durable_hitl_disabled"
    assert_error_envelope(captured.value.payload, code="durable_hitl_disabled")


def test_review_list_and_show_encode_requests(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        if req.full_url.endswith("/api/runs/run%2F1"):
            return FakeResponse(
                {"review_workflow": {"review_id": "review/1"}}
            )
        if "/reviews/" in req.full_url:
            return FakeResponse({"review_id": "review/1"})
        return FakeResponse({"reviews": [], "next_cursor": None})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    config = tool.ToolConfig(base_url="http://127.0.0.1:9000")

    tool.list_reviews(
        config,
        status="waiting_decision",
        limit=20,
        cursor="cursor/value",
    )
    detail = tool.show_review(
        run_id="run/1",
        review_id=None,
        config=config,
    )

    assert detail["review_id"] == "review/1"
    assert urls == [
        (
            "http://127.0.0.1:9000/api/reviews"
            "?status=waiting_decision&limit=20&cursor=cursor%2Fvalue"
        ),
        "http://127.0.0.1:9000/api/runs/run%2F1",
        "http://127.0.0.1:9000/api/runs/run%2F1/reviews/review%2F1",
    ]


def test_review_show_fails_when_run_has_no_durable_review(monkeypatch):
    monkeypatch.setattr(
        tool,
        "get_run",
        lambda run_id, config: {"review_workflow": None},
    )

    with pytest.raises(tool.ToolClientError, match="run_has_no_durable_review"):
        tool.show_review(
            run_id="run_1",
            review_id=None,
            config=tool.ToolConfig(),
        )


def test_result_requests_canonical_result_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        return FakeResponse(
            {"artifact": {"artifact_id": "research-report.md"}}
        )

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    value = tool.result(
        "run/1",
        config=tool.ToolConfig(base_url="http://127.0.0.1:9000"),
    )

    assert value["artifact"]["artifact_id"] == "research-report.md"
    assert captured["url"] == "http://127.0.0.1:9000/api/runs/run%2F1/result"


def test_cli_result_prints_canonical_result(monkeypatch, capsys):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        return FakeResponse(
            {
                "run_id": "run_1",
                "artifact": {"artifact_id": "research-report.md"},
            }
        )

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    exit_code = tool.main(
        [
            "--base-url",
            "http://127.0.0.1:9000",
            "result",
            "--run-id",
            "run_1",
        ]
    )

    assert exit_code == 0
    assert urls == ["http://127.0.0.1:9000/api/runs/run_1/result"]
    assert json.loads(capsys.readouterr().out)["artifact"]["artifact_id"] == (
        "research-report.md"
    )


def test_cli_run_result_requires_wait_before_network(monkeypatch, capsys):
    monkeypatch.setattr(
        tool,
        "start_run",
        lambda **kwargs: pytest.fail("network path must not be called"),
    )

    assert tool.main(["run", "--query", "q", "--result"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="result_requires_wait",
    )


@pytest.mark.parametrize("run_id", [None, "", 123])
def test_cli_run_wait_rejects_invalid_creation_run_id(
    monkeypatch, capsys, run_id
):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": run_id})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: pytest.fail("invalid run_id must fail first"),
    )

    assert tool.main(["run", "--query", "q", "--wait"]) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="run_response_invalid",
    )


def test_cli_run_wait_result_prints_only_canonical_result(monkeypatch, capsys):
    calls = []

    def fake_wait(run_id, config, *, poll_seconds, timeout_seconds):
        calls.append(("poll", poll_seconds, timeout_seconds))
        return {"run_id": run_id, "execution_status": "completed"}

    monkeypatch.setattr(
        tool,
        "start_run",
        lambda **kwargs: calls.append(("create",)) or {"run_id": "run_1"},
    )
    monkeypatch.setattr(tool, "wait_for_run", fake_wait)
    monkeypatch.setattr(
        tool,
        "result",
        lambda *args, **kwargs: calls.append(("result",))
        or {"run_id": "run_1", "artifact": {"content": "# Report"}},
    )

    exit_code = tool.main(
        [
            "run",
            "--query",
            "q",
            "--wait",
            "--result",
            "--poll-seconds",
            "0.25",
            "--wait-timeout-seconds",
            "30",
        ]
    )

    assert exit_code == 0
    assert calls == [("create",), ("poll", 0.25, 30), ("result",)]
    assert json.loads(capsys.readouterr().out) == {
        "run_id": "run_1",
        "artifact": {"content": "# Report"},
    }


def test_cli_run_result_error_retains_service_code_and_safe_run_id(
    monkeypatch, capsys
):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": "run_1"})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: {"execution_status": "completed"},
    )
    monkeypatch.setattr(
        tool,
        "result",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                409,
                {
                    "code": "run_review_required",
                    "problem": "Review required.",
                    "fix": "Resolve the controlled review.",
                },
            )
        ),
    )

    assert tool.main(
        ["run", "--query", "private query", "--wait", "--result"]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="run_review_required")
    assert payload["run_id"] == "run_1"
    assert "private query" not in json.dumps(payload)


def test_cli_run_wait_timeout_includes_only_safe_run_context(
    monkeypatch, capsys
):
    monkeypatch.setattr(tool, "start_run", lambda **kwargs: {"run_id": "run_1"})
    monkeypatch.setattr(
        tool,
        "wait_for_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            tool.ToolClientError("run_wait_timeout")
        ),
    )

    assert tool.main(["run", "--query", "private query", "--wait"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_error_envelope(payload, code="run_wait_timeout")
    assert payload["run_id"] == "run_1"
    rendered = json.dumps(payload)
    assert "private query" not in rendered
    assert "thread" not in payload


def test_scope_file_unreadable_is_private(tmp_path):
    path = tmp_path / "private-scope.json"
    with pytest.raises(tool.ToolClientError) as captured:
        tool.read_scope_file(path)

    assert_error_envelope(captured.value.payload, code="scope_file_unreadable")
    assert str(path) not in json.dumps(captured.value.payload)


@pytest.mark.parametrize("content", ['{"broken":', "[]"])
def test_scope_file_invalid_is_private(tmp_path, content):
    path = tmp_path / "private-scope.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(tool.ToolClientError) as captured:
        tool.read_scope_file(path)

    assert_error_envelope(captured.value.payload, code="scope_file_invalid")
    rendered = json.dumps(captured.value.payload)
    assert str(path) not in rendered
    assert content not in rendered


def test_cli_run_wait_then_result_is_secret_safe_consumer_flow(
    monkeypatch,
    capsys,
):
    requests = []

    def fake_urlopen(req, timeout):
        requests.append(
            {
                "method": req.get_method(),
                "url": req.full_url,
                "headers": dict(req.headers),
                "body": (
                    json.loads(req.data.decode("utf-8"))
                    if req.data is not None
                    else None
                ),
            }
        )
        if req.full_url.endswith("/api/runs") and req.get_method() == "POST":
            return FakeResponse(
                {
                    "status": "started",
                    "run_id": "run_1",
                    "thread_id": "thread_1",
                },
                status=202,
            )
        if req.full_url.endswith("/api/runs/run_1/result"):
            return FakeResponse(
                {
                    "run_id": "run_1",
                    "artifact": {
                        "artifact_id": "research-report.md",
                        "content": "# Report",
                    },
                }
            )
        if req.full_url.endswith("/api/runs/run_1"):
            return FakeResponse(
                {
                    "run_id": "run_1",
                    "execution_status": "completed",
                    "delivery_status": "ready",
                }
            )
        raise AssertionError(f"unexpected request: {req.full_url}")

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "secret-key")
    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    exit_code = tool.main(
        [
            "--base-url",
            "http://127.0.0.1:9000",
            "run",
            "--query",
            "bounded public smoke",
            "--thread-id",
            "thread_1",
            "--wait",
            "--result",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "run_id": "run_1",
        "artifact": {
            "artifact_id": "research-report.md",
            "content": "# Report",
        },
    }
    assert "secret-key" not in captured.out
    assert "secret-key" not in captured.err
    assert [item["method"] for item in requests] == ["POST", "GET", "GET"]
    assert [item["url"] for item in requests] == [
        "http://127.0.0.1:9000/api/runs",
        "http://127.0.0.1:9000/api/runs/run_1",
        "http://127.0.0.1:9000/api/runs/run_1/result",
    ]
    assert requests[0]["body"] == {
        "query": "bounded public smoke",
        "profile_id": "generic",
        "scope": {},
        "thread_id": "thread_1",
    }


def test_result_preserves_structured_http_error(monkeypatch):
    body = io.BytesIO(
        json.dumps(
            {
                "code": "run_review_required",
                "problem": "Review required.",
                "fix": "Approve or reject review.",
            }
        ).encode("utf-8")
    )
    http_error = tool.error.HTTPError(
        "http://127.0.0.1:8000/api/runs/run_1/result",
        409,
        "Conflict",
        {},
        body,
    )
    monkeypatch.setattr(
        tool.request,
        "urlopen",
        lambda req, timeout: (_ for _ in ()).throw(http_error),
    )

    with pytest.raises(tool.ToolClientHTTPError) as captured:
        tool.result("run_1", tool.ToolConfig())

    assert captured.value.status == 409
    assert captured.value.payload["code"] == "run_review_required"


def test_review_read_parser_commands():
    parser = tool._build_parser()

    listed = parser.parse_args(["review", "list"])
    shown = parser.parse_args(["review", "show", "--run-id", "run_1"])

    assert listed.command == "review"
    assert listed.review_command == "list"
    assert listed.status == "waiting_decision"
    assert listed.limit == 20
    assert shown.review_command == "show"
    assert shown.run_id == "run_1"
    assert shown.review_id is None


def test_stable_decision_id_is_semantic_and_retry_safe():
    first = tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="reject",
        reason="Not accepted",
    )

    assert first == tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="reject",
        reason="Not accepted",
    )
    assert first != tool.stable_decision_id(
        run_id="run_1",
        review_id="review_1",
        revision=1,
        action="approve",
        reason=None,
    )
    assert re.fullmatch(r"decision_[0-9a-f]{32}", first)


def test_reject_parser_has_no_plain_reason_argument():
    parser = tool._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["review", "reject", "--run-id", "run_1", "--reason", "secret"]
        )


def test_reject_requires_exactly_one_safe_reason_source(tmp_path):
    reason_file = tmp_path / "reason.txt"
    reason_file.write_text("Not accepted\n", encoding="utf-8")

    assert tool.read_rejection_reason(
        reason_file=reason_file,
        reason_stdin=False,
        stdin=io.StringIO(""),
    ) == "Not accepted"
    assert tool.read_rejection_reason(
        reason_file=None,
        reason_stdin=True,
        stdin=io.StringIO("Read from stdin\n"),
    ) == "Read from stdin"
    with pytest.raises(
        tool.ToolClientError,
        match="exactly_one_reason_source_required",
    ):
        tool.read_rejection_reason(
            reason_file=None,
            reason_stdin=False,
            stdin=io.StringIO(""),
        )
    with pytest.raises(
        tool.ToolClientError,
        match="exactly_one_reason_source_required",
    ):
        tool.read_rejection_reason(
            reason_file=reason_file,
            reason_stdin=True,
            stdin=io.StringIO(""),
        )


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("missing-reason.txt", None),
        ("invalid-utf8-reason.txt", b"\xff\xfe"),
    ],
)
def test_reject_reason_file_failure_is_structured_and_private(
    tmp_path,
    capsys,
    filename,
    content,
):
    reason_file = tmp_path / filename
    if content is not None:
        reason_file.write_bytes(content)

    exit_code = tool.main(
        [
            "review",
            "reject",
            "--run-id",
            "run_1",
            "--reason-file",
            str(reason_file),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert_error_envelope(
        json.loads(captured.out),
        code="rejection_reason_unreadable",
    )
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert str(reason_file) not in captured.out
    assert str(reason_file) not in captured.err


class _RecordingTextIO(io.StringIO):
    def __init__(self, value):
        super().__init__(value)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


def test_rejection_reason_reads_bounded_overflow_sentinel_from_stdin():
    stdin = _RecordingTextIO("x" * 1003)

    with pytest.raises(
        tool.ToolClientError,
        match="rejection_reason_must_be_1_to_1000_characters",
    ):
        tool.read_rejection_reason(
            reason_file=None,
            reason_stdin=True,
            stdin=stdin,
        )

    assert stdin.read_sizes == [1002]


def test_rejection_reason_reads_bounded_overflow_sentinel_from_file(
    monkeypatch,
):
    reason_stream = _RecordingTextIO("x" * 1003)
    monkeypatch.setattr(
        Path,
        "open",
        lambda self, *args, **kwargs: reason_stream,
    )

    with pytest.raises(
        tool.ToolClientError,
        match="rejection_reason_must_be_1_to_1000_characters",
    ):
        tool.read_rejection_reason(
            reason_file=Path("reason.txt"),
            reason_stdin=False,
            stdin=io.StringIO(""),
        )

    assert reason_stream.read_sizes == [1002]


def test_rejection_reason_rejects_text_after_allowed_trailing_newline():
    stdin = _RecordingTextIO("x" * 1000 + "\n" + "DO_NOT_DROP")

    with pytest.raises(
        tool.ToolClientError,
        match="rejection_reason_must_be_1_to_1000_characters",
    ):
        tool.read_rejection_reason(
            reason_file=None,
            reason_stdin=True,
            stdin=stdin,
        )

    assert stdin.read_sizes == [1002]


@pytest.mark.parametrize("reason", ["", "x" * 1001])
def test_rejection_reason_is_bounded(reason):
    with pytest.raises(
        tool.ToolClientError,
        match="rejection_reason_must_be_1_to_1000_characters",
    ):
        tool.read_rejection_reason(
            reason_file=None,
            reason_stdin=True,
            stdin=io.StringIO(reason),
        )


def test_submit_review_decision_fetches_current_contract_before_post(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "review_id": "review/1",
            "review_revision": 3,
            "state_version": 7,
        },
    )

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(
            {
                "status": "resume_pending",
                "run_id": "run/1",
                "review_id": "review/1",
                "decision_id": captured["payload"]["decision_id"],
                "idempotent_replay": False,
            },
            status=202,
        )

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    response = tool.submit_review_decision(
        run_id="run/1",
        review_id=None,
        decision_id=None,
        action="reject",
        reason="Not accepted",
        config=tool.ToolConfig(base_url="http://127.0.0.1:9000"),
    )

    assert captured["url"] == (
        "http://127.0.0.1:9000/api/runs/run%2F1"
        "/reviews/review%2F1/decisions"
    )
    assert captured["method"] == "POST"
    assert captured["payload"] == {
        "decision_id": tool.stable_decision_id(
            run_id="run/1",
            review_id="review/1",
            revision=3,
            action="reject",
            reason="Not accepted",
        ),
        "review_revision": 3,
        "action": "reject",
        "reason": "Not accepted",
        "expected_state_version": 7,
    }
    assert "reason" not in response


def test_review_decision_parser_commands():
    parser = tool._build_parser()

    approved = parser.parse_args(
        ["review", "approve", "--run-id", "run_1", "--wait"]
    )
    rejected = parser.parse_args(
        [
            "review",
            "reject",
            "--run-id",
            "run_1",
            "--reason-stdin",
        ]
    )

    assert approved.review_command == "approve"
    assert approved.wait is True
    assert approved.review_id is None
    assert approved.decision_id is None
    assert rejected.review_command == "reject"
    assert rejected.reason_stdin is True
    assert rejected.reason_file is None


def test_cli_does_not_print_api_key(monkeypatch, capsys):
    def fake_urlopen(req, timeout):
        return FakeResponse({"status": "ok", "service": "decision-research-agent"})

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "secret-key")
    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    exit_code = tool.main(["healthcheck"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "secret-key" not in captured.out
    assert '"status": "ok"' in captured.out


def test_cli_rejects_api_key_argument():
    with pytest.raises(SystemExit):
        tool._build_parser().parse_args(["--api-key", "secret-key", "healthcheck"])


def test_doctor_checks_health_and_profile_manifest(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        if req.full_url.endswith("/api/evidence-verifications/health"):
            return FakeResponse(
                {
                    "status": "ok",
                    "worker_running": True,
                }
            )
        if req.full_url.endswith("/api/reviews/health"):
            return FakeResponse(
                {
                    "status": "ok",
                    "worker_running": True,
                    "gate_report_status": "PASS",
                }
            )
        if req.full_url.endswith("/health"):
            return FakeResponse({"status": "ok", "service": "decision-research-agent"})
        return FakeResponse(
            {
                "profile": {"profile_id": "talent-hiring-signal"},
                "harness_policy": {"allowed_tools": ["internet_search"]},
            }
        )

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    result = tool.doctor(tool.ToolConfig(base_url="http://127.0.0.1:9000"))

    assert result["status"] == "ok"
    assert result["checks"]["server"]["status"] == "ok"
    assert result["checks"]["server"]["service"] == "decision-research-agent"
    assert result["checks"]["talent_profile"]["status"] == "ok"
    assert result["checks"]["durable_review"] == {
        "status": "ok",
        "worker_running": True,
        "gate_report_status": "PASS",
    }
    assert result["checks"]["evidence_verification"] == {
        "status": "ok",
        "worker_running": True,
    }
    assert urls == [
        "http://127.0.0.1:9000/health",
        "http://127.0.0.1:9000/api/profiles/talent-hiring-signal",
        "http://127.0.0.1:9000/api/reviews/health",
        (
            "http://127.0.0.1:9000/api/"
            "evidence-verifications/health"
        ),
    ]


def test_doctor_treats_disabled_review_as_optional(monkeypatch):
    monkeypatch.setattr(tool, "healthcheck", lambda config: {"status": "ok"})
    monkeypatch.setattr(
        tool,
        "profile_manifest",
        lambda profile_id, config: {
            "profile": {"profile_id": "talent-hiring-signal"},
            "harness_policy": {"allowed_tools": []},
        },
    )
    monkeypatch.setattr(
        tool,
        "review_health",
        lambda config: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                404,
                {"code": "durable_hitl_disabled"},
            )
        ),
    )
    monkeypatch.setattr(
        tool,
        "evidence_verification_health",
        lambda config: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                404,
                {"code": "evidence_verification_disabled"},
            )
        ),
    )

    result = tool.doctor(tool.ToolConfig())

    assert result["status"] == "ok"
    assert result["checks"]["durable_review"]["status"] == "disabled"
    assert result["checks"]["evidence_verification"]["status"] == (
        "disabled"
    )


def test_doctor_fails_when_enabled_review_is_not_ready(monkeypatch):
    monkeypatch.setattr(tool, "healthcheck", lambda config: {"status": "ok"})
    monkeypatch.setattr(
        tool,
        "profile_manifest",
        lambda profile_id, config: {
            "profile": {"profile_id": "talent-hiring-signal"},
            "harness_policy": {"allowed_tools": []},
        },
    )
    monkeypatch.setattr(
        tool,
        "review_health",
        lambda config: {
            "status": "failed",
            "worker_running": False,
            "gate_report_status": "PASS",
        },
    )
    monkeypatch.setattr(
        tool,
        "evidence_verification_health",
        lambda config: (_ for _ in ()).throw(
            tool.ToolClientHTTPError(
                404,
                {"code": "evidence_verification_disabled"},
            )
        ),
    )

    result = tool.doctor(tool.ToolConfig())

    assert result["status"] == "failed"
    assert result["checks"]["durable_review"]["status"] == "failed"


def test_run_wait_parser_defaults():
    args = tool._build_parser().parse_args(["run", "--query", "q", "--wait"])

    assert args.result is False
    assert args.poll_seconds == 1
    assert args.wait_timeout_seconds == 600


@pytest.mark.parametrize(
    ("poll_seconds", "timeout_seconds", "code"),
    [
        (0, 1, "run_poll_seconds_must_be_positive"),
        (1, 0, "run_wait_timeout_seconds_must_be_positive"),
    ],
)
def test_wait_for_run_rejects_non_positive_bounds(
    poll_seconds, timeout_seconds, code
):
    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_run(
            "run_1",
            tool.ToolConfig(),
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )

    assert captured.value.payload["code"] == code


def test_wait_for_run_sleep_does_not_cross_deadline(monkeypatch):
    clock = FakeClock()
    poll_times = []
    monkeypatch.setattr(tool.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(tool.time, "sleep", clock.sleep)

    def fake_get_run(run_id, config):
        poll_times.append(clock.now)
        return {"execution_status": "running"}

    monkeypatch.setattr(tool, "get_run", fake_get_run)

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_run(
            "run_1",
            tool.ToolConfig(),
            poll_seconds=10,
            timeout_seconds=1,
        )

    assert captured.value.payload["code"] == "run_wait_timeout"
    assert clock.now == 1
    assert clock.sleeps == [1]
    assert poll_times == [0.0]


@pytest.mark.parametrize(
    "terminal_status",
    ["completed", "completed_with_fallback", "failed"],
)
def test_wait_for_run_polls_until_terminal(monkeypatch, terminal_status):
    responses = iter(
        [
            {"run_id": "run-1", "execution_status": "running"},
            {"run_id": "run-1", "execution_status": terminal_status},
        ]
    )
    monkeypatch.setattr(tool, "get_run", lambda run_id, config: next(responses))
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    result = tool.wait_for_run(
        "run-1",
        tool.ToolConfig(),
        poll_seconds=0.01,
        timeout_seconds=1,
    )

    assert result["execution_status"] == terminal_status


def test_wait_for_review_returns_terminal_resolution(monkeypatch):
    responses = iter(
        [
            {"workflow": {"status": "resume_pending"}},
            {"workflow": {"status": "approved"}},
        ]
    )
    monkeypatch.setattr(tool, "show_review", lambda **kwargs: next(responses))
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    result = tool.wait_for_review(
        run_id="run_1",
        review_id="review_1",
        config=tool.ToolConfig(),
        poll_seconds=0.01,
        timeout_seconds=1,
    )

    assert result["workflow"]["status"] == "approved"


def test_wait_for_review_fails_closed_on_manual_recovery(monkeypatch):
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "workflow": {
                "status": "manual_recovery",
                "last_error_code": "checkpoint_corrupt",
            }
        },
    )

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )

    assert_error_envelope(captured.value.payload, code="manual_recovery")
    assert captured.value.payload["recovery_code"] == "checkpoint_corrupt"


def test_local_error_catalog_always_builds_minimum_envelope():
    assert hasattr(tool, "_LOCAL_ERROR_DETAILS")
    for code in sorted(tool._LOCAL_ERROR_DETAILS):
        assert_error_envelope(tool.ToolClientError(code).payload, code=code)


def test_manual_recovery_does_not_expose_unbounded_error_code(monkeypatch):
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {
            "workflow": {
                "status": "manual_recovery",
                "last_error_code": "/private/path",
            }
        },
    )

    with pytest.raises(tool.ToolClientError) as captured:
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )

    assert captured.value.payload["recovery_code"] == "unknown"
    assert "/private/path" not in json.dumps(captured.value.payload)


def test_wait_for_review_sleep_does_not_cross_deadline(monkeypatch):
    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = FakeClock()
    monkeypatch.setattr(tool.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(tool.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        tool,
        "show_review",
        lambda **kwargs: {"workflow": {"status": "resume_pending"}},
    )

    with pytest.raises(tool.ToolClientError, match="review_wait_timeout"):
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=10,
            timeout_seconds=1,
        )

    assert clock.now == 1


@pytest.mark.parametrize(
    ("poll_seconds", "timeout_seconds", "code"),
    [
        (0, 1, "review_poll_seconds_must_be_positive"),
        (1, 0, "review_wait_timeout_seconds_must_be_positive"),
    ],
)
def test_wait_for_review_rejects_non_positive_bounds(
    poll_seconds,
    timeout_seconds,
    code,
):
    with pytest.raises(tool.ToolClientError, match=code):
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )


def test_review_wait_parser_defaults():
    args = tool._build_parser().parse_args(
        ["review", "wait", "--run-id", "run_1"]
    )

    assert args.poll_seconds == 1
    assert args.wait_timeout_seconds == 120
    assert args.review_id is None


def _args(*, base_url="", timeout=""):
    return argparse.Namespace(base_url=base_url, timeout=timeout)


def test_config_from_env_prefers_canonical_values(monkeypatch):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_URL",
        "https://canonical.example",
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", "17")

    config = tool.config_from_env(_args())

    assert config == tool.ToolConfig(
        base_url="https://canonical.example",
        api_key="",
        timeout_seconds=17,
    )


@pytest.mark.parametrize("canonical_timeout", ["", "invalid", "0", "-1"])
def test_invalid_canonical_timeout_uses_default(
    monkeypatch,
    canonical_timeout,
):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS",
        canonical_timeout,
    )

    config = tool.config_from_env(_args())

    assert config.timeout_seconds == tool.ToolConfig.timeout_seconds


def test_empty_canonical_url_uses_default_without_legacy(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_URL", "   ")

    config = tool.config_from_env(_args())

    assert config.base_url == tool.ToolConfig.base_url


def test_cli_flags_override_environment(monkeypatch):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_URL",
        "https://canonical.example",
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", "17")

    config = tool.config_from_env(
        _args(base_url="https://cli.example", timeout="29")
    )

    assert config.base_url == "https://cli.example"
    assert config.timeout_seconds == 29


def test_evidence_verify_requires_explicit_confirmation(capsys):
    assert tool.main(
        [
            "evidence",
            "verify",
            "--run-id",
            "run_1",
            "--evidence-id",
            "ev_1",
        ]
    ) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="confirm_source_match_required",
    )


def test_evidence_reject_reason_file_is_bounded_and_not_truncated(
    tmp_path,
    capsys,
):
    path = tmp_path / "reason.txt"
    path.write_text("x" * 1000 + "\nextra", encoding="utf-8")

    assert tool.main(
        [
            "evidence",
            "reject",
            "--run-id",
            "run_1",
            "--evidence-id",
            "ev_1",
            "--reason-code",
            "content_mismatch",
            "--reason-file",
            str(path),
        ]
    ) == 1
    assert_error_envelope(
        json.loads(capsys.readouterr().out),
        code="verification_reason_must_be_1_to_1000_characters",
    )


def test_verification_id_is_stable_and_content_scoped():
    first = tool.stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="verify",
        reason_code=None,
        reason_note=None,
    )

    assert first == tool.stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="verify",
        reason_code=None,
        reason_note=None,
    )
    assert first != tool.stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="reject",
        reason_code="content_mismatch",
        reason_note="mismatch",
    )


def test_evidence_finalize_uses_current_run_state_version(monkeypatch):
    requests = []

    def fake_request(method, url, *, config, payload=None):
        requests.append((method, url, payload))
        if method == "GET":
            return {"run_id": "run_1", "state_version": 5}
        return {"publication_id": "publication_2"}

    monkeypatch.setattr(tool, "_request_json", fake_request)
    result = tool.finalize_evidence_verification(
        run_id="run_1",
        config=tool.ToolConfig(base_url="http://127.0.0.1:9000"),
    )

    assert requests[-1] == (
        "POST",
        (
            "http://127.0.0.1:9000/api/runs/run_1/evidence/"
            "verification-snapshots"
        ),
        {"expected_state_version": 5},
    )
    assert result["publication_id"] == "publication_2"


def test_evidence_list_and_show_encode_requests(monkeypatch):
    requests = []

    def fake_request(method, url, *, config, payload=None):
        requests.append((method, url, payload))
        return {"items": []} if "verifications?" in url else {
            "effective": {"evidence_id": "ev/1"}
        }

    monkeypatch.setattr(tool, "_request_json", fake_request)
    config = tool.ToolConfig(base_url="http://127.0.0.1:9000")

    tool.list_evidence_verifications(
        run_id="run/1",
        limit=10,
        cursor="cursor/value",
        config=config,
    )
    tool.show_evidence_verification(
        run_id="run/1",
        evidence_id="ev/1",
        config=config,
    )

    assert requests == [
        (
            "GET",
            (
                "http://127.0.0.1:9000/api/runs/run%2F1/evidence/"
                "verifications?limit=10&cursor=cursor%2Fvalue"
            ),
            None,
        ),
        (
            "GET",
            (
                "http://127.0.0.1:9000/api/runs/run%2F1/evidence/"
                "ev%2F1/verification"
            ),
            None,
        ),
    ]
