import pytest
import yaml
from pathlib import Path


@pytest.fixture
def prompt_config():
    """Load prompts.yml configuration for testing."""
    prompt_path = Path(__file__).parents[2] / "prompt" / "prompts.yml"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestPromptConfigLoading:
    """Verify prompts.yml loads correctly and contains required structure."""

    def test_prompts_yml_loads(self, prompt_config):
        """prompts.yml must parse without YAML errors."""
        assert "main_agent" in prompt_config
        assert "sub_agents" in prompt_config

    def test_main_agent_has_system_prompt(self, prompt_config):
        """main_agent must have system_prompt field."""
        assert "system_prompt" in prompt_config["main_agent"]
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert len(prompt) > 0

    def test_sub_agents_defined(self, prompt_config):
        """sub_agents must define tavily, db, and ragflow."""
        sub_agents = prompt_config["sub_agents"]
        assert "tavily" in sub_agents
        assert "db" in sub_agents
        assert "ragflow" in sub_agents


class TestFourStageGating:
    """Verify four-stage gating workflow is present in system prompt."""

    def test_four_stage_markers_present(self, prompt_config):
        """System prompt must contain all four stage completion markers."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        for i in range(1, 5):
            assert f"【阶段 {i} 完成】" in prompt, f"Missing stage {i} completion marker"

    def test_stage_names_present(self, prompt_config):
        """System prompt must contain all four stage names."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        stage_names = ["阶段 1 - 需求分析", "阶段 2 - 信息收集",
                       "阶段 3 - 大纲确认", "阶段 4 - 报告生成"]
        for name in stage_names:
            assert name in prompt, f"Missing stage name: {name}"

    def test_stage_order_enforcement(self, prompt_config):
        """Prompt must enforce stage ordering (no skip, no reorder)."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        # Check for ordering constraint language
        assert "不得跳过" in prompt or "不得颠倒" in prompt
        assert "必须" in prompt  # mandatory execution language

    def test_gating_workflow_section_exists(self, prompt_config):
        """Four-stage gating section header must be present."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert "【工作流程：四阶段门控】" in prompt


class TestReportOutline:
    """Verify report outline template is present in system prompt."""

    def test_required_report_sections(self, prompt_config):
        """Report outline must include mandatory sections."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        for section in ["摘要", "核心发现", "结论与建议"]:
            assert section in prompt, f"Missing required report section: {section}"

    def test_report_template_structure(self, prompt_config):
        """Report template must use markdown heading structure."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert "## 摘要" in prompt
        assert "## 背景信息" in prompt
        assert "## 核心发现" in prompt
        assert "## 结论与建议" in prompt
        assert "## 参考资料" in prompt


class TestKeyConstraints:
    """Verify key constraints are present in system prompt."""

    def test_key_constraints_section(self, prompt_config):
        """Key constraints section must exist in prompt."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert "关键约束" in prompt

    def test_placeholder_content_prohibited(self, prompt_config):
        """Prompt must prohibit placeholder content."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert "严禁使用" in prompt or "占位符" in prompt

    def test_info_before_generation(self, prompt_config):
        """Prompt must require info collection before file generation."""
        prompt = prompt_config["main_agent"]["system_prompt"]
        assert "获取信息之前" in prompt or "信息收集" in prompt
