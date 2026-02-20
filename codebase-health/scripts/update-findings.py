#!/usr/bin/env python3
"""Update implementation fields in health-scan-findings.json.

Two modes of operation:

Batch mode (merge subagent results):
    python3 update-findings.py --findings <path> --batch <path>

Single mode (per-finding update):
    python3 update-findings.py --findings <path> --id F001 --status applied \
        --change-description "..." --files-modified a.py,b.py \
        --tests-run --tests-passed --rollback-commit abc123f

    python3 update-findings.py --findings <path> --id F001 --status rolled-back \
        --failure-reason "Test failed after removing function"

Atomic writes via temp file + os.replace(). Zero external dependencies.
"""

import argparse
import json
import os
import sys


def load_findings(path):
    """Load and return the findings JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_findings(path, data):
    """Atomic write: write to .tmp then replace."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def build_implementation(args):
    """Build an implementation object from CLI args."""
    impl = {
        "status": args.status,
        "change_description": args.change_description,
        "files_modified": (
            [f.strip() for f in args.files_modified.split(",") if f.strip()]
            if args.files_modified
            else []
        ),
        "tests_run": args.tests_run,
        "tests_passed": args.tests_passed,
        "rollback_commit": args.rollback_commit,
        "failure_reason": args.failure_reason,
    }
    return impl


def apply_single(data, finding_id, implementation):
    """Apply implementation to a single finding by ID. Returns True if found."""
    for finding in data.get("findings", []):
        if finding.get("id") == finding_id:
            finding["implementation"] = implementation
            return True
    return False


def apply_batch(data, batch):
    """Apply a batch of results. Returns (updated_count, missing_ids)."""
    # Build lookup by ID for O(1) access
    findings_by_id = {f["id"]: f for f in data.get("findings", [])}

    updated = 0
    missing = []
    for entry in batch:
        fid = entry.get("id")
        impl = entry.get("implementation")
        if not fid:
            print("Warning: batch entry missing 'id', skipping", file=sys.stderr)
            continue
        if fid in findings_by_id:
            findings_by_id[fid]["implementation"] = impl
            updated += 1
        else:
            missing.append(fid)

    return updated, missing


def main():
    parser = argparse.ArgumentParser(
        description="Update implementation fields in health-scan-findings.json"
    )
    parser.add_argument(
        "--findings", required=True, help="Path to health-scan-findings.json"
    )

    # Batch mode
    parser.add_argument(
        "--batch", default=None,
        help="Path to batch results JSON ([{id, implementation}, ...])"
    )

    # Single mode
    parser.add_argument("--id", default=None, help="Finding ID (e.g. F001)")
    parser.add_argument(
        "--status", default=None,
        choices=["applied", "skipped", "failed", "rolled-back"],
        help="Implementation status"
    )
    parser.add_argument("--change-description", default=None)
    parser.add_argument(
        "--files-modified", default=None,
        help="Comma-separated list of modified files"
    )
    parser.add_argument(
        "--tests-run", action="store_true", default=False,
        help="Tests were run after this change"
    )
    parser.add_argument(
        "--tests-passed", action="store_true", default=False,
        help="Tests passed after this change"
    )
    parser.add_argument("--rollback-commit", default=None)
    parser.add_argument("--failure-reason", default=None)

    args = parser.parse_args()

    # Validate mode
    if args.batch and args.id:
        print("Error: --batch and --id are mutually exclusive", file=sys.stderr)
        sys.exit(1)
    if not args.batch and not args.id:
        print("Error: specify either --batch <path> or --id <ID> --status <status>",
              file=sys.stderr)
        sys.exit(1)
    if args.id and not args.status:
        print("Error: --status is required with --id", file=sys.stderr)
        sys.exit(1)

    # Load findings
    findings_path = os.path.abspath(args.findings)
    if not os.path.isfile(findings_path):
        print(f"Error: findings file not found: {findings_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = load_findings(findings_path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: failed to load findings: {e}", file=sys.stderr)
        sys.exit(1)

    if args.batch:
        # Batch mode
        batch_path = os.path.abspath(args.batch)
        if not os.path.isfile(batch_path):
            print(f"Error: batch file not found: {batch_path}", file=sys.stderr)
            sys.exit(1)
        try:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error: failed to load batch file: {e}", file=sys.stderr)
            sys.exit(1)

        updated, missing = apply_batch(data, batch)
        if missing:
            print(f"Warning: {len(missing)} IDs not found: {', '.join(missing)}",
                  file=sys.stderr)
        print(f"Updated {updated} findings ({len(missing)} not found)", file=sys.stderr)
    else:
        # Single mode
        impl = build_implementation(args)
        found = apply_single(data, args.id, impl)
        if not found:
            print(f"Warning: finding {args.id} not found in {findings_path}",
                  file=sys.stderr)
            print("Updated 0 findings (1 not found)", file=sys.stderr)
        else:
            print(f"Updated 1 finding ({args.id})", file=sys.stderr)

    save_findings(findings_path, data)


if __name__ == "__main__":
    main()
