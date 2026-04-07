---
name: transcript-export
description: Export the current Claude Code session as Markdown or JSON
allowed-tools: Bash, Read
argument-hint: "<format: md|json> <file-name>"
---

# /mg:transcript-export

Export the current Claude Code session transcript to a file.

## Arguments

Parse `$ARGUMENTS` to extract:
- **format** (required): `md` or `json`
- **file-path** (required): Output file path (absolute or relative to `/tmp/`)

Example: `/mg:transcript-export md /tmp/my-session.md`

If arguments are missing or unclear, ask the user.

## Exporter Tool

The exporter is at: `{MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py`

## Export Protocol

### Step 1: Export

Run the exporter with only `--format` and `--output`. A PreToolUse hook automatically injects the `--transcript` flag with the current session's JSONL path — no session ID or project path needed:
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py \
  --format <format> \
  --output <file-path>
```

### Step 2: Report

Echo the exporter's stdout to the user verbatim — it includes file path, size, token breakdown by model, and subagent count.

## JSON Schema Reference

The JSON output format is documented in: `{MG_INSTALL_SCRIPTS_DIR}/references/transcript-json-schema.md`

The JSON output is compatible with `/mg:transcript-analyze` — you can analyze the exported JSON:
```
/mg:transcript-analyze /tmp/<file-name>
```
