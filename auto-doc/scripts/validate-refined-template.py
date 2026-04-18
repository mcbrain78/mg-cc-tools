#!/usr/bin/env python3
"""Validate a refined template against structural rules.

Checks that a refined template produced by the template-refiner agent
satisfies the requirements from template-refiner.md:

- Every ## heading has a <purpose> tag in the block below it
- Every ### and #### heading has both <purpose> and <evidence> tags
- No <!-- OPTIONAL markers remain anywhere in the file
- No markdown heading lines (## , ### , #### ) inside <example> blocks
- At least one ## heading exists (sanity check)
- PRODUCT_NAME metadata comment is present in the preamble

When --parsed-template is provided, additional cross-validation runs:

- Every non-optional parsed section has a heading in the refined output
- Synthesized sections (section.synthesized_from non-null) have at least
  one ### subheading and reference the product_name in their <purpose>
- Bounded sections (section.boundary non-null) contain the boundary text
  verbatim in their <purpose>

Usage:
    python3 validate-refined-template.py --template path/to/DOCUMENT.template.md
    python3 validate-refined-template.py --template ... --parsed-template ...

Output: JSON to stdout with {valid, headings, errors, warnings}.
Exit code 0 if valid, 1 if errors found.

Zero external dependencies (stdlib only).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.heading_map import slugify_heading


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


def _section_content(template_text, headings, idx):
    """Return the content block for the idx-th heading (up to next heading)."""
    start = headings[idx]["end"]
    end = headings[idx + 1]["start"] if idx + 1 < len(headings) else len(template_text)
    return template_text[start:end]


def _extract_tag(content, tag):
    """Extract the body of the first <tag>...</tag> match in content."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", content, re.DOTALL)
    return m.group(1).strip() if m else None


def validate_structural(template_text):
    """Run the structural invariants (no parsed template needed)."""
    errors = []
    warnings = []

    comment_ranges = _find_ranges(template_text, r"<!--.*?-->")
    example_ranges = _find_ranges(template_text, r"<example>.*?</example>")

    heading_re = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

    for m in heading_re.finditer(template_text):
        if _in_range(m.start(), example_ranges) and not _in_range(m.start(), comment_ranges):
            line = _line_number(template_text, m.start())
            errors.append(f"Line {line}: heading inside <example> block: {m.group(0).strip()}")

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

    for m in re.finditer(r"<!--\s*docs-meta:", template_text):
        line = _line_number(template_text, m.start())
        errors.append(f"Line {line}: docs-meta placeholder from generic template not removed")

    for m in re.finditer(r"<!--\s*OPTIONAL", template_text):
        line = _line_number(template_text, m.start())
        line_start = template_text.rfind("\n", 0, m.start()) + 1
        line_end = template_text.find("\n", m.start())
        if line_end == -1:
            line_end = len(template_text)
        line_text = template_text[line_start:line_end].strip()
        errors.append(f"Line {line}: OPTIONAL marker not resolved: {line_text}")

    if not any(h["level"] == 2 for h in headings):
        errors.append("No ## headings found in template")

    if not re.search(r"<!--\s*PRODUCT_NAME:", template_text):
        warnings.append(
            "No <!-- PRODUCT_NAME: ... --> metadata in preamble. "
            "Refiner should inject product_name for writer consistency."
        )

    for idx, heading in enumerate(headings):
        content = _section_content(template_text, headings, idx)
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

    return headings, errors, warnings


def _product_name_from_preamble(template_text):
    m = re.search(r"<!--\s*PRODUCT_NAME:\s*(.+?)\s*-->", template_text)
    return m.group(1).strip() if m else None


def validate_against_parsed(template_text, headings, parsed_sections):
    """Cross-validate refined output against parsed-template JSON.

    Checks:
    - Every non-optional parsed ## section has a heading with matching slug
    - Synthesized ## sections have at least one ### subheading AND their
      <purpose> references the product_name
    - Bounded ## sections' <purpose> contains the boundary text verbatim
    """
    errors = []
    warnings = []

    # Build a map of refined `##` heading slugs → index in `headings` list
    level2 = [(i, h) for i, h in enumerate(headings) if h["level"] == 2]
    slug_to_heading = {}
    for i, h in level2:
        slug_to_heading[slugify_heading(h["title"])] = (i, h)

    product_name = _product_name_from_preamble(template_text)

    for section in parsed_sections:
        if section.get("level", 2) != 2:
            continue  # cross-check runs at ## level

        slug = section["slug"]
        optional = section.get("optional", False)
        synth = section.get("synthesized_from")
        boundary = section.get("boundary")

        if slug not in slug_to_heading:
            if not optional:
                errors.append(
                    f"Parsed section '{slug}' missing from refined output "
                    f"(non-optional)"
                )
            continue

        idx, _ = slug_to_heading[slug]
        content = _section_content(template_text, headings, idx)
        purpose_body = _extract_tag(content, "purpose") or ""

        # Synthesized invariants
        if synth:
            # Count ### subheadings until next ## or EOF
            subs = 0
            for j in range(idx + 1, len(headings)):
                if headings[j]["level"] == 2:
                    break
                if headings[j]["level"] == 3:
                    subs += 1
            if subs == 0:
                errors.append(
                    f"Synthesized section '{slug}' has no ### subheadings "
                    f"(refiner should propose ≥1)"
                )

            if product_name and product_name not in purpose_body:
                errors.append(
                    f"Synthesized section '{slug}' <purpose> does not "
                    f"reference product_name '{product_name}' "
                    f"(required for vocabulary anchoring)"
                )

        # Bounded invariants
        if boundary:
            if boundary.strip() not in purpose_body:
                errors.append(
                    f"Bounded section '{slug}' <purpose> does not contain "
                    f"the boundary text verbatim"
                )

    return errors, warnings


def validate(template_text, parsed_sections=None):
    """Validate a refined template and return a result dict."""
    headings, errors, warnings = validate_structural(template_text)

    if parsed_sections is not None:
        ce, cw = validate_against_parsed(template_text, headings, parsed_sections)
        errors.extend(ce)
        warnings.extend(cw)

    return {
        "valid": len(errors) == 0,
        "headings": len(headings),
        "errors": errors,
        "warnings": warnings,
    }


def _load_parsed_sections(path):
    if not path:
        return None
    if not os.path.exists(path):
        return {"__error__": f"Parsed template file not found: {path}"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {"__error__": f"Parsed template is not valid JSON: {e}"}
    return data.get("sections", [])


def main():
    parser = argparse.ArgumentParser(
        description="Validate a refined template against structural rules"
    )
    parser.add_argument(
        "--template", required=True,
        help="Path to the refined template file to validate",
    )
    parser.add_argument(
        "--parsed-template", default=None,
        help="Optional path to the parsed-template JSON (produced by "
             "parse-template.py). If provided, cross-validates synth / "
             "boundary invariants and section coverage.",
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

    parsed = _load_parsed_sections(args.parsed_template)
    if isinstance(parsed, dict) and "__error__" in parsed:
        print(json.dumps({
            "valid": False,
            "headings": 0,
            "errors": [parsed["__error__"]],
            "warnings": [],
        }))
        sys.exit(1)

    result = validate(template_text, parsed_sections=parsed)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
