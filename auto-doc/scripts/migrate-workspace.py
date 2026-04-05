#!/usr/bin/env python3
"""One-time migration of .mg/docs/ from flat layout to step-based layout.

Moves durable artifacts from the old directory structure (scan-logs/, tmp/,
root-level docs-verify-* files) into step-owned directories (scan/, generate/,
verify/). Transient working files in tmp/ are discarded.

Usage:
    python3 migrate-workspace.py .mg/docs
    python3 migrate-workspace.py .mg/docs --dry-run

Idempotent: skips files that already exist at the destination.
"""

import argparse
import os
import shutil
import sys


def _needs_migration(mg_docs):
    """Check if the workspace uses the old layout."""
    return (
        os.path.isdir(os.path.join(mg_docs, "scan-logs"))
        or os.path.isdir(os.path.join(mg_docs, "tmp"))
        or os.path.isfile(os.path.join(mg_docs, "docs-verify-findings.json"))
    )


def _move(src, dst, dry_run, moves):
    """Move a file/dir from src to dst, skipping if dst exists."""
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        moves.append(f"  SKIP (exists): {dst}")
        return
    if dry_run:
        moves.append(f"  WOULD MOVE: {src} -> {dst}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    moves.append(f"  MOVED: {src} -> {dst}")


def migrate(mg_docs, dry_run=False):
    """Run the migration.

    Returns (moves, discards) — lists of log messages.
    """
    moves = []
    discards = []

    scan_logs = os.path.join(mg_docs, "scan-logs")
    tmp_dir = os.path.join(mg_docs, "tmp")
    scan_dir = os.path.join(mg_docs, "scan")
    generate_dir = os.path.join(mg_docs, "generate")
    verify_dir = os.path.join(mg_docs, "verify")

    # ── Scan artifacts: scan-logs/ → scan/ ──────────────────────
    if os.path.isdir(scan_logs):
        import glob

        # Named scan outputs (scan-project.json covered by scan-*.json glob)
        for pattern in [
            "scan-*.json",
            "scan-orientation.md",
            "staleness-results.json",
            "note-classifications.json",
        ]:
            for src in glob.glob(os.path.join(scan_logs, pattern)):
                name = os.path.basename(src)
                _move(src, os.path.join(scan_dir, name), dry_run, moves)

        # Templates subdir
        templates_src = os.path.join(scan_logs, "templates")
        if os.path.isdir(templates_src):
            _move(templates_src, os.path.join(scan_dir, "templates"), dry_run, moves)

        # Term proposals → generate/terms/
        terms_dir = os.path.join(generate_dir, "terms")
        for src in glob.glob(os.path.join(scan_logs, "terms-*.json")):
            name = os.path.basename(src)
            _move(src, os.path.join(terms_dir, name), dry_run, moves)

        reconciliation = os.path.join(scan_logs, "glossary-reconciliation.log")
        _move(
            reconciliation,
            os.path.join(terms_dir, "glossary-reconciliation.log"),
            dry_run,
            moves,
        )

        # Verify refs → verify/
        for name in [
            "verify-refs-broken.json",
            "verify-refs-symbols.json",
            "verify-refs.json",
        ]:
            src = os.path.join(scan_logs, name)
            dst_name = name.replace("verify-", "", 1)  # refs-broken.json
            _move(src, os.path.join(verify_dir, dst_name), dry_run, moves)

    # ── Root-level scan artifact ────────────────────────────────
    _move(
        os.path.join(mg_docs, "diff-scope.json"),
        os.path.join(scan_dir, "diff-scope.json"),
        dry_run,
        moves,
    )

    # ── Generate artifacts: root → generate/ ────────────────────
    _move(
        os.path.join(mg_docs, "reference-manifests"),
        os.path.join(generate_dir, "reference-manifests"),
        dry_run,
        moves,
    )
    _move(
        os.path.join(mg_docs, "xml-sources"),
        os.path.join(generate_dir, "xml-sources"),
        dry_run,
        moves,
    )

    # ── Verify artifacts: root → verify/ ────────────────────────
    verify_file_map = {
        "docs-verify-findings.json": "findings.json",
        "docs-verify-report.md": "report.md",
        "docs-verify-findings-dismissed.json": "findings-dismissed.json",
        "docs-verify-findings-mechanical.json": "findings-mechanical.json",
        "docs-verify-findings-editorial.json": "findings-editorial.json",
        "docs-verify-findings-code-example.json": "findings-code-example.json",
        "docs-verify-findings-data-model.json": "findings-data-model.json",
        "docs-verify-findings-cross-doc.json": "findings-cross-doc.json",
        "docs-verify-findings-completeness.json": "findings-completeness.json",
    }
    for old_name, new_name in verify_file_map.items():
        _move(
            os.path.join(mg_docs, old_name),
            os.path.join(verify_dir, new_name),
            dry_run,
            moves,
        )

    # Dynamic per-document editorial findings
    for entry in os.listdir(mg_docs) if os.path.isdir(mg_docs) else []:
        if (
            entry.startswith("docs-verify-findings-editorial-")
            and entry.endswith(".json")
        ):
            new_name = entry.replace("docs-verify-", "", 1)
            _move(
                os.path.join(mg_docs, entry),
                os.path.join(verify_dir, new_name),
                dry_run,
                moves,
            )

    # ── Discard transient working files ─────────────────────────
    if os.path.isdir(tmp_dir):
        if dry_run:
            discards.append(f"  WOULD DISCARD: {tmp_dir}/ (transient working files)")
        else:
            shutil.rmtree(tmp_dir)
            discards.append(f"  DISCARDED: {tmp_dir}/ (transient working files)")

    # Remove empty scan-logs/ after migration
    if os.path.isdir(scan_logs):
        if dry_run:
            # In dry-run, files haven't actually moved — report intent
            discards.append(f"  WOULD REMOVE: {scan_logs}/ (if empty after migration)")
        else:
            try:
                remaining = os.listdir(scan_logs)
            except OSError:
                remaining = []
            if not remaining:
                os.rmdir(scan_logs)
                discards.append(f"  REMOVED: {scan_logs}/ (empty after migration)")
            else:
                discards.append(
                    f"  KEPT: {scan_logs}/ ({len(remaining)} files remain)"
                )

    return moves, discards


def main():
    parser = argparse.ArgumentParser(
        description="Migrate .mg/docs/ from flat to step-based layout"
    )
    parser.add_argument(
        "mg_docs",
        help="Path to .mg/docs/ directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without moving files",
    )

    args = parser.parse_args()
    mg_docs = os.path.abspath(args.mg_docs)

    if not os.path.isdir(mg_docs):
        print(f"Error: directory not found: {mg_docs}", file=sys.stderr)
        sys.exit(1)

    if not _needs_migration(mg_docs):
        print("No migration needed — workspace already uses new layout.")
        return

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Migrating workspace: {mg_docs}")

    moves, discards = migrate(mg_docs, dry_run=args.dry_run)

    if moves:
        print(f"\n{prefix}Artifacts migrated:")
        for msg in moves:
            print(msg)

    if discards:
        print(f"\n{prefix}Cleanup:")
        for msg in discards:
            print(msg)

    if not moves and not discards:
        print("Nothing to migrate.")
    elif not args.dry_run:
        print("\nMigration complete.")


if __name__ == "__main__":
    main()
