"""CORS 配置管理"""
import os


def get_allowed_origins() -> list:
    """
    获取允许的 CORS 源列表。

    通过 FRONTEND_ORIGIN 环境变量配置前端地址。
    如果未设置，默认允许 localhost:5173（Vite 开发服务器）。

    Returns:
        list: 允许的源地址列表
    """
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    return [frontend_origin]


def validate_cors_origin(origin: str) -> bool:
    """
    校验请求源是否合法。

    Args:
        origin: 请求的 Origin 头

    Returns:
        bool: 是否允许该源
    """
    allowed = get_allowed_origins()
    return origin in allowed
