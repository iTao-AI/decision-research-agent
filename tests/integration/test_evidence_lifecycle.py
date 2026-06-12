import subprocess
import sys
import textwrap
from pathlib import Path


def test_run_deep_agent_freezes_shared_context_evidence_before_cleanup(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        class FakeAgent:
            async def astream(self, *args, **kwargs):
                if False:
                    yield None

        main_agent.main_agent = FakeAgent()
        main_agent.project_root = Path({str(tmp_path)!r})
        main_agent.shared_context.publish_fact(
            "thread-lifecycle",
            "SharedContext-only evidence",
            "https://example.com/shared-only",
            "search_evidence",
        )

        from agent.run_result import OutcomeBox
        box = OutcomeBox()
        outcome = asyncio.run(
            main_agent.run_deep_agent("query", "thread-lifecycle", outcome_box=box)
        )

        assert outcome.evidence_entries[0].source_url == "https://example.com/shared-only"
        assert box.latest().evidence_entries == outcome.evidence_entries
        assert main_agent.shared_context.query_facts("thread-lifecycle", "search_evidence") == []
        print("OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_run_deep_agent_publishes_partial_outcome_before_exception_cleanup(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        class FakeAgent:
            async def astream(self, *args, **kwargs):
                main_agent.shared_context.publish_fact(
                    "thread-failed",
                    "Partial evidence",
                    "https://example.com/partial",
                    "search_evidence",
                )
                raise RuntimeError("boom")
                yield

        main_agent.main_agent = FakeAgent()
        main_agent.project_root = Path({str(tmp_path)!r})

        from agent.run_result import OutcomeBox
        box = OutcomeBox()
        try:
            asyncio.run(main_agent.run_deep_agent("query", "thread-failed", outcome_box=box))
        except RuntimeError:
            pass

        assert box.latest().failure_kind == "execution_error"
        assert box.latest().evidence_entries[0].source_url == "https://example.com/partial"
        assert main_agent.shared_context.query_facts("thread-failed", "search_evidence") == []
        print("OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_run_deep_agent_uses_run_id_for_runtime_state_but_thread_id_for_langgraph(
    tmp_path,
):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        captured = {{}}

        class FakeAgent:
            async def astream(self, *args, **kwargs):
                captured["config"] = kwargs["config"]
                main_agent.shared_context.publish_fact(
                    "run-1",
                    "Run-scoped evidence",
                    "https://example.com/run-scoped",
                    "search_evidence",
                )
                if False:
                    yield None

        main_agent.main_agent = FakeAgent()
        main_agent.project_root = Path({str(tmp_path)!r})

        outcome = asyncio.run(
            main_agent.run_deep_agent("query", "thread-1", run_id="run-1")
        )

        assert outcome.thread_id == "thread-1"
        assert outcome.run_id == "run-1"
        assert outcome.session_dir.name == "session_run-1"
        assert captured["config"]["configurable"]["thread_id"] == "thread-1"
        assert captured["config"]["metadata"]["research_run_id"] == "run-1"
        assert outcome.evidence_entries[0].source_url == "https://example.com/run-scoped"
        assert main_agent.shared_context.query_facts("run-1", "search_evidence") == []
        print("OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_talent_profile_does_not_copy_uploaded_files_into_run_workspace(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        class FakeTalentAgent:
            async def astream(self, *args, **kwargs):
                from api.context import get_allowed_source_domains_context
                assert get_allowed_source_domains_context() == ("jobs.example.com",)
                if False:
                    yield None

        main_agent.project_root = Path({str(tmp_path)!r})
        upload_dir = main_agent.project_root / "updated" / "session_run-talent"
        upload_dir.mkdir(parents=True)
        (upload_dir / "private.txt").write_text("private", encoding="utf-8")
        main_agent.agent_factory._compiled[
            ("talent-hiring-signal", "1", "talent-restricted-v1")
        ] = FakeTalentAgent()

        outcome = asyncio.run(
            main_agent.run_deep_agent(
                "query",
                "thread-talent",
                run_id="run-talent",
                profile_id="talent-hiring-signal",
                scope={{
                    "declared_samples": [
                        {{
                            "source_type": "public_job_posting",
                            "reference": "https://jobs.example.com/role",
                        }}
                    ]
                }},
            )
        )

        assert not (outcome.session_dir / "private.txt").exists()
        from api.context import get_allowed_source_domains_context
        assert get_allowed_source_domains_context() == ()
        print("OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
