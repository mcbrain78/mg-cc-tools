#!/usr/bin/env python3
"""PreToolUse hook that intercepts trigger.py execution for CC regression testing.

When a Bash command containing 'cc-regression-test' and 'trigger.py' is detected,
sleeps 10 seconds (simulating evaluation), then returns permissionDecision: "ask"
so the user sees an approval prompt. All other commands pass through.
"""
import json
import sys
import time


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name == "Bash" and "cc-regression-test" in command and "trigger.py" in command:
        time.sleep(10)
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "CC regression test: hook interception confirmed. "
                    "Approve to continue test."
                ),
            }
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
