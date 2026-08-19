#!/usr/bin/env python3
"""Check that every dispatched writer agent produced output.

This replaces a check in auto-doc-generate.md that globbed the docs directory for
`*.md` immediately after the writer agents returned, and warned per audience if
files were missing. It looked in the wrong place at the wrong time, and the two
failures it produced were opposite:

  * On a first run the docs directory holds nothing but GLOSSARY.md, because the
    audience documents are not written until finalize -- two stages later. So the
    check warned about every audience even when every agent had succeeded.
  * On a re-run the docs directory still holds the previous run's documents. So
    the check passed even when every agent had failed, and reported those stale
    files as this run's creations.

What a writer agent actually produces at that point is accumulated sections in a
write-state file, never markdown -- the agent instructions forbid Write() and hand
document assembly to finalize. So that is what this checks.

Two state-file layouts exist. Orient-write documents get one file each,
`write-state-<audience>-<DOCUMENT>.json`; documents falling back to the standard
prompt share one per audience, `write-state-<audience>.json`, keyed by document
inside. Both are accepted, because which one applies depends on whether
prepare-templates ever ran for that pair, and the caller should not have to know.

A state file with zero sections counts as a failure, not a pass: an agent that
initialised its state and then died leaves the file behind, and the whole point of
this check is to catch exactly that.

Exit 0 if every expected pair produced sections, 1 otherwise. Unlike the glob it
replaces, a non-zero exit here means real work is missing.

Usage:
    check-writer-output.py --generate-dir <dir> --expect "<audience>:<DOC>,..."
"""

import argparse
import json
import os
import sys


def _load(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _count_sections(doc_data):
    """Sections recorded for one document, however deeply nested."""
    if not isinstance(doc_data, dict):
        return 0
    sections = doc_data.get("sections")
    if not isinstance(sections, dict):
        return 0

    total = 0
    stack = [sections]
    while stack:
        current = stack.pop()
        for value in current.values():
            if not isinstance(value, dict):
                continue
            total += 1
            nested = value.get("sections")
            if isinstance(nested, dict):
                stack.append(nested)
    return total


def inspect(generate_dir, audience, document):
    """Return (status, detail) for one expected audience/document pair."""
    per_doc = os.path.join(
        generate_dir, f"write-state-{audience}-{document}.json"
    )
    per_audience = os.path.join(generate_dir, f"write-state-{audience}.json")

    for path, layout in ((per_doc, "orient-write"), (per_audience, "standard")):
        state = _load(path)
        if state is None:
            continue
        documents = state.get("documents")
        if not isinstance(documents, dict) or document not in documents:
            continue
        count = _count_sections(documents[document])
        if count == 0:
            return "EMPTY", (
                f"{layout} state {os.path.basename(path)} exists but recorded 0 "
                f"sections -- the agent started and did not write"
            )
        return "OK", f"{count} sections ({layout})"

    if os.path.exists(per_doc) or os.path.exists(per_audience):
        return "MISSING", (
            "a write-state file exists for this audience but has no entry for "
            "this document -- the agent did not reach it"
        )
    return "MISSING", "no write-state file was produced"


def parse_expect(raw):
    """Parse "aud:DOC,aud:DOC" into [(audience, document)]."""
    pairs = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(
                f"expected <audience>:<DOCUMENT>, got {token!r}"
            )
        audience, document = token.split(":", 1)
        audience, document = audience.strip(), document.strip()
        if not audience or not document:
            raise ValueError(
                f"expected <audience>:<DOCUMENT>, got {token!r}"
            )
        pairs.append((audience, document))
    return pairs


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Verify each dispatched writer agent produced sections."
    )
    p.add_argument("--generate-dir", required=True)
    p.add_argument(
        "--expect",
        required=True,
        help='dispatched pairs, e.g. "devops:OPERATIONS,developers:ARCHITECTURE"',
    )
    args = p.parse_args(argv)

    try:
        pairs = parse_expect(args.expect)
    except ValueError as exc:
        print(f"ERROR: --expect {exc}", file=sys.stderr)
        return 2
    if not pairs:
        print("ERROR: --expect listed no audience/document pairs", file=sys.stderr)
        return 2

    if not os.path.isdir(args.generate_dir):
        print(
            f"ERROR: generate dir does not exist: {args.generate_dir}",
            file=sys.stderr,
        )
        return 2

    failures = []
    for audience, document in pairs:
        status, detail = inspect(args.generate_dir, audience, document)
        print(f"  {status:8} {audience}/{document} -- {detail}")
        if status != "OK":
            failures.append(f"{audience}/{document}")

    print()
    if failures:
        print(
            f"WRITER OUTPUT: {len(failures)} of {len(pairs)} dispatched "
            f"document(s) produced nothing: {', '.join(failures)}"
        )
        print(
            "Partial generation is acceptable -- continue, but report these as "
            "failed rather than counting the files already in the docs directory."
        )
        return 1

    print(f"WRITER OUTPUT: all {len(pairs)} dispatched document(s) produced sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
