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


def find_optional_sections(templates_dir):
    """Find all optional sections across all templates.

    Returns a sorted list of 'DOCUMENT/section-slug' strings.
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

            for i, line in enumerate(lines):
                # Look for ## headings
                if not line.startswith("## "):
                    continue

                heading = line[3:].strip()
                slug = slugify(heading)

                # Check if next non-empty line contains <!-- OPTIONAL
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if "<!-- OPTIONAL" in next_line:
                        optional.append(f"{doc_name}/{slug}")
                    break

    return sorted(optional)


def main():
    parser = argparse.ArgumentParser(
        description="List optional sections from documentation templates"
    )
    parser.add_argument(
        "--templates-dir", required=True,
        help="Path to templates directory (searched recursively)",
    )

    args = parser.parse_args()
    templates_dir = os.path.abspath(args.templates_dir)

    if not os.path.isdir(templates_dir):
        print(f"Error: templates directory not found: {templates_dir}", file=sys.stderr)
        sys.exit(1)

    sections = find_optional_sections(templates_dir)
    json.dump(sections, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
