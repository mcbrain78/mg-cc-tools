#!/usr/bin/env python3
"""Print how many elements a JSON array file holds.

Used where the orchestrator needs to branch on "did anything land in this file"
-- currently the dismissed-this-run list, which decides whether the classification
agent is spawned at all.

A missing file counts as 0 rather than an error: the pipeline creates these lists
lazily, and "not there yet" and "there but empty" mean the same thing to every
caller. A file holding something other than an array IS an error, because that
means the producer wrote a shape the consumer does not expect.

Prints the count alone on stdout so the caller can read it as a number.

Usage:
    count-json-array.py --file <path>
"""

import argparse
import json
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description="Print the length of a JSON array file.")
    p.add_argument("--file", required=True)
    args = p.parse_args(argv)

    try:
        with open(args.file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(0)
        return 0
    except json.JSONDecodeError as exc:
        print(f"ERROR: {args.file} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, list):
        print(
            f"ERROR: {args.file} holds {type(data).__name__}, expected a JSON array",
            file=sys.stderr,
        )
        return 1

    print(len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
