#!/usr/bin/env python3
"""Deterministic template pre-parser for the scan pipeline.

Reads a .template.md file and produces structured JSON describing its
sections, slugs, directives (SYNTHESIZED, BOUNDARY, OPTIONAL, PURPOSE).

Usage:
    python3 parse-template.py \
        --template path/to/DOCUMENT.template.md \
        --document DOCUMENT_NAME \
        --output path/to/output.json

This replaces LLM template parsing with deterministic extraction,
eliminating invented synthesized_from, malformed slugs, and empty
orphan sections.

Zero external dependencies -- stdlib only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.heading_map import slugify_heading

# Valid project_model fields for synthesized_from validation
VALID_PROJECT_MODEL_FIELDS = {
    "tech_stack",
    "entry_points",
    "components",
    "infrastructure",
    "database",
    "user_interfaces",
}

# Pattern to strip inline HTML comments before slugifying
INLINE_COMMENT_RE = re.compile(r"\s*<!--.*?-->\s*$")

# Directive patterns
SYNTHESIZED_RE = re.compile(r"<!--\s*SYNTHESIZED:\s*(.+?)\s*-->")
BOUNDARY_RE = re.compile(r"<!--\s*BOUNDARY:\s*(.+?)\s*-->")
OPTIONAL_INLINE_RE = re.compile(r"<!--\s*OPTIONAL")
PURPOSE_START_RE = re.compile(r"<!--\s*PURPOSE:\s*(.*)")
PURPOSE_END_RE = re.compile(r"(.*?)-->")


def _extract_heading(line):
    """Extract heading text and level from a markdown heading line.

    Returns (level, text) or (None, None) if not a heading.
    """
    if line.startswith("### "):
        return 3, line[4:]
    if line.startswith("## "):
        return 2, line[3:]
    return None, None


def _clean_heading_text(text):
    """Strip inline HTML comments from heading text before slugifying."""
    return INLINE_COMMENT_RE.sub("", text).strip()


def _is_optional(lines, start_idx):
    """Check if heading line or the next non-empty line has OPTIONAL marker."""
    if OPTIONAL_INLINE_RE.search(lines[start_idx]):
        return True
    for j in range(start_idx + 1, len(lines)):
        next_line = lines[j].strip()
        if not next_line:
            continue
        return bool(OPTIONAL_INLINE_RE.search(next_line))
    return False


def _extract_block_directives(lines, start_idx, end_idx):
    """Extract SYNTHESIZED, BOUNDARY, and PURPOSE from lines[start_idx:end_idx]."""
    synthesized_from = None
    boundary = None
    purpose = None

    in_purpose = False
    purpose_lines = []

    for i in range(start_idx, end_idx):
        line = lines[i]

        # SYNTHESIZED
        m = SYNTHESIZED_RE.search(line)
        if m:
            raw = m.group(1)
            synthesized_from = [f.strip() for f in raw.split(",") if f.strip()]
            continue

        # BOUNDARY
        m = BOUNDARY_RE.search(line)
        if m:
            boundary = m.group(1).strip()
            continue

        # PURPOSE (multiline)
        if in_purpose:
            m = PURPOSE_END_RE.search(line)
            if m:
                before_close = m.group(1).strip()
                if before_close:
                    purpose_lines.append(before_close)
                in_purpose = False
            else:
                stripped = line.strip()
                if stripped:
                    purpose_lines.append(stripped)
            continue

        m = PURPOSE_START_RE.search(line)
        if m:
            rest = m.group(1).strip()
            # Check if PURPOSE closes on the same line
            close_m = PURPOSE_END_RE.search(rest)
            if close_m and "-->" in line[line.index("PURPOSE"):]:
                # Single-line PURPOSE
                before_close = close_m.group(1).strip()
                if before_close:
                    purpose_lines.append(before_close)
            else:
                if rest:
                    purpose_lines.append(rest)
                in_purpose = True

    if purpose_lines:
        purpose = " ".join(purpose_lines)

    return synthesized_from, boundary, purpose


def _validate_synthesized_from(synthesized_from, heading, document):
    """Warn to stderr if synthesized_from paths reference invalid fields."""
    if not synthesized_from:
        return
    for path in synthesized_from:
        parts = path.split(".")
        if len(parts) != 2 or parts[0] != "project_model":
            print(
                f"Warning: {document}/{heading}: invalid synthesized_from "
                f"path '{path}' (expected project_model.<field>)",
                file=sys.stderr,
            )
            continue
        if parts[1] not in VALID_PROJECT_MODEL_FIELDS:
            print(
                f"Warning: {document}/{heading}: unknown project_model field "
                f"'{parts[1]}' in synthesized_from",
                file=sys.stderr,
            )


def parse_template(template_path, document_name):
    """Parse a template file and return structured section data.

    Returns a dict with:
        document: str
        sections: list of section dicts
        valid_slugs: list of slug strings
    """
    with open(template_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections = []

    # Find all heading positions (## and ###), skipping # title
    heading_positions = []
    for i, line in enumerate(lines):
        level, text = _extract_heading(line)
        if level is not None:
            heading_positions.append((i, level, text))

    for idx, (line_idx, level, raw_text) in enumerate(heading_positions):
        # Determine block end (next heading or EOF)
        if idx + 1 < len(heading_positions):
            block_end = heading_positions[idx + 1][0]
        else:
            block_end = len(lines)

        clean_text = _clean_heading_text(raw_text)
        slug = slugify_heading(clean_text)

        if not slug:
            continue

        optional = _is_optional(lines, line_idx)

        synthesized_from, boundary, purpose = _extract_block_directives(
            lines, line_idx + 1, block_end
        )

        _validate_synthesized_from(synthesized_from, clean_text, document_name)

        section = {
            "heading": clean_text,
            "slug": slug,
            "level": level,
            "synthesized_from": synthesized_from,
            "boundary": boundary,
            "optional": optional,
            "purpose": purpose,
        }
        sections.append(section)

    valid_slugs = [s["slug"] for s in sections]

    return {
        "document": document_name,
        "sections": sections,
        "valid_slugs": valid_slugs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse documentation template into structured JSON"
    )
    parser.add_argument(
        "--template", required=True,
        help="Path to .template.md file",
    )
    parser.add_argument(
        "--document", required=True,
        help="Document name (e.g., USER_GUIDE)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path for output JSON",
    )

    args = parser.parse_args()

    template_path = os.path.abspath(args.template)
    if not os.path.isfile(template_path):
        print(f"Error: template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    result = parse_template(template_path, args.document)

    from lib.json_io import save_json
    save_json(os.path.abspath(args.output), result)

    section_count = len(result["sections"])
    synth_count = sum(
        1 for s in result["sections"] if s.get("synthesized_from")
    )
    print(
        f"Parsed {args.document}: {section_count} sections, "
        f"{synth_count} synthesized",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
