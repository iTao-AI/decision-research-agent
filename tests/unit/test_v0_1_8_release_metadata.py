from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE = PROJECT_ROOT / "docs/releases/v0.1.8.md"
HEADINGS = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)
HISTORICAL = {
    "v0.1.0.md": "96088198dae7236c05f5bdc5b37f69f126f76c4e4191c7affd36a41d247b8ef2",
    "v0.1.1.md": "2debd84d4383a6335e54ff59cad3521c458698c4ca2b3eb78b4303a8933bbbf7",
    "v0.1.2.md": "4fbde856a85bd5be4ec0d38640f50119024b9dd980b86479b9d7af658789f5bb",
    "v0.1.3.md": "f1b4f34fce15463994645a7e4be0fee03cb22428541116afd96ba45e47c5431d",
    "v0.1.4.md": "2dd2b7650ce0d8f57e8f63954f49165fb1b0974cbc597cf14a414675b3aa8bba",
    "v0.1.5.md": "61cbac951a6513a3eb8f160647b9f16b95ca6ed96a4cca8bea80786462a90b6b",
    "v0.1.6.md": "0cb73ea51e8aae8d4e997a0225a31439dbc11b2977692d3510b8d33d1963552e",
    "v0.1.7.md": "19a64c096aa1f51d42c47a5936da79bddcbf9d08d9db903a4489d4dccf88c3ed",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", text, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == HEADINGS
    return {
        match.group(1): text[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        ]
        for index, match in enumerate(matches)
    }


def test_v0_1_8_version_identity_and_current_links_are_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend/package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend/package-lock.json"))
    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.8"
    assert package["version"] == "0.1.8"
    assert lock["version"] == "0.1.8"
    assert lock["packages"][""]["version"] == "0.1.8"
    assert RELEASE.exists()
    for path in (PROJECT_ROOT / "README.md", PROJECT_ROOT / "README_CN.md", PROJECT_ROOT / "docs/README.md"):
        assert "docs/releases/v0.1.8.md" in _read(path) or "releases/v0.1.8.md" in _read(path)


def test_v0_1_8_release_note_is_closed_and_public_neutral() -> None:
    notes = _read(RELEASE)
    assert notes.startswith(
        "# Decision Research Agent v0.1.8\n\nRelease preparation date: 2026-07-30."
    )
    sections = {name: " ".join(body.split()) for name, body in _sections(notes).items()}
    for phrase in (
        "SELECT-only",
        "CURRENT_USER()",
        "one-statement scanner",
        "65,536 bytes",
        "100 rows",
        "5,000 ms",
        "Connector/Python",
        "greenlet==3.5.4",
    ):
        assert phrase in sections["Changes"] or phrase in sections["Compatibility And Migration"]
    compatibility = sections["Compatibility And Migration"]
    assert "external MySQL" in compatibility
    assert "existing Compose volume" in compatibility
    assert "v0.1.7 remains immutable" in compatibility
    rollback = sections["Rollback"]
    assert "Stop recommending v0.1.8" in rollback
    assert "Do not move published tags" in rollback
    limits = sections["Known Limits"]
    for phrase in ("deployment", "provider", "hosted", "multi-tenant", "business impact"):
        assert phrase in limits
    assert "does not claim that v0.1.8 is published" in notes.lower()


def test_v0_1_8_preserves_every_historical_release_note() -> None:
    for filename, expected in HISTORICAL.items():
        assert sha256((PROJECT_ROOT / "docs/releases" / filename).read_bytes()).hexdigest() == expected
