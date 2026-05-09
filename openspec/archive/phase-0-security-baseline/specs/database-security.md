# Spec: 数据库查询安全

## 描述

数据库查询工具必须防止 SQL 注入和破坏性操作。所有查询限制为只读，表名必须通过白名单校验。

## 需求

### REQ-1: SQL 语句类型校验

**Given** 一个 SQL 查询请求  
**When** 调用 `execute_sql_query(query)`  
**Then** 系统必须校验 query 为纯 SELECT 语句（不包含 INTO、UNION DELETE 等写入操作）  

**Given** 一个包含 DROP/DELETE/UPDATE/INSERT/ALTER/CREATE/TRUNCATE 的查询  
**When** 调用 `execute_sql_query(query)`  
**Then** 系统必须拒绝并返回错误信息："只允许 SELECT 查询"

**Given** 一个 SELECT INTO 查询  
**When** 调用 `execute_sql_query(query)`  
**Then** 系统必须拒绝并返回错误信息："SELECT INTO 不被允许"

### REQ-2: 表名白名单校验

**Given** 数据库中存在表 `users`, `orders`, `products`  
**When** 调用 `get_table_data("users")`  
**Then** 系统必须从 `SHOW TABLES` 获取的白名单中校验表名  
**And** 如果表名在白名单中，执行查询  
**And** 如果表名不在白名单中，返回错误信息

**Given** 一个恶意表名 `users; DROP TABLE users`  
**When** 调用 `get_table_data("users; DROP TABLE users")`  
**Then** 系统必须拒绝并返回错误信息："无效的表名"

### REQ-3: 边界场景 - 特殊字符表名

**Given** 一个包含特殊字符的表名请求  
**When** 调用 `get_table_data("users UNION SELECT * FROM information_schema.tables")`  
**Then** 系统必须拒绝并返回错误信息："无效的表名"

**Given** 一个空字符串表名  
**When** 调用 `get_table_data("")`  
**Then** 系统必须返回错误信息："表名不能为空"

**Given** 一个包含路径遍历的表名  
**When** 调用 `get_table_data("../../etc/passwd")`  
**Then** 系统必须拒绝并返回错误信息："无效的表名"

### REQ-4: 白名单来源

**Given** 系统需要校验表名合法性  
**When** 调用 `get_table_data()` 或 `list_sql_tables()`  
**Then** 系统必须复用 `list_sql_tables()` 已有的 `SHOW TABLES` 查询结果作为白名单  
**And** 不得引入新的数据库查询方式（如 `information_schema.tables`）  
**Note**: 白名单缓存不属于 Phase 0 范围，将在 Phase 2 连接管理器中实现
