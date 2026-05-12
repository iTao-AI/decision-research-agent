# Delta: 子 Agent 架构

**Change ID:** `sub-agent-architecture-upgrade`
**Affects:** agent/sub_agents/, agent/main_agent.py

---

## ADDED

### Requirement: AgentContext 状态管理

系统必须提供 `AgentContext` 用于追踪 Agent 执行状态。

#### Scenario: 创建 Agent 上下文
- GIVEN 一个 Agent 执行请求
- WHEN 创建 `AgentContext`
- THEN 包含 thread_id、workspace_dir、memory（空字典）、metadata（空字典）

#### Scenario: 跨工具调用状态共享
- GIVEN 一个已创建的 `AgentContext`
- WHEN 第一个工具调用后写入 memory
- THEN 第二个工具调用可以读取该 memory

#### Scenario: 元数据追踪
- GIVEN 一个已创建的 `AgentContext`
- WHEN Agent 执行完毕
- THEN metadata 记录调用次数、执行时间、token 消耗（如果可用）

---

### Requirement: AgentConfig 类型安全

每个子 Agent 必须使用带类型注解的 `AgentConfig` 替代 dict 字面量。

#### Scenario: 创建 Agent 配置
- GIVEN Agent 的名称、描述、system_prompt、工具列表
- WHEN 创建 `AgentConfig`
- THEN 所有字段有类型约束，缺失必填字段时报错

#### Scenario: 输出 deepagents 兼容格式
- GIVEN 一个 `AgentConfig` 实例
- WHEN 调用 `to_dict()` 方法
- THEN 输出格式与原始 dict 完全一致（name、description、system_prompt、tools）

---

### Requirement: BaseAgent 基类

提供 `BaseAgent` 基类，封装 `AgentConfig` + `AgentContext` + `to_dict()` 方法。

#### Scenario: 子类继承
- GIVEN 一个继承 `BaseAgent` 的子类
- WHEN 子类初始化
- THEN 自动获得 config、context、to_dict 能力

---

## MODIFIED

### Requirement: 子 Agent 定义方式

子 Agent 从 dict 字面量改为类实例。

#### Scenario: NetworkSearchAgent
- GIVEN 原始 `network_search_agent` 是 dict
- WHEN 重构为 `NetworkSearchAgent` 类
- THEN `.to_dict()` 输出与原始 dict 一致

#### Scenario: DatabaseQueryAgent
- GIVEN 原始 `database_query_agent` 是 dict
- WHEN 重构为 `DatabaseQueryAgent` 类
- THEN `.to_dict()` 输出与原始 dict 一致

#### Scenario: KnowledgeBaseAgent
- GIVEN 原始 `knowledge_base_agent` 是 dict
- WHEN 重构为 `KnowledgeBaseAgent` 类
- THEN `.to_dict()` 输出与原始 dict 一致

---

### Requirement: main_agent.py 适配

`main_agent.py` 需适配新的 Agent 类格式。

#### Scenario: subagents_list 构建
- GIVEN 3 个 Agent 类实例
- WHEN 构建 `subagents_list`
- THEN 通过 `.to_dict()` 输出 dict 列表，传给 `create_deep_agent`

---

## REMOVED

### Requirement: 子 Agent dict 字面量定义（Removed: 2026-05-10）

不再使用 dict 字面量定义子 Agent。原因：无类型安全、无状态管理、扩展性差。
