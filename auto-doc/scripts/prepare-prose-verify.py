#!/usr/bin/env python3
"""Prepare per-section prose+refs pairs for LLM prose-vs-refs verification.

Reads an XML source document and extracts per-section pairs of:
- body: the section markdown prose
- refs_as_text: human-readable bullet list of declared code references

The refs are formatted as readable text (not raw XML) so the LLM can
naturally compare prose claims against declared refs.

Usage:
    python3 prepare-prose-verify.py \
        --xml-file PATH \
        --output-dir PATH

Creates one JSON file per section in nested directories mirroring the
section tree: {output_dir}/{path}.json with keys "path", "slug",
"body", "refs_as_text". Also writes a manifest.json listing all
section paths.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import save_json
from lib.xml_doc import parse_xml_doc, walk_sections


def format_refs_as_text(refs):
    """Format a list of flat ref dicts as a human-readable bullet list.

    Args:
        refs: List of flat ref dicts from parse_xml_doc.

    Returns:
        String with one bullet per ref, or "(no refs declared)" if empty.
    """
    if not refs:
        return "(no refs declared)"

    lines = []
    for ref in refs:
        ref_type = ref.get("type", "")
        line = _format_single_ref(ref_type, ref)
        if line:
            lines.append(f"- {line}")

    return "\n".join(lines) if lines else "(no refs declared)"


def _format_single_ref(ref_type, ref):
    """Format a single ref dict as a readable string."""
    if ref_type == "db":
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        column = ref.get("column")
        base = f"[db] {schema}.{table}" if schema else f"[db] {table}"
        if column:
            base += f".{column}"
        return base

    if ref_type == "code":
        kind = ref.get("kind", "")
        name = ref.get("name", "")
        module = ref.get("module", "")
        attr = ref.get("attr")
        param = ref.get("param")
        parts = [f"[code:{kind}]", name]
        if module:
            parts.append(f"in {module}")
        if attr:
            parts.append(f"(attr: {attr})")
        if param:
            parts.append(f"(param: {param})")
        return " ".join(parts)

    if ref_type == "flow":
        return f"[flow] {ref.get('name', '')}"

    if ref_type == "env":
        return f"[env] {ref.get('name', '')}"

    if ref_type == "config":
        return f"[config] {ref.get('path', '')}"

    if ref_type == "enum":
        cls = ref.get("class", "")
        field = ref.get("field", "")
        value = ref.get("value", "")
        return f"[enum] {cls}.{field} = {value}"

    if ref_type == "dep":
        return f"[dep] {ref.get('name', '')}"

    if ref_type == "literal":
        return f"[literal] {ref.get('name', '')}"

    if ref_type == "ext":
        return f"[ext] {ref.get('name', '')}"

    return None


def prepare(xml_path, output_dir):
    """Extract per-section prose+refs pairs from XML.

    Args:
        xml_path: Path to the XML source file.
        output_dir: Directory to write per-section JSON files.

    Returns:
        List of section path strings that were written.
    """
    doc = parse_xml_doc(xml_path)
    doc_name = os.path.splitext(os.path.basename(xml_path))[0]
    os.makedirs(output_dir, exist_ok=True)

    paths = []
    for path, section in walk_sections(doc["sections"]):
        slug = section["slug"]
        body = section["body"]
        refs_text = format_refs_as_text(section["refs"])

        section_data = {
            "path": path,
            "slug": slug,
            "document": doc_name,
            "audience": doc["audience"],
            "body": body,
            "refs_as_text": refs_text,
        }

        # Nested directory structure: monitoring-alerting/etl-run-logging.json
        parent_dir = os.path.join(output_dir, os.path.dirname(path))
        os.makedirs(parent_dir, exist_ok=True)
        save_json(os.path.join(parent_dir, f"{slug}.json"), section_data)
        paths.append(path)

    # Write manifest
    manifest = {
        "xml_file": xml_path,
        "audience": doc["audience"],
        "document": doc_name,
        "sections": paths,
    }
    save_json(os.path.join(output_dir, "manifest.json"), manifest)

    return paths


def main():
    parser = argparse.ArgumentParser(
        description="Prepare per-section prose+refs pairs for verification"
    )
    parser.add_argument(
        "--xml-file", required=True,
        help="Path to the XML source file",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Directory to write per-section JSON files",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.xml_file):
        print(f"Error: XML file not found: {args.xml_file}", file=sys.stderr)
        sys.exit(1)

    paths = prepare(args.xml_file, args.output_dir)
    print(f"Prepared {len(paths)} sections for prose verification", file=sys.stderr)


if __name__ == "__main__":
    main()
