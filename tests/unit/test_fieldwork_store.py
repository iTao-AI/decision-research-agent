import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from fieldwork.service import FieldworkError, FieldworkService


PDF_A = b"%PDF-1.4\nfixture-a\n%%EOF\n"
PDF_B = b"%PDF-1.4\nfixture-b\n%%EOF\n"
HTML = b"<!doctype html><html lang='zh-CN'><head><title>V2</title></head><body>V2</body></html>"


class EvidenceBackend:
    """A deterministic external catalog. The real DRA ledger is exercised by every test."""

    def __init__(self, directory):
        self.directory = directory
        self.catalog = {}
        self.ingestions = []
        self.interrupt_after_ingest = False
        self.wait_on_ingest = None
        self.wrong_live_revision = False

    def ingest(self, path, digest):
        assert path == self.directory / "originals" / f"{digest}.pdf"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        if self.wait_on_ingest:
            entered, proceed = self.wait_on_ingest
            entered.set()
            assert proceed.wait(5)
        if digest not in self.catalog:
            self.ingestions.append(digest)
            self.catalog[digest] = {
                "source_id": f"source-{digest[:8]}",
                "publication_id": f"publication-{digest[:8]}",
                "producer_run_id": f"mke-{digest[:8]}",
                "revision": 1,
                "total_pages": 1,
            }
        if self.interrupt_after_ingest:
            raise KeyboardInterrupt
        return self.catalog[digest]

    def select(self, material, query, consumer_run_id):
        assert query
        assert material["total_pages"] == 1
        return [
            self.evidence(material, f"excerpt-{material['source_id']}", consumer_run_id),
            self.evidence(
                material,
                f"context-{material['source_id']}",
                consumer_run_id,
                text="客户 IT 负责授权。",
            ),
        ]

    def reread(self, material, evidence_id, consumer_run_id):
        evidence = self.evidence(material, evidence_id, consumer_run_id)
        if self.wrong_live_revision:
            evidence["revision"] = 2
        return evidence

    @staticmethod
    def evidence(material, evidence_id, consumer_run_id, text="样本可用于试点。"):
        raw = text.encode("utf-8")
        return {
            "id": evidence_id,
            "material_id": material["id"],
            "title": material["title"],
            "source_id": material["source_id"],
            "publication_id": material["publication_id"],
            "producer_run_id": material["producer_run_id"],
            "revision": material["revision"],
            "consumer_run_id": consumer_run_id,
            "page_start": 1,
            "page_end": 1,
            "text": text,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_start": 0,
            "byte_end": len(raw),
        }


def propose(project, evidence):
    return {
        "headline": "样本安排",
        "summary": "依据项目已确认约定和本次选段。",
        "items": [
            {
                "area": area,
                "state": "proceed",
                "priority": "normal",
                "owner": "试点负责人",
                "action": "核对展示顺序" if project["sample_prepared"] else "准备样本",
                "reason": "有本次项目资料。",
                "question": "",
                "evidence_ids": [evidence[0]["id"]],
            }
            for area in ("demo", "live_access", "interview")
        ],
        "usage": {"input_tokens": 8, "output_tokens": 4},
    }


@pytest.fixture
def workbench(tmp_path):
    backend = EvidenceBackend(tmp_path / "northstar")
    return FieldworkService(tmp_path, lambda _: backend, propose, "replay"), backend


def add_material(service):
    return service.submit_material("客户 IT 回函", PDF_A)["materials"][0]


def make_pending(service):
    material = add_material(service)
    return material, service.analyze(material["id"])["proposal"]


def test_confirm_once_and_restore_frozen_version_and_old_evidence_after_restart(tmp_path, workbench):
    service, backend = workbench
    original = service.project()
    assert original["stage"] == "现场调查"
    assert original["confirmed"]["version"] == 1
    assert len(original["confirmed"]["evidence"]) == 2

    material, proposal = make_pending(service)
    referenced = proposal["items"][0]["evidence_ids"][0]
    assert len(proposal["evidence"]) == 4
    assert service.live_evidence(proposal["id"], referenced)["status"] == "available"

    confirmed = service.review(proposal["id"], "accept", "")
    restarted = FieldworkService(tmp_path, lambda _: backend, propose, "replay")
    assert restarted.project() == confirmed
    assert restarted.review(proposal["id"], "accept", "") == confirmed
    assert restarted.export(1) == original["confirmed"]
    assert restarted.export(2) == confirmed["confirmed"]
    assert restarted.history()["confirmed"][0]["proposal_id"] == proposal["id"]

    backend.wrong_live_revision = True
    restarted.submit_material("客户 IT 回函", PDF_B, replace=material["id"])
    live = restarted.live_evidence(proposal["id"], referenced)
    assert live["status"] == "unavailable"
    assert live["frozen"]["text"] == "样本可用于试点。"
    assert restarted.proposal(proposal["id"])["evidence"] == proposal["evidence"]
    assert restarted.export(2) == confirmed["confirmed"]


def test_lost_intake_response_reconciles_catalog_and_advances_revision_once(tmp_path, workbench):
    service, backend = workbench
    material, proposal = make_pending(service)
    backend.interrupt_after_ingest = True
    with pytest.raises(KeyboardInterrupt):
        service.submit_material("客户 IT 回函", PDF_B, replace=material["id"])

    restarted = FieldworkService(tmp_path, lambda _: backend, propose, "replay")
    assert restarted.project()["materials"] == [material]
    assert restarted.project()["revision"] == 2
    with pytest.raises(FieldworkError, match="资料") as blocked:
        restarted.review(proposal["id"], "accept", "")
    assert blocked.value.status == 409
    assert restarted.project()["confirmed"]["version"] == 1

    backend.interrupt_after_ingest = False
    adopted = restarted.submit_material("客户 IT 回函", PDF_B, replace=material["id"])
    retry = restarted.submit_material("客户 IT 回函", PDF_B, replace=material["id"])
    assert retry == adopted
    assert sum(item["active"] for item in adopted["materials"]) == 1
    assert adopted["revision"] == 3
    assert len(backend.ingestions) == 2

    with pytest.raises(FieldworkError) as stale:
        restarted.review(proposal["id"], "accept", "")
    assert stale.value.code == "stale_proposal"
    assert restarted.proposal(proposal["id"])["status"] == "superseded"


def test_replacement_fences_acceptance_before_catalog_returns(workbench):
    service, backend = workbench
    material, proposal = make_pending(service)
    entered, proceed = threading.Event(), threading.Event()
    backend.wait_on_ingest = entered, proceed
    with ThreadPoolExecutor() as workers:
        changing = workers.submit(service.submit_material, "客户 IT 回函", PDF_B, material["id"])
        assert entered.wait(5)
        try:
            with pytest.raises(FieldworkError) as blocked:
                service.review(proposal["id"], "accept", "")
            assert blocked.value.status == 409
            assert service.project()["confirmed"]["version"] == 1
        finally:
            proceed.set()
        assert changing.result(timeout=5)["proposal"]["status"] == "superseded"


def test_return_is_idempotent_preserves_feedback_and_cannot_be_overwritten(workbench):
    service, _ = workbench
    _, proposal = make_pending(service)
    returned = service.review(proposal["id"], "return", "请核实批准范围。")

    assert returned["proposal"]["status"] == "returned"
    assert returned["proposal"]["feedback"] == "请核实批准范围。"
    assert returned["confirmed"]["version"] == 1
    assert service.review(proposal["id"], "return", "请核实批准范围。") == returned
    with pytest.raises(FieldworkError) as conflict:
        service.review(proposal["id"], "accept", "")
    assert conflict.value.status == 409


def test_recorded_sample_progress_changes_actual_model_input_and_invalidates_old_draft(workbench):
    service, _ = workbench
    material, proposal = make_pending(service)
    original_revision = proposal["basis_revision"]
    progress = service.progress(True)
    assert progress["sample_prepared"]
    assert service.progress(True)["revision"] == original_revision + 1
    assert progress["proposal"]["status"] == "superseded"

    new_proposal = service.analyze(material["id"])["proposal"]
    assert new_proposal["items"][0]["action"] == "核对展示顺序"
    assert new_proposal["basis_revision"] == original_revision + 1
    assert proposal["items"][0]["action"] == "准备样本"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda draft: draft["items"][0].update(evidence_ids=["other-run-passage"]), "invalid_reference"),
        (lambda draft: draft["items"][0].update(evidence_ids=[]), "invalid_reference"),
        (lambda draft: draft["items"][0].update(state="approved"), "invalid_proposal"),
        (lambda draft: draft["items"].pop(), "invalid_proposal"),
    ],
)
def test_failed_analysis_keeps_current_plan_and_persists_inputs_without_public_proposal(
    tmp_path, change, code
):
    backend = EvidenceBackend(tmp_path / "northstar")

    def invalid(project, evidence):
        draft = propose(project, evidence)
        change(draft)
        return draft

    service = FieldworkService(tmp_path, lambda _: backend, invalid, "replay")
    material = add_material(service)
    with pytest.raises(FieldworkError) as invalid_output:
        service.analyze(material["id"])
    assert invalid_output.value.code == code
    assert service.project()["proposal"] is None
    assert service.project()["confirmed"]["version"] == 1

    with sqlite3.connect(tmp_path / "northstar" / "fieldwork.sqlite3") as db:
        run = db.execute("SELECT status, error_code, input_json, output_json FROM analysis_runs").fetchone()
    assert run[0:2] == ("failed", code)
    assert "样本可用于试点。" in run[2]
    assert "样本安排" in run[3]


def test_registered_html_is_version_bound_immutable_and_restored(tmp_path, workbench):
    from fieldwork.artifact import snapshot_fingerprint

    service, backend = workbench
    _, proposal = make_pending(service)
    service.review(proposal["id"], "accept", "")
    snapshot_digest = snapshot_fingerprint(service.export(2))
    markup = HTML.replace(
        b"</head>", f'<meta name="fieldwork-snapshot-sha256" content="{snapshot_digest}"></head>'.encode()
    )
    metadata = service.register_html(2, markup)
    assert metadata == {"version": 2, "sha256": hashlib.sha256(markup).hexdigest()}
    assert service.register_html(2, markup) == metadata
    assert service.project()["deliverables"] == [metadata]
    with pytest.raises(FieldworkError) as conflict:
        service.register_html(2, markup.replace(b"V2", b"other"))
    assert conflict.value.status == 409
    for invalid in (HTML, markup):
        with pytest.raises(FieldworkError) as rejected:
            service.register_html(1, invalid)
        assert rejected.value.code == "invalid_html"
    restored = FieldworkService(tmp_path, lambda _: backend, propose, "replay")
    assert restored.html(2) == markup
    with pytest.raises(FieldworkError):
        restored.html(1)


def test_provider_failure_preserves_bounded_receipt_without_exposing_it(workbench):
    from fieldwork.analysis import ModelFailure

    service, _ = workbench
    material = add_material(service)
    receipt = {
        "finish_reason": "length",
        "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
        "request_sha256": "a" * 64,
        "raw_text": '{"headline":"未完成稿',
    }

    def truncated(project, evidence):
        raise ModelFailure("model_incomplete", receipt)

    service.analyzer = truncated
    with pytest.raises(FieldworkError) as failure:
        service.analyze(material["id"])
    assert failure.value.code == "model_incomplete"
    assert "未完成稿" not in failure.value.message
    assert service.project()["proposal"] is None
    with service.store.connect() as db:
        run = db.execute("SELECT status, error_code, output_json FROM analysis_runs").fetchone()
    assert tuple(run)[:2] == ("failed", "model_incomplete")
    assert json.loads(run["output_json"]) == receipt


def test_incomplete_evidence_preserves_prior_view_and_explains_why(workbench):
    from fieldwork.mke import MkeError

    service, backend = workbench
    material, _ = make_pending(service)
    before = service.project()

    def incomplete(*args):
        raise MkeError("mke_incomplete_coverage")

    backend.select = incomplete
    with pytest.raises(FieldworkError) as rejected:
        service.analyze(material["id"])
    assert rejected.value.code == "mke_incomplete_coverage"
    assert "读取不完整" in rejected.value.message
    assert service.project() == before


def test_admitted_intake_retries_remain_idempotent_after_a_newer_replacement(workbench):
    service, backend = workbench
    first = add_material(service)
    second = service.submit_material("客户 IT 回函", PDF_B, replace=first["id"])["materials"][0]
    latest = service.submit_material("客户 IT 回函", b"%PDF-1.4\\nThird revision", replace=second["id"])

    assert service.submit_material("客户 IT 回函", PDF_A) == latest
    assert service.submit_material("客户 IT 回函", PDF_B, replace=first["id"]) == latest
    assert len(backend.ingestions) == 3


def test_material_versions_are_independent_of_mke_revisions_and_remain_frozen(workbench):
    service, _ = workbench
    first, old_proposal = make_pending(service)
    service.review(old_proposal["id"], "accept", "")
    replacement = service.submit_material("客户 IT 回函", PDF_B, replace=first["id"])
    active, retired = replacement["materials"]
    current = service.analyze(active["id"])["proposal"]
    archive = service.export(2)
    old_ref = archive["evidence"][0]
    current_ref = current["evidence"][0]

    assert (active["material_version"], retired["material_version"]) == (2, 1)
    assert (active["revision"], retired["revision"]) == (1, 1)
    assert (current_ref["source_id"], old_ref["source_id"]) == (active["source_id"], retired["source_id"])
    assert (current_ref["material_version"], old_ref["material_version"]) == (2, 1)
    assert (current_ref["revision"], old_ref["revision"]) == (1, 1)
    reread = service.live_evidence(old_proposal["id"], old_ref["id"])
    assert reread["status"] == "available"
    assert reread["current"] == old_ref


def test_frozen_reference_before_material_versions_remains_live_readable(workbench):
    service, _ = workbench
    _, proposal = make_pending(service)
    legacy = [{key: value for key, value in item.items() if key != "material_version"} for item in proposal["evidence"]]
    with service.store.connect(write=True) as db:
        db.execute("UPDATE proposals SET evidence = ? WHERE id = ?", (json.dumps(legacy), proposal["id"]))

    original = legacy[0]
    reread = service.live_evidence(proposal["id"], original["id"])
    assert reread == {"status": "available", "frozen": original, "current": original}


def test_state_root_alias_resolves_to_same_archived_path_as_mke(tmp_path):
    from fieldwork.mke import MkeEvidence

    class PublishedEvidence(MkeEvidence):
        def _published(self, digest, lock_fd):
            return {
                "source_id": "source",
                "publication_id": "publication",
                "producer_run_id": "producer",
                "revision": 1,
                "total_pages": 1,
            }

    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)
    service = FieldworkService(alias, lambda path: PublishedEvidence("/unused", path), propose, "replay")

    material = add_material(service)
    assert material["source_id"] == "source"
    assert (physical / "northstar" / "originals" / f"{material['sha256']}.pdf").read_bytes() == PDF_A


def test_restart_reconciles_interrupted_model_run_without_retrying_it(tmp_path, workbench):
    service, backend = workbench

    def interrupted(project, evidence):
        raise KeyboardInterrupt

    service.analyzer = interrupted
    material = add_material(service)
    with pytest.raises(KeyboardInterrupt):
        service.analyze(material["id"])

    restored = FieldworkService(tmp_path, lambda _: backend, propose, "replay")
    assert restored.project()["proposal"] is None
    assert restored.project()["confirmed"]["version"] == 1
    with restored.store.connect() as db:
        run = db.execute("SELECT status, error_code, input_json FROM analysis_runs").fetchone()
    assert tuple(run)[:2] == ("failed", "analysis_interrupted")
    assert "样本可用于试点。" in run["input_json"]


def test_fenced_analysis_does_not_hide_earlier_pending_proposal_when_intake_fails(tmp_path, workbench):
    service, backend = workbench
    previous_material, previous_proposal = make_pending(service)
    generating, finish_analysis = threading.Event(), threading.Event()
    ingesting, fail_intake = threading.Event(), threading.Event()

    def analyzer(project, evidence):
        generating.set()
        assert finish_analysis.wait(5)
        return propose(project, evidence)

    def broken_ingest(path, digest):
        ingesting.set()
        assert fail_intake.wait(5)
        raise OSError("ingestion failed")

    service.analyzer = analyzer
    backend.ingest = broken_ingest
    with ThreadPoolExecutor() as workers:
        analysis = workers.submit(service.analyze, previous_material["id"])
        try:
            assert generating.wait(5)
            observer = FieldworkService(tmp_path, lambda _: backend, propose, "replay")
            with observer.store.connect() as db:
                status = db.execute("SELECT status FROM analysis_runs ORDER BY rowid DESC LIMIT 1").fetchone()[0]
            assert status == "generating"
            intake = workers.submit(service.submit_material, "客户 IT 回函", PDF_B, previous_material["id"])
            assert ingesting.wait(5)
            finish_analysis.set()
            with pytest.raises(FieldworkError) as rejected:
                analysis.result(timeout=5)
            assert rejected.value.code == "stale_proposal"
        finally:
            finish_analysis.set()
            fail_intake.set()
        with pytest.raises(FieldworkError) as failed:
            intake.result(timeout=5)
        assert failed.value.code == "intake_failed"

    assert service.project()["proposal"] == previous_proposal
    assert len(service.history()["proposals"]) == 1
    with service.store.connect() as db:
        run = db.execute("SELECT status, error_code, output_json FROM analysis_runs ORDER BY rowid DESC LIMIT 1").fetchone()
    assert tuple(run)[:2] == ("failed", "stale_proposal")
    assert "样本安排" in run["output_json"]
    assert service.review(previous_proposal["id"], "accept", "")["confirmed"]["version"] == 2
