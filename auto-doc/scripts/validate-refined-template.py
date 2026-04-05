#!/usr/bin/env python3
"""Validate a refined template against structural rules.

Checks that a refined template produced by the template-refiner agent
satisfies the requirements from template-refiner.md:

- Every ## heading has a <purpose> tag in the block below it
- Every ### and #### heading has both <purpose> and <evidence> tags
- No <!-- OPTIONAL markers remain anywhere in the file
- No markdown heading lines (## , ### , #### ) inside <example> blocks
- At least one ## heading exists (sanity check)

Usage:
    python3 validate-refined-template.py --template path/to/DOCUMENT.template.md

Output: JSON to stdout with {valid, headings, errors, warnings}.
Exit code 0 if valid, 1 if errors found.

Zero external dependencies (stdlib only).
"""

import argparse
import json
import re
import sys


def _find_ranges(template_text, pattern):
    """Find all (start, end) ranges for a regex pattern."""
    return [(m.start(), m.end()) for m in re.finditer(pattern, template_text, re.DOTALL)]


def _in_range(pos, ranges):
    """Check if a character position falls inside any range."""
    for start, end in ranges:
        if start <= pos < end:
            return True
    return False


def _line_number(text, pos):
    """Return 1-based line number for a character position."""
    return text[:pos].count("\n") + 1


def validate(template_text):
    """Validate a refined template and return a result dict.

    Returns:
        dict with keys: valid (bool), headings (int), errors (list), warnings (list).
    """
    errors = []
    warnings = []

    # Build exclusion ranges (same approach as next-heading.py)
    comment_ranges = _find_ranges(template_text, r"<!--.*?-->")
    example_ranges = _find_ranges(template_text, r"<example>.*?</example>")

    heading_re = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

    # Check for headings inside <example> blocks (error)
    for m in heading_re.finditer(template_text):
        if _in_range(m.start(), example_ranges) and not _in_range(m.start(), comment_ranges):
            line = _line_number(template_text, m.start())
            errors.append(f"Line {line}: heading inside <example> block: {m.group(0).strip()}")

    # Collect legitimate headings (outside comments and example blocks)
    headings = []
    for m in heading_re.finditer(template_text):
        if not _in_range(m.start(), comment_ranges) and not _in_range(m.start(), example_ranges):
            headings.append({
                "line": _line_number(template_text, m.start()),
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "start": m.start(),
                "end": m.end(),
            })

    # Check for generation-time placeholder comments (belong in generic templates only)
    for m in re.finditer(r"<!--\s*docs-meta:", template_text):
        line = _line_number(template_text, m.start())
        errors.append(f"Line {line}: docs-meta placeholder from generic template not removed")

    # Check for unresolved OPTIONAL markers
    for m in re.finditer(r"<!--\s*OPTIONAL", template_text):
        line = _line_number(template_text, m.start())
        # Get the full line text for the error message
        line_start = template_text.rfind("\n", 0, m.start()) + 1
        line_end = template_text.find("\n", m.start())
        if line_end == -1:
            line_end = len(template_text)
        line_text = template_text[line_start:line_end].strip()
        errors.append(f"Line {line}: OPTIONAL marker not resolved: {line_text}")

    # Sanity: at least one ## heading
    if not any(h["level"] == 2 for h in headings):
        errors.append("No ## headings found in template")

    # Check required tags for each heading
    for idx, heading in enumerate(headings):
        content_start = heading["end"]
        content_end = headings[idx + 1]["start"] if idx + 1 < len(headings) else len(template_text)
        content = template_text[content_start:content_end]

        has_purpose = bool(re.search(r"<purpose>.*?</purpose>", content, re.DOTALL))
        has_evidence = bool(re.search(r"<evidence>.*?</evidence>", content, re.DOTALL))

        level = heading["level"]
        label = "#" * level + " " + heading["title"]

        if not has_purpose:
            errors.append(f"Line {heading['line']}: {label} \u2014 missing <purpose> tag")

        if level in (3, 4) and not has_evidence:
            errors.append(f"Line {heading['line']}: {label} \u2014 missing <evidence> tag")

        if level == 2 and not has_evidence:
            warnings.append(
                f"Line {heading['line']}: {label} \u2014 no <evidence> tag (recommended for ## headings)"
            )

    return {
        "valid": len(errors) == 0,
        "headings": len(headings),
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate a refined template against structural rules"
    )
    parser.add_argument(
        "--template", required=True,
        help="Path to the refined template file to validate",
    )

    args = parser.parse_args()

    try:
        with open(args.template, "r", encoding="utf-8") as f:
            template_text = f.read()
    except FileNotFoundError:
        print(json.dumps({
            "valid": False,
            "headings": 0,
            "errors": [f"Template file not found: {args.template}"],
            "warnings": [],
        }))
        sys.exit(1)

    result = validate(template_text)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
