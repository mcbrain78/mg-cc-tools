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


# ---------------------------------------------------------------------------
# Tests — Wave grouping
# ---------------------------------------------------------------------------

class TestWaveGrouping:
    """Test _group_processes_by_wave directly."""

    def _load_fn(self):
        mod = load_exporter()
        return mod._group_processes_by_wave

    def _make_messages_with_agent_calls(self, *wave_descs):
        """Build orchestrator messages. Each arg is a list of Agent descriptions for one wave."""
        msgs = []
        for descs in wave_descs:
            tool_calls = [
                {"name": "Agent", "input": {"description": d}, "id": f"tc_{i}"}
                for i, d in enumerate(descs)
            ]
            msgs.append({
                "role": "assistant",
                "toolCalls": tool_calls,
            })
        return msgs

    def _make_proc(self, agent_id, description):
        return {"id": agent_id, "description": description, "messages": [], "metrics": {}}

    def test_parallel_agents_same_wave(self):
        """Two Agent calls in the same message → one wave with both processes."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(
            ["scan alpha", "scan beta"],
        )
        processes = [
            self._make_proc("p1", "general-purpose: scan alpha"),
            self._make_proc("p2", "general-purpose: scan beta"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 1
        assert len(waves[0]) == 2
        assert waves[0][0]["id"] == "p1"
        assert waves[0][1]["id"] == "p2"

    def test_sequential_agents_separate_waves(self):
        """Agent calls in different messages → separate waves."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(
            ["task A"],
            ["task B"],
        )
        processes = [
            self._make_proc("p1", "general-purpose: task A"),
            self._make_proc("p2", "general-purpose: task B"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 2
        assert len(waves[0]) == 1
        assert waves[0][0]["id"] == "p1"
        assert len(waves[1]) == 1
        assert waves[1][0]["id"] == "p2"

    def test_unmatched_processes_in_final_group(self):
        """Processes with no matching Agent call go into a trailing group."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(
            ["task A"],
        )
        processes = [
            self._make_proc("p1", "general-purpose: task A"),
            self._make_proc("p2", "general-purpose: orphan task"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 2
        assert waves[0][0]["id"] == "p1"
        assert waves[1][0]["id"] == "p2"

    def test_wave_numbering_sequential(self):
        """Three separate waves should be numbered 1, 2, 3."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(
            ["task A"],
            ["task B"],
            ["task C"],
        )
        processes = [
            self._make_proc("p1", "general-purpose: task A"),
            self._make_proc("p2", "general-purpose: task B"),
            self._make_proc("p3", "general-purpose: task C"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 3
        # Each wave has exactly one process
        for w in waves:
            assert len(w) == 1

    def test_no_agent_calls_all_unmatched(self):
        """When orchestrator has no Agent calls, all processes are unmatched."""
        group = self._load_fn()
        messages = [{"role": "assistant", "toolCalls": [
            {"name": "Bash", "input": {"command": "ls"}, "id": "tc_1"},
        ]}]
        processes = [
            self._make_proc("p1", "general-purpose: task A"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 1
        assert waves[0][0]["id"] == "p1"

    def test_empty_processes(self):
        """No processes → no waves."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(["task A"])
        waves = group(messages, [])
        assert waves == []

    def test_mixed_waves_and_unmatched(self):
        """Two waves + one orphan → 3 groups total."""
        group = self._load_fn()
        messages = self._make_messages_with_agent_calls(
            ["alpha", "beta"],
            ["gamma"],
        )
        processes = [
            self._make_proc("p1", "general-purpose: alpha"),
            self._make_proc("p2", "general-purpose: beta"),
            self._make_proc("p3", "general-purpose: gamma"),
            self._make_proc("p4", "general-purpose: orphan"),
        ]
        waves = group(messages, processes)
        assert len(waves) == 3
        assert [p["id"] for p in waves[0]] == ["p1", "p2"]
        assert [p["id"] for p in waves[1]] == ["p3"]
        assert [p["id"] for p in waves[2]] == ["p4"]


class TestWaveGroupingIntegration:
    """Test that wave tags appear in actual md-subagent output."""

    def _make_session_with_agents(self, tmp_path, wave_specs):
        """Create a JSONL session with subagent files.

        wave_specs: list of lists of descriptions, e.g. [["task A", "task B"], ["task C"]]
        """
        # Build orchestrator entries
        entries = [_make_user_entry()]
        agent_idx = 0
        for wave in wave_specs:
            # One assistant message per wave, with all Agent tool calls
            tool_use_blocks = []
            for desc in wave:
                tool_use_blocks.append({
                    "type": "tool_use",
                    "id": f"tu_agent_{agent_idx}",
                    "name": "Agent",
                    "input": {"description": desc},
                })
                agent_idx += 1
            entries.append(_make_assistant_entry(
                content=tool_use_blocks,
                uuid=f"a_wave_{agent_idx}",
                request_id=f"req_wave_{agent_idx}",
            ))

        # Write orchestrator JSONL
        jsonl_path = tmp_path / "sess-1.jsonl"
        with open(jsonl_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        # Create subagent dir: <stem>/subagents/agent-<id>.jsonl
        subagents_dir = tmp_path / "sess-1" / "subagents"
        subagents_dir.mkdir(parents=True)

        agent_idx = 0
        for wave in wave_specs:
            for desc in wave:
                agent_id = f"agent-{agent_idx:03d}"
                # Write metadata
                meta_path = subagents_dir / f"{agent_id}.meta.json"
                meta_path.write_text(json.dumps({
                    "agentType": "general-purpose",
                    "description": desc,
                }))
                # Write agent JSONL (minimal)
                agent_jsonl = subagents_dir / f"{agent_id}.jsonl"
                agent_entries = [
                    _make_user_entry(content=f"Task: {desc}", uuid=f"au_{agent_idx}"),
                    _make_assistant_entry(
                        content=[{"type": "text", "text": f"Done: {desc}"}],
                        uuid=f"aa_{agent_idx}",
                        parent=f"au_{agent_idx}",
                        request_id=f"req_sub_{agent_idx}",
                    ),
                ]
                with open(agent_jsonl, "w") as f:
                    for e in agent_entries:
                        f.write(json.dumps(e) + "\n")
                agent_idx += 1

        return jsonl_path

    def test_wave_tags_in_output(self, tmp_path):
        """Parallel agents produce <wave> tags in md-subagent output."""
        mod = load_exporter()
        jsonl_path = self._make_session_with_agents(tmp_path, [
            ["scan alpha", "scan beta"],
            ["scan gamma"],
        ])
        output_path = tmp_path / "out.md"
        mod.main(["--transcript", str(jsonl_path), "--format", "md-subagent", "--output", str(output_path)])
        output = output_path.read_text()

        assert '<wave n="1">' in output
        assert '<wave n="2">' in output
        assert output.count("<wave") == 2
        assert output.count("</wave>") == 2

    def test_wave_column_in_session_meta(self, tmp_path):
        """Session-meta agent table includes Wave column."""
        mod = load_exporter()
        jsonl_path = self._make_session_with_agents(tmp_path, [
            ["task A"],
            ["task B"],
        ])
        output_path = tmp_path / "out.md"
        mod.main(["--transcript", str(jsonl_path), "--format", "md-subagent", "--output", str(output_path)])
        output = output_path.read_text()

        assert "| Wave | ID |" in output
        # Wave numbers should appear in table rows
        assert "| 1 |" in output
        assert "| 2 |" in output
