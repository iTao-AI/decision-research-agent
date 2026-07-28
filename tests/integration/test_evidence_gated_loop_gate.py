from __future__ import annotations

import pytest


def test_frozen_generic_downstream_fixture_rejects_strict_profile() -> None:
    from scripts.downstream_consumer_contract import (
        ContractValidationError,
        build_fixture_bundle,
        validate_fixture_bundle,
    )

    payload = build_fixture_bundle()
    payload["cases"][0]["profile_id"] = "generic-strict-citation"
    with pytest.raises(ContractValidationError, match="contract_schema_invalid"):
        validate_fixture_bundle(payload)
