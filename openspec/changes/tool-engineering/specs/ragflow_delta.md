# Delta: RAGFlow 工具

**Change ID:** `tool-engineering`
**Affects:** tools/ragflow_tools.py

---

## ADDED

### Requirement: RAGFlow 会话清理保证

提问工具必须确保临时 session 在使用后被删除，即使中途发生异常。

#### Scenario: 正常流程删除 session
- GIVEN 有效的助手名称和问题
- WHEN 调用 create_ask_delete
- THEN session 在回答获取后被删除

#### Scenario: 异常情况仍删除 session
- GIVEN 有效的助手名称，但 ask 过程抛异常
- WHEN 调用 create_ask_delete
- THEN finally 块确保 session 被尝试删除，返回错误字符串

### Requirement: RAGFlow 环境配置

RAGFlow 工具应通过 os.environ 读取配置，不在工具文件中调用 load_dotenv()。

#### Scenario: 环境变量已配置
- GIVEN RAGFLOW_API_URL 和 RAGFLOW_API_KEY 已设置
- WHEN 调用 get_assistant_list 或 create_ask_delete
- THEN 正常连接 RAGFlow 服务

#### Scenario: 环境变量缺失
- GIVEN RAGFLOW_API_URL 或 RAGFLOW_API_KEY 未设置
- WHEN 调用 get_assistant_list 或 create_ask_delete
- THEN 返回错误字符串提示配置缺失

---

## MODIFIED

(None — RAGFlow 工具的核心逻辑保持不变，仅修复 session 泄漏和 env 加载)

---

## REMOVED

(None)
