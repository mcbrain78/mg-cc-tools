"""Tests for the md-subagent compact Markdown export format."""
import json

from conftest import load_exporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_entry(content="Hello", uuid="u1", parent=None, ts="2026-01-01T00:00:00.000Z"):
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": ts,
        "message": {"role": "user", "content": content},
        "cwd": "/tmp/test-project",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "sess-1",
        "version": "2.1.0",
        "userType": "external",
    }


def _make_assistant_entry(
    content=None, uuid="a1", parent="u1", ts="2026-01-01T00:00:01.000Z",
    request_id="req_001", usage=None, model="claude-opus-4-6",
):
    if content is None:
        content = [{"type": "text", "text": "Hi there!"}]
    if usage is None:
        usage = {"input_tokens": 5, "output_tokens": 10,
                 "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": ts,
        "requestId": request_id,
        "message": {"role": "assistant", "content": content, "usage": usage, "model": model},
        "cwd": "/tmp/test-project",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "sess-1",
        "version": "2.1.0",
        "userType": "external",
    }


def _make_system_entry(content="", subtype="turn_duration", uuid="s1", ts="2026-01-01T00:00:05.000Z"):
    return {
        "type": "system",
        "uuid": uuid,
        "parentUuid": None,
        "timestamp": ts,
        "content": content,
        "subtype": subtype,
        "cwd": "/tmp/test-project",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "sess-1",
        "version": "2.1.0",
        "userType": "external",
    }


def _make_tool_result_user_entry(tool_use_id, content, is_error=False, uuid="u2", ts="2026-01-01T00:00:02.000Z"):
    return _make_user_entry(
        content=[{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }],
        uuid=uuid,
        ts=ts,
    )


def _write_jsonl(entries, tmp_path):
    jsonl_path = tmp_path / "sess-1.jsonl"
    with open(jsonl_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return jsonl_path


def _export_md_subagent(entries, tmp_path):
    """Write entries to JSONL and export as md-subagent. Returns output text."""
    mod = load_exporter()
    jsonl_path = _write_jsonl(entries, tmp_path)
    output_path = tmp_path / "out.md"
    mod.main(["--transcript", str(jsonl_path), "--format", "md-subagent", "--output", str(output_path)])
    return output_path.read_text()


# ---------------------------------------------------------------------------
# Tests — Command template compaction
# ---------------------------------------------------------------------------

class TestCommandTemplateCompaction:

    def test_long_command_message_compacted(self, tmp_path):
        """A user message >2KB with <command-name> tag gets compacted to [command: ...]."""
        # Build a message that looks like a command template
        long_content = (
            "<command-name>/mg:health-scan</command-name>\n"
            "## Health Scan\n\n"
            + "x" * 3000
        )
        entries = [
            _make_user_entry(content=long_content),
            _make_assistant_entry(),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "[command: /mg:health-scan]" in output
        # The long content should NOT appear
        assert "x" * 100 not in output

    def test_short_user_message_not_compacted(self, tmp_path):
        """Short user messages are kept as-is."""
        entries = [
            _make_user_entry(content="Hello world"),
            _make_assistant_entry(),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "User: Hello world" in output

    def test_command_template_fallback_to_heading(self, tmp_path):
        """Falls back to ## heading when no <command-name> tag present."""
        long_content = (
            "## Auto Documentation\n\n"
            + "y" * 3000
        )
        entries = [
            _make_user_entry(content=long_content),
            _make_assistant_entry(),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "[command: Auto Documentation]" in output


# ---------------------------------------------------------------------------
# Tests — Agent spawn rendering
# ---------------------------------------------------------------------------

class TestAgentSpawnRendering:

    def test_agent_tool_call_rendered_as_one_liner(self, tmp_path):
        """Agent tool_use blocks render as Agent(description)."""
        content = [
            {"type": "tool_use", "id": "tu_1", "name": "Agent",
             "input": {"description": "scan for dead code"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Agent(scan for dead code)" in output


# ---------------------------------------------------------------------------
# Tests — Bash result preservation
# ---------------------------------------------------------------------------

class TestBashResultPreservation:

    def test_bash_output_preserved(self, tmp_path):
        """Bash tool results keep their output (signal for analysis)."""
        content_assistant = [
            {"type": "tool_use", "id": "tu_bash", "name": "Bash",
             "input": {"command": "python3 scanner.py"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_bash", "Found 3 issues\nDone"),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Found 3 issues" in output
        assert "Bash(python3 scanner.py)" in output


# ---------------------------------------------------------------------------
# Tests — Read result compaction
# ---------------------------------------------------------------------------

class TestReadResultCompaction:

    def test_read_result_shows_size_only(self, tmp_path):
        """Read tool results are replaced with [N chars]."""
        content_assistant = [
            {"type": "tool_use", "id": "tu_read", "name": "Read",
             "input": {"file_path": "/tmp/foo.py"}},
        ]
        file_content = "x" * 5000
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_read", file_content),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Read(/tmp/foo.py)" in output
        assert "[5,000 chars]" in output
        # The actual file content should NOT appear
        assert "x" * 100 not in output


# ---------------------------------------------------------------------------
# Tests — Error preservation
# ---------------------------------------------------------------------------

class TestErrorPreservation:

    def test_error_result_shown_in_full(self, tmp_path):
        """Error results are shown with ERROR: prefix."""
        content_assistant = [
            {"type": "tool_use", "id": "tu_bash", "name": "Bash",
             "input": {"command": "false"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_bash", "command failed: exit 1", is_error=True),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "ERROR: command failed: exit 1" in output


# ---------------------------------------------------------------------------
# Tests — Thinking blocks omitted
# ---------------------------------------------------------------------------

class TestThinkingOmitted:

    def test_thinking_blocks_not_in_output(self, tmp_path):
        """Thinking blocks are omitted entirely."""
        content = [
            {"type": "thinking", "thinking": "Let me think about this carefully..."},
            {"type": "text", "text": "Here is my answer."},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "think about this carefully" not in output
        assert "Here is my answer." in output


# ---------------------------------------------------------------------------
# Tests — System messages omitted
# ---------------------------------------------------------------------------

class TestSystemMessagesOmitted:

    def test_system_messages_not_in_output(self, tmp_path):
        """System messages (context compaction, turn_duration) are omitted."""
        entries = [
            _make_user_entry(),
            _make_assistant_entry(),
            _make_system_entry(content="Turn took 5.2s", subtype="turn_duration"),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Turn took" not in output
        assert "turn_duration" not in output


# ---------------------------------------------------------------------------
# Tests — Parallel agent calls (dedup fix integration)
# ---------------------------------------------------------------------------

class TestParallelAgentCalls:

    def test_all_parallel_agents_visible(self, tmp_path):
        """Three Agent spawns with the same requestId all appear in output."""
        entries = [
            _make_user_entry(),
            # Three parallel Agent tool_use entries (same requestId, different tool_use IDs)
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_a1", "name": "Agent",
                          "input": {"description": "scanner alpha"}}],
                uuid="a1", request_id="req_parallel", ts="2026-01-01T00:00:01.000Z",
            ),
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_a2", "name": "Agent",
                          "input": {"description": "scanner beta"}}],
                uuid="a2", request_id="req_parallel", ts="2026-01-01T00:00:01.100Z",
            ),
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_a3", "name": "Agent",
                          "input": {"description": "scanner gamma"}}],
                uuid="a3", request_id="req_parallel", ts="2026-01-01T00:00:01.200Z",
            ),
        ]
        output = _export_md_subagent(entries, tmp_path)
        # All three should appear
        assert "Agent(scanner alpha)" in output
        assert "Agent(scanner beta)" in output
        assert "Agent(scanner gamma)" in output


# ---------------------------------------------------------------------------
# Tests — Write/Edit result rendering
# ---------------------------------------------------------------------------

class TestWriteEditResults:

    def test_write_result_shows_ok(self, tmp_path):
        """Write tool results render as → ok."""
        content_assistant = [
            {"type": "tool_use", "id": "tu_write", "name": "Write",
             "input": {"file_path": "/tmp/out.py"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_write", "File written successfully"),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Write(/tmp/out.py)" in output
        assert "→ ok" in output

    def test_edit_error_shows_error(self, tmp_path):
        """Edit tool error results show ERROR:."""
        content_assistant = [
            {"type": "tool_use", "id": "tu_edit", "name": "Edit",
             "input": {"file_path": "/tmp/foo.py"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_edit", "old_string not found", is_error=True),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Edit(/tmp/foo.py)" in output
        assert "ERROR: old_string not found" in output


# ---------------------------------------------------------------------------
# Tests — Grep/Glob tool rendering
# ---------------------------------------------------------------------------

class TestGrepGlobRendering:

    def test_grep_with_path(self, tmp_path):
        content_assistant = [
            {"type": "tool_use", "id": "tu_grep", "name": "Grep",
             "input": {"pattern": "def main", "path": "/tmp/src"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_grep", "file1.py:10:def main():\nfile2.py:5:def main():"),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Grep(def main, /tmp/src)" in output

    def test_glob_pattern_only(self, tmp_path):
        content_assistant = [
            {"type": "tool_use", "id": "tu_glob", "name": "Glob",
             "input": {"pattern": "**/*.py"}},
        ]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content_assistant),
            _make_tool_result_user_entry("tu_glob", "a.py\nb.py\nc.py"),
        ]
        output = _export_md_subagent(entries, tmp_path)
        assert "Glob(**/*.py)" in output
        # Result should be size, not the actual file list
        assert "[" in output and "chars]" in output


# ---------------------------------------------------------------------------
# Tests — Assistant text truncation
# ---------------------------------------------------------------------------

class TestAssistantTextTruncation:

    def test_long_text_truncated(self, tmp_path):
        long_text = "A" * 300
        content = [{"type": "text", "text": long_text}]
        entries = [
            _make_user_entry(),
            _make_assistant_entry(content=content),
        ]
        output = _export_md_subagent(entries, tmp_path)
        # Should have truncation indicator
        assert "..." in output
        # Should not have the full text
        assert "A" * 300 not in output
        # Should have the first 200 chars
        assert "A" * 200 in output
