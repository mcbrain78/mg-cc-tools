#!/usr/bin/env python3
"""Convert Claude Code JSONL session files to structured JSON or Markdown.

Reads raw JSONL files from ~/.claude/projects/ and produces either:
- JSON compatible with cc_transcript_analyzer.py / cc_transcript_compactor.py
- Markdown with conversation turns, tool calls, and metrics

Usage:
    python3 cc_transcript_exporter.py <session-id> --format json --output /tmp/out.json
    python3 cc_transcript_exporter.py <session-id> --format md --output /tmp/out.md
    python3 cc_transcript_exporter.py <session-id> --format md --output /tmp/out.md --project /path/to/project
    python3 cc_transcript_exporter.py <session-id> --format md --output /tmp/out.md --truncate 5000
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_DIR = Path.home() / ".claude" / "projects"

# Entry types we care about for conversation
CONVERSATION_TYPES = {"user", "assistant", "system"}

# Entry types we skip entirely
SKIP_TYPES = {"file-history-snapshot", "progress", "queue-operation", "last-prompt",
              "agent-name", "custom-title"}

DEFAULT_TRUNCATE = 2000

# ---------------------------------------------------------------------------
# Session resolution
# ---------------------------------------------------------------------------

def _encode_project_path(project_path: str) -> str:
    """Encode a project path to the directory name format CC uses.

    CC replaces both / and _ with - in the encoded directory name.
    """
    return project_path.replace("/", "-").replace("_", "-")


def _find_project_dirs(project_path: str | None) -> list[Path]:
    """Find candidate project directories in ~/.claude/projects/."""
    if not CLAUDE_DIR.exists():
        return []

    if project_path:
        encoded = _encode_project_path(project_path)
        candidate = CLAUDE_DIR / encoded
        if candidate.is_dir():
            return [candidate]
        # Try partial match
        return [d for d in CLAUDE_DIR.iterdir() if d.is_dir() and encoded in d.name]

    # No project specified — return all
    return [d for d in CLAUDE_DIR.iterdir() if d.is_dir()]


def resolve_session(session_id: str, project_path: str | None = None) -> Path:
    """Find a JSONL file matching the session ID (full UUID or prefix).

    Returns the path to the JSONL file.
    """
    project_dirs = _find_project_dirs(project_path)
    if not project_dirs:
        print(f"Error: no project directories found in {CLAUDE_DIR}", file=sys.stderr)
        sys.exit(1)

    # Try direct file match first (full UUID)
    for pdir in project_dirs:
        candidate = pdir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # Try prefix match
    matches = []
    for pdir in project_dirs:
        for f in pdir.glob("*.jsonl"):
            if f.stem.startswith(session_id):
                matches.append(f)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: ambiguous session ID prefix '{session_id}' — matches {len(matches)} sessions:", file=sys.stderr)
        for m in matches[:5]:
            print(f"  {m.stem}", file=sys.stderr)
        sys.exit(1)

    print(f"Error: no session found matching '{session_id}'", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def _parse_jsonl(path: Path) -> list[dict]:
    """Read JSONL file, return list of parsed JSON objects."""
    entries = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: skipping malformed line {lineno}: {e}", file=sys.stderr)
    return entries


def _deduplicate_by_request_id(entries: list[dict]) -> list[dict]:
    """Deduplicate streaming assistant entries by requestId.

    Claude Code writes multiple entries per API response while streaming.
    Keep only the last entry per requestId (it has final token counts and
    complete content).
    """
    # Build map of requestId -> last entry index for assistant entries
    request_last: dict[str, int] = {}
    for i, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            rid = entry.get("requestId")
            if rid:
                request_last[rid] = i

    # Keep: non-assistant entries, and only the last assistant per requestId
    keep_indices: set[int] = set()
    for i, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            rid = entry.get("requestId")
            if rid and request_last.get(rid) == i:
                keep_indices.add(i)
            elif not rid:
                keep_indices.add(i)
        else:
            keep_indices.add(i)

    return [entries[i] for i in sorted(keep_indices)]


def _entry_to_message(entry: dict) -> dict | None:
    """Convert a JSONL entry to a normalized message dict.

    Returns None for entries that should be skipped.
    """
    entry_type = entry.get("type", "")

    if entry_type in SKIP_TYPES:
        return None

    if entry_type in ("user", "assistant"):
        msg_data = entry.get("message", {})
        role = msg_data.get("role", entry_type)
        content = msg_data.get("content", "")
        usage = msg_data.get("usage")
        model = msg_data.get("model")

        # Build toolCalls and toolResults arrays (matching claude-devtools format)
        tool_calls = []
        tool_results = []

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                        "isTask": block.get("caller", {}).get("type") == "task" if isinstance(block.get("caller"), dict) else False,
                    })
                elif block.get("type") == "tool_result":
                    tool_results.append({
                        "toolUseId": block.get("tool_use_id", ""),
                        "content": block.get("content", ""),
                        "isError": block.get("is_error", False),
                    })

        message = {
            "uuid": entry.get("uuid", ""),
            "parentUuid": entry.get("parentUuid"),
            "type": entry_type,
            "timestamp": entry.get("timestamp", ""),
            "role": role,
            "content": content,
            "cwd": entry.get("cwd", ""),
            "gitBranch": entry.get("gitBranch", ""),
            "isSidechain": entry.get("isSidechain", False),
            "isMeta": entry.get("isMeta", False),
            "userType": entry.get("userType", "external"),
            "isCompactSummary": entry.get("isCompactSummary", False),
            "toolCalls": tool_calls,
            "toolResults": tool_results,
        }

        if usage:
            message["usage"] = usage
        if model:
            message["model"] = model
        if entry.get("requestId"):
            message["requestId"] = entry["requestId"]

        return message

    if entry_type == "system":
        # System entries (e.g., context compaction, local commands)
        content = entry.get("content", "")
        subtype = entry.get("subtype", "")
        return {
            "uuid": entry.get("uuid", ""),
            "parentUuid": entry.get("parentUuid"),
            "type": "system",
            "timestamp": entry.get("timestamp", ""),
            "role": "system",
            "content": content,
            "subtype": subtype,
            "cwd": entry.get("cwd", ""),
            "gitBranch": entry.get("gitBranch", ""),
            "isSidechain": entry.get("isSidechain", False),
            "isMeta": entry.get("isMeta", False),
            "userType": entry.get("userType", "external"),
            "isCompactSummary": False,
            "toolCalls": [],
            "toolResults": [],
        }

    # Unknown type — skip
    return None


# ---------------------------------------------------------------------------
# Subagent resolution
# ---------------------------------------------------------------------------

def _resolve_subagents(session_jsonl: Path) -> list[dict]:
    """Find and parse subagent JSONL files for a session.

    Returns list of Process dicts compatible with claude-devtools format.
    """
    session_dir = session_jsonl.parent / session_jsonl.stem
    subagents_dir = session_dir / "subagents"

    if not subagents_dir.is_dir():
        return []

    processes = []
    for agent_jsonl in sorted(subagents_dir.glob("agent-*.jsonl")):
        # Skip compact summaries
        if "compact" in agent_jsonl.stem:
            continue

        agent_id = agent_jsonl.stem.replace("agent-", "")

        # Read metadata
        meta_path = agent_jsonl.with_suffix(".meta.json")
        meta = {}
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Parse the subagent JSONL
        raw_entries = _parse_jsonl(agent_jsonl)
        deduped = _deduplicate_by_request_id(raw_entries)
        messages = []
        for entry in deduped:
            msg = _entry_to_message(entry)
            if msg is not None:
                messages.append(msg)

        if not messages:
            continue

        # Compute metrics for this subagent
        metrics = _compute_metrics(messages)

        # Timestamps
        timestamps = [m["timestamp"] for m in messages if m.get("timestamp")]
        start_time = timestamps[0] if timestamps else ""
        end_time = timestamps[-1] if timestamps else ""
        duration_ms = metrics.get("durationMs", 0)

        process = {
            "id": agent_id,
            "filePath": str(agent_jsonl),
            "messages": messages,
            "startTime": start_time,
            "endTime": end_time,
            "durationMs": duration_ms,
            "metrics": metrics,
            "isParallel": False,
            "isOngoing": False,
        }

        # Add metadata fields if available
        if meta.get("agentType"):
            process["description"] = meta["agentType"]
            if meta.get("description"):
                process["description"] = f"{meta['agentType']}: {meta['description']}"

        processes.append(process)

    return processes


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _parse_timestamp(ts: str) -> datetime | None:
    """Parse ISO timestamp to datetime."""
    if not ts:
        return None
    try:
        # Handle both Z and +00:00 suffixes
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _compute_metrics(messages: list[dict]) -> dict:
    """Compute aggregate token metrics from messages."""
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    message_count = len(messages)

    for msg in messages:
        usage = msg.get("usage", {})
        if not usage:
            continue
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cache_read_tokens += usage.get("cache_read_input_tokens", 0)
        cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens

    # Duration from timestamps
    timestamps = [m["timestamp"] for m in messages if m.get("timestamp")]
    duration_ms = 0
    if len(timestamps) >= 2:
        first = _parse_timestamp(timestamps[0])
        last = _parse_timestamp(timestamps[-1])
        if first and last:
            duration_ms = int((last - first).total_seconds() * 1000)

    return {
        "durationMs": duration_ms,
        "totalTokens": total_tokens,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadTokens": cache_read_tokens,
        "cacheCreationTokens": cache_creation_tokens,
        "messageCount": message_count,
    }


def _compute_metrics_by_model(messages: list[dict]) -> dict[str, dict]:
    """Compute token metrics grouped by model.

    Returns dict mapping model name -> {inputTokens, outputTokens,
    cacheReadTokens, cacheCreationTokens, totalTokens}.
    Messages without a model or usage field are skipped.
    """
    by_model: dict[str, dict] = {}
    for msg in messages:
        model = msg.get("model")
        usage = msg.get("usage")
        if not model or not usage:
            continue
        if model not in by_model:
            by_model[model] = {
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheReadTokens": 0,
                "cacheCreationTokens": 0,
                "totalTokens": 0,
            }
        bucket = by_model[model]
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        cc = usage.get("cache_creation_input_tokens", 0)
        bucket["inputTokens"] += inp
        bucket["outputTokens"] += out
        bucket["cacheReadTokens"] += cr
        bucket["cacheCreationTokens"] += cc
        bucket["totalTokens"] += inp + out + cr + cc
    return by_model


# ---------------------------------------------------------------------------
# Session metadata extraction
# ---------------------------------------------------------------------------

def _extract_session_metadata(
    entries: list[dict], session_jsonl: Path, processes: list[dict]
) -> dict:
    """Extract session metadata from JSONL entries."""
    session_id = ""
    slug = ""
    git_branch = ""
    cwd = ""
    version = ""
    first_message = ""
    first_timestamp = ""

    for entry in entries:
        if not session_id and entry.get("sessionId"):
            session_id = entry["sessionId"]
        if not git_branch and entry.get("gitBranch"):
            git_branch = entry["gitBranch"]
        if not cwd and entry.get("cwd"):
            cwd = entry["cwd"]
        if not version and entry.get("version"):
            version = entry["version"]
        if not first_timestamp and entry.get("timestamp"):
            first_timestamp = entry["timestamp"]

        # First user message text as firstMessage
        if not first_message and entry.get("type") == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                first_message = content.strip()[:200]
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            first_message = text[:200]
                            break

        # Check for slug/custom-title entries
        if entry.get("type") == "custom-title":
            slug = entry.get("title", "")

    # Fall back to JSONL filename as session ID
    if not session_id:
        session_id = session_jsonl.stem

    # Derive project path from parent directory name
    project_dir = session_jsonl.parent.name
    project_path = cwd or project_dir.replace("-", "/", 1).replace("-", "/")

    return {
        "id": session_id,
        "projectId": project_dir,
        "projectPath": project_path,
        "createdAt": first_timestamp,
        "firstMessage": first_message,
        "messageTimestamp": first_timestamp,
        "hasSubagents": len(processes) > 0,
        "messageCount": 0,  # filled in later
        "isOngoing": False,
        "gitBranch": git_branch,
        "slug": slug,
    }


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def build_session_detail(session_jsonl: Path) -> dict:
    """Parse a JSONL session file into a SessionDetail-compatible structure.

    Returns dict with keys: session, messages, chunks, processes, metrics
    """
    # Step 1: Parse JSONL
    raw_entries = _parse_jsonl(session_jsonl)
    if not raw_entries:
        print(f"Error: no entries found in {session_jsonl}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Deduplicate streaming assistant entries
    deduped = _deduplicate_by_request_id(raw_entries)

    # Step 3: Convert to messages
    messages = []
    for entry in deduped:
        msg = _entry_to_message(entry)
        if msg is not None:
            messages.append(msg)

    # Step 4: Resolve subagents
    processes = _resolve_subagents(session_jsonl)

    # Step 5: Compute metrics (orchestrator + all subagents)
    main_metrics = _compute_metrics(messages)
    for proc in processes:
        proc_metrics = proc.get("metrics", {})
        main_metrics["inputTokens"] += proc_metrics.get("inputTokens", 0)
        main_metrics["outputTokens"] += proc_metrics.get("outputTokens", 0)
        main_metrics["cacheReadTokens"] += proc_metrics.get("cacheReadTokens", 0)
        main_metrics["cacheCreationTokens"] += proc_metrics.get("cacheCreationTokens", 0)
        main_metrics["messageCount"] += proc_metrics.get("messageCount", 0)

    main_metrics["totalTokens"] = (
        main_metrics["inputTokens"]
        + main_metrics["outputTokens"]
        + main_metrics["cacheReadTokens"]
        + main_metrics["cacheCreationTokens"]
    )

    # Step 5b: Compute per-model breakdown
    by_model = _compute_metrics_by_model(messages)

    # Merge subagent per-model metrics with " (agents)" suffix
    agent_model_counts: dict[str, int] = {}  # model -> number of agents using it
    agent_by_model: dict[str, dict] = {}
    for proc in processes:
        proc_by_model = _compute_metrics_by_model(proc.get("messages", []))
        for model, model_metrics in proc_by_model.items():
            agent_model_counts[model] = agent_model_counts.get(model, 0) + 1
            if model not in agent_by_model:
                agent_by_model[model] = {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cacheReadTokens": 0,
                    "cacheCreationTokens": 0,
                    "totalTokens": 0,
                }
            bucket = agent_by_model[model]
            for key in ("inputTokens", "outputTokens", "cacheReadTokens",
                        "cacheCreationTokens", "totalTokens"):
                bucket[key] += model_metrics[key]

    for model, model_metrics in agent_by_model.items():
        key = f"{model} (agents)"
        model_metrics["agentCount"] = agent_model_counts[model]
        by_model[key] = model_metrics

    main_metrics["byModel"] = by_model

    # Step 6: Build session metadata
    session_meta = _extract_session_metadata(raw_entries, session_jsonl, processes)
    session_meta["messageCount"] = len(messages)

    return {
        "session": session_meta,
        "messages": messages,
        "chunks": [],
        "processes": processes,
        "metrics": main_metrics,
    }


def export_json(detail: dict, output_path: str) -> None:
    """Write session detail as formatted JSON."""
    with open(output_path, "w") as f:
        json.dump(detail, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.1f}s"
    mins = int(secs // 60)
    remaining_secs = int(secs % 60)
    if mins < 60:
        return f"{mins}m {remaining_secs}s"
    hours = int(mins // 60)
    remaining_mins = mins % 60
    return f"{hours}h {remaining_mins}m"


def _format_tokens(n: int) -> str:
    """Format token count with commas."""
    return f"{n:,}"


def _extract_text_from_content(content) -> str:
    """Extract plain text from content (string or content block array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text with indicator if too long."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text):,} chars total]"


def export_markdown(detail: dict, output_path: str, truncate: int = DEFAULT_TRUNCATE) -> None:
    """Write session detail as formatted Markdown."""
    session = detail["session"]
    messages = detail["messages"]
    metrics = detail["metrics"]
    processes = detail["processes"]

    lines: list[str] = []

    # Header
    lines.append("# Session Export\n")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Session | `{session.get('id', 'unknown')}` |")
    lines.append(f"| Project | `{session.get('projectPath', 'unknown')}` |")
    if session.get("gitBranch"):
        lines.append(f"| Branch | `{session['gitBranch']}` |")
    if session.get("createdAt"):
        lines.append(f"| Date | {session['createdAt']} |")
    lines.append("")

    # Metrics
    lines.append("## Metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Duration | {_format_duration(metrics.get('durationMs', 0))} |")
    lines.append(f"| Messages | {metrics.get('messageCount', 0)} |")
    if processes:
        lines.append(f"| Subagents | {len(processes)} |")
    lines.append("")

    # Token usage breakdown by model
    by_model = metrics.get("byModel", {})
    lines.append("### Token Usage\n")
    lines.append("| Source | Input | Cache Read | Cache Write | Output | Total |")
    lines.append("|--------|-------|------------|-------------|--------|-------|")
    for source, m in by_model.items():
        agent_count = m.get("agentCount")
        if agent_count is not None:
            # Replace " (agents)" suffix with " (N agents)"
            label = source.replace(" (agents)", f" ({agent_count} agents)")
        else:
            label = source
        lines.append(
            f"| {label} "
            f"| {_format_tokens(m.get('inputTokens', 0))} "
            f"| {_format_tokens(m.get('cacheReadTokens', 0))} "
            f"| {_format_tokens(m.get('cacheCreationTokens', 0))} "
            f"| {_format_tokens(m.get('outputTokens', 0))} "
            f"| {_format_tokens(m.get('totalTokens', 0))} |"
        )
    if len(by_model) > 1:
        lines.append(
            f"| **Total** "
            f"| **{_format_tokens(metrics.get('inputTokens', 0))}** "
            f"| **{_format_tokens(metrics.get('cacheReadTokens', 0))}** "
            f"| **{_format_tokens(metrics.get('cacheCreationTokens', 0))}** "
            f"| **{_format_tokens(metrics.get('outputTokens', 0))}** "
            f"| **{_format_tokens(metrics.get('totalTokens', 0))}** |"
        )
    lines.append("")

    # Conversation
    lines.append("## Conversation\n")
    turn = 0
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        turn += 1

        if role == "user":
            lines.append(f"### User (Turn {turn})")
            # Check for tool results
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                lines.append(text)
                        elif block.get("type") == "tool_result":
                            tool_content = block.get("content", "")
                            if isinstance(tool_content, list):
                                tool_text = "\n".join(
                                    b.get("text", "") for b in tool_content
                                    if isinstance(b, dict)
                                )
                            elif isinstance(tool_content, str):
                                tool_text = tool_content
                            else:
                                tool_text = str(tool_content)
                            is_error = block.get("is_error", False)
                            prefix = "**Error Result:**" if is_error else "**Result:**"
                            lines.append(f"{prefix}")
                            lines.append("```")
                            lines.append(_truncate(tool_text, truncate))
                            lines.append("```")
            elif isinstance(content, str):
                if content.strip():
                    lines.append(content.strip())
            lines.append("")

        elif role == "assistant":
            lines.append(f"### Assistant (Turn {turn})")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "thinking":
                        thinking = block.get("thinking", "").strip()
                        if thinking:
                            # Render as blockquote
                            lines.append("> *Thinking:*")
                            for tline in thinking.split("\n")[:20]:
                                lines.append(f"> {tline}")
                            total_lines = thinking.count("\n") + 1
                            if total_lines > 20:
                                lines.append(f"> ... [{total_lines} lines total]")
                            lines.append("")
                    elif btype == "text":
                        text = block.get("text", "").strip()
                        if text:
                            lines.append(text)
                            lines.append("")
                    elif btype == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        lines.append(f"**Tool:** `{tool_name}`")
                        lines.append("```json")
                        input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
                        lines.append(_truncate(input_str, truncate))
                        lines.append("```")
                        lines.append("")
            elif isinstance(content, str):
                if content.strip():
                    lines.append(content.strip())
            lines.append("")

        elif role == "system":
            subtype = msg.get("subtype", "")
            lines.append(f"### System (Turn {turn})")
            if subtype:
                lines.append(f"*{subtype}*")
            text = content if isinstance(content, str) else _extract_text_from_content(content)
            if text.strip():
                lines.append(text.strip())
            lines.append("")
            lines.append("---")
            lines.append("")

    # Subagent summary (if any)
    if processes:
        lines.append("## Subagents\n")
        lines.append("| ID | Description | Messages | Duration | Tokens |")
        lines.append("|----|-------------|----------|----------|--------|")
        for proc in processes:
            pid = proc.get("id", "?")[:12]
            desc = proc.get("description", "—")
            pm = proc.get("metrics", {})
            lines.append(
                f"| `{pid}` | {desc} "
                f"| {pm.get('messageCount', 0)} "
                f"| {_format_duration(pm.get('durationMs', 0))} "
                f"| {_format_tokens(pm.get('totalTokens', 0))} |"
            )
        lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Claude Code JSONL sessions to JSON or Markdown",
    )
    parser.add_argument(
        "session_id",
        help="Session UUID (full or prefix)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "md"],
        default="md",
        help="Output format (default: md)",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--project", "-p",
        default=None,
        help="Project path to search sessions in (default: cwd)",
    )
    parser.add_argument(
        "--truncate", "-t",
        type=int,
        default=DEFAULT_TRUNCATE,
        help=f"Max chars for tool results in markdown (default: {DEFAULT_TRUNCATE})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Resolve project path
    project_path = args.project or os.getcwd()

    # Find the JSONL file
    session_jsonl = resolve_session(args.session_id, project_path)

    # Build the session detail
    detail = build_session_detail(session_jsonl)

    # Export
    if args.format == "json":
        export_json(detail, args.output)
    else:
        export_markdown(detail, args.output, truncate=args.truncate)

    # Report
    output_size = Path(args.output).stat().st_size
    if output_size >= 1_048_576:
        size_str = f"{output_size / 1_048_576:.1f}MB"
    elif output_size >= 1024:
        size_str = f"{output_size / 1024:.0f}KB"
    else:
        size_str = f"{output_size}B"

    session_meta = detail["session"]
    metrics = detail["metrics"]
    print(f"Exported session {session_meta['id']}")
    print(f"  Format:    {args.format}")
    print(f"  Output:    {args.output} ({size_str})")
    print(f"  Messages:  {session_meta['messageCount']}")
    print(f"  Tokens:    {_format_tokens(metrics['totalTokens'])}")
    if detail["processes"]:
        print(f"  Subagents: {len(detail['processes'])}")


if __name__ == "__main__":
    main()
