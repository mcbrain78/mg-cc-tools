# CC Session Analyzer — Concept

## Problem

Claude Code session exports can reach 90MB+. Claude needs to debug these sessions but can't load them into context. The existing compactor (`cc_session_compactor.py`) does uniform reduction, but debugging needs **selective access** — show me the errors, one agent's trace, or the orchestrator flow, not everything at once.

### Data distribution in session exports

Measured from actual samples:

| Component | 75MB session | 7MB session | 1MB session |
|-----------|-------------|-------------|-------------|
| chunks (UI duplicate) | 36.5MB (53%) | 3.4MB (48%) | 0.7MB (77%) |
| processes (agent msgs) | 31.5MB (45%) | 2.8MB (40%) | 0 |
| orchestrator messages | 1.3MB (2%) | 0.2MB (3%) | 0.2MB (23%) |
| session/metrics | <1KB | <1KB | <1KB |

### Key findings

1. `chunks` duplicates orchestrator messages + UI metadata — always safe to drop (50%+ of file size). Present in all session sizes, including small agent-less sessions
2. Agent size varies widely: largest agents ~750KB with 20+ file reads, average ~150KB
3. Claude Code truncates large tool outputs with `<persisted-output>` markers pointing to files on disk — recoverable by resolving the path
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
3. **Load-and-query.** Every invocation loads the full JSON (~0.4s for 75MB). No server, no index files, no state.
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
Location: agent[a697] msg[34] tool_call[4]
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
[08] 11:15  result: afc4 → FAILED: Exit code 1 — ruff check
[09] 11:48  result: a697 → PLAN COMPLETE (1/1 tasks)
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

  [1] msg[3]  Read scripts/process.py → ok (142 lines)
  [2] msg[5]  Read config/settings.json → ok (8 lines)
  [3] msg[7]  Grep "def main" in scripts/ → 3 matches
              → "Found the main functions. Let me run the processing script..."
  [4] msg[9]  Bash python3 scripts/process.py --input data.json → error (FileNotFoundError)
              → "The file wasn't found. Let me check the data directory..."
  [5] msg[11] Read data/ → ok (5 entries)
              → "The file is named data.csv, not data.json. Let me fix..."

Result: "PLAN COMPLETE. Tasks: 1/1..."

--- 5 of 25 tool calls. Next: agent a697 --offset 5 ---
```

All tool results show metadata only (status, size). Each line includes the message index (`msg[N]`) for direct navigation: `msg a697 9` shows full content of tool call [4].
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

Message N is the 0-based index into the messages array. Matches the `msg[N]` references in `errors` output.
Tool call indices in `agent` view (`[1]`, `[2]`, ...) count tool_use blocks sequentially — use `msg` to see full content.

Not paginated (single message + context).

#### `search <pattern> [--scope orchestrator|agents|agent:<prefix>]`

Search tool inputs, tool results (with persisted file recovery), and assistant text. Shows location and matching content (truncated to ~200 chars per hit). Results grouped by location.

Scope filters:
- `--scope orchestrator` — orchestrator messages only
- `--scope agents` — all agent processes only
- `--scope agent:a697` — single agent only
- Default (no flag): search everything

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

## Design Decisions

### D1: Error detection — curated high-confidence patterns

Avoid broad string matching (which produces false positives from grep results, log files, and assistant text discussing errors). Use a small set of high-confidence signals:

- `is_error` flag (snake_case) on `tool_result` content blocks — only present when `true`, absent otherwise. Appears on any tool type (Read, Bash, Write observed). Check `content[N].is_error` where `content[N].type == "tool_result"`
- `isError` flag (camelCase boolean) on `toolResults` array items — always present on every item, for all tool types. More universal but `toolResults` is a redundant denormalized copy (stripped at compactor L1). Prefer `is_error` on content blocks since the analyzer works on raw exports
- Python tracebacks: `Traceback (most recent call last)` in tool_result content
- Bash exit codes: `Exit code [1-9]` as a standalone line in tool_result content (not inside grep output or file content)
- Agent results: `FAILED` or `ERROR` in the first or last line of the result text (note: agent results end with a `<usage>` block — check the last line before `<usage>`)

Only scan tool_result content blocks — never flag patterns in assistant reasoning or tool_use inputs. If coverage proves insufficient post-v1, add a second tier later.

**Noise filtering:** Some `is_error=true` results are benign tool limitations, not real failures. Exclude from error counts:
- `exceeds maximum allowed tokens` / `content exceeds maximum` — Claude Code refusing to read a large file (routine, not a bug)
- `File has not been read yet` — tool precondition, not a failure
- `File does not exist` — wrong path, agent typically corrects and continues

These are tool-level constraints that agents routinely handle. Only surface errors that indicate actual failures in the session's work.

**Failed agent definition:** Claude Code does not set `is_error` on agent tool_results, and agents describe failures in natural language (no standardized status keyword). Detection is best-effort:
- Check for `is_error` on the agent's orchestrator-level tool_result (future-proofing — not set today)
- Pattern match known conventions: `PLAN FAILED`, `PLAN COMPLETE` (GSD agents), `FAILED`, `ERROR` in the first or last line before the trailing `<usage>` block
- If no signal is found, classify the agent as "ok" (unknown is safer than false positive)

An agent that had internal tool errors but recovered is "ok" — failure means the agent's final result indicates it did not complete its task.

### D2: `flow` extraction — mechanical, every message

Every orchestrator message gets a flow line. No AI classification. Classify mechanically by role + content blocks:

**Message structure in CC exports:** text and tool_use are separate assistant messages in all observed samples (0 combined messages across 4 samples). The Anthropic API allows combining them, so handle both cases but expect separation. Tool results arrive as `role=user` messages with `content` as a list of `tool_result` blocks. User-typed input arrives as `role=user` with `content` as a plain string. Both forms occur — check content type before parsing. `thinking` blocks may appear in assistant messages. System messages have no `role` (use `type=system`).

Classification rules:
- No `role` / `type=system` → skip (internal CC messages)
- `role=user`, has `tool_result` content blocks → check if it's an Agent return (match tool_use_id to a prior Agent tool_use). If yes: `result: <id_prefix> → <status from last line>`. If no: skip unless `is_error`/`isError` is true, in which case show: `result: <tool_name> → error (<first line of content>)`
- `role=user`, string or text content → `user: <first 80 chars>`
- `role=assistant`, has `tool_use` content blocks → one line per tool_use block (Agent calls show prompt + process_id prefix, others show tool name + truncated input)
- `role=assistant`, text only (no tool_use) → `asst: <first 80 chars>`
- `role=assistant`, thinking only (no text, no tool_use) → skip
- Timestamps from `timestamp` field on messages if present; omit if absent

### D2a: Agent-to-process linkage

Agent tool_result messages contain `agentId: <process_id>` appended as trailing text in the result content. Parse this to link orchestrator Agent calls to entries in the `processes` array. Process entries have `startTime`/`endTime` (epoch ms) for duration, `id` for matching, and their own `messages` array for the agent's conversation.

This linkage is consistent in all observed samples (213/213 matches in the 75MB sample). The implementation should still fail gracefully if the agentId pattern is missing — show `(unknown)` instead of a process_id prefix.

### D3: `search` scope filters — included in v1

`search <pattern> [--scope orchestrator|agents|agent:<prefix>]`

Without scope, search is nearly unusable on large sessions. Default (no flag) searches everything.

### D4: `agent-list` sort/filter — deferred to post-v1

Default chronological sort only. The overview already surfaces heaviest and failed agents.

### D5: Content display — metadata vs full content

The 2000-char preview from Claude Code's `<persisted-output>` truncation is arbitrary — not a meaningful summary. Commands either show metadata or full content, never the arbitrary preview.

**Summary commands** (metadata only, no tool result content):
- `overview`, `flow`, `agent`, `agent-list`
- Tool calls show: tool name, input summary, status (ok/error/persisted)
- Point to `msg` for full content

**Content commands** (full content, recover persisted files):
- `msg`, `errors` — always attempt persisted file recovery
- `search` — lazy recovery: iterate messages, and when a `<persisted-output>` block is encountered, read the persisted file and search its content. If the file is missing, search the preview text instead. Strip the wrapper before matching — never match against `<persisted-output>` tags or the `Full output saved to:` metadata line
- Script runs on originating machine where persisted files exist
- If persisted file missing: fall back to the preview text within the `<persisted-output>` block

### D6: Ambiguous agent prefix

If a prefix matches multiple agents, list them and exit:
`"Ambiguous prefix 'a6' — matches a697, a6f2, a601. Use a longer prefix."`

## Implementation Notes

### Loading
`json.load()` for every invocation. ~0.4s for 75MB. No caching, no index files, no server.

### Chunks
Drop `chunks` immediately after loading. Always duplicate data, never needed for analysis.

### Persisted Output Recovery

Tool result content containing `<persisted-output>` has this structure:
```
<persisted-output>
Output too large (30.3KB). Full output saved to: ./sample-name.persisted/abc123.txt

Preview (first 2KB):
     1→line content here
     2→line content here
...
</persisted-output>
```

Recovery steps:
1. Detect `<persisted-output>` wrapper in tool result content string
2. Extract path from `Full output saved to: <path>` line
3. Resolve path — absolute paths resolve directly, relative paths resolve from the session JSON file's parent directory
4. If file exists, read and use full content; if missing, extract the preview text after `Preview (first 2KB):` as fallback
5. Strip the `<persisted-output>` wrapper from display — show either recovered content or preview, never the wrapper itself
6. Recovery applies to content commands only (`msg`, `errors`, `search`) per D5

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
