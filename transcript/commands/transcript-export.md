---
name: transcript-export
description: Export the current Claude Code session as Markdown or JSON
allowed-tools: Bash, Read
argument-hint: "<format: md|md-subagent|json> <file-name> [transcript-file]"
---

# /mg:transcript-export

Export the current Claude Code session transcript to a file.

## Arguments

Parse `$ARGUMENTS` to extract:
- **format** (required): `md`, `md-subagent`, or `json`
- **file-path** (required): Output file path (absolute or relative to `/tmp/`)
- **transcript-file** (optional): JSONL transcript path from another session (from `/mg:transcript-session-file`)

Example: `/mg:transcript-export md /tmp/my-session.md`
Cross-session: `/mg:transcript-export md /tmp/my-session.md /path/to/other-session.jsonl`

If arguments are missing or unclear, ask the user.

## Exporter Tool

The exporter is at: `{MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py`

## Export Protocol

### Step 1: Export

Run the exporter with `--format` and `--output`. A PreToolUse hook automatically injects the `--transcript` flag with the current session's JSONL path — no session ID or project path needed.

When **transcript-file** is provided, include `--transcript <transcript-file>` explicitly (the hook detects `--transcript` is already present and skips injection):
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py \
  --format <format> \
  --output <file-path> \
  [--transcript <transcript-file>]
```

### Step 2: Report

Echo the exporter's stdout to the user verbatim — it includes file path, size, token breakdown by model, and subagent count.

## JSON Schema Reference

The JSON output format is documented in: `{MG_INSTALL_SCRIPTS_DIR}/references/transcript-json-schema.md`

The JSON output is compatible with `/mg:transcript-analyze` — you can analyze the exported JSON:
```
/mg:transcript-analyze /tmp/<file-name>
```
