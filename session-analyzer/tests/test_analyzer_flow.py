"""Tests for flow helpers: SAN-14 (agent linkage) and flow command."""
import argparse
import pytest

from conftest import load_analyzer


class TestAgentLinkage:
    """SAN-14: agent-to-process linkage via agentId."""

    def test_extract_agent_id(self):
        mod = load_analyzer()
        text = (
            "Some result text here.\n"
            "agentId: afd61812c0eb385cc (for resuming to continue this agent's work if needed)\n"
            "<usage>total_tokens: 1000\ntool_uses: 5\nduration_ms: 2000</usage>"
        )
        agent_id = mod.extract_agent_id(text)
        assert agent_id == "afd61812c0eb385cc"

    def test_extract_agent_id_missing(self):
        mod = load_analyzer()
        text = "Just a normal tool result with no agent ID."
        agent_id = mod.extract_agent_id(text)
        assert agent_id is None

    def test_build_agent_map(self):
        mod = load_analyzer()
        processes = [
            {"id": "abc123", "messages": [], "durationMs": 100},
            {"id": "def456", "messages": [], "durationMs": 200},
        ]
        data = {"processes": processes}
        agent_map = mod.build_agent_map(data)
        assert "abc123" in agent_map
        assert "def456" in agent_map
        assert agent_map["abc123"]["durationMs"] == 100

    @pytest.mark.slow
    def test_agent_map_75mb(self, sample_75mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        agent_map = mod.build_agent_map(data)
        assert len(agent_map) == 216


class TestFlowCommand:
    """Tests for the flow command classification rules."""

    def test_flow_output_format(self, sample_1mb_path, sample_1mb_data):
        """Flow on 1MB sample produces lines for every non-skipped message."""
        mod = load_analyzer()
        args = argparse.Namespace(offset=0, limit=200, all=True)
        result = mod.cmd_flow(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        # Should have flow lines for non-skipped messages
        assert len(lines) > 0
        # Verify timestamp or --:--:-- prefix pattern
        for line in lines[:5]:
            assert ":" in line  # timestamps or flow labels

    def test_flow_skips_system_messages(self):
        """System messages (no role or type=system) produce no flow lines."""
        mod = load_analyzer()
        messages = [
            {"type": "system", "content": "System prompt here"},
            {"content": "No role message"},
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(offset=0, limit=20, all=True)
        result = mod.cmd_flow(data, "test.json", args)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        assert len(lines) == 0

    def test_flow_skips_thinking_only(self):
        """Assistant messages with only thinking blocks produce no flow lines."""
        mod = load_analyzer()
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "Let me think about this..."}],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(offset=0, limit=20, all=True)
        result = mod.cmd_flow(data, "test.json", args)
        lines = [l for l in result.strip().split("\n") if l.strip() and not l.startswith("---")]
        assert len(lines) == 0

    def test_flow_pagination(self, sample_1mb_path, sample_1mb_data):
        """Flow with --limit 5 shows footer."""
        mod = load_analyzer()
        args = argparse.Namespace(offset=0, limit=5, all=False)
        result = mod.cmd_flow(sample_1mb_data, str(sample_1mb_path), args)
        assert "--offset" in result
        assert "5 of" in result

    @pytest.mark.slow
    def test_flow_agent_linkage_75mb(self, sample_75mb_path):
        """Flow on 75MB sample shows Agent calls with process_id prefix."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(offset=0, limit=5000, all=True)
        result = mod.cmd_flow(data, str(sample_75mb_path), args)
        assert "Agent(" in result
        # Should have at least one process_id prefix in brackets
        assert "[" in result
