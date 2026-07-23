import pytest
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.middleware.tool_call_limit import (
    ToolCallLimitExceededError,
)
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


def _generic_researcher_tool_middleware():
    middleware = build_profile_middleware("generic", role="network_search")
    candidates = [
        item
        for item in middleware
        if isinstance(item, ToolCallLimitMiddleware) and item.tool_name is None
    ]
    assert len(candidates) == 1
    return candidates[0]


def _network_search_named_tool_middleware():
    middleware = build_profile_middleware("generic", role="network_search")
    candidates = [
        item
        for item in middleware
        if isinstance(item, ToolCallLimitMiddleware)
        and item.tool_name == "internet_search"
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
        "named_tool_limits": {},
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


def test_network_search_has_soft_named_cap_and_hard_global_ceiling():
    middleware = build_profile_middleware("generic", role="network_search")

    assert middleware_contract(middleware) == {
        "model_run_limit": 20,
        "global_tool_run_limit": 16,
        "task_run_limit": None,
        "exit_behavior": "error",
        "named_tool_limits": {
            "internet_search": {
                "run_limit": 5,
                "exit_behavior": "continue",
            }
        },
    }
    assert [
        (
            type(item).__name__,
            getattr(item, "tool_name", None),
            item.run_limit,
            item.exit_behavior,
        )
        for item in middleware
    ] == [
        ("ModelCallLimitMiddleware", None, 20, "error"),
        ("ToolCallLimitMiddleware", None, 16, "error"),
        ("ToolCallLimitMiddleware", "internet_search", 5, "continue"),
    ]


def test_database_and_knowledge_researchers_keep_only_hard_global_ceiling():
    for role in ("database_query", "knowledge_base"):
        middleware = build_profile_middleware("generic", role=role)

        assert middleware_contract(middleware) == {
            "model_run_limit": 20,
            "global_tool_run_limit": 16,
            "task_run_limit": None,
            "exit_behavior": "error",
            "named_tool_limits": {},
        }


def test_network_search_named_cap_injects_bounded_feedback_after_five_calls():
    middleware = _network_search_named_tool_middleware()
    call = {
        "name": "internet_search",
        "args": {"query": "bounded"},
        "id": "call-6",
        "type": "tool_call",
    }

    update = middleware.after_model(
        {
            "messages": [AIMessage(content="", tool_calls=[call])],
            "thread_tool_call_count": {"internet_search": 5},
            "run_tool_call_count": {"internet_search": 5},
        },
        Runtime(),
    )

    assert update["thread_tool_call_count"] == {"internet_search": 5}
    assert update["run_tool_call_count"] == {"internet_search": 6}
    assert len(update["messages"]) == 1
    feedback = update["messages"][0]
    assert feedback.tool_call_id == "call-6"
    assert feedback.name == "internet_search"
    assert feedback.status == "error"
    assert feedback.content == (
        "Tool call limit exceeded. Do not call 'internet_search' again."
    )


def test_generic_researcher_allows_two_parallel_calls_from_12_to_14():
    middleware = _generic_researcher_tool_middleware()
    calls = [
        {
            "name": "internet_search",
            "args": {"query": f"bounded-{index}"},
            "id": f"call-{index}",
            "type": "tool_call",
        }
        for index in range(2)
    ]

    update = middleware.after_model(
        {
            "messages": [AIMessage(content="", tool_calls=calls)],
            "thread_tool_call_count": {"__all__": 12},
            "run_tool_call_count": {"__all__": 12},
        },
        Runtime(),
    )

    assert update == {
        "thread_tool_call_count": {"__all__": 14},
        "run_tool_call_count": {"__all__": 14},
    }


def test_generic_researcher_blocks_two_parallel_calls_after_16():
    middleware = _generic_researcher_tool_middleware()
    calls = [
        {
            "name": "internet_search",
            "args": {"query": f"bounded-{index}"},
            "id": f"call-{index}",
            "type": "tool_call",
        }
        for index in range(2)
    ]

    with pytest.raises(ToolCallLimitExceededError) as raised:
        middleware.after_model(
            {
                "messages": [AIMessage(content="", tool_calls=calls)],
                "thread_tool_call_count": {"__all__": 16},
                "run_tool_call_count": {"__all__": 16},
            },
            Runtime(),
        )

    assert raised.value.tool_name is None
    assert raised.value.run_limit == 16
    assert raised.value.run_count == 18
    assert raised.value.thread_limit is None
    assert raised.value.thread_count == 18


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
        "named_tool_limits": {},
    }
