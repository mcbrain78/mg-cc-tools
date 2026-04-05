"""Heading map utilities for deterministic heading injection.

Provides slugify_heading (canonical, single source) and read_heading_map
which builds a lookup from next-heading.py state files so write-section.py
can inject headings without LLM involvement.
"""

import os
import re

from lib.json_io import load_json


def slugify_heading(heading):
    """Convert a heading to a slug: lowercase, spaces to hyphens, strip non-alnum."""
    slug = heading.strip().lower()
    slug = slug.replace("/", "-")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-")


def read_heading_map(state_file_path):
    """Read a next-heading.py state file and build a heading_path -> info lookup.

    Filters queue entries where type == "write" and returns a dict keyed by
    heading_path with {"title": str, "level": int} values.

    Returns empty dict if the file doesn't exist or has no write entries.
    """
    if not os.path.isfile(state_file_path):
        return {}

    state = load_json(state_file_path, default={})
    queue = state.get("queue", [])

    result = {}
    for entry in queue:
        if entry.get("type") == "write":
            heading_path = entry.get("heading_path", "")
            if heading_path:
                result[heading_path] = {
                    "title": entry.get("title", ""),
                    "level": entry.get("level", 2),
                }
    return result
