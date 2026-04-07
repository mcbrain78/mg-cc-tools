"""Tests for overview command: SAN-02, SAN-03, SAN-18, SAN-23, SAN-24."""
import re
import subprocess
import sys

import pytest

from conftest import load_analyzer


class TestLoadSession:
    """SAN-02: load_session drops chunks and validates keys."""

    def test_load_drops_chunks(self, sample_1mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_1mb_path))
        assert "chunks" not in data
        for key in ("session", "messages", "processes", "metrics"):
            assert key in data


class TestOverviewSections:
    """SAN-03: overview output contains expected sections."""

    def test_overview_output_sections(self, sample_1mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_1mb_path))
        args = _make_overview_args()
        output = mod.cmd_overview(data, str(sample_1mb_path), args)
        # Verify key section headers exist
        assert "Session" in output
        assert "Timeline" in output
        assert "Orchestrator" in output
        # Error section (either "Errors" header or error count)
        assert "Error" in output
        assert "Persisted" in output


class TestContextualCommands:
    """SAN-23: overview omits agent commands when no agents."""

    def test_overview_no_agents_omits_agent_commands(self, sample_1mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_1mb_path))
        args = _make_overview_args()
        output = mod.cmd_overview(data, str(sample_1mb_path), args)
        assert "agent-list" not in output.lower()
        assert "agent <" not in output.lower()

    @pytest.mark.slow
    def test_overview_with_agents_includes_agent_commands(self, sample_75mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        args = _make_overview_args()
        output = mod.cmd_overview(data, str(sample_75mb_path), args)
        # Agent commands should be present
        assert "agent-list" in output.lower() or "agent_list" in output.lower()


class TestNoAnsi:
    """SAN-18: no ANSI escape codes in output."""

    def test_no_ansi(self, sample_1mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_1mb_path))
        args = _make_overview_args()
        output = mod.cmd_overview(data, str(sample_1mb_path), args)
        ansi_re = re.compile(r"\x1b\[")
        assert not ansi_re.search(output), f"ANSI escape codes found in output"


class TestDefaultCommand:
    """Default command (no subcommand) produces overview."""

    def test_overview_default_command(self, sample_1mb_path, analyzer_path):
        result = subprocess.run(
            [sys.executable, str(analyzer_path), str(sample_1mb_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout
        # Should contain overview sections
        assert "Session" in output
        assert "Timeline" in output


class TestSummaryMode:
    """SAN-24: overview is a summary command -- no full tool result content."""

    def test_summary_vs_content_mode(self, sample_1mb_path):
        mod = load_analyzer()
        data = mod.load_session(str(sample_1mb_path))
        args = _make_overview_args()
        output = mod.cmd_overview(data, str(sample_1mb_path), args)
        # Overview should NOT contain raw tool result content (e.g., full file reads)
        # Check that no single line is excessively long (would indicate dumped content)
        for line in output.split("\n"):
            assert len(line) < 500, f"Line too long for summary mode ({len(line)} chars)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_overview_args():
    """Create a minimal args namespace for cmd_overview."""
    import argparse
    return argparse.Namespace(command="overview")
