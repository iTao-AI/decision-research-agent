"""Integration tests for server-side task finalization."""
import pytest

from agent.run_result import AgentRunResult


@pytest.fixture
def task_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(db_path))
    return str(db_path)


def _save_task(thread_id: str, query: str):
    from api.persistence import save_task

    save_task(thread_id=thread_id, query=query, status="pending")


class TestServerTaskFinalization:
    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_completed_when_report_exists(
        self,
        tmp_path,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-completed"
        query = "query"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        report = session_dir / "report.md"
        report.write_text("report", encoding="utf-8")
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            assert task_query == query
            assert task_thread_id == thread_id
            return AgentRunResult(
                thread_id=thread_id,
                query=query,
                session_dir=session_dir,
                last_agent_text="agent text",
            )

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        finalization = await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert finalization.status == "completed"
        assert task["status"] == "completed"
        assert task["output_path"] == str(report)

    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_completed_with_fallback(
        self,
        tmp_path,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-fallback"
        query = "query"
        session_dir = tmp_path / f"session_{thread_id}"
        session_dir.mkdir()
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            return AgentRunResult(
                thread_id=thread_id,
                query=query,
                session_dir=session_dir,
                last_agent_text="agent text",
            )

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        finalization = await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert finalization.status == "completed_with_fallback"
        assert task["status"] == "completed_with_fallback"
        assert task["output_path"].endswith("fallback_report.md")

    @pytest.mark.asyncio
    async def test_run_task_with_persistence_marks_failed_on_exception(
        self,
        task_db,
        monkeypatch,
    ):
        import api.server as server
        from api.persistence import get_task

        thread_id = "server-failed"
        query = "query"
        _save_task(thread_id, query)

        async def fake_run_deep_agent(task_query, task_thread_id):
            raise RuntimeError("agent failed")

        monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)

        with pytest.raises(RuntimeError):
            await server._run_task_with_persistence(query, thread_id)

        task = get_task(thread_id=thread_id)
        assert task["status"] == "failed"
        assert task["error_message"] == "agent failed"

    @pytest.mark.asyncio
    async def test_mark_task_timeout_persists_failed_status(self, task_db):
        import api.server as server
        from api.persistence import get_research_run_with_evidence, get_task

        thread_id = "server-timeout"
        _save_task(thread_id, "query")

        await server._mark_task_timeout(thread_id, 7)

        task = get_task(thread_id=thread_id)
        research_run = get_research_run_with_evidence(thread_id=thread_id)

        assert task["status"] == "failed"
        assert task["error_message"] == "Agent task timed out after 7s"
        assert research_run["status"] == "failed"
        assert research_run["quality_report"]["issues"][0]["code"] == "task_timeout"
