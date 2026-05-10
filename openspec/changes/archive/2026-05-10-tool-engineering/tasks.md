# Implementation Tasks: 工具工程化

**Change ID:** `tool-engineering`

---

## Phase A: MySQL 连接管理器

- [x] A.1 新建 `tools/db_connection.py`：MySQLConnectionManager 类，支持连接池 ✓ 2026-05-10
- [x] A.2 编写 `tools/db_connection.py` 单元测试（连接池创建、获取、释放） ✓ 2026-05-10
- [x] A.3 重构 `tools/mysql_tools.py`：使用 ConnectionManager 替代每次新建连接 ✓ 2026-05-10
- [x] A.4 编写 `tools/mysql_tools.py` 单元测试（白名单校验、SQL 类型校验、错误返回格式） ✓ 2026-05-10

**Quality Gate:**
- [ ] pytest 单元测试通过
- [ ] lint 检查通过

---

## Phase B: Tavily 工具重构

- [x] B.1 重构 `tools/tavily_tools.py`：改为返回错误字符串、增加重试（3次）和超时（10秒） ✓ 2026-05-10
- [x] B.2 编写 `tools/tavily_tools.py` 单元测试（重试逻辑、超时、错误返回格式） ✓ 2026-05-10

**Quality Gate:**
- [x] pytest 单元测试通过
- [x] lint 检查通过

---

## Phase C: RAGFlow 工具重构

- [x] C.1 重构 `tools/ragflow_tools.py`：RAGFlow client 封装，修复 session 泄漏 ✓ 2026-05-10
- [x] C.2 编写 `tools/ragflow_tools.py` 单元测试（session 清理、错误返回格式） ✓ 2026-05-10

**Quality Gate:**
- [x] pytest 单元测试通过
- [x] lint 检查通过

---

## Phase D: env 加载集中化

- [x] D.1 在 `api/server.py` 启动时统一 `load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")`，锁定路径避免 CWD 问题 ✓ 2026-05-10
- [x] D.2 从所有工具文件中移除 `load_dotenv()` 调用 ✓ 2026-05-10
- [x] D.3 验证工具函数通过 `os.environ` 正常读取配置 ✓ 2026-05-10

**Quality Gate:**
- [x] 现有测试全部通过
- [x] 工具文件不再有 `load_dotenv` 调用

---

## Completion Checklist

- [ ] 所有 phases 完成
- [ ] 所有 quality gates 通过
- [ ] 测试覆盖率 > 60%（工具函数）
- [ ] 准备 `/openspec-archive`
