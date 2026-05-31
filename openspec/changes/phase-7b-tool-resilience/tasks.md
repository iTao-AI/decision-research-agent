# Phase 7b Tasks

## Phase 1: 基础设施（重试装饰器 + 超时配置）

- [x] 1.1 创建 `tools/retry_utils.py`：实现 `@retry` 异步装饰器
  - 支持 `max_retries`、`backoff_factor`、`max_wait`、`retryable_exceptions`、`service_name` 参数
  - 指数退避：`min(2^attempt * backoff_factor, max_wait)`
  - 通过 monitor 报告重试事件
  - 定义 `TIMEOUTS` 配置字典
- [x] 1.2 创建 `tests/unit/test_retry_utils.py`：重试装饰器单元测试
  - 测试首次成功无需重试
  - 测试失败后重试成功
  - 测试超过最大重试次数
  - 测试不可重试异常直接抛出
  - 测试超时异常被 asyncio.wait_for 触发
  - 测试自定义重试参数

## Phase 2: 工具层韧性增强

- [x] 2.1 修复 Tavily timeout 死代码 + 使用统一重试装饰器
  - 修正 `_search_with_retry()` 中 timeout 传递给 Tavily SDK
  - 移除内联重试逻辑，改用 `@retry` 装饰器
  - 增加 `asyncio.wait_for` 超时包裹
  - 修复已有测试（如有）
- [x] 2.2 RAGFlow 增加超时和重试
  - 对 `list_assistants` 工具的 HTTP 调用增加 60s 超时
  - 对 `ask_question` 工具的 `session.ask()` 流式调用增加 60s 超时
  - 使用 `@retry` 装饰器包裹关键调用
  - 错误字符串格式化为结构化降级信息
- [x] 2.3 MySQL 连接池增加超时配置
  - `db_connection.py` 连接池增加 `connect_timeout=10`
  - `mysql_tools.py` 查询增加 `read_timeout=30`（通过连接参数）
  - 超时错误返回结构化错误字符串

## Phase 3: 其他工具超时

- [x] 3.1 PDF 转换增加超时
  - `pdf_tools.py` 的 `convert_md_to_pdf` 增加 60s 超时包裹
  - 超时返回结构化错误字符串
- [x] 3.2 LLM 调用增加超时（如可行）
  - `agent/llm.py` 检查是否有超时配置入口
  - 如有，增加 120s 超时
  - 如无（SDK 不支持），在 `main_agent.py` 的 `astream` 调用外层包裹

## Phase 4: API 层任务超时

- [x] 4.1 `api/task_tracker.py` 增加任务级超时
  - `TrackedTask` 增加 `timeout_seconds` 字段
  - 支持从环境变量 `AGENT_TASK_TIMEOUT_SECONDS` 读取（默认 1800s）
  - 超时后调用 `task.cancel()` 并更新状态
- [x] 4.2 `api/server.py` 确认超时链路
  - 确认 WebSocket 在任务超时时发送超时事件
  - 确认任务状态正确标记为 `"timeout"`
- [x] 4.3 任务超时单元测试
  - 模拟超时场景，验证任务被 cancel
  - 验证环境变量配置生效

## Phase 5: 验证

- [x] 5.1 运行全部单元测试，确认无回归
- [x] 5.2 运行全部集成测试（如有 API key）
- [x] 5.3 手动验证超时和重试行为（可选，需 API key）
