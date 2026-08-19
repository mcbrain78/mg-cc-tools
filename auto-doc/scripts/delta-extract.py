#!/usr/bin/env python3
"""Delta extraction: skip unchanged sections across audit runs.

Compares content hashes from the current prose-verify data against
previously stored hashes. For unchanged sections, carries forward
entities from the previous run instead of re-extracting.

Usage:
    python3 delta-extract.py \
        --prose-verify-dir DIR \
        --prev-entities-file FILE \
        --entities-file FILE \
        [--changed-sections-out FILE]

Output (JSON to stdout):
    {"changed": ["section/path", ...], "reused": N}

`--changed-sections-out` writes the `changed` list to a file as well. The caller
needs it on disk anyway, to pass as the extraction agent's `--sections-filter`,
and having the producer write it removes a round trip where the orchestrator read
the list out of this JSON and interpolated it back into a shell argument -- a step
that could only ever reproduce or corrupt what was already known here.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def _hashes_file(entities_file):
    """Derive the hashes sidecar path from an entities file path."""
    base, ext = os.path.splitext(entities_file)
    return f"{base}-hashes{ext}"


def _collect_current_hashes(prose_verify_dir):
    """Read content_hash from each section JSON in the prose-verify dir.

    Returns:
        dict mapping section_path -> content_hash
    """
    manifest = load_json(
        os.path.join(prose_verify_dir, "manifest.json"),
        default={},
    )
    sections = manifest.get("sections", [])
    hashes = {}
    for section_path in sections:
        slug = section_path.rsplit("/", 1)[-1] if "/" in section_path else section_path
        parent = os.path.dirname(section_path) if "/" in section_path else ""
        json_path = os.path.join(prose_verify_dir, parent, f"{slug}.json")
        section_data = load_json(json_path, default={})
        h = section_data.get("content_hash")
        if h:
            hashes[section_path] = h
    return hashes


def delta_extract(prose_verify_dir, prev_entities_file, entities_file):
    """Compare hashes and carry forward entities for unchanged sections.

    Returns:
        dict with "changed" (list of section paths) and "reused" (int count).
    """
    current_hashes = _collect_current_hashes(prose_verify_dir)

    # Load previous hashes
    prev_hashes_path = _hashes_file(prev_entities_file)
    prev_hashes = load_json(prev_hashes_path, default={})

    # Load previous entities
    prev_entities = load_json(prev_entities_file, default=[])

    changed = []
    reused_count = 0
    carried_entities = []

    for section_path, current_hash in current_hashes.items():
        prev_hash = prev_hashes.get(section_path)
        if prev_hash and prev_hash == current_hash:
            # Unchanged — carry forward entities from this section
            section_entities = [
                e for e in prev_entities if e.get("section") == section_path
            ]
            carried_entities.extend(section_entities)
            reused_count += 1
        else:
            changed.append(section_path)

    # Also include sections that are new (in current but not in prev)
    # They're already in changed via the else branch above.

    # Write carried entities to the current entities file
    if carried_entities:
        existing = load_json(entities_file, default=[])
        existing.extend(carried_entities)
        save_json(entities_file, existing)

    # Save current hashes for next run
    current_hashes_path = _hashes_file(entities_file)
    save_json(current_hashes_path, current_hashes)

    return {"changed": sorted(changed), "reused": reused_count}


def main():
    parser = argparse.ArgumentParser(
        description="Delta extraction: skip unchanged sections across audit runs",
    )
    parser.add_argument(
        "--prose-verify-dir", required=True,
        help="Directory with per-section JSON files from prepare-prose-verify.py",
    )
    parser.add_argument(
        "--prev-entities-file", required=True,
        help="Previous run's entities file (may not exist)",
    )
    parser.add_argument(
        "--entities-file", required=True,
        help="Current run's entities file (created/appended)",
    )
    parser.add_argument(
        "--changed-sections-out",
        help="Also write the changed-sections list here, for use as a "
             "--sections-filter argument",
    )

    args = parser.parse_args()
    result = delta_extract(
        prose_verify_dir=args.prose_verify_dir,
        prev_entities_file=args.prev_entities_file,
        entities_file=args.entities_file,
    )

    if args.changed_sections_out:
        out_parent = os.path.dirname(os.path.abspath(args.changed_sections_out))
        os.makedirs(out_parent, exist_ok=True)
        # Written even when empty: the caller skips extraction in that case, and a
        # stale filter file left over from a previous run would be worse than an
        # empty one.
        save_json(args.changed_sections_out, result["changed"])

    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline
    print(
        f"Delta: {len(result['changed'])} changed, {result['reused']} reused",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
