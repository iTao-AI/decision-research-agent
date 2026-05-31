import mysql.connector
from mysql.connector import pooling, Error


class MySQLConnectionManager:
    """MySQL 连接管理器，支持连接池复用"""

    def __init__(self, config: dict):
        self.config = config
        self._pool = None

    def create_pool(self) -> str:
        """创建连接池。成功返回空字符串，失败返回错误字符串"""
        required_keys = ["user", "password", "host", "port", "database"]
        if not all(self.config.get(k) for k in required_keys):
            return "错误：MySQL 配置缺失（需 user, password, host, port, database）"
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="deep_search_pool",
                pool_size=5,
                pool_reset_session=True,
                connection_timeout=10,  # 连接超时 10s
                **self.config,
            )
            return ""
        except Error as e:
            error_msg = str(e).lower()
            if "timed out" in error_msg or "timeout" in error_msg:
                return "Error: database connection timed out"
            return f"错误：创建 MySQL 连接池失败: {e}"

    def get_connection(self):
        """从连接池获取连接。未创建池时返回错误字符串"""
        if self._pool is None:
            return "错误：连接池未创建，请先调用 create_pool()"
        try:
            return self._pool.get_connection()
        except Error as e:
            error_msg = str(e).lower()
            if "timed out" in error_msg or "timeout" in error_msg:
                return "Error: database connection timed out"
            return f"错误：获取连接失败: {e}"

    def release_connection(self, connection):
        """释放连接回池"""
        if self._pool is not None:
            try:
                self._pool.add_connection(connection)
            except Error:
                pass
