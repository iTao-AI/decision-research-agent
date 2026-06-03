"""Unit tests for the manual E2E runner helpers."""
import importlib.util
from pathlib import Path


def _load_runner_module():
    path = Path("scripts/e2e_runner.py").resolve()
    spec = importlib.util.spec_from_file_location("e2e_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestE2ERunnerHelpers:
    def test_is_terminal_status(self):
        runner = _load_runner_module()

        assert runner.is_terminal_status("completed") is True
        assert runner.is_terminal_status("completed_with_fallback") is True
        assert runner.is_terminal_status("failed") is True
        assert runner.is_terminal_status("running") is False

    def test_ws_url_for_http_api_base(self):
        runner = _load_runner_module()

        assert runner.default_ws_base("http://127.0.0.1:8000") == "ws://127.0.0.1:8000"
        assert runner.default_ws_base("https://example.com") == "wss://example.com"

    def test_count_websocket_events(self):
        runner = _load_runner_module()
        events = [
            {"type": "monitor_event", "event": "assistant_call"},
            {"type": "monitor_event", "event": "tool_start"},
            {"type": "monitor_event", "event": "tool_start"},
            {"type": "pong"},
        ]

        summary = runner.summarize_ws_events(events)

        assert summary["websocket_events"] == 3
        assert summary["assistant_calls"] == 1
        assert summary["tool_starts"] == 2
