#!/usr/bin/env python3
"""Script-gated heading iterator for writer agent loop.

Parses a refined template on first invocation, builds a flat
emission queue of orient/write/done responses, and returns one
response per call. State is persisted to a JSON file between calls.

Two modes of operation:

Init mode (called by generate-setup.py, never by agent):
    next-heading.py --init --state-file PATH --template PATH --scan-file PATH --document DOC
                    [--db-table-map PATH] [--db-model PATH]
    Builds queue, saves state file, exits with no stdout.

Runtime mode (called by writer agents -- no file paths):
    next-heading.py --generate-dir DIR --audience AUD --document DOC
    Derives state file from convention: {generate_dir}/heading-state-{audience}-{DOCUMENT}.json

Legacy mode (backward compatible):
    next-heading.py --state-file PATH --template PATH --scan-file PATH --document DOC
    Initializes on first call if state file doesn't exist.

Returns JSON to stdout (runtime/legacy only):
    {"type": "orient", "section": "...", "heading_outline": [...], "source_files": [...]}
    {"type": "write", "heading_path": "...", "level": N, "title": "...", "heading_line": "## ...", "purpose": "...", "example": "..."}
    {"done": true, "headings_processed": N}
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.db_format import slice_and_format
from lib.heading_map import slugify_heading
from lib.json_io import load_json, save_json



def _extract_xml_tag(content_block, tag_name):
    """Extract content from an XML tag like <tag_name>content</tag_name>.

    Args:
        content_block: Raw text between headings.
        tag_name: XML tag name to match (e.g., "purpose", "example").

    Returns:
        Extracted content string, or empty string if not found.
    """
    pattern = rf'<{tag_name}>(.*?)</{tag_name}>'
    m = re.search(pattern, content_block, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def parse_template(template_text):
    """Parse a refined template into a list of ## sections with children.

    Strips HTML comments before heading detection to avoid treating
    headings inside EXAMPLE blocks as real template headings (Pitfall 3).

    Returns:
        List of section dicts:
        [
            {
                "slug": "section-slug",
                "title": "Section Title",
                "level": 2,
                "purpose": "...",
                "example": "...",
                "children": [
                    {"slug": "child-slug", "title": "Child Title", "level": 3,
                     "purpose": "...", "example": "...", "children": [...]},
                ]
            },
        ]
    """
    # Find headings in the original text, skipping those inside HTML comments.
    # We work on the original to preserve PURPOSE/EXAMPLE comment positions.

    # Build list of (level, title, raw_content_after) from original text.
    # Strategy: find each heading line in the original, grab content until next heading.
    heading_line_pattern = re.compile(r'^(#{2,4})\s+(.+)$', re.MULTILINE)

    # Get heading positions in original text, but only those NOT inside
    # HTML comments or XML example tags.
    comment_ranges = []
    for m in re.finditer(r'<!--.*?-->', template_text, re.DOTALL):
        comment_ranges.append((m.start(), m.end()))
    for m in re.finditer(r'<example>.*?</example>', template_text, re.DOTALL):
        comment_ranges.append((m.start(), m.end()))

    def _in_comment(pos):
        for start, end in comment_ranges:
            if start <= pos < end:
                return True
        return False

    original_headings = []
    for m in heading_line_pattern.finditer(template_text):
        if not _in_comment(m.start()):
            level = len(m.group(1))
            title = m.group(2).strip()
            title = re.sub(r'\s*<!--\s*optional\s*-->\s*$', '', title,
                           flags=re.IGNORECASE).strip()
            original_headings.append({
                "level": level,
                "title": title,
                "pos": m.end(),
            })

    # Extract content blocks (raw text between headings in original).
    parsed = []
    for i, h in enumerate(original_headings):
        if i + 1 < len(original_headings):
            content = template_text[h["pos"]:original_headings[i + 1]["pos"]]
            # Find the start of the next heading line to get just the content block.
            next_heading_match = heading_line_pattern.search(content)
            if next_heading_match and not _in_comment(h["pos"] + next_heading_match.start()):
                content = content[:next_heading_match.start()]
        else:
            content = template_text[h["pos"]:]

        purpose = _extract_xml_tag(content, "purpose")
        example = _extract_xml_tag(content, "example")
        # evidence intentionally NOT extracted — stripped before reaching writer

        parsed.append({
            "level": h["level"],
            "title": h["title"],
            "slug": slugify_heading(h["title"]),
            "purpose": purpose,
            "example": example,
        })

    # Step 3: Build tree structure from flat list.
    sections = []
    for item in parsed:
        if item["level"] == 2:
            sections.append({
                "slug": item["slug"],
                "title": item["title"],
                "level": 2,
                "purpose": item["purpose"],
                "example": item["example"],
                "children": [],
            })
        elif item["level"] == 3 and sections:
            sections[-1]["children"].append({
                "slug": item["slug"],
                "title": item["title"],
                "level": 3,
                "purpose": item["purpose"],
                "example": item["example"],
                "children": [],
            })
        elif item["level"] == 4 and sections and sections[-1]["children"]:
            sections[-1]["children"][-1]["children"].append({
                "slug": item["slug"],
                "title": item["title"],
                "level": 4,
                "purpose": item["purpose"],
                "example": item["example"],
                "children": [],
            })

    return sections


def _collect_heading_paths(section):
    """Collect all heading_paths depth-first for a ## section.

    Returns:
        List of heading_path strings (slug-separated).
    """
    paths = [section["slug"]]
    for child in section.get("children", []):
        child_path = f"{section['slug']}/{child['slug']}"
        paths.append(child_path)
        for grandchild in child.get("children", []):
            paths.append(f"{child_path}/{grandchild['slug']}")
    return paths


def _walk_headings_depth_first(section):
    """Walk all headings in a section depth-first.

    Yields dicts with: path, level, purpose, example.
    """
    yield {
        "path": section["slug"],
        "level": section["level"],
        "title": section["title"],
        "purpose": section["purpose"],
        "example": section["example"],
    }
    for child in section.get("children", []):
        child_path = f"{section['slug']}/{child['slug']}"
        yield {
            "path": child_path,
            "level": child["level"],
            "title": child["title"],
            "purpose": child["purpose"],
            "example": child["example"],
        }
        for grandchild in child.get("children", []):
            yield {
                "path": f"{child_path}/{grandchild['slug']}",
                "level": grandchild["level"],
                "title": grandchild["title"],
                "purpose": grandchild["purpose"],
                "example": grandchild["example"],
            }


def build_emission_queue(sections, document, source_material_index, db_table_map=None):
    """Build the complete sequence of responses to emit.

    Args:
        sections: Parsed section list from parse_template().
        document: Document identifier (e.g., "OPERATIONS").
        source_material_index: Dict from scan file.
        db_table_map: Optional dict of section_key -> [table_names].

    Returns:
        List of response dicts (orient, write, done).
    """
    queue = []
    total_headings = 0

    for section in sections:
        slug = section["slug"]
        key = f"{document}/{slug}"
        source_files = source_material_index.get(key, {}).get("source_files", [])

        outline = _collect_heading_paths(section)

        orient = {
            "type": "orient",
            "section": slug,
            "heading_outline": outline,
            "source_files": source_files,
        }

        # Inject relevant tables from db-table-map
        if db_table_map:
            entry = db_table_map.get(key)
            if entry is not None:
                if isinstance(entry, dict) and "tables" in entry:
                    orient["relevant_tables"] = entry["tables"]
                    if entry.get("usage"):
                        orient["db_table_usage"] = entry["usage"]
                elif isinstance(entry, list):
                    # Legacy format: plain list of table names
                    orient["relevant_tables"] = entry

        queue.append(orient)

        for heading in _walk_headings_depth_first(section):
            total_headings += 1
            response = {
                "type": "write",
                "heading_path": heading["path"],
                "level": heading["level"],
                "title": heading["title"],
                "heading_line": "#" * heading["level"] + " " + heading["title"],
                "purpose": heading["purpose"],
                "example": heading["example"],
            }
            if "/" in heading["path"]:
                response["parent_path"] = heading["path"].rsplit("/", 1)[0]
            queue.append(response)

    queue.append({"done": True, "headings_processed": total_headings})
    return queue


def _inject_db_column_detail(queue, db_model_data, db_table_map):
    """Inject db_column_detail and database_name into orient responses.

    Modifies queue in-place. For each orient response with relevant_tables,
    calls slice_and_format() to produce the formatted column detail string
    and stores it as db_column_detail on the orient dict. Also injects
    database_name from the database model so writers have it when
    constructing db refs.
    """
    if not db_model_data or not db_table_map:
        return
    db_name = db_model_data.get("database_name")
    for entry in queue:
        if entry.get("type") != "orient":
            continue
        tables = entry.get("relevant_tables")
        if not tables:
            continue
        detail = slice_and_format(db_model_data, tables)
        if detail:
            entry["db_column_detail"] = detail
        if db_name:
            entry["database_name"] = db_name


def _build_parsed_section_map(parsed_template_data):
    """Build {slug: parsed_section_dict} from parse-template.py JSON output.

    Returns empty dict if parsed_template_data is falsy or missing sections.
    """
    if not parsed_template_data:
        return {}
    return {
        s["slug"]: s
        for s in parsed_template_data.get("sections", [])
        if s.get("slug")
    }


def _resolve_synth_context(project_model, synthesized_from):
    """Resolve dotted-path synth hints against project_model to concrete values.

    Each path in synthesized_from is of form "project_model.<field>". Only
    paths whose field exists in project_model resolve. Returns a dict mapping
    field name -> value. Empty dict if nothing resolves.
    """
    result = {}
    if not project_model or not synthesized_from:
        return result
    for path in synthesized_from:
        parts = path.split(".")
        if len(parts) != 2 or parts[0] != "project_model":
            continue
        field = parts[1]
        if field in project_model:
            result[field] = project_model[field]
    return result


def _inject_synth_and_boundary(queue, parsed_section_map, project_model):
    """Inject synth_context, synthesized_from, and boundary_text.

    For each orient response, looks up the section in parsed_section_map.
    If synthesized_from is present, resolves the field list against
    project_model into a compact synth_context slice. If boundary is
    present, passes the raw boundary text through as boundary_text.

    Modifies queue in-place.
    """
    if not parsed_section_map:
        return
    for entry in queue:
        if entry.get("type") != "orient":
            continue
        slug = entry.get("section")
        if not slug:
            continue
        section = parsed_section_map.get(slug)
        if not section:
            continue

        synth = section.get("synthesized_from")
        if synth:
            entry["synthesized_from"] = synth
            resolved = _resolve_synth_context(project_model, synth)
            if resolved:
                entry["synth_context"] = resolved

        boundary = section.get("boundary")
        if boundary:
            entry["boundary_text"] = boundary


def _inject_product_name(queue, product_name):
    """Inject product_name into every orient response.

    Writers use this as the vocabulary anchor for consistent product
    framing across sections. Skips injection when product_name is empty.
    """
    if not product_name:
        return
    for entry in queue:
        if entry.get("type") == "orient":
            entry["product_name"] = product_name


def _derive_state_path(generate_dir, audience, document):
    """Derive convention-based state file path.

    Returns: {generate_dir}/heading-state-{audience}-{document}.json
    """
    return os.path.join(generate_dir, f"heading-state-{audience}-{document}.json")


def main():
    parser = argparse.ArgumentParser(
        description="Script-gated heading iterator for writer agent loop",
    )
    # Init mode args (called by generate-setup.py)
    parser.add_argument(
        "--init", action="store_true",
        help="Init mode: build queue, save state, exit (no stdout output)",
    )
    parser.add_argument(
        "--state-file",
        help="Path to state file (required for init and legacy mode)",
    )
    parser.add_argument(
        "--template",
        help="Path to refined template file (required for init and legacy mode)",
    )
    parser.add_argument(
        "--scan-file",
        help="Path to docs-scan.json (required for init and legacy mode)",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document identifier (e.g., OPERATIONS)",
    )
    parser.add_argument(
        "--db-table-map",
        help="Path to db-table-map.json (optional, adds relevant_tables to orient responses)",
    )
    parser.add_argument(
        "--db-model",
        help="Path to database-model.json (optional, --init only, inlines column detail)",
    )
    parser.add_argument(
        "--parsed-template",
        help="Path to parse-template.py JSON for this document (optional). When "
             "provided, orient responses gain synthesized_from + synth_context "
             "for synth sections and boundary_text for bounded sections.",
    )
    parser.add_argument(
        "--project-model",
        help="Path to slimmed project-model.json (optional). When provided, "
             "synth fields resolve against it and product_name is injected "
             "into every orient response.",
    )

    # Runtime mode args (called by writer agents)
    parser.add_argument(
        "--generate-dir",
        help="Path to generate directory (runtime mode: derives state file path)",
    )
    parser.add_argument(
        "--audience",
        help="Audience name (runtime mode: used with --generate-dir to derive state path)",
    )

    args = parser.parse_args()

    # --- Init mode ---
    if args.init:
        if not args.state_file:
            print("Error: --state-file required with --init", file=sys.stderr)
            sys.exit(2)
        if not args.template:
            print("Error: --template required with --init", file=sys.stderr)
            sys.exit(2)
        if not args.scan_file:
            print("Error: --scan-file required with --init", file=sys.stderr)
            sys.exit(2)

        if not os.path.isfile(args.template):
            print(f"Error: template not found: {args.template}", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(args.scan_file):
            print(f"Error: scan file not found: {args.scan_file}", file=sys.stderr)
            sys.exit(1)

        with open(args.template, "r", encoding="utf-8") as f:
            template_text = f.read()

        scan_data = load_json(args.scan_file, default={})
        source_material_index = scan_data.get("source_material_index", {})

        db_table_map = None
        if args.db_table_map and os.path.isfile(args.db_table_map):
            db_table_map = load_json(args.db_table_map, default={})

        sections = parse_template(template_text)
        queue = build_emission_queue(
            sections, args.document, source_material_index, db_table_map,
        )

        # Inject inline db_column_detail if --db-model provided
        if args.db_model and os.path.isfile(args.db_model):
            db_model_data = load_json(args.db_model, default={})
            _inject_db_column_detail(queue, db_model_data, db_table_map)

        # Load parsed-template metadata (synth/boundary signals per section)
        parsed_section_map = {}
        if args.parsed_template and os.path.isfile(args.parsed_template):
            parsed_data = load_json(args.parsed_template, default={})
            parsed_section_map = _build_parsed_section_map(parsed_data)

        # Load project_model (for synth resolution + product_name injection)
        project_model = {}
        if args.project_model and os.path.isfile(args.project_model):
            project_model = load_json(args.project_model, default={})

        # Inject synth_context + boundary_text from parsed template + project_model
        if parsed_section_map:
            _inject_synth_and_boundary(queue, parsed_section_map, project_model)

        # Inject product_name into every orient response
        _inject_product_name(queue, project_model.get("product_name", ""))

        state = {"queue": queue, "index": 0}
        save_json(args.state_file, state)
        return  # No stdout output in init mode

    # --- Determine state file path ---
    if args.generate_dir and args.audience:
        # Runtime mode: derive from convention
        state_file = _derive_state_path(args.generate_dir, args.audience, args.document)
    elif args.state_file:
        # Legacy mode: explicit state file (also used when template/scan-file provided)
        state_file = args.state_file
    else:
        print(
            "Error: provide either --generate-dir + --audience or --state-file",
            file=sys.stderr,
        )
        sys.exit(2)

    state = load_json(state_file)
    if state is None:
        # First call with no pre-initialized state: parse template and build queue.
        # This is the legacy path — kept for backward compat and non-devops writers.
        if not args.template:
            print("Error: --template required when state not pre-initialized", file=sys.stderr)
            sys.exit(2)
        if not args.scan_file:
            print("Error: --scan-file required when state not pre-initialized", file=sys.stderr)
            sys.exit(2)

        if not os.path.isfile(args.template):
            print(f"Error: template not found: {args.template}", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(args.scan_file):
            print(f"Error: scan file not found: {args.scan_file}", file=sys.stderr)
            sys.exit(1)

        with open(args.template, "r", encoding="utf-8") as f:
            template_text = f.read()

        scan_data = load_json(args.scan_file, default={})
        source_material_index = scan_data.get("source_material_index", {})

        db_table_map = None
        if args.db_table_map and os.path.isfile(args.db_table_map):
            db_table_map = load_json(args.db_table_map, default={})

        sections = parse_template(template_text)
        queue = build_emission_queue(
            sections, args.document, source_material_index, db_table_map,
        )

        # Legacy-mode synth/boundary/product_name injection
        parsed_section_map = {}
        if args.parsed_template and os.path.isfile(args.parsed_template):
            parsed_data = load_json(args.parsed_template, default={})
            parsed_section_map = _build_parsed_section_map(parsed_data)
        project_model = {}
        if args.project_model and os.path.isfile(args.project_model):
            project_model = load_json(args.project_model, default={})
        if parsed_section_map:
            _inject_synth_and_boundary(queue, parsed_section_map, project_model)
        _inject_product_name(queue, project_model.get("product_name", ""))

        state = {"queue": queue, "index": 0}

    queue = state["queue"]
    index = state["index"]

    if index >= len(queue):
        # Already past end -- re-emit done.
        done_response = queue[-1] if queue and queue[-1].get("done") else {
            "done": True, "headings_processed": 0,
        }
        print(json.dumps(done_response))
        return

    response = queue[index]

    # If this is the done response, don't advance past it so repeated
    # calls keep returning done (idempotent).
    if response.get("done"):
        save_json(state_file, state)
        print(json.dumps(response))
        return

    state["index"] = index + 1
    save_json(state_file, state)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
