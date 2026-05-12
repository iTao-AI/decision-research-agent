# Proposal: Phase 0 安全基线修复

## 变更概述

修复项目中的 4 个 P0 级别安全漏洞，建立安全基线。这些漏洞在代码 review 中被独立工程评审发现，属于必须立即修复的生产环境问题。

## 问题描述

当前代码存在以下安全问题：

1. **SQL 注入漏洞**（`tools/mysql_tools.py`）
   - `execute_sql_query` 允许执行任意 SQL 语句（DROP、DELETE、UPDATE 等）
   - `get_table_data` 使用黑名单过滤表名，可被绕过

2. **文件上传路径遍历**（`api/server.py`）
   - 直接使用 `file.filename` 拼接路径，`../../../etc/passwd` 可逃出目标目录

3. **CORS 全开放**（`api/server.py`）
   - `allow_origins=["*"]` 任何源都能调用 API

4. **异步任务错误丢失**（`api/server.py`）
   - `asyncio.create_task` fire-and-forget，异常静默丢失

## 解决方案

### 1. SQL 白名单 + 只读限制

- `execute_sql_query` 添加 SQL 语句类型校验，只允许纯 SELECT（拒绝 SELECT INTO、UNION DELETE 等写入操作）
- 表名校验改为白名单校验，复用 `list_sql_tables()` 已有的 `SHOW TABLES` 查询结果

### 2. 文件上传路径遍历修复

- 使用 `Path(file.filename).name` 提取纯文件名
- 拒绝包含路径分隔符的文件名

### 3. CORS 限制

- 将 `allow_origins` 从 `["*"]` 改为前端实际地址
- 通过环境变量配置前端地址

### 4. 异步任务错误处理

- 保存 task 引用到全局字典
- 添加 `add_done_callback` 记录异常

## 影响评估

### 对现有功能的影响

| 功能 | 影响 | 风险等级 |
|------|------|----------|
| 数据库查询 | `execute_sql_query` 只允许 SELECT，破坏性查询被拒绝 | 中（Agent prompt 原本就只要求查询，但需要验证 prompt 是否足够） |
| 文件上传 | 文件名中的路径分隔符被剥离，文件名可能冲突 | 低（原行为是安全漏洞） |
| WebSocket 实时流 | 无影响 | 无 |
| Agent 委派 | 无影响 | 无 |
| 报告生成 | 无影响 | 无 |

### 回归风险

- SQL 白名单需要确保 `SHOW TABLES` 能正常执行，否则所有数据库查询失败
- CORS 限制需要正确配置前端地址，否则前端无法调用 API

## Out of Scope（不做什么）

以下功能**不在本 Phase 范围内**，将在后续 Phase 处理：

- MySQL 连接池优化（Phase 2）
- 工具函数错误处理统一化（Phase 2）
- Agent 架构升级（Phase 1）
- 跨平台 PDF 替换（Phase 6）
- 测试套件（Phase 5）
- Docker 部署（Phase 6）
- RAGFlow session 泄漏修复（Phase 2）
- WebSocket 重连泄漏（Phase 7）
- Monitor 日志脱敏（Phase 4）

## 技术选型说明

| 决策 | 选择 | 为什么 | 备选 |
|------|------|--------|------|
| SQL 限制方式 | 只允许 SELECT + 表名白名单 | 最安全的方案，彻底杜绝注入 | 黑名单过滤（当前方案，已被绕过） |
| 白名单来源 | 复用 `list_sql_tables()` 的 `SHOW TABLES` | 已有逻辑，不引入新查询 | `information_schema.tables`（额外查询） |
| 文件名校验 | `Path(filename).name` 提取 | Python 标准库，简洁可靠 | 正则过滤（过度设计） |
| CORS 配置 | 环境变量 | 开发/生产环境可切换 | 硬编码前端地址（不灵活） |

## 验收标准

1. `execute_sql_query` 执行 DROP/DELETE/UPDATE 时返回错误信息
2. 上传文件名为 `../../../etc/passwd` 时，文件被保存为 `passwd` 或拒绝
3. 非前端源发起的 CORS 预检请求被拒绝
4. Agent 任务异常后，异常信息可通过 API 或日志查询

---

## Archive Information

**Archived:** 2026-05-09
**Duration:** 1 day
**Outcome:** Successfully implemented

### Files Modified
- `tools/mysql_tools.py` — SQL 类型校验 + 表名白名单
- `api/server.py` — CORS 限制 + 文件上传安全 + 任务跟踪
- `api/upload_security.py` — 文件名净化（新）
- `api/cors_config.py` — CORS 源配置（新）
- `api/task_tracker.py` — 异步任务跟踪（新）
- `api/context.py` — Unicode 引号修复
- `tests/unit/test_mysql_security.py` — SQL 安全测试（新）
- `tests/unit/test_upload_security.py` — 文件上传安全测试（新）
- `tests/unit/test_cors_config.py` — CORS 配置测试（新）
- `tests/unit/test_task_tracker.py` — 异步任务跟踪测试（新）
- `tests/unit/test_regression.py` — 回归测试（新）
- `.env.example` — 添加 FRONTEND_ORIGIN

### Specs Created
- `openspec/specs/database-security.md`
- `openspec/specs/upload-security.md`
- `openspec/specs/api-security.md`
