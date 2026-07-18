#!/usr/bin/env python3
"""Build or check the deterministic secure-local-runtime contract proof."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import importlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.secure_local_runtime_contracts import (  # noqa: E402
    BOUNDARIES,
    EXPECTED_CASE_IDS,
    LIMITS,
    REPORT_SCHEMA_VERSION,
    REPORT_SOURCE,
    _case,
    render_markdown,
    serialize_report,
    validate_report,
)


BASELINE_JSON_PATH = PROJECT_ROOT / "docs/evidence/secure-local-runtime-v1.json"
BASELINE_MARKDOWN_PATH = PROJECT_ROOT / "docs/evidence/secure-local-runtime-v1.md"
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile.backend"
ENV_TEMPLATE_PATH = PROJECT_ROOT / ".env.example"
DOCKERIGNORE_PATH = PROJECT_ROOT / ".dockerignore"
MAX_BASELINE_BYTES = 1_000_000
_INVALID_CODE = "secure_local_runtime_proof_invalid"
_CORS_ORIGIN_ENV = "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN"
_HTTP_PROOF_PATH = "/api/profiles/generic"
_PROOF_API_SECRET = "secure-runtime-proof-ephemeral"
_PROOF_IMPORT_MODULES = ("api.server", "agent.main_agent", "agent.llm")


class _ProofError(ValueError):
    """A deliberately detail-free proof or CLI failure."""


def _invalid() -> None:
    raise _ProofError(_INVALID_CODE)


def _restore_environment_value(name: str, previous: object) -> None:
    if previous is _MISSING:
        os.environ.pop(name, None)
    else:
        os.environ[name] = str(previous)


_MISSING = object()


def _load_production_modules():
    """Load production owners lazily under a deterministic access bootstrap."""

    if "api.server" in sys.modules:
        server = sys.modules["api.server"]
    else:
        previous_secret = os.environ.get("API_SECRET", _MISSING)
        previous_origin = os.environ.get(_CORS_ORIGIN_ENV, _MISSING)
        previous_dotenv = os.environ.get("PYTHON_DOTENV_DISABLED", _MISSING)
        previous_provider_key = os.environ.get("OPENAI_API_KEY", _MISSING)
        os.environ["API_SECRET"] = ""
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        os.environ["OPENAI_API_KEY"] = "provider-disabled-local-proof"
        os.environ.pop(_CORS_ORIGIN_ENV, None)
        try:
            server = importlib.import_module("api.server")
        finally:
            _restore_environment_value("API_SECRET", previous_secret)
            _restore_environment_value(_CORS_ORIGIN_ENV, previous_origin)
            _restore_environment_value("PYTHON_DOTENV_DISABLED", previous_dotenv)
            _restore_environment_value("OPENAI_API_KEY", previous_provider_key)
    return (
        server,
        importlib.import_module("api.cors_config"),
        importlib.import_module("api.runtime_access"),
        importlib.import_module("api.run_repository"),
    )


@contextmanager
def _runtime_state(server, cors_config, runtime_access, environ: dict[str, str]):
    policy = runtime_access.load_runtime_access_policy(environ)
    configuration = cors_config.load_cors_configuration(
        access_policy=policy,
        environ=environ,
    )
    previous_policy = server.app.state.runtime_access_policy
    previous_cors = server.app.state.cors_configuration
    server.app.state.runtime_access_policy = policy
    server.app.state.cors_configuration = configuration
    try:
        yield
    finally:
        server.app.state.runtime_access_policy = previous_policy
        server.app.state.cors_configuration = previous_cors


def _observe_source_launcher(server) -> dict[str, Any]:
    with patch.object(server.uvicorn, "run") as run:
        server.run_source_server()
    if run.call_count != 1:
        _invalid()
    args, kwargs = run.call_args
    if (
        len(args) != 1
        or args[0] is not server.app
        or set(kwargs) != {"host", "port", "reload", "log_level"}
    ):
        _invalid()
    return {
        "host": kwargs.get("host"),
        "port": kwargs.get("port"),
        "reload": kwargs.get("reload"),
        "log_level": kwargs.get("log_level"),
    }


def _route_reached(response) -> bool:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return False
    return (
        response.status_code == 200
        and type(payload) is dict
        and type(payload.get("profile")) is dict
        and payload["profile"].get("profile_id") == "generic"
    )


def _http_observation(
    server,
    cors_config,
    runtime_access,
    *,
    environ: dict[str, str],
    peer: str,
    authority: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    decisions = []
    current_decider = server.decide_runtime_access

    def observe_decision(*args, **kwargs):
        decision = current_decider(*args, **kwargs)
        decisions.append(decision)
        return decision

    headers = {"Host": authority, **(extra_headers or {})}
    with _runtime_state(server, cors_config, runtime_access, environ), patch.object(
        server,
        "decide_runtime_access",
        observe_decision,
    ):
        client = TestClient(
            server.app,
            base_url="http://127.0.0.1",
            client=(peer, 50000),
            follow_redirects=False,
        )
        try:
            response = client.get(_HTTP_PROOF_PATH, headers=headers)
        finally:
            client.close()
    if len(decisions) != 1:
        _invalid()
    return {
        "decision_code": decisions[0].code,
        "http_status": response.status_code,
        "route_reached": _route_reached(response),
    }


def _observe_http_cases(server, cors_config, runtime_access) -> list[dict[str, Any]]:
    empty = {}
    configured = {"API_SECRET": _PROOF_API_SECRET}
    cases = [
        _case(
            "http_empty_secret_ipv4_loopback_allowed",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="127.0.0.1",
                authority="127.0.0.1:8000",
            ),
        ),
        _case(
            "http_empty_secret_ipv6_loopback_allowed",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="::1",
                authority="[::1]:8000",
            ),
        ),
        _case(
            "http_empty_secret_non_loopback_rejected",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="192.0.2.10",
                authority="127.0.0.1:8000",
            ),
        ),
        _case(
            "http_empty_secret_unknown_peer_rejected",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="unknown-peer",
                authority="127.0.0.1:8000",
            ),
        ),
        _case(
            "http_empty_secret_non_loopback_authority_rejected",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="127.0.0.1",
                authority="service.example",
            ),
        ),
        _case(
            "http_empty_secret_forwarded_rejected",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=empty,
                peer="127.0.0.1",
                authority="127.0.0.1:8000",
                extra_headers={"Forwarded": "for=192.0.2.10"},
            ),
        ),
        _case(
            "http_configured_secret_invalid_rejected",
            _http_observation(
                server,
                cors_config,
                runtime_access,
                environ=configured,
                peer="192.0.2.10",
                authority="service.example",
                extra_headers={"X-API-Key": "invalid"},
            ),
        ),
    ]

    loopback = _http_observation(
        server,
        cors_config,
        runtime_access,
        environ=configured,
        peer="127.0.0.1",
        authority="127.0.0.1:8000",
        extra_headers={"X-API-Key": _PROOF_API_SECRET},
    )
    non_loopback = _http_observation(
        server,
        cors_config,
        runtime_access,
        environ=configured,
        peer="192.0.2.10",
        authority="service.example",
        extra_headers={"X-API-Key": _PROOF_API_SECRET},
    )
    decision_code = (
        loopback["decision_code"]
        if loopback["decision_code"] == non_loopback["decision_code"]
        else "inconsistent"
    )
    cases.append(
        _case(
            "http_configured_secret_valid_all_peers",
            {
                "decision_code": decision_code,
                "loopback_route_reached": loopback["route_reached"],
                "non_loopback_route_reached": non_loopback["route_reached"],
            },
        )
    )
    return cases


def _websocket_observation(
    server,
    cors_config,
    runtime_access,
    *,
    db_path: Path,
    run_id: str,
    environ: dict[str, str],
    url: str,
    headers: dict[str, str],
    expect_connection: bool,
) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    decisions = []
    lookup_observed = False
    connection_observed = False
    current_decider = server.decide_runtime_access
    current_get_run = server.get_run
    current_connect = server.manager.connect_run

    def observe_decision(*args, **kwargs):
        decision = current_decider(*args, **kwargs)
        decisions.append(decision)
        return decision

    def observe_lookup(*, run_id):
        nonlocal lookup_observed
        lookup_observed = True
        return current_get_run(run_id=run_id)

    async def observe_connection(websocket, *, run_id, thread_id):
        nonlocal connection_observed
        connection_observed = True
        return await current_connect(
            websocket,
            run_id=run_id,
            thread_id=thread_id,
        )

    close_code = 0
    close_reason = None
    completed_connection = False
    application_environ = {
        **environ,
        "DECISION_RESEARCH_AGENT_DB_PATH": str(db_path),
    }
    with (
        patch.dict(os.environ, application_environ, clear=False),
        _runtime_state(server, cors_config, runtime_access, environ),
        patch.object(server, "decide_runtime_access", observe_decision),
        patch.object(server, "get_run", observe_lookup),
        patch.object(server.manager, "connect_run", observe_connection),
    ):
        client = TestClient(
            server.app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
            follow_redirects=False,
        )
        try:
            try:
                with client.websocket_connect(url, headers=headers) as websocket:
                    if expect_connection:
                        websocket.send_text("ping")
                        payload = websocket.receive_json()
                        completed_connection = (
                            type(payload) is dict
                            and payload.get("type") == "pong"
                            and payload.get("run_id") == run_id
                        )
            except WebSocketDisconnect as error:
                close_code = error.code
                close_reason = error.reason
        finally:
            client.close()

    if len(decisions) != 1:
        _invalid()
    decision_code = decisions[0].code
    if close_reason is not None and close_reason != decision_code:
        _invalid()
    if expect_connection and not completed_connection:
        connection_observed = False
    return {
        "decision_code": decision_code,
        "close_code": close_code,
        "run_lookup_observed": lookup_observed,
        "connection_observed": connection_observed,
    }


def _observe_websocket_cases(
    server,
    cors_config,
    runtime_access,
    run_repository,
) -> list[dict[str, Any]]:
    with TemporaryDirectory(prefix="dra-secure-runtime-proof-") as directory:
        db_path = Path(directory) / "application.db"
        created = run_repository.create_run(
            db_path=str(db_path),
            thread_id="secure-runtime-proof-thread",
            query="deterministic local protocol observation",
        )
        run_id = created["run_id"]
        configured = {"API_SECRET": _PROOF_API_SECRET}
        accepted = _websocket_observation(
            server,
            cors_config,
            runtime_access,
            db_path=db_path,
            run_id=run_id,
            environ=configured,
            url=f"/ws/runs/{run_id}",
            headers={
                "Host": "127.0.0.1:8000",
                "X-API-Key": _PROOF_API_SECRET,
            },
            expect_connection=True,
        )
        query_rejected = _websocket_observation(
            server,
            cors_config,
            runtime_access,
            db_path=db_path,
            run_id=run_id,
            environ=configured,
            url=f"/ws/runs/{run_id}?api_key=discarded",
            headers={
                "Host": "127.0.0.1:8000",
                "X-API-Key": _PROOF_API_SECRET,
            },
            expect_connection=False,
        )
        origin_environ = {
            **configured,
            _CORS_ORIGIN_ENV: "https://allowed.example",
        }
        origin_rejected = _websocket_observation(
            server,
            cors_config,
            runtime_access,
            db_path=db_path,
            run_id=run_id,
            environ=origin_environ,
            url=f"/ws/runs/{run_id}",
            headers={
                "Host": "127.0.0.1:8000",
                "X-API-Key": _PROOF_API_SECRET,
                "Origin": "https://rejected.example",
            },
            expect_connection=False,
        )

    return [
        _case(
            "websocket_header_credential_accepted",
            {
                "decision_code": accepted["decision_code"],
                "run_lookup_observed": accepted["run_lookup_observed"],
                "connection_observed": accepted["connection_observed"],
            },
        ),
        _case(
            "websocket_query_credential_rejected",
            query_rejected,
        ),
        _case(
            "websocket_invalid_origin_rejected",
            origin_rejected,
        ),
    ]


def _cors_rejection_observation(
    cors_config,
    runtime_access,
    *,
    policy_environ: dict[str, str],
    origin: str,
) -> dict[str, Any]:
    rejected = False
    code = "not_rejected"
    try:
        cors_config.load_cors_configuration(
            access_policy=runtime_access.load_runtime_access_policy(
                policy_environ
            ),
            environ={_CORS_ORIGIN_ENV: origin},
        )
    except cors_config.CorsConfigurationError as error:
        rejected = True
        code = str(error)
    return {
        "configuration_code": code,
        "construction_rejected": rejected,
    }


def _observe_cors_cases(cors_config, runtime_access) -> list[dict[str, Any]]:
    return [
        _case(
            "cors_invalid_origin_rejected",
            _cors_rejection_observation(
                cors_config,
                runtime_access,
                policy_environ={"API_SECRET": _PROOF_API_SECRET},
                origin="*",
            ),
        ),
        _case(
            "cors_empty_secret_remote_origin_rejected",
            _cors_rejection_observation(
                cors_config,
                runtime_access,
                policy_environ={},
                origin="https://remote.example",
            ),
        ),
    ]


def _required_interpolation(value: Any, variable: str) -> bool:
    return (
        type(value) is str
        and value.startswith(f"${{{variable}:?")
        and value.endswith("}")
    )


def _dotenv_assignments(text: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            _invalid()
        key, value = line.split("=", 1)
        if not key or key in assignments:
            _invalid()
        assignments[key] = value
    return assignments


def _validate_env_template() -> None:
    text = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    assignments = _dotenv_assignments(text)
    expected = {
        "API_SECRET": "",
        "OPENAI_API_KEY": "",
        "TAVILY_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
        "MYSQL_ROOT_PASSWORD": "",
        "MYSQL_USER": "decision_research",
        "MYSQL_PASSWORD": "",
        "MYSQL_DATABASE": "decision_research",
        "MYSQL_HOST": "localhost",
        "RAGFLOW_API_KEY": "",
    }
    if any(assignments.get(key) != value for key, value in expected.items()):
        _invalid()
    if "your-" in text.lower():
        _invalid()


def _validate_build_context() -> None:
    entries = {
        line.strip()
        for line in DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required = {
        "data/",
        ".worktrees/",
        "frontend/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".coverage",
        "!docs/evidence/durable-hitl-gate-report.json",
    }
    if not required.issubset(entries):
        _invalid()


def _dockerfile_instructions(dockerfile: str) -> list[str]:
    instructions: list[str] = []
    current = ""
    for raw_line in dockerfile.splitlines():
        stripped = raw_line.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        continued = stripped.endswith("\\")
        component = stripped[:-1].rstrip() if continued else stripped
        current = f"{current} {component}".strip()
        if not continued:
            instructions.append(current)
            current = ""
    if current:
        _invalid()
    return instructions


def _dockerfile_json_instruction(
    instructions: list[str],
    name: str,
) -> list[str]:
    commands = [
        body
        for instruction in instructions
        for opcode, body in [_dockerfile_instruction_parts(instruction)]
        if opcode == name.upper()
    ]
    if len(commands) != 1:
        _invalid()
    try:
        command = json.loads(commands[0])
    except json.JSONDecodeError:
        _invalid()
    if type(command) is not list or any(type(value) is not str for value in command):
        _invalid()
    return command


def _dockerfile_instruction_parts(instruction: str) -> tuple[str, str]:
    parts = instruction.split(None, 1)
    if not parts:
        _invalid()
    return parts[0].upper(), parts[1] if len(parts) == 2 else ""


def _observe_container_artifacts() -> list[dict[str, Any]]:
    try:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        services = compose["services"]
        backend = services["backend"]
        mysql = services["mysql"]
    except (KeyError, TypeError, yaml.YAMLError):
        _invalid()
    if any(type(value) is not dict for value in (compose, services, backend, mysql)):
        _invalid()

    backend_ports = backend.get("ports")
    mysql_ports = mysql.get("ports")
    backend_host_ip = (
        "127.0.0.1"
        if backend_ports == ["127.0.0.1:8000:8000"]
        else "not_loopback"
    )
    mysql_host_ip = (
        "127.0.0.1"
        if mysql_ports == ["127.0.0.1:3306:3306"]
        else "not_loopback"
    )
    backend_environment = backend.get("environment")
    mysql_environment = mysql.get("environment")
    api_secret_required = (
        type(backend_environment) is dict
        and _required_interpolation(
            backend_environment.get("API_SECRET"),
            "API_SECRET",
        )
    )
    mysql_root_required = (
        type(mysql_environment) is dict
        and _required_interpolation(
            mysql_environment.get("MYSQL_ROOT_PASSWORD"),
            "MYSQL_ROOT_PASSWORD",
        )
    )
    mysql_password_required = (
        type(mysql_environment) is dict
        and _required_interpolation(
            mysql_environment.get("MYSQL_PASSWORD"),
            "MYSQL_PASSWORD",
        )
    )
    env_file_parameterized = backend.get("env_file") == [
        "${DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE:-.env}"
    ]
    depends_on = backend.get("depends_on")
    if (
        type(depends_on) is not dict
        or type(depends_on.get("mysql")) is not dict
        or depends_on["mysql"].get("condition") != "service_healthy"
    ):
        _invalid()

    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    instructions = _dockerfile_instructions(dockerfile)
    health_prefix = (
        "--interval=5s --timeout=3s --start-period=20s --retries=12 CMD "
    )
    health_instructions = [
        body
        for instruction in instructions
        for opcode, body in [_dockerfile_instruction_parts(instruction)]
        if opcode == "HEALTHCHECK"
    ]
    expected_health_command = [
        "python",
        "-c",
        (
            "import json; from urllib.request import urlopen; "
            "r=urlopen('http://127.0.0.1:8000/health', timeout=2); "
            "assert r.status == 200; assert json.load(r) == "
            "{'status':'ok','service':'decision-research-agent'}"
        ),
    ]
    backend_health = False
    if len(health_instructions) == 1 and health_instructions[0].startswith(health_prefix):
        try:
            backend_health = (
                json.loads(health_instructions[0][len(health_prefix) :])
                == expected_health_command
            )
        except json.JSONDecodeError:
            backend_health = False

    command = _dockerfile_json_instruction(instructions, "CMD")
    expected_command = [
        "uvicorn",
        "api.server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--log-level",
        "warning",
    ]
    if command != expected_command or any(
        _dockerfile_instruction_parts(instruction)[0] == "USER"
        for instruction in instructions
    ):
        _invalid()
    uvicorn_log_level = command[-1]

    mysql_health = mysql.get("healthcheck") == {
        "test": [
            "CMD-SHELL",
            'mysqladmin ping -h 127.0.0.1 -uroot -p"$${MYSQL_ROOT_PASSWORD}" --silent',
        ],
        "interval": "5s",
        "timeout": "3s",
        "retries": 12,
        "start_period": "20s",
    }
    cap_drop = backend.get("cap_drop") == ["ALL"]
    no_new_privileges = backend.get("security_opt") == [
        "no-new-privileges:true"
    ]
    _validate_env_template()
    _validate_build_context()

    return [
        _case(
            "compose_loopback_required_secrets",
            {
                "backend_host_ip": backend_host_ip,
                "mysql_host_ip": mysql_host_ip,
                "api_secret_required": api_secret_required,
                "mysql_root_password_required": mysql_root_required,
                "mysql_password_required": mysql_password_required,
                "service_env_file_parameterized": env_file_parameterized,
            },
        ),
        _case(
            "container_health_privilege_contract",
            {
                "backend_healthcheck_declared": backend_health,
                "mysql_healthcheck_declared": mysql_health,
                "cap_drop_all_declared": cap_drop,
                "no_new_privileges_declared": no_new_privileges,
                "uvicorn_log_level": uvicorn_log_level,
                "container_runtime_scope": "separate_required_lane",
            },
        ),
    ]


def _build_report_once() -> list[dict[str, Any]]:
    server, cors_config, runtime_access, run_repository = _load_production_modules()
    captured_stdout = io.StringIO()
    with redirect_stdout(captured_stdout):
        cases = [
            _case(
                "source_launcher_loopback_no_reload",
                _observe_source_launcher(server),
            ),
            *_observe_http_cases(server, cors_config, runtime_access),
            *_observe_websocket_cases(
                server,
                cors_config,
                runtime_access,
                run_repository,
            ),
            *_observe_cors_cases(cors_config, runtime_access),
            *_observe_container_artifacts(),
        ]
    return cases


def _candidate_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if [item.get("case_id") for item in cases if type(item) is dict] != list(
        EXPECTED_CASE_IDS
    ):
        _invalid()
    return validate_report(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "valid",
            "source": REPORT_SOURCE,
            "cases": cases,
            "boundaries": dict(BOUNDARIES),
            "limits": list(LIMITS),
        }
    )


def build_report() -> dict[str, Any]:
    preexisting_modules = {
        name for name in _PROOF_IMPORT_MODULES if name in sys.modules
    }
    preexisting_attributes: dict[str, object] = {}
    for name in _PROOF_IMPORT_MODULES:
        parent_name, attribute = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        preexisting_attributes[name] = (
            _MISSING if parent is None else getattr(parent, attribute, _MISSING)
        )
    try:
        first = _candidate_report(_build_report_once())
        second = _candidate_report(_build_report_once())
        if (
            serialize_report(first) != serialize_report(second)
            or render_markdown(first).encode("utf-8")
            != render_markdown(second).encode("utf-8")
        ):
            _invalid()
        return first
    finally:
        for name in _PROOF_IMPORT_MODULES:
            if name in preexisting_modules:
                continue
            sys.modules.pop(name, None)
            parent_name, attribute = name.rsplit(".", 1)
            parent = sys.modules.get(parent_name)
            if parent is None:
                continue
            previous = preexisting_attributes[name]
            if previous is _MISSING:
                if hasattr(parent, attribute):
                    delattr(parent, attribute)
            else:
                setattr(parent, attribute, previous)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise _ProofError(_INVALID_CODE)


def _bounded_read(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_size > MAX_BASELINE_BYTES
        ):
            _invalid()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or after.st_size > MAX_BASELINE_BYTES
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            _invalid()
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            value = handle.read(MAX_BASELINE_BYTES + 1)
        if len(value) > MAX_BASELINE_BYTES:
            _invalid()
        return value
    except _ProofError:
        raise
    except (OSError, ValueError) as error:
        raise _ProofError(_INVALID_CODE) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validated_baselines(
    json_path: Path,
    markdown_path: Path,
) -> tuple[bytes, bytes]:
    json_bytes = _bounded_read(json_path)
    markdown_bytes = _bounded_read(markdown_path)
    try:
        payload = json.loads(json_bytes.decode("utf-8"))
        if type(payload) is not dict:
            _invalid()
        report = validate_report(payload)
        canonical_json = serialize_report(report)
        canonical_markdown = render_markdown(report).encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _ProofError(_INVALID_CODE) from error
    if json_bytes != canonical_json or markdown_bytes != canonical_markdown:
        _invalid()
    return json_bytes, markdown_bytes


def _validate_output_path(path: Path) -> Path:
    try:
        parent = path.parent.resolve(strict=True)
        metadata = parent.stat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_mode & 0o222 == 0
            or not os.access(parent, os.W_OK)
        ):
            _invalid()
        target = parent / path.name
        try:
            target_metadata = target.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(target_metadata.st_mode) or not stat.S_ISREG(
                target_metadata.st_mode
            ):
                _invalid()
        return target
    except _ProofError:
        raise
    except (OSError, RuntimeError) as error:
        raise _ProofError(_INVALID_CODE) from error


def _validated_output_paths(
    json_path: Path,
    markdown_path: Path,
) -> tuple[Path, Path]:
    json_target = _validate_output_path(json_path)
    markdown_target = _validate_output_path(markdown_path)
    try:
        resolved_alias = json_target.resolve(strict=False) == markdown_target.resolve(
            strict=False
        )
        inode_alias = (
            json_target.exists()
            and markdown_target.exists()
            and os.path.samefile(json_target, markdown_target)
        )
        if resolved_alias or inode_alias:
            _invalid()
    except _ProofError:
        raise
    except (OSError, RuntimeError) as error:
        raise _ProofError(_INVALID_CODE) from error
    return json_target, markdown_target


def _stage_output(target: Path, content: bytes) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary_path
    except Exception as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise _ProofError(_INVALID_CODE) from error


def _write_outputs(
    json_path: Path,
    markdown_path: Path,
    json_content: bytes,
    markdown_content: bytes,
) -> None:
    json_target, markdown_target = _validated_output_paths(
        json_path,
        markdown_path,
    )
    staged: list[Path] = []
    try:
        json_temporary = _stage_output(json_target, json_content)
        staged.append(json_temporary)
        markdown_temporary = _stage_output(markdown_target, markdown_content)
        staged.append(markdown_temporary)
        os.replace(json_temporary, json_target)
        staged.remove(json_temporary)
        os.replace(markdown_temporary, markdown_target)
        staged.remove(markdown_temporary)
    except _ProofError:
        raise
    except Exception as error:
        raise _ProofError(_INVALID_CODE) from error
    finally:
        for temporary_path in staged:
            temporary_path.unlink(missing_ok=True)


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--json-output", required=True)
    build.add_argument("--markdown-output", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--json-baseline", default=str(BASELINE_JSON_PATH))
    check.add_argument(
        "--markdown-baseline",
        default=str(BASELINE_MARKDOWN_PATH),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "build":
            json_path, markdown_path = _validated_output_paths(
                Path(args.json_output),
                Path(args.markdown_output),
            )
            report = build_report()
            _write_outputs(
                json_path,
                markdown_path,
                serialize_report(report),
                render_markdown(report).encode("utf-8"),
            )
            print('{"status":"built"}')
        else:
            baseline_json, baseline_markdown = _validated_baselines(
                Path(args.json_baseline),
                Path(args.markdown_baseline),
            )
            report = build_report()
            if (
                serialize_report(report) != baseline_json
                or render_markdown(report).encode("utf-8") != baseline_markdown
            ):
                _invalid()
            print('{"status":"valid","match":true}')
        return 0
    except Exception:
        print(
            '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}',
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
