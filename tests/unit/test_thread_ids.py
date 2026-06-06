from pathlib import Path

import pytest

from api.thread_ids import safe_session_dir, validate_thread_id


def test_validate_thread_id_rejects_path_traversal():
    with pytest.raises(ValueError, match="thread_id"):
        validate_thread_id("../../../../../../tmp/escape")


def test_safe_session_dir_stays_inside_root(tmp_path):
    session_dir = safe_session_dir(tmp_path, "thread-001")

    assert session_dir == Path(tmp_path, "session_thread-001")
    assert session_dir.resolve().is_relative_to(tmp_path.resolve())
