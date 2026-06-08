"""Task finalization: report selection, fallback report, and persistence."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from agent.run_result import AgentRunResult
from agent.research import evaluate_report_quality, prepare_final_evidence
from agent.token_tracking import token_collector
from api.monitor import monitor
from api.persistence import replace_evidence_entries, save_research_run, update_task


@dataclass(frozen=True)
class TaskFinalization:
    thread_id: str
    status: str
    output_path: str | None
    fallback_used: bool
    error_message: str | None = None


def _find_latest_markdown_report(run_result: AgentRunResult) -> Path | None:
    started_timestamp = (
        run_result.started_at.timestamp() if run_result.started_at is not None else None
    )
    candidates = [
        path
        for path in run_result.session_dir.glob("*.md")
        if path.name != "fallback_report.md"
        and path.is_file()
        and path.stat().st_size > 0
        and (started_timestamp is None or path.stat().st_mtime >= started_timestamp)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _fallback_report_content(run_result: AgentRunResult) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    diagnostics = (
        "\n".join(f"- {item}" for item in run_result.diagnostics)
        or "- No diagnostic events captured"
    )
    last_agent_text = (
        run_result.last_agent_text.strip() or "No final agent text was captured."
    )

    return (
        "# Fallback Report\n\n"
        "This fallback report was generated because the agent task finished "
        "without a non-empty Markdown report.\n\n"
        f"- Thread ID: `{run_result.thread_id}`\n"
        f"- Generated at: `{generated_at}`\n"
        f"- Assistant calls observed: `{run_result.assistant_calls}`\n"
        f"- Tool messages observed: `{run_result.tool_starts}`\n\n"
        "## Original Query\n\n"
        f"{run_result.query}\n\n"
        "## Last Agent Output\n\n"
        f"{last_agent_text}\n\n"
        "## Diagnostics\n\n"
        f"{diagnostics}\n"
    )


def _write_fallback_report(run_result: AgentRunResult) -> Path:
    run_result.session_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = run_result.session_dir / "fallback_report.md"
    fallback_path.write_text(_fallback_report_content(run_result), encoding="utf-8")
    return fallback_path


def _token_usage(thread_id: str) -> dict:
    return token_collector.get_summary(thread_id)


def _token_usage_json(token_usage: dict) -> str:
    return json.dumps(token_usage, ensure_ascii=False)


def persist_research_run(
    run_result: AgentRunResult,
    status: str,
    output_path: str | None,
    fallback_used: bool,
    token_usage: dict,
) -> None:
    """Persist the auditable research run and its evidence ledger."""
    report_path = Path(output_path) if output_path else None
    evidence_entries = prepare_final_evidence(
        run_result.evidence_entries,
        report_path,
    )
    quality_report = evaluate_report_quality(
        report_path=report_path,
        fallback_used=fallback_used,
        evidence_entries=evidence_entries,
        token_usage=token_usage,
        diagnostics=run_result.diagnostics,
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    save_research_run(
        thread_id=run_result.thread_id,
        query=run_result.query,
        status=status,
        started_at=(
            run_result.started_at.isoformat()
            if run_result.started_at is not None
            else None
        ),
        completed_at=completed_at,
        output_path=output_path,
        fallback_used=fallback_used,
        assistant_calls=run_result.assistant_calls,
        tool_starts=run_result.tool_starts,
        diagnostics_json=json.dumps(run_result.diagnostics, ensure_ascii=False),
        token_usage_json=_token_usage_json(token_usage),
        quality_report_json=json.dumps(quality_report.to_dict(), ensure_ascii=False),
    )
    replace_evidence_entries(
        thread_id=run_result.thread_id,
        entries=evidence_entries,
    )


def finalize_task_run(run_result: AgentRunResult) -> TaskFinalization:
    """Persist a successful agent run as completed or completed_with_fallback."""
    report_path = _find_latest_markdown_report(run_result)
    fallback_used = False
    status = "completed"

    if report_path is None:
        report_path = _write_fallback_report(run_result)
        fallback_used = True
        status = "completed_with_fallback"

    output_path = str(report_path)
    token_usage = _token_usage(run_result.thread_id)
    persist_research_run(
        run_result=run_result,
        status=status,
        output_path=output_path,
        fallback_used=fallback_used,
        token_usage=token_usage,
    )
    update_task(
        thread_id=run_result.thread_id,
        status=status,
        output_path=output_path,
        token_usage_json=_token_usage_json(token_usage),
    )
    monitor.report_task_finalized(
        thread_id=run_result.thread_id,
        status=status,
        fallback_used=fallback_used,
        output_path=output_path,
        error_message=None,
    )
    if fallback_used:
        monitor.report_task_result("任务已完成但未生成正式报告，系统已创建兜底报告。")

    return TaskFinalization(
        thread_id=run_result.thread_id,
        status=status,
        output_path=output_path,
        fallback_used=fallback_used,
        error_message=None,
    )
