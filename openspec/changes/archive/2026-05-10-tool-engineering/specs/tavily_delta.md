# Delta: Tavily 工具

**Change ID:** `tool-engineering`
**Affects:** tools/tavily_tools.py

---

## ADDED

### Requirement: 网络搜索重试机制

网络搜索失败时应自动重试，最多 3 次，使用指数退避策略。

#### Scenario: 首次请求失败后重试
- GIVEN 网络短暂不可用
- WHEN 调用 internet_search
- THEN 自动重试，最多 3 次，成功后返回结果

#### Scenario: 重试耗尽
- GIVEN 网络持续不可用
- WHEN 调用 internet_search 且 3 次重试均失败
- THEN 返回错误字符串，不抛异常

### Requirement: 网络搜索超时

网络搜索应有 10 秒超时限制，防止无限等待。

#### Scenario: 请求超时
- GIVEN 服务器响应超过 10 秒
- WHEN 调用 internet_search
- THEN 超时后返回错误字符串，不抛异常

---

## MODIFIED

### Requirement: 网络搜索错误处理

internet_search 应返回错误字符串，不向外抛异常。

#### Scenario: API Key 无效
- GIVEN TAVILY_API_KEY 配置错误
- WHEN 调用 internet_search
- THEN 返回包含错误信息的字符串，不 raise 异常

---

## REMOVED

### Requirement: Tavily 顶层 client 创建

移除模块顶层的 `tavily_client = TavilyClient(api_key=...)` 初始化。改为每次调用时惰性创建。
