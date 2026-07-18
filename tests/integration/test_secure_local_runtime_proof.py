from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import sys

import pytest
import yaml

from api.runtime_access import AccessDecision
from scripts import secure_local_runtime_proof as proof
from scripts.secure_local_runtime_contracts import (
    BOUNDARIES,
    EXPECTED_CASE_IDS,
    EXPECTED_OBSERVATIONS,
    LIMITS,
    render_markdown,
    serialize_report,
    validate_report,
)


def _assert_check_fails_closed(valid_report, tmp_path, capsys) -> None:
    json_path = tmp_path / "mutation-baseline.json"
    markdown_path = tmp_path / "mutation-baseline.md"
    json_path.write_bytes(serialize_report(valid_report))
    markdown_path.write_text(render_markdown(valid_report), encoding="utf-8")

    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_path),
            "--markdown-baseline",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )


def test_build_report_crosses_real_production_paths_and_is_byte_stable():
    first = proof.build_report()
    second = proof.build_report()

    assert validate_report(first) is first
    assert first["schema_version"] == "dra.secure-local-runtime.v1"
    assert first["source"] == "production_path_deterministic_local"
    assert [item["case_id"] for item in first["cases"]] == list(
        EXPECTED_CASE_IDS
    )
    assert [item["observations"] for item in first["cases"]] == [
        EXPECTED_OBSERVATIONS[case_id] for case_id in EXPECTED_CASE_IDS
    ]
    assert first["boundaries"] == BOUNDARIES
    assert first["limits"] == LIMITS
    assert serialize_report(first) == serialize_report(second)
    assert render_markdown(first) == render_markdown(second)


def test_backend_ci_requires_proof_before_non_docker_tests_only():
    workflow = yaml.safe_load(
        (proof.PROJECT_ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
    )
    backend_steps = workflow["jobs"]["backend"]["steps"]
    expected = {
        "name": "Run secure local runtime proof",
        "env": {"PYTHON_DOTENV_DISABLED": "1"},
        "run": "python scripts/secure_local_runtime_proof.py check",
    }

    assert expected in backend_steps
    assert backend_steps.index(expected) < next(
        index
        for index, step in enumerate(backend_steps)
        if step.get("run") == 'python -m pytest -q -m "not docker"'
    )
    assert expected not in workflow["jobs"]["container"]["steps"]
    assert sum(
        step == expected
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ) == 1


def test_builder_observes_production_http_websocket_and_cors_symbols(
    monkeypatch,
):
    import api.cors_config as cors_config
    import api.server as server

    transports: list[str] = []
    cors_calls = 0
    real_decide = server.decide_runtime_access
    real_load_cors = cors_config.load_cors_configuration

    def observe_decision(*args, **kwargs):
        decision = real_decide(*args, **kwargs)
        transports.append(args[1].transport)
        return decision

    def observe_cors(*args, **kwargs):
        nonlocal cors_calls
        cors_calls += 1
        return real_load_cors(*args, **kwargs)

    monkeypatch.setattr(server, "decide_runtime_access", observe_decision)
    monkeypatch.setattr(cors_config, "load_cors_configuration", observe_cors)

    report = proof.build_report()
    assert validate_report(report) is report
    assert set(transports) == {"http", "websocket"}
    assert transports.count("http") >= 18
    assert transports.count("websocket") >= 6
    assert cors_calls >= 20


def test_bypassing_the_production_access_policy_fails_closed(
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    import api.server as server

    monkeypatch.setattr(
        server,
        "decide_runtime_access",
        lambda *_args, **_kwargs: AccessDecision(
            allowed=True,
            code="allowed_loopback",
        ),
    )

    _assert_check_fails_closed(valid_report, tmp_path, capsys)


def test_restoring_websocket_query_credentials_fails_closed(
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    import api.server as server

    real_builder = server.build_websocket_access_context

    def ignore_query_credential(websocket):
        return real_builder(websocket).model_copy(
            update={"query_credential_present": False}
        )

    monkeypatch.setattr(
        server,
        "build_websocket_access_context",
        ignore_query_credential,
    )

    _assert_check_fails_closed(valid_report, tmp_path, capsys)


@pytest.mark.parametrize(
    "mutation",
    (
        "widen_backend",
        "remove_cap_drop",
        "weaken_mysql_health",
        "comment_backend_health",
        "enable_container_reload",
        "tabbed_user_instruction",
    ),
)
def test_container_artifact_mutations_fail_closed(
    mutation,
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    compose = yaml.safe_load(proof.COMPOSE_PATH.read_text(encoding="utf-8"))
    if mutation == "widen_backend":
        compose["services"]["backend"]["ports"] = ["8000:8000"]
    elif mutation == "remove_cap_drop":
        compose["services"]["backend"].pop("cap_drop")
    elif mutation == "weaken_mysql_health":
        compose["services"]["mysql"]["healthcheck"] = {
            "test": ["CMD", "true"]
        }
    if mutation in {"widen_backend", "remove_cap_drop", "weaken_mysql_health"}:
        mutated = tmp_path / "docker-compose.yml"
        mutated.write_text(
            yaml.safe_dump(compose, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(proof, "COMPOSE_PATH", mutated)
    else:
        dockerfile = proof.DOCKERFILE_PATH.read_text(encoding="utf-8")
        if mutation == "comment_backend_health":
            dockerfile = dockerfile.replace("\nHEALTHCHECK ", "\n# HEALTHCHECK ")
        elif mutation == "enable_container_reload":
            dockerfile = dockerfile.replace(
                '", "--log-level", "warning"]',
                '", "--log-level", "warning", "--reload"]',
            )
        else:
            dockerfile = dockerfile.replace(
                "\n# Start the FastAPI server",
                "\nUSER\t1000\n\n# Start the FastAPI server",
            )
        mutated = tmp_path / "Dockerfile.backend"
        mutated.write_text(dockerfile, encoding="utf-8")
        monkeypatch.setattr(proof, "DOCKERFILE_PATH", mutated)

    _assert_check_fails_closed(valid_report, tmp_path, capsys)


def test_false_launcher_observation_fails_closed(
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        proof,
        "_observe_source_launcher",
        lambda _server: {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False,
            "log_level": "warning",
        },
    )

    _assert_check_fails_closed(valid_report, tmp_path, capsys)


def test_reordered_production_cases_fail_closed(
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    real_build_once = proof._build_report_once

    def reversed_cases():
        return list(reversed(real_build_once()))

    monkeypatch.setattr(proof, "_build_report_once", reversed_cases)

    _assert_check_fails_closed(valid_report, tmp_path, capsys)


@pytest.fixture(scope="module")
def valid_report():
    return proof.build_report()


def test_cli_build_and_check_emit_exact_stable_success_lines(
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"
    monkeypatch.setattr(proof, "build_report", lambda: deepcopy(valid_report))

    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"status":"built"}\n'
    assert captured.err == ""
    assert json_output.read_bytes() == serialize_report(valid_report)
    assert markdown_output.read_text(encoding="utf-8") == render_markdown(
        valid_report
    )

    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_output),
            "--markdown-baseline",
            str(markdown_output),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"status":"valid","match":true}\n'
    assert captured.err == ""


@pytest.mark.parametrize(
    "arguments",
    (
        [],
        ["unknown"],
        ["build"],
        ["build", "--json-output", "candidate.json"],
        ["check", "extra"],
        ["check", "--unknown-option"],
    ),
)
def test_invalid_cli_arguments_are_one_stable_error_line(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/secure_local_runtime_proof.py", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )


@pytest.mark.parametrize(
    "arguments",
    (["--help"], ["build", "--help"], ["check", "--help"]),
)
def test_help_succeeds_and_module_import_is_silent(arguments):
    completed = subprocess.run(
        [sys.executable, "scripts/secure_local_runtime_proof.py", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert completed.returncode == 0
    assert completed.stdout.startswith("usage:")
    assert completed.stderr == ""

    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import scripts.secure_local_runtime_proof; "
                "raise SystemExit(1 if 'api.server' in sys.modules else 0)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )
    assert imported.returncode == 0
    assert imported.stdout == imported.stderr == ""


def test_file_cli_build_succeeds_without_provider_credentials(tmp_path):
    json_output = tmp_path / "candidate.json"
    markdown_output = tmp_path / "candidate.md"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "OPENAI_API_KEY",
            "OPENAI_ADMIN_KEY",
            "API_SECRET",
            "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN",
        }
    }
    environment["PYTHON_DOTENV_DISABLED"] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/secure_local_runtime_proof.py",
            "build",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == '{"status":"built"}\n'
    assert completed.stderr == ""
    report = validate_report(json.loads(json_output.read_text(encoding="utf-8")))
    assert markdown_output.read_text(encoding="utf-8") == render_markdown(report)


def test_first_library_build_does_not_retain_synthetic_production_state():
    code = """
import os
import sys

from scripts.secure_local_runtime_proof import build_report

owned = ("api.server", "agent.main_agent", "agent.llm")
assert all(name not in sys.modules for name in owned)
before = {
    "API_SECRET": os.environ["API_SECRET"],
    "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
}
build_report()
assert all(name not in sys.modules for name in owned)
assert {key: os.environ[key] for key in before} == before

import api
import agent

assert "server" not in vars(api)
assert "main_agent" not in vars(agent)
assert "llm" not in vars(agent)

from api import server
from agent import llm

assert server.runtime_access_policy.secret_value == "caller-configured"
assert server.app.state.runtime_access_policy.secret_value == "caller-configured"
models = (
    (llm.model.primary, llm.model.fallback)
    if hasattr(llm.model, "primary")
    else (llm.model,)
)
assert all(
    item.wrapped.openai_api_key.get_secret_value() == "caller-provider"
    for item in models
)
"""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "API_SECRET",
            "OPENAI_API_KEY",
            "OPENAI_ADMIN_KEY",
            "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN",
        }
    }
    environment.update(
        {
            "API_SECRET": "caller-configured",
            "OPENAI_API_KEY": "caller-provider",
            "PYTHON_DOTENV_DISABLED": "1",
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == completed.stderr == ""


@pytest.mark.parametrize(
    "mode",
    (
        "missing",
        "corrupt",
        "semantic",
        "oversized",
        "symlink",
        "directory",
        "incoherent",
    ),
)
def test_check_rejects_invalid_baselines_before_building(
    mode,
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "baseline.json"
    markdown_path = tmp_path / "baseline.md"
    json_path.write_bytes(serialize_report(valid_report))
    markdown_path.write_text(render_markdown(valid_report), encoding="utf-8")
    if mode == "missing":
        json_path.unlink()
    elif mode == "corrupt":
        json_path.write_bytes(b"{not-json")
    elif mode == "semantic":
        malformed = deepcopy(valid_report)
        malformed["cases"][0]["observations"]["host"] = "0.0.0.0"
        json_path.write_text(
            json.dumps(malformed, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
    elif mode == "oversized":
        with json_path.open("wb") as handle:
            handle.truncate(proof.MAX_BASELINE_BYTES + 1)
    elif mode == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(serialize_report(valid_report))
        json_path.unlink()
        json_path.symlink_to(target)
    elif mode == "directory":
        json_path.unlink()
        json_path.mkdir()
    else:
        markdown_path.write_text("# stale\n", encoding="utf-8")

    def unexpected_build():
        pytest.fail("invalid baselines must fail before production observation")

    monkeypatch.setattr(proof, "build_report", unexpected_build)
    assert proof.main(
        [
            "check",
            "--json-baseline",
            str(json_path),
            "--markdown-baseline",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )


@pytest.mark.parametrize(
    "mode",
    ("same", "hardlink", "symlink", "directory", "missing_parent", "unwritable"),
)
def test_build_rejects_invalid_or_aliasing_outputs_before_observation(
    mode,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    restore_mode = None
    if mode == "same":
        markdown_path = json_path
    elif mode == "hardlink":
        json_path.write_text("old", encoding="utf-8")
        os.link(json_path, markdown_path)
    elif mode == "symlink":
        target = tmp_path / "target.md"
        target.write_text("old", encoding="utf-8")
        markdown_path.symlink_to(target)
    elif mode == "directory":
        markdown_path.mkdir()
    elif mode == "missing_parent":
        markdown_path = tmp_path / "missing" / "candidate.md"
    else:
        locked = tmp_path / "locked"
        locked.mkdir()
        restore_mode = locked.stat().st_mode
        locked.chmod(0o500)
        json_path = locked / "candidate.json"
        markdown_path = locked / "candidate.md"

    def unexpected_build():
        pytest.fail("invalid outputs must fail before production observation")

    monkeypatch.setattr(proof, "build_report", unexpected_build)
    try:
        assert proof.main(
            [
                "build",
                "--json-output",
                str(json_path),
                "--markdown-output",
                str(markdown_path),
            ]
        ) == 1
    finally:
        if restore_mode is not None:
            json_path.parent.chmod(restore_mode)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )


@pytest.mark.parametrize("failure_index", (1, 2))
def test_build_write_failure_preserves_targets_and_cleans_sibling_temps(
    failure_index,
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    json_path.write_bytes(b"old-json")
    markdown_path.write_bytes(b"old-markdown")
    monkeypatch.setattr(proof, "build_report", lambda: deepcopy(valid_report))
    real_stage = proof._stage_output
    calls = 0

    def fail_selected_stage(target, content):
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected write failure")
        return real_stage(target, content)

    monkeypatch.setattr(proof, "_stage_output", fail_selected_stage)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )
    assert json_path.read_bytes() == b"old-json"
    assert markdown_path.read_bytes() == b"old-markdown"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "candidate.json",
        "candidate.md",
    ]


@pytest.mark.parametrize("failure_index", (1, 2))
def test_build_replace_failure_keeps_whole_files_and_cleans_sibling_temps(
    failure_index,
    valid_report,
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"
    json_path.write_bytes(b"old-json")
    markdown_path.write_bytes(b"old-markdown")
    monkeypatch.setattr(proof, "build_report", lambda: deepcopy(valid_report))
    real_replace = proof.os.replace
    calls = 0

    def fail_selected_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(proof.os, "replace", fail_selected_replace)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )
    expected_json = serialize_report(valid_report)
    assert json_path.read_bytes() == (
        b"old-json" if failure_index == 1 else expected_json
    )
    assert markdown_path.read_bytes() == b"old-markdown"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "candidate.json",
        "candidate.md",
    ]


def test_unexpected_observation_error_maps_to_stable_fail_closed_cli(
    tmp_path,
    monkeypatch,
    capsys,
):
    json_path = tmp_path / "candidate.json"
    markdown_path = tmp_path / "candidate.md"

    def broken_build():
        raise RuntimeError("private production diagnostic")

    monkeypatch.setattr(proof, "build_report", broken_build)
    assert proof.main(
        [
            "build",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        '{"status":"invalid","code":"secure_local_runtime_proof_invalid"}\n'
    )
    assert list(tmp_path.iterdir()) == []


def test_two_fresh_builds_are_byte_identical_and_public_safe(tmp_path, capsys):
    outputs = [
        (tmp_path / f"fresh-{index}.json", tmp_path / f"fresh-{index}.md")
        for index in (1, 2)
    ]
    for json_path, markdown_path in outputs:
        assert proof.main(
            [
                "build",
                "--json-output",
                str(json_path),
                "--markdown-output",
                str(markdown_path),
            ]
        ) == 0
        captured = capsys.readouterr()
        assert captured.out == '{"status":"built"}\n'
        assert captured.err == ""

    first = outputs[0][0].read_bytes() + b"\n" + outputs[0][1].read_bytes()
    second = outputs[1][0].read_bytes() + b"\n" + outputs[1][1].read_bytes()
    assert first == second
    forbidden = (
        b"api_key=",
        b"API_SECRET=",
        b"proof-only-api-secret",
        b"test-secret",
        b"Traceback (most recent call last)",
        b"/Users/",
        b"/private/tmp/",
        b"api.openai.com",
    )
    assert all(marker not in first for marker in forbidden)
