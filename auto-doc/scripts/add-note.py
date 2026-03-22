#!/usr/bin/env python3
"""Append a single note to notes-inbox.json.

Called by the /mg:auto-doc-add command to capture documentation notes
atomically. Each note gets a sequential ID (NOTE-001, NOTE-002, ...),
an ISO timestamp, optional context (phase, file), and starts with
status "pending" and classification None.

Usage:
    python3 add-note.py \
        --inbox <path/to/notes-inbox.json> \
        --text "Document the new auth flow" \
        [--phase "01-foundation"] \
        [--file "src/auth.py"]

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def next_note_id(notes):
    """Generate the next sequential NOTE-NNN id.

    Uses max existing number + 1 to handle gaps in numbering.
    Returns NOTE-001 for an empty notes list.
    """
    max_num = 0
    for note in notes:
        match = re.match(r"NOTE-(\d+)", note.get("id", ""))
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return f"NOTE-{max_num + 1:03d}"


def main():
    parser = argparse.ArgumentParser(
        description="Append a note to notes-inbox.json"
    )
    parser.add_argument(
        "--inbox", required=True,
        help="Path to notes-inbox.json"
    )
    parser.add_argument(
        "--text", required=True,
        help="Note text"
    )
    parser.add_argument(
        "--phase", default=None,
        help="GSD phase context (optional)"
    )
    parser.add_argument(
        "--file", default=None, dest="context_file",
        help="Active file context (optional)"
    )

    args = parser.parse_args()

    inbox_path = os.path.abspath(args.inbox)
    inbox = load_json(inbox_path, default={"notes": []})

    # Ensure notes array exists
    if "notes" not in inbox:
        inbox["notes"] = []

    note_id = next_note_id(inbox["notes"])

    note = {
        "id": note_id,
        "text": args.text,
        "added": datetime.now(timezone.utc).isoformat(),
        "context": {
            "phase": args.phase,
            "file": args.context_file,
        },
        "classification": None,
        "status": "pending",
    }

    inbox["notes"].append(note)
    save_json(inbox_path, inbox)

    # Truncate display text for confirmation
    display_text = args.text[:60]
    if len(args.text) > 60:
        display_text += "..."
    print(f"Added note {note_id}: {display_text}", file=sys.stderr)


if __name__ == "__main__":
    main()
