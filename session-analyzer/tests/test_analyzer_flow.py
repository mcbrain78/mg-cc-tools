"""Tests for flow helpers: SAN-14 (agent linkage)."""
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
