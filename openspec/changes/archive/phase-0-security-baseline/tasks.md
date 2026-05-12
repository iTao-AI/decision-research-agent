# Tasks: Phase 0 安全基线修复

## Phase A: SQL 安全修复（~25 分钟）

### Task A.1: 添加 SQL 语句类型校验
- **文件**: `tools/mysql_tools.py`
- **内容**: 在 `execute_sql_query` 中添加 SQL 解析，只允许纯 SELECT 语句（拒绝 SELECT INTO、UNION DELETE 等写入操作）
- **验收**: `DROP TABLE`、`DELETE FROM`、`UPDATE`、`INSERT`、`ALTER`、`CREATE`、`TRUNCATE`、`SELECT INTO` 等语句被拒绝，返回错误信息
- **状态**: [x] ✓ 2026-05-09

### Task A.2: 实现表名白名单校验
- **文件**: `tools/mysql_tools.py`
- **内容**: 
  - 复用 `list_sql_tables()` 已有的 `SHOW TABLES` 查询逻辑获取白名单
  - 在 `get_table_data` 中用白名单替换黑名单过滤
- **验收**: 恶意表名被拒绝，合法表名正常查询
- **状态**: [x] ✓ 2026-05-09

### Task A.3: 编写 SQL 安全单元测试
- **文件**: `tests/unit/test_mysql_security.py`
- **内容**: 
  - 测试 SELECT 语句被允许
  - 测试 DROP/DELETE/UPDATE/INSERT/ALTER/CREATE/TRUNCATE/SELECT INTO 被拒绝
  - 测试恶意表名被拒绝
  - 测试空表名被拒绝
- **验收**: 19 个测试全部通过
- **状态**: [x] ✓ 2026-05-09

**Quality Gate:** PASSED

## Phase B: 文件上传安全修复（~15 分钟）

### Task B.1: 添加文件名净化逻辑
- **文件**: `api/server.py` → `api/upload_security.py`
- **内容**: 使用 `Path(file.filename).name` 提取纯文件名，支持 Windows 风格路径
- **验收**: `../../../etc/passwd` 被保存为 `passwd`
- **状态**: [x] ✓ 2026-05-09

### Task B.2: 添加超长文件名防御
- **文件**: `api/upload_security.py`
- **内容**: 文件名超过 255 字符时返回 400 错误
- **验收**: 超长文件名被拒绝
- **状态**: [x] ✓ 2026-05-09

### Task B.3: 编写文件上传安全单元测试
- **文件**: `tests/unit/test_upload_security.py`
- **内容**:
  - 测试路径遍历攻击被防御
  - 测试空文件名被拒绝
  - 测试超长文件名被拒绝
  - 测试 Windows 风格路径遍历
- **验收**: 6 个测试全部通过
- **状态**: [x] ✓ 2026-05-09

**Quality Gate:** PASSED

## Phase C: CORS 配置修复（~10 分钟）

### Task C.1: 限制 CORS 源
- **文件**: `api/server.py` → `api/cors_config.py`
- **内容**:
  - 提取 CORS 配置到独立模块
  - 将 `allow_origins` 从 `["*"]` 改为 `get_allowed_origins()`
  - 通过环境变量 `FRONTEND_ORIGIN` 配置前端地址
- **验收**: 默认只允许 `http://localhost:5173`
- **状态**: [x] ✓ 2026-05-09

### Task C.2: 更新 .env.example
- **文件**: `.env.example`
- **内容**: 添加 `FRONTEND_ORIGIN=http://localhost:5173`
- **状态**: [x] ✓ 2026-05-09

**Quality Gate:** PASSED

## Phase D: 异步任务错误处理（~10 分钟）

### Task D.1: 保存 task 引用
- **文件**: `api/server.py` → `api/task_tracker.py`
- **内容**:
  - 添加 `active_tasks` 字典
  - `create_tracked_task` 替代 `asyncio.create_task`
  - `add_done_callback` 记录异常
- **验收**: Agent 任务异常后，异常信息可通过日志查询
- **状态**: [x] ✓ 2026-05-09

**Quality Gate:** PASSED

## Phase E: 回归测试（~20 分钟）

### Task E.1: 验证现有功能正常
- **内容**:
  - 验证所有安全模块能正常加载
  - 验证 FastAPI app 能正常创建
  - 验证安全函数集成正常
- **验收**: 6 个回归测试全部通过
- **状态**: [x] ✓ 2026-05-09

### Task E.2: 提交 PR
- **内容**: 创建 commit，推送到 GitHub
- **状态**: [x] ✓ 2026-05-09

**Quality Gate:** PASSED
