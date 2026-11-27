"""Opt-in, single-operator loopback browser entry point for Fieldwork."""

import argparse
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from fieldwork.analysis import DeepSeekAnalysis, ReplayAnalysis
from fieldwork.mke import MkeEvidence
from fieldwork.replay import FrozenEvidence
from fieldwork.service import FieldworkError, FieldworkService

_BASE = "/api/fieldwork/projects/northstar"
_MAX_PDF = 8 * 1024 * 1024
_MAX_JSON = 16 * 1024
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,220}")
_EXPORT_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"


def _local_target(value: str):
    try:
        parts = urlsplit(value)
        if parts.hostname in _LOOPBACK and parts.username is None and parts.password is None:
            return parts.scheme, parts.hostname, parts.port
    except ValueError:
        pass
    return None


def _fail(code: str, message: str, status: int):
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status)


async def _bounded_body(request: Request, limit: int) -> bytes:
    claimed = request.headers.get("content-length")
    if claimed is not None and (not claimed.isascii() or not claimed.isdecimal() or len(claimed) > 20):
        raise FieldworkError("invalid_length", "无法读取提交内容。", 400)
    if claimed and int(claimed) > limit:
        raise FieldworkError("body_too_large", "提交内容超过允许大小。", 413)
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise FieldworkError("body_too_large", "提交内容超过允许大小。", 413)
        content.extend(chunk)
    return bytes(content)


def _has_media(request: Request, media: str) -> bool:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower() == media


async def _json(request: Request, allowed: set[str]) -> dict:
    if not _has_media(request, "application/json"):
        raise FieldworkError("unsupported_media", "需要 JSON 请求。", 415)
    try:
        payload = json.loads(await _bounded_body(request, _MAX_JSON))
    except (UnicodeError, ValueError):
        raise FieldworkError("invalid_request", "请求内容格式有误。", 400) from None
    if not isinstance(payload, dict) or not set(payload) <= allowed:
        raise FieldworkError("invalid_request", "请求字段有误。", 400)
    return payload


def _identifier(value):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise FieldworkError("invalid_id", "无法识别这条记录。", 400)
    return value


def _markdown(snapshot: dict) -> str:
    def literal(text):
        return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", escape(text)).replace("\n", " ")

    lines = [f"# {literal(snapshot['headline'])}", "", f"已确认版本 V{snapshot['version']}", "",
             literal(snapshot["summary"]), "", "## 事项", ""]
    refs = {row["id"]: index for index, row in enumerate(snapshot["evidence"], start=1)}
    for item in snapshot["items"]:
        ids = "、".join(f"E{refs[identity]:02d}" for identity in item["evidence_ids"])
        lines.extend([f"- {literal(item['action'])}（{literal(item['owner'])}，{ids}）",
                      f"  - {literal(item['reason'])}"])
        if item["question"]:
            lines.append(f"  - 待确认：{literal(item['question'])}")
    lines.extend(["", "## 冻结依据", ""])
    used = {identity for item in snapshot["items"] for identity in item["evidence_ids"]}
    for row in snapshot["evidence"]:
        if row["id"] in used:
            lines.extend([
                f"- E{refs[row['id']]:02d} · {literal(row['title'])} · 第 {row['page_start']} 页",
                f"  - {literal(row['text'])}",
            ])
    return "\n".join(lines) + "\n"


def create_app(root: Path, *, mode="replay", mke=None, model=None, dist=None, service=None):
    if service is None:
        if mode == "replay":
            frozen = FrozenEvidence.load()

            def factory(_project_dir):
                return frozen
        elif mode in {"mke-replay", "live"} and mke is not None:
            def factory(project_dir):
                return MkeEvidence(mke, project_dir)
        else:
            raise ValueError("Fieldwork requires a configured MKE executable")
        if mode == "live" and model is None:
            raise ValueError("Fieldwork live requires a configured model")
        service = FieldworkService(Path(root), factory, model or ReplayAnalysis(), mode)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_only(request, call_next):
        target = _local_target(f"{request.url.scheme}://{request.headers.get('host', '')}")
        if target is None:
            return _fail("not_local", "此工作台仅允许本机操作。", 403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and (
            (origin is not None and _local_target(origin) != target)
            or request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
        ):
            return _fail("origin_denied", "请在本机工作台提交。", 403)
        result = await call_next(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(_BASE):
            result.headers["Cache-Control"] = "no-store"
        return result

    @app.exception_handler(FieldworkError)
    async def fieldwork_error(_request, error):
        return _fail(error.code, error.message, error.status)

    @app.get(_BASE)
    def project():
        return service.project()

    @app.post(_BASE + "/materials")
    async def materials(request: Request, title: str = "", replace: str | None = None):
        if not _has_media(request, "application/pdf"):
            raise FieldworkError("unsupported_media", "请选择文本层 PDF。", 415)
        content = await _bounded_body(request, _MAX_PDF)
        return await run_in_threadpool(service.submit_material, title, content,
                                       _identifier(replace) if replace is not None else None)

    @app.post(_BASE + "/analysis")
    async def analysis(request: Request):
        data = await _json(request, {"material_id"})
        return await run_in_threadpool(service.analyze, _identifier(data.get("material_id")))

    @app.post(_BASE + "/review")
    async def review(request: Request):
        data = await _json(request, {"proposal_id", "decision", "feedback"})
        decision, feedback = data.get("decision"), data.get("feedback", "")
        if decision not in ("accept", "return") or not isinstance(feedback, str):
            raise FieldworkError("invalid_request", "请选择采纳或填写退回意见。", 400)
        return await run_in_threadpool(service.review, _identifier(data.get("proposal_id")), decision, feedback)

    @app.post(_BASE + "/progress")
    async def progress(request: Request):
        data = await _json(request, {"sample_prepared"})
        if data.get("sample_prepared") is not True:
            raise FieldworkError("invalid_request", "只能记录已完成的样本准备。", 400)
        return await run_in_threadpool(service.progress, True)

    @app.get(_BASE + "/history")
    def history():
        return service.history()

    @app.get(_BASE + "/proposals/{proposal_id}")
    def proposal(proposal_id: str):
        return service.proposal(_identifier(proposal_id))

    @app.get(_BASE + "/proposals/{proposal_id}/evidence/{evidence_id}/live")
    def evidence(proposal_id: str, evidence_id: str):
        return service.live_evidence(_identifier(proposal_id), _identifier(evidence_id))

    @app.get(_BASE + "/exports/{version}.{format}")
    def export(version: int, format: str, download: bool = False):
        headers = {}
        if format == "html":
            headers.update({"Content-Security-Policy": _EXPORT_CSP, "Referrer-Policy": "no-referrer"})
            body, media = service.html(version), "text/html"
        elif format == "json":
            body = json.dumps(service.export(version), ensure_ascii=False, indent=2).encode() + b"\n"
            media = "application/json"
        elif format == "md":
            body, media = _markdown(service.export(version)), "text/markdown"
        else:
            raise FieldworkError("unknown_format", "没有此格式的交付物。", 404)
        if format != "html" or download:
            headers["Content-Disposition"] = f'attachment; filename="fieldwork-v{version}.{format}"'
        return Response(body, media_type=media, headers=headers)

    if dist is not None:
        dist = Path(dist).resolve()
        if not (dist / "index.html").is_file():
            raise ValueError("Build the frontend before serving Fieldwork")

        @app.get("/fieldwork", include_in_schema=False)
        @app.get("/fieldwork/", include_in_schema=False)
        def workbench():
            return FileResponse(dist / "index.html")

        app.mount("/", StaticFiles(directory=dist, html=True))

    return app


def _deepseek_key(settings):
    deepseek_base = (settings.get("DEEPSEEK_API_BASE") or "").rstrip("/")
    openai_base = (settings.get("OPENAI_BASE_URL") or "").rstrip("/")
    official = {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
    if deepseek_base and deepseek_base not in official:
        raise ValueError("model_configuration_invalid")
    key = settings.get("DEEPSEEK_API_KEY")
    if not key and (deepseek_base in official or openai_base in official):
        if not openai_base or openai_base in official:
            key = settings.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("model_configuration_invalid")
    return key


def main():
    import uvicorn
    from dotenv import dotenv_values

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Local state directory")
    parser.add_argument("--mode", choices=("replay", "mke-replay", "live"), default="replay")
    parser.add_argument("--mke", type=Path)
    parser.add_argument("--dist", type=Path, default=Path("frontend/dist"))
    parser.add_argument("--port", type=int, default=7195)
    parser.add_argument("--max-model-calls", type=int, default=1)
    parser.add_argument("--env-file", type=Path, help="Operator-managed provider configuration for live mode")
    parser.add_argument("--register-html", nargs=2, metavar=("VERSION", "FILE"))
    args = parser.parse_args()
    if args.register_html:
        version, file = args.register_html
        try:
            service = FieldworkService(args.root, lambda _: None, ReplayAnalysis(), args.mode)
            path = Path(file)
            with path.open("rb") as source:
                content = source.read(256 * 1024 + 1)
            receipt = service.register_html(int(version), content)
        except (FieldworkError, OSError, ValueError) as error:
            parser.exit(1, f"Registration failed ({getattr(error, 'code', 'invalid_artifact')}).\n")
        print(json.dumps(receipt, ensure_ascii=False))
        return
    model = None
    if args.mode == "live":
        config = dotenv_values(args.env_file, interpolate=False) if args.env_file else {}
        settings = {
            name: os.environ.get(name) or config.get(name)
            for name in ("DEEPSEEK_API_BASE", "DEEPSEEK_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_KEY")
        }
        try:
            model = DeepSeekAnalysis(_deepseek_key(settings), max_calls=args.max_model_calls)
        except ValueError:
            parser.exit(1, "Fieldwork live needs an official DeepSeek configuration and a valid request limit.\n")
    app = create_app(args.root, mode=args.mode, mke=args.mke, model=model, dist=args.dist)
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
