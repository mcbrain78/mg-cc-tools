"""Tests for `_classify_agent_status` — fixes false positives where:
- "ERROR" / "FAILED" appear as data values in narrative text (not as
  failure announcements) and were caught by an unanchored substring match.
- An agent had recoverable tool errors early in its run but completed
  cleanly: the original code returned "failed" on any historical is_error,
  contradicting its own comment ("last tool_result").
"""
from conftest import load_analyzer


# ---------------------------------------------------------------------------
# Helpers — mirror the patterns in test_transcript_analyze_errors.py
# ---------------------------------------------------------------------------

def _assistant_msg(text):
    return {
        "role": "assistant",
        "type": "assistant",
        "content": [{"type": "text", "text": text}],
    }


def _tool_result_msg(text="ok", is_error=False):
    block: dict[str, object] = {"type": "tool_result", "tool_use_id": "toolu_test", "content": text}
    if is_error:
        block["is_error"] = True
    return {"role": "user", "type": "user", "content": [block]}


def _multi_tool_result_msg(blocks):
    """blocks: list of (text, is_error) tuples — produces one user message
    with multiple tool_result siblings (parallel-batch case)."""
    content = []
    for i, (text, is_error) in enumerate(blocks):
        b = {"type": "tool_result", "tool_use_id": f"toolu_{i}", "content": text}
        if is_error:
            b["is_error"] = True
        content.append(b)
    return {"role": "user", "type": "user", "content": content}


# ---------------------------------------------------------------------------
# Bug 1 regressions — substring → anchored
# ---------------------------------------------------------------------------

class TestErrorAsDataValue:
    """Bug 1: 'ERROR' as a data value should not trigger 'failed'."""

    def test_error_as_enum_value_in_last_line_is_ok(self):
        """The a082a141 case from the road-runner audit-v2 session."""
        mod = load_analyzer()
        text = (
            "All sections processed.\n\n"
            "**Remaining uncleared** (8 entities, for wave 2): "
            "`version`, `absolute`, `multiple`, `error`, `none`, `zero` "
            "(enum-like values in config schema)."
        )
        assert mod._classify_agent_status([_assistant_msg(text)]) == "ok"

    def test_error_in_identifier_is_ok(self):
        mod = load_analyzer()
        text = "Defined ERROR_CODE_42 as the standard non-recoverable code."
        assert mod._classify_agent_status([_assistant_msg(text)]) == "ok"


# ---------------------------------------------------------------------------
# Bug 1 — true failure announcements still detected
# ---------------------------------------------------------------------------

class TestFailureAnnouncementsStillDetected:

    def test_markdown_header_failed_first_line(self):
        mod = load_analyzer()
        text = "# Failed\n\nThe pipeline could not complete."
        assert mod._classify_agent_status([_assistant_msg(text)]) == "failed"

    def test_bold_error_at_line_start(self):
        mod = load_analyzer()
        text = "**ERROR**: connection refused"
        assert mod._classify_agent_status([_assistant_msg(text)]) == "failed"

    def test_plan_failed_phrase(self):
        mod = load_analyzer()
        text = "PLAN FAILED: dependency resolution did not converge"
        assert mod._classify_agent_status([_assistant_msg(text)]) == "failed"


# ---------------------------------------------------------------------------
# Bug 2 regressions — recovered errors should be 'ok'
# ---------------------------------------------------------------------------

class TestRecoveredErrors:
    """Bug 2: an agent that hit an early script error and recovered should
    not be classified as failed. The four extraction agents in the
    road-runner audit-v2 session all hit this."""

    def test_early_error_then_clean_tool_result_is_ok(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Exit code 2: argument --name", is_error=True),
            _tool_result_msg("Added entity: pytest in commands/testing"),
        ]
        assert mod._classify_agent_status(messages) == "ok"

    def test_early_error_then_clean_assistant_summary_is_ok(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Exit code 2", is_error=True),
            _tool_result_msg("Added entity: ok"),
            _assistant_msg("All sections have been processed. Total: 312 entities."),
        ]
        assert mod._classify_agent_status(messages) == "ok"


# ---------------------------------------------------------------------------
# Bug 2 — terminal failures still detected
# ---------------------------------------------------------------------------

class TestTerminalToolErrors:

    def test_terminal_tool_error_is_failed(self):
        mod = load_analyzer()
        messages = [
            _tool_result_msg("Added entity: ok"),
            _tool_result_msg("Exit code 1: catastrophic failure", is_error=True),
        ]
        assert mod._classify_agent_status(messages) == "failed"

    def test_parallel_batch_one_error_is_failed(self):
        mod = load_analyzer()
        messages = [
            _multi_tool_result_msg([
                ("ok", False),
                ("Exit code 2: bad arg", True),
            ]),
        ]
        assert mod._classify_agent_status(messages) == "failed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_messages_is_ok(self):
        mod = load_analyzer()
        assert mod._classify_agent_status([]) == "ok"
