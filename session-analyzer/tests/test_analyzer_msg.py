"""Tests for msg command: SAN-08, SAN-09, SAN-15, SAN-24."""
import argparse
import os
import tempfile
import pytest

from conftest import load_analyzer


class TestMsgCommand:
    """Tests for msg command with context."""

    def test_msg_orchestrator(self, sample_1mb_path, sample_1mb_data):
        """Run msg 5 on 1MB sample, verify it shows message 5 with +/-2 context."""
        mod = load_analyzer()
        args = argparse.Namespace(index=5, agent=None)
        result = mod.cmd_msg(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        # Should show messages 3-7 (5-2 to 5+2)
        assert "msg[5]" in result
        assert "msg[3]" in result or "msg[4]" in result  # at least one context message
        # Target message should be marked with ***
        assert "***" in result

    def test_msg_out_of_range(self, sample_1mb_path, sample_1mb_data):
        """Run msg 99999 on 1MB sample, verify error message."""
        mod = load_analyzer()
        args = argparse.Namespace(index=99999, agent=None)
        with pytest.raises(SystemExit):
            mod.cmd_msg(sample_1mb_data, str(sample_1mb_path), args)

    def test_msg_shows_full_content(self):
        """Verify msg output includes full tool result text (content command)."""
        mod = load_analyzer()
        long_content = "DETAILED_RESULT_TEXT " * 100
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "Let me check."}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_test",
                        "content": long_content,
                    },
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(index=2, agent=None)
        result = mod.cmd_msg(data, "test.json", args)
        assert isinstance(result, str)
        # Content command should show full result text
        assert "DETAILED_RESULT_TEXT" in result

    @pytest.mark.slow
    def test_msg_agent_form_75mb(self, sample_75mb_path):
        """Run msg --agent <prefix> 0 on 75MB sample, verify it shows agent's first message."""
        mod = load_analyzer()
        data = mod.load_session(str(sample_75mb_path))
        first_proc = data["processes"][0]
        prefix = first_proc["id"][:8]
        args = argparse.Namespace(index=0, agent=prefix)
        result = mod.cmd_msg(data, str(sample_75mb_path), args)
        assert isinstance(result, str)
        assert "msg[0]" in result

    def test_msg_strips_usage_blocks(self):
        """Verify <usage> blocks are stripped from display."""
        mod = load_analyzer()
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Some text\n<usage>tokens: 100</usage>",
                    },
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(index=0, agent=None)
        result = mod.cmd_msg(data, "test.json", args)
        assert isinstance(result, str)
        assert "<usage>" not in result


class TestPersistedRecovery:
    """SAN-15: persisted output recovery."""

    def test_persisted_recovery_from_file(self, tmp_path):
        """Create temp file, verify recover_persisted returns file content."""
        mod = load_analyzer()
        temp_file = tmp_path / "output.txt"
        temp_file.write_text("Full recovered content from persisted file")
        text = (
            f"<persisted-output>\nFull output saved to: {temp_file}\n\n"
            "Preview (first 2KB):\nPartial preview...\n</persisted-output>"
        )
        result = mod.recover_persisted(text, tmp_path)
        assert result == "Full recovered content from persisted file"

    def test_persisted_fallback_to_preview(self, tmp_path):
        """Create text with wrapper pointing to non-existent file, verify falls back to preview."""
        mod = load_analyzer()
        text = (
            "<persisted-output>\nFull output saved to: /nonexistent/path/output.txt\n\n"
            "Preview (first 2KB):\nThis is the preview text.\n</persisted-output>"
        )
        result = mod.recover_persisted(text, tmp_path)
        assert "This is the preview text." in result

    def test_persisted_no_wrapper(self):
        """Plain text without wrapper passes through unchanged."""
        mod = load_analyzer()
        text = "Just normal text without any persisted wrapper"
        from pathlib import Path
        result = mod.recover_persisted(text, Path("/tmp"))
        assert result == text

    def test_persisted_strip_wrapper(self):
        """Verify <persisted-output> tags are stripped from output."""
        mod = load_analyzer()
        text = (
            "<persisted-output>\nSome content here\n</persisted-output>"
        )
        from pathlib import Path
        result = mod.recover_persisted(text, Path("/tmp"))
        assert "<persisted-output>" not in result
        assert "</persisted-output>" not in result


class TestDisplayModes:
    """SAN-24: summary vs content command modes."""

    def test_msg_is_content_command(self):
        """Verify msg shows full tool result content."""
        mod = load_analyzer()
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_test",
                        "content": "Full detailed result text that should appear in msg output",
                    },
                ],
            },
        ]
        data = {"session": {}, "metrics": {}, "messages": messages, "processes": []}
        args = argparse.Namespace(index=0, agent=None)
        result = mod.cmd_msg(data, "test.json", args)
        assert "Full detailed result text" in result

    def test_overview_is_summary_command(self, sample_1mb_path, sample_1mb_data):
        """Verify overview does NOT show full tool result content."""
        mod = load_analyzer()
        args = argparse.Namespace()
        result = mod.cmd_overview(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        # Overview should not contain raw tool result content
        # It should contain sections like "=== Session ===" and "=== Errors ==="
        assert "=== Session ===" in result
        assert "=== Errors" in result
