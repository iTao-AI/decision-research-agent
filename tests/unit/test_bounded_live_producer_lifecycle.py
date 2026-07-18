from __future__ import annotations

import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

import pytest
import yaml

from scripts.bounded_live_producer_contracts import (
    EvaluationError,
    FailureCode,
    FailurePhase,
)
from scripts.bounded_live_producer_lifecycle import (
    LIVE_BUDGET,
    ActiveDeadline,
    CredentialDeclaration,
    LifecycleBudget,
    ManagedComposeProject,
    _validate_and_extract_archive,
    cleanup_receipt,
    load_live_configuration,
    prepare_source_snapshot,
    run_bounded_subprocess,
    sanitize_compose_projection,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _tiny_repository(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "VERSION").write_text("0.1.5\n", encoding="utf-8")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "Dockerfile.backend").write_text("FROM scratch\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "secure_local_runtime_proof.py").write_text(
        "print('ok')\n", encoding="utf-8"
    )
    _git(root, "add", "VERSION", "docker-compose.yml", "Dockerfile.backend", "scripts")
    _git(root, "commit", "-qm", "fixture")
    return root


REQUIRED_PATHS = (
    "VERSION",
    "docker-compose.yml",
    "Dockerfile.backend",
    "scripts/secure_local_runtime_proof.py",
)


def _declaration(**changes: object) -> CredentialDeclaration:
    values: dict[str, object] = {
        "provider_id": "openai-compatible",
        "provider_base_url": "https://api.openai.com/v1",
        "primary_model": "gpt-5",
        "fallback_model": "gpt-5-mini",
        "pricing_basis": None,
        "pricing_currency": None,
    }
    values.update(changes)
    return CredentialDeclaration(**values)


def _valid_env() -> dict[str, str]:
    return {
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_API_KEY": "provider-secret",
        "LLM_MODEL": "gpt-5",
        "LLM_FALLBACK_MODEL": "gpt-5-mini",
        "API_SECRET": "service-secret",
        "TAVILY_API_KEY": "search-secret",
        "MYSQL_ROOT_PASSWORD": "root-secret",
        "MYSQL_USER": "decision_research",
        "MYSQL_PASSWORD": "mysql-secret",
        "MYSQL_DATABASE": "decision_research",
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL": "false",
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION": "false",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
        "RAGFLOW_API_KEY": "",
    }


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    path.chmod(0o600)


def _compose_projection() -> dict[str, object]:
    project_name = "dra-proof-11111111111111111111111111111111"
    return {
        "name": project_name,
        "services": {
            "backend": {
                "build": {"context": "/task/snapshot", "dockerfile": "Dockerfile.backend"},
                "command": None,
                "entrypoint": None,
                "environment": {
                    "API_SECRET": "service-secret",
                    "OPENAI_API_KEY": "provider-secret",
                    "TAVILY_API_KEY": "search-secret",
                    "MYSQL_PASSWORD": "mysql-secret",
                    "MYSQL_ROOT_PASSWORD": "",
                    "MYSQL_HOST": "mysql",
                    "MYSQL_PORT": "3306",
                    "DECISION_RESEARCH_AGENT_DB_PATH": "/app/data/decision_research_agent.db",
                    "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH": "/app/data/review_checkpoints.db",
                },
                "ports": [{"target": 8000, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp", "mode": "ingress"}],
                "volumes": [
                    {
                        "type": "volume",
                        "source": f"{project_name}_backend_data",
                        "target": "/app/data",
                    },
                    {
                        "type": "volume",
                        "source": f"{project_name}_backend_output",
                        "target": "/app/output",
                    },
                ],
                "networks": {"app-network": None},
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "depends_on": {"mysql": {"condition": "service_healthy", "required": True}},
            },
            "mysql": {
                "command": None,
                "entrypoint": None,
                "image": "mysql:8.0",
                "environment": {
                    "MYSQL_ROOT_PASSWORD": "root-secret",
                    "MYSQL_DATABASE": "decision_research",
                    "MYSQL_USER": "decision_research",
                    "MYSQL_PASSWORD": "mysql-secret",
                },
                "ports": [{"target": 3306, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp", "mode": "ingress"}],
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        'mysqladmin ping -h 127.0.0.1 -uroot -p"$${MYSQL_ROOT_PASSWORD}" --silent',
                    ],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                    "start_period": "20s",
                },
                "volumes": [
                    {
                        "type": "volume",
                        "source": f"{project_name}_mysql_data",
                        "target": "/var/lib/mysql",
                    }
                ],
                "networks": {"app-network": None},
            },
        },
        "volumes": {
            "backend_data": {"name": f"{project_name}_backend_data"},
            "backend_output": {"name": f"{project_name}_backend_output"},
            "mysql_data": {"name": f"{project_name}_mysql_data"},
        },
        "networks": {
            "app-network": {
                "name": f"{project_name}_app-network",
                "driver": "bridge",
                "ipam": {},
            }
        },
    }


def test_live_budget_is_exact_and_frozen() -> None:
    assert LIVE_BUDGET == LifecycleBudget(30, 3300, 1200, 1800, 300, 120, 3450)
    with pytest.raises((AttributeError, TypeError)):
        LIVE_BUDGET.active_seconds = 1  # type: ignore[misc]


def test_active_deadline_uses_only_remaining_time_and_never_goes_negative() -> None:
    readings = iter([10.0, 12.0, 14.5, 15.0])
    deadline = ActiveDeadline(
        5,
        code=FailureCode.RUN_OBSERVATION_DEADLINE,
        phase=FailurePhase.OBSERVE,
        monotonic=lambda: next(readings),
    )
    assert deadline.remaining(10) == 3.0
    assert deadline.remaining(10) == 0.5
    with pytest.raises(EvaluationError) as raised:
        deadline.remaining(10)
    assert raised.value.code is FailureCode.RUN_OBSERVATION_DEADLINE


def test_child_deadline_cannot_extend_parent_and_cleanup_is_independent() -> None:
    now = [100.0]
    clock = lambda: now[0]
    active = ActiveDeadline(
        3300,
        code=FailureCode.SERVICE_START_FAILED,
        phase=FailurePhase.DOCKER,
        monotonic=clock,
    )
    now[0] = 3200.0
    child = active.child(
        1200,
        code=FailureCode.SERVICE_START_FAILED,
        phase=FailurePhase.DOCKER,
    )
    assert child.remaining(1200) == 200.0
    cleanup = ActiveDeadline(
        LIVE_BUDGET.cleanup_seconds,
        code=FailureCode.CLEANUP_FAILED,
        phase=FailurePhase.CLEANUP,
        monotonic=clock,
    )
    assert cleanup.remaining(999) == 120.0


def test_prepare_source_snapshot_binds_clean_exact_tracked_archive(tmp_path: Path) -> None:
    source = _tiny_repository(tmp_path)
    snapshot = prepare_source_snapshot(
        source,
        tmp_path / "tasks",
        required_paths=REQUIRED_PATHS,
        archive_bytes_max=64 * 1024 * 1024,
        archive_members_max=32,
        archive_member_bytes_max=1024,
    )
    assert snapshot.commit == _git(source, "rev-parse", "HEAD")
    assert snapshot.tree == _git(source, "rev-parse", "HEAD^{tree}")
    assert snapshot.version == "0.1.5"
    assert len(snapshot.archive_sha256) == 64
    assert snapshot.members == tuple(_git(source, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    assert snapshot.root.is_dir()
    assert (snapshot.root / "VERSION").read_text(encoding="utf-8") == "0.1.5\n"


@pytest.mark.parametrize("dirty_name", ["untracked.txt", "VERSION"])
def test_prepare_source_snapshot_rejects_dirty_or_untracked_source(
    tmp_path: Path, dirty_name: str
) -> None:
    source = _tiny_repository(tmp_path)
    (source / dirty_name).write_text("dirty\n", encoding="utf-8")
    with pytest.raises(EvaluationError) as raised:
        prepare_source_snapshot(source, tmp_path / "tasks", required_paths=REQUIRED_PATHS)
    assert raised.value.code is FailureCode.SOURCE_DIRTY
    assert not (tmp_path / "tasks").exists()


def test_prepare_source_snapshot_rejects_missing_required_tracked_path(tmp_path: Path) -> None:
    source = _tiny_repository(tmp_path)
    with pytest.raises(EvaluationError) as raised:
        prepare_source_snapshot(
            source, tmp_path / "tasks", required_paths=(*REQUIRED_PATHS, "missing.txt")
        )
    assert raised.value.code is FailureCode.SOURCE_IDENTITY_INVALID


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("/absolute", "file"),
        ("../escape", "file"),
        ("dir\\escape", "file"),
        ("link", "symlink"),
        ("hard", "hardlink"),
        ("device", "device"),
    ],
)
def test_archive_validation_rejects_unsafe_members(
    tmp_path: Path, name: str, kind: str
) -> None:
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as handle:
        member = tarfile.TarInfo(name)
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "target"
        elif kind == "hardlink":
            member.type = tarfile.LNKTYPE
            member.linkname = "target"
        elif kind == "device":
            member.type = tarfile.CHRTYPE
        else:
            member.size = 1
            handle.addfile(member, io.BytesIO(b"x"))
            member = None
        if member is not None:
            handle.addfile(member)
    with pytest.raises(EvaluationError) as raised:
        _validate_and_extract_archive(
            archive,
            tmp_path / "extract",
            expected_members=(name,),
            archive_bytes_max=1024 * 1024,
            archive_members_max=10,
            archive_member_bytes_max=1024,
        )
    assert raised.value.code is FailureCode.SOURCE_ARCHIVE_INVALID


def test_archive_validation_rejects_case_collisions_and_incomplete_membership(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as handle:
        for name in ("A.txt", "a.txt"):
            member = tarfile.TarInfo(name)
            member.size = 1
            handle.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(EvaluationError):
        _validate_and_extract_archive(
            archive,
            tmp_path / "extract",
            expected_members=("A.txt", "a.txt", "missing.txt"),
            archive_bytes_max=1024 * 1024,
            archive_members_max=10,
            archive_member_bytes_max=1024,
        )


def test_load_live_configuration_accepts_owner_only_file_and_matching_declaration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "live.env"
    _write_env(path, _valid_env())
    loaded = load_live_configuration(path, _declaration(), process_api_key="service-secret")
    assert loaded["LLM_MODEL"] == "gpt-5"
    assert loaded["LANGSMITH_API_KEY"] == ""


@pytest.mark.parametrize("mode", [0o004, 0o040, 0o200])
def test_load_live_configuration_rejects_unsafe_permissions(
    tmp_path: Path, mode: int
) -> None:
    path = tmp_path / "live.env"
    _write_env(path, _valid_env())
    path.chmod(mode)
    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(path, _declaration(), process_api_key="service-secret")
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


def test_load_live_configuration_rejects_symlink_unknown_duplicate_and_api_mismatch(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.env"
    _write_env(target, _valid_env())
    link = tmp_path / "link.env"
    link.symlink_to(target)
    with pytest.raises(EvaluationError):
        load_live_configuration(link, _declaration(), process_api_key="service-secret")

    values = _valid_env()
    values["HTTP_PROXY"] = "http://proxy.invalid"
    _write_env(target, values)
    with pytest.raises(EvaluationError):
        load_live_configuration(target, _declaration(), process_api_key="service-secret")

    _write_env(target, _valid_env())
    with target.open("a", encoding="utf-8") as handle:
        handle.write("API_SECRET=again\n")
    with pytest.raises(EvaluationError):
        load_live_configuration(target, _declaration(), process_api_key="service-secret")

    _write_env(target, _valid_env())
    with pytest.raises(EvaluationError):
        load_live_configuration(target, _declaration(), process_api_key="different")


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "https://user@api.openai.com/v1",
        "https://api.openai.com:8443/v1",
        "https://api.openai.com/v1?x=1",
        "https://127.0.0.1/v1",
        "https://service.internal/v1",
        "https://api.openai.com/other",
    ],
)
def test_credential_declaration_rejects_unsafe_provider_urls(url: str) -> None:
    with pytest.raises(ValueError):
        _declaration(provider_base_url=url)


def test_load_live_configuration_validates_flags_privacy_and_pricing_bundle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "live.env"
    values = _valid_env()
    values["LANGSMITH_TRACING"] = "true"
    _write_env(path, values)
    with pytest.raises(EvaluationError):
        load_live_configuration(path, _declaration(), process_api_key="service-secret")

    values = _valid_env()
    values.update(
        {
            "TOKEN_PRICING_JSON": '{"input":"0.10000000","output":"0.20000000"}',
            "TOKEN_PRICING_BASIS": "openai-public-2026-07",
            "TOKEN_PRICING_CURRENCY": "USD",
        }
    )
    _write_env(path, values)
    loaded = load_live_configuration(
        path,
        _declaration(
            pricing_basis="openai-public-2026-07", pricing_currency="USD"
        ),
        process_api_key="service-secret",
    )
    assert loaded["TOKEN_PRICING_CURRENCY"] == "USD"


def test_sanitize_compose_projection_redacts_secrets_paths_and_names_deterministically() -> None:
    first = sanitize_compose_projection(_compose_projection())
    second = sanitize_compose_projection(_compose_projection())
    assert first == second
    encoded = json.dumps(first, sort_keys=True)
    for forbidden in (
        "service-secret",
        "provider-secret",
        "search-secret",
        "mysql-secret",
        "root-secret",
        "/task/snapshot",
        "dra-proof-11111111111111111111111111111111",
        "dra-proof-11111111111111111111111111111111_backend_data",
    ):
        assert forbidden not in encoded
    assert first["services"]["backend"]["ports"][0]["published"] == 0
    assert first["services"]["backend"]["ports"][0]["host_ip"] == "127.0.0.1"


def test_sanitize_compose_projection_rejects_unknown_secret_and_shape_mutations() -> None:
    payload = _compose_projection()
    payload["services"]["backend"]["environment"]["NEW_TOKEN"] = "secret"  # type: ignore[index]
    with pytest.raises(EvaluationError) as raised:
        sanitize_compose_projection(payload)
    assert raised.value.code is FailureCode.COMPOSE_CONFIG_INVALID

    payload = _compose_projection()
    payload["services"]["backend"]["ports"][0]["host_ip"] = "0.0.0.0"  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["services"]["redis"] = {}  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["services"]["backend"]["build"]["args"] = {"SECRET": "value"}  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["services"]["backend"]["depends_on"]["mysql"]["condition"] = "service_started"  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["services"]["mysql"]["healthcheck"]["retries"] = 99  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["volumes"]["backend_data"]["labels"] = {"TOKEN": "secret"}  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["networks"]["app-network"]["labels"] = {"TOKEN": "secret"}  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)

    payload = _compose_projection()
    payload["services"]["backend"]["entrypoint"] = ["sh"]  # type: ignore[index]
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(payload)


def test_run_bounded_subprocess_captures_both_streams_and_scrubs_environment(
    tmp_path: Path,
) -> None:
    result = run_bounded_subprocess(
        [
            sys.executable,
            "-c",
            "import os,sys; print(os.getenv('PATH','')); print(os.getenv('OPENAI_API_KEY','missing')); print('err', file=sys.stderr)",
        ],
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "OPENAI_API_KEY": "must-not-leak"},
        deadline=ActiveDeadline(
            5, code=FailureCode.SERVICE_START_FAILED, phase=FailurePhase.DOCKER
        ),
        allowed_environment=("PATH",),
        stream_bytes_max=1024,
    )
    assert "missing" in result.stdout
    assert result.stderr == "err\n"


def test_run_bounded_subprocess_rejects_overflow_and_kills_timeout(tmp_path: Path) -> None:
    deadline = ActiveDeadline(
        5, code=FailureCode.SERVICE_START_FAILED, phase=FailurePhase.DOCKER
    )
    with pytest.raises(EvaluationError):
        run_bounded_subprocess(
            [sys.executable, "-c", "print('x' * 2048)"],
            cwd=tmp_path,
            env={},
            deadline=deadline,
            allowed_environment=(),
            stream_bytes_max=1024,
        )
    with pytest.raises(EvaluationError) as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            cwd=tmp_path,
            env={},
            deadline=ActiveDeadline(
                0.05,
                code=FailureCode.SERVICE_START_FAILED,
                phase=FailurePhase.DOCKER,
            ),
            allowed_environment=(),
            stream_bytes_max=1024,
        )
    assert raised.value.code is FailureCode.SERVICE_START_FAILED


def test_managed_compose_project_uses_exact_paths_services_ports_and_ownership(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args[-3:] == ("ps", "-aq",):
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-0123456789abcdef0123456789abcdef",
        environment={"PATH": os.environ.get("PATH", "")},
        runner=runner,
    )
    project.assert_unclaimed(ActiveDeadline(5, code=FailureCode.COMPOSE_CONFIG_INVALID, phase=FailurePhase.DOCKER))
    project.build_backend(ActiveDeadline(5, code=FailureCode.IMAGE_BUILD_FAILED, phase=FailurePhase.DOCKER))
    project.start_mysql(ActiveDeadline(5, code=FailureCode.SERVICE_START_FAILED, phase=FailurePhase.DOCKER))
    project.start_backend(ActiveDeadline(5, code=FailureCode.SERVICE_START_FAILED, phase=FailurePhase.DOCKER))
    flattened = "\n".join(" ".join(command) for command in commands)
    assert "--env-file" in flattened
    assert "--project-name dra-proof-0123456789abcdef0123456789abcdef" in flattened
    assert "build backend" in flattened
    assert "up -d mysql" in flattened
    assert "up -d backend" in flattened
    assert project.port_overrides == {
        "DECISION_RESEARCH_AGENT_BACKEND_HOST_PORT": "0",
        "DECISION_RESEARCH_AGENT_MYSQL_HOST_PORT": "0",
    }


def test_managed_compose_project_refuses_preexisting_exact_project_resource(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        output = "preexisting-container\n" if args[1:3] == ("container", "ls") else ""
        return subprocess.CompletedProcess(args, 0, output, "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-11111111111111111111111111111111",
        environment={},
        runner=runner,
    )
    with pytest.raises(EvaluationError) as raised:
        project.assert_unclaimed(
            ActiveDeadline(
                5,
                code=FailureCode.COMPOSE_CONFIG_INVALID,
                phase=FailurePhase.DOCKER,
            )
        )
    assert raised.value.code is FailureCode.COMPOSE_CONFIG_INVALID


def test_managed_compose_project_preflight_includes_stopped_containers(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-33333333333333333333333333333333",
        environment={},
        runner=runner,
    )
    project.assert_unclaimed(
        ActiveDeadline(
            5, code=FailureCode.COMPOSE_CONFIG_INVALID, phase=FailurePhase.DOCKER
        )
    )
    container_command = next(command for command in commands if command[1] == "container")
    assert "-a" in container_command


def test_cleanup_receipt_uses_recorded_ids_fixed_order_and_preserves_preexisting_images(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    task_temp = tmp_path / "owned-temp"
    task_temp.mkdir()
    calls: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if len(args) >= 3 and args[2] == "inspect":
            return subprocess.CompletedProcess(args, 1, "", "not found")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-fedcba9876543210fedcba9876543210",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=("container-backend", "container-mysql"),
        volume_ids=("volume-backend", "volume-mysql"),
        network_ids=("network-app",),
        image_tag="dra-proof-image:fedcba9876543210fedcba9876543210",
        image_id="sha256:" + "a" * 64,
        temp_paths=(task_temp,),
    )
    receipt = cleanup_receipt(
        project,
        ActiveDeadline(5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP),
    )
    assert receipt["attempted"] is True
    assert receipt["succeeded"] is True
    assert not task_temp.exists()
    flattened = "\n".join(" ".join(command) for command in calls)
    assert "down -v --remove-orphans" in flattened
    assert "image rm dra-proof-image:fedcba9876543210fedcba9876543210" in flattened
    assert "prune" not in flattened
    assert "--rmi" not in flattened
    assert "mysql:8.0" not in flattened


def test_cleanup_receipt_removes_tracked_temp_before_resource_receipt_exists(
    tmp_path: Path,
) -> None:
    task_temp = tmp_path / "owned-temp"
    root = task_temp / "snapshot-build" / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-55555555555555555555555555555555",
        environment={},
        runner=runner,
    )
    project.track_temp_paths((task_temp,))
    receipt = cleanup_receipt(
        project,
        ActiveDeadline(5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP),
    )
    assert receipt["zero_temp_residue"] is True
    assert not task_temp.exists()


def test_cleanup_receipt_fails_when_recorded_resource_still_exists(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "still-present", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-22222222222222222222222222222222",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=("container-backend",),
        volume_ids=("volume-backend",),
        network_ids=("network-app",),
        image_tag="dra-proof-image:22222222222222222222222222222222",
        image_id="sha256:" + "b" * 64,
        temp_paths=(),
    )
    with pytest.raises(EvaluationError) as raised:
        cleanup_receipt(
            project,
            ActiveDeadline(
                5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP
            ),
        )
    assert raised.value.code is FailureCode.CLEANUP_FAILED


def test_cleanup_receipt_rejects_unrecorded_exact_project_label_residue(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        if len(args) >= 3 and args[2] == "inspect":
            return subprocess.CompletedProcess(args, 1, "", "not found")
        if len(args) >= 3 and args[2] == "ls":
            return subprocess.CompletedProcess(args, 0, "unrecorded-resource\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-44444444444444444444444444444444",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=("container-backend",),
        volume_ids=("volume-backend",),
        network_ids=("network-app",),
        image_tag="dra-proof-image:44444444444444444444444444444444",
        image_id="sha256:" + "c" * 64,
        temp_paths=(),
    )
    with pytest.raises(EvaluationError):
        cleanup_receipt(
            project,
            ActiveDeadline(
                5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP
            ),
        )


def test_cleanup_failure_is_typed_and_dual_failure_preserves_both_causes(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def failing_runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "failed")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        environment={},
        runner=failing_runner,
    )
    primary = EvaluationError(FailureCode.RUN_FAILED, FailurePhase.OBSERVE, False)
    with pytest.raises(ExceptionGroup) as raised:
        cleanup_receipt(
            project,
            ActiveDeadline(5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP),
            primary_error=primary,
        )
    assert raised.value.exceptions[0] is primary
    assert isinstance(raised.value.exceptions[1], EvaluationError)


def test_managed_compose_project_rejects_arbitrary_paths_and_project_names(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    outside = tmp_path / "outside.yml"
    outside.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        ManagedComposeProject(
            root=root,
            compose_paths=(outside,),
            env_file=env_file,
            project_name="user-controlled",
            environment={},
        )


def test_fixture_override_is_exact_and_requires_explicit_test_mode(tmp_path: Path) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml"
    )
    assert fixture_path.is_file()
    assert yaml.safe_load(fixture_path.read_text(encoding="utf-8")) == {
        "services": {
            "backend": {
                "command": [
                    "python",
                    "scripts/bounded_live_producer_container_fixture.py",
                    "serve",
                ],
                "environment": {
                    "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE": "true"
                },
            }
        }
    }

    projection = _compose_projection()
    projection["services"]["backend"]["command"] = [  # type: ignore[index]
        "python",
        "scripts/bounded_live_producer_container_fixture.py",
        "serve",
    ]
    projection["services"]["backend"]["environment"][  # type: ignore[index]
        "DECISION_RESEARCH_AGENT_BOUNDED_PRODUCER_FIXTURE"
    ] = "true"
    sanitized = sanitize_compose_projection(projection, fixture_mode=True)
    assert sanitized["services"]["backend"]["command"] == "<fixture-command>"
    with pytest.raises(EvaluationError):
        sanitize_compose_projection(projection)

    root = tmp_path / "snapshot"
    override = root / "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml"
    override.parent.mkdir(parents=True)
    base = root / "docker-compose.yml"
    base.write_text("services: {}\n", encoding="utf-8")
    override.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")
    env_file = tmp_path / "fixture.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args[:5] == ("docker", "image", "inspect", "--format", "{{.Id}}"):
            return subprocess.CompletedProcess(args, 0, "sha256:" + "f" * 64 + "\n", "")
        if args[:2] == ("docker", "run"):
            return subprocess.CompletedProcess(args, 0, '{"status":"valid","match":true}\n', "")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(base, override),
        env_file=env_file,
        project_name="dra-proof-0123456789abcdef0123456789abcdef",
        environment={},
        runner=runner,
    )
    deadline = ActiveDeadline(
        5,
        code=FailureCode.SERVICE_START_FAILED,
        phase=FailurePhase.DOCKER,
    )
    with pytest.raises(ValueError, match="fixture_secure_check_required"):
        project.start_fixture_backend(deadline)
    project.verify_snapshot_secure_runtime(deadline)
    project.start_fixture_backend(deadline)
    flattened = " ".join(commands[-1])
    assert str(override) in flattened
    assert flattened.endswith("up -d backend")
    secure_command = next(command for command in commands if command[:2] == ("docker", "run"))
    assert "--network" in secure_command and "none" in secure_command
    assert "--cap-drop" in secure_command and "ALL" in secure_command
    assert "--security-opt" in secure_command
    assert "PYTHON_DOTENV_DISABLED=1" in secure_command
    assert secure_command[-2:] == (
        "scripts/secure_local_runtime_proof.py",
        "check",
    )


def test_fixture_archive_may_defer_only_to_the_locked_image_secure_check(
    tmp_path: Path,
) -> None:
    root = _tiny_repository(tmp_path)
    secure_script = root / "scripts/secure_local_runtime_proof.py"
    secure_script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    _git(root, "add", "scripts/secure_local_runtime_proof.py")
    _git(root, "commit", "-qm", "failing host check")

    with pytest.raises(EvaluationError) as default_failure:
        prepare_source_snapshot(
            root,
            tmp_path / "default-check",
            required_paths=REQUIRED_PATHS,
        )
    assert default_failure.value.code is FailureCode.SOURCE_ARCHIVE_INVALID

    deferred = prepare_source_snapshot(
        root,
        tmp_path / "deferred-check",
        required_paths=REQUIRED_PATHS,
        verify_secure_runtime=False,
    )
    assert deferred.secure_runtime_checked is False


def test_fixture_override_cleanup_treats_already_absent_ids_as_clean(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task-root"
    root = task_root / "snapshot"
    root.mkdir(parents=True)
    base = root / "docker-compose.yml"
    base.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "fixture.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(
        args: tuple[str, ...],
        *,
        cwd: Path,
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        assert cwd.is_dir()
        if "inspect" in args or any(token in args for token in ("rm", "down")):
            return subprocess.CompletedProcess(args, 1 if "inspect" in args or "rm" in args else 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(base,),
        env_file=env_file,
        project_name="dra-proof-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=("c" * 64,),
        volume_ids=("dra-proof-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb_backend_data",),
        network_ids=("d" * 64,),
        image_tag="dra-proof-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-backend",
        image_id="sha256:" + "e" * 64,
        temp_paths=(task_root,),
    )
    receipt = cleanup_receipt(
        project,
        ActiveDeadline(
            5,
            code=FailureCode.CLEANUP_FAILED,
            phase=FailurePhase.CLEANUP,
        ),
    )
    assert receipt["succeeded"] is True
    assert not task_root.exists()
    assert any(command[:3] == ("docker", "image", "rm") for command in commands)
