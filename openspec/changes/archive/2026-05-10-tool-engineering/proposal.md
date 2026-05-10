<!-- /autoplan restore point: /Users/mac/.gstack/projects/iTao-AI-deep-search-agent/feature-sub-agent-architecture-upgrade-autoplan-restore-20260510-152054.md -->

# Proposal: 工具工程化 — 连接管理、统一错误处理、env 集中加载

**Change ID:** `tool-engineering`
**Created:** 2026-05-10
**Status:** Implementation Complete
**Completed:** 2026-05-10

---

## Problem Statement

三个工具模块（mysql_tools、tavily_tools、ragflow_tools）存在以下共性问题：

1. **env 加载分散**：每个工具文件顶层 `load_dotenv()`，重复执行且难以控制加载时机
2. **MySQL 无连接复用**：每次调用都 `connect(**config)` 新建连接，无连接池
3. **错误处理不统一**：Tavily 工具 `raise e` 抛异常，MySQL 和 RAGFlow 返回错误字符串
4. **Tavily 缺少重试/超时**：网络请求无保护机制
5. **RAGFlow 临时 session 泄漏风险**：`create_ask_delete` 中 session 创建后如果中途异常可能未删除

## Proposed Solution

1. **`tools/db_connection.py`（新增）**：MySQLConnectionManager 连接管理器，支持连接池
   - 使用 `mysql.connector.pooling.MySQLConnectionPool`
   - 同步 pool + `asyncio.to_thread` 包装，避免阻塞事件循环
2. **`tools/mysql_tools.py`（重构）**：使用 ConnectionManager，统一返回错误字符串
3. **`tools/tavily_tools.py`（重构）**：改为返回错误字符串，增加重试和超时
4. **`tools/ragflow_tools.py`（重构）**：RAGFlow client 封装，修复 session 泄漏
5. **`api/server.py`（修改）**：启动时统一 `load_dotenv()`，工具文件移除 `load_dotenv()`

## Scope

### In Scope
- MySQL 连接池和连接复用
- 工具统一错误处理（返回字符串，不抛异常）
- Tavily 重试和超时
- RAGFlow client 封装
- env 加载集中到 server 启动

### Out of Scope
- monitor 单例解耦（Phase 3 可观测性升级）
- AgentContext 注入工具（后续架构优化）
- 切换 MySQL 驱动到 aiomysql

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| tools/mysql_tools.py | Yes | 重构为使用 ConnectionManager |
| tools/tavily_tools.py | Yes | 重试/超时/错误处理统一 |
| tools/ragflow_tools.py | Yes | client 封装/session 泄漏修复 |
| tools/db_connection.py | New | 新增连接管理器 |
| api/server.py | Yes | 启动时 load_dotenv() |

## Architecture Considerations

- `mysql.connector` pooling 是同步的，用 `asyncio.to_thread` 包装避免阻塞事件循环
- 工具保持 `@tool` 装饰器不变，向后兼容
- 错误处理统一为返回字符串，不向外抛异常

## Success Criteria

- [ ] MySQL 工具使用连接池，不复用单个全局连接
- [ ] 所有工具函数返回错误字符串，不抛异常
- [ ] Tavily 工具具备重试（3次）和超时（10秒）
- [ ] RAGFlow session 确保删除，即使中途异常
- [ ] 工具文件不再调用 `load_dotenv()`
- [ ] 现有工具调用测试全部通过

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| 连接池在 async 上下文阻塞 | Medium | High | 使用 asyncio.to_thread 包装所有 pool 操作 |
| Tavily 重试导致延迟叠加 | Low | Medium | 指数退避，最大延迟 30 秒 |
| RAGFlow 删除 session 失败 | Low | Low | try/finally 确保清理 |
| env 加载时机变化导致配置丢失 | Low | High | server 启动时最早加载，工具只读 os.environ |
