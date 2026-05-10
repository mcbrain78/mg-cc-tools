#!/usr/bin/env python3
"""Merge temp writer manifests into persisted reference manifests.

Replaces the procedural manifest merge steps in auto-doc-generate.md
with a deterministic script. For each audience, reads the temp manifest
produced by the writer agent, overlays it onto the persisted manifest,
cleans up stale sections via _written_sections metadata, and writes
atomically.

Usage:
    python3 merge-manifests.py \
        --tmp-dir /tmp/auto-doc-xyz \
        --output-dir project/.mg/docs/reference-manifests \
        --audiences end-users,developers,agents,devops

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def process_written_sections(temp_manifest, persisted_manifest):
    """Process _written_sections metadata for stale section cleanup.

    For each document in the temp manifest, if a _written_sections entry
    exists, remove sections from the persisted manifest that are NOT in
    the sections_written list (stale sections dropped during regeneration).
    Then delete the _written_sections entry from temp so it is not persisted.

    Args:
        temp_manifest: The temp manifest dict (modified in place).
        persisted_manifest: The persisted manifest dict (modified in place).
    """
    temp_docs = temp_manifest.get("documents", {})
    persisted_docs = persisted_manifest.get("documents", {})

    for doc_name, sections in list(temp_docs.items()):
        if "_written_sections" not in sections:
            continue

        written_meta = sections["_written_sections"]
        sections_written = written_meta.get("sections_written", [])

        # Remove stale sections from persisted manifest
        if doc_name in persisted_docs:
            persisted_sections = persisted_docs[doc_name]
            stale_keys = [
                key for key in list(persisted_sections.keys())
                if key != "_written_sections" and key not in sections_written
            ]
            for key in stale_keys:
                del persisted_sections[key]

        # Delete metadata entry from temp (don't persist it)
        del sections["_written_sections"]


def overlay_manifests(temp_manifest, persisted_manifest):
    """Overlay temp manifest entries onto persisted manifest.

    For each document -> section in the temp manifest, replace the
    matching entry in the persisted manifest. Preserve entries in
    the persisted manifest that are not in the temp manifest.

    Args:
        temp_manifest: The temp manifest dict (source).
        persisted_manifest: The persisted manifest dict (modified in place).

    Returns:
        The updated persisted manifest dict.
    """
    if "documents" not in persisted_manifest:
        persisted_manifest["documents"] = {}

    temp_docs = temp_manifest.get("documents", {})
    for doc_name, sections in temp_docs.items():
        if doc_name not in persisted_manifest["documents"]:
            persisted_manifest["documents"][doc_name] = {}
        for section_name, section_data in sections.items():
            persisted_manifest["documents"][doc_name][section_name] = section_data

    return persisted_manifest


def merge_audience(tmp_dir, output_dir, audience):
    """Merge temp manifest for a single audience into persisted manifest.

    Args:
        tmp_dir: Directory containing temp manifests.
        output_dir: Directory containing persisted reference manifests.
        audience: The audience key (e.g., "developers").

    Returns:
        (doc_count, section_count) tuple, or None if temp manifest missing.
    """
    temp_path = os.path.join(tmp_dir, f"manifest-{audience}.json")
    if not os.path.isfile(temp_path):
        return None

    temp_manifest = load_json(temp_path, default={})
    persisted_path = os.path.join(output_dir, f"{audience}.json")
    persisted_manifest = load_json(persisted_path, default={
        "audience": audience,
        "generated": "",
        "documents": {},
    })

    # Step 1: Process _written_sections for stale cleanup
    process_written_sections(temp_manifest, persisted_manifest)

    # Step 2: Overlay temp entries onto persisted
    overlay_manifests(temp_manifest, persisted_manifest)

    # Step 3: Update metadata
    persisted_manifest["audience"] = audience
    persisted_manifest["generated"] = datetime.now(timezone.utc).isoformat()

    # Step 4: Write atomically
    save_json(persisted_path, persisted_manifest)

    docs = persisted_manifest.get("documents", {})
    if not isinstance(docs, dict):
        docs = {}
    doc_count = len(docs)
    section_count = sum(len(secs) for secs in docs.values())
    return doc_count, section_count


def main():
    parser = argparse.ArgumentParser(
        description="Merge temp writer manifests into persisted reference manifests"
    )
    parser.add_argument(
        "--tmp-dir", required=True,
        help="Directory containing temp manifest files",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Directory for persisted reference manifests",
    )
    parser.add_argument(
        "--audiences", required=True,
        help="Comma-separated list of audience keys",
    )

    args = parser.parse_args()
    audiences = [a.strip() for a in args.audiences.split(",") if a.strip()]

    os.makedirs(args.output_dir, exist_ok=True)

    for audience in audiences:
        result = merge_audience(args.tmp_dir, args.output_dir, audience)
        if result is None:
            print(
                f"{audience}: skipped (no temp manifest)",
                file=sys.stderr,
            )
        else:
            doc_count, section_count = result
            print(
                f"{audience}: {doc_count} documents, {section_count} sections",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
