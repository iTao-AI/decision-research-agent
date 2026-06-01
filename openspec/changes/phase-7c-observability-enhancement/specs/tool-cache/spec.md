## ADDED Requirements

### Requirement: TTL 缓存核心

系统提供 `TTLCache` 类，实现基于 TTL（Time-To-Live）的内存缓存。

#### Scenario: 存入和读取
- **WHEN** 调用 `cache.set("key1", "value", ttl=300)` 后调用 `cache.get("key1")`
- **THEN** 返回 `"value"`

#### Scenario: 过期 key 返回 None
- **WHEN** 存入 key 时设置 `ttl=0.1`，等待 0.2 秒后调用 `cache.get("key")`
- **THEN** 返回 `None`，且该 key 从缓存中清除

#### Scenario: 不存在的 key 返回 None
- **WHEN** 调用 `cache.get("nonexistent")`
- **THEN** 返回 `None`

#### Scenario: 容量上限淘汰
- **WHEN** 缓存容量为 100，存入第 101 个 key
- **THEN** 自动淘汰最早过期的 key，保持总量不超过上限

### Requirement: 缓存装饰器

系统提供 `@cached_tool` 装饰器，为异步工具函数自动添加缓存能力。

#### Scenario: 首次调用写入缓存
- **WHEN** 装饰后的函数首次以相同参数调用
- **THEN** 执行原函数并将结果存入缓存

#### Scenario: 缓存命中跳过执行
- **WHEN** 装饰后的函数以相同参数在 TTL 内再次调用
- **THEN** 直接返回缓存结果，不执行原函数

#### Scenario: 不同参数产生不同缓存
- **WHEN** 装饰后的函数以不同参数调用
- **THEN** 视为不同的缓存 key，各自独立缓存

#### Scenario: 缓存命中上报 monitor
- **WHEN** 缓存命中返回结果
- **THEN** 调用 `monitor.report_cache_hit(tool_name, cached=True)` 记录命中事件

### Requirement: Tavily 应用缓存

Tavily 搜索工具应用 `@cached_tool` 装饰器。

#### Scenario: Tavily 搜索缓存生效
- **WHEN** 相同查询在 5 分钟内第二次执行
- **THEN** 返回缓存结果，不实际调用 Tavily API

#### Scenario: 缓存过期后重新调用
- **WHEN** 相同查询在缓存 TTL（默认 5 分钟）过期后执行
- **THEN** 重新调用 Tavily API 并刷新缓存

#### Scenario: 缓存不影响错误处理
- **WHEN** Tavily API 调用抛出异常
- **THEN** 异常正常传播，不将错误结果存入缓存
