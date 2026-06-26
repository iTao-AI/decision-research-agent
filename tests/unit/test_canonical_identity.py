from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_active_surface_uses_canonical_identity():
    from scripts.check_canonical_identity import find_forbidden_terms

    assert find_forbidden_terms(ROOT) == []


def test_canonical_identity_check_ignores_local_only_paths(tmp_path):
    from scripts.check_canonical_identity import find_forbidden_terms

    local_files = [
        tmp_path / ".env",
        tmp_path / ".agents" / "notes.md",
        tmp_path / ".gstack" / "qa.md",
        tmp_path / ".worktrees" / "old" / "README.md",
    ]
    for path in local_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("deep-search-agent\n", encoding="utf-8")

    (tmp_path / "README.md").write_text("Decision Research Agent\n", encoding="utf-8")

    assert find_forbidden_terms(tmp_path) == []


def test_canonical_identity_check_still_scans_active_public_files(tmp_path):
    from scripts.check_canonical_identity import find_forbidden_terms

    (tmp_path / "README.md").write_text("deep-search-agent\n", encoding="utf-8")

    assert find_forbidden_terms(tmp_path) == [
        {"path": "README.md", "line": 1, "term": "deep-search-agent"}
    ]


def test_health_service_uses_canonical_identifier():
    from fastapi.testclient import TestClient
    from api.server import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "decision-research-agent",
    }
