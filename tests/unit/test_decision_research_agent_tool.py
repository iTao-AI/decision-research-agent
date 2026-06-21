import argparse
import io
import json
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
    assert urls == [
        "http://127.0.0.1:9000/health",
        "http://127.0.0.1:9000/api/profiles/talent-hiring-signal",
    ]


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
