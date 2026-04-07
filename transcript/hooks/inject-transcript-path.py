#!/usr/bin/env python3
"""PreToolUse:Bash hook that injects --transcript into exporter commands.

Claude Code passes ``transcript_path`` (the full JSONL path for the current
session) to every hook via stdin JSON.  When the Bash command contains an
invocation of ``cc_transcript_exporter.py``, this hook appends
``--transcript <path>`` so the exporter can skip all session-ID resolution.

Non-exporter commands pass through silently (no output → no modification).
"""
import json
import sys


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    if "cc_transcript_exporter.py" not in command:
        return

    transcript_path = event.get("transcript_path")
    if not transcript_path:
        return

    # Already has --transcript — don't double-inject
    if "--transcript" in command:
        return

    tool_input["command"] = f"{command} --transcript {transcript_path}"

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": tool_input,
        }
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
