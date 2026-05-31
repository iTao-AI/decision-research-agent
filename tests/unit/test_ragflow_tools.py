"""Phase 7b: RAGFlow 工具重构测试 — 超时、重试和 session 清理"""
import asyncio
import os
import time
import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture(autouse=True)
def _mock_dependencies():
    """Mock ragflow SDK and dependencies"""
    for mod in ["ragflow_sdk", "dotenv", "api.monitor", "tools.ragflow_tools"]:
        sys.modules.pop(mod, None)

    mock_ragflow_mod = MagicMock()
    mock_ragflow_sdk = MagicMock()
    mock_ragflow_mod.RAGFlow = mock_ragflow_sdk
    sys.modules["ragflow_sdk"] = mock_ragflow_mod
    sys.modules["api.monitor"] = MagicMock()
    sys.modules["api.monitor"].monitor = MagicMock()

    os.environ["RAGFLOW_API_KEY"] = "test_key"
    os.environ["RAGFLOW_API_URL"] = "http://localhost:8080"

    yield

    for mod in ["ragflow_sdk", "dotenv", "api.monitor", "tools.ragflow_tools"]:
        sys.modules.pop(mod, None)


class TestRAGFlowTools:
    """测试 RAGFlow 工具的 session 清理和错误返回"""

    def test_get_assistant_list_returns_string(self):
        """正常应返回格式化的字符串"""
        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_chat.description = "Test Desc"
        mock_chat.datasets = []
        mock_rag.list_chats.return_value = [mock_chat]

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import get_assistant_list
            result = get_assistant_list.invoke({"dummy_arg": ""})
            assert "TestBot" in result

    def test_get_assistant_list_missing_config(self):
        """配置缺失应返回错误字符串"""
        os.environ.pop("RAGFLOW_API_KEY", None)

        from tools.ragflow_tools import get_assistant_list
        result = get_assistant_list.invoke({"dummy_arg": ""})
        assert "错误" in result

    def test_create_ask_delete_session_cleanup_on_success(self):
        """正常流程应删除 session"""
        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_session = MagicMock()
        mock_session.id = "session_123"
        mock_chat.create_session.return_value = mock_session

        # Mock streaming response
        mock_response = MagicMock()
        mock_response.content = "Test answer"
        mock_session.ask.return_value = [mock_response]

        mock_rag.list_chats.return_value = [mock_chat]

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import create_ask_delete
            result = create_ask_delete.invoke({
                "assistant_name": "TestBot",
                "question": "Hello",
            })

            mock_chat.delete_sessions.assert_called_once_with(ids=["session_123"])
            assert "Test answer" in result

    def test_create_ask_delete_session_cleanup_on_exception(self):
        """异常流程也应删除 session"""
        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_session = MagicMock()
        mock_session.id = "session_456"
        mock_chat.create_session.return_value = mock_session
        mock_session.ask.side_effect = Exception("Network error")
        mock_rag.list_chats.return_value = [mock_chat]

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import create_ask_delete
            result = create_ask_delete.invoke({
                "assistant_name": "TestBot",
                "question": "Hello",
            })

            mock_chat.delete_sessions.assert_called_once_with(ids=["session_456"])
            assert "失败" in result


class TestRAGFlowTimeoutAndRetry:
    """测试超时和重试行为"""

    def test_timeout_raises_without_retry(self):
        """超时后应抛出 TimeoutError（不重试，交给工具入口统一降级）"""
        from tools import ragflow_tools

        def _block():
            time.sleep(10)
            return "should not reach here"

        # Patch TIMEOUTS so the test runs fast
        old_val = ragflow_tools.TIMEOUTS["ragflow"]
        ragflow_tools.TIMEOUTS["ragflow"] = 0.2
        try:
            start = time.monotonic()
            with pytest.raises(TimeoutError, match="test timed out after 0.2s"):
                ragflow_tools._retry_with_timeout(_block, service_name="test")
            elapsed = time.monotonic() - start
        finally:
            ragflow_tools.TIMEOUTS["ragflow"] = old_val

        # Should return immediately, not wait 10s
        assert elapsed < 2.0, f"Waited {elapsed:.1f}s"

    def test_connection_error_returns_structured_error(self):
        """连接错误重试后应返回结构化错误字符串"""
        mock_rag = MagicMock()
        mock_rag.list_chats.side_effect = ConnectionError("refused")

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import get_assistant_list
            result = get_assistant_list.invoke({"dummy_arg": ""})
            assert "unavailable after retries" in result

    def test_ask_timeout_raises_without_retry(self):
        """提问 helper 超时后应抛出 TimeoutError（不返回错误字符串）"""
        from tools import ragflow_tools

        def _block():
            time.sleep(10)
            return "should not reach here"

        old_val = ragflow_tools.TIMEOUTS["ragflow"]
        ragflow_tools.TIMEOUTS["ragflow"] = 0.2
        try:
            start = time.monotonic()
            with pytest.raises(TimeoutError, match="ragflow-ask timed out after 0.2s"):
                ragflow_tools._retry_with_timeout(_block, service_name="ragflow-ask")
            elapsed = time.monotonic() - start
        finally:
            ragflow_tools.TIMEOUTS["ragflow"] = old_val

        # Should return immediately, not wait 10s
        assert elapsed < 2.0, f"Waited {elapsed:.1f}s"

    def test_get_assistant_list_real_blocking_timeout_returns_structured_error(self):
        """助手列表入口遇到真实阻塞时应返回 timeout 错误，而不是类型错误"""
        from tools import ragflow_tools

        mock_rag = MagicMock()

        def _block():
            time.sleep(10)
            return []

        mock_rag.list_chats.side_effect = _block

        old_val = ragflow_tools.TIMEOUTS["ragflow"]
        ragflow_tools.TIMEOUTS["ragflow"] = 0.2
        try:
            with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
                from tools.ragflow_tools import get_assistant_list

                start = time.monotonic()
                result = get_assistant_list.invoke({"dummy_arg": ""})
                elapsed = time.monotonic() - start
        finally:
            ragflow_tools.TIMEOUTS["ragflow"] = old_val

        assert elapsed < 2.0, f"Waited {elapsed:.1f}s"
        assert result == "Error: knowledge base query timed out after retries"

    def test_ask_real_blocking_timeout_returns_structured_error(self):
        """提问入口遇到真实阻塞时应返回 timeout 错误，而不是继续使用错误字符串"""
        from tools import ragflow_tools

        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_session = MagicMock()
        mock_session.id = "sess_timeout"
        mock_chat.create_session.return_value = mock_session

        def _block(*args, **kwargs):
            time.sleep(10)
            return []

        mock_session.ask.side_effect = _block
        mock_rag.list_chats.return_value = [mock_chat]

        old_val = ragflow_tools.TIMEOUTS["ragflow"]
        ragflow_tools.TIMEOUTS["ragflow"] = 0.2
        try:
            with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
                from tools.ragflow_tools import create_ask_delete

                start = time.monotonic()
                result = create_ask_delete.invoke({
                    "assistant_name": "TestBot",
                    "question": "Hello",
                })
                elapsed = time.monotonic() - start
        finally:
            ragflow_tools.TIMEOUTS["ragflow"] = old_val

        assert elapsed < 2.0, f"Waited {elapsed:.1f}s"
        assert result == "Error: knowledge base query timed out after retries"
        mock_chat.delete_sessions.assert_called_once_with(ids=["sess_timeout"])

    def test_ask_connection_error_returns_structured_error(self):
        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_session = MagicMock()
        mock_session.id = "sess_2"
        mock_chat.create_session.return_value = mock_session
        mock_session.ask.side_effect = ConnectionError("connection refused")
        mock_rag.list_chats.return_value = [mock_chat]

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import create_ask_delete
            result = create_ask_delete.invoke({
                "assistant_name": "TestBot",
                "question": "Hello",
            })
            assert "unavailable after retries" in result

    def test_cleanup_on_timeout(self):
        """超时后应仍执行 session 清理"""
        mock_rag = MagicMock()
        mock_chat = MagicMock()
        mock_chat.name = "TestBot"
        mock_session = MagicMock()
        mock_session.id = "sess_cleanup"
        mock_chat.create_session.return_value = mock_session
        mock_session.ask.side_effect = TimeoutError("timed out")
        mock_rag.list_chats.return_value = [mock_chat]

        with patch("tools.ragflow_tools.RAGFlow", return_value=mock_rag):
            from tools.ragflow_tools import create_ask_delete
            create_ask_delete.invoke({
                "assistant_name": "TestBot",
                "question": "Hello",
            })
            mock_chat.delete_sessions.assert_called_once_with(ids=["sess_cleanup"])


class TestRealBlockingTimeout:
    """测试真实阻塞场景下的超时行为 — 不 mock TimeoutError"""

    def test_run_with_timeout_returns_immediately_on_block(self):
        """_run_with_timeout 应在超时后立即返回，不等待阻塞线程结束"""
        from tools.ragflow_tools import _run_with_timeout

        def _block_for_10_seconds():
            time.sleep(10)
            return "should not reach here"

        start = time.monotonic()
        with pytest.raises(TimeoutError, match="operation timed out after"):
            _run_with_timeout(_block_for_10_seconds, timeout=0.2)
        elapsed = time.monotonic() - start

        # Should return within ~0.2s timeout, NOT wait for 10s sleep
        assert elapsed < 2.0, f"Waited {elapsed:.1f}s instead of returning within timeout"
