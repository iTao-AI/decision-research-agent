# 外部服务清单

## 依赖概览

| 服务 | 用途 | 协议 | SLA/可用性 | 当前超时 | 当前重试 | 降级策略 |
|------|------|------|------------|----------|----------|----------|
| DeepSeek official API | LLM 推理 | OpenAI 兼容 HTTP | 外部托管 | 120s | provider fallback | DeepSeek V4 Flash fallback |
| Tavily Search | 网络搜索 | REST API | ~99% | 无 | 3 次 | 无 |
| RAGFlow | 企业知识库检索 | REST API (流式) | 自建，不稳定 | 无 | 无 | 返回空结果 |
| MySQL | 业务数据存储 | TCP | 自建 | 连接池管理 | 无 | 无 |

## 各服务详情

### DeepSeek official API

- **环境变量**: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_REASONING_EFFORT`, `LLM_THINKING_MODE`
- **模型**: 默认 `deepseek-v4-pro`，fallback 为 `deepseek-v4-flash`
- **兼容变量**: `LLM_QWEN_MAX` 仅在 `LLM_MODEL` 未设置时读取
- **当前配置**: thinking mode 默认 enabled，`reasoning_effort` 默认 max
- **待改进**: 请求 ID 记录、provider 错误分层统计

### Tavily Search

- **环境变量**: `TAVILY_API_KEY`
- **API**: Tavily Search API
- **当前重试**: 内置 3 次重试
- **当前超时**: 无（待改进，Phase 7b）
- **降级策略**: 无 fallback 引擎（待改进，Phase 7b）

### RAGFlow

- **环境变量**: `RAGFLOW_API_URL`, `RAGFLOW_API_KEY`
- **API**: 自建 RAGFlow 服务
- **当前重试**: 无（待改进，Phase 7b）
- **当前超时**: 流式响应无超时（待改进，Phase 7b）
- **降级策略**: 返回空结果字符串

### MySQL

- **环境变量**: `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT`
- **连接管理**: 连接池
- **瞬断重试**: 无（待改进，Phase 7b）

## 安全注意事项

1. **API Key 管理**: 所有密钥存于 `.env` 文件，不应提交到 git
2. **路径遍历防护**: 文件读写工具限制在 session workspace 内
3. **SQL 注入**: 由子 Agent prompt 约束，但缺少参数化查询强制
4. **SSRF**: 外部服务 URL 可配置，需确保不暴露内网地址

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-05-19 | 初始外部服务清单 |
