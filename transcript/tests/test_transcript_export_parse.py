"""Tests for JSONL parsing, deduplication, and message conversion."""
import json


from conftest import load_exporter


# ---------------------------------------------------------------------------
# Fixtures — synthetic JSONL data
# ---------------------------------------------------------------------------

def _make_user_entry(content="Hello", uuid="u1", parent=None, ts="2026-01-01T00:00:00.000Z", session_id="sess-1"):
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": ts,
        "message": {"role": "user", "content": content},
        "cwd": "/tmp/test-project",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": session_id,
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
        usage = {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}
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


def _make_progress_entry(ts="2026-01-01T00:00:00.500Z"):
    return {
        "type": "progress",
        "timestamp": ts,
        "data": {"hookName": "test"},
        "uuid": "p1",
    }


def _make_file_history_entry():
    return {
        "type": "file-history-snapshot",
        "messageId": "fh1",
        "snapshot": {"trackedFileBackups": {}},
    }


def _write_jsonl(entries, tmp_path):
    """Write entries to a JSONL file and return the path."""
    jsonl_path = tmp_path / "sess-1.jsonl"
    with open(jsonl_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return jsonl_path


# ---------------------------------------------------------------------------
# Tests — JSONL parsing
# ---------------------------------------------------------------------------

class TestParseJsonl:

    def test_parse_basic_entries(self, tmp_path):
        mod = load_exporter()
        entries = [_make_user_entry(), _make_assistant_entry()]
        path = _write_jsonl(entries, tmp_path)
        result = mod._parse_jsonl(path)
        assert len(result) == 2
        assert result[0]["type"] == "user"
        assert result[1]["type"] == "assistant"

    def test_parse_skips_blank_lines(self, tmp_path):
        mod = load_exporter()
        path = tmp_path / "test.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps(_make_user_entry()) + "\n")
            f.write("\n")
            f.write(json.dumps(_make_assistant_entry()) + "\n")
        result = mod._parse_jsonl(path)
        assert len(result) == 2

    def test_parse_skips_malformed_lines(self, tmp_path):
        mod = load_exporter()
        path = tmp_path / "test.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps(_make_user_entry()) + "\n")
            f.write("NOT VALID JSON\n")
            f.write(json.dumps(_make_assistant_entry()) + "\n")
        result = mod._parse_jsonl(path)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests — Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:

    def test_keeps_last_assistant_per_request_id(self, tmp_path):
        mod = load_exporter()
        # Three streaming entries for the same request — keep only the last
        entries = [
            _make_user_entry(),
            _make_assistant_entry(
                content=[{"type": "thinking", "thinking": "hmm"}],
                uuid="a1", request_id="req_001", ts="2026-01-01T00:00:01.000Z",
            ),
            _make_assistant_entry(
                content=[{"type": "text", "text": "partial"}],
                uuid="a2", request_id="req_001", ts="2026-01-01T00:00:02.000Z",
            ),
            _make_assistant_entry(
                content=[{"type": "text", "text": "complete answer"}],
                uuid="a3", request_id="req_001", ts="2026-01-01T00:00:03.000Z",
                usage={"input_tokens": 10, "output_tokens": 50, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            ),
        ]
        result = mod._deduplicate_by_request_id(entries)
        # Should keep: user entry + last assistant entry
        assert len(result) == 2
        assert result[0]["type"] == "user"
        assert result[1]["uuid"] == "a3"

    def test_keeps_all_for_different_request_ids(self, tmp_path):
        mod = load_exporter()
        entries = [
            _make_user_entry(),
            _make_assistant_entry(uuid="a1", request_id="req_001"),
            _make_user_entry(uuid="u2", content="next", ts="2026-01-01T00:00:05.000Z"),
            _make_assistant_entry(uuid="a2", request_id="req_002", ts="2026-01-01T00:00:06.000Z"),
        ]
        result = mod._deduplicate_by_request_id(entries)
        assert len(result) == 4

    def test_keeps_non_assistant_entries(self, tmp_path):
        mod = load_exporter()
        entries = [
            _make_file_history_entry(),
            _make_user_entry(),
            _make_progress_entry(),
            _make_assistant_entry(),
            _make_system_entry(),
        ]
        result = mod._deduplicate_by_request_id(entries)
        # All non-assistant + 1 assistant = 5
        assert len(result) == 5

    def test_merges_parallel_tool_calls_same_request_id(self, tmp_path):
        """Parallel tool calls (e.g. 3 Agent spawns) share a requestId but have
        distinct tool_use blocks.  All must be preserved after deduplication."""
        mod = load_exporter()
        entries = [
            _make_user_entry(),
            # Three separate JSONL entries for the same API response,
            # each containing one tool_use block with a unique ID.
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_1", "name": "Agent", "input": {"description": "agent 1"}}],
                uuid="a1", request_id="req_parallel", ts="2026-01-01T00:00:01.000Z",
                usage={"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            ),
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_2", "name": "Agent", "input": {"description": "agent 2"}}],
                uuid="a2", request_id="req_parallel", ts="2026-01-01T00:00:01.100Z",
                usage={"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            ),
            _make_assistant_entry(
                content=[{"type": "tool_use", "id": "tu_3", "name": "Agent", "input": {"description": "agent 3"}}],
                uuid="a3", request_id="req_parallel", ts="2026-01-01T00:00:01.200Z",
                usage={"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            ),
        ]
        result = mod._deduplicate_by_request_id(entries)
        # Should keep: user + 1 merged assistant entry
        assert len(result) == 2
        merged = result[1]
        assert merged["type"] == "assistant"
        # All three tool_use blocks must be in the merged content
        content = merged["message"]["content"]
        tool_ids = [b["id"] for b in content if b.get("type") == "tool_use"]
        assert tool_ids == ["tu_1", "tu_2", "tu_3"]
        # Usage comes from the last entry
        assert merged["message"]["usage"]["input_tokens"] == 5


# ---------------------------------------------------------------------------
# Tests — Entry to message conversion
# ---------------------------------------------------------------------------

class TestEntryToMessage:

    def test_user_message_text(self):
        mod = load_exporter()
        entry = _make_user_entry(content="Hello world")
        msg = mod._entry_to_message(entry)
        assert msg is not None
        assert msg["role"] == "user"
        assert msg["content"] == "Hello world"
        assert msg["uuid"] == "u1"

    def test_assistant_message_with_tool_calls(self):
        mod = load_exporter()
        content = [
            {"type": "text", "text": "Let me check."},
            {"type": "tool_use", "id": "tool_1", "name": "Bash", "input": {"command": "ls"}},
        ]
        entry = _make_assistant_entry(content=content)
        msg = mod._entry_to_message(entry)
        assert msg is not None
        assert msg["role"] == "assistant"
        assert len(msg["toolCalls"]) == 1
        assert msg["toolCalls"][0]["name"] == "Bash"
        assert msg["toolCalls"][0]["id"] == "tool_1"

    def test_user_message_with_tool_results(self):
        mod = load_exporter()
        content = [
            {"type": "tool_result", "tool_use_id": "tool_1", "content": "file.txt", "is_error": False},
        ]
        entry = _make_user_entry(content=content)
        msg = mod._entry_to_message(entry)
        assert msg is not None
        assert len(msg["toolResults"]) == 1
        assert msg["toolResults"][0]["toolUseId"] == "tool_1"
        assert msg["toolResults"][0]["isError"] is False

    def test_system_message(self):
        mod = load_exporter()
        entry = _make_system_entry(content="compacted", subtype="context_compaction")
        msg = mod._entry_to_message(entry)
        assert msg is not None
        assert msg["role"] == "system"
        assert msg["subtype"] == "context_compaction"

    def test_skips_progress_entries(self):
        mod = load_exporter()
        entry = _make_progress_entry()
        msg = mod._entry_to_message(entry)
        assert msg is None

    def test_skips_file_history_entries(self):
        mod = load_exporter()
        entry = _make_file_history_entry()
        msg = mod._entry_to_message(entry)
        assert msg is None

    def test_preserves_usage_data(self):
        mod = load_exporter()
        usage = {"input_tokens": 5, "output_tokens": 20, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}
        entry = _make_assistant_entry(usage=usage)
        msg = mod._entry_to_message(entry)
        assert msg["usage"] == usage

    def test_preserves_model(self):
        mod = load_exporter()
        entry = _make_assistant_entry(model="claude-sonnet-4-5-20250514")
        msg = mod._entry_to_message(entry)
        assert msg["model"] == "claude-sonnet-4-5-20250514"


# ---------------------------------------------------------------------------
# Tests — Metrics computation
# ---------------------------------------------------------------------------

class TestMetrics:

    def test_aggregate_tokens(self):
        mod = load_exporter()
        messages = [
            {"usage": {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}, "timestamp": "2026-01-01T00:00:00.000Z"},
            {"usage": {"input_tokens": 3, "output_tokens": 20, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 0}, "timestamp": "2026-01-01T00:00:10.000Z"},
            {"timestamp": "2026-01-01T00:00:05.000Z"},  # no usage — should not crash
        ]
        metrics = mod._compute_metrics(messages)
        assert metrics["inputTokens"] == 8
        assert metrics["outputTokens"] == 30
        assert metrics["cacheReadTokens"] == 300
        assert metrics["cacheCreationTokens"] == 50
        assert metrics["totalTokens"] == 388
        assert metrics["messageCount"] == 3

    def test_duration_from_timestamps(self):
        mod = load_exporter()
        messages = [
            {"timestamp": "2026-01-01T00:00:00.000Z", "usage": {}},
            {"timestamp": "2026-01-01T00:05:00.000Z", "usage": {}},
        ]
        metrics = mod._compute_metrics(messages)
        assert metrics["durationMs"] == 300_000  # 5 minutes

    def test_empty_messages(self):
        mod = load_exporter()
        metrics = mod._compute_metrics([])
        assert metrics["totalTokens"] == 0
        assert metrics["durationMs"] == 0
        assert metrics["messageCount"] == 0


# ---------------------------------------------------------------------------
# Tests — Per-model metrics
# ---------------------------------------------------------------------------

class TestMetricsByModel:

    def test_single_model(self):
        mod = load_exporter()
        messages = [
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}},
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 3, "output_tokens": 20, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 0}},
        ]
        result = mod._compute_metrics_by_model(messages)
        assert len(result) == 1
        assert "claude-opus-4-6" in result
        m = result["claude-opus-4-6"]
        assert m["inputTokens"] == 8
        assert m["outputTokens"] == 30
        assert m["cacheReadTokens"] == 300
        assert m["cacheCreationTokens"] == 50
        assert m["totalTokens"] == 388

    def test_mixed_models(self):
        mod = load_exporter()
        messages = [
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
            {"model": "claude-haiku-4-5", "usage": {"input_tokens": 2, "output_tokens": 8, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
        ]
        result = mod._compute_metrics_by_model(messages)
        assert len(result) == 2
        assert result["claude-opus-4-6"]["inputTokens"] == 8
        assert result["claude-opus-4-6"]["outputTokens"] == 15
        assert result["claude-opus-4-6"]["totalTokens"] == 23
        assert result["claude-haiku-4-5"]["inputTokens"] == 2
        assert result["claude-haiku-4-5"]["totalTokens"] == 10

    def test_skips_messages_without_model(self):
        mod = load_exporter()
        messages = [
            {"usage": {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 3, "output_tokens": 7, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
        ]
        result = mod._compute_metrics_by_model(messages)
        assert len(result) == 1
        assert result["claude-opus-4-6"]["totalTokens"] == 10

    def test_skips_messages_without_usage(self):
        mod = load_exporter()
        messages = [
            {"model": "claude-opus-4-6"},
            {"model": "claude-opus-4-6", "usage": {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
        ]
        result = mod._compute_metrics_by_model(messages)
        assert result["claude-opus-4-6"]["totalTokens"] == 3

    def test_empty_messages(self):
        mod = load_exporter()
        result = mod._compute_metrics_by_model([])
        assert result == {}


# ---------------------------------------------------------------------------
# Tests — --transcript flag (direct JSONL path)
# ---------------------------------------------------------------------------

class TestTranscriptFlag:

    def test_export_with_transcript_flag(self, tmp_path):
        """Exporter works when given --transcript pointing at a JSONL file."""
        mod = load_exporter()

        entries = [
            _make_user_entry(content="Hello"),
            _make_assistant_entry(),
        ]
        jsonl_path = _write_jsonl(entries, tmp_path)
        output_path = tmp_path / "out.md"

        mod.main(["--transcript", str(jsonl_path), "--format", "md", "--output", str(output_path)])
        assert output_path.exists()
        content = output_path.read_text()
        assert "Session Export" in content

    def test_export_json_with_transcript_flag(self, tmp_path):
        mod = load_exporter()

        entries = [
            _make_user_entry(content="Hello"),
            _make_assistant_entry(),
        ]
        jsonl_path = _write_jsonl(entries, tmp_path)
        output_path = tmp_path / "out.json"

        mod.main(["--transcript", str(jsonl_path), "--format", "json", "--output", str(output_path)])
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert "session" in data
        assert "messages" in data

    def test_transcript_flag_missing_file_exits(self, tmp_path):
        mod = load_exporter()
        import pytest
        with pytest.raises(SystemExit):
            mod.main(["--transcript", "/nonexistent/file.jsonl", "--output", str(tmp_path / "o.md")])

    def test_no_args_exits(self):
        mod = load_exporter()
        import pytest
        with pytest.raises(SystemExit):
            mod.main(["--output", "/tmp/o.md"])

    def test_export_without_output_exits(self, tmp_path):
        """Normal export (no --print-transcript-path) requires --output."""
        mod = load_exporter()
        import pytest
        entries = [_make_user_entry()]
        jsonl_path = _write_jsonl(entries, tmp_path)
        with pytest.raises(SystemExit):
            mod.main(["--transcript", str(jsonl_path)])

    def test_export_md_subagent_basic_structure(self, tmp_path):
        """md-subagent format produces session-meta, orchestrator, and agent sections."""
        mod = load_exporter()

        entries = [
            _make_user_entry(content="Hello"),
            _make_assistant_entry(),
        ]
        jsonl_path = _write_jsonl(entries, tmp_path)
        output_path = tmp_path / "out.md"

        mod.main(["--transcript", str(jsonl_path), "--format", "md-subagent", "--output", str(output_path)])
        assert output_path.exists()
        content = output_path.read_text()
        assert "<session-meta>" in content
        assert "</session-meta>" in content
        assert "<orchestrator>" in content
        assert "</orchestrator>" in content


# ---------------------------------------------------------------------------
# Tests — --print-transcript-path flag
# ---------------------------------------------------------------------------

class TestPrintTranscriptPath:

    def test_prints_path_and_exits(self, tmp_path, capsys):
        """--print-transcript-path prints the resolved path without requiring --output."""
        mod = load_exporter()
        entries = [_make_user_entry()]
        jsonl_path = _write_jsonl(entries, tmp_path)

        mod.main(["--transcript", str(jsonl_path), "--print-transcript-path"])
        captured = capsys.readouterr()
        assert captured.out.strip() == str(jsonl_path)

    def test_prints_resolved_path(self, tmp_path, capsys):
        """The printed path matches the --transcript value exactly."""
        mod = load_exporter()
        entries = [_make_user_entry()]
        jsonl_path = _write_jsonl(entries, tmp_path)

        mod.main(["--transcript", str(jsonl_path), "--print-transcript-path"])
        printed = capsys.readouterr().out.strip()
        from pathlib import Path
        assert Path(printed).exists()
        assert Path(printed) == jsonl_path

    def test_no_export_performed(self, tmp_path, capsys):
        """--print-transcript-path returns early — no output file is created."""
        mod = load_exporter()
        entries = [_make_user_entry()]
        jsonl_path = _write_jsonl(entries, tmp_path)
        output_path = tmp_path / "should-not-exist.md"

        mod.main(["--transcript", str(jsonl_path), "--print-transcript-path",
                   "--output", str(output_path)])
        assert not output_path.exists()
