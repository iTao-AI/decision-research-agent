import json
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.research_findings_consumer import validate_delivery


DATASET = Path(__file__).resolve().parents[2] / "benchmarks" / "findings-quality-v1"


@pytest.fixture
def cases():
    return _read_dataset("cases.json")


@pytest.fixture
def annotations():
    return _read_dataset("annotations.json")


def _read_dataset(filename):
    path = DATASET / filename
    if not path.is_file():
        pytest.fail(f"Missing frozen corpus file: {filename}")
    return json.loads(path.read_text(encoding="utf-8"))


def test_corpus_supplies_the_planned_range_of_frozen_cases():
    cases = _read_dataset("cases.json")
    ids = [case["case_id"] for case in cases]
    assert 16 <= len(ids) <= 20
    assert ids == sorted(set(ids))
    assert 4 <= len({case["family"] for case in cases}) <= 6
    assert {case["split"] for case in cases} == {"development", "holdout"}
    assert all(case["statement"] for case in cases)


def test_family_and_source_groups_never_cross_splits(cases):
    families = defaultdict(set)
    sources = defaultdict(set)
    for case in cases:
        families[case["family"]].add(case["split"])
        for reference in case["references"]:
            owner = reference["source_identity"].split("/blob/", 1)[0]
            sources[owner].add(case["split"])

    assert all(len(splits) == 1 for splits in families.values())
    assert all(len(splits) == 1 for splits in sources.values())


def test_every_cited_span_replays_except_the_declared_structural_case(cases, annotations):
    structurally_invalid = {
        annotation["case_id"]
        for annotation in annotations
        if annotation["authority"] == "deterministic_structural"
        and annotation["verdict"] is None
    }
    mismatches = {
        case["case_id"]
        for case in cases
        for reference in case["references"]
        if reference["snippet"][reference["excerpt_start"] : reference["excerpt_end"]]
        != reference["excerpt"]
    }

    assert mismatches == structurally_invalid == {"delivery-owner-broken-reference"}


def test_inverted_pilot_controls_have_the_same_sources_and_question_as_their_controls(cases):
    by_id = {case["case_id"]: case for case in cases}

    for inverted_id, normal_id in (
        ("control-entailment-flip", "binding-support-limit"),
        ("control-human-value", "human-value-supported"),
    ):
        inverted = by_id[inverted_id]
        normal = by_id[normal_id]
        assert inverted["question"] == normal["question"]
        assert inverted["references"] == normal["references"]
        assert inverted["statement"] != normal["statement"]
        assert inverted["split"] == normal["split"] == "development"
        assert inverted["origin"] == normal["origin"] == "synthetic_control"


def test_blind_review_pool_keeps_unreviewed_rows_out_of_human_calibration(cases, annotations):
    assert [annotation["case_id"] for annotation in annotations] == [
        case["case_id"] for case in cases
    ]
    review_candidates = [annotation for annotation in annotations if annotation["blind_review"]]
    assert 6 <= len(review_candidates) <= 8
    assert {annotation["verdict"] for annotation in review_candidates} == {
        "supported",
        "contradicted",
        "insufficient_evidence",
        "conflicting_evidence",
    }
    assert {annotation["authority"] for annotation in annotations} <= {
        "synthetic_expectation", "deterministic_structural"
    }
    assert all(
        annotation["reviewer"] is None and annotation["review_date"] is None
        for annotation in annotations
    )


def test_historical_pointers_have_neither_primary_reports_nor_replay_case_ids(cases):
    history = _read_dataset("historical.json")
    case_ids = {case["case_id"] for case in cases}

    assert history
    assert all(row["date"] and row["diagnosis"]["locator"] for row in history)
    assert all(row["origin"] == "historical_review" for row in history)
    assert all(row["primary_artifact_available"] is False for row in history)
    assert case_ids.isdisjoint(row["case_id"] for row in history)


def test_demo_delivery_preserves_the_synthetic_control(cases):
    demo = _read_dataset("demo-delivery.json")
    receipt = validate_delivery(demo, demo["run_id"])
    case = next(case for case in cases if case["case_id"] == "control-entailment-flip")
    finding = demo["report"]["findings"][0]
    assert demo["provenance"]["origin"] == "synthetic_control"
    assert demo["report"]["questions"] == [case["question"]]
    assert finding["statement"] == case["statement"]
    assert len(finding["references"]) == len(case["references"])
    for bound, frozen in zip(finding["references"], case["references"], strict=True):
        assert all(bound[key] == value for key, value in frozen.items() if key != "source_version")
    assert receipt["references"][0]["verification_status"] == "unverified"
