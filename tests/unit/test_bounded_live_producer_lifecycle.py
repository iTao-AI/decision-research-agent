from __future__ import annotations

import io
import importlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tarfile
import time

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
                        "source": "backend_data",
                        "target": "/app/data",
                        "volume": {},
                    },
                    {
                        "type": "volume",
                        "source": "backend_output",
                        "target": "/app/output",
                        "volume": {},
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
                        "source": "mysql_data",
                        "target": "/var/lib/mysql",
                        "volume": {},
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


def test_prepare_source_snapshot_narrows_every_subprocess_to_outer_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    source = _tiny_repository(tmp_path)
    real_run = module.subprocess.run
    timeouts: list[float] = []

    def record_timeout(*args: object, **kwargs: object):
        timeout = kwargs.get("timeout")
        assert isinstance(timeout, (int, float))
        timeouts.append(float(timeout))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", record_timeout)
    deadline = ActiveDeadline(
        5,
        code=FailureCode.SOURCE_ARCHIVE_INVALID,
        phase=FailurePhase.DOCKER,
    )
    prepare_source_snapshot(
        source,
        tmp_path / "tasks",
        required_paths=REQUIRED_PATHS,
        deadline=deadline,
        verify_secure_runtime=False,
    )
    assert timeouts
    assert max(timeouts) <= 5.0


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


def test_prepare_source_snapshot_fails_closed_when_head_changes_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _tiny_repository(tmp_path)
    captured_commit = _git(source, "rev-parse", "HEAD")
    (source / "VERSION").write_text("0.1.6\n", encoding="utf-8")
    _git(source, "add", "VERSION")
    _git(source, "commit", "-qm", "second fixture")
    changed_commit = _git(source, "rev-parse", "HEAD")
    _git(source, "reset", "--hard", captured_commit)

    module = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    real_git_output = module._git_output
    switched = False

    def switch_after_commit(root: Path, *arguments: str, **kwargs: object) -> str:
        nonlocal switched
        result = real_git_output(root, *arguments, **kwargs)
        if arguments == ("rev-parse", "--verify", "HEAD") and not switched:
            switched = True
            _git(root, "reset", "--hard", changed_commit)
        return result

    monkeypatch.setattr(module, "_git_output", switch_after_commit)
    with pytest.raises(EvaluationError) as raised:
        prepare_source_snapshot(
            source,
            tmp_path / "raced-tasks",
            required_paths=REQUIRED_PATHS,
        )
    assert raised.value.code in {
        FailureCode.SOURCE_IDENTITY_INVALID,
        FailureCode.SOURCE_ARCHIVE_INVALID,
    }
    assert not (tmp_path / "raced-tasks").exists()


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
    loaded = load_live_configuration(
        path,
        _declaration(),
        process_api_key="service-secret",
        repository_root=tmp_path / "repository",
    )
    try:
        assert loaded["LLM_MODEL"] == "gpt-5"
        assert loaded["LANGSMITH_API_KEY"] == ""
    finally:
        getattr(loaded, "close", lambda: None)()


@pytest.mark.parametrize("mode", [0o004, 0o040, 0o200, 0o500, 0o700])
def test_load_live_configuration_rejects_unsafe_permissions(
    tmp_path: Path, mode: int
) -> None:
    path = tmp_path / "live.env"
    _write_env(path, _valid_env())
    path.chmod(mode)
    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(
            path,
            _declaration(),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


def test_load_live_configuration_rejects_symlink_unknown_duplicate_and_api_mismatch(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.env"
    _write_env(target, _valid_env())
    link = tmp_path / "link.env"
    link.symlink_to(target)
    with pytest.raises(EvaluationError):
        load_live_configuration(
            link,
            _declaration(),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )

    values = _valid_env()
    values["HTTP_PROXY"] = "http://proxy.invalid"
    _write_env(target, values)
    with pytest.raises(EvaluationError):
        load_live_configuration(
            target,
            _declaration(),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )

    _write_env(target, _valid_env())
    with target.open("a", encoding="utf-8") as handle:
        handle.write("API_SECRET=again\n")
    with pytest.raises(EvaluationError):
        load_live_configuration(
            target,
            _declaration(),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )

    _write_env(target, _valid_env())
    with pytest.raises(EvaluationError):
        load_live_configuration(
            target,
            _declaration(),
            process_api_key="different",
            repository_root=tmp_path / "repository",
        )


def test_load_live_configuration_rejects_repository_contained_credential_file(
    tmp_path: Path,
) -> None:
    source = _tiny_repository(tmp_path)
    path = source / "tracked-live.env"
    _write_env(path, _valid_env())
    _git(source, "add", path.name)
    _git(source, "commit", "-qm", "tracked credential fixture")

    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(
            path,
            _declaration(),
            process_api_key="service-secret",
            repository_root=source,
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


def test_load_live_configuration_rejects_external_hard_link_to_tracked_credential(
    tmp_path: Path,
) -> None:
    source = _tiny_repository(tmp_path)
    tracked = source / "tracked-live.env"
    _write_env(tracked, _valid_env())
    _git(source, "add", tracked.name)
    _git(source, "commit", "-qm", "tracked credential fixture")
    external = tmp_path / "external-live.env"
    os.link(tracked, external)

    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(
            external,
            _declaration(),
            process_api_key="service-secret",
            repository_root=source,
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


def test_load_live_configuration_rejects_credential_from_linked_worktree_of_same_repo(
    tmp_path: Path,
) -> None:
    source = _tiny_repository(tmp_path)
    linked = tmp_path / "linked-credentials"
    _git(source, "worktree", "add", "-q", "-b", "credential-fixture", str(linked))
    path = linked / "live.env"
    _write_env(path, _valid_env())

    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(
            path,
            _declaration(),
            process_api_key="service-secret",
            repository_root=source,
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


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


@pytest.mark.parametrize(
    "url",
    [
        "https://127.1/v1",
        "https://127.0.1/v1",
        "https://0x7f.1/v1",
        "https://0177.0.0.1/v1",
        "https://2130706433/v1",
        "https://１２７.０.０.１/v1",
        "https://１２７.0.0.1/v1",
    ],
)
def test_credential_declaration_rejects_numeric_and_unicode_address_aliases(
    url: str,
) -> None:
    with pytest.raises(ValueError, match="credential_declaration_invalid"):
        _declaration(provider_base_url=url)


def test_credential_declaration_accepts_public_https_dns_host_and_approved_path() -> None:
    assert _declaration(provider_base_url="https://provider.example/v1").provider_id == (
        "openai-compatible"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"provider_id": "vendor/provider"},
        {"primary_model": "vendor/model"},
        {"fallback_model": "vendor/model"},
        {
            "pricing_basis": "operator/basis",
            "pricing_currency": "USD",
        },
    ],
)
def test_credential_declaration_rejects_report_incompatible_identifiers(
    change: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="credential_declaration_invalid"):
        _declaration(**change)


def test_load_live_configuration_validates_flags_privacy_and_pricing_bundle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "live.env"
    values = _valid_env()
    values["LANGSMITH_TRACING"] = "true"
    _write_env(path, values)
    with pytest.raises(EvaluationError):
        load_live_configuration(
            path,
            _declaration(),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )

    values = _valid_env()
    values.update(
        {
            "TOKEN_PRICING_JSON": (
                '{"gpt-5":{"completion":0.2,"prompt":0.1},'
                '"gpt-5-mini":{"completion":0.04,"prompt":0.02}}'
            ),
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
        repository_root=tmp_path / "repository",
    )
    try:
        assert loaded["TOKEN_PRICING_CURRENCY"] == "USD"
    finally:
        getattr(loaded, "close", lambda: None)()


@pytest.mark.parametrize(
    "pricing",
    [
        '{"gpt-5":"0.10000000","gpt-5-mini":"0.20000000"}',
        '{"gpt-5":{"completion":0.2,"prompt":0.1}}',
        '{"gpt-5":{"completion":"0.2","prompt":0.1},'
        '"gpt-5-mini":{"completion":0.04,"prompt":0.02}}',
        '{"gpt-5":{"completion":0.2,"input":0.1},'
        '"gpt-5-mini":{"completion":0.04,"prompt":0.02}}',
    ],
)
def test_load_live_configuration_rejects_runtime_incompatible_pricing(
    tmp_path: Path,
    pricing: str,
) -> None:
    path = tmp_path / "live.env"
    values = _valid_env()
    values.update(
        {
            "TOKEN_PRICING_JSON": pricing,
            "TOKEN_PRICING_BASIS": "operator-v1",
            "TOKEN_PRICING_CURRENCY": "USD",
        }
    )
    _write_env(path, values)
    with pytest.raises(EvaluationError) as raised:
        load_live_configuration(
            path,
            _declaration(pricing_basis="operator-v1", pricing_currency="USD"),
            process_api_key="service-secret",
            repository_root=tmp_path / "repository",
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID


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

    payload = _compose_projection()
    payload["services"]["backend"]["volumes"][0]["volume"] = {  # type: ignore[index]
        "nocopy": True
    }
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


@pytest.mark.skipif(os.name != "posix", reason="process-group contract requires POSIX")
def test_run_bounded_subprocess_kills_inherited_pipe_descendant_within_deadline(
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "descendant.pid"
    script = (
        "import pathlib,subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(2)'],"
        "stdout=sys.stdout,stderr=sys.stderr); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); "
        "raise SystemExit(0)"
    )
    descendant_pid: int | None = None
    started = time.monotonic()
    try:
        with pytest.raises(EvaluationError) as raised:
            run_bounded_subprocess(
                [sys.executable, "-c", script],
                cwd=tmp_path,
                env={"PATH": os.environ.get("PATH", "")},
                deadline=ActiveDeadline(
                    0.2,
                    code=FailureCode.SERVICE_START_FAILED,
                    phase=FailurePhase.DOCKER,
                ),
                allowed_environment=("PATH",),
                stream_bytes_max=1024,
            )
        elapsed = time.monotonic() - started
        assert raised.value.code is FailureCode.SERVICE_START_FAILED
        assert elapsed < 0.75
        descendant_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(50):
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("descendant survived bounded subprocess deadline")
    finally:
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "posix", reason="process-group contract requires POSIX")
def test_run_bounded_subprocess_kills_group_when_join_is_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    pid_path = tmp_path / "descendant.pid"
    script = (
        "import pathlib,subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(2)'],"
        "stdout=sys.stdout,stderr=sys.stderr); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); "
        "raise SystemExit(0)"
    )
    original_join = lifecycle.threading.Thread.join
    join_interrupted = False

    def interrupt_first_join(thread: object, timeout: float | None = None) -> None:
        nonlocal join_interrupted
        if not join_interrupted:
            join_interrupted = True
            raise KeyboardInterrupt
        original_join(thread, timeout)

    monkeypatch.setattr(lifecycle.threading.Thread, "join", interrupt_first_join)
    descendant_pid: int | None = None
    try:
        with pytest.raises(KeyboardInterrupt):
            run_bounded_subprocess(
                [sys.executable, "-c", script],
                cwd=tmp_path,
                env={"PATH": os.environ.get("PATH", "")},
                deadline=ActiveDeadline(
                    0.5,
                    code=FailureCode.SERVICE_START_FAILED,
                    phase=FailurePhase.DOCKER,
                ),
                allowed_environment=("PATH",),
                stream_bytes_max=1024,
            )
        descendant_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(50):
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("descendant survived interrupted subprocess drain")
    finally:
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_managed_compose_uses_one_captured_credential_input_after_path_replacement(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    original = _valid_env()
    _write_env(env_file, original)
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    captured_inputs: list[bytes] = []
    captured_paths: list[Path] = []

    def runner(
        args: tuple[str, ...],
        *,
        env: dict[str, str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        credential_path = Path(args[args.index("--env-file") + 1])
        assert Path(env["DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE"]) == credential_path
        captured_paths.append(credential_path)
        captured_inputs.append(credential_path.read_bytes())
        if len(captured_inputs) == 1:
            replacement = {**original, "LLM_MODEL": "replacement-model"}
            replacement_path = tmp_path / "replacement.env"
            _write_env(replacement_path, replacement)
            os.replace(replacement_path, env_file)
        elif len(captured_inputs) == 2:
            current = env_file.read_bytes()
            env_file.write_bytes(b"x" * len(current))
            env_file.chmod(0o600)
        return subprocess.CompletedProcess(args, 0, "", "")

    try:
        project = ManagedComposeProject(
            root=root,
            compose_paths=(compose,),
            env_file=configuration,
            project_name="dra-proof-90909090909090909090909090909090",
            environment={},
            runner=runner,
        )
        deadline = ActiveDeadline(
            5,
            code=FailureCode.SERVICE_START_FAILED,
            phase=FailurePhase.DOCKER,
        )
        project._invoke(("config", "--format", "json"), deadline, compose=True)
        project._invoke(("build", "backend"), deadline, compose=True)
        project._invoke(("up", "-d", "mysql"), deadline, compose=True)
        assert len(captured_inputs) == 3
        assert captured_inputs[0] == captured_inputs[1] == captured_inputs[2]
        assert len(set(captured_paths)) == 3
        assert all(not path.exists() for path in captured_paths)
        assert b"LLM_MODEL=gpt-5\n" in captured_inputs[0]
        assert b"replacement-model" not in captured_inputs[0]
    finally:
        getattr(configuration, "close", lambda: None)()


def test_managed_compose_materializes_owner_read_only_single_command_snapshot(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    captured_inputs: list[bytes] = []
    captured_paths: list[Path] = []

    def runner(
        args: tuple[str, ...],
        *,
        env: dict[str, str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        credential_path = Path(args[args.index("--env-file") + 1])
        assert Path(env["DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE"]) == credential_path
        metadata = credential_path.lstat()
        assert stat.S_IMODE(metadata.st_mode) == 0o400
        assert metadata.st_nlink == 1
        assert stat.S_IMODE(credential_path.parent.stat().st_mode) == 0o700
        with pytest.raises(PermissionError):
            credential_path.open("wb")
        captured_paths.append(credential_path)
        captured_inputs.append(credential_path.read_bytes())
        return subprocess.CompletedProcess(args, 0, "", "")

    try:
        project = ManagedComposeProject(
            root=root,
            compose_paths=(compose,),
            env_file=configuration,
            project_name="dra-proof-91919191919191919191919191919191",
            environment={},
            runner=runner,
        )
        project._invoke(
            ("config", "--format", "json"),
            ActiveDeadline(
                5,
                code=FailureCode.COMPOSE_CONFIG_INVALID,
                phase=FailurePhase.DOCKER,
            ),
            compose=True,
        )
        assert len(captured_inputs) == 1
        assert b"LLM_MODEL=gpt-5\n" in captured_inputs[0]
        assert not captured_paths[0].exists()
    finally:
        configuration.close()


def test_managed_compose_fails_closed_when_command_snapshot_is_replaced(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    captured_directory: Path | None = None

    def runner(
        args: tuple[str, ...],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal captured_directory
        credential_path = Path(args[args.index("--env-file") + 1])
        captured_directory = credential_path.parent
        replacement = captured_directory / "replacement.env"
        replacement.write_bytes(b"API_SECRET=replaced\n")
        replacement.chmod(0o400)
        os.replace(replacement, credential_path)
        return subprocess.CompletedProcess(args, 0, "", "")

    try:
        project = ManagedComposeProject(
            root=root,
            compose_paths=(compose,),
            env_file=configuration,
            project_name="dra-proof-92929292929292929292929292929292",
            environment={},
            runner=runner,
        )
        with pytest.raises(EvaluationError) as raised:
            project._invoke(
                ("config", "--format", "json"),
                ActiveDeadline(
                    5,
                    code=FailureCode.COMPOSE_CONFIG_INVALID,
                    phase=FailurePhase.DOCKER,
                ),
                compose=True,
            )
        assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID
        assert captured_directory is not None and not captured_directory.exists()
    finally:
        configuration.close()


def test_managed_compose_fails_closed_and_cleans_after_pathname_rebinding(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    paths: dict[str, Path] = {}
    attacker_directory = tmp_path / "attacker-credential"
    attacker_directory.mkdir()
    attacker_env = attacker_directory / "live.env"
    attacker_env.write_bytes(b"API_SECRET=attacker-controlled\n")
    attacker_env.chmod(0o400)

    def runner(
        args: tuple[str, ...],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        credential_path = Path(args[args.index("--env-file") + 1])
        original_directory = credential_path.parent
        renamed_directory = original_directory.with_name(
            original_directory.name + "-renamed"
        )
        original_directory.rename(renamed_directory)
        original_directory.symlink_to(attacker_directory, target_is_directory=True)
        paths.update(original=original_directory, renamed=renamed_directory)
        return subprocess.CompletedProcess(args, 0, "", "")

    try:
        project = ManagedComposeProject(
            root=root,
            compose_paths=(compose,),
            env_file=configuration,
            project_name="dra-proof-93939393939393939393939393939393",
            environment={},
            runner=runner,
        )
        with pytest.raises(EvaluationError) as raised:
            project._invoke(
                ("config", "--format", "json"),
                ActiveDeadline(
                    5,
                    code=FailureCode.COMPOSE_CONFIG_INVALID,
                    phase=FailurePhase.DOCKER,
                ),
                compose=True,
            )
        assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID
        assert not paths["original"].exists()
        assert not paths["original"].is_symlink()
        assert not paths["renamed"].exists()
        assert attacker_env.read_bytes() == b"API_SECRET=attacker-controlled\n"
    finally:
        configuration.close()


def test_managed_compose_closes_secret_fd_after_cross_parent_directory_rename(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    moved_directory = tmp_path / "moved-credential"
    original_directory: Path | None = None
    reader_fd: int | None = None

    def runner(
        args: tuple[str, ...],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal original_directory, reader_fd
        credential_path = Path(args[args.index("--env-file") + 1])
        original_directory = credential_path.parent
        snapshot = next(iter(configuration._active_snapshots))
        reader_fd = snapshot.reader_fd
        original_directory.rename(moved_directory)
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=configuration,
        project_name="dra-proof-94949494949494949494949494949493",
        environment={},
        runner=runner,
    )
    with pytest.raises(EvaluationError) as raised:
        project._invoke(
            ("config", "--format", "json"),
            ActiveDeadline(
                5,
                code=FailureCode.COMPOSE_CONFIG_INVALID,
                phase=FailurePhase.DOCKER,
            ),
            compose=True,
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID
    assert reader_fd is not None
    snapshot = next(iter(configuration._active_snapshots))
    assert snapshot.reader_fd == -1
    with pytest.raises(OSError):
        os.fstat(reader_fd)
    assert moved_directory.is_dir()
    assert not (moved_directory / "live.env").exists()
    with pytest.raises(EvaluationError) as cleanup_raised:
        configuration.close()
    assert cleanup_raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID
    assert original_directory is not None
    moved_directory.rename(original_directory)
    configuration.close()
    assert not original_directory.exists()


def test_managed_compose_retries_snapshot_cleanup_after_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    credential_directory: Path | None = None
    original_unlink = lifecycle.os.unlink
    interrupted = False

    def interrupt_first_unlink(path: object, *args: object, **kwargs: object) -> None:
        nonlocal interrupted
        if not interrupted and path == "live.env" and kwargs.get("dir_fd") is not None:
            interrupted = True
            raise KeyboardInterrupt
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "unlink", interrupt_first_unlink)

    def runner(
        args: tuple[str, ...],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal credential_directory
        credential_directory = Path(args[args.index("--env-file") + 1]).parent
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=configuration,
        project_name="dra-proof-94949494949494949494949494949494",
        environment={},
        runner=runner,
    )
    with pytest.raises(EvaluationError) as raised:
        project._invoke(
            ("config", "--format", "json"),
            ActiveDeadline(
                5,
                code=FailureCode.COMPOSE_CONFIG_INVALID,
                phase=FailurePhase.DOCKER,
            ),
            compose=True,
        )
    assert raised.value.code is FailureCode.CREDENTIAL_SOURCE_INVALID
    assert credential_directory is not None and credential_directory.exists()
    configuration.close()
    assert not credential_directory.exists()


@pytest.mark.parametrize(
    "primary",
    [
        EvaluationError(
            FailureCode.COMPOSE_CONFIG_INVALID,
            FailurePhase.DOCKER,
            False,
        ),
        KeyboardInterrupt(),
    ],
)
@pytest.mark.parametrize(
    "cleanup_error",
    [KeyboardInterrupt(), RuntimeError("cleanup")],
)
def test_managed_compose_preserves_primary_when_snapshot_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    primary: BaseException,
    cleanup_error: BaseException,
) -> None:
    lifecycle = importlib.import_module("scripts.bounded_live_producer_lifecycle")
    repository = tmp_path / "repository"
    root = repository / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "external-live.env"
    _write_env(env_file, _valid_env())
    configuration = load_live_configuration(
        env_file,
        _declaration(),
        process_api_key="service-secret",
        repository_root=repository,
    )
    original_unlink = lifecycle.os.unlink
    cleanup_failed = False

    def fail_first_unlink(path: object, *args: object, **kwargs: object) -> None:
        nonlocal cleanup_failed
        if not cleanup_failed and path == "live.env" and kwargs.get("dir_fd") is not None:
            cleanup_failed = True
            raise cleanup_error
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "unlink", fail_first_unlink)

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise primary

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=configuration,
        project_name="dra-proof-95959595959595959595959595959595",
        environment={},
        runner=runner,
    )
    with pytest.raises(BaseExceptionGroup) as raised:
        project._invoke(
            ("config", "--format", "json"),
            ActiveDeadline(
                5,
                code=FailureCode.COMPOSE_CONFIG_INVALID,
                phase=FailurePhase.DOCKER,
            ),
            compose=True,
        )
    assert raised.value.exceptions[0] is primary
    assert isinstance(raised.value.exceptions[1], EvaluationError)
    configuration.close()


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
        if args[:3] == ("docker", "image", "inspect"):
            return subprocess.CompletedProcess(args, 1, "", "not found")
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


def test_build_success_registers_image_tag_before_later_inspection_failure(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task-root"
    root = task_root / "snapshot-build" / "snapshot"
    root.mkdir(parents=True)
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if "inspect" in args:
            return subprocess.CompletedProcess(args, 1, "", "not found")
        return subprocess.CompletedProcess(args, 0, "", "")

    project_name = "dra-proof-56565656565656565656565656565656"
    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name=project_name,
        environment={},
        runner=runner,
    )
    project.track_temp_paths((task_root,))
    deadline = ActiveDeadline(
        5,
        code=FailureCode.IMAGE_BUILD_FAILED,
        phase=FailurePhase.DOCKER,
    )
    project.assert_unclaimed(deadline)
    project.build_backend(deadline)
    cleanup_receipt(
        project,
        ActiveDeadline(
            5,
            code=FailureCode.CLEANUP_FAILED,
            phase=FailurePhase.CLEANUP,
        ),
    )
    assert (
        "docker",
        "image",
        "rm",
        f"{project_name}-backend",
    ) in commands


def test_secure_check_timeout_registers_exact_container_and_image_for_cleanup(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task-root"
    root = task_root / "snapshot-build" / "snapshot"
    override = root / "tests/fixtures/bounded-live-producer-v1/docker-compose.fixture.yml"
    override.parent.mkdir(parents=True)
    base = root / "docker-compose.yml"
    base.write_text("services: {}\n", encoding="utf-8")
    override.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "fixture.env"
    env_file.write_text("", encoding="utf-8")
    commands: list[tuple[str, ...]] = []
    project_name = "dra-proof-78787878787878787878787878787878"

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args[:5] == ("docker", "image", "inspect", "--format", "{{.Id}}"):
            return subprocess.CompletedProcess(args, 0, "sha256:" + "d" * 64 + "\n", "")
        if args[:2] == ("docker", "run"):
            raise EvaluationError(
                FailureCode.SOURCE_ARCHIVE_INVALID,
                FailurePhase.DOCKER,
                False,
            )
        if "inspect" in args:
            return subprocess.CompletedProcess(args, 1, "", "not found")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(base, override),
        env_file=env_file,
        project_name=project_name,
        environment={},
        runner=runner,
    )
    project.track_temp_paths((task_root,))
    with pytest.raises(EvaluationError):
        project.verify_snapshot_secure_runtime(
            ActiveDeadline(
                5,
                code=FailureCode.SOURCE_ARCHIVE_INVALID,
                phase=FailurePhase.DOCKER,
            )
        )
    cleanup_receipt(
        project,
        ActiveDeadline(
            5,
            code=FailureCode.CLEANUP_FAILED,
            phase=FailurePhase.CLEANUP,
        ),
    )
    assert ("docker", "container", "rm", "-f", f"{project_name}-secure-check") in commands
    assert ("docker", "image", "rm", f"{project_name}-backend") in commands


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
        container_ids=("a" * 64, "b" * 64),
        volume_ids=("volume-backend", "volume-mysql"),
        network_ids=("c" * 64,),
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


@pytest.mark.parametrize(
    ("container_ids", "network_ids"),
    [
        (("a" * 12,), ("b" * 64,)),
        (("a" * 64,), ("b" * 12,)),
    ],
)
def test_record_ownership_rejects_short_docker_ids(
    tmp_path: Path,
    container_ids: tuple[str, ...],
    network_ids: tuple[str, ...],
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-25252525252525252525252525252525",
        environment={},
    )
    with pytest.raises(ValueError, match="ownership_receipt_invalid"):
        project.record_ownership(
            container_ids=container_ids,
            volume_ids=("dra-proof-25252525252525252525252525252525_data",),
            network_ids=network_ids,
            image_tag="dra-proof-25252525252525252525252525252525-backend",
            image_id="sha256:" + "c" * 64,
            temp_paths=(),
        )


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
        container_ids=("d" * 64,),
        volume_ids=("volume-backend",),
        network_ids=("e" * 64,),
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


def test_cleanup_receipt_does_not_treat_failed_inspect_as_absence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")
    container_id = "a" * 64
    volume_id = "volume-backend"
    network_id = "b" * 64
    image_tag = "dra-proof-image:23232323232323232323232323232323"

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        if "rm" in args:
            return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")
        if "inspect" in args:
            return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")
        if "--filter" in args and any(
            value.startswith("label=com.docker.compose.project=") for value in args
        ):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:5] == ("docker", "container", "ls", "-a", "-q"):
            return subprocess.CompletedProcess(args, 0, f"{container_id}\n", "")
        if args[:4] == ("docker", "volume", "ls", "-q"):
            return subprocess.CompletedProcess(args, 0, f"{volume_id}\n", "")
        if args[:5] == ("docker", "network", "ls", "-q", "--no-trunc"):
            return subprocess.CompletedProcess(args, 0, f"{network_id}\n", "")
        if args[:5] == ("docker", "image", "ls", "-q", "--no-trunc"):
            return subprocess.CompletedProcess(args, 0, "sha256:" + "a" * 64 + "\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-23232323232323232323232323232323",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=(container_id,),
        volume_ids=(volume_id,),
        network_ids=(network_id,),
        image_tag=image_tag,
        image_id="sha256:" + "a" * 64,
        temp_paths=(),
    )
    with pytest.raises(EvaluationError) as raised:
        cleanup_receipt(
            project,
            ActiveDeadline(
                5,
                code=FailureCode.CLEANUP_FAILED,
                phase=FailurePhase.CLEANUP,
            ),
        )
    assert raised.value.code is FailureCode.CLEANUP_FAILED


def test_cleanup_receipt_accepts_nonzero_exact_remove_only_after_empty_inventory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = tmp_path / "live.env"
    env_file.write_text("", encoding="utf-8")

    def runner(args: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        if "rm" in args:
            return subprocess.CompletedProcess(args, 1, "", "already absent")
        return subprocess.CompletedProcess(args, 0, "", "")

    project = ManagedComposeProject(
        root=root,
        compose_paths=(compose,),
        env_file=env_file,
        project_name="dra-proof-24242424242424242424242424242424",
        environment={},
        runner=runner,
    )
    project.record_ownership(
        container_ids=("f" * 64,),
        volume_ids=("volume-backend",),
        network_ids=("e" * 64,),
        image_tag="dra-proof-image:24242424242424242424242424242424",
        image_id="sha256:" + "a" * 64,
        temp_paths=(),
    )
    assert cleanup_receipt(
        project,
        ActiveDeadline(
            5,
            code=FailureCode.CLEANUP_FAILED,
            phase=FailurePhase.CLEANUP,
        ),
    )["succeeded"] is True


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
        container_ids=("1" * 64,),
        volume_ids=("volume-backend",),
        network_ids=("2" * 64,),
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
    project._project_claimed = True
    primary = EvaluationError(FailureCode.RUN_FAILED, FailurePhase.OBSERVE, False)
    with pytest.raises(ExceptionGroup) as raised:
        cleanup_receipt(
            project,
            ActiveDeadline(5, code=FailureCode.CLEANUP_FAILED, phase=FailurePhase.CLEANUP),
            primary_error=primary,
        )
    assert raised.value.exceptions[0] is primary
    assert isinstance(raised.value.exceptions[1], EvaluationError)


def test_cleanup_failure_preserves_keyboard_interrupt_in_base_exception_group(
    tmp_path: Path,
) -> None:
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
        project_name="dra-proof-cacacacacacacacacacacacacacacaca",
        environment={},
        runner=failing_runner,
    )
    project._project_claimed = True
    primary = KeyboardInterrupt()
    with pytest.raises(BaseExceptionGroup) as raised:
        cleanup_receipt(
            project,
            ActiveDeadline(
                5,
                code=FailureCode.CLEANUP_FAILED,
                phase=FailurePhase.CLEANUP,
            ),
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
        if args[:3] == ("docker", "container", "inspect"):
            return subprocess.CompletedProcess(args, 1, "", "not found")
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
    source_mount = secure_command[secure_command.index("--volume") + 1]
    assert source_mount.endswith(":/proof:ro")
    assert "--tmpfs" in secure_command
    assert "/proof/data:rw,nosuid,nodev,noexec,size=16m" in secure_command
    assert "/proof/output:rw,nosuid,nodev,noexec,size=16m" in secure_command
    assert (root / "data").stat().st_mode & 0o777 == 0o700
    assert (root / "output").stat().st_mode & 0o777 == 0o700
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
