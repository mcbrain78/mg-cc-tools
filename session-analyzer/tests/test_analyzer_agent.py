"""Tests for agent-list and agent deep dive commands: SAN-04, SAN-05, SAN-07, SAN-16."""
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


class TestAgentDeepDive:
    """Tests for agent deep dive command (SAN-06)."""

    @pytest.mark.slow
    def test_agent_by_prefix_75mb(self, sample_75mb_path):
        """Pick a known agent from 75MB sample, verify deep dive output."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        # Get first process ID as prefix
        first_proc = data["processes"][0]
        prefix = first_proc["id"][:8]
        args = argparse.Namespace(prefix=prefix, offset=0, limit=100, all=True)
        result = mod.cmd_agent(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        # Header should contain agent prefix
        assert prefix in result
        # Should have interleaved entries
        assert "msg[" in result

    def test_agent_shows_tool_calls(self):
        """Verify output contains -> tool call entries."""
        mod = load_analyzer()
        data = _make_agent_data()
        args = argparse.Namespace(prefix="agent001", offset=0, limit=100, all=True)
        result = mod.cmd_agent(data, "test.json", args)
        assert isinstance(result, str)
        assert "->" in result

    def test_agent_summary_mode(self):
        """Verify agent output does NOT contain full tool result content (summary command)."""
        mod = load_analyzer()
        data = _make_agent_data()
        args = argparse.Namespace(prefix="agent001", offset=0, limit=100, all=True)
        result = mod.cmd_agent(data, "test.json", args)
        assert isinstance(result, str)
        # The full tool result content should NOT appear
        assert "FULL_TOOL_RESULT_CONTENT_THAT_IS_VERY_LONG" not in result
        # But the status indicator should appear
        assert "<-" in result

    def test_agent_msg_references(self):
        """Verify each entry has msg[N] reference."""
        mod = load_analyzer()
        data = _make_agent_data()
        args = argparse.Namespace(prefix="agent001", offset=0, limit=100, all=True)
        result = mod.cmd_agent(data, "test.json", args)
        assert isinstance(result, str)
        assert "msg[0]" in result
        assert "msg[1]" in result

    def test_agent_shows_header(self):
        """Agent header shows ID, status, message count."""
        mod = load_analyzer()
        data = _make_agent_data()
        args = argparse.Namespace(prefix="agent001", offset=0, limit=100, all=True)
        result = mod.cmd_agent(data, "test.json", args)
        assert isinstance(result, str)
        assert "Agent agent00" in result
        assert "messages" in result


class TestAmbiguousPrefix:
    """SAN-16: ambiguous agent prefix handling."""

    @pytest.mark.slow
    def test_ambiguous_prefix_75mb(self, sample_75mb_path):
        """Use a 1-char prefix that matches multiple agents, verify error lists matches."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        # Use a 1-char prefix that likely matches multiple agents
        # Get first char of a process ID
        first_char = data["processes"][0]["id"][0]
        # Count how many match
        matching = [p for p in data["processes"] if p["id"].startswith(first_char)]
        if len(matching) < 2:
            pytest.skip("Need at least 2 agents with same prefix char")
        with pytest.raises(SystemExit):
            mod.resolve_agent_prefix(data, first_char)

    def test_no_match_prefix(self):
        """Use a prefix matching no agents, verify error message."""
        mod = load_analyzer()
        data = {"processes": [{"id": "abc123", "messages": []}]}
        with pytest.raises(SystemExit):
            mod.resolve_agent_prefix(data, "zzz")

    def test_exact_match(self):
        """Use full ID, verify it resolves to exactly one agent."""
        mod = load_analyzer()
        data = {"processes": [
            {"id": "abc123def", "messages": []},
            {"id": "abc456ghi", "messages": []},
        ]}
        proc, pid = mod.resolve_agent_prefix(data, "abc123def")
        assert pid == "abc123def"
        assert proc["id"] == "abc123def"

    def test_ambiguous_prefix_message(self, capsys):
        """Ambiguous prefix error message lists matching prefixes."""
        mod = load_analyzer()
        data = {"processes": [
            {"id": "abc123def", "messages": []},
            {"id": "abc456ghi", "messages": []},
        ]}
        with pytest.raises(SystemExit):
            mod.resolve_agent_prefix(data, "abc")
        captured = capsys.readouterr()
        assert "Ambiguous" in captured.out or "Ambiguous" in captured.err


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_data():
    """Create synthetic data with one agent process for testing."""
    return {
        "session": {},
        "metrics": {},
        "messages": [],
        "processes": [
            {
                "id": "agent001deadbeef",
                "durationMs": 5000,
                "isOngoing": False,
                "metrics": {"totalTokens": 1000},
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "Do the task: build the feature"}],
                    },
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "I will start working on this."},
                            {
                                "type": "tool_use",
                                "id": "toolu_001",
                                "name": "Read",
                                "input": {"file_path": "/tmp/test.py"},
                            },
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_001",
                                "content": "FULL_TOOL_RESULT_CONTENT_THAT_IS_VERY_LONG " * 50,
                            },
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "The file looks good. Task complete."}],
                    },
                ],
            },
        ],
    }
