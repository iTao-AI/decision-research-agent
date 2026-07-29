"""Process-lifetime single-writer exclusion for one application database."""
from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat

try:
    import fcntl
except ImportError:  # pragma: no cover - unsupported platforms fail closed
    fcntl = None

from api.database import application_db_path, prepare_application_db_parent
from api.run_execution_models import RunExecutionConflict


@dataclass(frozen=True)
class RunExecutionWriter:
    descriptor: int
    lock_path: str
    held: bool = True

    def release(self) -> None:
        if not self.held:
            return
        assert fcntl is not None
        fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        os.close(self.descriptor)
        object.__setattr__(self, "held", False)


def acquire_run_execution_writer(
    *, db_path: str | Path
) -> RunExecutionWriter:
    if (
        fcntl is None
        or not hasattr(fcntl, "flock")
        or not hasattr(os, "O_CLOEXEC")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise RunExecutionConflict("run_execution_writer_unavailable")
    canonical = application_db_path(db_path)
    try:
        prepare_application_db_parent(canonical)
        lock_path = Path(f"{canonical}.execution-writer.lock")
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.set_inheritable(descriptor, False)
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise OSError("unsafe lock type")
            if stat.S_IMODE(details.st_mode) != 0o600:
                os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise RunExecutionConflict(
                    "run_execution_writer_already_active"
                ) from exc
            raise
        return RunExecutionWriter(
            descriptor=descriptor,
            lock_path=str(lock_path),
        )
    except RunExecutionConflict:
        raise
    except (OSError, RuntimeError) as exc:
        raise RunExecutionConflict("run_execution_writer_unavailable") from exc
