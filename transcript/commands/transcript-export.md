---
name: transcript-export
description: Export the current Claude Code session as Markdown or JSON
allowed-tools: Bash, Read
---

# /mg:transcript-export

Export the current Claude Code session transcript to a file.

## Arguments

Parse `$ARGUMENTS` to extract:
- **format** (required): `md` or `json`
- **file-name** (required): Output filename (written to `/tmp/`)

Example: `/mg:transcript-export md my-session.md`

If arguments are missing or unclear, ask the user.

## Exporter Tool

The exporter is at: `{MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py`

## Export Protocol

### Step 1: Resolve Session ID

Determine the current session ID. Check the `$SESSION_ID` environment variable:
```
echo $SESSION_ID
```

If `$SESSION_ID` is empty, look for the most recently modified JSONL file in the current project's session directory:
```
ls -t ~/.claude/projects/$(pwd | sed 's|/|-|g')/*.jsonl 2>/dev/null | head -1
```

Extract the UUID from the filename (everything before `.jsonl`).

If that also fails, ask the user for a session ID.

### Step 2: Export

Run the exporter:
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_exporter.py <session-id> --format <format> --output /tmp/<file-name> --project "$(pwd)"
```

### Step 3: Report

Report the result to the user:
- Output file path and size
- Number of messages and tokens
- Number of subagents (if any)

## JSON Schema Reference

The JSON output format is documented in: `{MG_INSTALL_SCRIPTS_DIR}/references/transcript-json-schema.md`

The JSON output is compatible with `/mg:transcript-analyze` — you can analyze the exported JSON:
```
/mg:transcript-analyze /tmp/<file-name>
```
