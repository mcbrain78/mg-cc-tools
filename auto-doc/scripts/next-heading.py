#!/usr/bin/env python3
"""Script-gated heading iterator for writer agent loop.

Parses a refined template on first invocation, builds a flat
emission queue of orient/write/done responses, and returns one
response per call. State is persisted to a JSON file between calls.

On each call:
1. Load state (or initialize by parsing template + scan file)
2. Emit the next response from the queue
3. Advance index and persist state

Usage:
    next-heading.py --state-file PATH --template PATH --scan-file PATH --document DOC

Returns JSON to stdout:
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


def build_emission_queue(sections, document, source_material_index):
    """Build the complete sequence of responses to emit.

    Args:
        sections: Parsed section list from parse_template().
        document: Document identifier (e.g., "OPERATIONS").
        source_material_index: Dict from scan file.

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

        queue.append({
            "type": "orient",
            "section": slug,
            "heading_outline": outline,
            "source_files": source_files,
        })

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


def main():
    parser = argparse.ArgumentParser(
        description="Script-gated heading iterator for writer agent loop",
    )
    parser.add_argument(
        "--state-file", required=True,
        help="Path to state file (created on first call)",
    )
    parser.add_argument(
        "--template", required=True,
        help="Path to refined template file",
    )
    parser.add_argument(
        "--scan-file", required=True,
        help="Path to docs-scan.json",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document identifier (e.g., OPERATIONS)",
    )

    args = parser.parse_args()

    state = load_json(args.state_file)
    if state is None:
        # First call: parse template and build queue.
        if not os.path.isfile(args.template):
            print(
                f"Error: template not found: {args.template}",
                file=sys.stderr,
            )
            sys.exit(1)

        if not os.path.isfile(args.scan_file):
            print(
                f"Error: scan file not found: {args.scan_file}",
                file=sys.stderr,
            )
            sys.exit(1)

        with open(args.template, "r", encoding="utf-8") as f:
            template_text = f.read()

        scan_data = load_json(args.scan_file, default={})
        source_material_index = scan_data.get("source_material_index", {})

        sections = parse_template(template_text)
        queue = build_emission_queue(sections, args.document, source_material_index)
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
        save_json(args.state_file, state)
        print(json.dumps(response))
        return

    state["index"] = index + 1
    save_json(args.state_file, state)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
