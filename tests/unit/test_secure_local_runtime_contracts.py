from __future__ import annotations

from copy import deepcopy
import json

import pytest

from scripts.secure_local_runtime_contracts import (
    BOUNDARIES,
    EXPECTED_CASE_IDS,
    EXPECTED_OBSERVATIONS,
    LIMITS,
    REPORT_SCHEMA_VERSION,
    REPORT_SOURCE,
    _case,
    render_markdown,
    serialize_report,
    validate_report,
)


def _valid_report() -> dict:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "valid",
        "source": REPORT_SOURCE,
        "cases": [
            {
                "case_id": case_id,
                "status": "passed",
                "observations": deepcopy(EXPECTED_OBSERVATIONS[case_id]),
            }
            for case_id in EXPECTED_CASE_IDS
        ],
        "boundaries": dict(BOUNDARIES),
        "limits": list(LIMITS),
    }


def test_contract_freezes_schema_case_order_and_exact_observations():
    assert REPORT_SCHEMA_VERSION == "dra.secure-local-runtime.v1"
    assert REPORT_SOURCE == "production_path_deterministic_local"
    assert EXPECTED_CASE_IDS == (
        "source_launcher_loopback_no_reload",
        "http_empty_secret_ipv4_loopback_allowed",
        "http_empty_secret_ipv6_loopback_allowed",
        "http_empty_secret_non_loopback_rejected",
        "http_empty_secret_unknown_peer_rejected",
        "http_empty_secret_non_loopback_authority_rejected",
        "http_empty_secret_forwarded_rejected",
        "http_configured_secret_invalid_rejected",
        "http_configured_secret_valid_all_peers",
        "websocket_header_credential_accepted",
        "websocket_query_credential_rejected",
        "websocket_invalid_origin_rejected",
        "cors_invalid_origin_rejected",
        "cors_empty_secret_remote_origin_rejected",
        "compose_loopback_required_secrets",
        "container_health_privilege_contract",
    )
    assert EXPECTED_OBSERVATIONS == {
        "source_launcher_loopback_no_reload": {
            "host": "127.0.0.1",
            "port": 8000,
            "reload": False,
            "log_level": "warning",
        },
        "http_empty_secret_ipv4_loopback_allowed": {
            "decision_code": "allowed_loopback",
            "http_status": 200,
            "route_reached": True,
        },
        "http_empty_secret_ipv6_loopback_allowed": {
            "decision_code": "allowed_loopback",
            "http_status": 200,
            "route_reached": True,
        },
        "http_empty_secret_non_loopback_rejected": {
            "decision_code": "api_auth_not_configured",
            "http_status": 503,
            "route_reached": False,
        },
        "http_empty_secret_unknown_peer_rejected": {
            "decision_code": "api_auth_not_configured",
            "http_status": 503,
            "route_reached": False,
        },
        "http_empty_secret_non_loopback_authority_rejected": {
            "decision_code": "local_authority_required",
            "http_status": 503,
            "route_reached": False,
        },
        "http_empty_secret_forwarded_rejected": {
            "decision_code": "forwarded_request_rejected",
            "http_status": 503,
            "route_reached": False,
        },
        "http_configured_secret_invalid_rejected": {
            "decision_code": "api_key_invalid",
            "http_status": 401,
            "route_reached": False,
        },
        "http_configured_secret_valid_all_peers": {
            "decision_code": "allowed_api_key",
            "loopback_route_reached": True,
            "non_loopback_route_reached": True,
        },
        "websocket_header_credential_accepted": {
            "decision_code": "allowed_api_key",
            "run_lookup_observed": True,
            "connection_observed": True,
        },
        "websocket_query_credential_rejected": {
            "decision_code": "query_credential_rejected",
            "close_code": 1008,
            "run_lookup_observed": False,
            "connection_observed": False,
        },
        "websocket_invalid_origin_rejected": {
            "decision_code": "origin_not_allowed",
            "close_code": 1008,
            "run_lookup_observed": False,
            "connection_observed": False,
        },
        "cors_invalid_origin_rejected": {
            "configuration_code": "cors_origin_invalid",
            "construction_rejected": True,
        },
        "cors_empty_secret_remote_origin_rejected": {
            "configuration_code": "cors_origin_requires_authenticated_runtime",
            "construction_rejected": True,
        },
        "compose_loopback_required_secrets": {
            "backend_host_ip": "127.0.0.1",
            "mysql_host_ip": "127.0.0.1",
            "backend_default_host_port": 8000,
            "mysql_default_host_port": 3306,
            "test_host_ports_parameterized": True,
            "api_secret_required": True,
            "mysql_root_password_required": True,
            "mysql_password_required": True,
            "backend_root_password_suppressed": True,
            "service_env_file_parameterized": True,
        },
        "container_health_privilege_contract": {
            "backend_healthcheck_declared": True,
            "mysql_healthcheck_declared": True,
            "cap_drop_all_declared": True,
            "no_new_privileges_declared": True,
            "uvicorn_log_level": "warning",
            "container_runtime_scope": "separate_required_lane",
        },
    }


def test_report_has_exact_top_level_contract_and_honest_boundaries():
    report = _valid_report()

    assert validate_report(report) is report
    assert set(report) == {
        "schema_version",
        "status",
        "source",
        "cases",
        "boundaries",
        "limits",
    }
    assert report["boundaries"] == {
        "source_loopback_access": "proven",
        "authenticated_api_key_access": "proven",
        "websocket_header_only_access": "proven",
        "cors_exact_origin": "proven",
        "container_configuration": "proven",
        "container_runtime": "separate_required_lane",
        "hosted_deployment": "not_claimed",
        "live_provider_result": "not_observed",
    }


def test_case_constructor_rejects_false_missing_extra_and_bool_as_int_observations():
    valid = deepcopy(
        EXPECTED_OBSERVATIONS["source_launcher_loopback_no_reload"]
    )
    assert _case("source_launcher_loopback_no_reload", valid) == {
        "case_id": "source_launcher_loopback_no_reload",
        "status": "passed",
        "observations": valid,
    }

    invalid_values = []
    false_observation = deepcopy(valid)
    false_observation["reload"] = True
    invalid_values.append(false_observation)
    missing_observation = deepcopy(valid)
    missing_observation.pop("host")
    invalid_values.append(missing_observation)
    extra_observation = deepcopy(valid)
    extra_observation["extra"] = True
    invalid_values.append(extra_observation)
    bool_as_int = deepcopy(valid)
    bool_as_int["port"] = True
    invalid_values.append(bool_as_int)

    for observations in invalid_values:
        with pytest.raises(
            ValueError,
            match="secure_local_runtime_proof_report_invalid",
        ):
            _case("source_launcher_loopback_no_reload", observations)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda report: report.__setitem__("schema_version", "unsupported"),
        lambda report: report.__setitem__("status", "partial"),
        lambda report: report.__setitem__("source", "helper_reimplementation"),
        lambda report: report.__setitem__("extra", True),
        lambda report: report["cases"].pop(),
        lambda report: report["cases"].reverse(),
        lambda report: report["cases"][0].__setitem__("extra", True),
        lambda report: report["cases"][0].__setitem__("status", "failed"),
        lambda report: report["cases"][0]["observations"].__setitem__(
            "host", "0.0.0.0"
        ),
        lambda report: report["cases"][0]["observations"].__setitem__(
            "port", True
        ),
        lambda report: report["cases"][1]["observations"].__setitem__(
            "route_reached", 1
        ),
        lambda report: report["cases"][1]["observations"].__setitem__(
            "decision_code", "unknown_code"
        ),
        lambda report: report["cases"][1]["observations"].__setitem__(
            "extra", True
        ),
        lambda report: report["boundaries"].__setitem__(
            "hosted_deployment", "proven"
        ),
        lambda report: report.__setitem__("limits", [*LIMITS, "/private/path"]),
        lambda report: report.__setitem__(
            "limits", [*LIMITS, "commit 0123456789abcdef0123456789abcdef01234567"]
        ),
        lambda report: report.__setitem__(
            "limits", [*LIMITS, "api_key=do-not-record"]
        ),
    ),
)
def test_validator_and_serializers_fail_closed_on_contract_or_public_safety_drift(
    mutate,
):
    report = _valid_report()
    mutate(report)

    with pytest.raises(
        ValueError,
        match="secure_local_runtime_proof_report_invalid",
    ):
        validate_report(report)
    with pytest.raises(
        ValueError,
        match="secure_local_runtime_proof_report_invalid",
    ):
        serialize_report(report)
    with pytest.raises(
        ValueError,
        match="secure_local_runtime_proof_report_invalid",
    ):
        render_markdown(report)


def test_serializers_are_byte_stable_and_markdown_carries_every_ordered_value():
    report = _valid_report()

    first_json = serialize_report(report)
    second_json = serialize_report(deepcopy(report))
    assert first_json == second_json
    assert first_json.endswith(b"\n")
    assert first_json == (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    markdown = render_markdown(report)
    assert markdown.startswith("# Secure Local Runtime v1 Proof\n")
    assert markdown.endswith("\n") and not markdown.endswith("\n\n")
    case_positions = [markdown.index(f"`{case_id}`") for case_id in EXPECTED_CASE_IDS]
    assert case_positions == sorted(case_positions)
    for case_id, observations in EXPECTED_OBSERVATIONS.items():
        assert case_id in markdown
        for key, value in observations.items():
            rendered_value = str(value).lower() if type(value) is bool else str(value)
            assert f"{key}={rendered_value}" in markdown
    boundary_positions = [markdown.index(f"`{key}: {value}`") for key, value in BOUNDARIES.items()]
    assert boundary_positions == sorted(boundary_positions)
    for limit in LIMITS:
        assert f"- {limit}" in markdown
