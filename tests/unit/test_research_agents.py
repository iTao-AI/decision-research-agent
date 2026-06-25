def test_generic_researchers_use_only_role_tools(monkeypatch):
    import agent.research_agents as research_agents

    captured = {}

    class FakeRunnable:
        pass

    def capture_create_agent(**kwargs):
        result = FakeRunnable()
        kwargs["_result"] = result
        captured[kwargs["name"]] = kwargs
        return result

    monkeypatch.setattr(research_agents, "create_agent", capture_create_agent)

    compiled = research_agents.compile_generic_researchers(model=object())

    assert set(compiled) == {
        "network_search",
        "database_query",
        "knowledge_base",
    }
    assert {
        tool.name for tool in captured["network_search"]["tools"]
    } == {"internet_search"}
    assert {
        tool.name for tool in captured["database_query"]["tools"]
    } == {"list_sql_tables", "get_table_data", "execute_sql_query"}
    assert {
        tool.name for tool in captured["knowledge_base"]["tools"]
    } == {"get_assistant_list", "create_ask_delete"}
    assert all(
        spec["runnable"] is captured[name]["_result"]
        for name, spec in compiled.items()
    )
