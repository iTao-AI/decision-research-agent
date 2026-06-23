import pytest
from pydantic import ValidationError

from api.publication_models import (
    PublicationRecord,
    VerificationFinalizationRequest,
    decode_evidence_cursor,
    encode_evidence_cursor,
    publication_id_for,
)


def test_publication_id_binds_run_revision_and_snapshot():
    first = publication_id_for(
        run_id="run_1",
        revision=2,
        verification_snapshot_id="vsnap_1",
    )

    assert first == publication_id_for(
        run_id="run_1",
        revision=2,
        verification_snapshot_id="vsnap_1",
    )
    assert first != publication_id_for(
        run_id="run_1",
        revision=3,
        verification_snapshot_id="vsnap_1",
    )


def test_finalization_request_requires_non_negative_state_version():
    with pytest.raises(ValidationError):
        VerificationFinalizationRequest(expected_state_version=-1)


def test_publication_contract_is_frozen_and_forbids_extra_fields():
    publication = PublicationRecord(
        publication_id="publication_1",
        run_id="run_1",
        revision=1,
        verification_snapshot_id="vsnap_1",
        review_id="review_1",
        status="review_required",
        is_current=True,
        artifact_ids=("decision-brief.json",),
        content_hash="a" * 64,
        created_at="2026-06-23T00:00:00+00:00",
    )

    with pytest.raises(ValidationError):
        publication.revision = 2
    with pytest.raises(ValidationError):
        PublicationRecord.model_validate(
            {
                **publication.model_dump(mode="json"),
                "unexpected": True,
            }
        )


def test_evidence_cursor_round_trips_one_bounded_identifier():
    cursor = encode_evidence_cursor(evidence_id="ev_run_1_abc")

    assert decode_evidence_cursor(cursor) == "ev_run_1_abc"


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not-base64",
        encode_evidence_cursor(evidence_id="ev_1") + "tampered",
    ],
)
def test_invalid_evidence_cursor_fails_closed(cursor):
    with pytest.raises(ValueError, match="invalid_evidence_cursor"):
        decode_evidence_cursor(cursor)
