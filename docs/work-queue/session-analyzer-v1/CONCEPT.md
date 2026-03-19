# CC Session Analyzer — Concept

## Problem

Claude Code session exports can reach 90MB+. Claude needs to debug these sessions but can't load them into context. The existing compactor (`cc_session_compactor.py`) does uniform reduction, but debugging needs **selective access** — show me the errors, one agent's trace, or the orchestrator flow, not everything at once.

### Data distribution in session exports

| Component | 90MB session | 75MB session | 1MB session |
|-----------|-------------|-------------|-------------|
| chunks (duplicate data) | 44.6MB (50%) | 36.5MB (48%) | 0 |
| processes (agent msgs) | 41.2MB (46%) | 31.6MB (42%) | 0 |
| orchestrator messages | 0.9MB (1%) | 1.3MB (2%) | 0.2MB (18%) |
| other (session, metrics) | 3.0MB (3%) | 6.0MB (8%) | 0.9MB (82%) |

### Key findings

1. `chunks` is a full duplicate of `processes` + UI metadata — always safe to drop (50% of file size)
2. Agent size is dominated by Read tool results (~1MB per agent for 20+ file reads)
3. Claude Code truncates large Bash outputs at 2000 chars with `<persisted-output>` markers pointing to files on disk — recoverable by resolving the path
4. Persisted paths work uniformly: originals use absolute paths (same machine), samples use relative paths (portable) — no special handling needed

## Two Scripts

### cc_session_compactor.py (renamed from reduce_cc_session_export.py)
- Pure transformation: session JSON in → smaller file out
- Levels 0-5 and l2-compact preserved as-is
- No query/display concerns

### cc_session_analyzer.py (new)
- Query tool: Claude runs it multiple times with different commands
- Imports compactor for `export` command
- Stateless with pagination — each invocation loads the file, returns one page of results

## Design Principles

1. **Self-teaching.** Running without arguments shows overview + available commands. Claude never needs a manual.
2. **Paginated.** Every list command has a default limit (20 items). Output ends with the exact command to get the next page. Claude copy-pastes it.
3. **2-second tax.** Every invocation loads the full JSON (~2s for 90MB). Acceptable for occasional debugging. No server, no index files, no state.
4. **Contextual.** Overview only shows commands relevant to what's in the session (no `agent-list` if there are no agents).

## Command Interface

### Default: no command = `overview`

```
python3 cc_session_analyzer.py session.json
```

### Commands

#### `overview` (default)

Session summary with contextual next steps. Always fits in context.

```
Session: 5c234780  Duration: 2h14m  Tokens: 12.4M
Size: 89.7MB (chunks: 44.6MB dropped, agents: 41.2MB, orch: 0.9MB)
Timeline: 11:02 → 13:16  First error: 11:45 (43min in)

Orchestrator: 381 messages, 166 tool calls
Agents: 123 total, 5 failed, 118 succeeded

Errors (5):
  agent[a697] "Execute plan 03-01...": FileNotFoundError: data.json
  agent[afc4] "Execute plan 03-02...": Exit code 1 — ruff check failed
  orch msg[45]: "Error: Command not found: vulture"
  orch msg[62]: "KeyError: 'valid'"
  orch msg[67]: timeout 60 seconds

Heaviest agents:
  a697  1.2MB  76 msgs  Read:23 Grep:1 Write:1
  afc4  1.1MB  60 msgs  Read:22 Write:1
  a4af  1.1MB  70 msgs  Read:22 Write:1

Persisted outputs: 9 (all recoverable)

Commands:
  errors                      Show all 5 errors with context
  flow                        Orchestrator decision trace (87 items)
  agent a697                  Deep dive into agent a697
  agent-list                  List all 123 agents
  msg <N>                     Orchestrator message N (±2 context)
  msg <agent-prefix> <N>      Agent message N (±2 context)
  search <pattern>            Search across all messages
  export [--level l2-compact] Produce a reduced file
```

Commands section is contextual — omits irrelevant options based on session content.

#### `errors`

All errors with context. Each error includes the agent's prompt snippet, the failing tool call, and surrounding assistant text.

```
--- Error 1/5 ---
Location: agent[a697] message[34]
Prompt: "Execute plan 03-01 — build mg-install-lib.py with TDD..."
Tool: Bash
Command: python3 scripts/process.py --input data.json
Result (error):
  Traceback (most recent call last):
    File "scripts/process.py", line 42, in main
      with open(input_path) as f:
  FileNotFoundError: [Errno 2] No such file or directory: 'data.json'

Before: "Let me run the processing script on the input data."
After: "The file wasn't found. Let me check if the path is correct..."
```

Paginated: default 20 errors per page.

#### `flow`

Orchestrator decision trace — one line per action. Timestamps included. Agent results show status (and error summary for failures).

```
[01] 11:02  user: /gsd:execute-phase 3
[02] 11:02  asst: Initializing phase 3...
[03] 11:02  call: Bash → gsd-tools init execute-phase "3"
[04] 11:02  call: Bash → gsd-tools phase-plan-index "03"
[05] 11:03  asst: Found 3 plans in 2 waves. Spawning wave 1...
[06] 11:03  call: Agent → "Execute plan 03-01" (a697)
[07] 11:03  call: Agent → "Execute plan 03-02" (afc4)
[08] 11:48  result: a697 → PLAN COMPLETE (1/1 tasks)
[09] 11:15  result: afc4 → FAILED: Exit code 1 — ruff check
[10] 11:48  asst: Wave 1 complete. Agent afc4 failed...

--- 10 of 87 items. Next: flow --offset 10 ---
```

Paginated: default 20 items per page.

#### `agent <id-prefix>`

Single agent deep dive. Tool calls and reasoning interleaved in execution order (preserves causal chain).

```
Agent: a697400c11ac
Prompt: "Execute plan 03-01 — build mg-install-lib.py with TDD..."
Duration: 45.2s  Tokens: 89,234  Messages: 76  Tools: 25

  [1] Read scripts/process.py → [ok, 142 lines]
  [2] Read config/settings.json → {"debug": true, "output": "/tmp/out"}
  [3] Grep "def main" in scripts/ → 3 files
      → "Found the main functions. Let me run the processing script..."
  [4] Bash python3 scripts/process.py --input data.json → ERROR FileNotFoundError
      → "The file wasn't found. Let me check the data directory..."
  [5] Read data/ → [directory listing, 5 entries]
      → "The file is named data.csv, not data.json. Let me fix..."

Result: "PLAN COMPLETE. Tasks: 1/1..."

--- 5 of 25 tool calls. Next: agent a697 --offset 5 ---
```

Read results stubbed to `[ok, N lines]` by default. Use `--full-reads` to show full content.
Paginated: default 20 tool calls per page.

#### `agent-list`

One line per agent.

```
  ID        Status  Duration  Tools  Size    Prompt
  a697      ok      45.2s     25    1.2MB   Execute plan 03-01 — build mg-install...
  afc4      error   12.1s     8     1.1MB   Execute plan 03-02 — create tool.toml...
  a4af      ok      38.7s     23    1.1MB   Execute plan 03-03 — install.md slash...

--- 3 of 123 agents. Next: agent-list --offset 3 ---
```

Paginated: default 20 agents per page.

#### `msg <N>` or `msg <agent-prefix> <N>`

Show a single message with ±2 surrounding messages for context. Full content, no truncation. Persisted outputs recovered if files exist.

Works for both orchestrator and agent messages:
```
python3 cc_session_analyzer.py session.json msg 45
python3 cc_session_analyzer.py session.json msg a697 34
```

Message N is the raw message index — matches what `errors` and `agent` report.

Not paginated (single message + context).

#### `search <pattern>`

Search tool inputs, tool results, and assistant text across the entire session. Shows location and matching content (truncated to ~200 chars per hit). Results grouped by location.

```
python3 cc_session_analyzer.py session.json search "FileNotFoundError"

  agent[a697] msg[34] tool_result (Bash):
    ...FileNotFoundError: [Errno 2] No such file or directory: 'data.json'

  agent[a697] msg[36] assistant:
    ..."The file wasn't found. Let me check if the path is correct..."

--- 2 of 2 matches ---
```

Paginated: default 20 matches per page.

#### `export [--level l2-compact]`

Produce a reduced file. Delegates to `cc_session_compactor.py` (imported). Drops chunks before compacting.

Not paginated (file output).

## Pagination

Every list command follows the same pattern:
- Default limit: 20 items
- `--offset N`: skip first N items
- `--limit N`: override default page size
- `--all`: show everything (no pagination)
- Output footer: `--- N of M items. Next: <exact command to copy-paste> ---`

Commands that paginate: `errors`, `flow`, `agent`, `agent-list`, `search`.
Commands that don't: `overview`, `msg`, `export`.

## Implementation Notes

### Loading
`json.load()` for every invocation. ~2s for 90MB. No caching, no index files, no server.

### Chunks
Drop `chunks` immediately after loading. Always duplicate data, never needed for analysis.

### Persisted Output Recovery
1. Detect `<persisted-output>` marker in tool result content
2. Extract path from `saved to: <path>` text
3. Resolve path — absolute paths resolve directly, relative paths resolve from session file's directory
4. If file exists, read content; otherwise use the 2000-char preview already in the JSON
5. Recovery happens in `msg` command and in `errors` context display

### Error Detection
Reuse compactor's error markers: `Error:`, `error:`, `ERROR`, `Exit code`, `exceeds maximum`.

## File Structure

```
mg-cc-tools/session-analyzer/
  cc_session_compactor.py        ← renamed from reduce_cc_session_export.py
  cc_session_analyzer.py         ← new
  samples/                       ← gitignored
    sample-*.json
    sample-*.persisted/
    sample-*.tar.gz
```

## What This Does NOT Do

- No persistent state — each invocation is independent
- No server or daemon — just a script
- No modification of the source session file — read-only
- No cross-session comparison
- No ANSI colors — Claude doesn't render them
