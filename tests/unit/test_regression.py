"""Phase E: 回归测试 - 验证模块加载正常"""
import pytest
import os
from unittest.mock import patch, MagicMock


class TestModuleLoading:
    """验证安全修复后模块加载正常"""

    def test_mysql_tools_loads(self):
        """mysql_tools 模块应该能正常加载"""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test"}):
            from tools import mysql_tools
            assert hasattr(mysql_tools, 'list_sql_tables')
            assert hasattr(mysql_tools, 'get_table_data')
            assert hasattr(mysql_tools, 'execute_sql_query')

    def test_upload_security_loads(self):
        """upload_security 模块应该能正常加载"""
        from api import upload_security
        assert hasattr(upload_security, 'sanitize_filename')
        assert hasattr(upload_security, 'validate_filename')

    def test_cors_config_loads(self):
        """cors_config 模块应该能正常加载"""
        from api import cors_config
        assert hasattr(cors_config, 'get_allowed_origins')
        assert hasattr(cors_config, 'validate_cors_origin')

    def test_task_tracker_loads(self):
        """task_tracker 模块应该能正常加载"""
        from api import task_tracker
        assert hasattr(task_tracker, 'create_tracked_task')
        assert hasattr(task_tracker, 'get_active_task')
        assert hasattr(task_tracker, 'clear_active_tasks')

    def test_server_app_creates(self):
        """FastAPI app 应该能正常创建（需要 mock 依赖）"""
        with patch.dict(os.environ, {
            "TAVILY_API_KEY": "test",
            "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "OPENAI_API_KEY": "test",
            "LLM_QWEN_MAX": "qwen-max",
        }):
            with patch('agent.main_agent.create_deep_agent', return_value=MagicMock()):
                from api import server as server_module
                assert server_module.app is not None
                assert server_module.app.title == "DeepAgents API"

    def test_security_functions_integrated(self):
        """安全函数应该能在 server 中使用"""
        from api.upload_security import sanitize_filename, validate_filename
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks

        # 保存原值
        original = os.environ.get("FRONTEND_ORIGIN")
        if "FRONTEND_ORIGIN" in os.environ:
            del os.environ["FRONTEND_ORIGIN"]

        # 重新导入获取默认值
        import importlib
        import api.cors_config
        importlib.reload(api.cors_config)
        from api.cors_config import get_allowed_origins

        # 验证函数可用
        assert sanitize_filename("test.txt") == "test.txt"
        assert validate_filename("test.txt") == ""
        assert "http://localhost:5173" in get_allowed_origins()
        clear_active_tasks()
        assert get_active_task("nonexistent") is None

        # 恢复
        if original is not None:
            os.environ["FRONTEND_ORIGIN"] = original
