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


def _emit_finding(findings_file, document, audience, section_path, display, ident):
    """Emit a reference-integrity finding via add-verify-finding.py.

    `ident` is the leaf identifier (the thing missing from prose) and is
    passed as `--entity` so the suppression filter at finding-write time
    and the central filter in load-audit-findings.py can match it.
    The description backticks `ident` so audit-fixer agents can also
    extract the entity from the description as a fallback.
    """
    subprocess.run(
        [
            sys.executable, ADD_FINDING_SCRIPT,
            "--findings-file", findings_file,
            "--document", document,
            "--section", section_path,
            "--audience", audience,
            "--check", "reference-integrity",
            f"--entity={ident}",
            "--description",
            f"Declared ref {display} — identifier `{ident}` not found in section body",
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
          findings_file, document, audience, not_entities_file=None,
          covered_entities_file=None):
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

    # Load persistent coverage entries scoped to this (document, audience).
    # Keyed by (name, section) -> covered_by. Consulted per-section below;
    # entries are ignored (stale) if the covered_by ref is no longer declared.
    coverage_map = {}
    if covered_entities_file:
        raw = load_json(covered_entities_file, default=[])
        for entry in raw:
            if (entry.get("document") == document
                    and entry.get("audience") == audience):
                coverage_map[(entry["name"], entry["section"])] = (
                    entry.get("covered_by", "")
                )

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
        all_declared_paths = [
            tuple(e["path"]) for e in ref_entries if e.get("path")
        ]
        body_lower = body.lower()
        # Refs implicitly referenced via persisted covered-entities whose
        # entity name still appears in body — agrees with the resolve stage's
        # covered-by rule (e.g. `DeclarativeBase` in body covers
        # `[dep] sqlalchemy`). Stale entries (entity no longer in body)
        # do not suppress the finding.
        covered_targets = {
            covered_by
            for (name, sec), covered_by in coverage_map.items()
            if sec == section_path and name.lower() in body_lower
        }
        for entry in ref_entries:
            ident = entry.get("identifier")
            if not ident:
                continue
            display = entry.get("display")
            if not display:
                continue  # db-hierarchy ancestor entry (parse-side fan-out artefact)
            # Skip when this ref's path is a proper prefix of another declared ref's
            # path (e.g. a table ref auto-emitted by fan-out is implicitly covered
            # by any column ref under it).
            entry_path = tuple(entry.get("path") or ())
            if entry_path and any(
                len(p) > len(entry_path) and p[:len(entry_path)] == entry_path
                for p in all_declared_paths
            ):
                continue
            if ident.lower() in body_lower:
                continue
            # [flow] refs: accept the kebab/snake variant — the canonical
            # Prefect deployment name (kebab) and the Python flow function
            # name (snake) refer to the same flow.
            if display.startswith("[flow]") and (
                ident.replace("-", "_").lower() in body_lower
                or ident.replace("_", "-").lower() in body_lower
            ):
                continue
            if ident in covered_targets:
                continue
            _emit_finding(
                findings_file, document, audience,
                section_path, display, ident,
            )

        # -- Clearing: identifier match + path resolution -----------
        section_entities = entities_by_section.get(section_path, [])
        if not section_entities:
            continue

        # Build the set of identifiers declared on this section's refs once
        # (used by both coverage validation and the identifier-match pass).
        all_idents = set()
        for entry in ref_entries:
            ident = entry.get("identifier")
            if ident:
                all_idents.add(ident)
            # Directory-only refs: identifier is empty, the path itself names
            # the directory. Promote both slash forms so prose mentioning
            # `src/foo` or `src/foo/` clears against ref path `src/foo/`.
            path = entry.get("path") or []
            if not ident and len(path) == 1 and path[0].endswith("/"):
                all_idents.add(path[0])
                all_idents.add(path[0].rstrip("/"))

        # Covered-clear pass: mark entities resolved via persistent coverage
        # entries when the covered_by identifier is still declared in this
        # section. Stale entries (covered_by no longer declared) fall through
        # to normal clearing/escalation.
        coverage_cleared = set()
        for name in section_entities:
            covered_by = coverage_map.get((name, section_path))
            if covered_by and covered_by in all_idents:
                coverage_cleared.add(name)

        ident_cleared = set(coverage_cleared)
        for name in section_entities:
            if name in all_idents:
                ident_cleared.add(name)

        # Additional first-pass: dotted entity → tail of any ref path.
        # Handles cases like prose `schema.table` against a db ref path
        # (db, schema, table) where the top-level `db` component isn't in prose.
        all_paths = [
            tuple(entry["path"])
            for entry in ref_entries
            if entry.get("path")
        ]
        for name in section_entities:
            if name in ident_cleared or "." not in name:
                continue
            segments = tuple(name.split("."))
            if any(
                len(p) >= len(segments) and p[-len(segments):] == segments
                for p in all_paths
            ):
                ident_cleared.add(name)

        # Implicit-components pass: clear entities matching any path component
        # implied by the section's refs.  Handles directory shorthand (flows/,
        # src/) covered by a leaf-file ref's path, and module-path segments
        # covered by code refs.  The trailing-slash strip lets prose `flows/`
        # match the segment `flows` extracted from a config ref.
        implicit = set(section.get("implicit_components") or [])
        if implicit:
            for name in section_entities:
                if name in ident_cleared:
                    continue
                if name.rstrip("/") in implicit:
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
    parser.add_argument(
        "--covered-entities-file", default=None,
        help="Path to persistent covered-entities JSON file "
             "(entities to clear via durable coverage, stale-validated)",
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
        covered_entities_file=args.covered_entities_file,
    )


if __name__ == "__main__":
    main()
