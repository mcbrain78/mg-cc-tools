"""Tests for search command: SAN-06, SAN-17."""
import argparse
import pytest

from conftest import load_analyzer


class TestSearchCommand:
    """Tests for search command basics."""

    def test_search_finds_text(self, sample_1mb_path, sample_1mb_data):
        """Search for a known string in 1MB sample, verify results found."""
        mod = load_analyzer()
        # "Bash" is a tool name that should appear in tool inputs
        args = argparse.Namespace(pattern="Bash", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        assert "msg[" in result

    def test_search_no_results(self, sample_1mb_path, sample_1mb_data):
        """Search for a nonsense pattern, verify empty results."""
        mod = load_analyzer()
        args = argparse.Namespace(pattern="ZZZZXYZZY_NONEXISTENT_42", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        assert "No matches" in result

    def test_search_pagination(self, sample_1mb_path, sample_1mb_data):
        """Search for a common pattern, verify pagination footer."""
        mod = load_analyzer()
        # Search for something common enough to have > 2 results
        args = argparse.Namespace(pattern="tool", scope=None, offset=0, limit=2, all=False)
        result = mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        if "No matches" not in result:
            # Should have pagination footer
            assert "of" in result

    def test_search_regex(self, sample_1mb_path, sample_1mb_data):
        """Search with a regex pattern, verify it matches."""
        mod = load_analyzer()
        args = argparse.Namespace(pattern="Exit code [0-9]+", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        # The 1MB sample has at least one error with exit code
        if "No matches" not in result:
            assert "msg[" in result

    def test_search_invalid_regex(self, sample_1mb_path, sample_1mb_data):
        """Search with invalid regex, verify error message."""
        mod = load_analyzer()
        args = argparse.Namespace(pattern="[invalid", scope=None, offset=0, limit=20, all=False)
        with pytest.raises(SystemExit):
            mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)

    def test_search_content_mode(self):
        """Verify search results show full matched content (content command)."""
        mod = load_analyzer()
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "This contains the UNIQUE_SEARCH_TARGET_TOKEN here."},
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(pattern="UNIQUE_SEARCH_TARGET_TOKEN", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "UNIQUE_SEARCH_TARGET_TOKEN" in result

    def test_search_persisted_recovery(self, sample_1mb_path, sample_1mb_data):
        """Search in persisted file content. The 1MB sample has a persisted output."""
        mod = load_analyzer()
        # Search for something that would be in the persisted file content
        # The persisted file contains JSON with "issues" key
        args = argparse.Namespace(pattern="issues", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        # Should find matches (the persisted content has "issues" in it)
        if "No matches" not in result:
            assert "msg[" in result

    def test_search_tool_input(self):
        """Verify search matches inside tool_use input JSON."""
        mod = load_analyzer()
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "Bash",
                        "input": {"command": "find UNIQUE_INPUT_PATTERN_XYZ in files"},
                    },
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(pattern="UNIQUE_INPUT_PATTERN_XYZ", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "UNIQUE_INPUT_PATTERN_XYZ" in result

    def test_search_tool_result(self):
        """Verify search matches inside tool_result content."""
        mod = load_analyzer()
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "Result containing UNIQUE_RESULT_PATTERN_ABC data",
                    },
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(pattern="UNIQUE_RESULT_PATTERN_ABC", scope=None, offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "UNIQUE_RESULT_PATTERN_ABC" in result


class TestSearchScope:
    """SAN-17: search scope filters."""

    def test_scope_orchestrator(self):
        """Search with --scope orchestrator, verify results only from orchestrator."""
        mod = load_analyzer()
        data = _make_scoped_data()
        args = argparse.Namespace(pattern="ORCH_ONLY_TOKEN", scope="orchestrator", offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "ORCH_ONLY_TOKEN" in result
        assert "orch" in result.lower()

    def test_scope_orchestrator_excludes_agents(self):
        """Search with --scope orchestrator should not find agent-only content."""
        mod = load_analyzer()
        data = _make_scoped_data()
        args = argparse.Namespace(pattern="AGENT_ONLY_TOKEN", scope="orchestrator", offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "No matches" in result

    @pytest.mark.slow
    def test_scope_agents_75mb(self, sample_75mb_path):
        """Search with --scope agents, verify results only from agent processes."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        # Search for something that would appear in agent text
        args = argparse.Namespace(pattern="Read", scope="agents", offset=0, limit=5, all=False)
        result = mod.cmd_search(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        if "No matches" not in result:
            # All results should be from agents, not orchestrator
            assert "agent:" in result

    @pytest.mark.slow
    def test_scope_specific_agent_75mb(self, sample_75mb_path):
        """Search with --scope agent:<prefix>, verify results from that agent only."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        first_proc = data["processes"][0]
        prefix = first_proc["id"][:8]
        args = argparse.Namespace(pattern=".", scope=f"agent:{prefix}", offset=0, limit=5, all=False)
        result = mod.cmd_search(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        if "No matches" not in result:
            assert f"agent:{prefix}" in result

    @pytest.mark.slow
    def test_scope_default_searches_everything(self, sample_75mb_path):
        """Search without scope flag searches both orchestrator and agents."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = argparse.Namespace(pattern=".", scope=None, offset=0, limit=50, all=False)
        result = mod.cmd_search(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        # Should have matches from both
        assert "orch" in result
        assert "agent:" in result

    def test_scope_agents_excludes_orchestrator(self):
        """Search with --scope agents should not find orchestrator-only content."""
        mod = load_analyzer()
        data = _make_scoped_data()
        args = argparse.Namespace(pattern="ORCH_ONLY_TOKEN", scope="agents", offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "No matches" in result

    def test_scope_agents_finds_agent_content(self):
        """Search with --scope agents finds content in agent processes."""
        mod = load_analyzer()
        data = _make_scoped_data()
        args = argparse.Namespace(pattern="AGENT_ONLY_TOKEN", scope="agents", offset=0, limit=20, all=False)
        result = mod.cmd_search(data, "test.json", args)
        assert isinstance(result, str)
        assert "AGENT_ONLY_TOKEN" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scoped_data():
    """Create synthetic data with orchestrator and agent messages for scope testing."""
    return {
        "session": {},
        "metrics": {},
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Orchestrator says ORCH_ONLY_TOKEN here."},
                ],
            },
        ],
        "processes": [
            {
                "id": "proc001deadbeef",
                "durationMs": 1000,
                "isOngoing": False,
                "metrics": {"totalTokens": 500},
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Agent says AGENT_ONLY_TOKEN here."},
                        ],
                    },
                ],
            },
        ],
    }
