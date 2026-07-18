"""Strict deterministic evidence contracts for the secure local runtime."""

from __future__ import annotations

import json
import re
from typing import Any


REPORT_SCHEMA_VERSION = "dra.secure-local-runtime.v1"
REPORT_SOURCE = "production_path_deterministic_local"
REPORT_INVALID_CODE = "secure_local_runtime_proof_report_invalid"

EXPECTED_CASE_IDS = (
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

EXPECTED_OBSERVATIONS: dict[str, dict[str, bool | int | str]] = {
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
        "api_secret_required": True,
        "mysql_root_password_required": True,
        "mysql_password_required": True,
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

BOUNDARIES = {
    "source_loopback_access": "proven",
    "authenticated_api_key_access": "proven",
    "websocket_header_only_access": "proven",
    "cors_exact_origin": "proven",
    "container_configuration": "proven",
    "container_runtime": "separate_required_lane",
    "hosted_deployment": "not_claimed",
    "live_provider_result": "not_observed",
}

LIMITS = [
    "Deterministic local contract evidence, not a Docker runtime observation or deployment certification.",
    "TLS, identity, authorization, RBAC, and hosted operation are not proven.",
    "Provider, model, tool, and research quality are not observed.",
    "The required Docker runtime lane remains authoritative for container build, health, privilege inspection, and cleanup.",
]

_COMMIT_SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", re.IGNORECASE)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'])[A-Za-z]:[\\/]")
_FORBIDDEN_PUBLIC_MARKERS = (
    "api_key=",
    "authorization: bearer",
    "openai_api_key",
    "tavily_api_key",
    "langsmith_api_key",
    "proof-only-api-secret",
    "test-secret",
    "your-secret-key",
    "traceback (most recent call last)",
    "api.openai.com",
    "/users/",
    "/private/",
    "/tmp/",
)


def _invalid_report() -> None:
    raise ValueError(REPORT_INVALID_CODE)


def _strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(
            _strict_equal(actual[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _strict_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _iter_public_strings(value: Any):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for key, item in value.items():
            yield from _iter_public_strings(key)
            yield from _iter_public_strings(item)
    elif type(value) is list:
        for item in value:
            yield from _iter_public_strings(item)


def _assert_public_safe(report: dict[str, Any]) -> None:
    for value in _iter_public_strings(report):
        lowered = value.lower()
        if (
            _COMMIT_SHA.search(value)
            or _WINDOWS_ABSOLUTE_PATH.search(value)
            or any(marker in lowered for marker in _FORBIDDEN_PUBLIC_MARKERS)
        ):
            _invalid_report()


def _case(
    case_id: str,
    observations: dict[str, Any],
) -> dict[str, Any]:
    expected = EXPECTED_OBSERVATIONS.get(case_id)
    if expected is None or not _strict_equal(observations, expected):
        _invalid_report()
    return {
        "case_id": case_id,
        "status": "passed",
        "observations": observations,
    }


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if type(report) is not dict or set(report) != {
        "schema_version",
        "status",
        "source",
        "cases",
        "boundaries",
        "limits",
    }:
        _invalid_report()
    if (
        type(report["schema_version"]) is not str
        or report["schema_version"] != REPORT_SCHEMA_VERSION
        or type(report["status"]) is not str
        or report["status"] != "valid"
        or type(report["source"]) is not str
        or report["source"] != REPORT_SOURCE
        or not _strict_equal(report["boundaries"], BOUNDARIES)
        or not _strict_equal(report["limits"], LIMITS)
    ):
        _invalid_report()

    cases = report["cases"]
    if type(cases) is not list or len(cases) != len(EXPECTED_CASE_IDS):
        _invalid_report()
    for case_id, item in zip(EXPECTED_CASE_IDS, cases, strict=True):
        if type(item) is not dict or set(item) != {
            "case_id",
            "status",
            "observations",
        }:
            _invalid_report()
        if (
            type(item["case_id"]) is not str
            or item["case_id"] != case_id
            or type(item["status"]) is not str
            or item["status"] != "passed"
            or not _strict_equal(
                item["observations"],
                EXPECTED_OBSERVATIONS[case_id],
            )
        ):
            _invalid_report()

    _assert_public_safe(report)
    return report


def serialize_report(report: dict[str, Any]) -> bytes:
    validate_report(report)
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _render_observation_value(value: bool | int | str) -> str:
    return str(value).lower() if type(value) is bool else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    validate_report(report)
    lines = [
        "# Secure Local Runtime v1 Proof",
        "",
        "Status: valid deterministic local production-path contract proof.",
        "",
        "## Cases",
        "",
        "| Case | Status | Observations |",
        "|---|---|---|",
    ]
    cases_by_id = {item["case_id"]: item for item in report["cases"]}
    for case_id in EXPECTED_CASE_IDS:
        item = cases_by_id[case_id]
        observations = item["observations"]
        rendered = "<br>".join(
            f"`{key}={_render_observation_value(observations[key])}`"
            for key in EXPECTED_OBSERVATIONS[case_id]
        )
        lines.append(f"| `{case_id}` | {item['status']} | {rendered} |")

    lines.extend(["", "## Boundaries", ""])
    lines.extend(
        f"- `{key}: {report['boundaries'][key]}`" for key in BOUNDARIES
    )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {value}" for value in LIMITS)
    return "\n".join(lines) + "\n"
