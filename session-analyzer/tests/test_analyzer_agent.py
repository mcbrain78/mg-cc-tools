"""Tests for agent-list command: SAN-04, SAN-05, SAN-07."""
import argparse
import pytest

from conftest import load_analyzer


class TestAgentList:
    """Tests for agent-list command."""

    @pytest.mark.slow
    def test_agent_list_format(self, sample_75mb_path):
        """Agent-list on 75MB sample shows 216 entries with --all flag."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(offset=0, limit=300, all=True)
        result = mod.cmd_agent_list(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        assert len(lines) == 216

    @pytest.mark.slow
    def test_agent_list_line_format(self, sample_75mb_path):
        """Each line contains ID prefix, status, duration, message count."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(offset=0, limit=5, all=False)
        result = mod.cmd_agent_list(data, str(sample_75mb_path), args)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        for line in lines:
            assert "msgs" in line
            assert "tools" in line
            assert "tok" in line

    @pytest.mark.slow
    def test_agent_list_pagination(self, sample_75mb_path):
        """Agent-list with --limit 5 shows footer with '5 of 216'."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(offset=0, limit=5, all=False)
        result = mod.cmd_agent_list(data, str(sample_75mb_path), args)
        assert "5 of 216" in result
        assert "--offset" in result

    def test_agent_list_no_agents(self, sample_1mb_path, sample_1mb_data):
        """Agent-list on 1MB sample (no agents) shows empty message."""
        mod = load_analyzer()
        args = argparse.Namespace(offset=0, limit=20, all=False)
        result = mod.cmd_agent_list(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        assert "No agents" in result or "0" in result

    @pytest.mark.slow
    def test_agent_list_prompt_summary(self, sample_75mb_path):
        """Prompt summary is present and truncated to 60 chars."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(offset=0, limit=5, all=False)
        result = mod.cmd_agent_list(data, str(sample_75mb_path), args)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        for line in lines:
            # Each line should have content beyond just the stats fields
            # The prompt summary comes after "tok" and should be non-empty
            parts = line.split("tok")
            assert len(parts) >= 2
            # The part after "tok" is the prompt summary
            summary = parts[-1].strip()
            assert len(summary) > 0
            assert len(summary) <= 63  # 60 chars + potential "..."
