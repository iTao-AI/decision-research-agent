import argparse
import io
import json
from pathlib import Path
import re
import warnings

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
        return FakeResponse({"status": "ok", "service": "deep-search-agent"})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    result = tool.healthcheck(tool.ToolConfig(base_url="http://127.0.0.1:9000", timeout_seconds=2))

    assert result["status"] == "ok"
    assert captured == {"url": "http://127.0.0.1:9000/health", "timeout": 2}


def test_start_task_posts_query_thread_id_and_auth_header(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"status": "started", "thread_id": "thread-1"})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    result = tool.start_task(
        query="research question",
        thread_id="thread-1",
        config=tool.ToolConfig(base_url="http://127.0.0.1:9000", api_key="secret-key"),
    )

    assert result["thread_id"] == "thread-1"
    assert captured["url"] == "http://127.0.0.1:9000/api/task"
    assert captured["headers"]["X-api-key"] == "secret-key"
    assert captured["body"] == {"query": "research question", "thread_id": "thread-1"}
    assert "secret-key" not in json.dumps(result)


def test_get_task_and_token_usage_call_expected_endpoints(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        if req.full_url.endswith("/api/tasks/thread-1"):
            return FakeResponse({"thread_id": "thread-1", "status": "completed"})
        return FakeResponse({"thread_id": "thread-1", "total_tokens": 123})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    config = tool.ToolConfig(base_url="http://127.0.0.1:9000")

    task = tool.get_task("thread-1", config)
    usage = tool.token_usage("thread-1", config)

    assert task["status"] == "completed"
    assert usage["total_tokens"] == 123
    assert urls == [
        "http://127.0.0.1:9000/api/tasks/thread-1",
        "http://127.0.0.1:9000/api/token-usage/thread-1",
    ]


def test_research_run_and_research_runs_call_expected_endpoints(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        if req.full_url.endswith("/api/research/runs/thread-1"):
            return FakeResponse({"thread_id": "thread-1", "evidence": []})
        return FakeResponse({"runs": [{"thread_id": "thread-1"}]})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)
    config = tool.ToolConfig(base_url="http://127.0.0.1:9000")

    run = tool.research_run("thread-1", config)
    runs = tool.research_runs(config, limit=5)

    assert run["thread_id"] == "thread-1"
    assert runs["runs"][0]["thread_id"] == "thread-1"
    assert urls == [
        "http://127.0.0.1:9000/api/research/runs/thread-1",
        "http://127.0.0.1:9000/api/research/runs?limit=5",
    ]


def test_get_task_url_encodes_thread_id(monkeypatch):
    urls = []

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        return FakeResponse({"thread_id": "a/b", "status": "completed"})

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    tool.get_task("a/b", tool.ToolConfig(base_url="http://127.0.0.1:9000"))
    tool.token_usage("a/b", tool.ToolConfig(base_url="http://127.0.0.1:9000"))
    tool.research_run("a/b", tool.ToolConfig(base_url="http://127.0.0.1:9000"))

    assert urls == [
        "http://127.0.0.1:9000/api/tasks/a%2Fb",
        "http://127.0.0.1:9000/api/token-usage/a%2Fb",
        "http://127.0.0.1:9000/api/research/runs/a%2Fb",
    ]


def test_http_failure_raises_structured_error(monkeypatch):
    def fake_urlopen(req, timeout):
        return FakeResponse({"detail": "bad request"}, status=400)

    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    with pytest.raises(tool.ToolClientError, match="HTTP 400"):
        tool.healthcheck(tool.ToolConfig())


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
    assert json.loads(captured.out) == {
        "status": "failed",
        "error": "rejection_reason_unreadable",
    }
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
        return FakeResponse({"status": "ok", "service": "deep-search-agent"})

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
            return FakeResponse({"status": "ok", "service": "deep-search-agent"})
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
    assert result["checks"]["server"]["service"] == "deep-search-agent"
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


def test_wait_for_run_polls_until_terminal(monkeypatch):
    responses = iter(
        [
            FakeResponse({"run_id": "run-1", "execution_status": "running"}),
            FakeResponse({"run_id": "run-1", "execution_status": "completed"}),
        ]
    )
    monkeypatch.setattr(tool.request, "urlopen", lambda req, timeout: next(responses))
    monkeypatch.setattr(tool.time, "sleep", lambda seconds: None)

    result = tool.wait_for_run(
        "run-1",
        tool.ToolConfig(base_url="http://127.0.0.1:9000"),
        poll_seconds=0.01,
    )

    assert result["execution_status"] == "completed"


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

    with pytest.raises(
        tool.ToolClientError,
        match="manual_recovery:checkpoint_corrupt",
    ):
        tool.wait_for_review(
            run_id="run_1",
            review_id="review_1",
            config=tool.ToolConfig(),
            poll_seconds=0.01,
            timeout_seconds=1,
        )


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
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_API_KEY", "legacy-secret")
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TIMEOUT_SECONDS", "23")
    tool._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = tool.config_from_env(_args())

    assert config == tool.ToolConfig(
        base_url="https://canonical.example",
        api_key="",
        timeout_seconds=17,
    )
    messages = [str(item.message) for item in caught]
    assert len(messages) == 3
    assert all("ignored" in message for message in messages)
    assert "legacy-secret" not in "\n".join(messages)
    assert "canonical.example" not in "\n".join(messages)
    assert "legacy.example" not in "\n".join(messages)


def test_config_from_env_supports_legacy_values_with_value_free_warnings(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_API_KEY", "legacy-secret")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TIMEOUT_SECONDS", "23")
    tool._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = tool.config_from_env(_args())

    assert config == tool.ToolConfig(
        base_url="https://legacy.example",
        api_key="legacy-secret",
        timeout_seconds=23,
    )
    messages = [str(item.message) for item in caught]
    assert len(messages) == 3
    assert all("deprecated; use" in message for message in messages)
    assert "legacy-secret" not in "\n".join(messages)
    assert "legacy.example" not in "\n".join(messages)


def test_legacy_config_survives_strict_future_warning_filter(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example")
    tool._reset_warning_state_for_tests()

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        config = tool.config_from_env(_args())

    assert config.base_url == "https://legacy.example"


@pytest.mark.parametrize("canonical_timeout", ["", "invalid", "0", "-1"])
def test_invalid_canonical_timeout_uses_default_without_legacy(
    monkeypatch,
    canonical_timeout,
):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS",
        canonical_timeout,
    )
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TIMEOUT_SECONDS", "23")

    config = tool.config_from_env(_args())

    assert config.timeout_seconds == tool.ToolConfig.timeout_seconds


def test_empty_canonical_url_uses_default_without_legacy(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_URL", "   ")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example")

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
    assert json.loads(capsys.readouterr().out)["error"] == (
        "confirm_source_match_required"
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
    assert json.loads(capsys.readouterr().out)["error"] == (
        "verification_reason_must_be_1_to_1000_characters"
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
