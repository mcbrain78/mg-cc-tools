#!/usr/bin/env python3
"""Script-controlled fix queue for audit findings.

Enforces sequential extract→edit→merge processing by managing a state file.
The orchestrator calls `init` once, then loops calling `next` until done.
Each `next` call merges the previous group (if any) before extracting the next.

Subcommands:
    init  -- Create state file with queue of approved groups
    next  -- Merge previous, extract next, return JSON status

Usage:
    fix-queue.py init \
        --grouping-file PATH \
        --findings-file PATH \
        --xml-dir PATH \
        --edit-dir PATH \
        --approved 0,1,2 \
        --state-file PATH

    fix-queue.py next --state-file PATH

Prints JSON to stdout. Diagnostics go to stderr.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

from lxml import etree

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def cmd_init(args):
    """Create state file with queue of approved group indices."""
    approved = [int(x.strip()) for x in args.approved.split(",") if x.strip()]

    # Validate group indices against grouping file
    grouping = load_json(args.grouping_file, default={"groups": []})
    groups = grouping.get("groups", [])
    valid = [i for i in approved if 0 <= i < len(groups)]
    if len(valid) < len(approved):
        skipped = set(approved) - set(valid)
        print(
            f"Warning: skipping out-of-range indices: {sorted(skipped)}",
            file=sys.stderr,
        )

    state = {
        "config": {
            "grouping_file": os.path.abspath(args.grouping_file),
            "findings_file": os.path.abspath(args.findings_file),
            "xml_dir": os.path.abspath(args.xml_dir),
            "edit_dir": os.path.abspath(args.edit_dir),
        },
        "queue": valid,
        "current": None,
        "completed": [],
        "skipped": [],
        "files_modified": [],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.state_file)), exist_ok=True)
    save_json(args.state_file, state)

    print(json.dumps({
        "status": "initialized",
        "queue_size": len(valid),
    }))
    print(
        f"Initialized queue with {len(valid)} groups", file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# next — merge previous, extract next
# ---------------------------------------------------------------------------

def _merge_current(state):
    """Merge the current group's edit file, update state.

    Returns list of errors (empty on success).
    """
    cfg = state["config"]
    current = state["current"]

    # Load grouping to get group_id for edit file path
    grouping = load_json(cfg["grouping_file"], default={"groups": []})
    groups = grouping.get("groups", [])
    group = groups[current]
    group_id = group.get("group_id", f"group-{current}")
    edit_file = os.path.join(cfg["edit_dir"], f"{group_id}.xml")

    if not os.path.isfile(edit_file):
        err = f"Edit file not found for merge: {edit_file}"
        print(f"  Error: {err}", file=sys.stderr)
        return [err]

    merge_script = os.path.join(SCRIPTS_DIR, "merge-edit-xml.py")
    result = subprocess.run(
        [sys.executable, merge_script, "--edit-file", edit_file],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        err = f"merge-edit-xml.py failed for {group_id}: {result.stderr}"
        print(f"  Error: {err}", file=sys.stderr)
        return [err]

    try:
        merge_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        err = f"merge-edit-xml.py returned invalid JSON for {group_id}"
        print(f"  Error: {err}", file=sys.stderr)
        return [err]

    # Accumulate files_modified (deduplicated)
    for f in merge_output.get("files_modified", []):
        if f not in state["files_modified"]:
            state["files_modified"].append(f)

    sections = merge_output.get("sections_updated", 0)
    print(
        f"  Merged group {current} ({group_id}): "
        f"{sections} sections into "
        f"{len(merge_output.get('files_modified', []))} files",
        file=sys.stderr,
    )

    # Move to completed
    state["completed"].append(current)
    state["current"] = None

    return merge_output.get("errors", [])


def _extract_group(state, group_index):
    """Extract edit XML for a group. Returns (edit_file, section_count) or (None, 0)."""
    cfg = state["config"]
    grouping = load_json(cfg["grouping_file"], default={"groups": []})
    groups = grouping.get("groups", [])
    group = groups[group_index]
    group_id = group.get("group_id", f"group-{group_index}")
    edit_file = os.path.join(cfg["edit_dir"], f"{group_id}.xml")

    extract_script = os.path.join(SCRIPTS_DIR, "extract-edit-xml.py")
    result = subprocess.run(
        [
            sys.executable, extract_script,
            "--grouping-file", cfg["grouping_file"],
            "--group-index", str(group_index),
            "--findings-file", cfg["findings_file"],
            "--xml-dir", cfg["xml_dir"],
            "--output", edit_file,
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(
            f"  Error: extract-edit-xml.py failed for {group_id}: {result.stderr}",
            file=sys.stderr,
        )
        return None, 0

    # Count sections in the output XML
    if not os.path.isfile(edit_file):
        return None, 0

    try:
        tree = etree.parse(edit_file)
        section_count = len(tree.getroot().findall("section"))
    except Exception:
        return None, 0

    return edit_file, section_count


def cmd_next(args):
    """Merge previous group (if any), extract next, return JSON status."""
    state = load_json(args.state_file)
    if state is None:
        print(json.dumps({"status": "error", "message": "State file not found"}))
        return

    errors = []

    # Step 1: Merge current group if set
    if state["current"] is not None:
        merge_errors = _merge_current(state)
        errors.extend(merge_errors)

    # Step 2: Find next non-empty group
    grouping = load_json(
        state["config"]["grouping_file"], default={"groups": []},
    )
    groups = grouping.get("groups", [])

    while state["queue"]:
        group_index = state["queue"].pop(0)
        group = groups[group_index]
        group_id = group.get("group_id", f"group-{group_index}")
        summary = group.get("root_cause_summary", "")

        edit_file, section_count = _extract_group(state, group_index)

        if section_count == 0:
            print(
                f"  Skipping group {group_index} ({group_id}): "
                f"0 matching XML sections",
                file=sys.stderr,
            )
            state["skipped"].append(group_index)
            save_json(args.state_file, state)
            continue

        # Found work — set as current and return
        state["current"] = group_index
        save_json(args.state_file, state)

        output = {
            "status": "next",
            "group_id": group_id,
            "group_index": group_index,
            "summary": summary,
            "edit_file": edit_file,
            "section_count": section_count,
        }
        if errors:
            output["merge_errors"] = errors
        print(json.dumps(output))
        return

    # Step 3: Queue exhausted — done
    state["current"] = None
    save_json(args.state_file, state)

    output = {
        "status": "done",
        "completed": len(state["completed"]),
        "skipped": len(state["skipped"]),
        "files_modified": state["files_modified"],
    }
    if errors:
        output["merge_errors"] = errors
    print(json.dumps(output))
    print(
        f"Done. {len(state['completed'])} completed, "
        f"{len(state['skipped'])} skipped, "
        f"{len(state['files_modified'])} files modified.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Script-controlled fix queue for audit findings",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Create state file")
    init_parser.add_argument("--grouping-file", required=True)
    init_parser.add_argument("--findings-file", required=True)
    init_parser.add_argument("--xml-dir", required=True)
    init_parser.add_argument("--edit-dir", required=True)
    init_parser.add_argument("--approved", required=True,
                             help="Comma-separated approved group indices")
    init_parser.add_argument("--state-file", required=True)

    # next
    next_parser = subparsers.add_parser("next", help="Process next group")
    next_parser.add_argument("--state-file", required=True)

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "next":
        cmd_next(args)


if __name__ == "__main__":
    main()
