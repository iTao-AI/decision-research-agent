# Delta Spec: 分层测试体系

**Change ID:** `phase-5-testing`
**Affects:** tests/

---

## ADDED

### Requirement: 测试基础设施 — conftest.py

系统必须提供共享测试 fixtures，避免每个测试文件重复搭建。

#### Scenario: session_dir fixture
- GIVEN 一个测试函数声明 `session_dir` fixture
- WHEN 测试运行时
- THEN 自动创建临时目录，测试结束后自动清理

#### Scenario: mock LLM response fixture
- GIVEN 一个测试函数声明 `mock_llm` fixture
- WHEN Agent 调用 LLM 时
- THEN 返回预设的 mock 响应，不调用真实 API

---

### Requirement: Agent 委派链路集成测试

必须验证主 Agent → 子 Agent 的委派结构正确性。

#### Scenario: 委派结构验证
- GIVEN mock LLM 返回包含委派指令的响应
- WHEN 主 Agent 处理任务
- THEN 子 Agent 列表包含预期的 Agent（network_search、database_query、knowledge_base）

#### Scenario: 工具注册验证
- GIVEN 主 Agent 初始化
- WHEN 检查可用工具
- THEN 每个子 Agent 的 to_dict() 输出包含 name、description、system_prompt、tools

---

### Requirement: 报告生成集成测试

必须验证报告文件生成到正确的工作目录。

#### Scenario: Markdown 报告生成
- GIVEN 一个有效的 session_dir
- WHEN Agent 完成报告生成
- THEN `.md` 文件存在于 session_dir 下
- AND 文件内容包含预期标题

#### Scenario: 报告路径隔离
- GIVEN 两个不同的 session_dir
- WHEN 两个 session 分别生成报告
- THEN 报告文件只出现在各自的 session_dir 下，不交叉

---

### Requirement: ContextVar 隔离集成测试

必须验证两个并发 run_deep_agent 调用的 session 隔离。

#### Scenario: 并发 session 隔离
- GIVEN 两个并发 run_deep_agent 调用，分别设置 session_dir_A 和 session_dir_B
- WHEN 两个任务执行过程中
- THEN A 只能读取 session_dir_A
- AND B 只能读取 session_dir_B
- AND 两者不会交叉访问对方的 session_dir

#### Scenario: ContextVar 清理
- GIVEN 一个 run_deep_agent 调用完成
- WHEN finally 块执行后
- THEN ContextVar 被正确重置，不影响后续请求

---

### Requirement: API 端点集成测试

必须验证核心 REST 端点的正确性和安全边界。

#### Scenario: POST /api/task 返回 thread_id
- GIVEN 有效的任务请求（query 参数）
- WHEN 发送 POST /api/task
- THEN 返回 200 和包含 thread_id 的 JSON

#### Scenario: POST /api/upload 路径遍历防御
- GIVEN 文件名包含 `../../../etc/passwd`
- WHEN 发送 POST /api/upload
- THEN 返回 400 或文件名被安全处理

#### Scenario: GET /api/telemetry 返回遥测数据
- GIVEN 一个已执行过工具的 thread_id
- WHEN 发送 GET /api/telemetry/{thread_id}
- THEN 返回该 thread_id 的 TelemetryRecord 列表

#### Scenario: GET /api/telemetry 不存在 thread_id
- GIVEN 一个不存在的 thread_id
- WHEN 发送 GET /api/telemetry/{thread_id}
- THEN 返回空数组

---
