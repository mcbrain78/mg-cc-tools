#!/usr/bin/env python3
"""Query Claude Code session exports for analysis.

Stateless CLI tool that loads session JSON, drops chunks, and provides
subcommands for navigating sessions of any size via pagination.

Usage:
    python3 cc_session_analyzer.py SESSION.json                  # overview (default)
    python3 cc_session_analyzer.py SESSION.json overview         # explicit overview
    python3 cc_session_analyzer.py SESSION.json errors           # paginated error list
    python3 cc_session_analyzer.py SESSION.json flow             # orchestrator decision trace
    python3 cc_session_analyzer.py SESSION.json agent-list       # all agents summary
    python3 cc_session_analyzer.py SESSION.json agent <prefix>   # single agent deep dive
    python3 cc_session_analyzer.py SESSION.json msg <N>          # single message with context
    python3 cc_session_analyzer.py SESSION.json search <pattern> # search tool I/O and text
    python3 cc_session_analyzer.py SESSION.json export           # delegate to compactor
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 20

NOISE_PATTERNS = [
    "exceeds maximum allowed tokens",
    "File has not been read yet",
    "File does not exist",
]

AGENT_ID_RE = re.compile(r"agentId:\s*([a-f0-9]+)")
USAGE_BLOCK_RE = re.compile(r"\s*<usage>.*?</usage>\s*$", re.DOTALL)
EXIT_CODE_RE = re.compile(r"^Exit code [1-9]", re.MULTILINE)
PERSISTED_RE = re.compile(r"<persisted-output>(.*?)</persisted-output>", re.DOTALL)
PERSISTED_PATH_RE = re.compile(r"Full output saved to:\s*(.+)")
PERSISTED_PREVIEW_RE = re.compile(
    r"Preview \(first \d+.*?\):\n(.*?)(?:</persisted-output>|$)", re.DOTALL
)


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def load_session(path: str) -> dict:
    """Load session JSON and drop chunks (always duplicate data)."""
    with open(path) as f:
        data = json.load(f)

    for key in ("session", "messages", "processes", "metrics"):
        if key not in data:
            print(
                f"Error: missing required key '{key}' -- not a CC session export",
                file=sys.stderr,
            )
            sys.exit(1)

    data.pop("chunks", None)
    return data


def extract_text(content) -> str:
    """Extract text from content (string or list of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def strip_usage(text: str) -> str:
    """Remove trailing <usage>...</usage> block from text."""
    return USAGE_BLOCK_RE.sub("", text)


# ---------------------------------------------------------------------------
# Error detection (independent of compactor -- SAN-22)
# ---------------------------------------------------------------------------

def _is_noise(text: str) -> bool:
    """Check if error text matches a benign noise pattern."""
    return any(noise in text for noise in NOISE_PATTERNS)


def detect_errors(messages: list) -> list:
    """Scan tool_result content blocks for real errors.

    Returns list of error dicts: {msg_index, context, message}.
    Only scans tool_result blocks in user messages (never assistant text).
    """
    errors = []

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role != "user":
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue

            text = extract_text(block.get("content", ""))
            is_err = False
            error_text = ""

            # Primary signal: is_error flag (snake_case)
            if block.get("is_error"):
                if _is_noise(text):
                    continue
                is_err = True
                error_text = text

            if not is_err:
                if not text:
                    continue
                if _is_noise(text):
                    continue

                # Python traceback
                if "Traceback (most recent call last)" in text:
                    is_err = True
                    error_text = text

                # Bash exit code (standalone line)
                elif EXIT_CODE_RE.search(text):
                    is_err = True
                    error_text = text

            if is_err:
                # Find preceding assistant message for context snippet
                context = _find_context(messages, i)
                errors.append({
                    "msg_index": i,
                    "context": context,
                    "message": error_text[:120] if len(error_text) > 120 else error_text,
                })

    return errors


def _find_context(messages: list, error_index: int) -> str:
    """Find the preceding assistant message text for context."""
    for j in range(error_index - 1, -1, -1):
        msg = messages[j]
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            content = msg.get("content")
            text = extract_text(content) if content else ""
            text = strip_usage(text).strip()
            if text:
                return text[:80]
    return ""


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------

def build_agent_map(data: dict) -> dict:
    """Map process IDs to process entries for fast lookup."""
    return {
        proc["id"]: proc
        for proc in data.get("processes", [])
        if isinstance(proc, dict) and "id" in proc
    }


def extract_agent_id(text: str) -> str | None:
    """Extract agentId from agent tool_result content."""
    m = AGENT_ID_RE.search(text)
    return m.group(1) if m else None


def link_orchestrator_to_agents(data: dict) -> dict:
    """Map tool_use_id -> process_id by parsing agentId from tool_results.

    Returns dict mapping tool_use_id to process_id (or None if not found).
    """
    agent_map = build_agent_map(data)
    linkage = {}

    for msg in data.get("messages", []):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue

            text = extract_text(block.get("content", ""))
            agent_id = extract_agent_id(text)
            if agent_id and agent_id in agent_map:
                tool_use_id = block.get("tool_use_id", "")
                if tool_use_id:
                    linkage[tool_use_id] = agent_id

    return linkage


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def add_pagination_args(subparser):
    """Add --offset, --limit, --all flags to a subparser."""
    subparser.add_argument("--offset", type=int, default=0, help="Skip first N items")
    subparser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Items per page")
    subparser.add_argument("--all", action="store_true", default=False, help="Show all items")


def paginate(items: list, args, command_prefix: str) -> tuple:
    """Apply pagination and generate footer.

    Returns (page, footer_string).
    """
    total = len(items)
    if getattr(args, "all", False):
        return items, f"--- {total} of {total} items ---"

    offset = getattr(args, "offset", 0)
    limit = getattr(args, "limit", DEFAULT_LIMIT)
    page = items[offset : offset + limit]
    shown = offset + len(page)

    if shown < total:
        next_offset = offset + limit
        footer = f"--- {shown} of {total} items. Next: {command_prefix} --offset {next_offset} ---"
    else:
        footer = f"--- {shown} of {total} items ---"

    return page, footer


# ---------------------------------------------------------------------------
# Persisted output helpers
# ---------------------------------------------------------------------------

def count_persisted(messages: list) -> tuple:
    """Count persisted outputs: returns (total, recoverable)."""
    total = 0
    recoverable = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue

            text = extract_text(block.get("content", ""))
            if "<persisted-output>" in text:
                total += 1
                path_match = PERSISTED_PATH_RE.search(text)
                if path_match:
                    raw_path = path_match.group(1).strip()
                    p = Path(raw_path)
                    if p.exists():
                        recoverable += 1

    return total, recoverable


def recover_persisted(text: str, session_dir: Path) -> str:
    """Replace persisted output wrapper with actual content or cleaned preview."""
    if "<persisted-output>" not in text:
        return text

    # Extract path from "Full output saved to: <path>" line
    path_match = PERSISTED_PATH_RE.search(text)
    if not path_match:
        return (
            text.replace("<persisted-output>", "")
            .replace("</persisted-output>", "")
            .strip()
        )

    raw_path = path_match.group(1).strip()
    p = Path(raw_path)
    if not p.is_absolute():
        p = session_dir / p

    if p.exists():
        return p.read_text()

    # Fall back to preview text
    preview_match = PERSISTED_PREVIEW_RE.search(text)
    if preview_match:
        return preview_match.group(1).strip()

    return (
        text.replace("<persisted-output>", "")
        .replace("</persisted-output>", "")
        .strip()
    )


# ---------------------------------------------------------------------------
# Overview command
# ---------------------------------------------------------------------------

def cmd_overview(data: dict, session_file: str, args) -> str:
    """Produce complete session overview.

    Returns plain text string (no ANSI codes).
    """
    session = data.get("session", {})
    metrics = data.get("metrics", {})
    messages = data.get("messages", [])
    processes = data.get("processes", [])

    lines = []

    # --- Session metadata ---
    lines.append("=== Session ===")
    lines.append(f"  ID: {session.get('id', 'unknown')}")
    lines.append(f"  Project: {session.get('projectPath', 'unknown')}")

    # createdAt may be epoch ms or ISO string
    created_at = session.get("createdAt", "")
    if isinstance(created_at, (int, float)):
        try:
            dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
            lines.append(f"  Created: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except (OSError, ValueError):
            lines.append(f"  Created: {created_at}")
    else:
        lines.append(f"  Created: {created_at}")

    duration_ms = metrics.get("durationMs", 0)
    duration_s = duration_ms / 1000
    if duration_s >= 3600:
        lines.append(f"  Duration: {duration_s / 3600:.1f}h")
    elif duration_s >= 60:
        lines.append(f"  Duration: {duration_s / 60:.1f}min")
    else:
        lines.append(f"  Duration: {duration_s:.0f}s")

    total_tokens = metrics.get("totalTokens", 0)
    lines.append(f"  Tokens: {total_tokens:,}")
    lines.append(f"  Messages: {metrics.get('messageCount', len(messages))}")
    lines.append(f"  Has subagents: {session.get('hasSubagents', False)}")

    # --- Size ---
    lines.append("")
    lines.append("=== Size ===")
    try:
        file_size = os.path.getsize(session_file)
        if file_size >= 1_048_576:
            lines.append(f"  File: {file_size / 1_048_576:.1f}MB")
        else:
            lines.append(f"  File: {file_size / 1024:.0f}KB")
    except OSError:
        lines.append("  File: unknown")
    lines.append("  (chunks dropped at load time)")

    # Estimate process/orchestrator sizes
    proc_msg_count = sum(
        len(p.get("messages", [])) for p in processes if isinstance(p, dict)
    )
    orch_msg_count = len(messages)
    lines.append(f"  Orchestrator messages: {orch_msg_count}")
    lines.append(f"  Agent messages: {proc_msg_count}")

    # --- Timeline ---
    lines.append("")
    lines.append("=== Timeline ===")
    timestamps = []
    for msg in messages:
        if isinstance(msg, dict) and "timestamp" in msg:
            timestamps.append(msg["timestamp"])

    if timestamps:
        lines.append(f"  Start: {timestamps[0]}")
        lines.append(f"  End:   {timestamps[-1]}")
    else:
        lines.append("  No timestamps available")

    # First error timestamp
    errors = detect_errors(messages)
    if errors:
        first_err_idx = errors[0]["msg_index"]
        first_err_msg = messages[first_err_idx] if first_err_idx < len(messages) else {}
        first_err_ts = first_err_msg.get("timestamp", "unknown")
        lines.append(f"  First error: {first_err_ts}")

    # --- Orchestrator stats ---
    lines.append("")
    lines.append("=== Orchestrator ===")
    lines.append(f"  Messages: {orch_msg_count}")

    # Count tool_use by tool name
    tool_counts: dict[str, int] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1

    total_tool_uses = sum(tool_counts.values())
    lines.append(f"  Tool calls: {total_tool_uses}")
    if tool_counts:
        sorted_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
        for name, count in sorted_tools:
            lines.append(f"    {name}: {count}")

    # --- Agents ---
    has_agents = len(processes) > 0
    if has_agents:
        lines.append("")
        lines.append("=== Agents ===")
        lines.append(f"  Total: {len(processes)}")

        # Count failed/succeeded by checking agent result status
        failed = 0
        succeeded = 0
        for proc in processes:
            if not isinstance(proc, dict):
                continue
            proc_messages = proc.get("messages", [])
            status = _classify_agent_status(proc_messages)
            if status == "failed":
                failed += 1
            else:
                succeeded += 1
        lines.append(f"  Succeeded: {succeeded}")
        lines.append(f"  Failed: {failed}")

    # --- Errors ---
    lines.append("")
    lines.append(f"=== Errors ({len(errors)}) ===")
    if errors:
        for err in errors:
            idx = err["msg_index"]
            ctx = err["context"]
            msg_text = err["message"]
            # Truncate for overview display
            msg_short = msg_text.replace("\n", " ")
            if len(msg_short) > 120:
                msg_short = msg_short[:117] + "..."
            lines.append(f"  msg[{idx}] {msg_short}")
            if ctx:
                lines.append(f"         context: {ctx}")
    else:
        lines.append("  None")

    # --- Heaviest agents ---
    if has_agents:
        lines.append("")
        lines.append("=== Heaviest Agents (top 3) ===")
        agent_sizes = []
        for proc in processes:
            if not isinstance(proc, dict):
                continue
            proc_messages = proc.get("messages", [])
            msg_count = len(proc_messages)
            # Count tool uses per agent
            agent_tool_counts: dict[str, int] = {}
            for m in proc_messages:
                if not isinstance(m, dict):
                    continue
                c = m.get("content")
                if not isinstance(c, list):
                    continue
                for block in c:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tn = block.get("name", "unknown")
                        agent_tool_counts[tn] = agent_tool_counts.get(tn, 0) + 1
            agent_sizes.append((proc.get("id", "?"), msg_count, agent_tool_counts))

        agent_sizes.sort(key=lambda x: -x[1])
        for pid, msg_count, tc in agent_sizes[:3]:
            top_tools = sorted(tc.items(), key=lambda x: -x[1])[:3]
            tool_str = ", ".join(f"{n}:{c}" for n, c in top_tools)
            lines.append(f"  {pid[:12]}  msgs={msg_count}  tools: {tool_str}")

    # --- Persisted outputs ---
    lines.append("")
    lines.append("=== Persisted Outputs ===")
    session_dir = Path(session_file).parent
    total_persisted, recoverable_persisted = count_persisted(messages)
    # Also count in agent messages
    for proc in processes:
        if not isinstance(proc, dict):
            continue
        pt, pr = count_persisted(proc.get("messages", []))
        total_persisted += pt
        recoverable_persisted += pr

    lines.append(f"  Total: {total_persisted}")
    lines.append(f"  Recoverable: {recoverable_persisted}")

    # --- Contextual commands ---
    lines.append("")
    lines.append("=== Commands ===")
    sf = session_file

    if errors:
        lines.append(f"  errors      -- List all errors with context")
        lines.append(f"               {sf} errors")

    lines.append(f"  flow        -- Orchestrator decision trace")
    lines.append(f"               {sf} flow")

    if has_agents:
        lines.append(f"  agent-list  -- Summary of all agents")
        lines.append(f"               {sf} agent-list")
        lines.append(f"  agent <id>  -- Deep dive into a single agent")
        lines.append(f"               {sf} agent <prefix>")

    lines.append(f"  msg <N>     -- Single message with context")
    lines.append(f"               {sf} msg 5")
    lines.append(f"  search <p>  -- Search tool I/O and text")
    lines.append(f"               {sf} search \"pattern\"")
    lines.append(f"  export      -- Export via compactor")
    lines.append(f"               {sf} export")

    return "\n".join(lines)


def _classify_agent_status(messages: list) -> str:
    """Classify agent status from its messages. Returns 'failed' or 'ok'."""
    if not messages:
        return "ok"

    # Check last assistant message
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        text = extract_text(msg.get("content", ""))
        text = strip_usage(text).strip()
        if not text:
            continue
        first_line = text.split("\n")[0].strip().upper()
        last_line = text.rsplit("\n", 1)[-1].strip().upper()
        if any(
            kw in first_line or kw in last_line
            for kw in ("FAILED", "ERROR", "PLAN FAILED")
        ):
            return "failed"
        break

    # Check tool_result is_error on the last tool_result
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("is_error"):
                    return "failed"

    return "ok"


# ---------------------------------------------------------------------------
# Stub commands (implemented in plans 02-04)
# ---------------------------------------------------------------------------

def cmd_errors(data, session_file, args):
    print("Not yet implemented: errors")


def cmd_flow(data, session_file, args):
    print("Not yet implemented: flow")


def cmd_agent(data, session_file, args):
    print("Not yet implemented: agent")


def cmd_agent_list(data, session_file, args):
    print("Not yet implemented: agent-list")


def cmd_msg(data, session_file, args):
    print("Not yet implemented: msg")


def cmd_search(data, session_file, args):
    print("Not yet implemented: search")


def cmd_export(data, session_file, args):
    print("Not yet implemented: export")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMANDS = {
    "overview": cmd_overview,
    "errors": cmd_errors,
    "flow": cmd_flow,
    "agent": cmd_agent,
    "agent-list": cmd_agent_list,
    "msg": cmd_msg,
    "search": cmd_search,
    "export": cmd_export,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query Claude Code session exports",
    )
    parser.add_argument("session_file", help="Path to session JSON export")
    subparsers = parser.add_subparsers(dest="command")

    # overview (default, not paginated)
    subparsers.add_parser("overview", help="Session summary with contextual commands")

    # errors (paginated)
    sub = subparsers.add_parser("errors", help="Error list with context")
    add_pagination_args(sub)

    # flow (paginated)
    sub = subparsers.add_parser("flow", help="Orchestrator decision trace")
    add_pagination_args(sub)

    # agent (paginated, takes prefix)
    sub = subparsers.add_parser("agent", help="Single agent deep dive")
    sub.add_argument("prefix", help="Agent ID prefix")
    add_pagination_args(sub)

    # agent-list (paginated)
    sub = subparsers.add_parser("agent-list", help="Summary of all agents")
    add_pagination_args(sub)

    # msg (not paginated)
    sub = subparsers.add_parser("msg", help="Single message with context")
    sub.add_argument("index", type=int, help="Message index")
    sub.add_argument("agent_prefix", nargs="?", default=None, help="Optional agent ID prefix")

    # search (paginated)
    sub = subparsers.add_parser("search", help="Search tool I/O and text")
    sub.add_argument("pattern", help="Search pattern (regex)")
    sub.add_argument("--scope", default=None, help="Scope: orchestrator, agents, agent:<prefix>")
    add_pagination_args(sub)

    # export (not paginated)
    sub = subparsers.add_parser("export", help="Export via compactor")
    sub.add_argument("--level", default="l2-compact", help="Compactor level")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.session_file:
        parser.print_help()
        sys.exit(1)

    data = load_session(args.session_file)

    # Default to overview when no subcommand given
    command = args.command or "overview"

    handler = COMMANDS.get(command)
    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

    result = handler(data, args.session_file, args)
    if isinstance(result, str):
        print(result)


if __name__ == "__main__":
    main()
