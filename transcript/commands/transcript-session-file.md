---
name: transcript-session-file
description: Print the JSONL transcript path for this session
allowed-tools: Bash
---

# /mg:transcript-session-file

Print the JSONL transcript file path for the current session.

Use this to get the path, then pass it to `/mg:transcript-export` in a different session for clean cross-session export.

## Protocol

Run:
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py --print-transcript-path
```

Echo the output path to the user verbatim.
