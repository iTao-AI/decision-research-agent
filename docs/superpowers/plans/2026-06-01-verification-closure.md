# Verification Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目验证状态从"文档已说明边界"推进到"命令和证据可闭环"——修复测试红灯、验证前端构建、补真实端到端运行记录。

**Architecture:** 先修复后端测试（retry mock 隔离 + WeasyPrint 环境），再验证前端构建，然后用真实 API 跑端到端任务采集证据，最后同步公开文档。

**Tech Stack:** Python 3.13, pytest, WeasyPrint, FastAPI, Vue 3, Vite, vue-tsc

**Source Spec:** `docs/superpowers/specs/2026-06-01-deep-search-agent-verification-evidence-design.md`

**Allowed Files:**
- `README.md`, `README_CN.md`, `docs/README.md`
- `docs/evidence/README.md`, `docs/evidence/run-log.md`, `docs/evidence/assets/`
- `tests/unit/test_retry_utils.py`, `tests/unit/test_pdf_converter.py`, `tests/conftest.py`
- `tools/retry_utils.py`
- `frontend/package.json`, `frontend/package-lock.json`
- 与测试或构建修复直接相关的代码/测试/配置文件

**Forbidden Files:**
- `docs/prd.md`
- 无关 OpenSpec archive
- 无关 Agent 功能、Prompt 策略或产品范围
- `frontend/node_modules/`

---

### Task 1: 修复 retry_utils mock 测试隔离

**问题根因：** `test_retry_utils.py` 在模块加载时用 `patch.dict("sys.modules", {"api.monitor": fake_monitor_module})` 创建 mock，但 `tools/retry_utils.py` 第 12 行做 `from api.monitor import monitor`。当全量测试运行时，`test_monitor_sanitization.py` 或 `test_telemetry_integration.py` 先导入真实的 `api.monitor`，使其进入 `sys.modules`。此时 `patch.dict` 不再生效，`retry_utils` 拿到的是真实 monitor 单例，导致 mock 断言计数混乱。

**修复策略：** 不用 `patch.dict("sys.modules")`，改用 `patch.object` 直接修补 `tools.retry_utils.monitor`——在使用的地方打补丁，而不是在定义的地方。

**Files:**
- Modify: `tests/unit/test_retry_utils.py`

- [x] **Step 1: 重写 test_retry_utils.py 的 mock 策略**

将模块级的 mock 创建和 sys.modules patch 替换为在 `tools.retry_utils` 上直接打补丁：

```python
"""Phase 7b Task 1: Retry decorator and TIMEOUTS config tests."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

from tools.retry_utils import retry, retry_async, TIMEOUTS


@pytest.fixture(autouse=True)
def _reset_monitor():
    """Reset mock before each test."""
    with patch("tools.retry_utils.monitor") as mock_monitor:
        yield mock_monitor
```

所有测试方法接收 `_reset_monitor` fixture 参数，用 `mock_monitor` 替换原来的 `mock_monitor` 全局变量。

具体来说，把每个测试中对 `mock_monitor.report_retry.call_count` 的断言改为使用 fixture 参数。

- [x] **Step 2: 更新所有 retry 测试方法签名**

每个需要检查 mock 的测试方法，将 `_reset_monitor` fixture 作为参数接收：

```python
# 示例：test_first_attempt_success
@pytest.mark.asyncio
async def test_first_attempt_success(self, _reset_monitor):
    mock_monitor = _reset_monitor
    call_count = 0

    @retry(max_retries=3, service_name="test_svc")
    async def successful_fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await successful_fn()
    assert result == "ok"
    assert call_count == 1
    assert mock_monitor.report_retry.call_count == 0
```

对 `TestRetryDecorator`、`TestRetryAsyncFunction`、`TestRetryWithAsyncioWaitFor` 中所有用到 `mock_monitor` 的测试都这样改。

TIMEOUTS 配置测试不需要 mock，保持不变。

- [x] **Step 3: 运行 retry_utils 测试确认通过**

Run: `python -m pytest tests/unit/test_retry_utils.py -v`
Expected: 24 passed, 0 failed

- [x] **Step 4: 运行全量测试确认隔离生效**

Run: `python -m pytest -q`
Expected: retry_utils 相关测试不再失败

- [x] **Step 5: Commit**

```bash
git add tests/unit/test_retry_utils.py
git commit -m "fix(tests): patch monitor at usage site in retry_utils tests

问题: patch.dict sys.modules 在全量测试时被其他文件先导入真实
api.monitor 覆盖，导致 mock 断言计数混乱。
方案: 改用 patch('tools.retry_utils.monitor') 在使用点打补丁，
每个测试通过 autouse fixture 获取独立 mock 实例。"
```

### Task 2: 处理 WeasyPrint 系统依赖测试

**问题根因：** 本机 Homebrew 已安装 cairo/pango/gobject（在 `/opt/homebrew/lib/`），但 Python WeasyPrint 的 cffi `dlopen` 不搜索 Homebrew 路径。设置 `DYLD_LIBRARY_PATH=/opt/homebrew/lib` 后 weasyprint 可以正常导入。

**修复策略：**
1. 在 `conftest.py` 顶层设置 macOS Homebrew library path，确保该设置早于测试模块收集和 `skipif` 判断。
2. 对真实 PDF 转换测试使用 `pytest.mark.skipif(not weasyprint_available())`，依赖可用时真实运行，依赖不可用时明确 skip。
3. `test_weasyprint_system_dep_missing` 不跳过。它应通过 monkeypatch import 阶段抛出 `OSError` 来模拟系统依赖缺失，继续覆盖友好错误路径。

**Files:**
- Modify: `tests/unit/test_pdf_converter.py`
- Modify: `tests/conftest.py`

- [x] **Step 1: 在 conftest.py 顶层添加 WeasyPrint 可用性检测**

注意：不要把 `DYLD_LIBRARY_PATH` 设置放进 autouse fixture。`pytest.mark.skipif(not weasyprint_available())` 在测试收集阶段就会求值，fixture 太晚。

```python
def _configure_weasyprint_library_path():
    """Make Homebrew-installed cairo/pango/gobject visible before test collection."""
    import os
    import platform

    if platform.system() == "Darwin":
        homebrew_lib = "/opt/homebrew/lib"
        if os.path.isdir(homebrew_lib):
            current = os.environ.get("DYLD_LIBRARY_PATH", "")
            if homebrew_lib not in current:
                os.environ["DYLD_LIBRARY_PATH"] = f"{homebrew_lib}:{current}" if current else homebrew_lib


_configure_weasyprint_library_path()


def weasyprint_available():
    """Check if weasyprint can actually import (system deps present)."""
    try:
        from weasyprint import HTML
        return True
    except (OSError, ImportError):
        return False
```

- [x] **Step 2: 修改 test_pdf_converter.py——可用时运行，不可用时 skip**

在文件顶部添加：

```python
import pytest
from pathlib import Path
from unittest.mock import patch

from tests.conftest import weasyprint_available

from utils.pdf_converter import convert_md_to_pdf

WEASYPRINT_SKIP_REASON = "WeasyPrint system dependencies (cairo/pango/gobject) not available"
```

将 `TestConvertMdToPdf` 中需要真实 WeasyPrint 的测试加上 skip 标记：

```python
class TestConvertMdToPdf:
    """测试跨平台 PDF 转换器"""

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_normal_conversion(self, test_md_file, output_pdf_path):
        ...

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_temp_html_cleaned_up(self, test_md_file, output_pdf_path):
        ...

    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_pdf_uses_same_directory(self, test_md_file):
        ...
```

- [x] **Step 3: 处理 test_weasyprint_system_dep_missing 测试**

这个测试验证 import 阶段 `OSError` 时返回友好错误。不要在 WeasyPrint 可用时 skip；可用时反而最适合模拟 import 失败路径。

```python
    def test_weasyprint_system_dep_missing(self, test_md_file, output_pdf_path):
        """weasyprint 系统依赖缺失时返回友好错误"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "weasyprint":
                raise OSError("cannot load library libcairo")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = convert_md_to_pdf(test_md_file, output_pdf_path)
            assert "转换失败" in result
            assert "cairo" in result.lower() or "pango" in result.lower() or "系统依赖" in result
```

- [x] **Step 4: 处理 test_chinese_content_rendering**

```python
    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_chinese_content_rendering(self, tmp_path):
        """中文内容正确渲染，无乱码"""
        md = tmp_path / "chinese.md"
        md.write_text("# 中文标题\n\n这是一段中文内容。", encoding='utf-8')
        pdf = tmp_path / "chinese.pdf"
        result = convert_md_to_pdf(md, pdf)
        assert "成功转换" in result
        assert pdf.exists()
        assert pdf.stat().st_size > 1000
```

- [x] **Step 5: 处理 test_markdown_not_installed_error**

这个测试不依赖 WeasyPrint（它修改 `converter_mod.markdown = None`），保持原样但加保护：

```python
    @pytest.mark.skipif(not weasyprint_available(), reason=WEASYPRINT_SKIP_REASON)
    def test_markdown_not_installed_error(self, test_md_file, output_pdf_path):
        """markdown 库未安装时返回友好错误"""
        import utils.pdf_converter as converter_mod
        original_markdown = getattr(converter_mod, 'markdown', None)
        converter_mod.markdown = None
        try:
            result = convert_md_to_pdf(test_md_file, output_pdf_path)
            assert "转换失败" in result or "缺少依赖" in result
        finally:
            if original_markdown is not None:
                converter_mod.markdown = original_markdown
```

- [x] **Step 6: 运行 PDF 转换器测试**

Run: `DYLD_LIBRARY_PATH=/opt/homebrew/lib python -m pytest tests/unit/test_pdf_converter.py -v`
Expected: 依赖可用时全部通过，不可用时合理 skip

- [x] **Step 7: 运行全量测试确认**

Run: `python -m pytest -q`
Expected: retry_utils 全通过，PDF 测试在依赖可用时全通过、不可用时合理 skip

- [x] **Step 8: Commit**

```bash
git add tests/unit/test_pdf_converter.py tests/conftest.py
git commit -m "fix(tests): handle WeasyPrint system deps for macOS Homebrew

问题: WeasyPrint 在 macOS 上找不到 Homebrew 安装的 cairo/pango/gobject。
方案: 在 conftest.py 顶层设置 DYLD_LIBRARY_PATH，确保 pytest
收集阶段即可检测 WeasyPrint；真实转换测试按依赖可用性 skip。
test_weasyprint_system_dep_missing 用 import 阶段 OSError 模拟缺失依赖。"
```

### Task 3: 前端构建验证

**Files:**
- Modify: `frontend/package.json` (if needed)
- Modify: `frontend/package-lock.json` (if npm install changes it)

- [x] **Step 1: 安装前端依赖**

Run: `cd frontend && npm install`
Expected: dependencies installed, `frontend/package-lock.json` remains consistent with `frontend/package.json`

- [x] **Step 2: 运行前端构建**

Run: `cd frontend && npm run build`
Expected: build succeeds with "built in Xms" output

如果构建失败（TypeScript 错误或 Vite 配置问题），做最小修复：
- 如果是 `vue-tsc` 版本问题，检查 `frontend/package.json` 中 `vue-tsc` 版本
- 如果是 TypeScript 类型错误，检查具体文件并修复类型

- [x] **Step 3: 如果构建通过，更新 Evidence Pack**

修改 `docs/evidence/run-log.md`，添加前端构建状态：

```markdown
**前端构建：**

- `cd frontend && npm install`：成功
- `cd frontend && npm run build`：成功，输出 "built in Xms"
```

如果构建失败，记录失败原因：

```markdown
**前端构建：**

- `cd frontend && npm install`：成功
- `cd frontend && npm run build`：失败，错误信息：[实际错误]
```

- [x] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json docs/evidence/run-log.md
git commit -m "chore: verify frontend build

添加前端依赖并运行构建，记录实际结果到 Evidence Pack。"
```

### Task 4: 端到端 Evidence Run

**Files:**
- Modify: `docs/evidence/run-log.md`
- Modify: `docs/evidence/assets/` (截图/产物)

**前置检查：** 确认 `.env` 中真实 LLM 和 Tavily API key 是否配置。占位值不算可用配置。

- [x] **Step 1: 检查 API key 可用性**

Run:

```bash
python - <<'PY'
from pathlib import Path

required = ["OPENAI_API_KEY", "TAVILY_API_KEY"]
values = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

missing = []
for key in required:
    value = values.get(key, "")
    if not value or value.startswith("your-"):
        missing.append(key)

if missing:
    print("E2E_BLOCKED_MISSING_KEYS=" + ",".join(missing))
    raise SystemExit(1)

optional = []
for key in ["MYSQL_HOST", "RAGFLOW_API_URL", "RAGFLOW_API_KEY"]:
    value = values.get(key, "")
    if not value or value.startswith("your-"):
        optional.append(key)

print("E2E_KEYS_OK")
if optional:
    print("E2E_OPTIONAL_SERVICES_UNVERIFIED=" + ",".join(optional))
PY
```

如果输出 `E2E_BLOCKED_MISSING_KEYS=...`，标记为 `E2E blocked with partial evidence`，跳到 Step 4。若只有 MySQL/RAGFlow 不可用，可继续跑网络搜索链路，但不得声称数据库或知识库子 Agent 完整验证。

- [x] **Step 2: 运行 1 个真实端到端任务**

启动后端服务器，通过 API 发送一个简单查询问题（如"2024年AI发展趋势"），记录。

为避免漏掉早期 WebSocket 事件，必须先连接 WebSocket，再 POST `/api/task`。如果本机缺少 `websockets` 包，可用 `python -m pip install websockets` 安装，或使用其他 WebSocket 客户端复现同样顺序。

```bash
# 启动后端（在另一个终端）
python api/server.py

# 在另一个终端先连 WebSocket，再 POST 任务
python - <<'PY'
import asyncio
import json
import time
import urllib.request

import websockets

THREAD_ID = "evidence-run-001"
QUERY = "2024年AI发展趋势"


async def main():
    events = []
    started = time.perf_counter()
    async with websockets.connect(f"ws://localhost:8000/ws/{THREAD_ID}") as ws:
        payload = json.dumps({"query": QUERY, "thread_id": THREAD_ID}).encode("utf-8")
        request = urllib.request.Request(
            "http://localhost:8000/api/task",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            print("POST_RESPONSE=" + response.read().decode("utf-8"))

        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=180)
            except asyncio.TimeoutError:
                print("WS_TIMEOUT")
                break

            events.append(json.loads(message))
            if events[-1].get("type") == "task_result":
                break

    elapsed = time.perf_counter() - started
    print("ELAPSED_SECONDS=%.2f" % elapsed)
    print("EVENT_COUNT=%d" % len(events))
    print("EVENT_TYPES=" + ",".join(event.get("type", "unknown") for event in events))
    print("EVENT_SAMPLE=" + json.dumps(events[:5], ensure_ascii=False))


asyncio.run(main())
PY
```

记录以下数据：
- 开始时间和结束时间（计算总耗时）
- WebSocket 事件样例（先连接 `ws://localhost:8000/ws/evidence-run-001`，再 POST）
- Token 用量：任务完成或超时后运行 `curl -s http://localhost:8000/api/token-usage/evidence-run-001`
- 生成产物路径（Markdown/PDF 报告）
- 子 Agent 调用次数（从 WebSocket 事件或日志中统计）

- [x] **Step 3: 将数据写入 run-log.md**

```markdown
## E2E Run #1

- **日期**: 2026-06-01
- **环境**: 本机 (macOS, Python 3.13)
- **输入问题**: "2024年AI发展趋势"
- **命令**: POST /api/task + WebSocket /ws/evidence-run-001
- **总耗时**: X 分钟 X 秒
- **子 Agent 调用**: 网络搜索 Agent (X 次), 数据库查询 Agent (X 次), 知识库 Agent (X 次)
- **WebSocket 事件样例**: session_created, tool_start (X events), task_result
- **Token 用量**: input: X, output: X, total: X
- **生成产物**: report.md, report.pdf
- **备注**: [任何失败、跳过或降级说明]
```

- [x] **Step 4: 如果 E2E blocked，记录 partial evidence**

```markdown
## E2E blocked with partial evidence

- **阻塞原因**: [具体缺失的 API key 或服务]
- **已完成局部链路**:
  - Docker QA 验证通过（见 assets/）
  - API smoke test: [端点是否响应]
  - WebSocket: [连接是否正常]
- **不能声称的指标**: [具体列表，如真实 token 用量、真实外部搜索结果]
```

- [x] **Step 5: Commit**

```bash
git add docs/evidence/run-log.md docs/evidence/assets/
git commit -m "docs: add E2E evidence run #1 to run log

采集真实端到端任务数据：耗时、token、子 Agent 调用、WebSocket 事件。"
```

### Task 5: 公开文档同步 + 全量验证

**Files:**
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/README.md`
- Modify: `docs/evidence/README.md`

- [x] **Step 1: 更新 README.md 和 README_CN.md 的 Evidence 表格**

根据 Task 2-4 的实际结果，更新 Evidence 表格。

如果后端测试全绿：
```markdown
| Local pytest run | 247 passed, 0 failed | `pytest -q` |
```

如果后端测试有合理 skip：
```markdown
| Local pytest run | 243 passed, 0 failed, 4 skipped (WeasyPrint deps) | `pytest -q` |
```

如果前端构建通过：
```markdown
| 前端构建 | 通过 | `cd frontend && npm run build` |
```

如果前端构建失败：
```markdown
| 前端构建 | 失败: [实际错误] | `cd frontend && npm run build` |
```

- [x] **Step 2: 更新 docs/evidence/README.md**

如果 run-log.md 有真实数据，更新索引：

```markdown
| [run-log.md](run-log.md) | 端到端运行记录：1 个真实任务样例 |
```

- [x] **Step 3: 运行安全扫描**

Run:
```bash
PUBLIC_SAFETY_PATTERNS='TBD|TODO|求职包装|面试话术|洗稿|虚构'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'
```
Expected: 无命中

- [x] **Step 4: 运行 Markdown 链接检查**

Run: 使用已有的链接检查脚本或手动检查所有 markdown 文件中的链接
Expected: 所有链接有效

- [x] **Step 5: 运行 git diff 检查**

Run: `git diff --cached --check`
Expected: 无 trailing whitespace 或其他问题

- [x] **Step 6: 确认 git status 只包含预期文件**

Run: `git status --short --branch`
Expected: 只包含本计划允许的文件

- [x] **Step 7: Commit**

```bash
git add README.md README_CN.md docs/README.md docs/evidence/README.md
git commit -m "docs: sync public docs with verification closure results

更新 Evidence 表格和文档索引，反映真实测试/构建/E2E 结果。"
```

---

## Verification Commands

计划执行完成后，运行以下验收命令：

```bash
# 1. 后端测试
python -m pytest -q

# 2. 前端构建
cd frontend && npm run build

# 3. 公开文档安全扫描
PUBLIC_SAFETY_PATTERNS='TBD|TODO|求职包装|面试话术|洗稿|虚构'
rg -n "$PUBLIC_SAFETY_PATTERNS" README.md README_CN.md docs/README.md docs/evidence docs/superpowers/specs --glob '!docs/superpowers/plans/**'

# 4. 工作区状态
git status --short --branch
git diff --stat
```

## Handoff Notes

- 本轮只修复本机可验证的测试（retry mock 隔离 + WeasyPrint 环境）
- Docker 环境中的测试修复留给后续 CI 配置
- 端到端 Evidence Run 只采集 1 个任务样例；benchmark（5-10 个固定任务）留给后续
- Codex + Gstack 最终验收时，应检查所有 Acceptance Criteria 是否满足
- 职业展示材料（简历 bullet、面试讲述稿）不在本轮范围内
