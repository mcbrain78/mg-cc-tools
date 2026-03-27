#!/usr/bin/env python3
"""Per-section write tool for auto-doc writer agents.

Bundles section content + symbol/file references in a single call so
provenance is captured at the moment of writing, not reconstructed later.

Two modes:

Section-write (called once per section):
    python3 write-section.py \
        --state-file /tmp/write-state-developers.json \
        --document ARCHITECTURE \
        --section system-overview \
        --content-file /tmp/section-developers-ARCHITECTURE-system-overview.md \
        --refs-file /tmp/refs-developers-ARCHITECTURE-system-overview.json \
        --header-file /tmp/header-developers-ARCHITECTURE.md \
        --project-root /path/to/project

Finalize (called once per audience after all writers complete):
    python3 write-section.py \
        --finalize \
        --state-file /tmp/write-state-developers.json \
        --docs-dir /path/to/docs \
        --audience developers \
        --manifest-file /tmp/manifest-developers.json \
        --mode initial

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json, save_text
from lib.symbols import extract_python_symbols


def slugify_heading(heading):
    """Convert a heading to a slug: lowercase, spaces to hyphens, strip non-alnum."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-")


def check_symbols(symbols, file_paths, project_root):
    """Advisory symbol check -- warnings on stderr, never affects exit code.

    Only checks .py files. Skips if no symbols, no .py file_paths, or
    no symbols could be extracted from existing files.
    """
    if not symbols:
        return
    py_paths = [fp for fp in file_paths if fp.endswith(".py")]
    if not py_paths:
        return

    all_defined = set()
    for rel_path in py_paths:
        abs_path = os.path.join(project_root, rel_path)
        if not os.path.isfile(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue
        all_defined.update(extract_python_symbols(source))

    if not all_defined:
        return

    for symbol in symbols:
        if symbol not in all_defined:
            paths_str = ", ".join(py_paths)
            print(
                f"WARNING: symbol '{symbol}' not found in file_paths [{paths_str}]. "
                f"Add the file that defines it.",
                file=sys.stderr,
            )


def section_write(args):
    """Accumulate a section into the state file."""
    # Load state file (create empty if missing)
    state = load_json(args.state_file, default={"documents": {}})

    # Read content-file, validate non-empty
    if not os.path.isfile(args.content_file):
        print(f"Error: content file not found: {args.content_file}", file=sys.stderr)
        sys.exit(1)
    with open(args.content_file, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        print(f"Error: content file is empty: {args.content_file}", file=sys.stderr)
        sys.exit(1)

    # Read refs-file, validate JSON with symbols and file_paths keys
    if not os.path.isfile(args.refs_file):
        print(f"Error: refs file not found: {args.refs_file}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(args.refs_file, "r", encoding="utf-8") as f:
            refs = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in refs file: {e}", file=sys.stderr)
        sys.exit(1)
    if "symbols" not in refs or "file_paths" not in refs:
        print(
            "Error: refs file must contain 'symbols' and 'file_paths' keys",
            file=sys.stderr,
        )
        sys.exit(1)

    # If --header-file provided, store as header string for document
    header = None
    if args.header_file:
        if not os.path.isfile(args.header_file):
            print(
                f"Error: header file not found: {args.header_file}", file=sys.stderr
            )
            sys.exit(1)
        with open(args.header_file, "r", encoding="utf-8") as f:
            header = f.read()

    # Ensure document structure exists
    doc_name = args.document
    section_name = args.section

    if doc_name not in state["documents"]:
        state["documents"][doc_name] = {
            "header": "",
            "sections_order": [],
            "sections": {},
        }

    doc = state["documents"][doc_name]

    if header is not None:
        doc["header"] = header

    # If section exists, overwrite content/refs (preserve order position).
    # If new, append to sections_order.
    if section_name not in doc["sections"]:
        doc["sections_order"].append(section_name)

    doc["sections"][section_name] = {
        "content": content,
        "symbols": refs["symbols"],
        "file_paths": refs["file_paths"],
        "calls": refs.get("calls", []),
    }

    # Advisory symbol check if --project-root provided
    if args.project_root:
        check_symbols(refs["symbols"], refs["file_paths"], args.project_root)

    # Save state atomically
    save_json(args.state_file, state)

    # Print to stderr
    sym_count = len(refs["symbols"])
    fp_count = len(refs["file_paths"])
    print(
        f"Wrote section {doc_name}/{section_name} "
        f"({sym_count} symbols, {fp_count} file_paths)",
        file=sys.stderr,
    )


def parse_existing_sections(content):
    """Parse a markdown document into header + ordered sections by ## headings.

    Returns (header_text, [(slug, heading_line, section_body), ...]).
    """
    parts = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    header = ""
    sections = []

    for i, part in enumerate(parts):
        if i == 0 and not part.startswith("## "):
            header = part
        else:
            lines = part.split("\n", 1)
            heading_line = lines[0]
            body = lines[1] if len(lines) > 1 else ""
            # Extract heading text after "## "
            heading_text = heading_line[3:].strip()
            slug = slugify_heading(heading_text)
            sections.append((slug, heading_line, body))

    return header, sections


def finalize(args):
    """Assemble documents from state, generate manifests, write files."""
    # Load state file. Exit 1 if missing.
    if not os.path.isfile(args.state_file):
        print(f"Error: state file not found: {args.state_file}", file=sys.stderr)
        sys.exit(1)

    state = load_json(args.state_file, default={"documents": {}})
    mode = args.mode or "initial"
    merge = getattr(args, "merge", False)

    # For each document in state: assemble and write
    docs_written = []
    for doc_name, doc_data in state.get("documents", {}).items():
        doc_dir = os.path.join(args.docs_dir, args.audience)
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f"{doc_name}.md")

        if merge and os.path.isfile(doc_path):
            # Merge mode: read existing doc, replace/append sections from state
            with open(doc_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

            existing_header, existing_sections = parse_existing_sections(
                existing_content
            )

            # Build lookup of new sections from state
            new_sections = {}
            for section_slug in doc_data.get("sections_order", []):
                section = doc_data["sections"].get(section_slug)
                if section:
                    new_sections[section_slug] = section["content"]

            # Replace matching sections, preserve unmodified ones
            result_parts = []
            if existing_header:
                result_parts.append(existing_header.rstrip("\n"))

            seen_slugs = set()
            for slug, heading_line, body in existing_sections:
                seen_slugs.add(slug)
                if slug in new_sections:
                    result_parts.append(new_sections[slug].rstrip("\n"))
                else:
                    # Preserve original section verbatim
                    result_parts.append(
                        (heading_line + "\n" + body).rstrip("\n")
                    )

            # Append new sections not in existing doc
            for section_slug in doc_data.get("sections_order", []):
                if section_slug not in seen_slugs:
                    section = doc_data["sections"].get(section_slug)
                    if section:
                        result_parts.append(section["content"].rstrip("\n"))

            assembled = "\n\n".join(result_parts) + "\n"
        else:
            # Standard assembly: header + sections in order
            parts = []
            header = doc_data.get("header", "")
            if header:
                parts.append(header.rstrip("\n"))

            for section_slug in doc_data.get("sections_order", []):
                section = doc_data["sections"].get(section_slug)
                if section:
                    parts.append(section["content"].rstrip("\n"))

            assembled = "\n\n".join(parts) + "\n"

        save_text(doc_path, assembled)
        docs_written.append(doc_name)

    # Build manifest in merge-manifests.py input format
    manifest = {"documents": {}}

    for doc_name, doc_data in state.get("documents", {}).items():
        sections_order = doc_data.get("sections_order", [])
        sections = doc_data.get("sections", {})

        # Section entries: only for sections with non-empty symbols or file_paths
        for section_slug in sections_order:
            section = sections.get(section_slug, {})
            symbols = section.get("symbols", [])
            file_paths = section.get("file_paths", [])
            if symbols or file_paths:
                if doc_name not in manifest["documents"]:
                    manifest["documents"][doc_name] = {}
                entry = {"symbols": symbols, "file_paths": file_paths}
                calls = section.get("calls", [])
                if calls:
                    entry["calls"] = calls
                manifest["documents"][doc_name][section_slug] = entry

        # _written_sections metadata: initial mode only
        if mode == "initial":
            if doc_name not in manifest["documents"]:
                manifest["documents"][doc_name] = {}
            manifest["documents"][doc_name]["_written_sections"] = {
                "symbols": [],
                "file_paths": [],
                "sections_written": list(sections_order),
            }

    # Write manifest atomically
    save_json(args.manifest_file, manifest)

    # Delete state file
    os.remove(args.state_file)

    # Print summary to stderr
    total_sections = sum(
        len(doc.get("sections_order", []))
        for doc in state.get("documents", {}).values()
    )
    print(
        f"Finalized {len(docs_written)} documents ({total_sections} sections) "
        f"for {args.audience}",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Per-section write tool with accumulation and finalize"
    )
    parser.add_argument(
        "--state-file",
        required=True,
        help="Path to accumulator state file (one per audience)",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Switch to finalize mode",
    )
    # Section-write mode args
    parser.add_argument("--document", help="Document name (e.g., ARCHITECTURE)")
    parser.add_argument("--section", help="Section slug (e.g., system-overview)")
    parser.add_argument(
        "--content-file", help="Path to temp file with section markdown"
    )
    parser.add_argument(
        "--refs-file", help="Path to temp JSON with symbols and file_paths"
    )
    parser.add_argument(
        "--header-file",
        help="Path to temp file with doc header (first section only)",
    )
    parser.add_argument(
        "--project-root", help="Enables advisory symbol validation"
    )
    # Finalize mode args
    parser.add_argument("--docs-dir", help="Absolute path to docs output root")
    parser.add_argument("--audience", help="Audience key for subdirectory path")
    parser.add_argument("--manifest-file", help="Path to write temp manifest JSON")
    parser.add_argument(
        "--mode", default="initial", help="initial (default) or update"
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge new sections into existing document (preserves unmodified sections)",
    )

    args = parser.parse_args()

    if args.finalize:
        if not args.docs_dir:
            parser.error("--docs-dir is required in finalize mode")
        if not args.audience:
            parser.error("--audience is required in finalize mode")
        if not args.manifest_file:
            parser.error("--manifest-file is required in finalize mode")
        finalize(args)
    else:
        if not args.document:
            parser.error("--document is required in section-write mode")
        if not args.section:
            parser.error("--section is required in section-write mode")
        if not args.content_file:
            parser.error("--content-file is required in section-write mode")
        if not args.refs_file:
            parser.error("--refs-file is required in section-write mode")
        section_write(args)


if __name__ == "__main__":
    main()
