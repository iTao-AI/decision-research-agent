"""Cross-layer source URL admission implication tests."""
from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent.source_url_policy import is_publishable_source_url
from scripts.bounded_live_producer_contracts import EvidenceReceipt
from scripts.downstream_consumer_contract import (
    ContractValidationError,
    _validate_evidence_rows,
)


def _row(source_url: str) -> dict[str, object]:
    return {
        "evidence_id": "ev-source-policy-1",
        "source_url": source_url,
        "source_identity": source_url,
        "retrieved_at": "2026-07-24T00:00:00+00:00",
        "citation_status": "cited",
        "verification_status": "unverified",
    }


def _downstream_accepts(source_url: str) -> bool:
    try:
        _validate_evidence_rows([_row(source_url)], exact=True)
    except ContractValidationError:
        return False
    return True


def _receipt_accepts(source_url: str) -> bool:
    try:
        EvidenceReceipt.model_validate(_row(source_url), strict=True)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.com/source",
        "https://docs.example.com/a/b",
        "https://example.com:443/source",
    ],
)
def test_producer_admission_implies_downstream_and_receipt_acceptance(
    source_url: str,
) -> None:
    assert is_publishable_source_url(source_url)
    assert _downstream_accepts(source_url)
    assert _receipt_accepts(source_url)


@pytest.mark.parametrize(
    "source_url",
    [
        "http://example.com/source",
        "https://user@example.com/source",
        "https://localhost/source",
        "https://10.0.0.1/source",
    ],
)
def test_consumer_rejected_drift_group_is_not_producer_admitted(
    source_url: str,
) -> None:
    assert not is_publishable_source_url(source_url)
    assert not _downstream_accepts(source_url)
    assert not _receipt_accepts(source_url)


@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.com/source?query=1",
        "https://example.com/source#fragment",
        "https://example.com:8443/source",
        "https://8.8.8.8/source",
        "https://example.com./source",
    ],
)
def test_receipt_rejected_compatibility_group_is_not_producer_admitted(
    source_url: str,
) -> None:
    assert not is_publishable_source_url(source_url)
    assert _downstream_accepts(source_url)
    assert not _receipt_accepts(source_url)


@pytest.mark.parametrize(
    "source_url",
    [
        "https://EXAMPLE.com/source",
        "https://example.com/ünicode",
        "https://example.com/source.",
        "https://example.com/" + ("a" * 2049),
    ],
)
def test_receipt_uses_the_exact_producer_publishable_url_policy(
    source_url: str,
) -> None:
    assert not is_publishable_source_url(source_url)
    assert not _receipt_accepts(source_url)
