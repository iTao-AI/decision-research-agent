import json

import pytest

from tools import deep_search_agent_tool as tool


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


def test_cli_does_not_print_api_key(monkeypatch, capsys):
    def fake_urlopen(req, timeout):
        return FakeResponse({"status": "ok", "service": "deep-search-agent"})

    monkeypatch.setenv("DEEP_SEARCH_AGENT_API_KEY", "secret-key")
    monkeypatch.setattr(tool.request, "urlopen", fake_urlopen)

    exit_code = tool.main(["healthcheck"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "secret-key" not in captured.out
    assert '"status": "ok"' in captured.out


def test_cli_rejects_api_key_argument():
    with pytest.raises(SystemExit):
        tool._build_parser().parse_args(["--api-key", "secret-key", "healthcheck"])
