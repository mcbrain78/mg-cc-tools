#!/usr/bin/env python3
"""DEPRECATED: verify-section-refs.py is no longer used.

Writer agents now emit typed_refs directly. Reference verification is handled
by verify-xml-refs.py (deterministic) and verify-prose.md (LLM audit).

This stub exists so that writers not yet migrated to typed_refs don't crash.
It accepts the same CLI args and exits 0 immediately.
"""

import sys


def main():
    print("SKIP — verify-section-refs.py is deprecated (typed_refs pipeline)", file=sys.stderr)


if __name__ == "__main__":
    main()
