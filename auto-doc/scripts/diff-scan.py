#!/usr/bin/env python3
"""Deterministic diff scoping for incremental documentation scans.

Produces a scoped work order (diff-scope.json) by cross-referencing
git diff output against reference manifests and optionally enriching
with GSD phase context.

CLI interface:
    diff-scan.py \\
        --project-root <path> \\
        --manifests-dir <path to .mg/docs/reference-manifests/> \\
        --docs-dir <path to docs/auto-doc/> \\
        --since <last generation ISO timestamp> \\
        --gsd-dir <path to .planning/phases/> (optional) \\
        --output <path to write diff-scope.json>

Zero external dependencies -- stdlib + lib/json_io only.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import save_json  # noqa: E402


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def resolve_commit(since_timestamp, project_root):
    """Resolve ISO timestamp to the nearest commit SHA before that time.

    Uses ``git rev-list --max-count=1 --before=<timestamp> HEAD``.

    Args:
        since_timestamp: ISO-8601 timestamp string.
        project_root: Repository root directory.

    Returns:
        Commit SHA string, or None if no commit exists before the
        timestamp (e.g. timestamp predates the first commit).
    """
    cmd = [
        "git", "rev-list", "--max-count=1",
        f"--before={since_timestamp}", "HEAD",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", cwd=project_root,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def get_changed_files(base_commit, project_root):
    """Return list of file paths changed between *base_commit* and HEAD.

    Uses ``git diff -M --name-only``.  Paths are normalised (no
    leading ``./``).

    Args:
        base_commit: Base commit SHA.
        project_root: Repository root directory.

    Returns:
        List of relative file path strings.
    """
    cmd = [
        "git", "diff", "-M", "--name-only",
        base_commit, "HEAD",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", cwd=project_root,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    paths = []
    for line in result.stdout.strip().splitlines():
        p = line.strip()
        if p:
            # Normalise: strip leading ./
            if p.startswith("./"):
                p = p[2:]
            paths.append(p)
    return paths


def get_renames(base_commit, project_root):
    """Return dict mapping *old_path* -> *new_path* for renames.

    Uses ``git diff -M --diff-filter=R --name-status`` and parses
    ``R<score>\\t<old>\\t<new>`` lines.

    Args:
        base_commit: Base commit SHA.
        project_root: Repository root directory.

    Returns:
        Dict of ``{old_path: new_path}``.
    """
    cmd = [
        "git", "diff", "-M", "--diff-filter=R",
        "--name-status", base_commit, "HEAD",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", cwd=project_root,
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    if result.returncode != 0:
        return {}
    renames = {}
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            old = parts[1].lstrip("./")
            new = parts[2].lstrip("./")
            renames[old] = new
    return renames


# ---------------------------------------------------------------------------
# Manifest cross-referencing
# ---------------------------------------------------------------------------

def build_file_to_sections_index(manifests_dir):
    """Build reverse index: file_path -> list of section refs.

    Reads all ``*.json`` manifest files in *manifests_dir*.  Skips
    ``_written_sections`` metadata entries and silently ignores
    corrupt JSON files.

    Args:
        manifests_dir: Directory containing per-audience manifest
            JSON files.

    Returns:
        Dict mapping file path strings to lists of
        ``{"audience", "document", "section"}`` dicts.
    """
    index = {}
    manifest_files = glob.glob(os.path.join(manifests_dir, "*.json"))
    for mf in manifest_files:
        try:
            with open(mf, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable manifest -- skip with warning
            print(
                f"Warning: skipping corrupt manifest {mf}",
                file=sys.stderr,
            )
            continue
        if not isinstance(manifest, dict) or "documents" not in manifest:
            continue
        audience = manifest.get(
            "audience",
            os.path.splitext(os.path.basename(mf))[0],
        )
        for doc_name, sections in manifest["documents"].items():
            if not isinstance(sections, dict):
                continue
            for section_slug, section_data in sections.items():
                if section_slug == "_written_sections":
                    continue
                if not isinstance(section_data, dict):
                    continue
                for fp in section_data.get("file_paths", []):
                    # Normalise path
                    if fp.startswith("./"):
                        fp = fp[2:]
                    if fp not in index:
                        index[fp] = []
                    index[fp].append({
                        "audience": audience,
                        "document": doc_name,
                        "section": section_slug,
                    })
    return index


# ---------------------------------------------------------------------------
# Change classification
# ---------------------------------------------------------------------------

def classify_changes(changed_files, renames, file_index, deleted_check_fn):
    """Classify changed files into affected sections, new candidates, and deleted.

    Args:
        changed_files: List of changed file paths from git diff.
        renames: Dict of old_path -> new_path from get_renames().
        file_index: Reverse index from build_file_to_sections_index().
        deleted_check_fn: Callable(file_path) -> bool indicating
            whether a file has been deleted from the working tree.

    Returns:
        Dict with keys ``affected_sections``, ``new_file_candidates``,
        ``deleted_files``.
    """
    # Build reverse renames: new_path -> old_path
    reverse_renames = {v: k for k, v in renames.items()}

    # Track sections by (audience, document, section) to deduplicate
    section_key_map = {}  # (aud, doc, sec) -> section_dict
    new_file_candidates = []
    deleted_files_map = {}  # file -> list of referenced_in entries

    for fpath in changed_files:
        # Check if this file is the new name of a rename
        old_path = reverse_renames.get(fpath)

        # Look up sections: try the file itself, and if renamed, the old path
        section_refs = []
        if fpath in file_index:
            section_refs.extend(file_index[fpath])
        if old_path and old_path in file_index:
            section_refs.extend(file_index[old_path])

        if not section_refs:
            # Not in any manifest -- it's a new file candidate
            new_file_candidates.append({
                "file": fpath,
                "reason": "new file, not in any manifest",
                "gsd_context": None,
            })
            continue

        # Check if the file is deleted
        is_deleted = deleted_check_fn(fpath)
        if is_deleted:
            if fpath not in deleted_files_map:
                deleted_files_map[fpath] = []
            for ref in section_refs:
                deleted_files_map[fpath].append({
                    "audience": ref["audience"],
                    "document": ref["document"],
                    "section": ref["section"],
                })
            # Still add to affected sections so the section gets flagged
            # (fall through)

        # Add to affected sections, deduplicating by (audience, doc, section)
        for ref in section_refs:
            key = (ref["audience"], ref["document"], ref["section"])
            if key not in section_key_map:
                section_key_map[key] = {
                    "audience": ref["audience"],
                    "document": ref["document"],
                    "section": ref["section"],
                    "reason": "source file modified",
                    "changed_files": [],
                    "gsd_context": None,
                    "renames": {},
                }
            entry = section_key_map[key]
            if fpath not in entry["changed_files"]:
                entry["changed_files"].append(fpath)
            # Record rename mapping if applicable
            if old_path:
                entry["renames"][old_path] = fpath

    # Build final lists
    affected_sections = list(section_key_map.values())
    # Clean up empty renames dicts
    for section in affected_sections:
        if not section["renames"]:
            del section["renames"]

    deleted_files = [
        {"file": f, "referenced_in": refs}
        for f, refs in deleted_files_map.items()
    ]

    return {
        "affected_sections": affected_sections,
        "new_file_candidates": new_file_candidates,
        "deleted_files": deleted_files,
    }


# ---------------------------------------------------------------------------
# GSD phase discovery
# ---------------------------------------------------------------------------

def discover_gsd_phases(gsd_dir, since_timestamp, project_root):
    """Find GSD phase summaries modified since *since_timestamp*.

    Searches for ``*-SUMMARY.md`` files under *gsd_dir* that have
    git commits since the given timestamp.  Reads frontmatter to
    extract phase number, name, deviations, and key decisions.

    Args:
        gsd_dir: Path to ``.planning/phases/`` directory, or None.
        since_timestamp: ISO-8601 timestamp string.
        project_root: Repository root directory.

    Returns:
        List of dicts with ``phase``, ``name``, ``deviations``,
        ``key_decisions``.  Empty list if *gsd_dir* is None or
        doesn't exist.
    """
    if gsd_dir is None or not os.path.isdir(gsd_dir):
        return []

    # Find SUMMARY.md files modified since timestamp via git log
    # Use relative path from project root for git
    try:
        rel_gsd = os.path.relpath(gsd_dir, project_root)
    except ValueError:
        return []

    cmd = [
        "git", "log",
        f"--since={since_timestamp}",
        "--name-only",
        "--pretty=format:",
        "--", f"{rel_gsd}/*-SUMMARY.md",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", cwd=project_root,
        )
    except (subprocess.SubprocessError, OSError):
        return []

    if result.returncode != 0:
        return []

    # Collect unique summary file paths
    summary_paths = set()
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and line.endswith("-SUMMARY.md"):
            summary_paths.add(line)

    phases = []
    seen_phase_nums = set()
    for rel_path in sorted(summary_paths):
        abs_path = os.path.join(project_root, rel_path)
        if not os.path.isfile(abs_path):
            continue

        phase_info = _parse_summary_frontmatter(abs_path)
        if phase_info and phase_info["phase"] not in seen_phase_nums:
            seen_phase_nums.add(phase_info["phase"])
            phases.append(phase_info)

    return phases


def _parse_summary_frontmatter(filepath):
    """Parse phase number, name, deviations, key_decisions from SUMMARY.md.

    Reads YAML-style frontmatter between ``---`` delimiters.

    Returns:
        Dict with ``phase``, ``name``, ``deviations``, ``key_decisions``
        or None if parsing fails.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    # Extract frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter = parts[1]

    phase_num = None
    phase_name = None
    key_decisions = []
    deviations = []

    for line in frontmatter.splitlines():
        line = line.strip()
        # Phase field: "phase: 06-fix-verify" or "phase: 06"
        m = re.match(r'^phase:\s*(.+)', line)
        if m:
            val = m.group(1).strip()
            # Extract phase number (leading digits)
            num_match = re.match(r'^(\d+)', val)
            if num_match:
                phase_num = num_match.group(1)
            # Extract name (after number and dash)
            name_match = re.match(r'^\d+-(.+)', val)
            if name_match:
                phase_name = name_match.group(1).strip()
            continue

        # Key decisions (YAML list items under key-decisions:)
        if line.startswith("- ") and key_decisions is not None:
            # Could be a key-decision or deviation list item
            item = line[2:].strip().strip('"').strip("'")
            if item:
                key_decisions.append(item)

    if phase_num is None:
        return None

    return {
        "phase": phase_num,
        "name": phase_name or "",
        "deviations": deviations,
        "key_decisions": key_decisions,
    }


# ---------------------------------------------------------------------------
# Main / CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.  Wires all functions together with argparse."""
    parser = argparse.ArgumentParser(
        description="Produce scoped work order for incremental documentation scan",
    )
    parser.add_argument("--project-root", required=True,
                        help="Repository root directory")
    parser.add_argument("--manifests-dir", required=True,
                        help="Path to .mg/docs/reference-manifests/")
    parser.add_argument("--docs-dir", required=True,
                        help="Path to docs/auto-doc/")
    parser.add_argument("--since", required=True,
                        help="ISO timestamp of last generation")
    parser.add_argument("--gsd-dir", default=None,
                        help="Path to .planning/phases/ (optional)")
    parser.add_argument("--output", required=True,
                        help="Path to write diff-scope.json")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)

    # 1. Resolve timestamp to base commit
    base_commit = resolve_commit(args.since, project_root)

    if base_commit is None:
        # No commit found before timestamp -- produce empty scope
        scope = {
            "since": args.since,
            "summary": {
                "files_changed": 0,
                "files_added": 0,
                "files_deleted": 0,
                "sections_affected": 0,
                "new_file_candidates": 0,
            },
            "affected_sections": [],
            "new_file_candidates": [],
            "deleted_files": [],
            "gsd_phases_since": [],
        }
        save_json(args.output, scope)
        print(
            "No commit found before timestamp, wrote empty scope.",
            file=sys.stderr,
        )
        return

    # 2. Get changed files and renames
    changed_files = get_changed_files(base_commit, project_root)
    renames = get_renames(base_commit, project_root)

    # 3. Build manifest index
    file_index = build_file_to_sections_index(args.manifests_dir)

    # 4. Classify changes
    def deleted_check_fn(fpath):
        """Check if file is deleted from the working tree."""
        return not os.path.exists(os.path.join(project_root, fpath))

    classification = classify_changes(
        changed_files, renames, file_index, deleted_check_fn,
    )

    # 5. Discover GSD phases
    gsd_phases = discover_gsd_phases(
        args.gsd_dir, args.since, project_root,
    )

    # 6. Enrich affected sections with GSD context
    if gsd_phases:
        gsd_summary = "; ".join(
            f"Phase {p['phase']}: {', '.join(p['key_decisions'])}"
            for p in gsd_phases
            if p["key_decisions"]
        )
        if gsd_summary:
            for section in classification["affected_sections"]:
                section["gsd_context"] = gsd_summary

    # 7. Compute summary counts
    n_added = len([
        f for f in changed_files
        if f not in file_index
        and f not in {v for v in renames.values()}
    ])
    n_deleted = len(classification["deleted_files"])

    summary = {
        "files_changed": len(changed_files),
        "files_added": n_added,
        "files_deleted": n_deleted,
        "sections_affected": len(classification["affected_sections"]),
        "new_file_candidates": len(classification["new_file_candidates"]),
    }

    # 8. Build and write output
    scope = {
        "since": args.since,
        "summary": summary,
        "affected_sections": classification["affected_sections"],
        "new_file_candidates": classification["new_file_candidates"],
        "deleted_files": classification["deleted_files"],
        "gsd_phases_since": gsd_phases,
    }

    save_json(args.output, scope)
    print(
        f"Wrote diff-scope.json: {summary['files_changed']} files changed, "
        f"{summary['sections_affected']} sections affected, "
        f"{summary['new_file_candidates']} new file candidates.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
