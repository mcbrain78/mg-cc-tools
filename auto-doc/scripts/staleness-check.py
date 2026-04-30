#!/usr/bin/env python3
"""Git-based section freshness analysis for XML documentation sources.

Walks XML source files and, for each section, compares the `last-updated`
attribute against the git history of every source file referenced by the
section's typed refs. Source files are derived from `config.path` refs
(direct file references) and `code.module` refs (the module a function or
class lives in). Refs without a source-file anchor (`db`, `env`, `flow`,
`enum`, `dep`, `literal`, `ext`, `malformed`) are skipped.

Output shape matches the previous markdown-based implementation so
the downstream consumer (`merge-scan.py`) is unchanged.

Used by the scan pipeline step.

Zero external dependencies beyond the project's lxml requirement (via
parse_xml_doc).
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.json_io import save_json
from lib.git_helpers import git_file_changed_since
from lib.xml_doc import parse_xml_doc, walk_sections


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


# ── Source-file extraction from refs ─────────────────────────────────────────


def _source_paths_from_refs(refs):
    """Return the ordered, deduplicated list of source file paths the
    section's typed refs anchor against.

    - `config.path` -> the file directly
    - `code.module` -> the module file of a function/class

    Other ref types (db, env, flow, enum, dep, literal, ext, malformed)
    have no source-file anchor and are skipped.
    """
    seen = set()
    paths = []
    for ref in refs:
        ref_type = ref.get("type", "")
        source = None
        if ref_type == "config":
            source = ref.get("path", "").strip()
        elif ref_type == "code":
            source = ref.get("module", "").strip()
        if source and source not in seen:
            seen.add(source)
            paths.append(source)
    return paths


# ── Staleness Analysis ───────────────────────────────────────────────────────


def _analyze_section(section, section_path, doc_path, project_root, is_git):
    """Analyze a single section for staleness.

    Returns a staleness entry dict, or None if the section is fresh.
    """
    last_updated = section.get("last_updated", "")
    sources = _source_paths_from_refs(section.get("refs", []))

    # Non-git repo: report all as unknown
    if not is_git:
        return {
            "document": doc_path,
            "section": section_path,
            "reason": "Unknown -- not a git repository",
            "changed_files": [],
            "severity": "low",
            "suggested_action": "Consider reviewing section freshness",
        }

    # No last-updated attribute: unknown
    if not last_updated:
        return {
            "document": doc_path,
            "section": section_path,
            "reason": "Unknown -- section has no last-updated attribute",
            "changed_files": [],
            "severity": "low",
            "suggested_action": "Regenerate section to stamp last-updated",
        }

    # No source-file refs: nothing to compare against, so fresh by default
    if not sources:
        return None

    changed_files = []
    broken_files = []

    for source in sources:
        source_path = os.path.join(project_root, source)

        if not os.path.isfile(source_path):
            broken_files.append(source)
            continue

        if git_file_changed_since(source, last_updated, repo_root=project_root):
            changed_files.append(source)

    if broken_files:
        all_affected = broken_files + changed_files
        return {
            "document": doc_path,
            "section": section_path,
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
        n_changed = len(changed_files)
        severity = "high" if n_changed >= 3 else "medium"
        return {
            "document": doc_path,
            "section": section_path,
            "reason": f"Stale -- {n_changed} source file(s) changed since {last_updated}",
            "changed_files": changed_files,
            "severity": severity,
            "suggested_action": (
                f"Regenerate section -- {n_changed} source files changed since {last_updated}"
            ),
        }

    return None


# ── Main Check Logic ─────────────────────────────────────────────────────────


def check_staleness(xml_dir, project_root):
    """Check all XML source documents under xml_dir for staleness.

    Args:
        xml_dir: Directory containing XML source files (nested per-audience
            subdirectories and root-level shared docs are both supported).
        project_root: Project root for git operations and path resolution.

    Returns:
        List of staleness entry dicts. Only includes entries that are NOT
        fresh (stale, broken, or unknown).
    """
    entries = []

    if not os.path.isdir(xml_dir):
        return entries

    is_git = _is_git_repo(project_root)

    for dirpath, _dirnames, filenames in os.walk(xml_dir):
        for fname in filenames:
            if not fname.endswith(".xml"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                doc = parse_xml_doc(fpath)
            except Exception as exc:  # pragma: no cover - defensive
                print(
                    f"Warning: failed to parse {fpath}: {exc}",
                    file=sys.stderr,
                )
                continue

            for path, section in walk_sections(doc["sections"]):
                entry = _analyze_section(
                    section, path, fpath, project_root, is_git
                )
                if entry is not None:
                    entries.append(entry)

    return entries


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Git-based section freshness analysis for XML documentation sources."
    )
    parser.add_argument(
        "--xml-dir",
        required=True,
        help="Directory containing XML source files to check.",
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
        xml_dir=args.xml_dir,
        project_root=args.project_root,
    )

    if args.output:
        save_json(args.output, {"staleness_report": entries})
    else:
        json.dump({"staleness_report": entries}, sys.stdout, indent=2)
        sys.stdout.write("\n")

    # Summary to stderr
    stale = sum(1 for e in entries if "stale" in e.get("reason", "").lower())
    broken = sum(
        1
        for e in entries
        if e.get("severity") == "high" and "broken" in e.get("reason", "").lower()
    )
    unknown = sum(1 for e in entries if "unknown" in e.get("reason", "").lower())

    doc_files = set()
    if os.path.isdir(args.xml_dir):
        for dirpath, _, filenames in os.walk(args.xml_dir):
            for fname in filenames:
                if fname.endswith(".xml"):
                    doc_files.add(os.path.join(dirpath, fname))

    total_sections = len(entries)
    print(
        f"Checked {total_sections} sections in {len(doc_files)} docs. "
        f"{stale} stale, {broken} broken, {unknown} unknown.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
