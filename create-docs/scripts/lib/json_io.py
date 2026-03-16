"""Shared JSON I/O utilities for create-docs scripts.

Provides atomic JSON load/save helpers used by all pipeline scripts.
Atomic writes use a temp file + os.replace() pattern to prevent
corruption from interrupted writes.

Zero external dependencies -- stdlib only.
"""

import json
import os


def load_json(path, default=None):
    """Load JSON from path, returning default if file doesn't exist.

    Args:
        path: Path to the JSON file.
        default: Value to return if the file doesn't exist.
            Defaults to None.

    Returns:
        Parsed JSON data, or default if file not found.
    """
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Atomic write JSON to path via temp file + os.replace.

    Creates parent directories if they don't exist. Writes to a
    temporary file first, then atomically replaces the target to
    prevent corruption from interrupted writes.

    Args:
        path: Destination file path.
        data: JSON-serializable data to write.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
