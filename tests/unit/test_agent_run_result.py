"""Tests for agent run result accumulation."""
from langchain_core.messages import AIMessage, ToolMessage


class CapturingMonitor:
    def __init__(self):
        self.assistant_calls = []
        self.task_results = []

    def report_assistant(self, assistant_name, args=None):
        self.assistant_calls.append((assistant_name, args))

    def report_task_result(self, result):
        self.task_results.append(result)


class TestAgentRunAccumulator:
    def test_records_task_tool_calls_and_emits_existing_monitor_event(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-001",
            query="研究问题",
            session_dir=tmp_path,
        )
        chunk = {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "subagent_type": "network_search",
                                    "description": "搜索公开资料",
                                },
                                "id": "call-1",
                            }
                        ],
                    )
                ]
            }
        }

        process_stream_chunk(chunk, accumulator, monitor)

        assert accumulator.assistant_calls == 1
        assert monitor.assistant_calls == [
            ("network_search", {"desc": "搜索公开资料"})
        ]

    def test_records_last_non_empty_ai_text(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-002",
            query="研究问题",
            session_dir=tmp_path,
        )

        process_stream_chunk(
            {"agent": {"messages": [AIMessage(content="第一段结果")]}},
            accumulator,
            monitor,
        )
        process_stream_chunk(
            {"agent": {"messages": [AIMessage(content="最终结果")]}},
            accumulator,
            monitor,
        )

        assert accumulator.last_agent_text == "最终结果"
        assert monitor.task_results == ["第一段结果", "最终结果"]

    def test_records_tool_messages_as_tool_events(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-003",
            query="研究问题",
            session_dir=tmp_path,
        )

        process_stream_chunk(
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="工具输出",
                            tool_call_id="call-1",
                            name="tavily_search",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )

        assert accumulator.tool_starts == 1
        assert accumulator.diagnostics == ["tool:tavily_search"]

    def test_collects_evidence_entries_from_tool_messages(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-evidence",
            query="研究 AI 搜索趋势",
            session_dir=tmp_path,
        )

        process_stream_chunk(
            {
                "network_search": {
                    "messages": [
                        ToolMessage(
                            content=(
                                '[{"url": "https://example.com/report", '
                                '"content": "Agent benchmark findings"}]'
                            ),
                            tool_call_id="call-1",
                            name="tavily_search",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )

        assert len(accumulator.evidence_entries) == 1
        evidence = accumulator.evidence_entries[0]
        assert evidence.thread_id == "thread-evidence"
        assert evidence.query_text == "研究 AI 搜索趋势"
        assert evidence.subagent_name == "network_search"
        assert evidence.tool_name == "tavily_search"
        assert evidence.source_url == "https://example.com/report"
        assert evidence.snippet == "Agent benchmark findings"
        assert evidence.citation_status == "uncited"
        assert evidence.verification_status == "unverified"

    def test_to_result_copies_accumulator_state(self, tmp_path):
        from agent.run_result import AgentRunAccumulator

        accumulator = AgentRunAccumulator(
            thread_id="thread-004",
            query="研究问题",
            session_dir=tmp_path,
        )
        accumulator.last_agent_text = "最终结果"
        accumulator.assistant_calls = 2
        accumulator.tool_starts = 3
        accumulator.diagnostics.append("tool:tavily_search")

        result = accumulator.to_result()

        assert result.thread_id == "thread-004"
        assert result.query == "研究问题"
        assert result.session_dir == tmp_path
        assert result.last_agent_text == "最终结果"
        assert result.assistant_calls == 2
        assert result.tool_starts == 3
        assert result.diagnostics == ["tool:tavily_search"]
        assert result.evidence_entries == []
        assert result.error_message is None
