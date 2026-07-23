# 外部服务清单

## 当前运行时边界

| 服务 | 用途 | 超时 | 重试与降级 |
|---|---|---|---|
| Official DeepSeek provider integration | LLM 推理 | 120s | 可配置 fallback model；provider 错误继续按调用方契约处理 |
| Tavily Search | 公共网络搜索 | 单次 15s，并设置有界总超时 | 3 total attempts；成功结果进入短期 cache；无备用搜索引擎 |
| RAGFlow | 可选知识库检索 | 单次 60s | 非 timeout 异常最多 3 total attempts；terminal on timeout；失败返回有界错误文本 |
| MySQL | 通用 profile 的只读数据查询 | 连接 10s，读取/查询 30s | 连接池管理；无透明写入或跨服务 fallback |

这些数值来自 `tools/retry_utils.py`、`tools/tavily_tools.py`、
`tools/ragflow_tools.py` 和 `tools/mysql_tools.py` 的当前实现。本文不声明外部
provider SLA。

## DeepSeek And OpenAI-Compatible Providers

- `deepseek-*` model identifiers use the official LangChain DeepSeek integration.
- DeepSeek configuration prefers `DEEPSEEK_API_BASE` and
  `DEEPSEEK_API_KEY`; `OPENAI_BASE_URL` and `OPENAI_API_KEY` remain
  compatibility aliases.
- Non-DeepSeek identifiers retain the OpenAI-compatible provider path.
- `LLM_QWEN_MAX` 仅在 `LLM_MODEL` 未设置时作为兼容配置读取。
- 默认请求超时为 120s。Fallback model 是 provider/model fallback，不代表
  对所有错误自动成功或具备可用性承诺。
- Thinking-mode assistant tool calls preserve the exact
  `reasoning_content` as provider protocol state for the next request.
- Provider protocol state is not Evidence, application state, review,
  publication, or delivery authority.
- 当强制 tool selection 与 provider thinking mode 不兼容时，运行时只对该次
  tool binding 使用关闭 thinking 的模型副本；普通调用保留配置的 thinking
  mode。
- Provider-free tests cover the protocol adapter and real DeepAgents
  composition. This does not prove a live provider result, research quality,
  cost, or production readiness.

## Optional LangSmith Diagnostics

- Local structured logs use only `deepseek_provider_selected`,
  `deepseek_reasoning_protocol_validated`,
  `deepseek_reasoning_protocol_rejected`, and
  `model_fallback_activated`. They contain bounded provider/protocol facts,
  counts, codes, and exception class names; they never contain reasoning,
  message/tool payloads, credentials, provider response bodies, exception
  text, or tracebacks.
- LangChain and DeepAgents already support automatic LangSmith tracing.
  DeepSeek model runs carry only the allowlisted provider family, model role,
  provider protocol, and thinking-mode tags/metadata added by this change.
- Checked-in configuration keeps `LANGSMITH_TRACING=false`,
  `LANGSMITH_HIDE_INPUTS=true`, and `LANGSMITH_HIDE_OUTPUTS=true`; no key is
  committed.
- The bounded-live producer continues to require tracing disabled, hidden
  inputs/outputs, and an empty LangSmith key.
- A privacy-first remote trace smoke is a separate operator authorization.
  It is not required for provider correctness and does not own ResearchRun,
  Evidence, review, publication, or delivery truth.

## Tavily Search

- 环境变量：`TAVILY_API_KEY`。
- 每次请求超时 15s；resilience wrapper 设置覆盖重试和退避的有界总超时。
- 请求最多执行 3 total attempts。成功响应进入 300s cache，并受 run/thread
  scoped search de-duplication 约束。
- 没有备用搜索 provider；最终失败作为有界工具错误返回。

## RAGFlow

- 环境变量：`RAGFLOW_API_URL`, `RAGFLOW_API_KEY`。
- 每次检索超时 60s。TimeoutError 是 terminal on timeout，不进入下一次尝试。
- 其他异常最多执行 3 total attempts，并使用有界退避。
- 没有备用知识库 provider；最终失败返回有界错误文本。

## MySQL

- 环境变量：`MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`,
  `MYSQL_DATABASE`, `MYSQL_PORT`。
- 连接池配置连接超时 10s、读取/查询超时 30s。
- 表浏览使用 table whitelist；自定义查询使用 SELECT-only textual guard，并
  拒绝常见写入关键字和 `SELECT INTO`。
- 该文本校验 is not an AST or parameter-binding authority。模型生成的任意 SQL
  仍应视为不可信输入；部署时应使用 least-privilege read-only account，并在
  数据库权限层拒绝写入和越权读取。

## 安全注意事项

1. 密钥只通过环境变量或本地 `.env` 注入，不提交到 Git。
2. 外部服务 URL 属于 operator 配置；部署环境应限制可达网络，避免把内部地址
   暴露给不可信配置来源。
3. Tool output 在进入 application ledger 前仍是不可信文本，必须通过既有 schema、
   Evidence reference 和持久化边界。
4. MySQL 应以数据库账户权限作为最终写保护；应用层文本校验不是 SQL parser。
