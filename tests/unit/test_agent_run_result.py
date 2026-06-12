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

    def test_talent_task_message_collects_schema_valid_research_packet(self, tmp_path):
        import json

        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        packet = {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Agent evaluation appears in the declared sample.",
                    "evidence_refs": ["ev-1"],
                    "sample_scope": "declared samples",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Agent evaluation is a recurring signal.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": ["ev-1"],
                    "confidence": 0.8,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "pending",
                    "conflict_status": "none",
                }
            ],
        }

        process_stream_chunk(
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content=json.dumps(packet),
                            tool_call_id="call-task",
                            name="task",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )

        assert [item.packet_id for item in accumulator.research_packets] == ["packet-1"]
        assert accumulator.evidence_entries == []

    def test_talent_invalid_task_message_fails_closed_in_outcome(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )

        process_stream_chunk(
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content='{"packet_id": "broken"}',
                            tool_call_id="call-task",
                            name="task",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )
        outcome = accumulator.to_outcome()

        assert outcome.failure_kind == "invalid_research_packet"
        assert outcome.research_packets == []

    def test_talent_task_message_with_broken_finding_reference_fails_closed(
        self, tmp_path
    ):
        import json

        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        packet = {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Unsupported claim.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["missing-finding"],
                    "evidence_refs": ["ev-1"],
                    "confidence": 0.8,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "pending",
                    "conflict_status": "none",
                }
            ],
        }

        process_stream_chunk(
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content=json.dumps(packet),
                            tool_call_id="call-task",
                            name="task",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )

        assert accumulator.to_outcome().failure_kind == "invalid_research_packet"

    def test_talent_missing_packet_does_not_mask_execution_failure(self, tmp_path):
        from agent.run_result import AgentRunAccumulator

        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )

        outcome = accumulator.to_outcome(failure_kind="execution_error")

        assert outcome.failure_kind == "execution_error"

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


class TestOutcomeBox:
    def test_publishes_latest_immutable_execution_outcome(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, ExecutionOutcome, OutcomeBox

        accumulator = AgentRunAccumulator(
            thread_id="thread-outcome",
            query="query",
            session_dir=tmp_path,
        )
        outcome = accumulator.to_outcome(
            failure_kind="timeout",
            cancellation_state="cancelled",
        )
        box = OutcomeBox()

        box.publish(outcome)

        assert isinstance(box.latest(), ExecutionOutcome)
        assert box.latest().failure_kind == "timeout"
        assert box.latest().cancellation_state == "cancelled"
