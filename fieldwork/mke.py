"""Read the independent MKE CLI's verified local PDF evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
from typing import Any


MAX_PDF_BYTES = 8 * 1024 * 1024
SHORT_PDF_PAGES = 8
MAX_SELECTED_ITEMS = 8
MAX_ITEM_BYTES = 16_384
MAX_SELECTED_BYTES = 65_536
COMMAND_TIMEOUT_SECONDS = 25
COMMAND_MAX_OUTPUT_BYTES = 2 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 30

_MESSAGES = {
    "mke_unavailable": "The local MKE service could not be started.",
    "mke_timeout": "The local MKE command timed out.",
    "mke_busy": "The local material library is busy.",
    "mke_output_limit": "The local MKE response exceeded the allowed size.",
    "mke_command_failed": "The local MKE command did not complete successfully.",
    "mke_ingest_failed": "MKE could not publish a text layer for this material.",
    "mke_incomplete_coverage": "The PDF does not contain extractable text on every page.",
    "mke_invalid_material": "The saved PDF or its identity is invalid.",
    "mke_invalid_evidence": "MKE returned inconsistent evidence provenance or content.",
    "mke_evidence_unavailable": "This exact evidence is no longer available in MKE.",
}


class MkeError(RuntimeError):
    """Sanitized adapter error suitable for a local service response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(_MESSAGES.get(code, "Local evidence could not be verified."))


def _matching(value: Any, pattern: str) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _integer(value: Any, minimum: int = 1) -> bool:
    return type(value) is int and value >= minimum


def _check(condition: Any, code: str = "mke_invalid_evidence") -> None:
    if not condition:
        raise MkeError(code)


def _record(value: Any) -> dict:
    _check(isinstance(value, dict))
    return value


def _success(page: dict, schema: str) -> dict:
    _check(page.get("ok") is True and page.get("schema_version") == f"mke.{schema}.v1")
    snapshot = _record(page.get("authority_snapshot"))
    observation = _record(snapshot.get("observation"))
    _check(snapshot.get("schema_version") == "mke.active_authority_snapshot.v1")
    _check(_matching(snapshot.get("active_set_fingerprint"), r"sha256:[0-9a-f]{64}"))
    permitted = ("active", "empty") if schema == "list_sources_response" else ("active",)
    _check(observation.get("library_id") == "local" and observation.get("state") in permitted)
    return snapshot


def _collection(pages: list[dict], schema: str, row_key: str) -> Iterator[tuple[dict, list]]:
    _check(pages)
    authority = None
    cursors = set()
    for index, page in enumerate(pages):
        snapshot = _success(page, schema)
        _check(authority is None or authority == snapshot)
        authority = snapshot
        rows = page.get(row_key)
        selection = _record(page.get("selection"))
        _check(isinstance(rows, list) and _integer(selection.get("returned"), 0)
               and selection["returned"] == len(rows))
        cursor = selection.get("next_cursor")
        if index < len(pages) - 1:
            _check(selection.get("status") == "more_available"
                   and isinstance(cursor, str) and cursor and cursor not in cursors)
            cursors.add(cursor)
        else:
            allowed = ("complete", "capped") if row_key == "matches" else ("complete",)
            _check(cursor is None and selection.get("status") in allowed)
        yield page, rows


def _lineage(material: dict) -> dict:
    _check(_matching(material.get("source_id"), r"src_[0-9a-f]{32}")
           and _matching(material.get("publication_id"), r"pub_[0-9a-f]{32}")
           and _matching(material.get("producer_run_id"), r"run_[0-9a-f]{32}")
           and _matching(material.get("sha256"), r"[0-9a-f]{64}")
           and _integer(material.get("revision"))
           and _integer(material.get("total_pages")),
           "mke_invalid_material")
    return {
        "source_id": material["source_id"], "publication_id": material["publication_id"],
        "publication_revision": material["revision"], "run_id": material["producer_run_id"],
        "content_fingerprint": f"sha256:{material['sha256']}",
    }


def _has_lineage(value: dict, lineage: dict) -> bool:
    return (_integer(value.get("publication_revision"))
            and all(value.get(key) == expected for key, expected in lineage.items()))


def _descriptor(value: Any, lineage: dict, total_pages: int) -> dict:
    descriptor = _record(value)
    _check(_has_lineage(descriptor, lineage)
           and _matching(descriptor.get("evidence_id"), r"ev_[0-9a-f]{32}")
           and _matching(descriptor.get("evidence_text_sha256"), r"sha256:[0-9a-f]{64}")
           and _integer(descriptor.get("original_utf8_bytes")))
    locator = _record(descriptor.get("locator"))
    start, end = locator.get("start"), locator.get("end")
    _check(locator.get("kind") == "page"
           and _integer(start) and _integer(end) and start <= end <= total_pages)
    return descriptor


class MkeEvidence:
    """One service-owned project directory, MKE database and producer lock."""

    def __init__(self, executable: str | Path, project_dir: Path):
        self.executable = Path(executable).resolve()
        self.project_dir = Path(project_dir).resolve()
        self.project_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path = self.project_dir / "library.sqlite"
        self.lock_path = self.project_dir / "mke.lock"

    @contextmanager
    def _locked(self) -> Iterator[int]:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        try:
            handle = self.lock_path.open("ab")
        except OSError:
            raise MkeError("mke_unavailable") from None
        with handle:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MkeError("mke_busy") from None
                    time.sleep(min(remaining, 0.05))
                except OSError:
                    raise MkeError("mke_unavailable") from None
            yield handle.fileno()

    def _run(self, *args: str, lock_fd: int) -> list[dict]:
        try:
            process = subprocess.Popen(
                [str(self.executable), "--db", str(self.db_path), *args],
                cwd=self.project_dir, env={"PATH": os.defpath, "PYTHONUTF8": "1"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                # Keep the producer lock through CLI exit even if DRA stops abruptly.
                start_new_session=True, pass_fds=(lock_fd,),
            )
        except OSError:
            raise MkeError("mke_unavailable") from None
        deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
        output = bytearray()
        finished = False
        try:
            assert process.stdout is not None
            with process.stdout, selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise MkeError("mke_timeout")
                    chunk = os.read(process.stdout.fileno(), 65_536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > COMMAND_MAX_OUTPUT_BYTES:
                        raise MkeError("mke_output_limit")
            returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
            finished = True
        except subprocess.TimeoutExpired:
            raise MkeError("mke_timeout") from None
        except OSError:
            raise MkeError("mke_command_failed") from None
        finally:
            if not finished:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=1)

        try:
            pages = [_record(json.loads(line)) for line in output.decode("utf-8").split("\n") if line]
        except (ValueError, RecursionError):
            raise MkeError("mke_invalid_evidence") from None
        if returncode != 0:
            if (args[:2] == ("evidence", "read") and len(pages) == 1
                    and pages[0].get("schema_version") == "mke.read_evidence_response.v1"
                    and pages[0].get("ok") is False and pages[0].get("problem") == "evidence_not_found"):
                raise MkeError("mke_evidence_unavailable")
            raise MkeError("mke_command_failed")
        _check(pages and all(page.get("ok") is True for page in pages))
        return pages

    def _saved_pdf(self, path: Path, digest: str) -> Path:
        _check(_matching(digest, r"[0-9a-f]{64}"), "mke_invalid_material")
        expected = self.project_dir / "originals" / f"{digest}.pdf"
        _check(path.absolute() == expected and path.resolve() == expected, "mke_invalid_material")
        try:
            with path.open("rb") as document:
                attributes = os.fstat(document.fileno())
                _check(stat.S_ISREG(attributes.st_mode) and 0 < attributes.st_size <= MAX_PDF_BYTES,
                       "mke_invalid_material")
                data = document.read(MAX_PDF_BYTES + 1)
        except OSError:
            raise MkeError("mke_invalid_material") from None
        _check(len(data) <= MAX_PDF_BYTES and data.startswith(b"%PDF-")
               and sha256(data).hexdigest() == digest, "mke_invalid_material")
        return expected

    def _published(self, digest: str, lock_fd: int) -> dict | None:
        pages = self._run("sources", "list", "--page-size", "20", "--json", lock_fd=lock_fd)
        sources = [_record(row) for _, rows in _collection(pages, "list_sources_response", "sources")
                   for row in rows]
        matches = [source for source in sources if source.get("content_fingerprint") == f"sha256:{digest}"]
        _check(len(matches) <= 1)
        if not matches:
            return None

        source = matches[0]
        coverage = _record(source.get("coverage"))
        material = {
            "sha256": digest, "source_id": source.get("source_id"),
            "publication_id": source.get("publication_id"),
            "revision": source.get("publication_revision"), "producer_run_id": source.get("run_id"),
            "total_pages": coverage.get("total_pages"),
        }
        lineage = _lineage(material)
        _check(source.get("media_type") == "application/pdf" and coverage.get("kind") == "pdf"
               and coverage.get("report_status") == "observed"
               and _integer(source.get("evidence_count"))
               and _integer(coverage.get("extracted_pages"))
               and source["evidence_count"] == coverage["extracted_pages"] <= material["total_pages"])
        run_id = lineage["run_id"]
        runs = self._run("run", "get", run_id, "--json", lock_fd=lock_fd)
        _check(len(runs) == 1)
        run = _record(runs[0].get("run"))
        report = _record(runs[0].get("intake_report"))
        _check(run.get("run_id") == run_id and run.get("state") == "published"
               and _integer(report.get("total_pages")) and report["total_pages"] == material["total_pages"]
               and _integer(report.get("extracted_pages"))
               and report["extracted_pages"] == coverage["extracted_pages"])
        _check(report["extracted_pages"] == material["total_pages"], "mke_incomplete_coverage")
        return material

    def ingest(self, path: Path, sha256: str) -> dict:
        """Reconcile any already-published bytes before invoking the producer."""
        with self._locked() as lock_fd:
            original = self._saved_pdf(Path(path), sha256)
            previous = self._published(sha256, lock_fd)
            if previous is not None:
                return previous
            try:
                receipts = self._run("ingest", str(original), "--json", lock_fd=lock_fd)
            except MkeError as exc:
                # A lost response may still have committed the Publication.
                recovered = self._published(sha256, lock_fd)
                if recovered is not None:
                    return recovered
                if exc.code == "mke_command_failed":
                    raise MkeError("mke_ingest_failed") from None
                raise
            _check(len(receipts) == 1)
            receipt = receipts[0]
            published = self._published(sha256, lock_fd)
            _check(published is not None and receipt.get("run_state") == "published"
                   and receipt.get("run_id") == published["producer_run_id"])
            return published

    def select(self, material: dict, query: str, consumer_run_id: str) -> list[dict]:
        lineage = _lineage(material)
        total_pages = material["total_pages"]
        query = query.strip()
        _check(query and not query.startswith("-") and len(query.encode("utf-8")) <= 512,
               "mke_invalid_material")
        scope = ("--source-id", lineage["source_id"], "--publication-id", lineage["publication_id"])
        with self._locked() as lock_fd:
            search = self._run("search", query, *scope, "--limit", str(MAX_SELECTED_ITEMS),
                               "--json", lock_fd=lock_fd)
            candidates = {}
            authority = search[0].get("authority_snapshot")
            for page, rows in _collection(search, "search_source_evidence_response", "matches"):
                _check(_has_lineage(_record(page.get("scope")), lineage) and page.get("query") == query)
                self._collect_descriptors(candidates, rows, lineage, total_pages)

            if total_pages <= SHORT_PDF_PAGES:
                # A complete short letter contributes its adjacent conditions even if
                # lexical search matched the permission sentence alone.
                browse = self._run(
                    "source", "browse", lineage["source_id"], *scope[2:],
                    "--page-start", "1", "--page-end", str(total_pages), "--json", lock_fd=lock_fd,
                )
                browsed = {}
                for page, rows in _collection(browse, "browse_source_evidence_response", "entries"):
                    source = _record(page.get("source"))
                    coverage = _record(source.get("coverage"))
                    _check(page.get("authority_snapshot") == authority and _has_lineage(source, lineage)
                           and _integer(source.get("evidence_count"))
                           and source["evidence_count"] == total_pages
                           and coverage.get("kind") == "pdf" and coverage.get("report_status") == "observed"
                           and _integer(coverage.get("total_pages")) and coverage["total_pages"] == total_pages)
                    self._collect_descriptors(browsed, rows, lineage, total_pages)
                # MKE publishes one Evidence record per extracted PDF page.
                locators = sorted((entry["locator"]["start"], entry["locator"]["end"]) for entry in browsed.values())
                _check(locators == [(number, number) for number in range(1, total_pages + 1)]
                       and all(browsed.get(key) == value for key, value in candidates.items()))
                sizes = [entry["original_utf8_bytes"] for entry in browsed.values()]
                _check(len(sizes) <= MAX_SELECTED_ITEMS and sum(sizes) <= MAX_SELECTED_BYTES
                       and all(size <= MAX_ITEM_BYTES for size in sizes), "mke_output_limit")
                candidates = browsed

            items = []
            remaining = MAX_SELECTED_BYTES
            for evidence_id, descriptor in candidates.items():
                size = descriptor["original_utf8_bytes"]
                if size <= min(remaining, MAX_ITEM_BYTES):
                    items.append(self._read(material, lineage, evidence_id, consumer_run_id,
                                            lock_fd=lock_fd, descriptor=descriptor, snapshot=authority))
                    remaining -= size
                if len(items) == MAX_SELECTED_ITEMS:
                    break
            return items

    @staticmethod
    def _collect_descriptors(candidates: dict, rows: list, lineage: dict, total_pages: int) -> None:
        for row in rows:
            descriptor = _descriptor(_record(row).get("evidence"), lineage, total_pages)
            key = descriptor["evidence_id"]
            _check(key not in candidates)
            candidates[key] = descriptor

    def reread(self, material: dict, evidence_id: str, consumer_run_id: str) -> dict:
        """Read this exact historical identity or return a safe unavailable error."""
        lineage = _lineage(material)
        with self._locked() as lock_fd:
            return self._read(material, lineage, evidence_id, consumer_run_id, lock_fd=lock_fd)

    def _read(
        self, material: dict, lineage: dict, evidence_id: str, consumer_run_id: str, *,
        lock_fd: int, descriptor: dict | None = None, snapshot: dict | None = None,
    ) -> dict:
        _check(_matching(evidence_id, r"ev_[0-9a-f]{32}"))
        reads = self._run("evidence", "read", evidence_id, "--max-bytes", "8192", "--json", lock_fd=lock_fd)
        data = bytearray()
        cursors = set()
        for index, page in enumerate(reads):
            authority = _success(page, "read_evidence_response")
            _check(snapshot is None or snapshot == authority)
            snapshot = authority
            actual = _descriptor(page.get("evidence"), lineage, material["total_pages"])
            _check(actual["evidence_id"] == evidence_id and (descriptor is None or descriptor == actual))
            descriptor = actual
            _check(descriptor["original_utf8_bytes"] <= MAX_ITEM_BYTES)
            content = _record(page.get("content"))
            _check(content.get("content_trust") == "untrusted_evidence"
                   and _integer(content.get("offset_bytes"), 0) and content["offset_bytes"] == len(data)
                   and _integer(content.get("returned_utf8_bytes")) and isinstance(content.get("text"), str))
            try:
                chunk = content["text"].encode("utf-8")
            except UnicodeEncodeError:
                raise MkeError("mke_invalid_evidence") from None
            _check(len(chunk) == content["returned_utf8_bytes"])
            data.extend(chunk)
            terminal = index == len(reads) - 1
            _check(page.get("complete") is terminal)
            cursor = page.get("next_cursor")
            if terminal:
                _check(cursor is None and len(data) == descriptor["original_utf8_bytes"])
            else:
                _check(isinstance(cursor, str) and cursor and cursor not in cursors
                       and len(data) < descriptor["original_utf8_bytes"])
                cursors.add(cursor)

        _check(descriptor is not None and data)
        digest = sha256(data).hexdigest()
        _check(descriptor["evidence_text_sha256"] == f"sha256:{digest}")
        return {
            "id": evidence_id, "material_id": material["id"], "title": material["title"],
            **{key: material[key] for key in ("source_id", "publication_id", "revision", "producer_run_id")},
            "consumer_run_id": consumer_run_id, "page_start": descriptor["locator"]["start"],
            "page_end": descriptor["locator"]["end"], "text": data.decode("utf-8"),
            "sha256": digest, "byte_start": 0, "byte_end": len(data),
        }
