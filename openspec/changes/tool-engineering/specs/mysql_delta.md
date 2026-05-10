# Delta: MySQL 工具

**Change ID:** `tool-engineering`
**Affects:** tools/mysql_tools.py, tools/db_connection.py (new)

---

## ADDED

### Requirement: MySQL 连接管理器

系统应提供 MySQLConnectionManager 类管理数据库连接池，复用连接而非每次新建。

#### Scenario: 创建连接池
- GIVEN 数据库配置正确（user, password, host, port, database 均有值）
- WHEN 调用 MySQLConnectionManager.get_pool()
- THEN 返回一个有效的 MySQLConnectionPool 实例

#### Scenario: 获取连接
- GIVEN 连接池已创建
- WHEN 调用 MySQLConnectionManager.get_connection()
- THEN 从池中返回一个可用连接，而非新建

#### Scenario: 连接池配置缺失
- GIVEN 数据库配置缺失（任一配置为空）
- WHEN 调用 MySQLConnectionManager.get_pool()
- THEN 返回错误字符串，提示配置缺失

### Requirement: SQL 类型校验

工具应拒绝非 SELECT 查询，防止数据修改。

#### Scenario: 拒绝写入操作
- GIVEN 用户传入 "DROP TABLE users"
- WHEN 调用 execute_sql_query
- THEN 返回错误字符串 "错误：只允许 SELECT 查询，检测到写入关键字 DROP"

#### Scenario: 允许纯 SELECT
- GIVEN 用户传入 "SELECT * FROM users LIMIT 10"
- WHEN 调用 execute_sql_query
- THEN 正常执行并返回查询结果

### Requirement: 表名白名单校验

工具应通过 SHOW TABLES 获取白名单，只允许访问真实存在的表。

#### Scenario: 访问不存在的表
- GIVEN 用户传入表名 "nonexistent_table"
- WHEN 调用 get_table_data
- THEN 返回错误字符串 "错误：无效的表名 'nonexistent_table'"

---

## MODIFIED

### Requirement: MySQL 工具错误处理

所有 MySQL 工具函数应返回错误字符串，不向外抛异常。

#### Scenario: 数据库连接失败
- GIVEN 数据库服务不可用
- WHEN 调用 list_sql_tables / get_table_data / execute_sql_query
- THEN 返回包含 "错误" 前缀的字符串，不抛异常

---

## REMOVED

(None)
