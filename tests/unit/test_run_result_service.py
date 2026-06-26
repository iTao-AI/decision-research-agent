import hashlib
from datetime import datetime, timezone
from pathlib import PurePosixPath

from agent.harness_contracts import ReportCandidate
from agent.run_result import ExecutionOutcome


def _outcome(**kwargs):
    values = {
        "thread_id": "thread-1",
        "query": "What changed?",
        "session_dir": PurePosixPath("/not/a/host/path"),
        "run_id": "run_1",
        "segment_id": "run_1_seg_000",
        "last_agent_text": "",
        "diagnostics": [],
    }
    values.update(kwargs)
    return ExecutionOutcome(**values)


def _noncanonical_report_candidate():
    candidate = object.__new__(ReportCandidate)
    object.__setattr__(
        candidate,
        "path",
        PurePosixPath("/workspace/other-report.md"),
    )
    object.__setattr__(candidate, "content", "# Wrong path")
    return candidate


def test_generic_report_candidate_builds_canonical_artifact():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="# Verified-shaped report",
            )
        )
    )

    assert result["artifact_id"] == "research-report.md"
    assert result["kind"] == "research_report_markdown"
    assert result["media_type"] == "text/markdown"
    assert result["content"] == "# Verified-shaped report"
    assert result["content_hash"] == hashlib.sha256(
        result["content"].encode("utf-8")
    ).hexdigest()


def test_generic_report_candidate_is_sanitized_before_hashing():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content=(
                    "# Report\n"
                    "Useful finding.\n"
                    "host=/Users/private/project/tasks.db\n"
                    "Traceback (most recent call last):\n"
                    "checkpoint_thread_id=thread-1\n"
                    "checkpoint metadata: /private/var/tmp/state.sqlite\n"
                ),
            )
        )
    )

    content = result["content"]
    assert result["kind"] == "research_report_markdown"
    assert "Useful finding." in content
    assert "/Users/private" not in content
    assert "tasks.db" not in content
    assert "Traceback" not in content
    assert "checkpoint" not in content.lower()
    assert "/private/var" not in content
    assert result["content_hash"] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def test_absent_report_builds_explicit_fallback():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(report_candidate=None, last_agent_text="partial")
    )

    assert result["artifact_id"] == "research-report.md"
    assert result["kind"] == "research_report_fallback_markdown"
    assert result["media_type"] == "text/markdown"
    assert "# Fallback Report" in result["content"]
    assert "partial" in result["content"]


def test_empty_report_builds_explicit_fallback():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content=" \n\t",
            ),
            last_agent_text="last bounded text",
        )
    )

    assert result["kind"] == "research_report_fallback_markdown"
    assert "last bounded text" in result["content"]


def test_noncanonical_virtual_path_builds_fallback():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=_noncanonical_report_candidate(),
            last_agent_text="fallback source",
        )
    )

    assert result["kind"] == "research_report_fallback_markdown"
    assert "/workspace/other-report.md" not in result["content"]


def test_over_one_mib_report_builds_bounded_fallback():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content="x" * (1024 * 1024 + 1),
            ),
            last_agent_text="oversized report summary",
        )
    )

    assert result["kind"] == "research_report_fallback_markdown"
    assert len(result["content"].encode("utf-8")) < 1024 * 1024


def test_fallback_redacts_absolute_paths_and_diagnostics():
    from api.run_result_service import build_generic_result_artifact

    result = build_generic_result_artifact(
        _outcome(
            report_candidate=None,
            last_agent_text=(
                "Output under /Users/private/project and "
                "Traceback (most recent call last)"
            ),
            diagnostics=[
                "db_path:/Users/private/data/tasks.db",
                "secret=do-not-emit",
            ],
        )
    )

    content = result["content"]
    assert "/Users/private" not in content
    assert "Traceback" not in content
    assert "tasks.db" not in content
    assert "do-not-emit" not in content


def test_fallback_is_deterministic_for_fixed_generated_at():
    from api.run_result_service import build_generic_result_artifact

    generated_at = datetime(2026, 6, 26, 5, 0, tzinfo=timezone.utc)

    first = build_generic_result_artifact(
        _outcome(report_candidate=None, last_agent_text="same"),
        generated_at=generated_at,
    )
    second = build_generic_result_artifact(
        _outcome(report_candidate=None, last_agent_text="same"),
        generated_at=generated_at,
    )

    assert first == second
    assert generated_at.isoformat() in first["content"]
