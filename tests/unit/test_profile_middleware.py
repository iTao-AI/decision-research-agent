from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from agent.profile_middleware import (
    build_profile_middleware,
    middleware_contract,
)


def _canonical_completion_middleware():
    middleware = build_profile_middleware("generic", role="coordinator")
    candidates = [
        item
        for item in middleware
        if type(item).__name__ == "CanonicalReportCompletionMiddleware"
    ]
    assert len(candidates) == 1
    return candidates[0]


def test_generic_coordinator_limits_are_fail_closed():
    middleware = build_profile_middleware("generic", role="coordinator")

    assert middleware_contract(middleware) == {
        "model_run_limit": 40,
        "global_tool_run_limit": 40,
        "task_run_limit": 8,
        "exit_behavior": "error",
    }


def test_canonical_completion_requests_one_framework_reentry_when_report_is_missing():
    middleware = _canonical_completion_middleware()

    update = middleware.after_model(
        {"messages": [AIMessage(content="Finished without a file.")]},
        Runtime(),
    )

    assert update["canonical_report_correction_count"] == 1
    assert update["jump_to"] == "model"
    assert len(update["messages"]) == 1
    assert isinstance(update["messages"][0], HumanMessage)
    assert "/workspace/research-report.md" in update["messages"][0].content


def test_canonical_completion_does_not_reenter_when_report_exists():
    middleware = _canonical_completion_middleware()

    update = middleware.after_model(
        {
            "messages": [AIMessage(content="Finished.")],
            "files": {
                "/workspace/research-report.md": {
                    "content": "# Canonical report\n",
                }
            },
        },
        Runtime(),
    )

    assert update is None


def test_canonical_completion_does_not_interrupt_a_tool_request():
    middleware = _canonical_completion_middleware()

    update = middleware.after_model(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "/workspace/research-report.md",
                                "content": "# Canonical report\n",
                            },
                            "id": "call-write",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        Runtime(),
    )

    assert update is None


def test_canonical_completion_never_reenters_twice():
    middleware = _canonical_completion_middleware()

    update = middleware.after_model(
        {
            "messages": [AIMessage(content="Still no file.")],
            "canonical_report_correction_count": 1,
        },
        Runtime(),
    )

    assert update is None


def test_generic_researcher_limits_are_fail_closed():
    for role in ("network_search", "database_query", "knowledge_base"):
        middleware = build_profile_middleware("generic", role=role)
        assert middleware_contract(middleware) == {
            "model_run_limit": 20,
            "global_tool_run_limit": 12,
            "task_run_limit": None,
            "exit_behavior": "error",
        }


def test_talent_researcher_has_only_model_budget():
    middleware = build_profile_middleware(
        "talent-hiring-signal",
        role="researcher",
    )

    assert middleware_contract(middleware) == {
        "model_run_limit": 12,
        "global_tool_run_limit": None,
        "task_run_limit": None,
        "exit_behavior": "error",
    }
