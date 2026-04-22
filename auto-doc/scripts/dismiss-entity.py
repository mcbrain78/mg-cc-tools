#!/usr/bin/env python3
"""Dismiss an entity from the uncleared list.

When --covered-by is provided and the identifier is present in the section's
declared refs, the entity is recorded in the persistent covered-entities file
(durable across audits) and removed from uncleared. This path runs regardless
of whether the entity is on the protected list — a successful coverage
assertion is its own resolution.

Otherwise, the entity goes through the protected check and the pattern guard,
then gets appended to the per-run dismissed-this-run file so the post-wave
classification agent can decide whether it belongs on the permanent
not-entities or protected-entities list.

Usage:
    python3 dismiss-entity.py \
        --entity NAME \
        --section SECTION \
        --uncleared-file FILE \
        --dismissed-this-run-file FILE \
        --audience AUDIENCE \
        --document DOCUMENT \
        [--protected-entities-file FILE] \
        [--covered-by IDENTIFIER --prose-verify-dir DIR --covered-entities-file FILE]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.coverage_validator import record_covered, validate_covered_by
from lib.json_io import load_json, save_json

# File extensions that indicate a file reference
_FILE_EXTENSIONS = (
    ".py", ".yaml", ".yml", ".json", ".sh", ".ini", ".toml",
    ".cfg", ".xml", ".env", ".md", ".sql",
)

# Schema-qualified name: word.word where each segment is ≥3 lowercase chars
# (catches raw_fmp.income_statements, public.stocks; excludes i.e., e.g., os.path)
_SCHEMA_QUALIFIED_RE = re.compile(r"^[a-z_][a-z0-9_]{2,}\.[a-z_][a-z0-9_]{2,}$")


def is_pattern_blocked(entity, ref_entries=None):
    """Check if entity matches a structurally ref-like pattern.

    For schema-qualified names (two dotted segments ≥3 chars each), the block
    is context-aware: if any declared ref path tail matches the dotted form,
    block dismissal (the entity IS covered by a real ref and should file a
    finding or use --covered-by). If no path matches, allow dismissal — the
    entity is likely a stdlib dotted name like ``json.loads`` and classifying
    it as not-entity is correct.

    Args:
        entity: The entity name considered for dismissal.
        ref_entries: Optional list of section ref_entries (each with a
            ``path`` array). When ``None``, schema-qualified names are
            blocked unconditionally (legacy behavior).

    Returns:
        (blocked, pattern) — blocked is True if the entity should not be
        dismissed; pattern describes why.
    """
    # File reference: contains / or ends with a known extension
    if "/" in entity:
        return True, "file path"
    for ext in _FILE_EXTENSIONS:
        if entity.endswith(ext):
            return True, f"file reference ({ext})"

    # Schema-qualified name: word.word with ≥3-char segments
    if _SCHEMA_QUALIFIED_RE.match(entity):
        if ref_entries is None:
            return True, "schema-qualified name"
        segments = tuple(entity.split("."))
        for entry in ref_entries:
            path = tuple(entry.get("path") or ())
            if len(path) >= len(segments) and path[-len(segments):] == segments:
                return True, "schema-qualified name matching declared ref"
        # No declared ref path tail matches → allow dismissal
        return False, ""

    return False, ""


def _section_json_path(prose_verify_dir, section_path):
    """Resolve section path to its JSON file location."""
    slug = os.path.basename(section_path)
    parent = os.path.dirname(section_path)
    if parent:
        return os.path.join(prose_verify_dir, parent, f"{slug}.json")
    return os.path.join(prose_verify_dir, f"{slug}.json")


def dismiss(
    entity,
    section,
    uncleared_file,
    dismissed_this_run_file,
    audience,
    document,
    protected_entities_file=None,
    covered_by=None,
    prose_verify_dir=None,
    covered_entities_file=None,
):
    """Dismiss entity from uncleared.

    With --covered-by: validates the covering identifier against the section's
    ref_entries. On success, records in the persistent covered-entities file
    and removes from uncleared (regardless of protection state). On failure,
    refuses.

    Without --covered-by: protected check, then pattern guard, then plain
    dismiss into dismissed-this-run.

    Returns:
        Tuple of (before_count, after_count), or None if refused.
    """
    # Coverage path: validated --covered-by wins regardless of protection
    if covered_by and prose_verify_dir:
        valid, reason = validate_covered_by(
            covered_by, section, prose_verify_dir,
        )
        if not valid:
            print(
                f"Cannot dismiss {entity} — --covered-by failed: {reason}",
                file=sys.stderr,
            )
            return None
        if covered_entities_file:
            record_covered(
                entity, section, audience, document,
                covered_by, covered_entities_file,
            )
        # Remove from uncleared (all entries for this entity, all sections)
        uncleared = load_json(uncleared_file, default=[])
        before = len(uncleared)
        updated = [e for e in uncleared if e["name"] != entity]
        save_json(uncleared_file, updated)
        after = len(updated)
        print(
            f"Covered: {entity} (by {covered_by}). "
            f"Uncleared: {before} → {after}",
            file=sys.stderr,
        )
        return before, after

    # No --covered-by: protected list blocks plain dismissal
    if protected_entities_file:
        protected = load_json(protected_entities_file, default=[])
        protected_names = {
            e["name"] if isinstance(e, dict) else e for e in protected
        }
        if entity in protected_names:
            print(
                f"PROTECTED: {entity} — this entity was previously confirmed "
                "as ref-worthy. File a finding instead.",
                file=sys.stderr,
            )
            return None

    # Pattern guard: refuse to dismiss structurally ref-like entities.
    # Pull section ref context when available so schema-qualified names are
    # only blocked if a declared ref path tail matches (avoids blocking
    # dismissal of stdlib dotted names like json.loads).
    ref_entries = None
    if prose_verify_dir:
        section_file = _section_json_path(prose_verify_dir, section)
        section_data = load_json(section_file)
        if section_data is not None:
            ref_entries = section_data.get("ref_entries", [])

    blocked, pattern = is_pattern_blocked(entity, ref_entries=ref_entries)
    if blocked:
        print(
            f"Cannot dismiss {entity} — looks like a {pattern}. "
            "File a finding instead.",
            file=sys.stderr,
        )
        return None

    uncleared = load_json(uncleared_file, default=[])
    before_count = len(uncleared)

    # Capture all sections where this entity was uncleared (for the classifier
    # to emit per-section findings). Must happen before the removal below.
    entity_sections = sorted({
        e["section"] for e in uncleared if e["name"] == entity
    })

    # Remove ALL entries with this entity name (across all sections)
    updated = [e for e in uncleared if e["name"] != entity]
    save_json(uncleared_file, updated)
    after_count = len(updated)

    # Add to dismissed-this-run (dedup by name)
    dismissed = load_json(dismissed_this_run_file, default=[])
    existing_names = {e["name"] for e in dismissed}
    if entity not in existing_names:
        dismissed.append({
            "name": entity,
            "sections": entity_sections,
            "audience": audience,
            "document": document,
        })
        save_json(dismissed_this_run_file, dismissed)

    print(
        f"Dismissed: {entity}. Uncleared: {before_count} → {after_count}",
        file=sys.stderr,
    )
    return before_count, after_count


def main():
    parser = argparse.ArgumentParser(
        description="Dismiss an entity from uncleared into dismissed-this-run",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to dismiss",
    )
    parser.add_argument(
        "--section", required=True,
        help="Section where the agent decided to dismiss",
    )
    parser.add_argument(
        "--uncleared-file", required=True,
        help="Path to uncleared entities JSON file",
    )
    parser.add_argument(
        "--dismissed-this-run-file", required=True,
        help="Path to dismissed-this-run JSON file",
    )
    parser.add_argument(
        "--audience", required=True,
        help="Audience name (e.g., devops, developer)",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document name (e.g., OPERATIONS)",
    )
    parser.add_argument(
        "--protected-entities-file",
        help="Path to protected-entities JSON file (optional)",
    )
    parser.add_argument(
        "--covered-by",
        help="Ref identifier that covers this entity (durable clear)",
    )
    parser.add_argument(
        "--prose-verify-dir",
        help="Path to prose-verify dir (required with --covered-by)",
    )
    parser.add_argument(
        "--covered-entities-file",
        help="Path to persistent covered-entities JSON file "
             "(required with --covered-by to record durable coverage)",
    )

    args = parser.parse_args()
    dismiss(
        entity=args.entity,
        section=args.section,
        uncleared_file=args.uncleared_file,
        dismissed_this_run_file=args.dismissed_this_run_file,
        audience=args.audience,
        document=args.document,
        protected_entities_file=args.protected_entities_file,
        covered_by=args.covered_by,
        prose_verify_dir=args.prose_verify_dir,
        covered_entities_file=args.covered_entities_file,
    )


if __name__ == "__main__":
    main()
