"""SQLite state for the local Fieldwork project."""

import json
import sqlite3
from contextlib import contextmanager
from hashlib import sha256


PROJECT_ID = "northstar"
PROJECT_TITLE = "北辰装备 · 现场服务助手"
PROJECT_STAGE = "现场调查"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS confirmed (
    version INTEGER PRIMARY KEY,
    proposal_id TEXT UNIQUE,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL,
    sample_prepared INTEGER NOT NULL CHECK (sample_prepared IN (0, 1)),
    confirmed_version INTEGER NOT NULL REFERENCES confirmed(version)
);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    lineage_id TEXT NOT NULL,
    replaces TEXT REFERENCES materials(id),
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'failed', 'active', 'retired')),
    provenance TEXT,
    error_code TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS active_material_revision
ON materials(lineage_id) WHERE state = 'active';
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL REFERENCES materials(id),
    basis_revision INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('selecting', 'generating', 'failed', 'completed')),
    input_json TEXT NOT NULL,
    output_json TEXT,
    error_code TEXT
);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    dra_run_id TEXT NOT NULL UNIQUE REFERENCES analysis_runs(id),
    basis_revision INTEGER NOT NULL,
    material_id TEXT NOT NULL REFERENCES materials(id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'superseded', 'accepted', 'returned')),
    mode TEXT NOT NULL,
    feedback TEXT NOT NULL DEFAULT '',
    draft TEXT NOT NULL,
    evidence TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS pending_proposal ON proposals(status) WHERE status = 'pending';
CREATE TABLE IF NOT EXISTS deliverables (
    version INTEGER PRIMARY KEY REFERENCES confirmed(version),
    sha256 TEXT NOT NULL,
    content BLOB NOT NULL
);
"""


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def seed_evidence(consumer_run_id="seed"):
    records = (
        (
            "seed_interview",
            "值班主管访谈",
            "新人查操作卡时，先请有经验的同事确认设备机型和固件版本；工单信息不全，要在值班访谈里补齐。拿不准的告警交给主管复核。",
        ),
        (
            "seed_trial",
            "周三演示约定",
            "周三先演示只读操作卡检索和人工复核。脱敏导出样本是否可用于演示，须等 IT 书面确认；实时告警读取尚未批准。",
        ),
    )
    result = []
    for identity, title, text in records:
        raw = text.encode("utf-8")
        result.append(
            {
                "id": identity,
                "material_id": identity,
                "title": title,
                "source_id": identity,
                "publication_id": f"{identity}_v1",
                "revision": 1,
                "producer_run_id": "seed",
                "consumer_run_id": consumer_run_id,
                "page_start": 1,
                "page_end": 1,
                "text": text,
                "sha256": sha256(raw).hexdigest(),
                "byte_start": 0,
                "byte_end": len(raw),
            }
        )
    return result


def _initial_snapshot():
    return {
        "version": 1,
        "proposal_id": None,
        "headline": "先推进现场访谈，同步核实演示权限",
        "summary": "周三先准备只读操作卡检索与人工复核。使用脱敏样本和读取实时告警分别确认。",
        "items": [
            {
                "area": "demo",
                "state": "waiting",
                "priority": "high",
                "action": "准备只读操作卡检索，确认脱敏样本能否用于周三演示",
                "owner": "试点负责人",
                "reason": "已有周三演示约定，样本使用仍待客户 IT 书面确认。",
                "question": "请客户 IT 确认可对外展示的样本及适用范围。",
                "evidence_ids": ["seed_trial"],
            },
            {
                "area": "live_access",
                "state": "waiting",
                "priority": "normal",
                "action": "单独跟进实时告警接口授权",
                "owner": "客户 IT",
                "reason": "现有试点约定尚未批准实时告警读取。",
                "question": "请客户 IT 说明审批负责人、范围和条件。",
                "evidence_ids": ["seed_trial"],
            },
            {
                "area": "interview",
                "state": "proceed",
                "priority": "normal",
                "action": "继续访谈值班主管，核实工单交接及设备版本",
                "owner": "现场调查负责人",
                "reason": "可以通过访谈补齐工单流程和操作卡适用条件。",
                "question": "",
                "evidence_ids": ["seed_interview"],
            },
        ],
        "evidence": seed_evidence(),
    }


def material_view(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "sha256": row["sha256"],
        "active": row["state"] == "active",
        **json.loads(row["provenance"]),
    }


def proposal_view(row):
    if row is None:
        return None
    return {
        **json.loads(row["draft"]),
        "id": row["id"],
        "dra_run_id": row["dra_run_id"],
        "basis_revision": row["basis_revision"],
        "material_id": row["material_id"],
        "status": row["status"],
        "mode": row["mode"],
        "feedback": row["feedback"],
        "evidence": json.loads(row["evidence"]),
    }


class FieldworkStore:
    def __init__(self, directory):
        self.path = directory / "fieldwork.sqlite3"
        with self.connect(write=True) as db:
            db.executescript(_SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO confirmed(version, snapshot) VALUES (1, ?)",
                (json_text(_initial_snapshot()),),
            )
            db.execute("INSERT OR IGNORE INTO project VALUES (1, 1, 0, 1)")

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def project(db, mode):
        state = db.execute("SELECT * FROM project WHERE singleton = 1").fetchone()
        return {
            "id": PROJECT_ID,
            "title": PROJECT_TITLE,
            "stage": PROJECT_STAGE,
            "revision": state["revision"],
            "sample_prepared": bool(state["sample_prepared"]),
            "mode": mode,
            "confirmed": FieldworkStore.snapshot(db, state["confirmed_version"]),
            "proposal": proposal_view(
                db.execute("SELECT * FROM proposals ORDER BY rowid DESC LIMIT 1").fetchone()
            ),
            "materials": [
                material_view(row)
                for row in db.execute(
                    """SELECT * FROM materials WHERE state IN ('active', 'retired')
                       ORDER BY (state = 'active') DESC, rowid DESC"""
                )
            ],
            "deliverables": [
                dict(row)
                for row in db.execute("SELECT version, sha256 FROM deliverables ORDER BY version DESC")
            ],
        }

    @staticmethod
    def snapshot(db, version):
        row = db.execute("SELECT snapshot FROM confirmed WHERE version = ?", (version,)).fetchone()
        return json.loads(row["snapshot"]) if row else None

    @staticmethod
    def supersede(db):
        db.execute("UPDATE proposals SET status = 'superseded' WHERE status = 'pending'")

    @staticmethod
    def intake_pending(db):
        return db.execute("SELECT 1 FROM materials WHERE state = 'pending' LIMIT 1").fetchone() is not None

    @staticmethod
    def reconcile_interrupted_analyses(db):
        db.execute(
            """UPDATE analysis_runs SET status = 'failed', error_code = 'analysis_interrupted'
               WHERE status IN ('selecting', 'generating')"""
        )
