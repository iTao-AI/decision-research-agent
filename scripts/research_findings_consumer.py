"""Consume existing structured delivery through a real Tool Client subprocess.

Only public CLI/HTTP observations enter this stdlib-only consumer. Its receipt
records structural checks, not source truth, entailment or research quality.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/decision_research_agent_tool.py"
MAX_CHILD_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
_QUESTION_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
_ERROR_CODE = re.compile(r"[A-Za-z0-9_]{1,128}\Z", re.ASCII)
_PROBLEMS = {
    "consumer_timeout": "The Tool Client subprocess exceeded its deadline.",
    "consumer_process_failed": "The Tool Client subprocess failed without a usable error.",
    "consumer_response_invalid": "The Tool Client output is not bounded valid UTF-8 JSON.",
    "consumer_delivery_invalid": "The public delivery package failed independent structural validation.",
    "consumer_output_failed": "The receipt could not be created without overwriting an existing file.",
}


class ConsumerError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.payload = {"code": code, "problem": _PROBLEMS.get(code, "The Tool Client or service rejected delivery."),
                        "cause": "Read-only consumption did not complete.",
                        "fix": "Inspect the error code and the existing run before consuming again.",
                        "retryable": retryable}
        super().__init__(code)


def strict_json(text: str):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value
    def reject_constant(_):
        raise ValueError("nonfinite number")
    value = json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return value


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid public delivery")


def _text(value, maximum: int) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _public_source_url(url) -> bool:
    # Deliberately independent of producer/server URL validators. No fetching.
    if (not _text(url, 2048) or not url.isascii() or url.endswith(tuple(".,;:!?"))
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)):
        return False
    for match in re.finditer("%", url):
        digits = url[match.start() + 1:match.start() + 3]
        if len(digits) != 2 or not re.fullmatch(r"[0-9A-Fa-f]{2}", digits):
            return False
        if int(digits, 16) < 32 or int(digits, 16) == 127:
            return False
    try:
        parsed = urlsplit(url)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or port not in {None, 443}
                or parsed.netloc != (host if port is None else f"{host}:{port}")
                or len(host) > 253 or not _DOMAIN.fullmatch(host)
                or host.endswith((".local", ".internal", ".localhost"))):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except (ValueError, UnicodeError):
        return False


def validate_delivery(package: dict, run_id: str) -> dict:
    """Check received structure and own-byte binding; never grant verification."""
    try:
        _require(type(package) is dict and package["run_id"] == run_id
                 and package["execution_status"] == "completed" and package["delivery_status"] == "ready")
        artifact, report = package["artifact"], package["report"]
        _require((artifact["artifact_id"], artifact["kind"], artifact["media_type"]) == (
            "research-findings.json", "research_findings_json", "application/json"))
        raw = artifact["content"].encode("utf-8")
        _require(0 < len(raw) <= 1024 * 1024 and hashlib.sha256(raw).hexdigest() == artifact["content_hash"])
        _require(strict_json(artifact["content"]) == report)
        _require(set(report) == {"schema_version", "run_id", "profile_id", "profile_version", "questions",
                                 "findings", "dispositions", "reported_contradictions", "limitations"})
        _require(report["schema_version"] == "dra.research-findings.v1" and report["run_id"] == run_id
                 and report["profile_id"] == "generic-evidence-report" and report["profile_version"] == "1")
        _require(package["review_status"] in {"not_required", "required", "resolved"})
        decision = package["review_decision"]
        _require(decision is None or (type(decision) is dict and decision["run_id"] == run_id
                                     and decision["action"] in {"approve", "reject"}))
        questions, findings, dispositions = report["questions"], report["findings"], report["dispositions"]
        _require(type(questions) is list and 1 <= len(questions) <= 5)
        ids = []
        for question in questions:
            _require(set(question) == {"question_id", "text"} and _text(question["text"], 4096)
                     and type(question["question_id"]) is str and bool(_QUESTION_ID.fullmatch(question["question_id"])))
            ids.append(question["question_id"])
        _require(len(set(ids)) == len(ids) and type(dispositions) is list and len(dispositions) == len(ids))
        by_question = {}
        for disposition in dispositions:
            qid, state = disposition["question_id"], disposition["status"]
            _require(qid in ids and qid not in by_question and state in {"candidate_findings", "unresolved"})
            _require(set(disposition) == ({"question_id", "status", "reason"} if state == "unresolved" else {"question_id", "status"}))
            if state == "unresolved":
                _require(_text(disposition["reason"], 2000))
            by_question[qid] = {**disposition, "finding_ids": []}
        evidence = package["evidence"]
        _require(type(evidence) is list)
        rows = {}
        for row in evidence:
            _require(row["run_id"] == run_id and _text(row["evidence_id"], 500) and row["evidence_id"] not in rows
                     and row["verification_status"] in {"unverified", "verified"}
                     and row["citation_status"] in {"uncited", "cited"})
            rows[row["evidence_id"]] = row
        _require(type(findings) is list and 1 <= len(findings) <= 20)
        refs = []
        for index, finding in enumerate(findings, start=1):
            _require(set(finding) == {"finding_id", "question_id", "statement", "references"}
                     and finding["finding_id"] == f"f{index}" and finding["question_id"] in ids
                     and _text(finding["statement"], 2000)
                     and type(finding["references"]) is list and 1 <= len(finding["references"]) <= 10)
            by_question[finding["question_id"]]["finding_ids"].append(finding["finding_id"])
            for ref in finding["references"]:
                _require(set(ref) == {"evidence_id", "evidence_fingerprint", "source_url", "source_identity",
                                      "snippet", "excerpt", "excerpt_start", "excerpt_end"})
                _require(_public_source_url(ref["source_url"]) and ref["source_identity"] == ref["source_url"]
                         and _text(ref["snippet"], 1024 * 1024) and _text(ref["excerpt"], 1000))
                snippet, excerpt, start, end = (ref[key] for key in ("snippet", "excerpt", "excerpt_start", "excerpt_end"))
                _require(type(start) is int and type(end) is int and 0 <= start < end <= len(snippet)
                         and snippet[start:end] == excerpt and snippet.find(excerpt) == start
                         and snippet.find(excerpt, start + 1) == -1)
                fingerprint = hashlib.sha256(f"{ref['source_identity']}\n{' '.join(snippet.split())}".encode("utf-8")).hexdigest()
                _require(ref["evidence_fingerprint"] == fingerprint and ref["evidence_id"] == f"ev_{run_id}_{fingerprint}")
                row = rows[ref["evidence_id"]]
                _require(all(row[key] == ref[key] for key in ("evidence_fingerprint", "source_url", "source_identity", "snippet")))
                matches = [item for item in evidence if item["source_identity"] == ref["source_identity"] and excerpt in item["snippet"]]
                _require(len(matches) == 1 and matches[0]["evidence_id"] == ref["evidence_id"])
                refs.append({"finding_id": finding["finding_id"], **{key: ref[key] for key in (
                    "evidence_id", "evidence_fingerprint", "source_url", "source_identity", "excerpt_start", "excerpt_end")},
                    "citation_status": row["citation_status"], "verification_status": row["verification_status"]})
        _require(all(bool(item["finding_ids"]) == (item["status"] == "candidate_findings") for item in by_question.values()))
        for field in ("reported_contradictions", "limitations"):
            _require(type(report[field]) is list and len(report[field]) <= 20 and all(_text(item, 2000) for item in report[field]))
        receipt = {"schema_version": "dra.research-findings-consumption.v1", "run_id": run_id,
                   "profile_id": report["profile_id"], "profile_version": report["profile_version"],
                   "execution_status": package["execution_status"], "delivery_status": package["delivery_status"],
                   "review_status": package["review_status"], "review_decision_action": decision["action"] if decision else None,
                   "artifact": {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"], "byte_count": len(raw)},
                   "questions": [by_question[qid] for qid in ids], "references": refs,
                   "reported_contradictions": report["reported_contradictions"], "limitations": report["limitations"],
                   "checks": {"artifact_hash": True, "report_matches_artifact": True, "run_profile_identity": True,
                              "question_dispositions": True, "same_run_evidence_binding": True,
                              "unicode_excerpt_offsets": True, "public_source_urls": True}}
        _require(len(_receipt_bytes(receipt)) <= MAX_RECEIPT_BYTES)
        return receipt
    except (KeyError, ValueError, TypeError, AttributeError, UnicodeError, RecursionError) as exc:
        raise ConsumerError("consumer_delivery_invalid") from exc


def _receipt_bytes(receipt: dict) -> bytes:
    return (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_receipt(output: Path, receipt: dict) -> None:
    try:
        raw = _receipt_bytes(receipt)
        _require(len(raw) <= MAX_RECEIPT_BYTES)
        # Publish one complete file exclusively; a failed write/link cannot
        # leave an empty receipt or overwrite a prior invocation's output.
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".findings-receipt-", delete=True) as scratch:
            scratch.write(raw)
            scratch.flush()
            os.link(scratch.name, output)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise ConsumerError("consumer_output_failed") from exc


def _child_deadline(timeout_raw: str) -> float:
    try:
        value = float(timeout_raw) if timeout_raw else 10.0
        if not math.isfinite(value) or not 0 < value <= 60:
            value = 10.0
    except ValueError:
        value = 10.0
    return 4 * value + 10


def _run_tool(command: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    deadline = time.monotonic() + timeout
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, start_new_session=(os.name == "posix")) as child:
        completed = False
        try:
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(command, timeout)
                    chunk = os.read(child.stdout.fileno(), min(65536, MAX_CHILD_BYTES + 1 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_CHILD_BYTES:
                        raise ConsumerError("consumer_response_invalid")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            returncode = child.wait(timeout=remaining)
            completed = True
            return subprocess.CompletedProcess(command, returncode, bytes(output))
        finally:
            if not completed:
                # Also stop the CLI's transport worker on a POSIX host.
                if os.name == "posix":
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif child.poll() is None:
                    child.kill()
                child.wait()


def consume(args) -> dict:
    raw_timeout = args.timeout or os.environ.get("DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS", "")
    command = [sys.executable, str(TOOL), "--base-url", args.base_url, f"--timeout={args.timeout}",
               "findings", "--run-id", args.run_id]
    try:
        child = _run_tool(command, timeout=_child_deadline(raw_timeout))
    except subprocess.TimeoutExpired as exc:
        raise ConsumerError("consumer_timeout", retryable=True) from exc
    except OSError as exc:
        raise ConsumerError("consumer_process_failed") from exc
    try:
        _require(len(child.stdout) <= MAX_CHILD_BYTES)
        value = strict_json(child.stdout.decode("utf-8"))
        _require(type(value) is dict)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ConsumerError("consumer_response_invalid" if child.returncode == 0 else "consumer_process_failed") from exc
    if child.returncode != 0:
        code = value.get("code")
        if child.returncode == 1 and type(code) is str and _ERROR_CODE.fullmatch(code):
            raise ConsumerError(code, retryable=value.get("retryable") is True)
        raise ConsumerError("consumer_process_failed")
    return validate_delivery(value, args.run_id)


def _emit(value: dict) -> None:
    raw = _receipt_bytes(value)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(raw.decode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout", default="")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        try:
            if args.output.exists():
                raise ConsumerError("consumer_output_failed")
        except (OSError, ValueError) as exc:
            raise ConsumerError("consumer_output_failed") from exc
        receipt = consume(args)
        write_receipt(args.output, receipt)
        _emit(receipt)
        return 0
    except ConsumerError as exc:
        _emit(exc.payload)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
