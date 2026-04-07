"""Tests for the inject-transcript-path PreToolUse hook."""
import json
import subprocess
import sys
from pathlib import Path

HOOK_PATH = Path(__file__).parent.parent / "hooks" / "inject-transcript-path.py"


def _run_hook(event: dict) -> dict | None:
    """Feed *event* to the hook via stdin, return parsed JSON or None."""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=5,
    )
    stdout = result.stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


# ---------------------------------------------------------------------------
# Pass-through (no output)
# ---------------------------------------------------------------------------

class TestPassThrough:

    def test_non_exporter_command(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "transcript_path": "/home/user/.claude/projects/foo/abc.jsonl",
        }
        assert _run_hook(event) is None

    def test_empty_command(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": ""},
            "transcript_path": "/home/user/.claude/projects/foo/abc.jsonl",
        }
        assert _run_hook(event) is None

    def test_missing_tool_input(self):
        event = {
            "tool_name": "Bash",
            "transcript_path": "/tmp/abc.jsonl",
        }
        assert _run_hook(event) is None

    def test_invalid_json_stdin(self):
        """Hook should exit silently on unparseable input."""
        result = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input="NOT JSON",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------

class TestInjection:

    def test_appends_transcript_flag(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 /target/.claude/transcript/cc_transcript_exporter.py --format md --output /tmp/out.md",
            },
            "transcript_path": "/home/user/.claude/projects/-home-user-myproj/abc-123.jsonl",
        }
        result = _run_hook(event)
        assert result is not None
        modified = result["hookSpecificOutput"]["updatedInput"]["command"]
        assert modified.endswith("--transcript /home/user/.claude/projects/-home-user-myproj/abc-123.jsonl")
        assert modified.startswith("python3 /target/.claude/transcript/cc_transcript_exporter.py")

    def test_preserves_other_tool_input_fields(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 /x/cc_transcript_exporter.py --format md --output /tmp/o.md",
                "timeout": 30000,
                "description": "Export transcript",
            },
            "transcript_path": "/tmp/sess.jsonl",
        }
        result = _run_hook(event)
        assert result is not None
        updated = result["hookSpecificOutput"]["updatedInput"]
        assert "--transcript" in updated["command"]
        assert updated["timeout"] == 30000
        assert updated["description"] == "Export transcript"

    def test_does_not_double_inject(self):
        """If --transcript is already present, pass through."""
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 /x/cc_transcript_exporter.py --format md --output /tmp/o.md --transcript /already/here.jsonl",
            },
            "transcript_path": "/other/path.jsonl",
        }
        assert _run_hook(event) is None


# ---------------------------------------------------------------------------
# Missing transcript_path
# ---------------------------------------------------------------------------

class TestMissingTranscriptPath:

    def test_no_transcript_path_key(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 cc_transcript_exporter.py --format md --output /tmp/o.md",
            },
        }
        assert _run_hook(event) is None

    def test_empty_transcript_path(self):
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 cc_transcript_exporter.py --format md --output /tmp/o.md",
            },
            "transcript_path": "",
        }
        assert _run_hook(event) is None
