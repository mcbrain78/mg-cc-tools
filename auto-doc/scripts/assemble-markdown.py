#!/usr/bin/env python3
"""Assemble a markdown file from an XML source document.

Reads the XML source, concatenates the header CDATA and all section body
CDATAs into a clean .md file. The <!-- section: slug --> markers embedded
in the CDATA pass through to the output.

Usage:
    python3 assemble-markdown.py --xml-file PATH --output PATH [--ledger PATH]

`--ledger` records the written path so the generate command can report what this
run produced from the writers themselves, rather than globbing the docs directory
afterwards and mistaking the previous run's output for its own.

Zero external dependencies beyond lxml (used by lib/xml_doc).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import save_text
from lib.written_ledger import record as record_written
from lib.xml_doc import parse_xml_doc, walk_sections


def assemble(xml_path):
    """Assemble markdown content from an XML document.

    Args:
        xml_path: Path to the XML source file.

    Returns:
        Assembled markdown string.
    """
    doc = parse_xml_doc(xml_path)

    parts = []
    header = doc["meta"]["header"]
    if header:
        parts.append(header.rstrip("\n"))

    for _path, section in walk_sections(doc["sections"]):
        body = section["body"]
        if body:
            parts.append(body.strip("\n"))

    return "\n\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Assemble markdown from XML source document"
    )
    parser.add_argument(
        "--xml-file", required=True,
        help="Path to the XML source file",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the assembled markdown",
    )
    parser.add_argument(
        "--ledger",
        help="Record the written path in this run's written-docs ledger",
    )
    parser.add_argument(
        "--audience",
        help="Audience to record in the ledger (optional, for reporting only)",
    )
    parser.add_argument(
        "--document",
        help="Document name to record in the ledger (optional, for reporting only)",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.xml_file):
        print(f"Error: XML file not found: {args.xml_file}", file=sys.stderr)
        sys.exit(1)

    md_content = assemble(args.xml_file)
    save_text(args.output, md_content)

    doc = parse_xml_doc(args.xml_file)
    n_sections = sum(1 for _ in walk_sections(doc["sections"]))

    # Recorded only after save_text has returned, so the ledger cannot claim a
    # file that was not actually written.
    if args.ledger:
        document = args.document or os.path.splitext(
            os.path.basename(args.output)
        )[0]
        record_written(
            args.ledger, args.output, "assemble",
            audience=args.audience, document=document, sections=n_sections,
        )

    print(
        f"Assembled {n_sections} sections → {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
