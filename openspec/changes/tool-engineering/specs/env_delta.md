# Delta: env 加载集中化

**Change ID:** `tool-engineering`
**Affects:** api/server.py, tools/mysql_tools.py, tools/tavily_tools.py, tools/ragflow_tools.py

---

## ADDED

### Requirement: 启动时 env 加载

api/server.py 应在应用启动时统一调用 load_dotenv()，确保所有工具函数可通过 os.environ 读取配置。

#### Scenario: 服务启动
- WHEN api/server.py 启动
- THEN load_dotenv() 在最早时机执行，加载 .env 文件

---

## MODIFIED

### Requirement: 工具文件不再调用 load_dotenv

工具文件应通过 os.environ 读取配置，不自行调用 load_dotenv()。

#### Scenario: 工具被调用
- WHEN 任何工具函数被执行
- THEN 工具直接从 os.environ 读取配置，不调用 load_dotenv()

---

## REMOVED

- mysql_tools.py 顶层 `load_dotenv()`
- tavily_tools.py 顶层 `load_dotenv()`
- ragflow_tools.py 中 `_load_ragflow_env()` 内部的 `load_dotenv()`
