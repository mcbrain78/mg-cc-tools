#!/usr/bin/env python3
"""Query Claude Code session exports for analysis.

Stateless CLI tool that loads session JSON, drops chunks, and provides
subcommands for navigating sessions of any size via pagination.

Usage:
    python3 cc_transcript_analyzer.py SESSION.json                  # overview (default)
    python3 cc_transcript_analyzer.py SESSION.json overview         # explicit overview
    python3 cc_transcript_analyzer.py SESSION.json errors           # paginated error list
    python3 cc_transcript_analyzer.py SESSION.json flow             # orchestrator decision trace
    python3 cc_transcript_analyzer.py SESSION.json agent-list       # all agents summary
    python3 cc_transcript_analyzer.py SESSION.json agent <prefix>   # single agent deep dive
    python3 cc_transcript_analyzer.py SESSION.json msg <N>          # single message with context
    python3 cc_transcript_analyzer.py SESSION.json search <pattern> # search tool I/O and text
    python3 cc_transcript_analyzer.py SESSION.json export           # delegate to compactor
"""
import argparse
import importlib.util
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
# Errors command
# ---------------------------------------------------------------------------

def _detect_errors_detailed(messages: list) -> list:
    """Like detect_errors but returns full text and error type classification.

    Returns list of dicts: {msg_index, error_type, context, full_text}.
    """
    errors = []

    for i, msg in enumerate(messages):
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
            error_type = None

            if block.get("is_error"):
                if _is_noise(text):
                    continue
                # Determine specific type
                if "Traceback (most recent call last)" in text:
                    error_type = "Python traceback"
                elif EXIT_CODE_RE.search(text):
                    error_type = "Bash exit code"
                else:
                    error_type = "is_error flag"
            else:
                if not text or _is_noise(text):
                    continue
                if "Traceback (most recent call last)" in text:
                    error_type = "Python traceback"
                elif EXIT_CODE_RE.search(text):
                    error_type = "Bash exit code"

            if error_type:
                context = _find_context(messages, i)
                errors.append({
                    "msg_index": i,
                    "error_type": error_type,
                    "context": context,
                    "full_text": text,
                })

    return errors


def cmd_errors(data, session_file, args):
    """Show all errors with full context, paginated."""
    messages = data.get("messages", [])
    session_dir = Path(session_file).parent
    errors = _detect_errors_detailed(messages)

    if not errors:
        return "No errors detected."

    # Build display entries
    entries = []
    for err in errors:
        lines = []
        lines.append(f"[msg[{err['msg_index']}]] {err['error_type']}")
        if err["context"]:
            lines.append(f"Prompt: {err['context']}")

        # Full error text -- recover persisted if needed (SAN-24)
        full_text = recover_persisted(err["full_text"], session_dir)
        text_lines = full_text.split("\n")
        if len(text_lines) > 40:
            remaining = len(text_lines) - 40
            text_lines = text_lines[:40]
            text_lines.append(f"... ({remaining} more lines)")
        lines.append("\n".join(text_lines))

        entries.append("\n".join(lines))

    # Apply pagination to the entry list
    sf = session_file
    page, footer = paginate(entries, args, f"{sf} errors")

    output_lines = []
    for entry in page:
        output_lines.append(entry)
        output_lines.append("")  # blank separator

    output_lines.append(footer)
    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Flow command
# ---------------------------------------------------------------------------

def _format_timestamp(msg: dict) -> str:
    """Extract HH:MM:SS from message timestamp, or --:--:-- if absent."""
    ts = msg.get("timestamp", "")
    if not ts:
        return "--:--:--"
    # Timestamp format: 2026-03-18T12:06:14.653Z
    # Extract HH:MM:SS
    if "T" in ts:
        time_part = ts.split("T")[1]
        # Remove Z and fractional seconds
        time_part = time_part.replace("Z", "")
        if "." in time_part:
            time_part = time_part.split(".")[0]
        return time_part
    return "--:--:--"


def _input_summary(tool_input, max_len: int = 60) -> str:
    """Create a summary of tool input for flow display."""
    if isinstance(tool_input, dict):
        # Common patterns
        if "command" in tool_input:
            s = str(tool_input["command"])
        elif "file_path" in tool_input:
            s = str(tool_input["file_path"])
        elif "pattern" in tool_input:
            s = str(tool_input["pattern"])
        elif "content" in tool_input:
            s = str(tool_input["content"])[:max_len]
        else:
            # Use first value
            vals = list(tool_input.values())
            s = str(vals[0]) if vals else ""
    elif isinstance(tool_input, str):
        s = tool_input
    else:
        s = str(tool_input)

    s = s.replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def cmd_flow(data, session_file, args):
    """Show orchestrator decision trace, one line per action."""
    messages = data.get("messages", [])
    linkage = link_orchestrator_to_agents(data)
    agent_map = build_agent_map(data)

    flow_lines = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        mtype = msg.get("type")

        # Skip system messages and messages with no role
        if not role or mtype == "system":
            continue

        ts = _format_timestamp(msg)
        content = msg.get("content")

        if role == "user":
            # Check for content blocks
            if isinstance(content, list):
                has_tool_result = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                )
                if has_tool_result:
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_result":
                            continue
                        tool_use_id = block.get("tool_use_id", "")
                        # Check if Agent return
                        if tool_use_id in linkage:
                            process_id = linkage[tool_use_id]
                            proc = agent_map.get(process_id, {})
                            # Derive status from result
                            result_text = extract_text(block.get("content", ""))
                            result_text = strip_usage(result_text).strip()
                            if block.get("is_error"):
                                status = "error"
                            elif any(kw in result_text[:200].upper() for kw in ("FAILED", "ERROR", "PLAN FAILED")):
                                status = "failed"
                            else:
                                status = "ok"
                            pid_prefix = process_id[:8] if process_id else "????????"
                            flow_lines.append(f"{ts} agent-return {pid_prefix}: {status}")
                        else:
                            # Non-agent tool_result -- skip unless error
                            if block.get("is_error"):
                                err_text = extract_text(block.get("content", ""))
                                if not _is_noise(err_text):
                                    err_short = err_text.replace("\n", " ")[:60]
                                    flow_lines.append(f"{ts} tool-error: {err_short}")
                else:
                    # Text content
                    text = extract_text(content) if isinstance(content, list) else ""
                    if not text and isinstance(content, list):
                        # Try string blocks
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                text = b.get("text", "")
                                break
                    if text:
                        text = text.replace("\n", " ").strip()
                        if len(text) > 80:
                            text = text[:77] + "..."
                        flow_lines.append(f"{ts} user: {text}")
            elif isinstance(content, str):
                text = content.replace("\n", " ").strip()
                if len(text) > 80:
                    text = text[:77] + "..."
                flow_lines.append(f"{ts} user: {text}")

        elif role == "assistant":
            if not isinstance(content, list):
                continue

            block_types = {
                b.get("type") for b in content if isinstance(b, dict)
            }

            # Check for tool_use blocks
            if "tool_use" in block_types:
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    tool_id = block.get("id", "")

                    if tool_name == "Agent":
                        # Agent call -- show prompt and linked process_id
                        prompt = ""
                        if isinstance(tool_input, dict):
                            prompt = str(tool_input.get("prompt", ""))
                        prompt_short = prompt.replace("\n", " ")[:60]

                        # Find linked process_id
                        pid_prefix = ""
                        for tid, pid in linkage.items():
                            # We need to find which tool_use_id maps to this tool_use
                            # The linkage maps tool_use_id -> process_id
                            # This tool_use block has id == tool_id
                            pass

                        # Check if this tool_use id is in linkage
                        if tool_id in linkage:
                            pid = linkage[tool_id]
                            pid_prefix = pid[:8]
                            proc = agent_map.get(pid, {})
                            dur_ms = proc.get("durationMs", 0)
                            dur_str = _format_duration(dur_ms)
                            flow_lines.append(
                                f"{ts} -> Agent({prompt_short}) [{pid_prefix} {dur_str}]"
                            )
                        else:
                            flow_lines.append(f"{ts} -> Agent({prompt_short})")
                    else:
                        summary = _input_summary(tool_input)
                        flow_lines.append(f"{ts} -> {tool_name}({summary})")

            elif "text" in block_types:
                # Text-only (no tool_use) -- skip if also has thinking only
                has_text = False
                text_content = ""
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        has_text = True
                        text_content = block.get("text", "")
                        break
                if has_text and text_content.strip():
                    text_content = text_content.replace("\n", " ").strip()
                    if len(text_content) > 80:
                        text_content = text_content[:77] + "..."
                    flow_lines.append(f"{ts} asst: {text_content}")

            elif block_types == {"thinking"}:
                # Thinking-only -- skip
                continue

    if not flow_lines:
        return "No flow lines generated."

    sf = session_file
    page, footer = paginate(flow_lines, args, f"{sf} flow")

    output = "\n".join(page)
    output += "\n" + footer
    return output


def _format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms <= 0:
        return "0ms"
    if ms < 1000:
        return f"{ms}ms"
    s = ms / 1000
    if s < 60:
        return f"{s:.0f}s"
    m = s / 60
    remaining_s = s % 60
    return f"{m:.0f}m {remaining_s:.0f}s"


def resolve_agent_prefix(data: dict, prefix: str) -> tuple:
    """Resolve an agent ID prefix to a single (process_entry, process_id).

    Exits with error if zero or multiple matches (SAN-16).
    """
    matches = []
    for proc in data.get("processes", []):
        if not isinstance(proc, dict):
            continue
        pid = proc.get("id", "")
        if pid.startswith(prefix):
            matches.append((proc, pid))

    if len(matches) == 0:
        print(f"No agent matching prefix '{prefix}'")
        sys.exit(1)
    elif len(matches) > 1:
        ids = ", ".join(pid[:8] for _, pid in matches[:10])
        if len(matches) > 10:
            ids += f", ... ({len(matches)} total)"
        print(f"Ambiguous prefix '{prefix}' -- matches {ids}. Use a longer prefix.")
        sys.exit(1)

    return matches[0]


def cmd_agent(data, session_file, args):
    """Show single agent deep dive with interleaved tool calls and reasoning."""
    proc, pid = resolve_agent_prefix(data, args.prefix)
    messages = proc.get("messages", [])
    msg_count = len(messages)

    # Status
    if proc.get("isOngoing"):
        status = "active"
    else:
        status = _classify_agent_status(messages)

    # Duration
    dur_ms = proc.get("durationMs", 0)
    dur_str = _format_duration(dur_ms)

    lines = []
    lines.append(f"Agent {pid[:8]} -- {status} -- {dur_str} -- {msg_count} messages")

    # Prompt: first user message content
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            text = extract_text(msg.get("content", ""))
            text = strip_usage(text).strip()
            if text:
                lines.append("")
                lines.append("Prompt:")
                lines.append(text)
            break

    lines.append("")

    # Build interleaved display entries
    entries = []
    # Track tool_use_id -> tool_name for matching results
    pending_tools = {}

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        content = msg.get("content")

        if role == "assistant":
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    text = strip_usage(block.get("text", "")).strip()
                    if not text:
                        continue
                    text_lines = text.split("\n")
                    if len(text_lines) > 20:
                        remaining = len(text_lines) - 20
                        display = "\n".join(text_lines[:20])
                        display += f"\n... ({remaining} more lines, use msg {pid[:8]} {idx} for full)"
                    else:
                        display = text
                    entries.append(f"msg[{idx}] asst: {display}")
                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    summary = _input_summary(tool_input, 80)
                    tool_id = block.get("id", "")
                    if tool_id:
                        pending_tools[tool_id] = tool_name
                    entries.append(f"msg[{idx}] -> {tool_name}({summary})")

        elif role == "user":
            if not isinstance(content, list):
                # Plain text user message
                text = extract_text(content) if content else ""
                if text:
                    text_short = text.replace("\n", " ").strip()
                    if len(text_short) > 80:
                        text_short = text_short[:77] + "..."
                    entries.append(f"msg[{idx}] user: {text_short}")
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    tool_name = pending_tools.pop(tool_use_id, "unknown")
                    text = extract_text(block.get("content", ""))

                    if block.get("is_error"):
                        # Show first 3 lines of error
                        err_lines = text.strip().split("\n")[:3]
                        err_display = "\n".join(err_lines)
                        entries.append(f"msg[{idx}] <- {tool_name}: error\n{err_display}")
                    elif "<persisted-output>" in text:
                        # Extract size hint
                        size_match = re.search(r"Output too large \(([^)]+)\)", text)
                        size_str = size_match.group(1) if size_match else "unknown"
                        entries.append(f"msg[{idx}] <- {tool_name}: persisted ({size_str})")
                    else:
                        entries.append(f"msg[{idx}] <- {tool_name}: ok")
                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        text_short = text.replace("\n", " ")
                        if len(text_short) > 80:
                            text_short = text_short[:77] + "..."
                        entries.append(f"msg[{idx}] user: {text_short}")

    if not entries:
        return "No messages in this agent."

    sf = session_file
    page, footer = paginate(entries, args, f"{sf} agent {pid[:8]}")

    output = "\n".join(lines) + "\n" + "\n".join(page) + "\n" + footer
    return output


def cmd_agent_list(data, session_file, args):
    """Show one line per agent with key metrics, paginated."""
    processes = data.get("processes", [])

    if not processes:
        return "No agents in this session."

    entries = []
    for proc in processes:
        if not isinstance(proc, dict):
            continue

        pid = proc.get("id", "????????")
        pid_short = pid[:8]

        # Status
        if proc.get("isOngoing"):
            status = "active"
        else:
            proc_messages = proc.get("messages", [])
            status = _classify_agent_status(proc_messages)

        # Duration
        dur_ms = proc.get("durationMs", 0)
        dur_str = _format_duration(dur_ms)

        # Message count
        msg_count = len(proc.get("messages", []))

        # Tool count -- count tool_use blocks across all assistant messages
        tool_count = 0
        for m in proc.get("messages", []):
            if not isinstance(m, dict):
                continue
            if m.get("role") != "assistant":
                continue
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_count += 1

        # Tokens
        metrics = proc.get("metrics", {})
        total_tokens = metrics.get("totalTokens", 0)

        # Prompt summary -- first 60 chars of first user message text
        prompt_summary = ""
        for m in proc.get("messages", []):
            if not isinstance(m, dict):
                continue
            if m.get("role") != "user":
                continue
            text = extract_text(m.get("content", ""))
            text = text.replace("\n", " ").strip()
            if text:
                if len(text) > 60:
                    prompt_summary = text[:57] + "..."
                else:
                    prompt_summary = text
                break

        entry = (
            f"{pid_short}  {status:6}  {dur_str:>8}  "
            f"{msg_count:>4} msgs  {tool_count:>4} tools  "
            f"{total_tokens:>8,} tok  {prompt_summary}"
        )
        entries.append(entry)

    sf = session_file
    page, footer = paginate(entries, args, f"{sf} agent-list")

    output = "\n".join(page)
    output += "\n" + footer
    return output


def cmd_msg(data, session_file, args):
    """Show single message with +/-2 context, full content (content command)."""
    session_dir = Path(session_file).parent

    # Determine message list
    agent_prefix = getattr(args, "agent", None)
    if agent_prefix:
        proc, pid = resolve_agent_prefix(data, agent_prefix)
        messages = proc.get("messages", [])
        location = f"agent:{pid[:8]}"
    else:
        messages = data.get("messages", [])
        location = "orchestrator"

    idx = args.index
    max_idx = len(messages) - 1
    if idx < 0 or idx > max_idx:
        print(f"Message index {idx} out of range (0-{max_idx})")
        sys.exit(1)

    # Context range: N-2 to N+2
    start = max(0, idx - 2)
    end = min(max_idx, idx + 2)

    lines = []
    lines.append(f"Messages from {location} [{start}-{end}]:")
    lines.append("")

    for i in range(start, end + 1):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "unknown")
        ts = msg.get("timestamp", "")
        marker = " ***" if i == idx else ""
        lines.append(f"--- msg[{i}] {role} {ts}{marker} ---")

        content = msg.get("content")

        if isinstance(content, str):
            text = strip_usage(content).strip()
            lines.append(text)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")

                if btype == "text":
                    text = strip_usage(block.get("text", "")).strip()
                    if text:
                        lines.append(text)

                elif btype == "thinking":
                    # Skip thinking blocks in display
                    continue

                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    lines.append(f"[tool_use] {tool_name}")
                    input_str = json.dumps(tool_input, indent=2)
                    input_lines = input_str.split("\n")
                    if len(input_lines) > 100:
                        lines.extend(input_lines[:100])
                        lines.append(f"... ({len(input_lines) - 100} more lines)")
                    else:
                        lines.extend(input_lines)

                elif btype == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    is_error = block.get("is_error", False)
                    status_str = " (error)" if is_error else ""
                    lines.append(f"[tool_result]{status_str}")
                    text = extract_text(block.get("content", ""))
                    # Content command: recover persisted outputs (SAN-15)
                    text = recover_persisted(text, session_dir)
                    text = strip_usage(text).strip()
                    if text:
                        lines.append(text)

        lines.append("")

    return "\n".join(lines)


def _search_messages(messages: list, pattern, session_dir: Path, location: str) -> list:
    """Search a list of messages for pattern matches.

    Returns list of result entry strings.
    """
    results = []

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue

        content = msg.get("content")
        searchable_parts = []

        if isinstance(content, str):
            searchable_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    searchable_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_input = block.get("input", {})
                    searchable_parts.append(json.dumps(tool_input, indent=2))
                elif btype == "tool_result":
                    text = extract_text(block.get("content", ""))
                    # Content command: recover persisted before matching (SAN-15)
                    text = recover_persisted(text, session_dir)
                    searchable_parts.append(text)

        # Search all parts
        full_text = "\n".join(searchable_parts)
        text_lines = full_text.split("\n")

        matched_lines = []
        for line_idx, line in enumerate(text_lines):
            if pattern.search(line):
                # Gather context: 1 line above and below
                ctx_start = max(0, line_idx - 1)
                ctx_end = min(len(text_lines) - 1, line_idx + 1)
                ctx = []
                for ci in range(ctx_start, ctx_end + 1):
                    if ci == line_idx:
                        ctx.append(f">>> {text_lines[ci]}")
                    else:
                        ctx.append(f"    {text_lines[ci]}")
                matched_lines.append("\n".join(ctx))

        if matched_lines:
            header = f"[{location}] msg[{idx}]"
            entry = header + "\n" + "\n".join(matched_lines)
            results.append(entry)

    return results


def cmd_search(data, session_file, args):
    """Search tool inputs, results, and assistant text with scope filtering."""
    session_dir = Path(session_file).parent

    # Compile regex
    try:
        pattern = re.compile(args.pattern, re.IGNORECASE)
    except re.error as e:
        print(f"Invalid regex pattern: {e}")
        sys.exit(1)

    # Determine scope
    scope = getattr(args, "scope", None)
    results = []

    if scope is None:
        # Default: search everything
        results.extend(
            _search_messages(data.get("messages", []), pattern, session_dir, "orch")
        )
        for proc in data.get("processes", []):
            if not isinstance(proc, dict):
                continue
            pid = proc.get("id", "????????")
            results.extend(
                _search_messages(
                    proc.get("messages", []), pattern, session_dir, f"agent:{pid[:8]}"
                )
            )
    elif scope == "orchestrator":
        results.extend(
            _search_messages(data.get("messages", []), pattern, session_dir, "orch")
        )
    elif scope == "agents":
        for proc in data.get("processes", []):
            if not isinstance(proc, dict):
                continue
            pid = proc.get("id", "????????")
            results.extend(
                _search_messages(
                    proc.get("messages", []), pattern, session_dir, f"agent:{pid[:8]}"
                )
            )
    elif scope.startswith("agent:"):
        prefix = scope[6:]
        proc, pid = resolve_agent_prefix(data, prefix)
        results.extend(
            _search_messages(
                proc.get("messages", []), pattern, session_dir, f"agent:{pid[:8]}"
            )
        )
    else:
        print(f"Unknown scope: {scope}. Use: orchestrator, agents, agent:<prefix>")
        sys.exit(1)

    if not results:
        return "No matches found."

    sf = session_file
    page, footer = paginate(results, args, f"{sf} search \"{args.pattern}\"")

    output = "\n\n".join(page) + "\n\n" + footer
    return output


def _import_compactor():
    """Import the compactor module from the same directory."""
    compactor_path = Path(__file__).parent / "cc_transcript_compactor.py"
    if not compactor_path.exists():
        print(f"Error: compactor not found at {compactor_path}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("cc_transcript_compactor", compactor_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}KB"
    return f"{size_bytes}B"


def cmd_export(data, session_file, args):
    """Export session via compactor with --level support."""
    compactor = _import_compactor()

    # Parse the level value (string from argparse)
    level_str = args.level
    if level_str == "l2-compact":
        level = "l2-compact"
    else:
        try:
            level = int(level_str)
            if level not in range(6):
                print(f"Error: invalid level {level} (expected 0-5 or 'l2-compact')", file=sys.stderr)
                sys.exit(1)
        except ValueError:
            print(f"Error: invalid level '{level_str}' (expected 0-5 or 'l2-compact')", file=sys.stderr)
            sys.exit(1)

    # Reload full JSON -- compactor needs original structure for its reduction logic
    session_path = Path(session_file)
    with open(session_path) as f:
        full_data = json.load(f)

    compactor.validate_schema(full_data)
    original_size = session_path.stat().st_size

    # Apply compactor reduction
    reduced = compactor.slim(full_data, level)

    # Determine output filename using compactor's convention
    if level == "l2-compact":
        output_path = session_path.with_suffix(".l2c.json")
    else:
        output_path = session_path.with_suffix(f".l{level}.json")

    with open(output_path, "w") as f:
        json.dump(reduced, f, indent=2)

    new_size = output_path.stat().st_size
    reduction = (1 - new_size / original_size) * 100 if original_size > 0 else 0

    print(f"Exported to: {output_path} ({_format_size(new_size)}, {reduction:.0f}% reduction)")


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
    sub.add_argument("--agent", default=None, help="Agent ID prefix to view agent process message")

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
