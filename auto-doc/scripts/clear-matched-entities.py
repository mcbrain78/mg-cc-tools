#!/usr/bin/env python3
"""Deterministic clearing of extracted entities against declared refs.

After wave 1 (LLM entity extraction), this script performs two operations
per section:

1. **Clearing (Check A partial):** Two-pass resolution per section.
   *First pass:* clear entities whose name exactly matches any ref
   identifier declared in the section's refs.
   *Second pass:* conservative path resolution for remaining entities —
   an entity clears when exactly one ref path is consistent with the
   entity set.  Uncleared entities go to the LLM for judgment.

2. **Check B (ref → body):** For each ref identifier, check whether it
   appears as a substring in the section body.  Missing identifiers are
   emitted as ``reference-integrity`` findings.

Usage:
    python3 clear-matched-entities.py \
        --entities-file FILE \
        --prose-verify-dir DIR \
        --uncleared-file FILE \
        --findings-file FILE \
        --document DOC \
        --audience AUD
"""

import argparse
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

ADD_FINDING_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "add-verify-finding.py",
)


def _section_json_path(prose_verify_dir, section_path):
    """Resolve section path to its JSON file location."""
    slug = os.path.basename(section_path)
    parent = os.path.dirname(section_path)
    if parent:
        return os.path.join(prose_verify_dir, parent, f"{slug}.json")
    return os.path.join(prose_verify_dir, f"{slug}.json")


def _emit_finding(findings_file, document, audience, section_path, display):
    """Emit a reference-integrity finding via add-verify-finding.py."""
    subprocess.run(
        [
            sys.executable, ADD_FINDING_SCRIPT,
            "--findings-file", findings_file,
            "--document", document,
            "--section", section_path,
            "--audience", audience,
            "--check", "reference-integrity",
            "--description",
            f"Declared ref {display} — identifier not found in section body",
            "--suggestion",
            "Remove the ref if the entity is no longer discussed, "
            "or mention it in the prose",
            "--wave", "0",
        ],
        capture_output=True, text=True,
    )


def _expand_dotted(entity_set):
    """Expand dotted entity names into component segments for matching."""
    expanded = set(entity_set)
    for name in entity_set:
        if "." in name:
            expanded.update(name.split("."))
    return expanded


def _resolve_entities(section_entities, ref_entries, context_names=None):
    """Conservative path resolution for multi-component clearing.

    An entity clears only when there is exactly one ref path consistent
    with the entity set in the section.  Uses a fixed-point loop: when
    a path is uniquely resolved, its newly-cleared components may
    disambiguate remaining entities.

    Args:
        section_entities: Entity names to attempt to clear.
        ref_entries: Ref entries with path arrays.
        context_names: Additional names considered present for path
            component checks (e.g. identifier-cleared entities).

    Returns:
        Tuple of (cleared_set, uncleared_set).
    """
    paths = [tuple(e["path"]) for e in ref_entries if e.get("path")]
    entity_set = set(section_entities)
    if context_names:
        entity_set |= set(context_names)
    entity_set = _expand_dotted(entity_set)

    # Inverted index: component name → list of paths containing it
    by_name = defaultdict(list)
    for path in paths:
        for component in path:
            by_name[component].append(path)

    cleared = set()
    progress = True
    while progress:
        progress = False
        for name in sorted(entity_set - cleared,
                           key=lambda n: len(by_name.get(n, []))):
            candidates = [
                p for p in by_name.get(name, [])
                if all(c in entity_set for c in p)
            ]
            if len(candidates) == 1:
                cleared.update(candidates[0])
                progress = True
                break  # restart — new clearings may disambiguate others

    return cleared, entity_set - cleared


def clear(entities_file, prose_verify_dir, uncleared_file,
          findings_file, document, audience, not_entities_file=None):
    """Run clearing + Check B across all sections.

    Returns:
        Tuple of (total_extracted, total_cleared, total_uncleared,
        affected_sections).
    """
    entities = load_json(entities_file, default=[])

    # Pre-filter entities against not-entities list (from prior dismissals)
    if not_entities_file:
        raw = load_json(not_entities_file, default=[])
        not_entity_names = {
            e["name"] if isinstance(e, dict) else e for e in raw
        }
        entities = [e for e in entities if e["name"] not in not_entity_names]

    # Normalize: strip trailing () from function-call notation
    for ent in entities:
        if ent["name"].endswith("()"):
            ent["name"] = ent["name"][:-2]

    manifest = load_json(os.path.join(prose_verify_dir, "manifest.json"))
    if manifest is None:
        print("Error: manifest.json not found", file=sys.stderr)
        sys.exit(1)

    # Group entities by section
    entities_by_section = {}
    for ent in entities:
        entities_by_section.setdefault(ent["section"], []).append(ent["name"])

    total_extracted = len(entities)
    total_cleared = 0
    uncleared = []
    affected_sections = []

    for section_path in manifest["sections"]:
        section_file = _section_json_path(prose_verify_dir, section_path)
        section = load_json(section_file)
        if section is None:
            continue

        ref_entries = section.get("ref_entries", [])
        body = section.get("body", "")

        # -- Check B: ref identifier → body ---------------------
        for entry in ref_entries:
            ident = entry.get("identifier")
            if not ident:
                continue
            if ident not in body:
                _emit_finding(
                    findings_file, document, audience,
                    section_path, entry.get("display", ident),
                )

        # -- Clearing: identifier match + path resolution -----------
        section_entities = entities_by_section.get(section_path, [])
        if not section_entities:
            continue

        # First pass: clear by identifier match
        all_idents = set()
        for entry in ref_entries:
            ident = entry.get("identifier")
            if ident:
                all_idents.add(ident)

        ident_cleared = set()
        for name in section_entities:
            if name in all_idents:
                ident_cleared.add(name)

        # Second pass: path resolution for remaining entities
        remaining = [n for n in section_entities if n not in ident_cleared]
        if remaining:
            path_cleared, _ = _resolve_entities(
                remaining, ref_entries, context_names=ident_cleared)
        else:
            path_cleared = set()

        cleared = ident_cleared | path_cleared

        section_has_uncleared = False
        for name in section_entities:
            if name in cleared:
                total_cleared += 1
            elif "." in name and all(seg in cleared for seg in name.split(".")):
                total_cleared += 1
            else:
                uncleared.append({"name": name, "section": section_path})
                section_has_uncleared = True

        if section_has_uncleared:
            affected_sections.append(section_path)

    # Write outputs
    save_json(uncleared_file, uncleared)
    affected_path = os.path.join(prose_verify_dir, "affected-sections.json")
    save_json(affected_path, affected_sections)

    total_uncleared = len(uncleared)
    n_affected = len(affected_sections)
    print(
        f"Extracted: {total_extracted}, Cleared: {total_cleared}, "
        f"Uncleared: {total_uncleared} across {n_affected} sections",
        file=sys.stderr,
    )
    return total_extracted, total_cleared, total_uncleared, affected_sections


def main():
    parser = argparse.ArgumentParser(
        description="Clear matched entities and run Check B",
    )
    parser.add_argument(
        "--entities-file", required=True,
        help="Path to wave-1 entities JSON file",
    )
    parser.add_argument(
        "--prose-verify-dir", required=True,
        help="Path to directory with manifest.json and per-section JSONs",
    )
    parser.add_argument(
        "--uncleared-file", required=True,
        help="Path to write uncleared entities JSON",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to findings JSON file (Check B appends here)",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document name (e.g. OPERATIONS)",
    )
    parser.add_argument(
        "--audience", required=True,
        help="Audience name (e.g. devops)",
    )
    parser.add_argument(
        "--not-entities-file", default=None,
        help="Path to not-entities JSON file (entities to pre-filter)",
    )

    args = parser.parse_args()
    clear(
        entities_file=args.entities_file,
        prose_verify_dir=args.prose_verify_dir,
        uncleared_file=args.uncleared_file,
        findings_file=args.findings_file,
        document=args.document,
        audience=args.audience,
        not_entities_file=args.not_entities_file,
    )


if __name__ == "__main__":
    main()
