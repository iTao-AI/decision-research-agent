from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from scripts.bounded_live_producer_contracts import (
    CleanupStatus,
    EvaluationError,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticStage,
)
from scripts.bounded_live_producer_diagnostics import (
    DIAGNOSTIC_FILENAME,
    DiagnosticOutputError,
    preflight_diagnostic_dir,
    publish_result_diagnostic,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _safe_dir(tmp_path: Path) -> Path:
    path = tmp_path / "diagnostic"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _repository(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _error() -> EvaluationError:
    return EvaluationError(
        "consumer_projection_invalid",
        "result",
        False,
        CleanupStatus.SUCCEEDED,
        diagnostic=ResultBoundaryDiagnostic(
            stage=ResultDiagnosticStage.RESPONSE_JSON,
            reason=ResultDiagnosticReason.RESPONSE_JSON_INVALID,
            http_status=200,
            response_bytes=8,
        ),
    )


def test_publishes_fixed_non_overwriting_mode_0600_file(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    deadlines: list[float] = []

    path = publish_result_diagnostic(
        sink,
        _error(),
        remaining_seconds=lambda requested: deadlines.append(requested) or requested,
    )

    assert path == output / DIAGNOSTIC_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_bytes().endswith(b"\n")
    assert deadlines
    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )
    assert path.is_file()


@pytest.mark.parametrize("mode", [0o770, 0o707, 0o755, 0o500])
def test_preflight_rejects_unsafe_directory_permissions(
    tmp_path: Path, mode: int
) -> None:
    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    output.chmod(mode)

    with pytest.raises(DiagnosticOutputError):
        preflight_diagnostic_dir(output, repository_root=repository)


def test_preflight_rejects_relative_missing_file_and_repository_paths(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    relative = Path("diagnostic")
    missing = tmp_path / "missing"
    regular = tmp_path / "regular"
    regular.write_text("x", encoding="utf-8")
    contained = repository / "diagnostic"
    contained.mkdir(mode=0o700)

    for candidate in (relative, missing, regular, repository, contained):
        with pytest.raises(DiagnosticOutputError):
            preflight_diagnostic_dir(candidate, repository_root=repository)


def test_preflight_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    leaf = tmp_path / "leaf"
    leaf.symlink_to(output, target_is_directory=True)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    nested = real_parent / "nested"
    nested.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    for candidate in (leaf, linked_parent / "nested"):
        with pytest.raises(DiagnosticOutputError):
            preflight_diagnostic_dir(candidate, repository_root=repository)


def test_preflight_rejects_wrong_owner_and_preexisting_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1)
    with pytest.raises(DiagnosticOutputError):
        preflight_diagnostic_dir(output, repository_root=repository)

    monkeypatch.undo()
    (output / DIAGNOSTIC_FILENAME).write_text("existing", encoding="utf-8")
    with pytest.raises(DiagnosticOutputError):
        preflight_diagnostic_dir(output, repository_root=repository)
    assert (output / DIAGNOSTIC_FILENAME).read_text(encoding="utf-8") == "existing"


def test_publication_rejects_directory_replacement(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    original = tmp_path / "original"
    output.rename(original)
    output.mkdir(mode=0o700)
    output.chmod(0o700)

    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert not (output / DIAGNOSTIC_FILENAME).exists()
    assert not (original / DIAGNOSTIC_FILENAME).exists()


def test_temporary_collision_is_not_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    monkeypatch.setattr(module.secrets, "token_hex", lambda _length: "fixed")
    temporary = output / f".{DIAGNOSTIC_FILENAME}.fixed.tmp"
    temporary.write_text("owned elsewhere", encoding="utf-8")

    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert temporary.read_text(encoding="utf-8") == "owned elsewhere"
    assert not (output / DIAGNOSTIC_FILENAME).exists()


def test_short_write_cleans_only_created_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    unrelated = output / "keep"
    unrelated.write_text("keep", encoding="utf-8")
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    monkeypatch.setattr(module.os, "write", lambda *_args, **_kwargs: 0)

    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert sorted(path.name for path in output.iterdir()) == ["keep"]


def test_link_failure_cleans_temporary_without_touching_unrelated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    unrelated = output / "keep"
    unrelated.write_text("keep", encoding="utf-8")
    sink = preflight_diagnostic_dir(output, repository_root=repository)

    def fail_link(*_args, **_kwargs) -> None:
        raise OSError("private")

    monkeypatch.setattr(module.os, "link", fail_link)
    with pytest.raises(DiagnosticOutputError, match="diagnostic_output_invalid"):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert sorted(path.name for path in output.iterdir()) == ["keep"]


def test_failure_cleanup_never_removes_replaced_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)

    def replace_temporary_then_fail(
        source: str, _destination: str, **_kwargs
    ) -> None:
        temporary = output / source
        temporary.unlink()
        temporary.write_bytes(b"operator replacement")
        raise OSError("private")

    monkeypatch.setattr(module.os, "link", replace_temporary_then_fail)
    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    replacements = list(output.iterdir())
    assert len(replacements) == 1
    assert replacements[0].read_bytes() == b"operator replacement"


def test_linked_final_rejects_replaced_temporary_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    real_link = module.os.link

    def replace_temporary_then_link(
        source: str, destination: str, **kwargs: object
    ) -> None:
        temporary = output / source
        temporary.unlink()
        temporary.write_bytes(b"operator replacement")
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(module.os, "link", replace_temporary_then_link)
    with pytest.raises(DiagnosticOutputError, match="diagnostic_output_invalid"):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    final = output / DIAGNOSTIC_FILENAME
    assert final.read_bytes() == b"operator replacement"
    temporary = next(path for path in output.iterdir() if path != final)
    assert temporary.read_bytes() == b"operator replacement"


def test_linked_final_rejects_same_inode_content_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    real_link = module.os.link

    def mutate_temporary_then_link(
        source: str, destination: str, **kwargs: object
    ) -> None:
        temporary = output / source
        temporary.write_bytes(b"x" * temporary.stat().st_size)
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(module.os, "link", mutate_temporary_then_link)
    with pytest.raises(DiagnosticOutputError, match="diagnostic_output_invalid"):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert (output / DIAGNOSTIC_FILENAME).read_bytes().startswith(b"x")


def test_owned_unlink_preserves_identity_mismatch_observed_after_quarantine_rename(
    tmp_path: Path,
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    output = _safe_dir(tmp_path)
    descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    name = "task-owned.tmp"
    target = output / name
    target.write_bytes(b"task")
    observed = target.stat()
    target.unlink()
    target.write_bytes(b"operator replacement")
    try:
        removed = module._unlink_if_owned(
            descriptor,
            name,
            expected_identity=(observed.st_dev, observed.st_ino),
        )
    finally:
        os.close(descriptor)

    assert not removed
    quarantined = list(output.iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"operator replacement"


def test_failure_cleanup_never_removes_replaced_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    real_fsync = module.os.fsync
    calls = 0

    def replace_final_then_fail(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            final = output / DIAGNOSTIC_FILENAME
            final.unlink()
            final.write_bytes(b"operator replacement")
            raise OSError("private")
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", replace_final_then_fail)
    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert (output / DIAGNOSTIC_FILENAME).read_bytes() == b"operator replacement"


@pytest.mark.parametrize("failure_call", [1, 2])
def test_file_or_directory_fsync_failure_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_call: int
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    real_fsync = module.os.fsync
    calls = 0

    def fail_selected(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("private")
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", fail_selected)
    with pytest.raises(DiagnosticOutputError, match="diagnostic_output_invalid"):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    if failure_call == 1:
        assert not (output / DIAGNOSTIC_FILENAME).exists()
        assert list(output.iterdir()) == []
    else:
        assert (output / DIAGNOSTIC_FILENAME).is_file()
        assert not any(path.name.endswith(".tmp") for path in output.iterdir())


def test_serializer_overflow_fails_before_filesystem_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bounded_live_producer_diagnostics as module

    repository = _repository(tmp_path)
    output = _safe_dir(tmp_path)
    sink = preflight_diagnostic_dir(output, repository_root=repository)
    monkeypatch.setattr(
        module,
        "serialize_result_diagnostic",
        lambda _error: b"x" * (module.MAX_DIAGNOSTIC_BYTES + 1),
    )

    with pytest.raises(DiagnosticOutputError):
        publish_result_diagnostic(
            sink,
            _error(),
            remaining_seconds=lambda requested: requested,
        )

    assert list(output.iterdir()) == []


def test_diagnostic_module_import_is_silent() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import scripts.bounded_live_producer_diagnostics"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
