#!/usr/bin/env python3
"""Write the set of sections that still have uncleared entities.

Between resolution waves the uncleared file shrinks: propagation inside a wave
removes an entity from every section that mentioned it, so sections that had work
at the start of the wave can have none by the end. The next wave's agents are
scoped by an affected-sections filter, and this recomputes it from whatever is
actually left.

Sorted and de-duplicated, so the filter is stable across runs and a section
mentioned by ten uncleared entities is listed once.

The first stdout word answers the caller's actual question -- whether to spawn a
wave for this document at all. `AFFECTED: <n>` means there is work; `NO-SECTIONS`
means there is none, which includes the uncleared file not existing. That is a
normal outcome of a converging audit, not a failure, so it exits 0; only a
malformed uncleared file is an error.

Usage:
    affected-sections.py --uncleared-file <path> --output <path>
"""

import argparse
import json
import os
import sys


def sections_from(uncleared):
    """Distinct section paths, sorted. Entries without a section are ignored."""
    return sorted({e["section"] for e in uncleared if e.get("section")})


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Recompute the affected-sections filter from uncleared entities."
    )
    p.add_argument("--uncleared-file", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)

    try:
        with open(args.uncleared_file) as f:
            uncleared = json.load(f)
    except FileNotFoundError:
        print(f"NO-SECTIONS: {args.uncleared_file} does not exist")
        return 0
    except json.JSONDecodeError as exc:
        print(f"ERROR: {args.uncleared_file} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(uncleared, list):
        print(
            f"ERROR: {args.uncleared_file} must hold a JSON array, got "
            f"{type(uncleared).__name__}",
            file=sys.stderr,
        )
        return 1

    sections = sections_from(uncleared)

    parent = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(parent, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(sections, f, indent=2)
        f.write("\n")

    if not sections:
        why = (
            f"{len(uncleared)} uncleared entr(ies) but none name a section"
            if uncleared
            else "uncleared is empty"
        )
        print(f"NO-SECTIONS: {why} -- wrote empty filter to {args.output}")
        return 0

    print(f"AFFECTED: {len(sections)} section(s) -> {args.output}")
    for s in sections:
        print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
