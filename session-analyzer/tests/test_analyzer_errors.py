"""Tests for error detection: SAN-12, SAN-13, SAN-22."""
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
