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
from lib.ref_utils import identifier_for_ref
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
    """Format a single ref dict as a readable string.

    Returns None for refs with empty required identifier fields
    (defense-in-depth for old XML that predates discharge logic).
    """
    if ref_type == "db":
        schema = ref.get("schema", "")
        table = ref.get("table", "")
        if not schema or not table:
            return None
        column = ref.get("column")
        base = f"[db] {schema}.{table}"
        if column:
            base += f".{column}"
        return base

    if ref_type == "code":
        kind = ref.get("kind", "")
        name = ref.get("name", "")
        if not kind or not name:
            return None
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
        name = ref.get("name", "")
        return f"[flow] {name}" if name else None

    if ref_type == "env":
        name = ref.get("name", "")
        return f"[env] {name}" if name else None

    if ref_type == "config":
        path = ref.get("path", "")
        return f"[config] {path}" if path else None

    if ref_type == "enum":
        cls = ref.get("class", "")
        field = ref.get("field", "")
        value = ref.get("value", "")
        if not cls or not field or not value:
            return None
        return f"[enum] {cls}.{field} = {value}"

    if ref_type == "dep":
        name = ref.get("name", "")
        return f"[dep] {name}" if name else None

    if ref_type == "literal":
        name = ref.get("name", "")
        return f"[literal] {name}" if name else None

    if ref_type == "ext":
        name = ref.get("name", "")
        return f"[ext] {name}" if name else None

    if ref_type == "malformed":
        original = ref.get("original_type", "?")
        # Find first non-empty candidate field
        candidate = ""
        for k, v in ref.items():
            if k in ("type", "original_type") or not isinstance(v, str):
                continue
            if v.strip():
                candidate = v.strip()
                break
        if candidate:
            return f"[malformed:{original}] {candidate}"
        return None

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

        malformed = [r for r in section["refs"] if r.get("type") == "malformed"]

        ref_entries = []
        for ref in section["refs"]:
            if ref.get("type") == "malformed":
                continue
            display = _format_single_ref(ref.get("type", ""), ref)
            ident = identifier_for_ref(ref)
            if display or ident:
                ref_entries.append({"display": display, "identifier": ident})

        section_data = {
            "path": path,
            "slug": slug,
            "document": doc_name,
            "audience": doc["audience"],
            "body": body,
            "refs_as_text": refs_text,
            "malformed_refs": malformed,
            "ref_entries": ref_entries,
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
