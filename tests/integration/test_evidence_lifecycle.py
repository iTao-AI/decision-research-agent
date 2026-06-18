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
                from api.context import (
                    get_allowed_aggregate_ids_context,
                    get_allowed_source_domains_context,
                )
                assert get_allowed_source_domains_context() == ("jobs.example.com",)
                assert get_allowed_aggregate_ids_context() == ("aggregate-v1",)
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
                        }},
                        {{
                            "source_type": "provided_aggregate",
                            "reference": "aggregate-v1",
                        }}
                    ]
                }},
            )
        )

        assert not (outcome.session_dir / "private.txt").exists()
        from api.context import (
            get_allowed_aggregate_ids_context,
            get_allowed_source_domains_context,
        )
        assert get_allowed_source_domains_context() == ()
        assert get_allowed_aggregate_ids_context() == ()
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


def test_talent_run_prefetches_declared_aggregate_evidence_and_normalizes_refs(tmp_path):
    fixtures = tmp_path / "benchmarks" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "aggregate-v1.json").write_text(
        '''
        {
          "aggregate_id": "aggregate-v1",
          "samples": [
            {
              "sample_id": "sample-1",
              "source_url": "https://jobs.example.com/role",
              "content": "AI Agent role requires evaluation and observability."
            },
            {
              "sample_id": "sample-2",
              "source_url": "https://jobs.example.com/role-2",
              "content": "AI Agent role requires RAG and tool integration."
            }
          ]
        }
        ''',
        encoding="utf-8",
    )
    script = textwrap.dedent(
        f"""
        import asyncio
        import json
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import ToolMessage

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"
        os.environ["DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"] = "true"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        import tools.provided_aggregate as aggregate_tool
        aggregate_tool.FIXTURE_ROOT = Path({str(fixtures)!r})

        class FakeTalentAgent:
            async def astream(self, *args, **kwargs):
                packet = {{
                    "packet_id": "packet-1",
                    "scope_id": "aggregate-v1",
                    "findings": [{{
                        "finding_id": "finding-1",
                        "research_question_id": "question-1",
                        "statement": "Evaluation appears in the declared sample.",
                        "evidence_refs": ["S1", "sample-snapshot-2", "sample_id:job-2"],
                        "sample_scope": "declared samples",
                        "confidence": 0.8,
                    }}],
                    "candidate_claims": [{{
                        "claim_id": "claim-1",
                        "text": "Evaluation is a hiring signal.",
                        "claim_type": "signal",
                        "finding_refs": ["finding-1"],
                        "evidence_refs": ["sample-001", "aggregate-v1"],
                        "confidence": 0.8,
                        "citation_status": "cited",
                        "verification_status": "unverified",
                        "review_status": "pending",
                        "conflict_status": "none",
                    }}],
                }}
                yield {{
                    "tools": {{
                        "messages": [
                            ToolMessage(
                                content=json.dumps(packet),
                                tool_call_id="call-task",
                                name="task",
                            )
                        ]
                    }}
                }}

        main_agent.project_root = Path({str(tmp_path)!r})
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
                    "declared_samples": [{{
                        "sample_id": "aggregate-v1",
                        "source_type": "provided_aggregate",
                        "reference": "aggregate-v1",
                    }}]
                }},
            )
        )

        assert [entry.source_url for entry in outcome.evidence_entries] == [
            "https://jobs.example.com/role",
            "https://jobs.example.com/role-2",
        ]
        assert all(entry.verification_status == "verified" for entry in outcome.evidence_entries)
        evidence_ids = [
            "ev_run-talent_" + entry.evidence_fingerprint
            for entry in outcome.evidence_entries
        ]
        assert outcome.research_packets[0].findings[0].evidence_refs == evidence_ids
        assert outcome.research_packets[0].candidate_claims[0].evidence_refs == evidence_ids
        assert main_agent.shared_context.query_facts("run-talent", "search_evidence") == []
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


def test_talent_profile_sets_bounded_recursion_limit(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"
        os.environ["DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT"] = "37"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        captured = {{}}

        class FakeTalentAgent:
            async def astream(self, *args, **kwargs):
                captured["config"] = kwargs["config"]
                if False:
                    yield None

        main_agent.project_root = Path({str(tmp_path)!r})
        main_agent.agent_factory._compiled[
            ("talent-hiring-signal", "1", "talent-restricted-v1")
        ] = FakeTalentAgent()

        outcome = asyncio.run(
            main_agent.run_deep_agent(
                "query",
                "thread-talent",
                run_id="run-talent",
                profile_id="talent-hiring-signal",
                scope={{"declared_samples": []}},
            )
        )

        assert captured["config"]["recursion_limit"] == 37
        assert outcome.failure_kind == "missing_research_packet"
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


def test_talent_profile_returns_failure_outcome_on_recursion_limit(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from langgraph.errors import GraphRecursionError

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        class LoopingTalentAgent:
            async def astream(self, *args, **kwargs):
                raise GraphRecursionError("recursion limit reached")
                yield

        main_agent.project_root = Path({str(tmp_path)!r})
        main_agent.agent_factory._compiled[
            ("talent-hiring-signal", "1", "talent-restricted-v1")
        ] = LoopingTalentAgent()

        from agent.run_result import OutcomeBox
        box = OutcomeBox()
        outcome = asyncio.run(
            main_agent.run_deep_agent(
                "query",
                "thread-loop",
                run_id="run-loop",
                outcome_box=box,
                profile_id="talent-hiring-signal",
                scope={{"declared_samples": []}},
            )
        )

        assert outcome.failure_kind == "recursion_limit_exceeded"
        assert "recursion limit reached" in outcome.error_message
        assert box.latest() == outcome
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


def test_talent_preload_failure_records_diagnostics_and_resets_context(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"
        os.environ["DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"] = "true"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        import tools.provided_aggregate as aggregate_tool
        from api.context import get_run_context

        class FakeTalentAgent:
            async def astream(self, *args, **kwargs):
                if False:
                    yield None

        def boom(*args, **kwargs):
            raise RuntimeError("fixture read failed")

        main_agent.project_root = Path({str(tmp_path)!r})
        main_agent.agent_factory._compiled[
            ("talent-hiring-signal", "1", "talent-restricted-v1")
        ] = FakeTalentAgent()

        with patch.object(type(aggregate_tool.provided_aggregate), "invoke", side_effect=boom):
            outcome = asyncio.run(
                main_agent.run_deep_agent(
                    "query",
                    "thread-preload",
                    run_id="run-preload",
                    profile_id="talent-hiring-signal",
                    scope={{
                        "declared_samples": [{{
                            "sample_id": "aggregate-v1",
                            "source_type": "provided_aggregate",
                            "reference": "aggregate-v1",
                        }}]
                    }},
                )
            )

        assert "provided_aggregate_preload_failed:RuntimeError" in outcome.diagnostics
        assert outcome.failure_kind == "missing_research_packet"
        assert get_run_context() is None
        assert main_agent.shared_context.query_facts("run-preload", "search_evidence") == []
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


def test_talent_preload_records_non_ok_and_malformed_result_diagnostics(tmp_path):
    script = textwrap.dedent(
        f"""
        import asyncio
        import os
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["OPENAI_BASE_URL"] = "http://test"
        os.environ["LLM_QWEN_MAX"] = "test"
        os.environ["DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES"] = "true"

        with patch("deepagents.create_deep_agent", return_value=MagicMock()):
            import agent.main_agent as main_agent

        import tools.provided_aggregate as aggregate_tool
        from agent.run_result import AgentRunAccumulator

        accumulator = AgentRunAccumulator(
            thread_id="thread-preload",
            query="query",
            session_dir=Path({str(tmp_path)!r}),
            profile_id="talent-hiring-signal",
            run_id="run-preload",
        )
        responses = iter([
            "not-a-dict",
            {{"status": "error", "error": {{"code": "fixture_bad"}}}},
            {{
                "status": "ok",
                "results": [
                    "bad-item",
                    {{"sample_id": "missing-id"}},
                    {{
                        "sample_id": "sample-1",
                        "url": "https://jobs.example.com/role",
                        "evidence_id": "ev_run-preload_abc",
                    }},
                ],
            }},
        ])

        def fake_invoke(*args, **kwargs):
            return next(responses)

        with patch.object(type(aggregate_tool.provided_aggregate), "invoke", side_effect=fake_invoke):
            asyncio.run(
                main_agent._preload_declared_aggregate_evidence(
                    accumulator,
                    ("bad-type", "bad-status", "aggregate-v1"),
                )
            )

        assert "provided_aggregate_preload_failed:invalid_preload_result" in accumulator.diagnostics
        assert "provided_aggregate_preload_failed:fixture_bad" in accumulator.diagnostics
        assert "provided_aggregate_item_invalid" in accumulator.diagnostics
        assert "provided_aggregate_item_missing_evidence_id" in accumulator.diagnostics
        assert "provided_aggregate_prefetched:aggregate-v1" in accumulator.diagnostics
        assert accumulator.evidence_aliases["aggregate-v1"] == ("ev_run-preload_abc",)
        assert accumulator.evidence_aliases["sample-1"] == ("ev_run-preload_abc",)
        assert accumulator.evidence_aliases["E-sample-1"] == ("ev_run-preload_abc",)
        assert "__declared_aggregate__" not in accumulator.evidence_aliases
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
