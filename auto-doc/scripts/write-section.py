#!/usr/bin/env python3
"""Per-section write tool for auto-doc writer agents.

Bundles section content + typed references in a single call so
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

    The refs file must contain a ``typed_refs`` key with a list of ref dicts.
    ``symbols`` and ``file_paths`` are derived automatically from typed_refs.

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
from lib.xml_doc import (
    add_section,
    build_xml_doc,
    get_section_paths,
    serialize_xml_doc,
    update_section_body,
    update_section_refs,
)


def _derive_symbols_and_file_paths(typed_refs):
    """Derive symbols and file_paths lists from typed_refs.

    symbols  = names from code refs (deduplicated, order-preserved)
    file_paths = modules from code refs + paths from config refs (deduplicated)
    """
    symbols = []
    file_paths = []
    seen_sym = set()
    seen_fp = set()

    for ref in typed_refs:
        rtype = ref.get("type")
        if rtype == "code":
            name = ref.get("name", "")
            if name and name not in seen_sym:
                symbols.append(name)
                seen_sym.add(name)
            module = ref.get("module", "")
            if module and module not in seen_fp:
                file_paths.append(module)
                seen_fp.add(module)
        elif rtype == "config":
            path = ref.get("path", "")
            if path and path not in seen_fp:
                file_paths.append(path)
                seen_fp.add(path)

    return symbols, file_paths


def _extract_diataxis(header):
    """Extract DIATAXIS type from header comment like <!-- DIATAXIS: how-to -->."""
    m = re.search(r"<!--\s*DIATAXIS:\s*(.+?)\s*-->", header)
    return m.group(1) if m else ""


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


def _resolve_parent(doc, parent_path):
    """Walk the state tree to find the parent section dict.

    Args:
        doc: Document dict from state (has sections, sections_order).
        parent_path: Slash-separated path (e.g., "monitoring-alerting/health-artifact").

    Returns:
        The parent section dict (which has subsections/subsections_order).

    Raises:
        SystemExit: If any path segment doesn't exist.
    """
    segments = parent_path.split("/")

    # First segment must be in top-level sections
    current = doc["sections"].get(segments[0])
    if current is None:
        print(f"Error: parent section not found: {segments[0]}", file=sys.stderr)
        sys.exit(1)

    # Walk remaining segments through subsections
    for i, seg in enumerate(segments[1:], 1):
        subs = current.get("subsections", {})
        current = subs.get(seg)
        if current is None:
            path_so_far = "/".join(segments[:i + 1])
            print(
                f"Error: parent section not found: {path_so_far}",
                file=sys.stderr,
            )
            sys.exit(1)

    return current


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

    # Inject <!-- section: slug --> marker before ## heading if not present
    section_name = args.section
    marker = f"<!-- section: {section_name} -->"
    if marker not in content:
        content = f"{marker}\n{content}"

    # Read refs-file, validate JSON with typed_refs key
    if not os.path.isfile(args.refs_file):
        print(f"Error: refs file not found: {args.refs_file}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(args.refs_file, "r", encoding="utf-8") as f:
            refs = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in refs file: {e}", file=sys.stderr)
        sys.exit(1)
    if "typed_refs" not in refs:
        print(
            "Error: refs file must contain 'typed_refs' key",
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

    if doc_name not in state["documents"]:
        state["documents"][doc_name] = {
            "header": "",
            "sections_order": [],
            "sections": {},
        }

    doc = state["documents"][doc_name]

    if header is not None:
        doc["header"] = header

    # Derive symbols and file_paths from typed_refs
    typed_refs = refs["typed_refs"]
    derived_symbols, derived_file_paths = _derive_symbols_and_file_paths(typed_refs)

    # Build the new section entry (always includes subsections keys)
    new_entry = {
        "content": content,
        "symbols": derived_symbols,
        "file_paths": derived_file_paths,
        "typed_refs": typed_refs,
        "subsections": {},
        "subsections_order": [],
    }

    parent_path = getattr(args, "parent", None)

    if parent_path:
        # Resolve parent in the state tree
        parent_section = _resolve_parent(doc, parent_path)

        # Ensure parent has subsections structure
        if "subsections" not in parent_section:
            parent_section["subsections"] = {}
        if "subsections_order" not in parent_section:
            parent_section["subsections_order"] = []

        # If overwriting existing child, preserve its subsections
        existing_child = parent_section["subsections"].get(section_name)
        if existing_child:
            new_entry["subsections"] = existing_child.get("subsections", {})
            new_entry["subsections_order"] = existing_child.get(
                "subsections_order", []
            )
        else:
            parent_section["subsections_order"].append(section_name)

        parent_section["subsections"][section_name] = new_entry
    else:
        # Top-level section (existing behavior + new subsections keys)
        if section_name not in doc["sections"]:
            doc["sections_order"].append(section_name)

        # If overwriting existing section, preserve its subsections
        existing = doc["sections"].get(section_name)
        if existing:
            new_entry["subsections"] = existing.get("subsections", {})
            new_entry["subsections_order"] = existing.get(
                "subsections_order", []
            )

        doc["sections"][section_name] = new_entry

    # Advisory symbol check if --project-root provided
    if args.project_root:
        check_symbols(derived_symbols, derived_file_paths, args.project_root)

    # Save state atomically
    save_json(args.state_file, state)

    # Print to stderr
    sym_count = len(derived_symbols)
    fp_count = len(derived_file_paths)
    print(
        f"Wrote section {doc_name}/{section_name} "
        f"({sym_count} symbols, {fp_count} file_paths)",
        file=sys.stderr,
    )


def parse_existing_sections(content):
    """Parse a markdown document into header + ordered sections by headings.

    Splits on ## through ##### headings. Returns flat list with
    path-based keys for merge matching.

    Returns:
        (header_text, [(path, heading_line, section_body), ...])
        where path is slash-separated (e.g., "monitoring/etl-logging").
    """
    parts = re.split(r"(?=^#{2,5} )", content, flags=re.MULTILINE)
    header = ""
    sections = []

    # Stack tracks current slug at each depth level
    # depth 0 = ##, depth 1 = ###, etc.
    path_stack = []

    for i, part in enumerate(parts):
        if i == 0 and not re.match(r"^#{2,5} ", part):
            header = part
            continue

        lines = part.split("\n", 1)
        heading_line = lines[0]
        body = lines[1] if len(lines) > 1 else ""

        # Count heading level
        match = re.match(r"^(#{2,5}) ", heading_line)
        if not match:
            continue
        level = len(match.group(1))  # 2 for ##, 3 for ###, etc.
        depth = level - 2  # 0 for ##, 1 for ###, etc.

        heading_text = heading_line[level + 1:].strip()
        slug = slugify_heading(heading_text)

        # Trim stack to current depth, then append slug
        path_stack = path_stack[:depth]
        path_stack.append(slug)
        path = "/".join(path_stack)

        sections.append((path, heading_line, body))

    return header, sections


def _state_section_to_xml_section(slug, section_data):
    """Recursively convert state section to XML section format.

    Returns:
        Dict with slug, body, and children keys.
    """
    children = []
    for child_slug in section_data.get("subsections_order", []):
        child_data = section_data.get("subsections", {}).get(child_slug)
        if child_data:
            children.append(_state_section_to_xml_section(child_slug, child_data))
    return {
        "slug": slug,
        "body": section_data["content"],
        "children": children,
    }


def _state_sections_to_xml(doc_data):
    """Convert state document data to list of section dicts for build_xml_doc."""
    sections = []
    for slug in doc_data.get("sections_order", []):
        section = doc_data.get("sections", {}).get(slug)
        if section:
            sections.append(_state_section_to_xml_section(slug, section))
    return sections


def _collect_all_sections_depth_first(sections, sections_order, prefix=""):
    """Recursively collect (path, section_data) in depth-first order."""
    result = []
    for slug in sections_order:
        section = sections.get(slug)
        if not section:
            continue
        path = f"{prefix}/{slug}" if prefix else slug
        result.append((path, section))
        result.extend(_collect_all_sections_depth_first(
            section.get("subsections", {}),
            section.get("subsections_order", []),
            path,
        ))
    return result


def _collect_manifest_entries(sections, sections_order, prefix=""):
    """Recursively collect manifest entries from nested state tree.

    Yields (path, symbols, file_paths) for sections with non-empty refs.
    """
    for slug in sections_order:
        section = sections.get(slug)
        if not section:
            continue
        path = f"{prefix}/{slug}" if prefix else slug
        symbols = section.get("symbols", [])
        file_paths = section.get("file_paths", [])
        if symbols or file_paths:
            yield path, symbols, file_paths
        # Recurse into subsections
        yield from _collect_manifest_entries(
            section.get("subsections", {}),
            section.get("subsections_order", []),
            path,
        )


def _collect_all_paths(sections, sections_order, prefix=""):
    """Collect all section paths from nested state tree."""
    paths = []
    for slug in sections_order:
        section = sections.get(slug)
        if not section:
            continue
        path = f"{prefix}/{slug}" if prefix else slug
        paths.append(path)
        paths.extend(_collect_all_paths(
            section.get("subsections", {}),
            section.get("subsections_order", []),
            path,
        ))
    return paths


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
        if args.audience:
            doc_dir = os.path.join(args.docs_dir, args.audience)
        else:
            doc_dir = args.docs_dir
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f"{doc_name}.md")

        if merge and os.path.isfile(doc_path):
            # Merge mode: read existing doc, replace/append sections from state
            with open(doc_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

            existing_header, existing_sections = parse_existing_sections(
                existing_content
            )

            # Build lookup of new sections from state (keyed by path)
            new_sections = {}
            all_state_sections = _collect_all_sections_depth_first(
                doc_data.get("sections", {}),
                doc_data.get("sections_order", []),
            )
            for path, sec_data in all_state_sections:
                new_sections[path] = sec_data["content"]

            # Replace matching sections, preserve unmodified ones
            result_parts = []
            if existing_header:
                result_parts.append(existing_header.rstrip("\n"))

            seen_paths = set()
            for path, heading_line, body in existing_sections:
                seen_paths.add(path)
                if path in new_sections:
                    result_parts.append(new_sections[path].rstrip("\n"))
                else:
                    # Preserve original section verbatim
                    result_parts.append(
                        (heading_line + "\n" + body).rstrip("\n")
                    )

            # Append new sections not in existing doc
            for path, sec_data in all_state_sections:
                if path not in seen_paths:
                    result_parts.append(sec_data["content"].rstrip("\n"))

            assembled = "\n\n".join(result_parts) + "\n"
        else:
            # Standard assembly: header + sections depth-first
            parts = []
            header = doc_data.get("header", "")
            if header:
                parts.append(header.rstrip("\n"))

            all_state_sections = _collect_all_sections_depth_first(
                doc_data.get("sections", {}),
                doc_data.get("sections_order", []),
            )
            for _path, sec_data in all_state_sections:
                parts.append(sec_data["content"].rstrip("\n"))

            assembled = "\n\n".join(parts) + "\n"

        save_text(doc_path, assembled)
        docs_written.append(doc_name)

    # Build manifest in merge-manifests.py input format
    manifest = {"documents": {}}

    for doc_name, doc_data in state.get("documents", {}).items():
        sections_order = doc_data.get("sections_order", [])
        sections = doc_data.get("sections", {})

        # Section entries: recursively collect all sections with non-empty refs
        for path, symbols, file_paths_list in _collect_manifest_entries(
            sections, sections_order
        ):
            if doc_name not in manifest["documents"]:
                manifest["documents"][doc_name] = {}
            entry = {"symbols": symbols, "file_paths": file_paths_list}
            manifest["documents"][doc_name][path] = entry

        # _written_sections metadata: initial mode only
        if mode == "initial":
            if doc_name not in manifest["documents"]:
                manifest["documents"][doc_name] = {}
            manifest["documents"][doc_name]["_written_sections"] = {
                "symbols": [],
                "file_paths": [],
                "sections_written": _collect_all_paths(
                    sections, sections_order
                ),
            }

    # Write manifest atomically
    save_json(args.manifest_file, manifest)

    # Build XML source files if --xml-dir is set
    xml_dir = getattr(args, "xml_dir", None)
    if xml_dir:
        for doc_name, doc_data in state.get("documents", {}).items():
            if args.audience:
                xml_out_dir = os.path.join(xml_dir, args.audience)
            else:
                xml_out_dir = xml_dir
            os.makedirs(xml_out_dir, exist_ok=True)
            xml_path = os.path.join(xml_out_dir, f"{doc_name}.xml")

            if merge and os.path.isfile(xml_path):
                # Merge mode: update existing XML tree in place
                from lxml import etree
                tree = etree.parse(xml_path)
                existing_paths = set(get_section_paths(tree))

                # Walk all state sections recursively
                all_sections = _collect_all_sections_depth_first(
                    doc_data.get("sections", {}),
                    doc_data.get("sections_order", []),
                )
                for path, sec_data in all_sections:
                    if path in existing_paths:
                        update_section_body(tree, path, sec_data["content"])
                    else:
                        # Extract parent_path and leaf slug
                        if "/" in path:
                            parent_path = path.rsplit("/", 1)[0]
                            leaf_slug = path.rsplit("/", 1)[1]
                        else:
                            parent_path = None
                            leaf_slug = path
                        add_section(
                            tree, leaf_slug, sec_data["content"],
                            parent_path=parent_path,
                        )
                    if sec_data.get("typed_refs"):
                        update_section_refs(tree, path, sec_data["typed_refs"])
            else:
                # Initial mode: build new XML from scratch (nested)
                header_text = doc_data.get("header", "")
                diataxis = _extract_diataxis(header_text)
                sections_for_xml = _state_sections_to_xml(doc_data)
                tree = build_xml_doc(
                    audience=args.audience,
                    diataxis=diataxis,
                    header=header_text,
                    sections=sections_for_xml,
                )
                # Populate XML <refs> from typed_refs at correct paths
                all_sections = _collect_all_sections_depth_first(
                    doc_data.get("sections", {}),
                    doc_data.get("sections_order", []),
                )
                for path, sec_data in all_sections:
                    if sec_data.get("typed_refs"):
                        update_section_refs(
                            tree, path, sec_data["typed_refs"]
                        )

            serialize_xml_doc(tree, xml_path)

    # Delete state file
    os.remove(args.state_file)

    # Print summary to stderr
    total_sections = sum(
        len(_collect_all_paths(
            doc.get("sections", {}),
            doc.get("sections_order", []),
        ))
        for doc in state.get("documents", {}).values()
    )
    audience_label = args.audience or "standalone"
    print(
        f"Finalized {len(docs_written)} documents ({total_sections} sections) "
        f"for {audience_label}",
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
    parser.add_argument(
        "--parent",
        help="Parent section path for nesting (e.g., 'monitoring-alerting/health-artifact')",
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
    parser.add_argument(
        "--xml-dir",
        help="When set, also build XML source files in this directory",
    )

    args = parser.parse_args()

    if args.finalize:
        if not args.docs_dir:
            parser.error("--docs-dir is required in finalize mode")
        if args.audience is None:
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
