#!/usr/bin/env python3
"""Git-based section freshness analysis for documentation.

Scans generated markdown documentation for docs-meta comments, then uses
git history to determine if the referenced source files have changed since
the documentation was last updated. Reports stale, broken, and unknown
sections with severity and suggested actions.

Used by the scan and generate-update pipeline steps.

Zero external dependencies -- stdlib only.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# Allow importing lib modules when run from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.json_io import save_json
from lib.git_helpers import git_file_changed_since, git_last_modified


# ── Constants ────────────────────────────────────────────────────────────────

# Pattern to extract docs-meta JSON from HTML comments
DOCS_META_PATTERN = re.compile(
    r"<!--\s*docs-meta:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)

# Pattern to detect markdown headings
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


# ── Git Helpers ──────────────────────────────────────────────────────────────


def _is_git_repo(project_root):
    """Check if project_root is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


# ── Docs-meta Parsing ────────────────────────────────────────────────────────


def _parse_sections(fpath):
    """Parse a markdown file into sections with their docs-meta metadata.

    Returns list of dicts with keys:
    - heading: section heading text (or filename if no heading before meta)
    - meta: parsed docs-meta dict (or None if no docs-meta comment)
    - line: line number of the docs-meta comment (or heading)
    """
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, IOError):
        return []

    sections = []
    lines = content.splitlines()

    current_heading = os.path.basename(fpath)
    has_any_meta = False

    for i, line in enumerate(lines, start=1):
        # Track headings
        heading_match = HEADING_PATTERN.match(line.strip())
        if heading_match:
            current_heading = heading_match.group(2).strip()

        # Check for docs-meta comments
        meta_match = DOCS_META_PATTERN.search(line)
        if meta_match:
            has_any_meta = True
            try:
                meta = json.loads(meta_match.group(1))
            except json.JSONDecodeError:
                meta = None

            sections.append({
                "heading": current_heading,
                "meta": meta,
                "line": i,
            })

    # If no docs-meta found at all, report the whole file as unknown
    if not has_any_meta and lines:
        sections.append({
            "heading": current_heading,
            "meta": None,
            "line": 1,
        })

    return sections


# ── Staleness Analysis ───────────────────────────────────────────────────────


def _analyze_section(section, doc_path, project_root, is_git):
    """Analyze a single section for staleness.

    Returns a staleness entry dict, or None if the section is fresh.
    """
    meta = section.get("meta")
    heading = section.get("heading", "Unknown")

    # No docs-meta: unknown staleness
    if meta is None:
        return {
            "document": doc_path,
            "section": heading,
            "reason": "Unknown -- no docs-meta comment found",
            "changed_files": [],
            "severity": "low",
            "suggested_action": "Consider reviewing section freshness",
        }

    # Non-git repo: report all as unknown
    if not is_git:
        return {
            "document": doc_path,
            "section": heading,
            "reason": "Unknown -- not a git repository",
            "changed_files": [],
            "severity": "low",
            "suggested_action": "Consider reviewing section freshness",
        }

    last_updated = meta.get("last_updated", "")
    sources = meta.get("sources", [])

    if not sources:
        return None  # Fresh by default if no sources listed

    changed_files = []
    broken_files = []

    for source in sources:
        source_path = os.path.join(project_root, source)

        # Check if source file exists
        if not os.path.isfile(source_path):
            broken_files.append(source)
            continue

        # Check if source changed since last_updated
        if last_updated and git_file_changed_since(
            source, last_updated, repo_root=project_root
        ):
            changed_files.append(source)

    # Determine staleness
    if broken_files:
        # Broken references: high severity
        all_affected = broken_files + changed_files
        return {
            "document": doc_path,
            "section": heading,
            "reason": f"Stale -- broken references to deleted files: {', '.join(broken_files)}",
            "changed_files": all_affected,
            "severity": "high",
            "suggested_action": (
                f"Remove or update references to deleted file {broken_files[0]}"
                if len(broken_files) == 1
                else f"Remove or update references to {len(broken_files)} deleted files"
            ),
        }

    if changed_files:
        # Stale: severity based on number of changed files
        n_changed = len(changed_files)
        severity = "high" if n_changed >= 3 else "medium"

        return {
            "document": doc_path,
            "section": heading,
            "reason": f"Stale -- {n_changed} source file(s) changed since {last_updated}",
            "changed_files": changed_files,
            "severity": severity,
            "suggested_action": (
                f"Regenerate section -- {n_changed} source files changed since {last_updated}"
            ),
        }

    # All sources unchanged -- section is fresh
    return None


# ── Main Check Logic ─────────────────────────────────────────────────────────


def check_staleness(docs_dir, project_root):
    """Check all markdown docs in docs_dir for staleness.

    Args:
        docs_dir: Directory containing generated markdown documentation.
        project_root: Project root for git operations and path resolution.

    Returns:
        List of staleness entry dicts. Only includes entries that are NOT
        fresh (stale, broken, or unknown).
    """
    entries = []

    if not os.path.isdir(docs_dir):
        return entries

    is_git = _is_git_repo(project_root)

    for dirpath, _dirnames, filenames in os.walk(docs_dir):
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dirpath, fname)
            sections = _parse_sections(fpath)

            for section in sections:
                entry = _analyze_section(
                    section, fpath, project_root, is_git
                )
                if entry is not None:
                    entries.append(entry)

    return entries


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Git-based section freshness analysis for documentation."
    )
    parser.add_argument(
        "--docs-dir",
        required=True,
        help="Directory containing generated docs to check.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Project root for git operations.",
    )
    parser.add_argument(
        "--output",
        help="Path to write JSON results. If omitted, prints to stdout.",
    )

    args = parser.parse_args()

    entries = check_staleness(
        docs_dir=args.docs_dir,
        project_root=args.project_root,
    )

    # Write output
    if args.output:
        save_json(args.output, entries)
    else:
        json.dump(entries, sys.stdout, indent=2)
        sys.stdout.write("\n")

    # Print summary to stderr
    stale = sum(1 for e in entries if "stale" in e.get("reason", "").lower())
    broken = sum(1 for e in entries if e.get("severity") == "high" and "broken" in e.get("reason", "").lower())
    unknown = sum(1 for e in entries if "unknown" in e.get("reason", "").lower())

    # Count docs
    doc_files = set()
    if os.path.isdir(args.docs_dir):
        for dirpath, _, filenames in os.walk(args.docs_dir):
            for fname in filenames:
                if fname.endswith(".md"):
                    doc_files.add(os.path.join(dirpath, fname))

    total_sections = len(entries)
    print(
        f"Checked {total_sections} sections in {len(doc_files)} docs. "
        f"{stale} stale, {broken} broken, {unknown} unknown.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
