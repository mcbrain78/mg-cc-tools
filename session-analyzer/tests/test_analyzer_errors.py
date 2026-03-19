"""Tests for error detection: SAN-12, SAN-13, SAN-22, and errors command."""
import argparse
import pytest

from conftest import load_analyzer


class TestErrorDetection:
    """SAN-12: curated error detection patterns."""

    def test_is_error_flag_detected(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Something went wrong", is_error=True),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) >= 1

    def test_traceback_detected(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg(
                "Traceback (most recent call last):\n"
                '  File "test.py", line 1, in <module>\n'
                "KeyError: 'foo'"
            ),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) >= 1

    def test_exit_code_detected(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Running tests...\nExit code 1\nTest failed"),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) >= 1

    def test_exit_code_in_assistant_not_scanned(self):
        """Error detection only scans tool_result blocks, not assistant text."""
        mod = load_analyzer()
        messages = [
            {
                "role": "assistant",
                "type": "assistant",
                "content": [
                    {"type": "text", "text": "The command had Exit code 1 which means failure."}
                ],
            },
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) == 0

    def test_normal_tool_result_not_error(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("File created successfully at: /tmp/test.py"),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) == 0


class TestNoiseFiltering:
    """SAN-13: noise patterns excluded from error counts."""

    def test_exceeds_max_tokens_filtered(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Tool exceeds maximum allowed tokens", is_error=True),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) == 0

    def test_file_not_read_filtered(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("File has not been read yet", is_error=True),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) == 0

    def test_file_not_exist_filtered(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("File does not exist", is_error=True),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) == 0

    def test_real_error_not_filtered(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Connection refused: database unreachable", is_error=True),
        ]
        errors = mod.detect_errors(messages)
        assert len(errors) >= 1


class TestIndependentDetection:
    """SAN-22: analyzer does NOT import compactor's ERROR_MARKERS."""

    def test_analyzer_does_not_use_compactor_error_markers(self):
        mod = load_analyzer()
        import inspect
        source = inspect.getsource(mod)
        assert "ERROR_MARKERS" not in source
        assert "from cc_session_compactor" not in source
        assert "import cc_session_compactor" not in source


class TestErrorsCommand:
    """Tests for the errors command output format and pagination."""

    def test_errors_command_format(self, sample_1mb_path, sample_1mb_data):
        """Errors on 1MB sample returns expected error count with correct format."""
        mod = load_analyzer()
        args = argparse.Namespace(offset=0, limit=20, all=False)
        result = mod.cmd_errors(sample_1mb_data, str(sample_1mb_path), args)
        assert isinstance(result, str)
        # 1MB sample has 1 error
        assert "[msg[" in result
        # Error type header present
        assert any(t in result for t in ("is_error flag", "Python traceback", "Bash exit code", "Agent failure"))

    def test_errors_pagination(self):
        """Multiple errors scenario with pagination footer."""
        mod = load_analyzer()
        # Build data with 5 errors
        messages = [
            {"role": "assistant", "content": [{"type": "text", "text": f"Trying thing {i}"}]}
            for i in range(5)
            for _ in "_"  # dummy to interleave
        ]
        msgs = []
        for i in range(5):
            msgs.append({"role": "assistant", "content": [{"type": "text", "text": f"Trying thing {i}"}]})
            msgs.append(_tool_result_msg(f"Connection refused #{i}", is_error=True))
        data = {"session": {}, "metrics": {}, "messages": msgs, "processes": []}
        args = argparse.Namespace(offset=0, limit=2, all=False)
        result = mod.cmd_errors(data, "test.json", args)
        assert isinstance(result, str)
        assert "2 of 5" in result
        assert "--offset" in result

    def test_errors_content_mode(self, sample_1mb_path, sample_1mb_data):
        """Errors command shows full error text (not truncated summary like overview)."""
        mod = load_analyzer()
        args = argparse.Namespace(offset=0, limit=20, all=False)
        result = mod.cmd_errors(sample_1mb_data, str(sample_1mb_path), args)
        # Should contain more than just the 120-char truncated version
        # The full error text includes traceback lines
        assert "Traceback" in result or "Exit code" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_result_msg(text, is_error=False):
    """Create a synthetic message with a tool_result content block."""
    block = {
        "type": "tool_result",
        "tool_use_id": "toolu_test",
        "content": text,
    }
    if is_error:
        block["is_error"] = True
    return {
        "role": "user",
        "type": "user",
        "content": [block],
    }
