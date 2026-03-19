# Phase 9: Session Analyzer - Research

**Researched:** 2026-03-19
**Domain:** CLI query tool for Claude Code session exports (Python, argparse, JSON processing)
**Confidence:** HIGH

## Summary

Phase 9 builds a stateless CLI query tool (`cc_session_analyzer.py`) that enables Claude to selectively navigate large CC session exports (up to 90MB+) through iterative commands. The tool is paired with a slash command (`/mg:analyze-session`) that teaches Claude to drive the analyzer autonomously. The existing `cc_session_compactor.py` (already renamed, 885 lines) is imported for the `export` command but otherwise untouched.

The session JSON structure is well-understood from empirical analysis of 4 sample files (1MB, 7MB, 18MB, 75MB). Key structural facts: top-level keys are `session`, `messages`, `chunks`, `processes`, `metrics`; chunks consume ~53% of file size and are always safe to drop; processes contain agent messages with `startTime`/`endTime`/`durationMs`; orchestrator Agent tool_result messages contain `agentId: <process_id>` as trailing text for linkage; `is_error` flag (snake_case) exists on tool_result blocks. The tool is pure Python 3.11+ with no third-party dependencies.

**Primary recommendation:** Build as a single `cc_session_analyzer.py` file (~600-900 lines) using argparse subcommands, with the compactor as an importable module. Prioritize the loading/parsing layer and `overview` command first, as every other command builds on the same data access patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Two-script architecture: `cc_session_compactor.py` (renamed, as-is) + `cc_session_analyzer.py` (new, stateless)
- Loading strategy: `json.load()` every invocation, drop `chunks` immediately, no caching/index/server
- Command interface: `overview` (default), `errors`, `flow`, `agent <prefix>`, `agent-list`, `msg <N>`, `search <pattern>`, `export`
- Pagination: default 20, `--offset N`, `--limit N`, `--all`, footer with exact next command
- Error detection: curated high-confidence patterns only (is_error flag, tracebacks, bash exit codes, agent result status)
- Noise filtering: exclude `exceeds maximum allowed tokens`, `File has not been read yet`, `File does not exist`
- Flow extraction: mechanical, every orchestrator message, classification by role + content blocks
- Agent-to-process linkage via `agentId: <process_id>` in tool_result text
- Content display modes: summary commands (metadata only) vs content commands (full content + persisted recovery)
- Persisted output recovery: detect wrapper, extract path, resolve, read or fall back to preview
- No ANSI colors
- Delivery: slash command `/mg:analyze-session` with tool.toml, install.sh, commands/analyze-session.md
- Testing: pytest with 1MB (default) and 75MB (`--slow`) samples
- Compactor integration: import as-is, independent error detection
- File structure: `session-analyzer/` directory with cc_session_compactor.py, cc_session_analyzer.py, commands/, tests/, samples/
- Dual mode slash command: goal-directed or autonomous investigation

### Claude's Discretion
- Internal code organization within the two scripts (class structure, helper functions)
- Exact regex patterns for error detection signal extraction
- How to handle malformed session JSON (missing fields, unexpected structure)
- Test file organization and naming within tests/
- Whether to add a `--verbose` or `--debug` flag for the analyzer itself
- install.sh structure and sed resolution patterns (following existing mg-cc-tools conventions)
- Slash command .md internal structure (prompt engineering for the autonomous query loop)

### Deferred Ideas (OUT OF SCOPE)
- Agent-list sort/filter options (by size, duration, status) -- post-v1
- Cross-session comparison -- explicitly out of scope
- Persistent state / server mode -- explicitly out of scope
- Verify-generate feedback loop integration -- separate concern
- Second-tier error detection patterns -- add only if v1 coverage proves insufficient
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SAN-01 | Compactor renamed from reduce_cc_session_export.py | Already done -- file exists at session-analyzer/cc_session_compactor.py (885 lines, verified) |
| SAN-02 | Analyzer loads JSON via json.load(), drops chunks | Benchmarked: 0.38s load for 75MB, chunks = 53% of file; drop is instant |
| SAN-03 | Overview command with full session summary | Session JSON structure fully mapped; all required fields identified in samples |
| SAN-04 | Errors command with context and pagination | Error patterns verified across 4 samples: is_error flag, tracebacks, exit codes all present |
| SAN-05 | Flow command with mechanical classification | Message roles and content block types analyzed; classification rules map cleanly to observed data |
| SAN-06 | Agent deep dive with interleaved tool calls/reasoning | Process message structure verified: messages list with role/content, tool_use/tool_result blocks |
| SAN-07 | Agent-list command | Process entries have id, durationMs, metrics, messages; prompt extraction from first user message |
| SAN-08 | Msg command with +/-2 context | Messages are indexed arrays in both orchestrator and process message lists |
| SAN-09 | Search command with persisted recovery | Persisted output wrapper structure verified; 435 persisted outputs in 75MB sample, 1 in 1MB |
| SAN-10 | Export command delegates to compactor | Compactor's `slim()` function and `main()` are importable; export just needs to drop chunks first then call compactor |
| SAN-11 | Pagination with --offset, --limit, --all | Standard argparse pattern; footer format specified in CONTEXT.md |
| SAN-12 | Error detection curated patterns | is_error (snake_case) flag verified on tool_result blocks; traceback/exit code patterns confirmed in samples |
| SAN-13 | Noise filtering | Patterns specified; no occurrences found in test samples but defensive filtering still required |
| SAN-14 | Agent-to-process linkage | agentId pattern verified: `agentId: <17-char-hex> (for resuming...)` in tool_result text |
| SAN-15 | Persisted output recovery | Wrapper structure: `<persisted-output>` tag, `Full output saved to:` path line, `Preview (first 2KB):` section |
| SAN-16 | Ambiguous agent prefix handling | Process IDs are 17-char hex strings; prefix matching with collision detection is straightforward |
| SAN-17 | Search scope filters | Scope maps to orchestrator messages list vs process message lists; prefix resolution for agent: scope |
| SAN-18 | No ANSI colors | Plain text output only; no colorama or similar |
| SAN-19 | Slash command with tool.toml and install.sh | Patterns verified from 12 existing tools; session-analyzer follows data-provider/codebase-health hybrid pattern |
| SAN-20 | Dual mode slash command | Command .md prompt engineering; $ARGUMENTS parsing for goal vs autonomous mode |
| SAN-21 | Pytest suite with 1MB/75MB samples | Test infrastructure exists in project; pyproject.toml has pytest in dev deps; conftest.py needed for --slow flag |
| SAN-22 | Independent error detection | Compactor uses broad ERROR_MARKERS; analyzer uses curated is_error + traceback + exit code patterns |
| SAN-23 | Contextual commands in overview | session.hasSubagents flag and process count determine agent command relevance |
| SAN-24 | Summary vs content display modes | Verified: summary commands show metadata, content commands show full text with persisted recovery |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | 3.11+ | JSON loading | Only dependency for session parsing; 0.38s for 75MB |
| Python stdlib `argparse` | 3.11+ | CLI interface | Subcommands for each analyzer command |
| Python stdlib `re` | 3.11+ | Pattern matching | Error detection regex, agentId extraction |
| Python stdlib `pathlib` | 3.11+ | Path resolution | Persisted output file recovery |
| `cc_session_compactor` | local | Export delegation | Already exists; imported for export command |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `datetime` | 3.11+ | Timestamp parsing | Duration calculations from ISO 8601 startTime/endTime |
| Python stdlib `textwrap` | 3.11+ | Text truncation | Truncating long content in summary views |
| `pytest` | dev dep | Test framework | Test suite with --slow marker |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse subcommands | sys.argv manual parsing | Argparse gives --help, type checking, default values for free |
| json.load() | ijson streaming | Streaming would save memory but adds dependency; json.load at 0.38s is fast enough |
| re module | simple string matching | Regex needed for exit code pattern `^Exit code [1-9]` with MULTILINE flag |

**Installation:**
```bash
# No additional packages -- pure stdlib + local import
# For development only:
pip install pytest ruff
```

## Architecture Patterns

### Recommended Project Structure
```
session-analyzer/
├── cc_session_compactor.py      # Existing 885-line compactor (renamed, unchanged)
├── cc_session_analyzer.py       # New query tool (~600-900 lines)
├── commands/
│   └── analyze-session.md       # Slash command for Claude
├── install.sh                   # Standard 3-mode installer
├── tool.toml                    # Tool metadata
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # --slow flag, sample path fixtures
│   ├── test_analyzer_overview.py
│   ├── test_analyzer_errors.py
│   ├── test_analyzer_flow.py
│   ├── test_analyzer_agent.py
│   ├── test_analyzer_search.py
│   ├── test_analyzer_msg.py
│   ├── test_analyzer_pagination.py
│   └── test_analyzer_export.py
└── samples/                     # Gitignored (large session exports)
    ├── sample-1mb-no-agents.json
    ├── sample-1mb-no-agents.persisted/
    ├── sample-7mb-7-agents.json
    ├── sample-18mb-102-agents.json
    ├── sample-75mb-216-agents.json
    └── sample-75mb-216-agents.persisted/
```

### Pattern 1: Load-Once Data Access Layer
**What:** A single function loads JSON, drops chunks, and returns a dict that all commands share.
**When to use:** Every command invocation.
**Example:**
```python
def load_session(path: str) -> dict:
    """Load session JSON and drop chunks (always duplicate data)."""
    with open(path) as f:
        data = json.load(f)
    # Validate required keys
    for key in ("session", "messages", "processes", "metrics"):
        if key not in data:
            print(f"Error: missing required key '{key}' -- not a CC session export", file=sys.stderr)
            sys.exit(1)
    data.pop("chunks", None)
    return data
```

### Pattern 2: Argparse Subcommands with Shared Arguments
**What:** Each analyzer command is a subcommand with shared pagination flags.
**When to use:** CLI interface design.
**Example:**
```python
parser = argparse.ArgumentParser(description="Query Claude Code session exports")
parser.add_argument("session_file", help="Path to session JSON export")
subparsers = parser.add_subparsers(dest="command")

# overview (default when no command given)
sub = subparsers.add_parser("overview")

# errors (paginated)
sub = subparsers.add_parser("errors")
add_pagination_args(sub)

# flow (paginated)
sub = subparsers.add_parser("flow")
add_pagination_args(sub)

# If no command, default to overview
args = parser.parse_args()
if args.command is None:
    args.command = "overview"
```

### Pattern 3: Pagination Helper
**What:** Generic pagination that wraps any list of items with offset/limit/footer.
**When to use:** All paginated commands (errors, flow, agent, agent-list, search).
**Example:**
```python
def paginate(items: list, args, command_prefix: str) -> tuple[list, str]:
    """Apply pagination and generate footer."""
    total = len(items)
    if getattr(args, 'all', False):
        return items, f"--- {total} of {total} items ---"
    offset = getattr(args, 'offset', 0)
    limit = getattr(args, 'limit', 20)
    page = items[offset:offset + limit]
    shown = offset + len(page)
    if shown < total:
        next_offset = offset + limit
        footer = f"--- {shown} of {total} items. Next: {command_prefix} --offset {next_offset} ---"
    else:
        footer = f"--- {shown} of {total} items ---"
    return page, footer
```

### Pattern 4: Error Detection Pipeline
**What:** Scan tool_result blocks only, apply curated patterns, filter noise.
**When to use:** overview (error count), errors command, and implicitly in flow (error tool results).
**Example:**
```python
NOISE_PATTERNS = [
    "exceeds maximum allowed tokens",
    "File has not been read yet",
    "File does not exist",
]

def is_real_error(block: dict) -> bool:
    """Check if a tool_result block represents a real error."""
    # Primary signal: is_error flag (snake_case)
    if block.get("is_error"):
        text = extract_text(block.get("content", ""))
        return not any(noise in text for noise in NOISE_PATTERNS)

    text = extract_text(block.get("content", ""))
    if not text:
        return False

    # Filter noise first
    if any(noise in text for noise in NOISE_PATTERNS):
        return False

    # Python traceback
    if "Traceback (most recent call last)" in text:
        return True

    # Bash exit code (standalone line, not inside file content)
    if re.search(r"^Exit code [1-9]", text, re.MULTILINE):
        return True

    return False
```

### Pattern 5: Agent-to-Process Linkage
**What:** Parse agentId from orchestrator tool_result text to connect Agent calls to process entries.
**When to use:** flow command (annotating Agent calls), agent command (resolving prefix to process).
**Example:**
```python
import re

AGENT_ID_RE = re.compile(r"agentId:\s*(\w+)")

def build_agent_map(data: dict) -> dict[str, dict]:
    """Map process IDs to process entries for fast lookup."""
    return {proc["id"]: proc for proc in data.get("processes", []) if isinstance(proc, dict)}

def extract_agent_id(tool_result_text: str) -> str | None:
    """Extract agentId from agent tool_result content."""
    m = AGENT_ID_RE.search(tool_result_text)
    return m.group(1) if m else None
```

### Pattern 6: Persisted Output Recovery
**What:** Detect `<persisted-output>` wrapper, extract file path, read or fall back to preview.
**When to use:** Content commands only (msg, errors, search).
**Example:**
```python
def recover_persisted(text: str, session_dir: Path) -> str:
    """Replace persisted output wrapper with actual content or cleaned preview."""
    if "<persisted-output>" not in text:
        return text

    # Extract path from "Full output saved to: <path>" line
    path_match = re.search(r"Full output saved to:\s*(.+)", text)
    if not path_match:
        # Strip wrapper, return inner text
        return text.replace("<persisted-output>", "").replace("</persisted-output>", "").strip()

    raw_path = path_match.group(1).strip()
    path = Path(raw_path)
    if not path.is_absolute():
        path = session_dir / path

    if path.exists():
        return path.read_text()

    # Fall back to preview text
    preview_match = re.search(r"Preview \(first \d+.*?\):\n(.*?)(?:</persisted-output>|$)", text, re.DOTALL)
    if preview_match:
        return preview_match.group(1).strip()

    return text.replace("<persisted-output>", "").replace("</persisted-output>", "").strip()
```

### Anti-Patterns to Avoid
- **Loading chunks:** Never keep chunks in memory -- they duplicate data and consume 53% of file size. Always `data.pop("chunks", None)` immediately after load.
- **Scanning assistant text for errors:** Error detection MUST only scan `tool_result` content blocks. Never flag patterns found in assistant reasoning or tool_use inputs.
- **Using compactor error detection:** The compactor's `ERROR_MARKERS` is intentionally broad for preservation during reduction. The analyzer needs its own curated, high-confidence patterns.
- **Rendering ANSI colors:** Claude cannot render ANSI escape codes. All output must be plain text.
- **Showing raw persisted-output wrapper:** Never display the `<persisted-output>` XML wrapper to the user. Either recover the full file or extract the preview text.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI argument parsing | Custom argv parsing | `argparse` with subcommands | Handles --help, type validation, default values, mutual exclusion |
| JSON loading | Streaming parser | `json.load()` | 0.38s for 75MB is fast enough; streaming adds complexity for no gain |
| Timestamp parsing | Manual string parsing | `datetime.fromisoformat()` | Handles ISO 8601 with timezone; Python 3.11+ handles `Z` suffix |
| Path resolution | Manual string manipulation | `pathlib.Path` | Handles absolute/relative, existence checks, parent directory |
| Text truncation | Manual slicing | `textwrap.shorten()` or controlled slicing | Handles word boundaries, ellipsis |
| Compactor functionality | Re-implement reduction levels | Import `cc_session_compactor.slim()` | 885 lines of tested code; no reason to duplicate |

**Key insight:** This tool is fundamentally a read-only query interface over a well-defined JSON structure. The complexity is in the output formatting and UX (pagination, contextual commands, persisted recovery), not in algorithms. Keep the data access simple and invest effort in clear, useful output.

## Common Pitfalls

### Pitfall 1: Content Block Type Variance
**What goes wrong:** Assuming tool_result content is always a string.
**Why it happens:** Content can be a string OR a list of `{type: "text", text: "..."}` objects.
**How to avoid:** Always use a helper function that handles both formats:
```python
def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""
```
**Warning signs:** Crash on `TypeError: string indices must be integers` when encountering list content.

### Pitfall 2: Exit Code False Positives
**What goes wrong:** Matching "Exit code 1" inside file content that was read by a tool, or inside grep output.
**Why it happens:** The pattern `Exit code N` can appear in any text that discusses exit codes.
**How to avoid:** Only match exit codes in tool_result content blocks. The CONTEXT.md specifies "standalone line" -- use `^Exit code [1-9]` with `re.MULTILINE`. This is still imperfect but catches the common case where Bash tool reports its exit code on its own line.
**Warning signs:** Error counts inflated by matching exit code mentions in documentation or code files.

### Pitfall 3: Agent Result Text vs Usage Block
**What goes wrong:** Including the `<usage>` block when extracting agent result text.
**Why it happens:** The `<usage>` block is appended to agent tool_result text after the actual result.
**How to avoid:** When checking agent result status (FAILED/ERROR patterns), strip trailing `<usage>...</usage>` block first. When displaying agent results, also strip it.
```python
USAGE_RE = re.compile(r"\s*<usage>.*?</usage>\s*$", re.DOTALL)
def strip_usage(text: str) -> str:
    return USAGE_RE.sub("", text)
```
**Warning signs:** Agent status misclassified because `<usage>` text interferes with first/last line checks.

### Pitfall 4: Messages Without Role
**What goes wrong:** Assuming every message has a `role` field.
**Why it happens:** System messages (type=system) have no role field. Observed: 2 such messages per sample.
**How to avoid:** Per CONTEXT.md flow rules: "No role / type=system -> skip". Check `msg.get("role")` before classifying.
**Warning signs:** KeyError on messages[N]["role"].

### Pitfall 5: Subprocess Test Pattern for Underscore-Named Scripts
**What goes wrong:** Trying to import `cc_session_analyzer` directly in tests leads to import path issues.
**Why it happens:** The project uses subprocess invocation for tests (see test_add_note.py pattern). However, `cc_session_analyzer.py` uses underscores (not kebab-case), making direct import possible.
**How to avoid:** Since the analyzer uses underscore naming, direct import via `importlib.machinery.SourceFileLoader` (project convention from Phase 1) OR subprocess are both viable. Direct import is simpler for testing internal functions.
**Warning signs:** Import failures if the test file can't find the module.

### Pitfall 6: Persisted Path Resolution
**What goes wrong:** Persisted output paths are relative to the session JSON file's parent, not CWD.
**Why it happens:** The `Full output saved to:` line uses paths like `./sample-75mb-216-agents.persisted/toolu_xxx.txt` -- relative to wherever the session was exported.
**How to avoid:** Per CONTEXT.md: "absolute paths directly, relative paths from session JSON file's parent directory." Use `Path(session_file).parent / relative_path`.
**Warning signs:** "File not found" errors when trying to recover persisted outputs that actually exist.

### Pitfall 7: Agent Tool_Use Count Mismatch
**What goes wrong:** Agent count from processes array (216) doesn't match Agent tool_use count in orchestrator (210) or agentId count in tool_results (213).
**Why it happens:** Some agents may be spawned by other agents (nested), some may not complete, some may have multiple returns.
**How to avoid:** Use the `processes` array as the authoritative agent list. The orchestrator Agent tool calls and agentId linkage are supplementary. Fail gracefully when linkage is missing -- show `(unknown)` per CONTEXT.md.
**Warning signs:** "Missing agent" errors when trying to match every process to an orchestrator call.

### Pitfall 8: Text and Tool_Use in Same Message
**What goes wrong:** Assuming text and tool_use blocks never appear in the same assistant message.
**Why it happens:** CONTEXT.md notes this is true in all observed samples (0 combined messages across 4 samples). But it says "handle combined case defensively."
**How to avoid:** Flow classification logic should handle both: if a message has tool_use blocks, emit one line per tool_use. If it also has text, emit a separate text line. Don't assume mutual exclusivity.
**Warning signs:** Missing tool calls or text in flow output.

## Code Examples

### Session JSON Top-Level Structure (from empirical analysis)
```python
# Verified structure from 4 sample files
{
    "session": {
        "id": str,           # Session UUID
        "projectPath": str,  # Absolute path
        "createdAt": str,    # ISO 8601
        "hasSubagents": bool,
        "messageCount": int,
        "contextConsumption": dict,  # Token usage breakdown
        # ... other metadata
    },
    "messages": [            # Orchestrator messages
        {
            "uuid": str,
            "timestamp": str,    # ISO 8601, always present
            "role": str,         # "user" | "assistant" (missing on system messages)
            "type": str,         # "user" | "assistant" | "system"
            "content": list,     # Content blocks
            "toolCalls": list,   # Redundant with content tool_use blocks
            "toolResults": list, # Redundant with content tool_result blocks
            # ... other fields
        }
    ],
    "chunks": list,          # ALWAYS DROP -- duplicate data, 53% of size
    "processes": [           # Agent processes
        {
            "id": str,          # 17-char hex, e.g. "afd61812c0eb385cc"
            "startTime": str,   # ISO 8601
            "endTime": str,     # ISO 8601
            "durationMs": int,
            "metrics": {
                "totalTokens": int,
                "inputTokens": int,
                "outputTokens": int,
                # ...
            },
            "messages": list,   # Same structure as orchestrator messages
            "isParallel": bool,
            "isOngoing": bool,
        }
    ],
    "metrics": {
        "durationMs": int,
        "totalTokens": int,
        "inputTokens": int,
        "outputTokens": int,
        "cacheReadTokens": int,
        "messageCount": int,
    }
}
```

### Agent Tool_Result with agentId Pattern
```python
# Actual format observed in all 4 samples:
# The agent's result text, followed by:
# "agentId: <17-char-hex> (for resuming to continue this agent's work if needed)"
# "<usage>total_tokens: N\ntool_uses: N\nduration_ms: N</usage>"

# Extraction pattern:
AGENT_ID_RE = re.compile(r"agentId:\s*([a-f0-9]+)")
USAGE_BLOCK_RE = re.compile(r"\s*<usage>.*?</usage>\s*$", re.DOTALL)
```

### Persisted Output Wrapper Structure
```
<persisted-output>
Output too large (102.8KB). Full output saved to: ./sample-75mb-216-agents.persisted/toolu_01ByULtEBjyh9vjCVAPU4pQH.txt

Preview (first 2KB):
     1|**UNITED STATES**
     2|
     ...
</persisted-output>
```

### Import Pattern for Compactor
```python
# cc_session_analyzer.py imports cc_session_compactor.py from same directory
import importlib.util
from pathlib import Path

def _import_compactor():
    """Import the compactor module from the same directory."""
    compactor_path = Path(__file__).parent / "cc_session_compactor.py"
    spec = importlib.util.spec_from_file_location("cc_session_compactor", compactor_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Or simpler if both files are in the same directory and invoked from there:
# Just use: from cc_session_compactor import slim, validate_schema
# But importlib is safer for any working directory.
```

### install.sh Pattern for Session Analyzer
```bash
# Follows data-provider pattern: command + script copied to target
# No agents directory (analyzer is a Python CLI, not an LLM agent)
# No project scaffolding (no .mg/ directory needed)
# Sed resolution: {SCRIPTS_DIR} placeholder in command .md

SUPPORT_DIR="${TARGET_DIR}/session-analyzer"
mkdir -p "${SUPPORT_DIR}"
cp "${SCRIPT_DIR}/cc_session_compactor.py" "${SUPPORT_DIR}/"
cp "${SCRIPT_DIR}/cc_session_analyzer.py" "${SUPPORT_DIR}/"
chmod +x "${SUPPORT_DIR}/"*.py

# Resolve {SCRIPTS_DIR} in command file
SCRIPTS_ABSOLUTE="${SUPPORT_DIR}"
sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "${COMMANDS_DIR}/analyze-session.md"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Open full session in editor | Compactor reduces to manageable size | Pre-phase 9 | Still loses detail; analyzer preserves full data with selective access |
| Single-pass reduction | Iterative query tool | Phase 9 | Claude can ask specific questions about 75MB sessions |
| Broad error markers | Curated high-confidence patterns | Phase 9 | Fewer false positives in error detection |

**Deprecated/outdated:**
- `reduce_cc_session_export.py`: Renamed to `cc_session_compactor.py` (SAN-01). No backwards compatibility maintained.

## Open Questions

1. **Combined text+tool_use messages**
   - What we know: Zero instances found across 4 samples (1MB, 7MB, 18MB, 75MB)
   - What's unclear: Whether future CC versions will produce combined messages
   - Recommendation: Handle defensively per CONTEXT.md -- emit both text and tool_use lines from same message

2. **Agent result status patterns**
   - What we know: FAILED/ERROR/PLAN FAILED/PLAN COMPLETE patterns specified in CONTEXT.md. Zero matches found in the 75MB sample (216 agents, all succeeded).
   - What's unclear: Exact format when agents do fail (no failing sample available)
   - Recommendation: Implement pattern matching as specified, classify unknown as "ok" per CONTEXT.md. Test with synthetic data.

3. **18MB sample persisted outputs**
   - What we know: 18MB sample exists as .tar.gz but no .persisted directory extracted
   - What's unclear: Whether it has persisted outputs
   - Recommendation: Use 1MB and 75MB samples (both have .persisted dirs) for persisted recovery tests

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (from pyproject.toml dev deps) |
| Config file | None -- needs conftest.py for --slow flag (Wave 0) |
| Quick run command | `python3 -m pytest session-analyzer/tests/ -x -q` |
| Full suite command | `python3 -m pytest session-analyzer/tests/ --slow -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAN-01 | Compactor renamed, functionality preserved | unit | `python3 -m pytest session-analyzer/tests/test_compactor_rename.py -x` | Wave 0 |
| SAN-02 | Load JSON, drop chunks | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::test_load_drops_chunks -x` | Wave 0 |
| SAN-03 | Overview output sections | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py -x` | Wave 0 |
| SAN-04 | Errors with context, paginated | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py -x` | Wave 0 |
| SAN-05 | Flow mechanical classification | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_flow.py -x` | Wave 0 |
| SAN-06 | Agent deep dive | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py -x` | Wave 0 |
| SAN-07 | Agent-list | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py::TestAgentList -x` | Wave 0 |
| SAN-08 | Msg command | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py -x` | Wave 0 |
| SAN-09 | Search with recovery | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_search.py -x` | Wave 0 |
| SAN-10 | Export delegates to compactor | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_export.py -x` | Wave 0 |
| SAN-11 | Pagination flags and footer | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_pagination.py -x` | Wave 0 |
| SAN-12 | Error detection patterns | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestErrorDetection -x` | Wave 0 |
| SAN-13 | Noise filtering | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestNoiseFiltering -x` | Wave 0 |
| SAN-14 | Agent-to-process linkage | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_flow.py::TestAgentLinkage -x` | Wave 0 |
| SAN-15 | Persisted output recovery | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py::TestPersistedRecovery -x` | Wave 0 |
| SAN-16 | Ambiguous prefix | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py::TestAmbiguousPrefix -x` | Wave 0 |
| SAN-17 | Search scope filters | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_search.py::TestSearchScope -x` | Wave 0 |
| SAN-18 | No ANSI colors | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::test_no_ansi -x` | Wave 0 |
| SAN-19 | Slash command + tool.toml + install.sh | manual | Verify file exists and installs correctly | Wave 0 |
| SAN-20 | Dual mode command | manual | Run command with and without goal argument | N/A |
| SAN-21 | Pytest suite with --slow | unit | `python3 -m pytest session-analyzer/tests/ --slow -x -q` | Wave 0 |
| SAN-22 | Independent error detection | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestIndependentDetection -x` | Wave 0 |
| SAN-23 | Contextual commands | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::TestContextualCommands -x` | Wave 0 |
| SAN-24 | Summary vs content modes | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py::TestDisplayModes -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest session-analyzer/tests/ -x -q --tb=short`
- **Per wave merge:** `python3 -m pytest session-analyzer/tests/ --slow -x -q --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `session-analyzer/tests/__init__.py` -- package marker
- [ ] `session-analyzer/tests/conftest.py` -- `--slow` pytest flag, sample path fixtures, skip logic for missing samples
- [ ] All test files listed above -- none exist yet
- [ ] pyproject.toml update: add `[tool.pytest.ini_options]` with `markers = ["slow: marks tests requiring large sample files"]`

## Sources

### Primary (HIGH confidence)
- Empirical analysis of 4 sample session files (1MB, 7MB, 18MB, 75MB) in `session-analyzer/samples/`
- Existing `cc_session_compactor.py` (885 lines) -- verified structure, imports, patterns
- Existing install.sh scripts (12 tools) -- verified patterns for tool anatomy
- Existing tool.toml files (12 tools) -- verified format
- Existing test files (create-docs, install, permission-hooks) -- verified test patterns
- pyproject.toml -- verified Python version (3.11+), dev dependencies

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions -- detailed specifications from user discussion session

### Tertiary (LOW confidence)
- None -- all findings verified against actual code and data

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pure stdlib, no external dependencies, all verified
- Architecture: HIGH -- patterns derived from existing codebase and empirical JSON analysis
- Pitfalls: HIGH -- all pitfalls discovered through actual data inspection, not assumed
- Error detection: MEDIUM -- patterns verified in samples but FAILED/ERROR agent status never observed in test data

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (stable -- CC export format changes infrequently)
