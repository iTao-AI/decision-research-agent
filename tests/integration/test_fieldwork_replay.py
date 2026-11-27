"""Black-box service checks against the frozen, fictional provider input."""

from pathlib import Path

from fastapi.testclient import TestClient

from fieldwork.web import create_app

PATH = "/api/fieldwork/projects/northstar"
FIXTURES = Path(__file__).resolve().parents[2] / "examples" / "fieldwork"


def client(root):
    return TestClient(create_app(root), base_url="http://127.0.0.1:7195")


def put_pdf(browser, case, replace=None):
    file = FIXTURES / case / "试点安排确认函.pdf"
    params = {"title": file.stem}
    if replace:
        params["replace"] = replace
    response = browser.post(PATH + "/materials", params=params, content=file.read_bytes(),
                            headers={"Content-Type": "application/pdf"})
    assert response.status_code == 200, response.text
    return response.json()


def analyze(browser, project):
    active, = [row for row in project["materials"] if row["active"]]
    response = browser.post(PATH + "/analysis", json={"material_id": active["id"]})
    assert response.status_code == 200, response.text
    proposal = response.json()["proposal"]
    assert proposal["id"]
    assert all(item["evidence_ids"] for item in proposal["items"])
    return proposal


def decisions(proposal):
    return {item["area"]: item for item in proposal["items"]}


def accept(browser, proposal):
    return browser.post(PATH + "/review", json={"proposal_id": proposal["id"], "decision": "accept"})


def test_offline_all_cases_and_stale_review(tmp_path):
    browser = client(tmp_path)
    a = put_pdf(browser, "A")
    a1 = analyze(browser, a)
    assert decisions(a1)["demo"]["action"] == "准备脱敏演示样本"
    assert decisions(a1)["live_access"]["state"] == "waiting"
    assert decisions(a1)["interview"]["state"] == "proceed"
    original, = a["materials"]
    b = put_pdf(browser, "B", original["id"])
    assert accept(browser, a1).status_code == 409
    old = browser.get(PATH + "/proposals/" + a1["id"]).json()
    assert any("周三客户演示" in item["text"] for item in old["evidence"])
    b1 = analyze(browser, b)
    assert decisions(b1)["demo"]["action"] == "安排团队内部排练"
    assert "另行书面授权" in decisions(b1)["demo"]["reason"]
    assert decisions(b1)["interview"]["state"] == "proceed"
    current, = [row for row in b["materials"] if row["active"]]
    c1 = analyze(browser, put_pdf(browser, "C", current["id"]))
    assert decisions(c1)["demo"]["state"] == "waiting"
    assert decisions(c1)["demo"]["owner"] == "客户 IT"
    assert "适用对象和数据范围" in decisions(c1)["demo"]["question"]
    assert browser.get(PATH).json()["confirmed"]["version"] == 1


def test_progress_changes_action_and_approval_restart_export(tmp_path):
    browser = client(tmp_path)
    change = put_pdf(browser, "A")
    first = analyze(browser, change)
    progress = browser.post(PATH + "/progress", json={"sample_prepared": True})
    assert progress.status_code == 200, progress.text
    assert accept(browser, first).status_code == 409
    ready = analyze(browser, progress.json())
    assert decisions(ready)["demo"]["action"] == "走查周三演示流程"
    assert accept(browser, ready).json()["confirmed"]["version"] == 2
    restarted = client(tmp_path)
    project = restarted.get(PATH).json()
    assert project["stage"] == "现场调查" and project["sample_prepared"]
    assert accept(restarted, ready).json()["confirmed"]["version"] == 2
    assert restarted.get(PATH + "/exports/2.json").json()["headline"] == project["confirmed"]["headline"]
    markdown = restarted.get(PATH + "/exports/2.md")
    assert "走查周三演示流程" in markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")
