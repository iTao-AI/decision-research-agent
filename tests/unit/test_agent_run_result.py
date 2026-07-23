"""Tests for agent run result accumulation."""
from langchain_core.messages import AIMessage, ToolMessage
import pytest


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

    def test_collects_evidence_only_from_network_search_internet_search(
        self, tmp_path
    ):
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
                            name="internet_search",
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
        assert evidence.tool_name == "internet_search"
        assert evidence.source_url == "https://example.com/report"
        assert evidence.snippet == "Agent benchmark findings"
        assert evidence.citation_status == "uncited"
        assert evidence.verification_status == "unverified"

    @pytest.mark.parametrize(
        ("node_name", "tool_name", "source_url"),
        [
            ("tools", "task", "https://example.com/task-summary"),
            ("tools", "task", "http://example.com/task-summary"),
            ("tools", "write_file", "https://example.com/file"),
            ("database_query", "database_query", "https://example.com/database"),
            (
                "knowledge_base",
                "knowledge_base_search",
                "https://example.com/knowledge",
            ),
            ("arbitrary_agent", "internet_search", "https://example.com/arbitrary"),
            ("network_search", "write_file", "https://example.com/network-file"),
        ],
    )
    def test_non_source_tool_messages_never_create_evidence(
        self,
        tmp_path,
        node_name,
        tool_name,
        source_url,
    ):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        accumulator = AgentRunAccumulator(
            thread_id="thread-no-authority",
            query="研究问题",
            session_dir=tmp_path,
        )
        process_stream_chunk(
            {
                node_name: {
                    "messages": [
                        ToolMessage(
                            content={
                                "results": [
                                    {
                                        "url": source_url,
                                        "content": "not source-authoritative",
                                    }
                                ]
                            },
                            tool_call_id="call-no-authority",
                            name=tool_name,
                        )
                    ]
                }
            },
            accumulator,
            CapturingMonitor(),
        )

        assert accumulator.evidence_entries == []

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

    def test_talent_structured_response_collects_research_packet(self, tmp_path):
        from agent.run_result import AgentRunAccumulator, process_stream_chunk
        from agent.talent_contracts import ResearchPacket

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        packet = ResearchPacket.model_validate(
            {
                "packet_id": "packet-structured",
                "scope_id": "scope-1",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "research_question_id": "question-1",
                        "statement": "Declared sample contains a signal.",
                        "evidence_refs": ["sample-1"],
                        "sample_scope": "declared samples",
                        "confidence": 0.8,
                    }
                ],
                "candidate_claims": [
                    {
                        "claim_id": "claim-1",
                        "text": "Declared sample contains a signal.",
                        "claim_type": "hiring_signal",
                        "finding_refs": ["finding-1"],
                        "evidence_refs": ["sample-1"],
                        "confidence": 0.8,
                        "citation_status": "cited",
                        "verification_status": "unverified",
                        "review_status": "pending",
                        "conflict_status": "none",
                    }
                ],
            }
        )

        process_stream_chunk(
            {"agent": {"messages": [], "structured_response": packet}},
            accumulator,
            monitor,
        )

        assert accumulator.research_packets == [packet]
        assert "research_packet:packet-structured" in accumulator.diagnostics

    def test_talent_outcome_normalizes_declared_evidence_alias_refs(self, tmp_path):
        import json

        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        accumulator.evidence_aliases = {
            "sample-1": ("ev_run_abc",),
            "E-sample-1": ("ev_run_abc",),
            "aggregate-v1": ("ev_run_abc", "ev_run_def"),
        }
        packet = {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Agent evaluation appears in the declared sample.",
                    "evidence_refs": ["E-sample-1"],
                    "sample_scope": "declared samples",
                    "confidence": 0.8,
                },
                {
                    "finding_id": "finding-2",
                    "research_question_id": "question-1",
                    "statement": "Aggregate-level limitation applies.",
                    "evidence_refs": ["ev_missing"],
                    "sample_scope": "declared aggregate",
                    "confidence": 0.7,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Agent evaluation is a recurring signal.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": ["aggregate-v1"],
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
        outcome = accumulator.to_outcome()

        assert outcome.research_packets[0].findings[0].evidence_refs == ["ev_run_abc"]
        assert outcome.research_packets[0].findings[1].evidence_refs == [
            "ev_missing"
        ]
        assert outcome.research_packets[0].candidate_claims[0].evidence_refs == [
            "ev_run_abc",
            "ev_run_def",
        ]

    def test_talent_invalid_research_packet_records_validation_reason(self, tmp_path):
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
                            content='{"packet_id":"packet-1"}',
                            tool_call_id="call-task",
                            name="task",
                        )
                    ]
                }
            },
            accumulator,
            monitor,
        )

        assert any(
            diagnostic.startswith("invalid_research_packet:ValidationError:")
            for diagnostic in accumulator.diagnostics
        )

    def test_talent_outcome_preserves_unknown_evidence_refs(self, tmp_path):
        import json

        from agent.run_result import AgentRunAccumulator, process_stream_chunk

        monitor = CapturingMonitor()
        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        accumulator.evidence_aliases = {"sample-1": ("ev_run_abc",)}
        packet = {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "research_question_id": "question-1",
                    "statement": "Unknown refs should remain reviewable.",
                    "evidence_refs": ["sample-1", "ev_missing"],
                    "sample_scope": "declared samples",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Unknown refs should remain reviewable.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["finding-1"],
                    "evidence_refs": ["ev_missing"],
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
        outcome = accumulator.to_outcome()

        assert outcome.research_packets[0].findings[0].evidence_refs == [
            "ev_run_abc",
            "ev_missing",
        ]
        assert outcome.research_packets[0].candidate_claims[0].evidence_refs == [
            "ev_missing"
        ]

    def test_talent_outcome_uses_latest_research_packet_when_subagent_retries(
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
        first_packet = {
            "packet_id": "packet-stale",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-stale",
                    "research_question_id": "question-1",
                    "statement": "Stale packet reported an access failure.",
                    "evidence_refs": ["sample-stale"],
                    "sample_scope": "declared samples",
                    "confidence": 0.8,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-stale",
                    "text": "Stale packet should not pollute final artifacts.",
                    "claim_type": "methodological_observation",
                    "finding_refs": ["finding-stale"],
                    "evidence_refs": ["sample-stale"],
                    "confidence": 0.8,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "required",
                    "conflict_status": "none",
                }
            ],
        }
        final_packet = {
            "packet_id": "packet-final",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-final",
                    "research_question_id": "question-1",
                    "statement": "Final packet cites declared evidence.",
                    "evidence_refs": ["sample-1"],
                    "sample_scope": "declared samples",
                    "confidence": 0.9,
                }
            ],
            "candidate_claims": [
                {
                    "claim_id": "claim-final",
                    "text": "Final packet should drive review artifacts.",
                    "claim_type": "hiring_signal",
                    "finding_refs": ["finding-final"],
                    "evidence_refs": ["sample-1"],
                    "confidence": 0.9,
                    "citation_status": "cited",
                    "verification_status": "unverified",
                    "review_status": "pending",
                    "conflict_status": "none",
                }
            ],
        }

        for packet in (first_packet, final_packet):
            process_stream_chunk(
                {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(packet),
                                tool_call_id=f"call-{packet['packet_id']}",
                                name="task",
                            )
                        ]
                    }
                },
                accumulator,
                monitor,
            )
        accumulator.evidence_aliases = {"sample-1": ("ev_run_abc",)}
        outcome = accumulator.to_outcome()

        assert [packet.packet_id for packet in outcome.research_packets] == [
            "packet-final"
        ]
        assert outcome.research_packets[0].findings[0].evidence_refs == ["ev_run_abc"]
        assert "research_packet_superseded:1:packet-stale" in outcome.diagnostics

    def test_talent_outcome_freezes_when_evidence_ref_normalization_fails(
        self, tmp_path, monkeypatch
    ):
        import agent.run_result as run_result

        accumulator = run_result.AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )

        def broken_normalize(*args, **kwargs):
            raise RuntimeError("broken")

        monkeypatch.setattr(
            run_result,
            "_normalize_research_packet_evidence_refs",
            broken_normalize,
        )
        outcome = accumulator.to_outcome()

        assert outcome.failure_kind == "invalid_research_packet"
        assert "evidence_ref_normalization_failed:RuntimeError" in outcome.diagnostics

    def test_talent_outcome_supersedes_packets_when_normalization_fails(
        self, tmp_path, monkeypatch
    ):
        import agent.run_result as run_result
        from agent.talent_contracts import Claim, Finding, ResearchPacket

        accumulator = run_result.AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        stale_packet = ResearchPacket(
            packet_id="packet-stale",
            scope_id="scope-1",
            findings=[
                Finding(
                    finding_id="finding-stale",
                    research_question_id="question-1",
                    statement="Stale packet should be discarded.",
                    evidence_refs=["sample-stale"],
                    sample_scope="declared samples",
                    confidence=0.5,
                )
            ],
            candidate_claims=[
                Claim(
                    claim_id="claim-stale",
                    text="Stale packet should not drive artifacts.",
                    claim_type="hiring_signal",
                    finding_refs=["finding-stale"],
                    evidence_refs=["sample-stale"],
                    confidence=0.5,
                    citation_status="cited",
                    verification_status="unverified",
                    review_status="pending",
                    conflict_status="none",
                )
            ],
        )
        final_packet = ResearchPacket(
            packet_id="packet-final",
            scope_id="scope-1",
            findings=[
                Finding(
                    finding_id="finding-final",
                    research_question_id="question-1",
                    statement="Final packet should be retained.",
                    evidence_refs=["sample-final"],
                    sample_scope="declared samples",
                    confidence=0.9,
                )
            ],
            candidate_claims=[
                Claim(
                    claim_id="claim-final",
                    text="Final packet should drive artifacts.",
                    claim_type="hiring_signal",
                    finding_refs=["finding-final"],
                    evidence_refs=["sample-final"],
                    confidence=0.9,
                    citation_status="cited",
                    verification_status="unverified",
                    review_status="pending",
                    conflict_status="none",
                )
            ],
        )
        accumulator.research_packets.extend([stale_packet, final_packet])

        def broken_normalize(*args, **kwargs):
            raise RuntimeError("broken")

        monkeypatch.setattr(
            run_result,
            "_normalize_research_packet_evidence_refs",
            broken_normalize,
        )
        outcome = accumulator.to_outcome()

        assert outcome.failure_kind == "invalid_research_packet"
        assert [packet.packet_id for packet in outcome.research_packets] == [
            "packet-final"
        ]
        assert "evidence_ref_normalization_failed:RuntimeError" in outcome.diagnostics
        assert "research_packet_superseded:1:packet-stale" in outcome.diagnostics

    def test_talent_outcome_prefers_latest_packet_with_resolved_evidence_refs(
        self, tmp_path
    ):
        from agent.run_result import AgentRunAccumulator
        from agent.talent_contracts import Claim, Finding, ResearchPacket

        accumulator = AgentRunAccumulator(
            thread_id="thread-talent",
            query="研究招聘信号",
            session_dir=tmp_path,
            profile_id="talent-hiring-signal",
        )
        resolved_packet = ResearchPacket(
            packet_id="packet-resolved",
            scope_id="scope-1",
            findings=[
                Finding(
                    finding_id="finding-resolved",
                    research_question_id="question-1",
                    statement="Resolved packet cites declared evidence.",
                    evidence_refs=["sample-1"],
                    sample_scope="declared samples",
                    confidence=0.9,
                )
            ],
            candidate_claims=[
                Claim(
                    claim_id="claim-resolved",
                    text="Resolved packet should drive artifacts.",
                    claim_type="hiring_signal",
                    finding_refs=["finding-resolved"],
                    evidence_refs=["sample-1"],
                    confidence=0.9,
                    citation_status="cited",
                    verification_status="unverified",
                    review_status="pending",
                    conflict_status="none",
                )
            ],
        )
        unresolved_packet = ResearchPacket(
            packet_id="packet-unresolved",
            scope_id="scope-1",
            findings=[
                Finding(
                    finding_id="finding-unresolved",
                    research_question_id="question-1",
                    statement="Unresolved packet invents evidence.",
                    evidence_refs=["d1-f5e4c3"],
                    sample_scope="declared samples",
                    confidence=0.9,
                )
            ],
            candidate_claims=[
                Claim(
                    claim_id="claim-unresolved",
                    text="Unresolved packet should not replace resolved evidence.",
                    claim_type="hiring_signal",
                    finding_refs=["finding-unresolved"],
                    evidence_refs=["d1-f5e4c3"],
                    confidence=0.9,
                    citation_status="cited",
                    verification_status="unverified",
                    review_status="pending",
                    conflict_status="none",
                )
            ],
        )
        accumulator.research_packets.extend([resolved_packet, unresolved_packet])
        accumulator.evidence_aliases = {"sample-1": ("ev_run_abc",)}

        outcome = accumulator.to_outcome()

        assert [packet.packet_id for packet in outcome.research_packets] == [
            "packet-resolved"
        ]
        assert outcome.research_packets[0].findings[0].evidence_refs == ["ev_run_abc"]
        assert "research_packet_superseded:1:packet-unresolved" in outcome.diagnostics

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
