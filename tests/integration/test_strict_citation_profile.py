import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from api.research_execution_service import ResearchExecutionService


WORKER_ID = "dispatch_worker_22222222222222222222222222222222"


class ScriptedCorrectionModel:
    def __init__(self, content, *, events=None):
        self.content = content
        self.call_count = 0
        self.events = events

    async def ainvoke(self, messages, config=None):
        del messages, config
        self.call_count += 1
        if self.events is not None:
            self.events.append("model_entered")
        return AIMessage(content=self.content)


class ScriptedGenericHarness:
    def __init__(self, report):
        self.report = report

    async def execute(self, request, *, runtime_context, observer):
        del request, runtime_context
        namespace = ("tools:strict-citation",)
        observer.on_nested_stream_chunk(
            namespace,
            {
                "model": {
                    "messages": [
                        AIMessage(content="", name="network_search"),
                    ]
                }
            },
        )
        observer.on_nested_stream_chunk(
            namespace,
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content=json.dumps(
                                {
                                    "results": [
                                        {
                                            "url": "https://example.com/source",
                                            "content": "Source context",
                                        }
                                    ]
                                }
                            ),
                            tool_call_id="call-source",
                            name="internet_search",
                        )
                    ]
                }
            },
        )
        observer.on_stream_chunk(
            {
                "agent": {
                    "messages": [AIMessage(content="done")],
                    "files": {
                        "/workspace/research-report.md": {
                            "content": self.report,
                            "encoding": "utf-8",
                        }
                    },
                }
            }
        )
        return observer.snapshot_outcome()


async def _execute(
    monkeypatch,
    tmp_path,
    *,
    report,
    response,
    events=None,
):
    import api.server as server
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run, get_run
    from api.run_result_service import RunResultUnavailable, resolve_run_result

    db_path = str(tmp_path / "runs.db")
    created = create_run(
        db_path=db_path,
        thread_id="thread-strict",
        query="Research question",
        profile_id="generic-strict-citation",
    )
    service = ResearchExecutionService(
        harness=ScriptedGenericHarness(report),
        project_root=Path(tmp_path),
    )

    async def fake_run_deep_agent(
        query,
        thread_id,
        *,
        run_id,
        segment_id,
        outcome_box,
        profile_id,
        scope,
    ):
        return await service.execute(
            query,
            thread_id,
            run_id=run_id,
            segment_id=segment_id,
            outcome_box=outcome_box,
            profile_id=profile_id,
            scope=scope,
        )

    model = ScriptedCorrectionModel(response, events=events)
    monkeypatch.setattr(server, "run_deep_agent", fake_run_deep_agent)
    monkeypatch.setattr(
        server,
        "strict_citation_chat_model",
        model,
        raising=False,
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_ID,
        lease_seconds=60,
        run_id=created["run_id"],
    )
    assert claim is not None
    checkpoint = server.FinalizationCheckpoint()
    task = server.create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            stage=server._RunStage(),
            termination_origin=server.TerminationOrigin(),
            finalization_checkpoint=checkpoint,
        ),
        task_id=created["run_id"],
        timeout_seconds=5,
        finalization_checkpoint=checkpoint,
    )
    await task
    try:
        resolved = resolve_run_result(
            db_path=db_path,
            run_id=created["run_id"],
        )
    except RunResultUnavailable as exc:
        resolved = exc
    return (
        get_run(db_path=db_path, run_id=created["run_id"]),
        resolved,
        model,
    )


@pytest.mark.asyncio
async def test_strict_initial_success_uses_zero_correction_calls(
    monkeypatch,
    tmp_path,
):
    run, result, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported https://example.com/source.",
        response="unused",
    )

    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert result.artifact["kind"] == "research_report_markdown"
    assert run["review_status"] == "not_required"
    assert run["evidence"][0]["citation_status"] == "cited"
    assert model.call_count == 0


@pytest.mark.asyncio
async def test_strict_correction_success_calls_once_and_persists_exact_url(
    monkeypatch,
    tmp_path,
):
    run, result, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
    )

    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert run["review_status"] == "not_required"
    assert model.call_count == 1
    assert "https://example.com/source" in result.artifact["content"]
    assert run["evidence"][0]["citation_status"] == "cited"
    assert result.artifact["content_hash"] == run["artifacts"][0]["content_hash"]


@pytest.mark.asyncio
async def test_strict_prepares_before_fence_then_invokes_immediately(
    monkeypatch,
    tmp_path,
):
    import api.server as server

    events = []
    original_prepare = server.prepare_strict_citation
    original_fence = server.run_finalization_fence_is_current

    def recording_prepare(**kwargs):
        result = original_prepare(**kwargs)
        assert result.messages
        assert all(message.content for message in result.messages)
        events.append("prepare_complete")
        return result

    def recording_fence(**kwargs):
        assert events == ["prepare_complete"]
        events.append("fence_read")
        return original_fence(**kwargs)

    monkeypatch.setattr(server, "prepare_strict_citation", recording_prepare)
    monkeypatch.setattr(
        server,
        "run_finalization_fence_is_current",
        recording_fence,
    )

    _, _, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        events=events,
    )

    assert events == ["prepare_complete", "fence_read", "model_entered"]
    assert model.call_count == 1


@pytest.mark.asyncio
async def test_false_fence_stops_after_preparation_without_model_call(
    monkeypatch,
    tmp_path,
):
    import api.server as server

    events = []
    original_prepare = server.prepare_strict_citation

    def recording_prepare(**kwargs):
        result = original_prepare(**kwargs)
        assert result.messages
        assert all(message.content for message in result.messages)
        events.append("prepare_complete")
        return result

    def false_fence(**kwargs):
        del kwargs
        events.append("fence_read")
        return False

    monkeypatch.setattr(server, "prepare_strict_citation", recording_prepare)
    monkeypatch.setattr(server, "run_finalization_fence_is_current", false_fence)

    _, _, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        events=events,
    )

    assert events == ["prepare_complete", "fence_read"]
    assert model.call_count == 0
