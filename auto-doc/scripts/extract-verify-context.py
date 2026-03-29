#!/usr/bin/env python3
"""Extract minimal verify context from docs-scan.json.

The full scan data can exceed subagent Read limits. This script
extracts only the 3 fields the verifier needs (root_path,
documented_sections, gap_analysis) into a small file.

The source_material_index is reduced to just its section keys
(a flat list), since Check 4 only needs to know which sections
exist — not the per-section source file details.

When --templates-dir is provided, also includes optional_sections
(sections marked <!-- OPTIONAL --> in templates) so the verifier
can skip them during completeness checks.

Usage:
    python3 extract-verify-context.py \
        --scan-file .mg/docs/docs-scan.json \
        --output .mg/docs/tmp/verify-scan-context.json \
        --templates-dir path/to/templates

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def _slugify(heading):
    """Convert a heading to a slug (lowercase, spaces to hyphens)."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _get_inscope_docs(config_path, global_config_path, audience_str):
    """Return set of in-scope document names, or None if no filter.

    When audience_str is provided, returns the union of shared_documents
    and the documents listed for each requested audience in config.
    """
    if not audience_str:
        return None

    global_cfg = load_json(global_config_path) or {}
    project_cfg = load_json(config_path) or {}
    config = {**global_cfg, **project_cfg}

    audience_set = set(re.split(r"[,\s]+", audience_str.strip())) - {""}
    docs = set()

    for doc in config.get("shared_documents", []):
        docs.add(doc)

    for aud_key, aud_conf in config.get("audiences", {}).items():
        if aud_key in audience_set:
            for doc in aud_conf.get("documents", []):
                docs.add(doc)

    return docs


def _find_optional_sections(templates_dir):
    """Find all optional sections across all templates.

    Returns a sorted list of 'DOCUMENT/section-slug' strings.
    """
    optional = []

    for dirpath, _dirnames, filenames in os.walk(templates_dir):
        for fname in filenames:
            if not fname.endswith(".template.md"):
                continue

            filepath = os.path.join(dirpath, fname)
            doc_name = fname.replace(".template.md", "")

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue

            for i, line in enumerate(lines):
                if not line.startswith("## "):
                    continue

                heading = line[3:].strip()
                slug = _slugify(heading)

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
        description="Extract verify context from scan data"
    )
    parser.add_argument(
        "--scan-file", required=True,
        help="Path to docs-scan.json",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write extracted context",
    )
    parser.add_argument(
        "--templates-dir", default=None,
        help="Path to templates directory (enables optional_sections in output)",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Comma/space-separated audience filter (e.g., 'devops,end-users')",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to project .docs.config.json (required with --audience)",
    )
    parser.add_argument(
        "--global-config", default=None,
        help="Path to global fallback .docs.config.json (required with --audience)",
    )

    args = parser.parse_args()
    scan_path = os.path.abspath(args.scan_file)
    output_path = os.path.abspath(args.output)

    scan_data = load_json(scan_path)
    if scan_data is None:
        print(f"Error: scan file not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    smi = scan_data.get("source_material_index", {})
    context = {
        "root_path": scan_data.get("root_path", ""),
        "documented_sections": sorted(smi.keys()) if isinstance(smi, dict) else [],
        "gap_analysis": scan_data.get("gap_analysis", {}),
        "project_model": scan_data.get("project_model", {}),
    }

    # Audience filtering — restrict sections and gaps to in-scope docs
    inscope_docs = _get_inscope_docs(
        os.path.abspath(args.config) if args.config else "",
        os.path.abspath(args.global_config) if args.global_config else "",
        args.audience,
    )
    if inscope_docs is not None:
        context["documented_sections"] = [
            key for key in context["documented_sections"]
            if key.split("/")[0] in inscope_docs
        ]
        gap = context.get("gap_analysis", {})
        mfa = gap.get("missing_for_audience")
        if isinstance(mfa, dict):
            audience_set = set(re.split(r"[,\s]+", args.audience.strip())) - {""}
            gap["missing_for_audience"] = {
                k: v for k, v in mfa.items() if k in audience_set
            }

    if args.templates_dir:
        templates_dir = os.path.abspath(args.templates_dir)
        if os.path.isdir(templates_dir):
            context["optional_sections"] = _find_optional_sections(templates_dir)

    save_json(output_path, context)
    print(f"Extracted verify context to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
