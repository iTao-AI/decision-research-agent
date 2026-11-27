"""Replay previously checked PDF readbacks with no executable or credentials."""

import json
import hashlib
from pathlib import Path

from fieldwork.mke import MkeError


class FrozenEvidence:
    def __init__(self, records: dict):
        self._records = records

    @classmethod
    def load(cls):
        path = Path(__file__).resolve().parents[1] / "examples/fieldwork/frozen-readback.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def ingest(self, path: Path, sha256: str) -> dict:
        if sha256 not in self._records or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise MkeError("replay_pdf_unavailable")
        return {"sha256": sha256, "source_id": "frozen-source-" + sha256,
                "publication_id": "frozen-publication-" + sha256, "revision": 1,
                "producer_run_id": "frozen-readback-" + sha256, "total_pages": 1}

    def select(self, material: dict, query: str, consumer_run_id: str) -> list[dict]:
        digest = material["sha256"]
        record = self._records.get(digest)
        if record is None or material["source_id"] != "frozen-source-" + digest:
            raise MkeError("replay_pdf_unavailable")
        text = record["text"]
        original = text.encode("utf-8")
        return [{**{key: material[key] for key in ("title", "source_id", "publication_id",
                                                  "revision", "producer_run_id")},
                 "id": "frozen-evidence-" + digest, "material_id": material["id"],
                 "consumer_run_id": consumer_run_id, "text": text,
                 "page_start": record["page_start"], "page_end": record["page_end"],
                 "sha256": hashlib.sha256(original).hexdigest(), "byte_start": 0,
                 "byte_end": len(original)}]

    def reread(self, material: dict, evidence_id: str, consumer_run_id: str) -> dict:
        current, = self.select(material, "", consumer_run_id)
        if current["id"] != evidence_id:
            raise MkeError("mke_evidence_unavailable")
        return current
