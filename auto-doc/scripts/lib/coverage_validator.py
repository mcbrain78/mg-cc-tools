"""Validate that a --covered-by identifier is declared in a section's refs.

Shared between dismiss-entity.py (resolve-agent path) and classify-entity.py
(classify-agent path) so both routes to covered-entities.json use the same
validation logic.
"""

import os

from .json_io import load_json


def section_json_path(prose_verify_dir, section_path):
    """Resolve a section path to its prose-verify JSON file location."""
    slug = os.path.basename(section_path)
    parent = os.path.dirname(section_path)
    if parent:
        return os.path.join(prose_verify_dir, parent, f"{slug}.json")
    return os.path.join(prose_verify_dir, f"{slug}.json")


def validate_covered_by(covered_by, section, prose_verify_dir):
    """Check if covered_by identifier exists in the section's ref_entries.

    Returns:
        (valid, reason) — valid is True if the identifier was found.
    """
    section_file = section_json_path(prose_verify_dir, section)
    section_data = load_json(section_file)
    if section_data is None:
        return False, f"section JSON not found: {section_file}"

    ref_entries = section_data.get("ref_entries", [])
    ref_identifiers = {
        e.get("identifier") for e in ref_entries if e.get("identifier")
    }

    if covered_by in ref_identifiers:
        return True, ""
    return False, f"identifier '{covered_by}' not found in section refs"
