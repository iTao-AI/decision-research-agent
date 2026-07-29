def test_database_path_uses_canonical_env(monkeypatch, tmp_path):
    from api.database import application_db_path

    canonical = tmp_path / "decision_research_agent.db"
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(canonical))

    assert application_db_path() == canonical.resolve()


def test_database_path_defaults_to_canonical_data_file(monkeypatch):
    from api.database import application_db_path

    monkeypatch.delenv("DECISION_RESEARCH_AGENT_DB_PATH", raising=False)

    path = application_db_path()

    assert path.name == "decision_research_agent.db"
    assert path.parent.name == "data"


def test_pure_database_path_resolution_does_not_create_missing_parent(tmp_path):
    from api.database import application_db_path

    path = tmp_path / "missing" / "nested" / "runs.db"
    assert application_db_path(path) == path.resolve()
    assert not path.parent.exists()
