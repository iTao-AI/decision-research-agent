from agent.profile_middleware import (
    build_profile_middleware,
    middleware_contract,
)


def test_generic_coordinator_limits_are_fail_closed():
    middleware = build_profile_middleware("generic", role="coordinator")

    assert middleware_contract(middleware) == {
        "model_run_limit": 40,
        "global_tool_run_limit": 40,
        "task_run_limit": 8,
        "exit_behavior": "error",
    }


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
