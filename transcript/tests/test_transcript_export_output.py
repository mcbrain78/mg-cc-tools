"""Tests for JSON and Markdown export output."""
import json
from pathlib import Path


from conftest import load_exporter, load_analyzer, load_compactor


# ---------------------------------------------------------------------------
# Fixtures — synthetic JSONL sessions
# ---------------------------------------------------------------------------

def _make_minimal_session(tmp_path):
    """Create a minimal JSONL session and return (path, entries)."""
    entries = [
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": "What is 2+2?"},
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-001",
            "version": "2.1.0",
            "userType": "external",
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "timestamp": "2026-01-01T00:00:01.000Z",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Simple math."},
                    {"type": "text", "text": "The answer is 4."},
                ],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 50,
                },
                "model": "claude-opus-4-6",
            },
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-001",
            "version": "2.1.0",
            "userType": "external",
        },
    ]
    path = tmp_path / "test-session-001.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path, entries


def _make_toolcall_session(tmp_path):
    """Create a session with tool calls and results."""
    entries = [
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": "List files"},
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-002",
            "version": "2.1.0",
            "userType": "external",
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "timestamp": "2026-01-01T00:00:01.000Z",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me list files."},
                    {"type": "tool_use", "id": "tool_1", "name": "Bash", "input": {"command": "ls"}},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 15, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                "model": "claude-opus-4-6",
            },
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-002",
            "version": "2.1.0",
            "userType": "external",
        },
        {
            "type": "user",
            "uuid": "u2",
            "parentUuid": "a1",
            "timestamp": "2026-01-01T00:00:02.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool_1", "content": "file1.txt\nfile2.txt", "is_error": False},
                ],
            },
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-002",
            "version": "2.1.0",
            "userType": "external",
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "parentUuid": "u2",
            "timestamp": "2026-01-01T00:00:03.000Z",
            "requestId": "req_002",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Found 2 files: file1.txt, file2.txt"}],
                "usage": {"input_tokens": 3, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                "model": "claude-opus-4-6",
            },
            "cwd": "/tmp/test-project",
            "gitBranch": "main",
            "isSidechain": False,
            "sessionId": "test-session-002",
            "version": "2.1.0",
            "userType": "external",
        },
    ]
    path = tmp_path / "test-session-002.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path, entries


# ---------------------------------------------------------------------------
# Tests — JSON output
# ---------------------------------------------------------------------------

class TestJsonOutput:

    def test_build_session_detail_structure(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        assert "session" in detail
        assert "messages" in detail
        assert "chunks" in detail
        assert "processes" in detail
        assert "metrics" in detail
        assert detail["chunks"] == []

    def test_session_metadata(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        session = detail["session"]
        assert session["id"] == "test-session-001"
        assert session["gitBranch"] == "main"
        assert session["messageCount"] == 2
        assert session["hasSubagents"] is False

    def test_messages_count(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        assert len(detail["messages"]) == 2

    def test_metrics_computed(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        metrics = detail["metrics"]
        assert metrics["inputTokens"] == 5
        assert metrics["outputTokens"] == 10
        assert metrics["cacheReadTokens"] == 100
        assert metrics["cacheCreationTokens"] == 50
        assert metrics["totalTokens"] == 165

    def test_json_export_roundtrip(self, tmp_path):
        """Export to JSON and verify it can be read back."""
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.json")
        mod.export_json(detail, output_path)
        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded["session"]["id"] == "test-session-001"
        assert len(loaded["messages"]) == 2

    def test_toolcall_messages(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_toolcall_session(tmp_path)
        detail = mod.build_session_detail(path)
        messages = detail["messages"]
        # 4 messages: user, assistant+tool, user+tool_result, assistant
        assert len(messages) == 4
        # Check tool calls on assistant message
        assert len(messages[1]["toolCalls"]) == 1
        assert messages[1]["toolCalls"][0]["name"] == "Bash"
        # Check tool results on user message
        assert len(messages[2]["toolResults"]) == 1
        assert messages[2]["toolResults"][0]["toolUseId"] == "tool_1"


# ---------------------------------------------------------------------------
# Tests — Analyzer compatibility
# ---------------------------------------------------------------------------

class TestAnalyzerCompatibility:
    """Verify JSON output passes analyzer's load_session validation."""

    def test_json_passes_analyzer_load(self, tmp_path):
        exporter = load_exporter()
        analyzer = load_analyzer()

        path, _ = _make_minimal_session(tmp_path)
        detail = exporter.build_session_detail(path)
        output_path = str(tmp_path / "output.json")
        exporter.export_json(detail, output_path)

        # This should not raise or sys.exit
        data = analyzer.load_session(output_path)
        assert "session" in data
        assert "messages" in data
        assert "processes" in data
        assert "metrics" in data

    def test_json_passes_compactor_validate(self, tmp_path):
        exporter = load_exporter()
        compactor = load_compactor()

        path, _ = _make_minimal_session(tmp_path)
        detail = exporter.build_session_detail(path)
        output_path = str(tmp_path / "output.json")
        exporter.export_json(detail, output_path)

        with open(output_path) as f:
            data = json.load(f)
        # validate_schema should not sys.exit
        compactor.validate_schema(data)


# ---------------------------------------------------------------------------
# Tests — Markdown output
# ---------------------------------------------------------------------------

class TestMarkdownOutput:

    def test_markdown_has_header(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "# Session Export" in content
        assert "test-session-001" in content

    def test_markdown_has_metrics(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "## Metrics" in content
        assert "### Token Usage" in content

    def test_markdown_has_conversation(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "## Conversation" in content
        assert "### User (Turn 1)" in content
        assert "### Assistant (Turn 2)" in content
        assert "What is 2+2?" in content
        assert "The answer is 4." in content

    def test_markdown_renders_thinking(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "> *Thinking:*" in content
        assert "Simple math." in content

    def test_markdown_renders_tool_calls(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_toolcall_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "**Tool:** `Bash`" in content
        assert '"command": "ls"' in content

    def test_markdown_renders_tool_results(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_toolcall_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "**Result:**" in content
        assert "file1.txt" in content

    def test_markdown_truncation(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_toolcall_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        # Very small truncation limit
        mod.export_markdown(detail, output_path, truncate=5)
        content = Path(output_path).read_text()
        assert "truncated" in content

    def test_markdown_token_table_single_model(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        assert "### Token Usage" in content
        assert "| Source | Input | Cache Read | Cache Write | Output | Total |" in content
        # Single model — no bold total row
        assert "| claude-opus-4-6 " in content
        assert "**Total**" not in content

    def test_markdown_token_table_with_agents(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        # Inject a byModel with both orchestrator and agents
        detail["metrics"]["byModel"] = {
            "claude-opus-4-6": {
                "inputTokens": 177, "outputTokens": 7364,
                "cacheReadTokens": 607635, "cacheCreationTokens": 74659,
                "totalTokens": 689835,
            },
            "claude-opus-4-6 (agents)": {
                "inputTokens": 5716, "outputTokens": 59135,
                "cacheReadTokens": 4947744, "cacheCreationTokens": 296717,
                "totalTokens": 5309312, "agentCount": 5,
            },
        }
        output_path = str(tmp_path / "output.md")
        mod.export_markdown(detail, output_path)
        content = Path(output_path).read_text()
        # Agent row should show count
        assert "claude-opus-4-6 (5 agents)" in content
        # Multiple sources — bold total row present
        assert "**Total**" in content


# ---------------------------------------------------------------------------
# Tests — JSON byModel
# ---------------------------------------------------------------------------

class TestJsonByModel:

    def test_json_by_model_present(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        assert "byModel" in detail["metrics"]
        by_model = detail["metrics"]["byModel"]
        assert "claude-opus-4-6" in by_model

    def test_json_by_model_sums_match(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        by_model = detail["metrics"]["byModel"]
        # Sum all model buckets
        total = sum(m["totalTokens"] for m in by_model.values())
        assert total == detail["metrics"]["totalTokens"]

    def test_json_by_model_roundtrip(self, tmp_path):
        mod = load_exporter()
        path, _ = _make_minimal_session(tmp_path)
        detail = mod.build_session_detail(path)
        output_path = str(tmp_path / "output.json")
        mod.export_json(detail, output_path)
        with open(output_path) as f:
            loaded = json.load(f)
        assert "byModel" in loaded["metrics"]
        assert "claude-opus-4-6" in loaded["metrics"]["byModel"]


# ---------------------------------------------------------------------------
# Tests — Session resolution
# ---------------------------------------------------------------------------

class TestSessionResolution:

    def test_resolve_full_uuid(self, tmp_path):
        mod = load_exporter()
        # Create a fake project directory structure
        project_dir = tmp_path / "projects" / "-tmp-test-project"
        project_dir.mkdir(parents=True)
        jsonl = project_dir / "abc12345-1234-5678-9abc-def012345678.jsonl"
        jsonl.write_text(json.dumps(_make_user_entry()) + "\n")

        # Monkey-patch CLAUDE_DIR
        original = mod.CLAUDE_DIR
        mod.CLAUDE_DIR = tmp_path / "projects"
        try:
            result = mod.resolve_session("abc12345-1234-5678-9abc-def012345678", "/tmp/test-project")
            assert result == jsonl
        finally:
            mod.CLAUDE_DIR = original

    def test_resolve_prefix(self, tmp_path):
        mod = load_exporter()
        project_dir = tmp_path / "projects" / "-tmp-test-project"
        project_dir.mkdir(parents=True)
        jsonl = project_dir / "abc12345-1234-5678-9abc-def012345678.jsonl"
        jsonl.write_text(json.dumps(_make_user_entry()) + "\n")

        original = mod.CLAUDE_DIR
        mod.CLAUDE_DIR = tmp_path / "projects"
        try:
            result = mod.resolve_session("abc12345", "/tmp/test-project")
            assert result == jsonl
        finally:
            mod.CLAUDE_DIR = original


def _make_user_entry():
    return {
        "type": "user",
        "uuid": "u1",
        "parentUuid": None,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {"role": "user", "content": "Hello"},
        "cwd": "/tmp/test-project",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "abc12345-1234-5678-9abc-def012345678",
        "version": "2.1.0",
        "userType": "external",
    }
