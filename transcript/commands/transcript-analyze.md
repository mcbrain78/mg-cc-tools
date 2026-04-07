---
name: transcript-analyze
description: Analyze a Claude Code session export to understand what happened, find errors, and trace decisions
allowed-tools: Bash, Read, Write, Glob, Grep
argument-hint: "<session-file> [question]"
---

# /mg:transcript-analyze

You are analyzing a Claude Code session export. The session file and optional goal are provided via $ARGUMENTS.

## Arguments

Parse `$ARGUMENTS` to extract:
- **session_file** (required): Path to the session JSON export file
- **goal** (optional): A specific question or investigation goal

If no session_file provided, ask the user for the path.

## Analyzer Tool

The session analyzer is at: `{MG_INSTALL_SCRIPTS_DIR}/cc_transcript_analyzer.py`

All commands follow this pattern:
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_analyzer.py <session_file> <command> [options]
```

Available commands:
- `overview` (default) -- session summary with stats, errors, and next steps
- `errors [--offset N] [--limit N] [--all]` -- all errors with full context
- `flow [--offset N] [--limit N] [--all]` -- orchestrator decision trace
- `agent <id-prefix> [--offset N] [--limit N] [--all]` -- single agent deep dive
- `agent-list [--offset N] [--limit N] [--all]` -- list all agents
- `msg <N>` or `msg <N> --agent <prefix>` -- single message with full content
- `search <pattern> [--scope orchestrator|agents|agent:<prefix>] [--offset N] [--limit N] [--all]` -- search content
- `export [--level l2-compact|0|1|2|3|4|5]` -- export reduced version

## Analysis Protocol

### Step 1: Overview

Always start by running the overview command:
```
python3 {MG_INSTALL_SCRIPTS_DIR}/cc_transcript_analyzer.py <session_file>
```

Read the output carefully. Note:
- Error count and locations
- Agent success/failure rates
- Session duration and token usage
- The contextual commands section at the bottom (follow its suggestions)

### Step 2: Investigate

**If a goal was provided:** Focus your investigation on answering the user's question. Use the commands that are most relevant:
- For "why did X fail?" -- check `errors`, then `msg` for specific errors, then `agent` for the failing agent
- For "what happened?" -- check `flow` for the decision sequence, then drill into interesting points with `msg`
- For "find X" -- use `search` with relevant patterns

**If no goal was provided:** Autonomously investigate based on what you found in the overview:
- If errors exist: run `errors` to see all errors with context, then `msg` to examine the worst ones
- If agents failed: run `agent-list` to identify failures, then `agent <prefix>` to understand why
- If the session is large: run `flow` to understand the decision sequence, identify key turning points

### Step 3: Iterate

Continue running commands until you have enough context to provide a useful analysis. Each command output includes references to help you drill deeper:
- Error entries have `msg[N]` references -- use `msg N` to see full context
- Flow entries reference agent IDs -- use `agent <prefix>` to deep dive
- Agent views reference message indices -- use `msg N --agent <prefix>` for full content
- Pagination footers include the exact command for the next page -- copy and run it

### Step 4: Report

Present your findings to the user:
- **Summary**: What the session did (in 2-3 sentences)
- **Key Findings**: Errors, failures, unusual patterns (with specific evidence from the session)
- **Timeline**: Important events in chronological order
- **Recommendations**: What to fix or investigate further (if applicable)

## Important Notes

- The analyzer produces plain text output -- read it carefully before running the next command
- Use pagination (--limit, --offset) to manage large outputs -- avoid --all on commands with many items
- The `msg` command is your drill-in tool -- use it whenever you need full content from a specific point
- The `search` command recovers persisted output files -- use it to find content that was too large for inline display
- All output is plain text (no ANSI colors) -- read it as-is
