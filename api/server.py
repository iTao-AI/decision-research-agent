import sys
import os
import uuid
import asyncio
import logging
import json
import uvicorn
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, field_validator
from typing import List
import shutil

# Load env once at startup — tools read from os.environ
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from agent.main_agent import run_deep_agent
from agent.run_result import AgentRunResult
from agent.telemetry import collector, TelemetryRecord
from api.monitor import monitor, manager
from api.upload_security import sanitize_filename, validate_filename
from api.cors_config import get_allowed_origins
from api.task_tracker import create_tracked_task
from api.persistence import (
    get_research_run_with_evidence,
    get_task,
    list_research_runs,
    save_research_run,
    save_task,
    update_task,
)
from api.task_finalizer import finalize_task_run, TaskFinalization
from api.thread_ids import safe_session_dir, validate_thread_id


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that checks X-API-Key header against API_SECRET in .env.

    When API_SECRET is not set, logs a warning and accepts all requests
    (backwards-compatible with development environments).
    """

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for docs and health endpoints
        if request.url.path in ("/docs", "/openapi.json", "/redoc", "/health"):
            return await call_next(request)

        api_secret = os.environ.get("API_SECRET", "")
        if not api_secret:
            logging.warning(
                "API_SECRET is not set — all requests are accepted without authentication. "
                "Set API_SECRET=your-key in .env to enable API key protection."
            )
            return await call_next(request)

        client_key = request.headers.get("X-API-Key", "")
        if client_key != api_secret:
            return JSONResponse(
                status_code=401,
                content={"detail": "请设置 API_SECRET（在 .env 中）并通过请求头 X-API-Key 传递正确的密钥"},
            )

        return await call_next(request)


app = FastAPI(title="DeepAgents API")

output_dir = project_root / "output"
output_dir.mkdir(exist_ok=True)

updated_dir = project_root / "updated"
updated_dir.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(APIKeyMiddleware)


@app.get("/health")
async def health():
    """Lightweight service health endpoint for agent-tool integrations."""
    return {"status": "ok", "service": "deep-search-agent"}


class TaskRequest(BaseModel):
    query: str
    thread_id: str = None

    @field_validator("thread_id")
    @classmethod
    def validate_optional_thread_id(cls, value):
        return validate_thread_id(value) if value is not None else value


def _validated_thread_id(thread_id: str) -> str:
    try:
        return validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _mark_task_timeout(thread_id: str, timeout_seconds: int) -> None:
    error_message = f"Agent task timed out after {timeout_seconds}s"
    task = await asyncio.to_thread(get_task, thread_id=thread_id)
    query = task["query"] if task and task.get("query") else ""
    completed_at = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(
        save_research_run,
        thread_id=thread_id,
        query=query,
        status="failed",
        completed_at=completed_at,
        output_path=None,
        fallback_used=False,
        diagnostics_json=json.dumps([f"timeout:{timeout_seconds}s"], ensure_ascii=False),
        token_usage_json="{}",
        quality_report_json=json.dumps(
            {
                "status": "failed",
                "issues": [
                    {
                        "code": "task_timeout",
                        "severity": "error",
                        "message": error_message,
                    }
                ],
                "metrics": {"timeout_seconds": timeout_seconds},
            },
            ensure_ascii=False,
        ),
    )
    await asyncio.to_thread(
        update_task,
        thread_id=thread_id,
        status="failed",
        error_message=error_message,
    )
    monitor.report_task_finalized(
        thread_id=thread_id,
        status="failed",
        fallback_used=False,
        output_path=None,
        error_message=error_message,
    )
    monitor._emit("error", error_message)


async def _run_task_with_persistence(query: str, thread_id: str) -> TaskFinalization:
    try:
        await asyncio.to_thread(update_task, thread_id=thread_id, status="running")
        result = await run_deep_agent(query, thread_id)
        if not isinstance(result, AgentRunResult):
            raise RuntimeError(
                f"run_deep_agent returned unsupported result type: {type(result).__name__}"
            )
        return await asyncio.to_thread(finalize_task_run, result)
    except Exception as e:
        await asyncio.to_thread(
            update_task,
            thread_id=thread_id,
            status="failed",
            error_message=str(e),
        )
        await asyncio.to_thread(
            save_research_run,
            thread_id=thread_id,
            query=query,
            status="failed",
            completed_at=None,
            output_path=None,
            fallback_used=False,
            diagnostics_json=json.dumps([f"error:{str(e)}"], ensure_ascii=False),
            token_usage_json="{}",
            quality_report_json=json.dumps(
                {
                    "status": "failed",
                    "issues": [
                        {
                            "code": "agent_error",
                            "severity": "error",
                            "message": "Agent execution failed.",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
        monitor.report_task_finalized(
            thread_id=thread_id,
            status="failed",
            fallback_used=False,
            output_path=None,
            error_message=str(e),
        )
        raise


@app.post("/api/task")
async def run_task(request: TaskRequest):
    """Start an agent task asynchronously."""
    thread_id = request.thread_id or str(uuid.uuid4())

    # Persist task and update status as it progresses
    await asyncio.to_thread(save_task, thread_id=thread_id, query=request.query, status="pending")

    create_tracked_task(
        _run_task_with_persistence(request.query, thread_id),
        thread_id,
        on_timeout=_mark_task_timeout,
    )
    return {"status": "started", "thread_id": thread_id}


@app.get("/api/tasks/{thread_id}")
async def get_task_status(thread_id: str):
    """Get task status and metadata from persistence."""
    thread_id = _validated_thread_id(thread_id)
    task = await asyncio.to_thread(get_task, thread_id=thread_id)
    if task is None:
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})
    return task


@app.get("/api/research/runs")
async def get_research_runs(limit: int = 50):
    """List recent auditable research runs."""
    runs = await asyncio.to_thread(list_research_runs, limit=limit)
    return {"runs": runs}


@app.get("/api/research/runs/{thread_id}")
async def get_research_run(thread_id: str):
    """Get one ResearchRun with its EvidenceLedger entries."""
    thread_id = _validated_thread_id(thread_id)
    run = await asyncio.to_thread(get_research_run_with_evidence, thread_id=thread_id)
    if run is None:
        return JSONResponse(status_code=404, content={"detail": "ResearchRun 不存在"})
    return run


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    """Upload files for a session."""
    thread_id = _validated_thread_id(thread_id)
    target_dir = safe_session_dir(updated_dir, thread_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        # 文件名校验
        original_name = file.filename or ""
        error = validate_filename(original_name)
        if error:
            return JSONResponse(status_code=400, content={"error": error})

        # 文件名净化
        safe_name = sanitize_filename(original_name)
        if not safe_name or safe_name in (".", ".."):
            return JSONResponse(status_code=400, content={"error": "无效的文件名"})

        file_path = target_dir / safe_name
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(safe_name)

    return {"status": "uploaded", "files": saved_files}


@app.get("/api/download")
async def download_file(path: str):
    """Download a file from the output directory."""
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()

        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能下载输出目录下的文件"}
    except Exception:
        return {"error": "无效的路径参数"}

    if not abs_path.exists():
        return {"error": "文件不存在"}

    return FileResponse(abs_path, filename=abs_path.name)


@app.get("/api/files")
async def list_files(path: str):
    """List files in a directory under output."""
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()

        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能访问输出目录下的文件"}

    except Exception as e:
        return {"error": f"路径无效: {e}"}

    if not abs_path.exists():
        return {"error": "目录不存在"}

    files = []
    try:
        for file_path in abs_path.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "type": "file",
                    "path": str(file_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime
                })
    except Exception as e:
        return {"error": str(e)}

    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return {"files": files}


@app.get("/api/telemetry/{thread_id}")
async def get_telemetry(thread_id: str):
    """Get telemetry records for a thread."""
    thread_id = _validated_thread_id(thread_id)
    records = collector.get_by_thread(thread_id)
    return [
        {
            "thread_id": r.thread_id,
            "agent_name": r.agent_name,
            "tool_name": r.tool_name,
            "duration_ms": r.duration_ms,
            "status": r.status,
            "error": r.error,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in records
    ]


@app.get("/api/token-usage/{thread_id}")
async def get_token_usage(thread_id: str):
    """Get token usage summary for a thread."""
    thread_id = _validated_thread_id(thread_id)
    from agent.token_tracking import token_collector
    summary = token_collector.get_summary(thread_id)
    return summary


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """WebSocket endpoint for real-time communication."""
    try:
        thread_id = validate_thread_id(thread_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid thread_id")
        return

    # Auth check for WebSocket connections
    api_secret = os.environ.get("API_SECRET", "")
    if api_secret:
        client_key = websocket.headers.get("x-api-key", "") or websocket.query_params.get("api_key", "")
        if client_key != api_secret:
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await manager.connect(websocket, thread_id)

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({
                "type": "pong",
                "message": f"服务端已收到: {data}"
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception as e:
        manager.disconnect(websocket, thread_id)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
