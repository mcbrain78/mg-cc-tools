#!/usr/bin/env python3
"""Report the documents this generate run wrote, and how big they are.

Driven by the ledger that write-section.py --finalize and assemble-markdown.py
append to as they write, not by a listing of the docs directory. Both places this
replaces used a glob, and a glob answers the wrong question -- it reports what is
on disk, which in update mode is dominated by previous runs:

  * The post-writer check globbed `docs_dir/**/*.md` two stages before the
    documents were written, so it named the previous run's files as this run's
    creations and could not see a writer that had died.
  * The summary table globbed the same directory at the end. By then the files do
    exist, but under an audience filter the table still listed every other
    audience's documents as part of this run's output.

Counting is done here rather than described in the prompt for the same reason the
paths are: section markers and word counts are mechanical, and a table assembled
by hand from a directory listing is exactly how a document nobody generated ends
up in the report.

`sections` comes from the `<!-- section: slug -->` markers in the written file, so
it describes the file as it now stands -- after polish, after any merge -- rather
than what a writer recorded earlier.

The only stage combination this warns about is finalize-without-assemble; see
`is_incomplete`. A report that warns on healthy runs is the failure it replaced,
so the bar for a warning here is that something is actually wrong.

Exit code is 0 whether or not the run was complete: this reports, it does not
gate. check-writer-output.py is the gate.

Usage:
    written-docs.py --ledger <path> [--docs-dir <path>]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.written_ledger import read as read_ledger

SECTION_MARKER = re.compile(r"<!--\s*section:")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
BOTH_STAGES = {"finalize", "assemble"}


def classify(entry):
    stages = set(entry.get("stages", []))
    if BOTH_STAGES <= stages:
        return "complete"
    if stages == {"finalize"}:
        return "finalize-only"
    if stages == {"assemble"}:
        return "assemble-only"
    return "no-stage-recorded"


def is_incomplete(entry):
    """Whether this document's state is worth warning about.

    Only `finalize-only` is: the document was assembled from accumulated sections
    but never re-assembled from XML, so the file predates ref resolution.

    `assemble-only` is NOT a warning. XML is the source of truth for a document
    (see schema.yaml), so producing a file from existing XML without re-running
    finalize is a legitimate repair, and flagging it would put this report back in
    the business of crying wolf -- which is the defect it was written to remove.
    """
    return classify(entry) in ("finalize-only", "no-stage-recorded")


def measure(path):
    """(sections, words) for a written document, or (None, None) if unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None, None
    sections = len(SECTION_MARKER.findall(text))
    prose = HTML_COMMENT.sub(" ", FRONTMATTER.sub("", text))
    return sections, len(prose.split())


def label(path, docs_dir):
    if docs_dir:
        try:
            rel = os.path.relpath(path, docs_dir)
        except ValueError:
            return path
        if not rel.startswith(".."):
            return rel
    return path


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Report the documents this generate run wrote."
    )
    p.add_argument("--ledger", required=True)
    p.add_argument(
        "--docs-dir",
        help="Show paths relative to this directory instead of absolute",
    )
    args = p.parse_args(argv)

    entries = sorted(
        read_ledger(args.ledger).get("documents", []),
        key=lambda e: e.get("path", ""),
    )

    if not entries:
        print(
            "WROTE: 0 documents -- no writer recorded one this run. If writer "
            "agents were dispatched, none of them reached finalize. Do not fall "
            "back to listing the docs directory; those files are from earlier runs."
        )
        return 0

    rows, missing, partial = [], [], []
    total_sections = total_words = 0
    for entry in entries:
        path = entry.get("path", "")
        name = label(path, args.docs_dir)
        sections, words = measure(path)
        if sections is None or words is None:
            missing.append(name)
            rows.append((name, "?", "?"))
            continue
        total_sections += sections
        total_words += words
        rows.append((name, str(sections), f"{words:,}"))
        if is_incomplete(entry):
            partial.append(f"{name} ({classify(entry)})")

    width = max([len("File")] + [len(r[0]) for r in rows])
    print("Generation Summary:")
    print()
    print(f"| {'File':<{width}} | Sections | Words  |")
    print(f"|{'-' * (width + 2)}|----------|--------|")
    for name, sections, words in rows:
        print(f"| {name:<{width}} | {sections:<8} | {words:<6} |")
    print()
    print(
        f"Total: {len(rows)} files, {total_sections} sections, "
        f"~{total_words:,} words"
    )

    if missing:
        print()
        print(
            f"UNREADABLE: {len(missing)} recorded document(s) could not be read "
            f"back: {', '.join(missing)}. A writer reported writing them, so "
            f"something removed or locked them afterwards."
        )
    if partial:
        print()
        print(
            f"INCOMPLETE: {len(partial)} document(s) did not pass through both "
            f"finalize and assemble: {', '.join(partial)}. The file exists but is "
            f"not this run's finished output -- report it as incomplete."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
