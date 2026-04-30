#!/usr/bin/env python3
"""List optional sections from documentation templates.

Walks a templates directory for *.template.md files. For each ## heading
whose next non-empty line contains '<!-- OPTIONAL', emits a section key
as DOCUMENT/section-slug.

Usage:
    python3 list-optional-sections.py --templates-dir path/to/templates

Outputs a JSON array to stdout.

Zero external dependencies -- stdlib only.
"""

import argparse
import json
import os
import re
import sys


def slugify(heading):
    """Convert a heading to a slug (lowercase, spaces to hyphens)."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def extract_document_name(filename):
    """Extract document name from template filename.

    e.g., USER_GUIDE.template.md -> USER_GUIDE
    """
    base = os.path.basename(filename)
    return base.replace(".template.md", "")


def _is_optional(lines, start):
    """Check if the line after heading or inline contains OPTIONAL marker."""
    # Check inline first (e.g., ### Heading <!-- OPTIONAL -->)
    if "<!-- OPTIONAL" in lines[start]:
        return True
    # Check next non-empty line
    for j in range(start + 1, len(lines)):
        next_line = lines[j].strip()
        if not next_line:
            continue
        return "<!-- OPTIONAL" in next_line
    return False


def find_optional_sections(templates_dir):
    """Find all optional sections across all templates.

    Returns a sorted list of keys:
    - '## ' headings: 'DOCUMENT/section-slug'
    - '### ' headings: 'DOCUMENT/section-slug/subsection-slug'
    """
    optional = []

    for dirpath, _dirnames, filenames in os.walk(templates_dir):
        for fname in filenames:
            if not fname.endswith(".template.md"):
                continue

            filepath = os.path.join(dirpath, fname)
            doc_name = extract_document_name(fname)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue

            current_h2_slug = None

            for i, line in enumerate(lines):
                if line.startswith("## "):
                    heading = line[3:].strip()
                    current_h2_slug = slugify(heading)
                    if _is_optional(lines, i):
                        optional.append(f"{doc_name}/{current_h2_slug}")
                elif line.startswith("### "):
                    # Extract heading text, stripping inline OPTIONAL comment
                    heading_text = re.sub(
                        r"\s*<!--.*?-->\s*$", "", line[4:]
                    ).strip()
                    h3_slug = slugify(heading_text)
                    if current_h2_slug and _is_optional(lines, i):
                        optional.append(
                            f"{doc_name}/{current_h2_slug}/{h3_slug}"
                        )

    return sorted(optional)


def main():
    parser = argparse.ArgumentParser(
        description="List optional sections from documentation templates"
    )
    parser.add_argument(
        "--templates-dir", required=True, action="append",
        help="Path to templates directory (searched recursively, repeatable)",
    )

    args = parser.parse_args()

    sections = []
    for tdir in args.templates_dir:
        templates_dir = os.path.abspath(tdir)
        if not os.path.isdir(templates_dir):
            print(f"Error: templates directory not found: {templates_dir}", file=sys.stderr)
            sys.exit(1)
        sections.extend(find_optional_sections(templates_dir))
    json.dump(sections, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
