"""Authoritative intake, analysis, human review and export for Fieldwork."""

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol
from uuid import uuid4

from .analysis import ModelFailure
from .artifact import validate_offline_html
from .mke import MkeError
from .store import PROJECT_ID, FieldworkStore, json_text, material_view, proposal_view, seed_evidence


MAX_PDF_BYTES = 8 * 1024 * 1024
_AREAS = {"demo", "live_access", "interview"}
_KNOWN_PROVENANCE = {"source_id", "publication_id", "revision", "producer_run_id", "total_pages"}
_EVIDENCE_FIELDS = {
    "id", "material_id", "title", "source_id", "publication_id", "revision",
    "producer_run_id", "consumer_run_id", "page_start", "page_end", "text",
    "sha256", "byte_start", "byte_end",
}
_ITEM_FIELDS = {"area", "state", "priority", "action", "owner", "reason", "question", "evidence_ids"}
_DRAFT_FIELDS = {"headline", "summary", "items"}
_OUTCOME_FIELDS = _DRAFT_FIELDS | {"model", "usage"}


class FieldworkError(Exception):
    def __init__(self, code, message, status):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class EvidenceBackend(Protocol):
    def ingest(self, path: Path, sha256: str) -> dict: ...
    def select(self, material: dict, query: str, consumer_run_id: str) -> list[dict]: ...
    def reread(self, material: dict, evidence_id: str, consumer_run_id: str) -> dict: ...


def _missing(resource):
    return FieldworkError(f"{resource}_not_found", "未找到该记录。", 404)


def _intake_pending():
    return FieldworkError("intake_pending", "有资料尚未完成登记。请用原文件重试登记。", 409)


def _stale_proposal():
    return FieldworkError("stale_proposal", "适用资料或项目安排已变化。请重新分析后再确认。", 409)


def _invalid_proposal():
    return FieldworkError("invalid_proposal", "建议的结构不完整。请重新分析。", 422)


def _mke_error(cause, *, message):
    if cause.code == "mke_incomplete_coverage":
        message = "资料读取不完整。已有确认版本仍可查阅，请重试。"
    return FieldworkError(cause.code, message, 502)


def _text(value, *, minimum=1, maximum=2000):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validate_draft(output, evidence):
    if not isinstance(output, dict) or not _DRAFT_FIELDS <= output.keys() <= _OUTCOME_FIELDS:
        raise _invalid_proposal()
    if not _text(output["headline"], maximum=200) or not _text(output["summary"]):
        raise _invalid_proposal()
    items = output["items"]
    if not isinstance(items, list) or len(items) != len(_AREAS):
        raise _invalid_proposal()
    available = {item["id"] for item in evidence}
    areas = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != _ITEM_FIELDS:
            raise _invalid_proposal()
        area, state, priority = item["area"], item["state"], item["priority"]
        if area not in ("demo", "live_access", "interview") or area in areas:
            raise _invalid_proposal()
        areas.add(area)
        if state not in ("proceed", "waiting") or priority not in ("high", "normal"):
            raise _invalid_proposal()
        if any(not _text(item[key]) for key in ("action", "owner", "reason")):
            raise _invalid_proposal()
        if not _text(item["question"], minimum=int(state == "waiting")):
            raise _invalid_proposal()
        references = item["evidence_ids"]
        if (
            not isinstance(references, list)
            or not references
            or len(references) > len(available)
            or any(not isinstance(ref, str) or ref not in available for ref in references)
            or len(set(references)) != len(references)
        ):
            raise FieldworkError("invalid_reference", "建议使用了缺失或不属于本次分析的引用。", 422)
    return {key: output[key] for key in ("headline", "summary", "items")}


def _provenance(value):
    if not isinstance(value, dict) or not _KNOWN_PROVENANCE <= value.keys():
        raise FieldworkError("catalog_mismatch", "资料登记回执不完整。", 502)
    for key in ("source_id", "publication_id", "producer_run_id"):
        if not _text(value[key], maximum=256):
            raise FieldworkError("catalog_mismatch", "资料登记回执不完整。", 502)
    for key in ("revision", "total_pages"):
        if type(value[key]) is not int or value[key] < 1:
            raise FieldworkError("catalog_mismatch", "资料登记回执不完整。", 502)
    return {key: value[key] for key in sorted(_KNOWN_PROVENANCE)}


def _checked_evidence(item, material, run_id):
    mismatch = FieldworkError("evidence_mismatch", "资料回读与本次登记的来源或原句不一致。", 502)
    if not isinstance(item, dict) or not _EVIDENCE_FIELDS <= item.keys():
        raise mismatch
    expected = {
        "material_id": material["id"],
        "title": material["title"],
        "consumer_run_id": run_id,
        **{key: material[key] for key in ("source_id", "publication_id", "revision", "producer_run_id")},
    }
    if any(item[key] != value for key, value in expected.items()):
        raise mismatch
    if not _text(item["id"], maximum=256) or not _text(item["text"], maximum=32_768):
        raise mismatch
    if any(type(item[key]) is not int for key in ("revision", "page_start", "page_end", "byte_start", "byte_end")):
        raise mismatch
    raw = item["text"].encode("utf-8")
    if (
        not 1 <= item["page_start"] <= item["page_end"] <= material["total_pages"]
        or item["byte_start"] < 0
        or item["byte_end"] - item["byte_start"] != len(raw)
        or sha256(raw).hexdigest() != item["sha256"]
    ):
        raise mismatch
    return {key: item[key] for key in sorted(_EVIDENCE_FIELDS)}


def _audit_output(output):
    # Keep bounded literal output for local diagnosis of rejected proposals.
    try:
        serialized = json_text(output)
        if len(serialized.encode("utf-8")) <= 128 * 1024:
            return serialized
    except (TypeError, ValueError, RecursionError):
        pass
    return json_text({"unavailable": "invalid_or_oversized_output"})


class FieldworkService:
    def __init__(
        self,
        root: Path,
        evidence_backend_factory: Callable[[Path], EvidenceBackend],
        analyzer: Callable[[dict, list[dict]], dict],
        mode: str,
    ):
        self.directory = Path(root).resolve() / PROJECT_ID
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.originals = self.directory / "originals"
        self.originals.mkdir(exist_ok=True, mode=0o700)
        self.store = FieldworkStore(self.directory)
        self.backend = evidence_backend_factory(self.directory)
        self.analyzer = analyzer
        self.mode = mode
        try:
            with self._exclusive("analysis", wait=False), self.store.connect(write=True) as db:
                self.store.reconcile_interrupted_analyses(db)
        except FieldworkError as error:
            if error.code != "analysis_running":
                raise

    @contextmanager
    def _exclusive(self, operation, *, wait=True):
        with (self.directory / f".{operation}.lock").open("ab") as lock:
            locking = fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB
            try:
                fcntl.flock(lock, locking)
            except BlockingIOError:
                raise FieldworkError("analysis_running", "已有分析在进行。", 409) from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def project(self):
        with self.store.connect() as db:
            return self.store.project(db, self.mode)

    def _archive(self, digest, content):
        destination = self.originals / f"{digest}.pdf"
        if destination.exists():
            if destination.is_symlink() or destination.stat().st_size != len(content):
                raise FieldworkError("original_mismatch", "无法确认资料原件。", 502)
            if sha256(destination.read_bytes()).hexdigest() != digest:
                raise FieldworkError("original_mismatch", "无法确认资料原件。", 502)
            return destination
        with NamedTemporaryFile(dir=self.originals, delete=False) as staged:
            temporary = Path(staged.name)
            try:
                staged.write(content)
                staged.flush()
                os.fsync(staged.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return destination

    def _intake_request(self, db, title, digest, replace):
        admitted = db.execute(
            """SELECT 1 FROM materials WHERE state IN ('active', 'retired')
               AND title = ? AND sha256 = ? AND replaces IS ?""",
            (title, digest, replace),
        ).fetchone()
        if admitted:
            return None
        if replace is None:
            active = db.execute(
                "SELECT * FROM materials WHERE title = ? AND state = 'active'", (title,)
            ).fetchone()
            if active:
                if active["sha256"] == digest:
                    return None
                raise FieldworkError("replacement_required", "同名资料已存在，请明确选择替换。", 409)
            lineage = None
        else:
            predecessor = db.execute("SELECT * FROM materials WHERE id = ?", (replace,)).fetchone()
            if predecessor is None or predecessor["state"] not in ("active", "retired"):
                raise _missing("material")
            lineage = predecessor["lineage_id"]
            active = db.execute(
                "SELECT * FROM materials WHERE lineage_id = ? AND state = 'active'", (lineage,)
            ).fetchone()
            if (
                active
                and active["sha256"] == digest
                and active["title"] == title
                and replace == active["id"]
            ):
                return None
            if not active or active["id"] != replace:
                raise FieldworkError("stale_material", "所选资料已有更新，请重新选择替换目标。", 409)
            duplicate_title = db.execute(
                "SELECT 1 FROM materials WHERE title = ? AND state = 'active' AND lineage_id != ?",
                (title, lineage),
            ).fetchone()
            if duplicate_title:
                raise FieldworkError("replacement_required", "另一份适用资料已经使用此名称。", 409)

        request = db.execute(
            """SELECT id FROM materials WHERE state IN ('pending', 'failed')
               AND title = ? AND sha256 = ? AND replaces IS ?
               ORDER BY rowid DESC LIMIT 1""",
            (title, digest, replace),
        ).fetchone()
        if self.store.intake_pending(db):
            pending = db.execute("SELECT id FROM materials WHERE state = 'pending'").fetchone()
            if request is None or request["id"] != pending["id"]:
                raise _intake_pending()
        if request:
            db.execute("UPDATE materials SET state = 'pending', error_code = NULL WHERE id = ?", (request["id"],))
            return request["id"]
        identity = f"material_{uuid4().hex}"
        db.execute(
            """INSERT INTO materials(id, lineage_id, replaces, title, sha256, state)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (identity, lineage or identity, replace, title, digest),
        )
        return identity

    def submit_material(self, title, content, replace=None):
        if (
            not _text(title, maximum=120)
            or any(char in title for char in "/\\")
            or any(ord(char) < 32 for char in title)
        ):
            raise FieldworkError("invalid_title", "请填写资料名称。", 422)
        if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
            raise FieldworkError("invalid_pdf", "请选择 PDF 文件。", 422)
        if len(content) > MAX_PDF_BYTES:
            raise FieldworkError("pdf_too_large", "PDF 文件超过 8 MiB。", 413)

        title = title.strip()
        digest = sha256(content).hexdigest()
        with self._exclusive("intake"):
            with self.store.connect(write=True) as db:
                identity = self._intake_request(db, title, digest, replace)
                if identity is None:
                    return self.store.project(db, self.mode)
            try:
                original = self._archive(digest, content)
                provenance = _provenance(self.backend.ingest(original, digest))
            except Exception as cause:
                if isinstance(cause, FieldworkError):
                    error = cause
                elif isinstance(cause, MkeError):
                    error = _mke_error(cause, message="无法完成文档登记。请核对原件后重试。")
                else:
                    error = FieldworkError("intake_failed", "无法完成文档登记。请重试。", 502)
                with self.store.connect(write=True) as db:
                    db.execute(
                        "UPDATE materials SET state = 'failed', error_code = ? WHERE id = ?",
                        (error.code, identity),
                    )
                raise error from None
            with self.store.connect(write=True) as db:
                if replace:
                    db.execute("UPDATE materials SET state = 'retired' WHERE id = ?", (replace,))
                db.execute(
                    "UPDATE materials SET state = 'active', provenance = ? WHERE id = ?",
                    (json_text(provenance), identity),
                )
                db.execute("UPDATE project SET revision = revision + 1 WHERE singleton = 1")
                self.store.supersede(db)
                return self.store.project(db, self.mode)

    def _begin_analysis(self, material_id, run_id):
        with self.store.connect(write=True) as db:
            if self.store.intake_pending(db):
                raise _intake_pending()
            row = db.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
            if row is None:
                raise _missing("material")
            if row["state"] != "active":
                raise FieldworkError("stale_material", "资料已被替换。请从当前适用资料重新分析。", 409)
            material = material_view(row)
            view = self.store.project(db, self.mode)
            # Prior approved decisions are project state. Only the new run's verified
            # passages and the two stable seed records are supplied for citations.
            project = {
                key: view[key] for key in ("id", "title", "stage", "revision", "sample_prepared", "mode")
            }
            project["confirmed"] = {key: value for key, value in view["confirmed"].items() if key != "evidence"}
            project["material"] = material
            self.store.reconcile_interrupted_analyses(db)
            db.execute(
                """INSERT INTO analysis_runs(id, material_id, basis_revision, mode, status, input_json)
                   VALUES (?, ?, ?, ?, 'selecting', ?)""",
                (run_id, material_id, project["revision"], self.mode, json_text({"project": project})),
            )
            return material, project

    def analyze(self, material_id):
        with self._exclusive("analysis", wait=False):
            run_id = f"fieldwork_run_{uuid4().hex}"
            material, project = self._begin_analysis(material_id, run_id)
            audit_output = None
            phase = "evidence"
            try:
                query = (
                    f"{material['title']}。{project['stage']}：周三演示及样本用法、对外或内部授权，"
                    "实时接口读取条件、现场访谈和需确认的安排。"
                )
                selected = self.backend.select(material, query, run_id)
                if not isinstance(selected, list) or not selected:
                    raise FieldworkError("evidence_unavailable", "当前资料没有可核对的原句。", 422)
                evidence = [_checked_evidence(item, material, run_id) for item in selected]
                evidence.extend(seed_evidence(run_id))
                if len({item["id"] for item in evidence}) != len(evidence):
                    raise FieldworkError("evidence_mismatch", "本次选段含重复的引用身份。", 502)
                model_input = json_text({"project": project, "evidence": evidence})
                with self.store.connect(write=True) as db:
                    db.execute(
                        "UPDATE analysis_runs SET status = 'generating', input_json = ? WHERE id = ?",
                        (model_input, run_id),
                    )
                phase = "analysis"
                actual_input = json.loads(model_input)
                output = self.analyzer(actual_input["project"], actual_input["evidence"])
                audit_output = _audit_output(output)
                draft = _validate_draft(output, evidence)
            except Exception as cause:
                if isinstance(cause, FieldworkError):
                    error = cause
                elif isinstance(cause, MkeError):
                    error = _mke_error(cause, message="当前资料未能完成可核对回读。")
                elif isinstance(cause, ModelFailure):
                    error = FieldworkError(cause.code, "未能完成分析。已有确认版本仍可查阅。", 502)
                    audit_output = _audit_output(cause.receipt)
                else:
                    error = FieldworkError(f"{phase}_failed", "未能完成分析。已有确认版本仍可查阅。", 502)
                with self.store.connect(write=True) as db:
                    db.execute(
                        """UPDATE analysis_runs SET status = 'failed', error_code = ?, output_json = ?
                           WHERE id = ?""",
                        (error.code, audit_output, run_id),
                    )
                raise error from None
            return self._record_proposal(run_id, material_id, project["revision"], evidence, draft, audit_output)

    def _record_proposal(self, run_id, material_id, basis_revision, evidence, draft, audit_output):
        with self.store.connect(write=True) as db:
            revision = db.execute("SELECT revision FROM project WHERE singleton = 1").fetchone()[0]
            stale = basis_revision != revision or self.store.intake_pending(db)
            if stale:
                db.execute(
                    """UPDATE analysis_runs SET status = 'failed', error_code = 'stale_proposal', output_json = ?
                       WHERE id = ?""",
                    (audit_output, run_id),
                )
            else:
                self.store.supersede(db)
                db.execute(
                    """INSERT INTO proposals(id, dra_run_id, basis_revision, material_id, status, mode, draft, evidence)
                       VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
                    (
                        f"proposal_{uuid4().hex}", run_id, basis_revision, material_id,
                        self.mode, json_text(draft), json_text(evidence),
                    ),
                )
                db.execute(
                    "UPDATE analysis_runs SET status = 'completed', output_json = ? WHERE id = ?",
                    (audit_output, run_id),
                )
                return self.store.project(db, self.mode)
        raise _stale_proposal()

    def review(self, proposal_id, decision, feedback):
        if decision not in ("accept", "return") or not _text(feedback, minimum=0):
            raise FieldworkError("invalid_review", "请选择确认方式并核对意见。", 422)
        feedback = feedback.strip()
        if decision == "return" and not feedback:
            raise FieldworkError("feedback_required", "请填写退回意见。", 422)
        target = "accepted" if decision == "accept" else "returned"
        with self.store.connect(write=True) as db:
            proposal = self._proposal(db, proposal_id)
            if proposal["status"] == target and proposal["feedback"] == feedback:
                return self.store.project(db, self.mode)
            if proposal["status"] == "superseded":
                raise _stale_proposal()
            if proposal["status"] != "pending":
                raise FieldworkError("already_reviewed", "这份建议已有处理结果。", 409)
            state = db.execute("SELECT * FROM project WHERE singleton = 1").fetchone()
            if self.store.intake_pending(db):
                raise _intake_pending()
            if proposal["basis_revision"] != state["revision"]:
                raise _stale_proposal()
            db.execute(
                "UPDATE proposals SET status = ?, feedback = ? WHERE id = ?", (target, feedback, proposal_id)
            )
            if target == "accepted":
                version = state["confirmed_version"] + 1
                snapshot = {
                    "version": version,
                    "proposal_id": proposal_id,
                    **{key: proposal[key] for key in ("headline", "summary", "items", "evidence")},
                }
                db.execute(
                    "INSERT INTO confirmed(version, proposal_id, snapshot) VALUES (?, ?, ?)",
                    (version, proposal_id, json_text(snapshot)),
                )
                db.execute(
                    "UPDATE project SET revision = revision + 1, confirmed_version = ? WHERE singleton = 1",
                    (version,),
                )
            return self.store.project(db, self.mode)

    def progress(self, sample_prepared):
        if type(sample_prepared) is not bool:
            raise FieldworkError("invalid_progress", "请选择样本准备状态。", 422)
        with self.store.connect(write=True) as db:
            changed = db.execute(
                """UPDATE project SET sample_prepared = ?, revision = revision + 1
                   WHERE singleton = 1 AND sample_prepared != ?""",
                (sample_prepared, sample_prepared),
            ).rowcount
            if changed:
                self.store.supersede(db)
            return self.store.project(db, self.mode)

    @staticmethod
    def _proposal(db, identity):
        row = db.execute("SELECT * FROM proposals WHERE id = ?", (identity,)).fetchone()
        if row is None:
            raise _missing("proposal")
        return proposal_view(row)

    def proposal(self, identity):
        with self.store.connect() as db:
            return self._proposal(db, identity)

    def live_evidence(self, proposal_id, evidence_id):
        with self.store.connect() as db:
            proposal = self._proposal(db, proposal_id)
            frozen = next((item for item in proposal["evidence"] if item["id"] == evidence_id), None)
            if frozen is None:
                raise _missing("evidence")
            if frozen["producer_run_id"] == "seed":
                return {"status": "unavailable", "frozen": frozen, "current": None, "reason": "seed_record"}
            row = db.execute("SELECT * FROM materials WHERE id = ?", (frozen["material_id"],)).fetchone()
            material = material_view(row)
        try:
            run_id = frozen["consumer_run_id"]
            current = _checked_evidence(self.backend.reread(material, evidence_id, run_id), material, run_id)
            if current != frozen:
                raise FieldworkError("evidence_mismatch", "当前原句与当时的冻结版本不一致。", 502)
        except MkeError as cause:
            return {"status": "unavailable", "frozen": frozen, "current": None, "reason": cause.code}
        except FieldworkError as cause:
            return {"status": "unavailable", "frozen": frozen, "current": None, "reason": cause.code}
        except Exception:
            return {"status": "unavailable", "frozen": frozen, "current": None, "reason": "read_failed"}
        return {"status": "available", "frozen": frozen, "current": current}

    def history(self):
        with self.store.connect() as db:
            return {
                "confirmed": [
                    {"version": row["version"], "proposal_id": row["proposal_id"], "headline": json.loads(row["snapshot"])["headline"]}
                    for row in db.execute("SELECT * FROM confirmed ORDER BY version DESC")
                ],
                "proposals": [
                    {key: proposal[key] for key in ("id", "status", "headline", "material_id", "feedback")}
                    for proposal in map(proposal_view, db.execute("SELECT * FROM proposals ORDER BY rowid DESC"))
                ],
            }

    def export(self, version):
        with self.store.connect() as db:
            snapshot = self.store.snapshot(db, version)
            if snapshot is None:
                raise _missing("version")
            return snapshot

    def register_html(self, version, content: bytes):
        with self.store.connect(write=True) as db:
            snapshot = self.store.snapshot(db, version)
            if snapshot is None:
                raise _missing("version")
            try:
                validate_offline_html(content, snapshot=snapshot)
            except ValueError:
                raise FieldworkError("invalid_html", "HTML 成果与确认版本或离线展示约定不符。", 422) from None
            digest = sha256(content).hexdigest()
            current = db.execute("SELECT sha256 FROM deliverables WHERE version = ?", (version,)).fetchone()
            if current:
                if current["sha256"] != digest:
                    raise FieldworkError("html_registered", "该版本已有登记成果。", 409)
            else:
                db.execute("INSERT INTO deliverables VALUES (?, ?, ?)", (version, digest, content))
        return {"version": version, "sha256": digest}

    def html(self, version):
        with self.store.connect() as db:
            row = db.execute("SELECT content FROM deliverables WHERE version = ?", (version,)).fetchone()
            if row is None:
                raise _missing("html")
            return row["content"]
