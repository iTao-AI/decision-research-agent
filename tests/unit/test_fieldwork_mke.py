from copy import deepcopy
import fcntl
from hashlib import sha256
from pathlib import Path
import shutil

import pytest

from fieldwork import mke
from fieldwork.mke import MkeError, MkeEvidence

SOURCE = "src_" + "1" * 32
PUBLICATION = "pub_" + "2" * 32
RUN = "run_" + "3" * 32
EVIDENCE = "ev_" + "4" * 32
TEXT = "客户确认，周三只展示脱敏样本。"
PDF = b"%PDF-1.7\nsynthetic bytes for command-boundary tests"
DIGEST = sha256(PDF).hexdigest()
PAGE = {"kind": "page", "start": 2, "end": 2}
AUTHORITY = {
    "schema_version": "mke.active_authority_snapshot.v1",
    "active_set_fingerprint": "sha256:" + "a" * 64,
    "observation": {"library_id": "local", "state": "active"},
}
LINEAGE = {
    "source_id": SOURCE, "publication_id": PUBLICATION, "publication_revision": 1,
    "run_id": RUN, "content_fingerprint": f"sha256:{DIGEST}",
}
DESCRIPTOR = {
    **LINEAGE, "evidence_id": EVIDENCE, "locator": PAGE,
    "evidence_text_sha256": "sha256:" + sha256(TEXT.encode()).hexdigest(),
    "original_utf8_bytes": len(TEXT.encode()),
}
MATERIAL = {
    "id": "change-letter", "title": "客户函", "sha256": DIGEST, "source_id": SOURCE,
    "publication_id": PUBLICATION, "revision": 1, "producer_run_id": RUN, "total_pages": 2,
}
SOURCE_ENTRY = {
    **LINEAGE, "media_type": "application/pdf", "evidence_count": 1,
    "coverage": {
        "kind": "pdf", "report_status": "observed", "total_pages": 2, "extracted_pages": 1,
    },
}
PUBLISHED = {
    "ok": True, "run": {"run_id": RUN, "state": "published", "source_generation": 1},
    "intake_report": {"total_pages": 2, "extracted_pages": 1},
}


def page(schema, **payload):
    return {"ok": True, "schema_version": f"mke.{schema}.v1", **payload}


def selection(rows, *, cursor=None):
    state = {"status": "complete", "returned": len(rows)}
    if cursor:
        state.update(status="more_available", next_cursor=cursor)
    return state


def catalog(rows):
    return page("list_sources_response", sources=rows, selection=selection(rows),
                authority_snapshot=AUTHORITY)


def read_pages():
    pieces = (TEXT[:4], TEXT[4:])
    offset = 0
    chunks = []
    for i, piece in enumerate(pieces):
        size = len(piece.encode())
        chunks.append(page(
            "read_evidence_response", evidence=deepcopy(DESCRIPTOR),
            content={"text": piece, "offset_bytes": offset, "returned_utf8_bytes": size,
                     "content_trust": "untrusted_evidence"},
            complete=i == 1, next_cursor=None if i else "continuation",
            authority_snapshot=deepcopy(AUTHORITY),
        ))
        offset += size
    return chunks


@pytest.fixture
def adapter(tmp_path):
    return MkeEvidence(Path("/no/local/mke-in-unit-tests"), tmp_path)


@pytest.fixture
def original(tmp_path):
    path = tmp_path / "originals" / f"{DIGEST}.pdf"
    path.parent.mkdir()
    path.write_bytes(PDF)
    return path


def test_ingest_reconciles_published_bytes_after_lost_response(adapter, original, monkeypatch):
    published = False
    ingests = 0

    def run(*args):
        nonlocal published, ingests
        if args[:2] == ("sources", "list"):
            return [catalog([SOURCE_ENTRY] if published else [])]
        if args[:1] == ("ingest",):
            assert args[1] == str(original)
            published = True
            ingests += 1
            raise MkeError("mke_timeout")
        assert args[:3] == ("run", "get", RUN)
        return [PUBLISHED]

    monkeypatch.setattr(adapter, "_run", run)
    first = adapter.ingest(original, DIGEST)
    assert first == {k: v for k, v in MATERIAL.items() if k not in ("id", "title")}
    assert adapter.ingest(original, DIGEST) == first
    assert ingests == 1


def test_ingest_rejects_catalog_run_mismatch(adapter, original, monkeypatch):
    def run(*args):
        if args[0] == "sources":
            return [catalog([SOURCE_ENTRY])]
        assert args[:3] == ("run", "get", RUN)
        return [{**PUBLISHED, "run": {**PUBLISHED["run"], "run_id": "run_" + "5" * 32}}]

    monkeypatch.setattr(adapter, "_run", run)
    with pytest.raises(MkeError, match="provenance"):
        adapter.ingest(original, DIGEST)


def test_ingest_rejects_saved_bytes_with_wrong_digest_before_mke(adapter, original, monkeypatch):
    original.write_bytes(PDF + b"changed")
    monkeypatch.setattr(adapter, "_run", lambda *_: pytest.fail("bad bytes must not reach MKE"))
    with pytest.raises(MkeError) as error:
        adapter.ingest(original, DIGEST)
    assert error.value.code == "mke_invalid_material"


def test_scoped_search_and_short_letter_browse_use_verified_readback(adapter, monkeypatch):
    commands = []

    def run(*args):
        commands.append(args)
        descriptor = {"evidence": DESCRIPTOR, "excerpt": {"text": "untrusted preview"}}
        if args[0] == "search":
            return [page("search_source_evidence_response", scope=LINEAGE, matches=[],
                         selection=selection([]), authority_snapshot=AUTHORITY, query="样本与审批")]
        if args[:2] == ("source", "browse"):
            return [page("browse_source_evidence_response", source=SOURCE_ENTRY,
                         entries=[descriptor], selection=selection([descriptor]),
                         authority_snapshot=AUTHORITY)]
        assert args[:3] == ("evidence", "read", EVIDENCE)
        return read_pages()

    monkeypatch.setattr(adapter, "_run", run)
    result, = adapter.select(MATERIAL, "样本与审批", "consumer-1")
    assert result == {
        **{key: MATERIAL[key] for key in (
            "title", "source_id", "publication_id", "revision", "producer_run_id",
        )},
        "id": EVIDENCE, "material_id": MATERIAL["id"], "consumer_run_id": "consumer-1",
        "page_start": 2, "page_end": 2, "text": TEXT,
        "sha256": sha256(TEXT.encode()).hexdigest(), "byte_start": 0, "byte_end": len(TEXT.encode()),
    }
    assert commands[0][:7] == (
        "search", "样本与审批", "--source-id", SOURCE, "--publication-id", PUBLICATION, "--limit",
    )
    assert commands[1][:5] == ("source", "browse", SOURCE, "--publication-id", PUBLICATION)


def test_search_fails_closed_on_wrong_producer_run(adapter, monkeypatch):
    def run(*args):
        assert args[0] == "search"
        return [page("search_source_evidence_response",
                     scope={**LINEAGE, "run_id": "run_" + "9" * 32}, matches=[],
                     selection=selection([]), authority_snapshot=AUTHORITY, query="样本")]

    monkeypatch.setattr(adapter, "_run", run)
    with pytest.raises(MkeError) as error:
        adapter.select(MATERIAL, "样本", "consumer-1")
    assert error.value.code == "mke_invalid_evidence"


@pytest.mark.parametrize("tamper", [
    "truncate", "overlap", "wrong_bytes", "undecodable_unicode", "mixed_publication",
    "mixed_authority", "forged_digest", "extra_after_complete", "early_terminal",
])
def test_readback_requires_exact_complete_same_run_utf8(adapter, monkeypatch, tamper):
    chunks = read_pages()
    if tamper == "truncate":
        chunks.pop()
    elif tamper == "overlap":
        chunks[-1]["content"]["offset_bytes"] -= 1
    elif tamper == "wrong_bytes":
        chunks[-1]["content"]["returned_utf8_bytes"] -= 1
    elif tamper == "undecodable_unicode":
        chunks[-1]["content"]["text"] = "\ud800"
    elif tamper == "mixed_publication":
        chunks[-1]["evidence"]["publication_id"] = "pub_" + "6" * 32
    elif tamper == "mixed_authority":
        chunks[-1]["authority_snapshot"]["active_set_fingerprint"] = "sha256:" + "9" * 64
    elif tamper == "forged_digest":
        for chunk in chunks:
            chunk["evidence"]["evidence_text_sha256"] = "sha256:" + "9" * 64
    elif tamper == "extra_after_complete":
        chunks.append(chunks[-1])
    elif tamper == "early_terminal":
        chunks[0].update(complete=True, next_cursor=None)

    monkeypatch.setattr(adapter, "_run", lambda *_: chunks)
    with pytest.raises(MkeError) as error:
        adapter.reread(MATERIAL, EVIDENCE, "consumer-1")
    assert error.value.code == "mke_invalid_evidence"


def test_live_read_unavailable_does_not_substitute_another_evidence(adapter, monkeypatch):
    def run(*args):
        assert args[:3] == ("evidence", "read", EVIDENCE)
        raise MkeError("mke_evidence_unavailable")

    monkeypatch.setattr(adapter, "_run", run)
    with pytest.raises(MkeError) as error:
        adapter.reread(MATERIAL, EVIDENCE, "consumer-1")
    assert error.value.code == "mke_evidence_unavailable"


def test_lock_wait_is_bounded(adapter, monkeypatch):
    monkeypatch.setattr(mke, "LOCK_TIMEOUT_SECONDS", 0)
    with adapter.lock_path.open("ab") as competing:
        fcntl.flock(competing, fcntl.LOCK_EX)
        with pytest.raises(MkeError) as error:
            adapter.reread(MATERIAL, EVIDENCE, "consumer-1")
    assert error.value.code == "mke_busy"


def executable_script(tmp_path, source):
    python = shutil.which("python3")
    if python is None:
        pytest.skip("python3 executable is required for a subprocess boundary check")
    script = tmp_path / "mke"
    script.write_text(f"#!{python}\n" + source, encoding="utf-8")
    script.chmod(0o700)
    return script


def test_subprocess_receives_only_configured_paths_and_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DRA_MKE_TEST_SECRET", "should-not-be-inherited")
    executable = executable_script(
        tmp_path,
        "import json, os, sys\nprint(json.dumps({'ok':True, 'db': sys.argv[2], "
        "'cwd': os.getcwd(), 'inherited': 'DRA_MKE_TEST_SECRET' in os.environ}))\n",
    )
    project = tmp_path / "project"
    adapter = MkeEvidence(executable, project)
    assert adapter._run("sources", "list", "--json") == [{
        "ok": True, "db": str(adapter.db_path), "cwd": str(adapter.project_dir), "inherited": False,
    }]


@pytest.mark.parametrize(("source", "expected"), [
    ("import time\ntime.sleep(5)\n", "mke_timeout"),
    ("import sys\nsys.stdout.write('x'*16384)\n", "mke_output_limit"),
])
def test_subprocess_output_and_time_are_bounded(tmp_path, monkeypatch, source, expected):
    monkeypatch.setattr(mke, "COMMAND_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(mke, "COMMAND_MAX_OUTPUT_BYTES", 4096)
    adapter = MkeEvidence(executable_script(tmp_path, source), tmp_path / "project")
    with pytest.raises(MkeError) as error:
        adapter._run("sources", "list", "--json")
    assert error.value.code == expected


def test_short_letter_does_not_silently_omit_an_oversized_condition(adapter, monkeypatch):
    oversized = {**DESCRIPTOR, "original_utf8_bytes": mke.MAX_ITEM_BYTES + 1}
    row = {"evidence": oversized}

    def run(*args):
        if args[0] == "search":
            return [page("search_source_evidence_response", scope=LINEAGE, matches=[],
                         selection=selection([]), authority_snapshot=AUTHORITY, query="样本")]
        if args[:2] == ("source", "browse"):
            return [page("browse_source_evidence_response", source=SOURCE_ENTRY,
                         entries=[row], selection=selection([row]), authority_snapshot=AUTHORITY)]
        pytest.fail("an incomplete short letter must not reach evidence selection")

    monkeypatch.setattr(adapter, "_run", run)
    with pytest.raises(MkeError) as error:
        adapter.select(MATERIAL, "样本", "consumer-1")
    assert error.value.code == "mke_output_limit"


def test_readback_rejects_evidence_claimed_in_empty_authority(adapter, monkeypatch):
    chunks = read_pages()
    for chunk in chunks:
        chunk["authority_snapshot"]["observation"]["state"] = "empty"

    monkeypatch.setattr(adapter, "_run", lambda *_: chunks)
    with pytest.raises(MkeError) as error:
        adapter.reread(MATERIAL, EVIDENCE, "consumer-1")
    assert error.value.code == "mke_invalid_evidence"
