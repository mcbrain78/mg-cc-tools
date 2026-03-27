#!/usr/bin/env python3
"""Filter and query notes from notes-inbox.json.

Reads the notes inbox and filters by audience and/or document from each
note's classification field. Notes with null/missing classification are
excluded from filtered queries. Ignores the status field entirely.

Usage:
    # All classified notes:
    python3 list-notes.py \
        --inbox .mg/docs/notes-inbox.json \
        --output /tmp/notes.json

    # Filter by audience:
    python3 list-notes.py \
        --inbox .mg/docs/notes-inbox.json \
        --audience developers \
        --output /tmp/notes.json

    # Filter by audience and document:
    python3 list-notes.py \
        --inbox .mg/docs/notes-inbox.json \
        --audience developers \
        --document ARCHITECTURE \
        --output /tmp/notes.json

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def filter_notes(notes, audience=None, document=None):
    """Filter notes by classification fields.

    Only includes notes that have a non-null classification.
    If audience and/or document are specified, filters by those fields.

    Args:
        notes: List of note dicts from the inbox.
        audience: If set, include only notes classified for this audience.
        document: If set, include only notes classified for this document.

    Returns:
        Filtered list of note dicts.
    """
    result = []
    for note in notes:
        classification = note.get("classification")
        if not classification:
            continue

        if audience and classification.get("audience") != audience:
            continue

        if document and classification.get("document") != document:
            continue

        result.append(note)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Filter and query notes from notes-inbox.json"
    )
    parser.add_argument(
        "--inbox", required=True,
        help="Path to notes-inbox.json",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write filtered results",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Filter by audience (e.g., developers)",
    )
    parser.add_argument(
        "--document", default=None,
        help="Filter by document name (e.g., ARCHITECTURE)",
    )

    args = parser.parse_args()

    inbox_path = os.path.abspath(args.inbox)
    output_path = os.path.abspath(args.output)

    # Load inbox -- treat missing file as empty
    inbox = load_json(inbox_path, default={"notes": []})
    notes = inbox.get("notes", [])

    filtered = filter_notes(
        notes,
        audience=args.audience,
        document=args.document,
    )

    save_json(output_path, filtered)

    print(
        f"Listed {len(filtered)} notes (from {len(notes)} total)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
