import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from api.research_execution_service import ResearchExecutionService
from api.run_result_service import RunResultUnavailable


WORKER_ID = "dispatch_worker_22222222222222222222222222222222"


class ScriptedCorrectionModel:
    def __init__(self, content, *, events=None, error=None):
        self.content = content
        self.call_count = 0
        self.events = events
        self.error = error

    async def ainvoke(self, messages, config=None):
        del messages, config
        self.call_count += 1
        if self.events is not None:
            self.events.append("model_entered")
        if self.error is not None:
            raise RuntimeError(self.error)
        return AIMessage(content=self.content)


class BlockingCorrectionModel:
    def __init__(self):
        self.call_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def ainvoke(self, messages, config=None):
        del messages, config
        self.call_count += 1
        self.entered.set()
        await self.release.wait()
        return AIMessage(
            content='{"placements":[{"target_id":"t001","source_id":"s001"}]}'
        )


class ScriptedGenericHarness:
    def __init__(self, report, *, source_url="https://example.com/source"):
        self.report = report
        self.source_url = source_url

    async def execute(self, request, *, runtime_context, observer):
        del request, runtime_context
        if self.source_url is not None:
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
                                                "url": self.source_url,
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
        if self.report is not None:
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
    source_url="https://example.com/source",
    model_error=None,
    capture_error=False,
    profile_id="generic-strict-citation",
    correction_model=None,
    timeout_seconds=5,
    cancel_after_model_entry=False,
    stale_during_model=False,
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
        profile_id=profile_id,
    )
    service = ResearchExecutionService(
        harness=ScriptedGenericHarness(report, source_url=source_url),
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

    model = correction_model or ScriptedCorrectionModel(
        response,
        events=events,
        error=model_error,
    )
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
    termination_origin = server.TerminationOrigin()
    task = server.create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            stage=server._RunStage(),
            termination_origin=termination_origin,
            finalization_checkpoint=checkpoint,
        ),
        task_id=created["run_id"],
        timeout_seconds=timeout_seconds,
        termination_origin=termination_origin,
        finalization_checkpoint=checkpoint,
    )
    if cancel_after_model_entry:
        await model.entered.wait()
        task.cancel()
    if stale_during_model:
        from api.run_repository import finalize_run_transaction

        await model.entered.wait()
        assert finalize_run_transaction(
            db_path=db_path,
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            expected_state_version=1,
            allowed_previous_statuses={"running"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
        )
        model.release.set()
    task_error = None
    try:
        await task
    except BaseException as exc:
        task_error = exc
        if not capture_error:
            raise
    await asyncio.sleep(0)
    try:
        resolved = resolve_run_result(
            db_path=db_path,
            run_id=created["run_id"],
        )
    except RunResultUnavailable as exc:
        resolved = exc
    result = (
        get_run(db_path=db_path, run_id=created["run_id"]),
        resolved,
        model,
    )
    if capture_error:
        return (*result, task_error)
    return result


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
    from api.run_repository import finalize_run_transaction

    events = []
    original_prepare = server.prepare_strict_citation

    def recording_prepare(**kwargs):
        result = original_prepare(**kwargs)
        assert result.messages
        assert all(message.content for message in result.messages)
        events.append("prepare_complete")
        return result

    def false_fence(**kwargs):
        events.append("fence_read")
        assert finalize_run_transaction(
            db_path=kwargs["db_path"],
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            expected_state_version=kwargs["expected_state_version"],
            allowed_previous_statuses={"running"},
            execution_status="completed",
            delivery_status="ready",
            evidence_entries=[],
        )
        return original_fence(**kwargs)

    original_fence = server.run_finalization_fence_is_current
    monkeypatch.setattr(server, "prepare_strict_citation", recording_prepare)
    monkeypatch.setattr(server, "run_finalization_fence_is_current", false_fence)

    run, _, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        events=events,
    )

    assert events == ["prepare_complete", "fence_read"]
    assert model.call_count == 0
    assert run["execution_status"] == "completed"
    assert run["delivery_status"] == "ready"
    assert run["evidence"] == []
    assert run["artifacts"] == []


def _assert_strict_failure(run, result, error, *, evidence_count):
    assert run["execution_status"] == "failed"
    assert run["review_status"] == "not_required"
    assert run["delivery_status"] == "failed"
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "run_finalization_failed"
    assert len(run["evidence"]) == evidence_count
    assert run["artifacts"] == []
    assert isinstance(result, RunResultUnavailable)
    assert result.code == "run_failed"
    assert error is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("report", "response", "source_url", "model_error", "code", "calls", "evidence_count"),
    [
        (
            "Supported finding.",
            "malformed",
            "https://example.com/source",
            None,
            "strict_citation_response_invalid",
            1,
            1,
        ),
        (
            "Supported finding.",
            '{"placements":[{"target_id":"t001","source_id":"unknown"}]}',
            "https://example.com/source",
            None,
            "strict_citation_response_invalid",
            1,
            1,
        ),
        (
            "Supported finding.",
            "unused",
            None,
            None,
            "strict_citation_source_unavailable",
            0,
            0,
        ),
        (
            None,
            "unused",
            "https://example.com/source",
            None,
            "strict_citation_initial_artifact_invalid",
            0,
            1,
        ),
        (
            "```\nunsafe-only\n```",
            "unused",
            "https://example.com/source",
            None,
            "strict_citation_target_unavailable",
            0,
            1,
        ),
        (
            "Supported finding.",
            "unused",
            "https://example.com/source",
            "provider-secret-detail",
            "strict_citation_model_failed",
            1,
            1,
        ),
    ],
)
async def test_strict_failures_are_closed_and_retain_only_safe_state(
    monkeypatch,
    tmp_path,
    caplog,
    report,
    response,
    source_url,
    model_error,
    code,
    calls,
    evidence_count,
):
    run, result, model, error = await _execute(
        monkeypatch,
        tmp_path,
        report=report,
        response=response,
        source_url=source_url,
        model_error=model_error,
        capture_error=True,
    )

    _assert_strict_failure(
        run,
        result,
        error,
        evidence_count=evidence_count,
    )
    assert model.call_count == calls
    assert str(error) == code
    assert code in caplog.text
    for forbidden in (
        "provider-secret-detail",
        "Source context",
        "https://example.com/source",
        "Supported finding.",
    ):
        assert forbidden not in str(error)
        assert forbidden not in caplog.text


@pytest.mark.asyncio
async def test_post_insertion_zero_citation_fails_once_without_retry(
    monkeypatch,
    tmp_path,
):
    import api.strict_citation_finalization as finalizer

    actual_mark = finalizer.mark_cited_evidence
    calls = 0

    def force_post_insertion_uncited(entries, artifact_content):
        nonlocal calls
        calls += 1
        if calls == 1:
            return actual_mark(entries, artifact_content)
        return list(entries)

    monkeypatch.setattr(
        finalizer,
        "mark_cited_evidence",
        force_post_insertion_uncited,
    )

    run, result, model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        capture_error=True,
    )

    _assert_strict_failure(run, result, error, evidence_count=1)
    assert str(error) == "strict_citation_invariant_failed"
    assert model.call_count == 1
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("seam", "code", "expected_calls"),
    [
        ("prepare", "strict_citation_packet_invalid", 0),
    ],
)
async def test_closed_internal_failure_codes_reach_only_tracker_log(
    monkeypatch,
    tmp_path,
    caplog,
    seam,
    code,
    expected_calls,
):
    import api.server as server
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
    )

    if seam == "prepare":
        def fail_prepare(**kwargs):
            del kwargs
            raise StrictCitationFinalizationError(code)

        monkeypatch.setattr(server, "prepare_strict_citation", fail_prepare)
    else:
        async def fail_invoke(**kwargs):
            del kwargs
            raise StrictCitationFinalizationError(code)

        monkeypatch.setattr(
            server,
            "invoke_prepared_strict_citation",
            fail_invoke,
        )

    run, result, model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        capture_error=True,
    )

    _assert_strict_failure(run, result, error, evidence_count=1)
    assert str(error) == code
    assert model.call_count == expected_calls
    assert code in caplog.text
    assert "https://example.com/source" not in caplog.text


@pytest.mark.asyncio
async def test_stale_target_after_model_call_fails_closed_once(
    monkeypatch,
    tmp_path,
    caplog,
):
    from dataclasses import replace

    import api.server as server

    actual_invoke = server.invoke_prepared_strict_citation

    async def invoke_with_stale_target(*, prepared, chat_model):
        stale_target = replace(
            prepared.targets[0],
            basis_sha256="0" * 64,
        )
        return await actual_invoke(
            prepared=replace(
                prepared,
                targets=(stale_target, *prepared.targets[1:]),
            ),
            chat_model=chat_model,
        )

    monkeypatch.setattr(
        server,
        "invoke_prepared_strict_citation",
        invoke_with_stale_target,
    )
    run, result, model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        capture_error=True,
    )

    _assert_strict_failure(run, result, error, evidence_count=1)
    assert str(error) == "strict_citation_target_stale"
    assert model.call_count == 1
    assert "strict_citation_target_stale" in caplog.text


@pytest.mark.asyncio
async def test_invalid_rebuilt_artifact_after_model_call_fails_closed_once(
    monkeypatch,
    tmp_path,
    caplog,
):
    import api.strict_citation_finalization as finalizer

    actual_build = finalizer.build_generic_result_artifact
    build_calls = 0

    def invalidate_rebuilt_artifact(outcome):
        nonlocal build_calls
        build_calls += 1
        artifact = actual_build(outcome)
        if build_calls == 3:
            return {
                **artifact,
                "kind": "research_report_fallback_markdown",
            }
        return artifact

    monkeypatch.setattr(
        finalizer,
        "build_generic_result_artifact",
        invalidate_rebuilt_artifact,
    )
    run, result, model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response='{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        capture_error=True,
    )

    _assert_strict_failure(run, result, error, evidence_count=1)
    assert str(error) == "strict_citation_artifact_invalid"
    assert model.call_count == 1
    assert build_calls == 3
    assert "strict_citation_artifact_invalid" in caplog.text


@pytest.mark.asyncio
async def test_timeout_during_correction_uses_existing_finalization_cause(
    monkeypatch,
    tmp_path,
):
    model = BlockingCorrectionModel()
    run, result, returned_model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response="unused",
        correction_model=model,
        timeout_seconds=1,
        capture_error=True,
    )

    assert returned_model is model
    assert model.entered.is_set()
    assert model.call_count == 1
    assert error is None
    assert run["execution_status"] == "failed"
    assert run["review_status"] == "not_required"
    assert run["delivery_status"] == "failed"
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "run_timeout"
    assert len(run["evidence"]) == 1
    assert run["artifacts"] == []
    assert isinstance(result, RunResultUnavailable)
    assert result.code == "run_failed"


@pytest.mark.asyncio
async def test_cancellation_during_correction_uses_existing_finalization_cause(
    monkeypatch,
    tmp_path,
):
    model = BlockingCorrectionModel()
    run, result, returned_model, error = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response="unused",
        correction_model=model,
        cancel_after_model_entry=True,
        capture_error=True,
    )

    assert returned_model is model
    assert model.call_count == 1
    assert isinstance(error, asyncio.CancelledError)
    assert run["execution_status"] == "failed"
    assert run["review_status"] == "not_required"
    assert run["delivery_status"] == "failed"
    assert run["failure_cause"]["phase"] == "finalization"
    assert run["failure_cause"]["code"] == "cancelled"
    assert len(run["evidence"]) == 1
    assert run["artifacts"] == []
    assert isinstance(result, RunResultUnavailable)
    assert result.code == "run_failed"


@pytest.mark.asyncio
async def test_writer_made_stale_in_flight_cannot_overwrite_winner(
    monkeypatch,
    tmp_path,
):
    model = BlockingCorrectionModel()
    run, result, returned_model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding.",
        response="unused",
        correction_model=model,
        stale_during_model=True,
    )

    assert returned_model is model
    assert model.call_count == 1
    assert run["execution_status"] == "completed"
    assert run["review_status"] == "not_required"
    assert run["delivery_status"] == "ready"
    assert run["evidence"] == []
    assert run["artifacts"] == []
    assert isinstance(result, RunResultUnavailable)
    assert result.code == "run_result_unavailable"


@pytest.mark.asyncio
async def test_strict_profile_uses_existing_identity_and_manifest_surfaces(
    tmp_path,
):
    import api.server as server
    from api.run_repository import (
        RunCreationConflict,
        create_or_replay_run,
        get_run,
    )

    db_path = str(tmp_path / "runs.db")
    first = create_or_replay_run(
        db_path=db_path,
        idempotency_key="strict-idempotency-key-0001",
        thread_id="thread-strict",
        query="Research question",
        profile_id="generic-strict-citation",
        profile_version="1",
    )
    replay = create_or_replay_run(
        db_path=db_path,
        idempotency_key="strict-idempotency-key-0001",
        thread_id="thread-strict",
        query="Research question",
        profile_id="generic-strict-citation",
        profile_version="1",
    )

    assert replay.run_id == first.run_id
    assert replay.idempotent_replay is True
    persisted = get_run(db_path=db_path, run_id=first.run_id)
    assert persisted["profile_id"] == "generic-strict-citation"
    assert persisted["profile_version"] == "1"
    with pytest.raises(RunCreationConflict, match="run_idempotency_conflict"):
        create_or_replay_run(
            db_path=db_path,
            idempotency_key="strict-idempotency-key-0001",
            thread_id="thread-strict",
            query="Research question",
            profile_id="generic",
            profile_version="1",
        )

    manifest = await server.get_profile_manifest("generic-strict-citation")
    assert manifest["profile"]["profile_id"] == "generic-strict-citation"
    assert manifest["profile"]["version"] == "1"
    assert set(server.RunRequest.model_fields) == {
        "query",
        "thread_id",
        "profile_id",
        "scope",
    }
    with pytest.raises(KeyError, match="unknown profile"):
        server.profile_registry.get("unknown-profile")


@pytest.mark.asyncio
async def test_strict_resolver_rejects_nonexact_persisted_profile_version(
    monkeypatch,
    tmp_path,
):
    import sqlite3

    from api.run_result_service import resolve_run_result

    run, _, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported https://example.com/source.",
        response="unused",
    )
    assert model.call_count == 0

    db_path = str(tmp_path / "runs.db")
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            UPDATE research_runs_v2
            SET profile_version = ?
            WHERE run_id = ?
            """,
            ("unexpected", run["run_id"]),
        )

    with pytest.raises(RunResultUnavailable) as exc_info:
        resolve_run_result(db_path=db_path, run_id=run["run_id"])
    assert exc_info.value.code == "run_result_unavailable"


@pytest.mark.asyncio
async def test_literal_generic_zero_citation_remains_ready_without_correction(
    monkeypatch,
    tmp_path,
):
    run, result, model = await _execute(
        monkeypatch,
        tmp_path,
        report="Supported finding without an exact URL.",
        response="unused",
        profile_id="generic",
    )

    assert run["execution_status"] == "completed"
    assert run["review_status"] == "not_required"
    assert run["delivery_status"] == "ready"
    assert run["evidence"][0]["citation_status"] == "uncited"
    assert result.artifact["kind"] == "research_report_markdown"
    assert model.call_count == 0
