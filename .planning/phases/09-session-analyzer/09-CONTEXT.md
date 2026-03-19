# Phase 9: Session Analyzer - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning
**Source:** Merged — context import (docs/work-queue/session-analyzer-v1/CONCEPT.md) + interactive discussion

<domain>
## Phase Boundary

Build a CLI query tool (`cc_session_analyzer.py`) that gives Claude selective access to CC session exports (up to 90MB+). Rename existing `reduce_cc_session_export.py` to `cc_session_compactor.py`. The analyzer is stateless, paginated, and self-teaching — Claude runs it multiple times with different commands to navigate sessions. Cross-session comparison and persistent state are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Two-script architecture
- `cc_session_compactor.py` — renamed from `reduce_cc_session_export.py`, pure transformation (session JSON in → smaller file out), levels 0-5 and l2-compact preserved as-is
- `cc_session_analyzer.py` — new query tool, imports compactor for `export` command, stateless with pagination

### Loading strategy
- `json.load()` for every invocation (~0.4s for 75MB), no caching, no index files, no server
- Drop `chunks` immediately after loading — always duplicate data (50%+ of file size), never needed for analysis

### Command interface
- Default (no command) = `overview` — session summary with contextual next steps, always fits in context
- `errors` — all errors with context (agent prompt snippet, failing tool call, surrounding assistant text), paginated
- `flow` — orchestrator decision trace, one line per action with timestamps, paginated
- `agent <id-prefix>` — single agent deep dive with tool calls and reasoning interleaved in execution order, paginated
- `agent-list` — one line per agent (ID, status, duration, tools, size, prompt), paginated
- `msg <N>` or `msg <agent-prefix> <N>` — single message with ±2 context, full content, not paginated
- `search <pattern> [--scope orchestrator|agents|agent:<prefix>]` — search tool inputs, results (with persisted file recovery), and assistant text, paginated
- `export [--level l2-compact]` — delegates to compactor, drops chunks first, not paginated

### Overview output structure
- Session metadata: ID, duration, tokens, size breakdown (chunks/agents/orch)
- Timeline with first error timestamp
- Orchestrator stats: message count, tool call count
- Agent stats: total, failed, succeeded
- Error list: location, prompt snippet, error message (all errors, not paginated in overview)
- Heaviest agents: top 3 by size with message count and tool breakdown
- Persisted outputs: count and recoverability status
- Contextual commands section: omit irrelevant options based on session content (no `agent-list` if no agents)

### Pagination design
- Default limit: 20 items for all paginated commands
- `--offset N`: skip first N items
- `--limit N`: override default page size
- `--all`: show everything (no pagination)
- Output footer: `--- N of M items. Next: <exact command to copy-paste> ---`
- Paginated commands: `errors`, `flow`, `agent`, `agent-list`, `search`
- Non-paginated commands: `overview`, `msg`, `export`

### Error detection — curated high-confidence patterns (D1)
- `is_error` flag (snake_case) on `tool_result` content blocks — preferred signal, only present when `true`
- Python tracebacks: `Traceback (most recent call last)` in tool_result content
- Bash exit codes: `Exit code [1-9]` as standalone line in tool_result content (not inside grep output or file content)
- Agent results: `FAILED` or `ERROR` in first or last line of result text (before trailing `<usage>` block)
- Only scan tool_result content blocks — never flag patterns in assistant reasoning or tool_use inputs
- Noise filtering: exclude `exceeds maximum allowed tokens`, `File has not been read yet`, `File does not exist` from error counts (benign tool limitations, not real failures)
- Failed agent definition: check `is_error` on orchestrator-level tool_result (future-proofing), pattern match `PLAN FAILED`/`PLAN COMPLETE`/`FAILED`/`ERROR` in first/last line before `<usage>`, classify unknown as "ok"

### Flow extraction — mechanical, every message (D2)
- Every orchestrator message gets a flow line, no AI classification
- Classification rules by role + content blocks:
  - No role / type=system → skip
  - role=user with tool_result blocks → check if Agent return (match tool_use_id), show result status; skip non-error tool results
  - role=user with string/text content → `user: <first 80 chars>`
  - role=assistant with tool_use blocks → one line per tool_use (Agent calls show prompt + process_id prefix)
  - role=assistant with text only → `asst: <first 80 chars>`
  - role=assistant with thinking only → skip
  - Timestamps from `timestamp` field if present; omit if absent

### Agent-to-process linkage (D2a)
- Agent tool_result messages contain `agentId: <process_id>` appended as trailing text
- Parse this to link orchestrator Agent calls to `processes` array entries
- Process entries have `startTime`/`endTime` (epoch ms) for duration, `id` for matching, own `messages` array
- Fail gracefully if agentId pattern missing — show `(unknown)` instead

### Content display modes (D5)
- Summary commands (metadata only): `overview`, `flow`, `agent`, `agent-list` — tool calls show name, input summary, status (ok/error/persisted), point to `msg` for full content
- Content commands (full content, recover persisted files): `msg`, `errors`, `search`
- Never show the arbitrary 2000-char `<persisted-output>` preview as-is — show either recovered full content or the preview text without the wrapper

### Persisted output recovery
- Detect `<persisted-output>` wrapper in tool result content string
- Extract path from `Full output saved to: <path>` line
- Resolve: absolute paths directly, relative paths from session JSON file's parent directory
- File exists → read full content; missing → extract preview text after `Preview (first 2KB):` as fallback
- Strip `<persisted-output>` wrapper from display
- Recovery applies to content commands only (`msg`, `errors`, `search`)

### Ambiguous agent prefix (D6)
- If prefix matches multiple agents, list them and exit: `"Ambiguous prefix 'a6' — matches a697, a6f2, a601. Use a longer prefix."`

### Search scope filters (D3)
- `--scope orchestrator` — orchestrator messages only
- `--scope agents` — all agent processes only
- `--scope agent:<prefix>` — single agent only
- Default (no flag): search everything
- Lazy persisted file recovery in search: read persisted file on encounter, fall back to preview if missing, strip wrapper before matching

### No ANSI colors
- Claude doesn't render them — plain text output only

### Agent-list sort/filter (D4)
- Default chronological sort only — deferred to post-v1
- Overview already surfaces heaviest and failed agents

### Delivery model
- Slash command: `/mg:analyze-session` — installs as a command .md with tool.toml and install.sh
- Command instructs Claude to run overview first, interpret output, then autonomously drive iterative queries until it has enough context
- Dual mode: if the user provides a goal/question alongside the session path, Claude targets queries toward answering that goal; if no goal, Claude analyzes the file and autonomously investigates any issues it finds
- Usage: `/mg:analyze-session <session-file> [goal/question]`

### Testing strategy
- Pytest test suite for both compactor and analyzer
- Test against 1MB sample (no agents) and 75MB sample (216 agents) for coverage across session sizes
- Structure + key values validation: verify output sections exist, pagination footer format correct, spot-check counts (error count, agent count, known error messages)
- 75MB tests marked with `@pytest.mark.slow` — skipped by default, run with `pytest --slow`
- 1MB tests run by default for fast feedback

### Compactor integration
- Import `cc_session_compactor` as-is — no refactoring of the compactor's internal API
- Independent error detection: analyzer implements its own D1 patterns from scratch (compactor's broad string matching serves a different purpose — preservation during reduction)
- No backwards compatibility for old `reduce_cc_session_export.py` name — clean break

### File structure
- `mg-cc-tools/session-analyzer/cc_session_compactor.py` (already renamed)
- `mg-cc-tools/session-analyzer/cc_session_analyzer.py` (new)
- `mg-cc-tools/session-analyzer/commands/analyze-session.md` (new — slash command)
- `mg-cc-tools/session-analyzer/install.sh` (new — standard 3-mode install)
- `mg-cc-tools/session-analyzer/tool.toml` (new — tool metadata)
- `mg-cc-tools/session-analyzer/tests/` (new — pytest suite)
- `mg-cc-tools/session-analyzer/samples/` (gitignored: sample-*.json, sample-*.persisted/, sample-*.tar.gz)

### Claude's Discretion
- Internal code organization within the two scripts (class structure, helper functions)
- Exact regex patterns for error detection signal extraction
- How to handle malformed session JSON (missing fields, unexpected structure)
- Test file organization and naming within tests/
- Whether to add a `--verbose` or `--debug` flag for the analyzer itself
- install.sh structure and sed resolution patterns (following existing mg-cc-tools conventions)
- Slash command .md internal structure (prompt engineering for the autonomous query loop)

</decisions>

<specifics>
## Specific Ideas

- Self-teaching design: running without arguments shows overview + available commands — Claude never needs a manual
- Every list command footer includes the exact copy-paste command for the next page
- Overview commands section is contextual — only shows commands relevant to what's in the session
- The `agent` view interleaves tool calls and reasoning to preserve the causal chain — each entry includes `msg[N]` for direct navigation via `msg` command
- Message structure note: text and tool_use are separate assistant messages in all observed CC export samples (0 combined messages across 4 samples), but handle combined case defensively
- Data distribution reference (measured from actual samples): chunks ~50% (always safe to drop), processes ~40-45%, orchestrator ~2-3%, session/metrics <1KB
- Dual mode slash command: goal-directed investigation focuses Claude's queries; autonomous mode investigates all issues found in overview

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cc_session_compactor.py`: Already renamed, 885 lines, fully functional with levels 0-5 and l2-compact — imported by analyzer for `export` command
- 4 sample session files: 1MB (no agents), 7MB (7 agents), 18MB (102 agents), 75MB (216 agents) with persisted output directories
- Compactor has error detection markers, size estimation logic, and content block traversal — but analyzer implements its own detection independently

### Established Patterns
- mg-cc-tools tool anatomy: `<tool-name>/install.sh` + `commands/*.md` + `tool.toml` + optional supporting resources
- Install scripts support three modes: `--project [<dir>]`, `--global`, `--target <path>`
- Path resolution at install time via sed replacement of placeholders
- tool.toml format: `[tool]` with description, `[preflight]` with required/optional deps, `[detect]` with paths array
- Manifest update via `mg-install-lib.py update-manifest` at end of install.sh

### Integration Points
- `cc_session_analyzer.py` imports `cc_session_compactor.py` for the `export` command
- `samples/` directory is gitignored via `**/samples/` pattern in root .gitignore
- Tests use sample files as fixtures (1MB always, 75MB with --slow flag)

</code_context>

<deferred>
## Deferred Ideas

- Agent-list sort/filter options (by size, duration, status) — post-v1
- Cross-session comparison — explicitly out of scope
- Persistent state / server mode — explicitly out of scope
- Verify-generate feedback loop integration — separate concern
- Second-tier error detection patterns — add only if v1 coverage proves insufficient

</deferred>

---

*Phase: 09-session-analyzer*
*Context gathered: 2026-03-19 via context import + interactive discussion*
