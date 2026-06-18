from concurrent.futures import ThreadPoolExecutor
import warnings

from agent import runtime_env


def test_canonical_value_wins_even_when_empty(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_API_KEY", "")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_API_KEY", "legacy-secret")

    assert (
        runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_API_KEY",
            "DEEP_SEARCH_AGENT_API_KEY",
        )
        == ""
    )


def test_canonical_value_warns_when_legacy_key_is_also_present(monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_URL", "https://canonical.invalid")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL",
            "DEEP_SEARCH_AGENT_URL",
        )

    assert value == "https://canonical.invalid"
    assert len(caught) == 1
    assert "ignored" in str(caught[0].message)
    assert "canonical.invalid" not in str(caught[0].message)
    assert "legacy.invalid" not in str(caught[0].message)


def test_legacy_value_warns_once_without_value(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL",
            "DEEP_SEARCH_AGENT_URL",
        )
        second = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL",
            "DEEP_SEARCH_AGENT_URL",
        )

    assert first == second == "https://legacy.example.invalid"
    assert len(caught) == 1
    assert "DEEP_SEARCH_AGENT_URL" in str(caught[0].message)
    assert "DECISION_RESEARCH_AGENT_URL" in str(caught[0].message)
    assert "legacy.example.invalid" not in str(caught[0].message)


def test_missing_keys_return_default_without_warning(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.delenv("DEEP_SEARCH_AGENT_URL", raising=False)
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = runtime_env.resolve_env(
            "DECISION_RESEARCH_AGENT_URL",
            "DEEP_SEARCH_AGENT_URL",
            default="http://127.0.0.1:8000",
        )

    assert value == "http://127.0.0.1:8000"
    assert caught == []


def test_warning_filter_cannot_break_legacy_resolution(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        assert (
            runtime_env.resolve_env(
                "DECISION_RESEARCH_AGENT_URL",
                "DEEP_SEARCH_AGENT_URL",
            )
            == "https://legacy.example.invalid"
        )


def test_concurrent_legacy_resolution_warns_once(monkeypatch):
    monkeypatch.delenv("DECISION_RESEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("DEEP_SEARCH_AGENT_URL", "https://legacy.example.invalid")
    runtime_env._reset_warning_state_for_tests()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(
                pool.map(
                    lambda _: runtime_env.resolve_env(
                        "DECISION_RESEARCH_AGENT_URL",
                        "DEEP_SEARCH_AGENT_URL",
                    ),
                    range(32),
                )
            )

    assert set(values) == {"https://legacy.example.invalid"}
    assert len(caught) == 1
