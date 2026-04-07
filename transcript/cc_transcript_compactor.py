#!/usr/bin/env python3
"""Reduce claude-devtools session JSON exports for analysis.

Strips tool result content, redundant fields, and UI metadata at
configurable levels while always preserving tool errors.

Usage:
    python3 scripts/reduce_cc_session_export.py SESSION.json                  # default level 2
    python3 scripts/reduce_cc_session_export.py SESSION.json --level 4        # specific level
    python3 scripts/reduce_cc_session_export.py SESSION.json --level l2-compact  # decision-graph
    python3 scripts/reduce_cc_session_export.py SESSION.json --analyze        # preview sizes
    python3 scripts/reduce_cc_session_export.py SESSION.json -o slim.json     # custom output

Levels:
    0          compact    — strip large content + chunks
    1          lean       — + drop redundant message fields
    2          minimal    — + drop per-turn usage
    l2-compact            — L2 + restructured agents with tool_trace, reasoning, stubs (default)
    3          skeleton   — + drop all non-error tool outputs
    4          analysis   — restructure: orchestrator msgs + per-agent tool lists
    5          summary    — + compact tool inputs (filenames, truncated commands)

Errors are preserved at ALL levels.
Output: SESSION.lN.json (includes level number), SESSION.l2c.json for l2-compact.
"""
import argparse
import json
import sys
from pathlib import Path

# --- Constants ---

KEEP_THRESHOLD = 2000  # tool results shorter than this are kept verbatim
KEEP_HEAD = 500
KEEP_TAIL = 200

REQUIRED_KEYS = {"session", "messages", "processes", "metrics"}

REDUNDANT_MSG_FIELDS = frozenset({
    "toolResults", "cwd", "parentUuid", "gitBranch", "isSidechain",
    "isMeta", "isCompactSummary", "userType", "sourceToolAssistantUUID",
    "requestId",
})

ERROR_MARKERS = ("Error:", "error:", "ERROR", "Exit code", "exceeds maximum")

# l2-compact constants
L2C_READ_STUB_THRESHOLD = 600
L2C_EXTRA_ORCH_FIELDS = frozenset({"toolUseResult", "toolCalls", "uuid"})
L2C_SCHEMA = {
    "version": "1.0",
    "description": "Reduced claude-devtools session export (l2-compact: decision-graph)",
    "guide": {
        "errors": "Search for is_error: true or check each agent's errors[] array. All error tool results are preserved in full regardless of size.",
        "tool_trace": "Each agent has a tool_trace[] array with every tool call in order. Each entry: {name, input, result}. Successful Read results >600 chars are stubbed as '[ok, N lines]'. All other results (Bash, Grep, Write, etc.) preserved in full.",
        "agent_outcomes": "agent.result contains the final assistant response. agent.prompt contains what was delegated.",
        "reasoning": "agent.reasoning[] contains assistant text blocks between tool calls — shows why the agent made each decision.",
        "orchestrator": "messages[] is the top-level conversation (preserved from L2). Look for tool_use blocks with name='Agent' to see delegation, tool_result blocks for what came back.",
        "timing": "agent.durationMs for per-agent timing, top-level metrics for session totals.",
    },
}

LEVEL_NAMES: dict[int | str, str] = {
    0: "compact",
    1: "lean",
    2: "minimal",
    "l2-compact": "l2-compact",
    3: "skeleton",
    4: "analysis",
    5: "summary",
}

LEVEL_NOTES: dict[int | str, str] = {
    0: "Strip content + chunks",
    1: "+ drop redundant fields",
    2: "+ drop per-turn usage",
    "l2-compact": "L2 + agent tool_trace with reasoning",
    3: "+ drop non-error tool outputs",
    4: "Restructured for analysis",
    5: "Flat per-agent summaries",
}


# --- Schema validation ---

def validate_schema(data: object) -> None:
    """Validate input is a claude-devtools session export."""
    if not isinstance(data, dict):
        print(f"Error: expected JSON object, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)

    for key in REQUIRED_KEYS:
        if key not in data:
            print(f"Error: not a claude-devtools session export (missing key '{key}')", file=sys.stderr)
            sys.exit(1)

    for key, expected in (("messages", list), ("processes", list)):
        if not isinstance(data[key], expected):
            actual = type(data[key]).__name__
            print(f"Error: expected '{key}' to be a {expected.__name__}, got {actual}", file=sys.stderr)
            sys.exit(1)

    for key, expected in (("session", dict), ("metrics", dict)):
        if not isinstance(data[key], expected):
            actual = type(data[key]).__name__
            print(f"Error: expected '{key}' to be a {expected.__name__}, got {actual}", file=sys.stderr)
            sys.exit(1)

    procs = data["processes"]
    if procs:
        first = procs[0]
        if not isinstance(first, dict) or "id" not in first or "messages" not in first:
            print("Error: processes[0] missing 'id' or 'messages' — not a claude-devtools export", file=sys.stderr)
            sys.exit(1)


# --- Error detection ---

def _text_is_error(text: str) -> bool:
    return any(m in text for m in ERROR_MARKERS)


def is_error_content(content: object) -> bool:
    """Check if tool result content contains error markers."""
    if isinstance(content, str):
        return _text_is_error(content)
    if isinstance(content, list):
        return any(
            isinstance(p, dict) and isinstance(p.get("text"), str) and _text_is_error(p["text"])
            for p in content
        )
    return False


def is_error_result(item: dict) -> bool:
    """Check if a tool result dict (from toolResults or content block) is an error."""
    if item.get("isError"):
        return True
    return is_error_content(item.get("content", ""))


# --- Content stripping helpers ---

def slim_text(text: str, tool_name: str | None = None) -> str:
    """Replace large non-error text with head + [stripped] + tail."""
    if len(text) <= KEEP_THRESHOLD or _text_is_error(text):
        return text

    total = len(text)
    lines = text.count("\n") + 1
    head = text[:KEEP_HEAD]
    tail = text[-KEEP_TAIL:] if KEEP_TAIL else ""
    label = f" from {tool_name}" if tool_name else ""
    marker = f"\n\n[... stripped {total:,} chars / ~{lines} lines{label} ...]\n\n"
    return head + marker + tail


def _slim_content_value(content: object, tool_name: str | None = None) -> object:
    """Slim a tool result content value (string or list of parts)."""
    if isinstance(content, str):
        return slim_text(content, tool_name)
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append({**part, "text": slim_text(part["text"], tool_name)})
            else:
                out.append(part)
        return out
    return content


def _get_tool_names(msg: dict) -> dict[str, str]:
    """Build tool_use_id -> tool_name map from a message."""
    names: dict[str, str] = {}
    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                names[block.get("id", "")] = block.get("name", "")
    for tc in msg.get("toolCalls", []):
        if isinstance(tc, dict):
            names[tc.get("toolUseId", tc.get("id", ""))] = tc.get("name", "")
    return names


# --- Level functions ---

def apply_l0(data: dict) -> dict:
    """L0 compact: strip large tool result content + drop chunks."""
    data.pop("chunks", None)

    for msg_list in _all_message_lists(data):
        for msg in msg_list:
            if not isinstance(msg, dict):
                continue
            tool_names = _get_tool_names(msg)

            # Slim content blocks
            content = msg.get("content", [])
            if isinstance(content, list):
                new_content = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        new_block = {**block}
                        new_block["content"] = _slim_content_value(block.get("content", ""), tool_names.get(tid))
                        new_content.append(new_block)
                    else:
                        new_content.append(block)
                msg["content"] = new_content

            # Slim toolResults
            trs = msg.get("toolResults", [])
            if isinstance(trs, list):
                new_trs = []
                for tr in trs:
                    if not isinstance(tr, dict):
                        new_trs.append(tr)
                        continue
                    if tr.get("isError"):
                        new_trs.append(tr)
                        continue
                    tid = tr.get("toolUseId", "")
                    new_tr = {**tr}
                    new_tr["content"] = _slim_content_value(tr.get("content", ""), tool_names.get(tid))
                    new_trs.append(new_tr)
                msg["toolResults"] = new_trs

    return data


def apply_l1(data: dict) -> dict:
    """L1 lean: drop redundant message fields."""
    for msg_list in _all_message_lists(data):
        for msg in msg_list:
            if not isinstance(msg, dict):
                continue
            for field in REDUNDANT_MSG_FIELDS:
                msg.pop(field, None)
    return data


def apply_l2(data: dict) -> dict:
    """L2 minimal: drop per-turn usage."""
    for msg_list in _all_message_lists(data):
        for msg in msg_list:
            if isinstance(msg, dict):
                msg.pop("usage", None)
    return data


def _extract_message_text(content: object) -> str:
    """Extract concatenated text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else ""
    return ""


def _extract_result_text(content: object) -> str:
    """Extract text from a tool_result content value (string or list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return str(content)


def _l2c_process_result(tool_name: str, content: object, is_err: bool) -> str:
    """Process a tool result for the l2-compact tool_trace."""
    text = _extract_result_text(content)

    # Errors always preserved in full
    if is_err:
        return text

    if tool_name == "Read":
        if len(text) <= L2C_READ_STUB_THRESHOLD:
            return text
        if _text_is_error(text):
            return text
        lines = text.count("\n") + 1
        return f"[ok, {lines} lines]"

    if tool_name == "Write":
        if text.startswith("File created successfully"):
            return "ok"
        return text

    # All other tools: keep in full
    return text


def apply_l2_compact(data: dict) -> dict:
    """L2-compact: restructure agents into tool_trace format with schema header.

    Preserves orchestrator messages (with extra field stripping), restructures
    each agent process into {prompt, result, reasoning, tool_trace, errors}.
    """
    # 1. Strip extra redundant fields from orchestrator messages
    for msg in data.get("messages", []):
        if isinstance(msg, dict):
            for field in L2C_EXTRA_ORCH_FIELDS:
                msg.pop(field, None)

    # 2. Restructure each process into tool_trace format
    new_processes = []
    for proc in data.get("processes", []):
        if not isinstance(proc, dict):
            continue

        messages = proc.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        # Find first user message and last assistant message
        first_user_idx = -1
        last_assistant_idx = -1
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user" and first_user_idx < 0:
                first_user_idx = i
            if msg.get("role") == "assistant":
                last_assistant_idx = i

        # Extract prompt and result
        prompt = ""
        if first_user_idx >= 0:
            prompt = _extract_message_text(messages[first_user_idx].get("content", ""))

        agent_result = ""
        if last_assistant_idx >= 0:
            agent_result = _extract_message_text(messages[last_assistant_idx].get("content", ""))

        # Extract reasoning (assistant text from intermediate messages)
        reasoning: list[str] = []
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            if i == first_user_idx or i == last_assistant_idx:
                continue
            if msg.get("role") == "assistant":
                text = _extract_message_text(msg.get("content", ""))
                if text.strip():
                    reasoning.append(text)

        # Build tool_trace: collect tool_use blocks, then match with tool_results
        tool_use_map: dict[str, dict] = {}
        tool_trace: list[dict] = []
        errors: list[str] = []

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_use_map[block.get("id", "")] = {
                        "name": block.get("name", ""),
                        "input": block.get("input"),
                    }
                elif block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "")
                    tool_info = tool_use_map.get(tid, {"name": "unknown", "input": {}})
                    tool_name = tool_info["name"]

                    is_err = bool(block.get("is_error")) or is_error_content(
                        block.get("content", "")
                    )

                    result_text = _l2c_process_result(
                        tool_name, block.get("content", ""), is_err
                    )

                    trace_entry: dict = {
                        "name": tool_name,
                        "input": tool_info["input"],
                        "result": result_text,
                    }
                    if is_err:
                        trace_entry["is_error"] = True
                    tool_trace.append(trace_entry)

                    if is_err:
                        errors.append(result_text)

        entry: dict = {
            "id": proc.get("id"),
            "durationMs": proc.get("durationMs"),
            "metrics": proc.get("metrics"),
            "prompt": prompt,
            "result": agent_result,
        }
        if reasoning:
            entry["reasoning"] = reasoning
        entry["tool_trace"] = tool_trace
        if errors:
            entry["errors"] = errors

        new_processes.append(entry)

    data["processes"] = new_processes

    # 3. Add _schema as first key
    data = {"_schema": L2C_SCHEMA, **data}

    return data


def apply_l3(data: dict) -> dict:
    """L3 skeleton: drop all non-error tool result content."""
    for msg_list in _all_message_lists(data):
        for msg in msg_list:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if isinstance(content, list):
                new_content = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        if is_error_content(block.get("content", "")):
                            new_content.append(block)
                        else:
                            new_content.append({"type": "tool_result", "tool_use_id": block.get("tool_use_id"), "content": "[stripped]"})
                    else:
                        new_content.append(block)
                msg["content"] = new_content
    return data


def apply_l4(data: dict) -> dict:
    """L4 analysis: restructure processes to compact form."""
    new_processes = []
    for proc in data.get("processes", []):
        if not isinstance(proc, dict):
            continue
        entry: dict = {
            "id": proc.get("id"),
            "durationMs": proc.get("durationMs"),
            "metrics": proc.get("metrics"),
            "tools": [],
            "errors": [],
        }
        for msg in proc.get("messages", []):
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    entry["tools"].append({
                        "name": block.get("name"),
                        "input": block.get("input"),
                    })
                elif block.get("type") == "tool_result" and is_error_content(block.get("content", "")):
                    c = block.get("content", "")
                    if isinstance(c, str):
                        entry["errors"].append(c)
                    elif isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                entry["errors"].append(part["text"])
        if not entry["errors"]:
            del entry["errors"]
        new_processes.append(entry)

    data["processes"] = new_processes
    return data


def apply_l5(data: dict) -> dict:
    """L5 summary: compact tool inputs."""
    truncation = {
        "file_path": -1,  # special: filename only
        "command": 80,
        "pattern": 60,
        "prompt": 60,
    }
    default_max = 40

    for proc in data.get("processes", []):
        if not isinstance(proc, dict):
            continue
        for tool in proc.get("tools", []):
            inp = tool.get("input")
            if not isinstance(inp, dict):
                continue
            compact = {}
            for k, v in inp.items():
                if not isinstance(v, str):
                    compact[k] = v
                    continue
                limit = truncation.get(k, default_max)
                if limit == -1:
                    compact[k] = v.rsplit("/", 1)[-1]  # filename only
                elif len(v) > limit:
                    compact[k] = v[:limit] + "..."
                else:
                    compact[k] = v
            tool["input"] = compact
    return data


# --- Helpers ---

def _all_message_lists(data: dict):
    """Yield all message lists (orchestrator + per-agent)."""
    msgs = data.get("messages", [])
    if isinstance(msgs, list):
        yield msgs
    for proc in data.get("processes", []):
        if isinstance(proc, dict):
            proc_msgs = proc.get("messages", [])
            if isinstance(proc_msgs, list):
                yield proc_msgs


APPLY_FNS = [apply_l0, apply_l1, apply_l2, apply_l3, apply_l4, apply_l5]


def slim(data: dict, level: int | str) -> dict:
    """Apply levels 0..level cumulatively, or a named variant."""
    if level == "l2-compact":
        data = apply_l0(data)
        data = apply_l1(data)
        data = apply_l2(data)
        data = apply_l2_compact(data)
        data["slim_level"] = "l2-compact"
        data["slim_schema"] = "restructured"
        return data

    for i in range(min(level + 1, len(APPLY_FNS))):  # type: ignore[arg-type]
        data = APPLY_FNS[i](data)

    schema = "restructured" if level >= 4 else "original"
    data["slim_level"] = level
    data["slim_schema"] = schema
    return data


# --- Analyze (estimation) ---

def estimate_sizes(data: dict, original_size: int) -> list[tuple[int, str, int, str]]:
    """Walk data once, estimate size at each level by subtraction.

    Key insight: toolResults is slimmed at L0 (content stripped), then dropped
    entirely at L1. We must estimate its post-L0 size, not subtract its original size.

    All measurements use json.dumps() (no indent) for consistency, then scale
    to indented file size at the end.
    """
    base = len(json.dumps(data))
    indent_ratio = original_size / base if base > 0 else 1.0

    total = base

    chunks_size = len(json.dumps(data.get("chunks", [])))

    # Accumulators — split toolResults from other redundant fields
    content_strip_savings = 0  # L0: savings from slimming content blocks
    toolresults_original = 0   # original toolResults size (for accurate L0)
    toolresults_slimmed = 0    # estimated post-L0 toolResults size (L1 drops this)
    other_redundant_size = 0   # L1: cwd, parentUuid, etc. (NOT toolResults)
    usage_size = 0             # L2: per-turn usage objects
    nonerror_results_post_l0 = 0  # L3: non-error tool results after L0 slimming

    # L4: additive — measure what survives in each section
    session_metrics_size = len(json.dumps(data.get("session", {}))) + len(json.dumps(data.get("metrics", {})))
    orch_kept_content_size = 0   # orchestrator content that survives L4 (tool_use + text + error results)
    orch_msg_metadata_size = 0   # orchestrator per-message metadata (uuid, timestamp, role, etc.)
    agent_tool_use_size = 0      # agent tool_use blocks as {name, input}
    agent_tool_use_compact = 0   # L5: agent tool_use with compacted inputs
    proc_metrics_size = 0

    # l2-compact accumulators
    l2c_extra_orch_size = 0      # toolUseResult + toolCalls + uuid on orchestrator messages
    l2c_agent_text_size = 0      # assistant text blocks in agents (reasoning + prompt/result)
    l2c_agent_read_savings = 0   # savings from stubbing Read results >600 chars
    l2c_agent_write_savings = 0  # savings from compressing Write "ok" results
    l2c_agent_msg_metadata = 0   # per-message metadata in agents (all stripped)

    def _estimate_slimmed(content: object) -> int:
        """Estimate post-L0 size of a tool result content value."""
        if isinstance(content, str):
            if len(content) > KEEP_THRESHOLD and not _text_is_error(content):
                return KEEP_HEAD + KEEP_TAIL + 80  # head + tail + marker + quotes
            return len(json.dumps(content))
        return len(json.dumps(content))

    def _compact_input_size(inp: object) -> int:
        """Estimate size of a tool input after L5 compaction."""
        if not isinstance(inp, dict):
            return len(json.dumps(inp))
        truncation = {"file_path": -1, "command": 80, "pattern": 60, "prompt": 60}
        default_max = 40
        compact = {}
        for k, v in inp.items():
            if not isinstance(v, str):
                compact[k] = v
            else:
                limit = truncation.get(k, default_max)
                if limit == -1:
                    compact[k] = v.rsplit("/", 1)[-1]
                elif len(v) > limit:
                    compact[k] = v[:limit] + "..."
                else:
                    compact[k] = v
        return len(json.dumps(compact))

    def _walk_messages(msg_list: list, is_agent: bool) -> None:
        nonlocal content_strip_savings, toolresults_original, toolresults_slimmed
        nonlocal other_redundant_size, usage_size, nonerror_results_post_l0
        nonlocal agent_tool_use_size, agent_tool_use_compact
        nonlocal orch_kept_content_size, orch_msg_metadata_size
        nonlocal l2c_agent_text_size, l2c_agent_read_savings, l2c_agent_write_savings
        nonlocal l2c_agent_msg_metadata

        # l2-compact: build tool_use_id -> name map for Read/Write classification
        agent_tool_names: dict[str, str] = {}

        for msg in msg_list:
            if not isinstance(msg, dict):
                continue

            # Redundant fields (excluding toolResults)
            for field in REDUNDANT_MSG_FIELDS - {"toolResults"}:
                if field in msg:
                    other_redundant_size += len(json.dumps(msg[field])) + len(field) + 5  # key overhead

            # l2-compact: agent message metadata that survives L2 but is removed
            # by restructuring.  Exclude content and fields already stripped by L1/L2.
            if is_agent:
                l2c_skip = REDUNDANT_MSG_FIELDS | {"content", "usage"}
                for k, v in msg.items():
                    if k not in l2c_skip:
                        l2c_agent_msg_metadata += len(json.dumps(v)) + len(k) + 5
                l2c_agent_msg_metadata += 20  # structural overhead (braces, commas)

            # toolResults — track original and slimmed separately
            trs = msg.get("toolResults")
            if trs is not None:
                tr_orig = len(json.dumps(trs))
                toolresults_original += tr_orig + 16  # "toolResults": key overhead

                # Estimate slimmed size
                tr_slim = 2  # []
                if isinstance(trs, list):
                    for tr in trs:
                        if isinstance(tr, dict):
                            tr_slim += _estimate_slimmed(tr.get("content", "")) + 50  # wrapper overhead
                toolresults_slimmed += tr_slim + 16

            # Usage
            if "usage" in msg:
                usage_size += len(json.dumps(msg["usage"])) + 10

            # Content blocks
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    c = block.get("content", "")
                    orig_size = len(json.dumps(c))
                    slimmed_size = _estimate_slimmed(c)
                    content_strip_savings += orig_size - slimmed_size

                    # L3: non-error results (post-L0 size)
                    if not is_error_content(c):
                        nonerror_results_post_l0 += slimmed_size + 40  # block wrapper
                    if not is_agent:
                        orch_kept_content_size += slimmed_size + 40

                    # l2-compact: estimate Read stub savings and Write compression
                    if is_agent:
                        tid = block.get("tool_use_id", "")
                        tname = agent_tool_names.get(tid, "")
                        if tname == "Read" and not is_error_content(c):
                            text_len = len(c) if isinstance(c, str) else len(json.dumps(c))
                            if text_len > L2C_READ_STUB_THRESHOLD:
                                l2c_agent_read_savings += slimmed_size - 20  # stub is ~20 chars
                        elif tname == "Write" and isinstance(c, str) and c.startswith("File created successfully"):
                            l2c_agent_write_savings += len(c) - 4  # "ok" + quotes

                elif btype == "tool_use":
                    tool_entry = {"name": block.get("name"), "input": block.get("input")}
                    entry_size = len(json.dumps(tool_entry))
                    if is_agent:
                        agent_tool_use_size += entry_size
                        agent_tool_use_compact += _compact_input_size(block.get("input")) + 20  # name + wrapper
                        agent_tool_names[block.get("id", "")] = block.get("name", "")
                    else:
                        orch_kept_content_size += len(json.dumps(block))

                elif btype == "text":
                    if is_agent:
                        l2c_agent_text_size += len(json.dumps(block.get("text", "")))
                    else:
                        orch_kept_content_size += len(json.dumps(block))

    # Walk orchestrator messages — also measure per-message metadata that survives L4
    for msg in data.get("messages", []):
        if isinstance(msg, dict):
            # At L4, orch messages keep: uuid, timestamp, role, model, agentId, type, content, toolCalls
            for field in ("uuid", "timestamp", "role", "model", "agentId", "type"):
                if field in msg:
                    orch_msg_metadata_size += len(json.dumps(msg[field])) + len(field) + 5
            if "toolCalls" in msg:
                orch_msg_metadata_size += len(json.dumps(msg["toolCalls"])) + 15
            orch_msg_metadata_size += 20  # braces, commas, "content": key

            # l2-compact: extra orchestrator fields to strip
            for field in L2C_EXTRA_ORCH_FIELDS:
                if field in msg:
                    l2c_extra_orch_size += len(json.dumps(msg[field])) + len(field) + 5

    _walk_messages(data.get("messages", []), is_agent=False)

    # Walk agent messages
    for proc in data.get("processes", []):
        if not isinstance(proc, dict):
            continue
        proc_metrics_size += len(json.dumps({
            "id": proc.get("id"), "durationMs": proc.get("durationMs"), "metrics": proc.get("metrics")
        }))
        _walk_messages(proc.get("messages", []), is_agent=True)

    # Compute level estimates (L0-L3: subtractive from total)
    l0 = total - chunks_size - content_strip_savings
    l0 = l0 - (toolresults_original - toolresults_slimmed)

    l1 = l0 - toolresults_slimmed - other_redundant_size
    l2 = l1 - usage_size
    l3 = l2 - nonerror_results_post_l0

    # L4: additive — sum of what survives the restructure
    l4 = (session_metrics_size + orch_kept_content_size + orch_msg_metadata_size
          + proc_metrics_size + agent_tool_use_size)

    # L5: replace agent tool inputs with compact versions
    l5 = l4 - agent_tool_use_size + agent_tool_use_compact

    # l2-compact: L2 base, minus extra orch fields, minus agent metadata overhead,
    # plus Read stub and Write compression savings.  Agent content (tool I/O + text)
    # is preserved but wrapped differently — roughly same size, so we only subtract
    # what's actually removed.
    l2c = (l2
           - l2c_extra_orch_size
           - l2c_agent_msg_metadata
           - l2c_agent_read_savings
           - l2c_agent_write_savings)

    results: list[tuple[int | str, str, int, str]] = []
    for level, est in enumerate([l0, l1, l2, l3, l4, l5]):
        est = max(int(est * indent_ratio), 1)
        results.append((level, LEVEL_NAMES[level], est, LEVEL_NOTES[level]))

    # Insert l2-compact after L2
    l2c_est = max(int(l2c * indent_ratio), 1)
    results.insert(3, ("l2-compact", "l2-compact", l2c_est, LEVEL_NOTES["l2-compact"]))

    return results


def analyze(data: dict, original_size: int) -> None:
    """Print estimated sizes at each level."""
    proc_count = len(data.get("processes", []))
    msg_count = sum(1 for _ in data.get("messages", []))
    for proc in data.get("processes", []):
        if isinstance(proc, dict):
            msg_count += len(proc.get("messages", []))

    print(f"Session: {original_size / 1_048_576:.1f}MB, {proc_count} agents, {msg_count} messages (claude-devtools export)")
    print()

    estimates = estimate_sizes(data, original_size)

    # Column widths
    print(f"  {'Level':<12} {'Name':<12} {'Est. size':>10} {'Reduction':>10}  {'Notes'}")
    for level, name, est_bytes, notes in estimates:
        if est_bytes > 1_048_576:
            size_str = f"{est_bytes / 1_048_576:.1f}MB"
        else:
            size_str = f"{est_bytes / 1024:.0f}KB"
        is_restructured = (isinstance(level, int) and level >= 4) or level == "l2-compact"
        if is_restructured:
            size_str = "~" + size_str
        reduction = (1 - est_bytes / original_size) * 100
        default = "  [default]" if level == "l2-compact" else ""
        level_str = str(level)
        print(f"  {level_str:<12} {name:<12} {size_str:>10} {reduction:>9.0f}%  {notes}{default}")

    print()
    print("Run with --level N or --level l2-compact to apply.")


# --- Main ---

def _parse_level(value: str) -> int | str:
    """Parse level argument: integer 0-5 or 'l2-compact'."""
    if value == "l2-compact":
        return value
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid level: {value!r} (expected 0-5 or 'l2-compact')")
    if n not in range(6):
        raise argparse.ArgumentTypeError(f"invalid level: {n} (expected 0-5 or 'l2-compact')")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reduce claude-devtools session JSON exports for analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to claude-devtools session JSON export")
    parser.add_argument("-o", "--output", help="Output path (default: INPUT.lN.json)")
    parser.add_argument("--level", type=_parse_level, default="l2-compact",
                        help="Strip level 0-5 or 'l2-compact' (default: l2-compact)")
    parser.add_argument("--analyze", action="store_true",
                        help="Preview estimated sizes at each level, then exit")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    validate_schema(data)
    original_size = input_path.stat().st_size

    if args.analyze:
        analyze(data, original_size)
        return

    data = slim(data, args.level)

    if args.output:
        output_path = Path(args.output)
    elif args.level == "l2-compact":
        output_path = input_path.with_suffix(".l2c.json")
    else:
        output_path = input_path.with_suffix(f".l{args.level}.json")

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    new_size = output_path.stat().st_size
    reduction = (1 - new_size / original_size) * 100
    level_name = LEVEL_NAMES[args.level]

    print(f"{original_size / 1_048_576:.1f}MB -> {new_size / 1_048_576:.1f}MB ({reduction:.0f}% reduction) — {level_name}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
