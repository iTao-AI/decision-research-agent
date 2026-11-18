"""Bad-case intake and provider-free findings quality evaluation."""
import copy
import json
from pathlib import Path

import pytest

from test_research_findings_consumer import package, rehash


def intake_arguments(tmp_path, delivery, *selection):
    path = tmp_path / "delivery.json"
    path.write_text(json.dumps(delivery), encoding="utf-8")
    return ["intake", "--delivery", str(path), "--reason", "Check the draft's scope",
            "--output", str(tmp_path / "suspect.json"), *selection]


def test_intake_preserves_the_report_identity_and_every_exact_reference(tmp_path):
    from scripts.findings_quality import main

    delivery = package()
    second = copy.deepcopy(delivery["report"]["findings"][0]["references"][0])
    second.update(excerpt="material", excerpt_start=13, excerpt_end=21)
    delivery["report"]["findings"][0]["references"].append(second)
    rehash(delivery)
    args = intake_arguments(tmp_path, delivery, "--question-id", "q1", "--finding-id", "f1",
                            "--expected-behavior", "Limit the statement to the source version.")
    assert main(args) == 0
    output = tmp_path / "suspect.json"
    first_bytes = output.read_bytes()
    case = json.loads(first_bytes)
    assert case["run_id"] == "run_fixture"
    assert case["report_hash"] == delivery["artifact"]["content_hash"]
    assert case["finding_id"] == "f1"
    assert case["statement"] == "Candidate"
    assert case["expected_behavior"] == "Limit the statement to the source version."
    assert [(ref["excerpt"], ref["excerpt_start"], ref["excerpt_end"]) for ref in case["references"]] == [
        ("observed", 4, 12), ("material", 13, 21)]
    assert all(ref["snippet"] == "A 🧪 observed material." for ref in case["references"])
    assert all(ref["evidence_id"].startswith("ev_run_fixture_") for ref in case["references"])
    assert main(args) == 0
    assert output.read_bytes() == first_bytes
    different = [item if item != "Check the draft's scope" else "Different observation" for item in args]
    assert main(different) == 1
    assert output.read_bytes() == first_bytes

    delivery["report"]["findings"][0]["statement"] = "Revised"
    rehash(delivery)
    (tmp_path / "delivery.json").write_text(json.dumps(delivery), encoding="utf-8")
    new_target = tmp_path / "revision.json"
    assert main([str(new_target) if item == str(output) else item for item in args]) == 0
    assert json.loads(new_target.read_bytes())["case_id"] != case["case_id"]


def test_intake_accepts_an_unresolved_question_without_a_finding(tmp_path):
    from scripts.findings_quality import main

    delivery = package()
    delivery["report"]["questions"].append({"question_id": "q2", "text": "What is the measured availability?"})
    delivery["report"]["dispositions"].append(
        {"question_id": "q2", "status": "unresolved", "reason": "The sources give no measurements."})
    rehash(delivery)
    assert main(intake_arguments(tmp_path, delivery, "--question-id", "q2")) == 0
    case = json.loads((tmp_path / "suspect.json").read_bytes())
    assert case["finding_id"] is None
    assert case["statement"] is None
    assert case["references"] == []
    assert case["disposition"]["reason"] == "The sources give no measurements."
    assert len(case["accepted_dispositions"]) == 2


@pytest.mark.parametrize("defect", ["artifact", "foreign_evidence", "missing_finding", "absent_question"])
def test_intake_rejects_invalid_delivery_or_selection(tmp_path, defect):
    from scripts.findings_quality import main

    delivery = package()
    selection = ["--question-id", "q1", "--finding-id", "f1"]
    if defect == "artifact":
        delivery["artifact"]["content_hash"] = "0" * 64
    elif defect == "foreign_evidence":
        delivery["evidence"][0]["run_id"] = "different-run"
    elif defect == "missing_finding":
        selection = ["--question-id", "q1"]
    else:
        selection = ["--question-id", "q2", "--finding-id", "f1"]
    assert main(intake_arguments(tmp_path, delivery, *selection)) == 1
    assert not (tmp_path / "suspect.json").exists()
