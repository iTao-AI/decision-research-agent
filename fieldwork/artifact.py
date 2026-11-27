"""Restrict a registered brief to inert, self-contained HTML."""

from hashlib import sha256
from html.parser import HTMLParser
import json
import re

_MAX_SIZE = 256 * 1024
_SNAPSHOT_META = "fieldwork-snapshot-sha256"
_TAGS = frozenset("""
html head meta title style body header main footer section article nav aside
h1 h2 h3 h4 p blockquote ol ul li dl dt dd strong b em small span div a details
summary time mark code pre table caption thead tbody tr th td br hr
""".split())
_DOCUMENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
_ATTRS = frozenset("id class lang role open title scope datetime".split())
_BAD_CSS = re.compile(r"\\|url\s*\(|(?:image|cross-fade|paint|element)(?:-set)?\s*\(|@(?!(?:media|page)\b)", re.I)


class _OfflineHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_style = False
        self.saw_html = False
        self.snapshot_digest = None

    def handle_starttag(self, tag, attrs):
        if tag not in _TAGS:
            raise ValueError("unsupported offline HTML element")
        self.saw_html |= tag == "html"
        self.in_style = tag == "style"
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            raise ValueError("duplicate offline HTML attribute")
        if tag == "meta" and attributes.get("name") == _SNAPSHOT_META:
            digest = attributes.get("content") or ""
            if self.snapshot_digest is not None or set(attributes) != {"name", "content"} or not re.fullmatch(
                r"[0-9a-f]{64}", digest
            ):
                raise ValueError("invalid offline HTML snapshot metadata")
            self.snapshot_digest = digest
            return
        for name, value in attrs:
            if name in _ATTRS or name.startswith("aria-"):
                continue
            if tag == "a" and name == "href" and value and value.startswith("#"):
                continue
            if tag == "meta" and (name, value) in {("charset", "utf-8"), ("name", "viewport")}:
                continue
            if tag == "meta":
                if attributes == {"http-equiv": "Content-Security-Policy", "content": _DOCUMENT_CSP}:
                    continue
                if name == "content" and attributes.get("name") == "viewport":
                    continue
            raise ValueError("unsupported offline HTML attribute")

    def handle_endtag(self, tag):
        if tag not in _TAGS:
            raise ValueError("unsupported offline HTML element")
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if self.in_style and _BAD_CSS.search(re.sub(r"/\*.*?\*/", "", data, flags=re.S)):
            raise ValueError("unsupported offline HTML stylesheet")


def snapshot_fingerprint(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_offline_html(content: bytes, *, snapshot: dict | None = None) -> None:
    if not 0 < len(content) <= _MAX_SIZE or b"\0" in content:
        raise ValueError("invalid offline HTML size or contents")
    parser = _OfflineHTML()
    parser.feed(content.decode("utf-8", errors="strict"))
    parser.close()
    if not parser.saw_html:
        raise ValueError("offline HTML must be a document")
    if snapshot is not None and parser.snapshot_digest != snapshot_fingerprint(snapshot):
        raise ValueError("offline HTML does not identify the selected snapshot")
