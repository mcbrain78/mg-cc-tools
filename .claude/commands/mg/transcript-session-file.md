---
name: transcript-session-file
description: Print the JSONL transcript path for this session
allowed-tools: Bash
---

# /mg:transcript-session-file

Print the JSONL transcript file path for the current session.

Use this to get the path, then pass it to `/mg:transcript-export` in a different session for clean cross-session export.

## Display Rule

The exporter wraps its output in `<verbatim>` tags. You MUST reproduce EVERY line between `<verbatim>` and `</verbatim>` exactly as-is in your response text. Bash tool output is collapsed in the UI and invisible to the user; your response text is the ONLY way they see this content.

## Protocol

Run:
```
python3 .claude/transcript/cc_transcript_exporter.py --print-transcript-path
```

Echo the output per the Display Rule above.
