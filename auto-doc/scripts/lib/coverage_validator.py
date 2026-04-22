"""Covered-entities validation and durable-record helpers.

Shared between dismiss-entity.py (resolve-agent path) and classify-entity.py
(classify-agent path) so both routes to covered-entities.json use the same
validation logic and schema.
"""

import os

from .json_io import load_json, save_json


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


def record_covered(entity, section, audience, document, covered_by,
                   covered_entities_file):
    """Append a coverage entry (deduped by name+section+document+audience).

    Returns True if added, False if an identical entry already existed.
    """
    covered = load_json(covered_entities_file, default=[])
    key = (entity, section, document, audience)
    existing_keys = {
        (e.get("name"), e.get("section"), e.get("document"), e.get("audience"))
        for e in covered
    }
    if key in existing_keys:
        return False
    covered.append({
        "name": entity,
        "section": section,
        "audience": audience,
        "document": document,
        "covered_by": covered_by,
    })
    save_json(covered_entities_file, covered)
    return True
