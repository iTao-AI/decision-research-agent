# LangSmith 可观测性

## 默认策略

本项目采用隐私优先的 LangSmith Tracing 配置：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-workspace-scoped-service-key
LANGSMITH_PROJECT=deep-search-agent-dev
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

该配置用于观察 Agent 调用树、节点耗时、错误、状态和元数据，但不上传研究问题、工具输入、工具输出或生成报告正文。

后端 Tracing 推荐使用仅授权给目标 workspace 的 **Service Key**。它代表服务身份，适合本地后端、自动运行和未来 CI；不要使用继承个人用户全部权限的 Personal Access Token 作为应用凭证。

Personal Access Token 只适合操作者本人通过 CLI 执行个人脚本、查询或管理操作。真实 `LANGSMITH_API_KEY` 只写入被 Git 忽略的 `.env` 或运行环境变量，不得写入仓库、命令参数、日志或 Agent 对话。

## 启用步骤

1. 从 `.env.example` 同步上述 LangSmith 配置到本地 `.env`。
2. 在 LangSmith Settings 创建限制到目标 workspace 的 Service Key，由操作者手动填写 `LANGSMITH_API_KEY`。
3. 启动后端并执行一次低敏感度测试任务。
4. 使用 CLI 验证项目和 Trace：

```bash
langsmith --version
langsmith project list
langsmith trace list --project deep-search-agent-dev --limit 5 --show-hierarchy
```

如果 `langsmith project list` 返回 `401 Unauthorized`，检查本地 API Key 是否有效。不得通过 `--api-key` 参数传递密钥。

## 完整 Trace 切换门槛

只有在隐私优先 Trace 无法定位具体模型输入输出问题，并且测试任务不包含私密数据时，才临时使用完整 Trace：

```dotenv
LANGSMITH_HIDE_INPUTS=false
LANGSMITH_HIDE_OUTPUTS=false
```

完整 Trace 使用完毕后，应恢复隐藏配置。真实企业数据、候选人数据、密钥、内部文档和未脱敏报告不得进入完整 Trace。

## 当前边界

- LangSmith 是调试与评估工具，不替代 ResearchRun、EvidenceLedger 或服务端审计记录。
- 隐藏 inputs/outputs 后，无法直接在 LangSmith 中检查 Prompt、工具参数和报告正文。
- 没有有效 `LANGSMITH_API_KEY` 时，Tracing 配置不会形成可查询的 LangSmith 项目。
