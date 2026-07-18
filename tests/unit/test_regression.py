"""Phase E: 回归测试 - 验证模块加载正常"""
import pytest
import os
import sys
import subprocess
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

    def test_cors_config_loads(self):
        """cors_config 模块应该能正常加载"""
        from api import cors_config
        assert hasattr(cors_config, 'get_allowed_origins')
        assert hasattr(cors_config, 'validate_cors_origin')
        assert hasattr(cors_config, 'load_cors_configuration')
        assert hasattr(cors_config, 'CorsConfiguration')

    def test_task_tracker_loads(self):
        """task_tracker 模块应该能正常加载"""
        from api import task_tracker
        assert hasattr(task_tracker, 'create_tracked_task')
        assert hasattr(task_tracker, 'get_active_task')
        assert hasattr(task_tracker, 'clear_active_tasks')

    def test_server_app_creates_isolated(self):
        """FastAPI app 应该能正常创建 — 用 subprocess 隔离避免模块污染"""
        result = subprocess.run(
            [sys.executable, "-c", """
import os
os.environ["TAVILY_API_KEY"] = "test"
os.environ["OPENAI_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["OPENAI_API_KEY"] = "test"
os.environ["LLM_QWEN_MAX"] = "qwen-max"
from unittest.mock import patch, MagicMock
with patch('agent.deepagents_harness.create_deep_agent', return_value=MagicMock()):
    with patch('tavily.TavilyClient', return_value=MagicMock()):
        with patch('ragflow_sdk.RAGFlow', return_value=MagicMock()):
            from api import server
            assert server.app is not None
            assert server.app.title == "Decision Research Agent API"
            print("OK")
"""],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        assert result.returncode == 0, f"server app failed to load:\n{result.stderr}"
        assert "OK" in result.stdout

    def test_cors_and_task_tracker_functions_integrated(self):
        """CORS and task tracker helpers remain importable."""
        from api.task_tracker import create_tracked_task, get_active_task, clear_active_tasks
        from api.cors_config import get_allowed_origins

        with patch.dict(
            os.environ,
            {
                "API_SECRET": "test-regression-only",
                "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN": "https://example.com",
            },
            clear=False,
        ):
            assert get_allowed_origins() == ["https://example.com"]
        clear_active_tasks()
        assert get_active_task("nonexistent") is None
