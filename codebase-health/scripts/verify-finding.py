#!/usr/bin/env python3
"""Record verification results for health scan findings.

Three modes of operation:

Append mode (verifier subagent building per-category results):
    python3 verify-finding.py \
        --output <scan-logs/verify-orphaned-code.json> \
        --id F001 --safety safe-to-fix \
        --reasoning "..." --impact-analysis "..." \
        --dependents "file1.py:func,file2.py:Class" \
        --test-coverage covered \
        --proposed-change "..." \
        [--risk-notes ""] [--requires-human-approval]

Single mode (update one finding in the main findings file):
    python3 verify-finding.py \
        --findings <health-scan-findings.json> \
        --id F001 --safety safe-to-fix \
        --reasoning "..." --impact-analysis "..." \
        --dependents "file1.py:func,file2.py:Class" \
        --test-coverage covered \
        --proposed-change "..." \
        [--risk-notes ""] [--requires-human-approval]

Batch mode (merge subagent results into main findings file):
    python3 verify-finding.py \
        --findings <health-scan-findings.json> \
        --batch <scan-logs/verify-orphaned-code.json>

Atomic writes via temp file + os.replace(). Zero external dependencies.
"""

import argparse
import json
import os
import sys

VALID_SAFETY = ["safe-to-fix", "needs-review", "do-not-touch"]
VALID_TEST_COVERAGE = ["covered", "partial", "none"]


def load_json(path):
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_array(path):
    """Load a JSON array from path, or return [] if file doesn't exist."""
    if not os.path.isfile(path):
        return []
    data = load_json(path)
    if not isinstance(data, list):
        print(f"Error: {path} does not contain a JSON array", file=sys.stderr)
        sys.exit(1)
    return data


def save_json(path, data):
    """Atomic write JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def build_verification(args):
    """Build a verification object from CLI args."""
    dependents = []
    if args.dependents:
        dependents = [d.strip() for d in args.dependents.split(",") if d.strip()]

    return {
        "safety": args.safety,
        "reasoning": args.reasoning,
        "impact_analysis": args.impact_analysis,
        "dependents": dependents,
        "test_coverage": args.test_coverage,
        "proposed_change": args.proposed_change,
        "risk_notes": args.risk_notes or "",
        "requires_human_approval": args.requires_human_approval,
    }


def apply_single(data, finding_id, verification):
    """Apply verification to a single finding by ID. Returns True if found."""
    for finding in data.get("findings", []):
        if finding.get("id") == finding_id:
            finding["verification"] = verification
            return True
    return False


def apply_batch(data, batch):
    """Apply a batch of verification results. Returns (updated_count, missing_ids)."""
    findings_by_id = {f["id"]: f for f in data.get("findings", [])}

    updated = 0
    missing = []
    for entry in batch:
        fid = entry.get("id")
        verification = entry.get("verification")
        if not fid:
            print("Warning: batch entry missing 'id', skipping", file=sys.stderr)
            continue
        if fid in findings_by_id:
            findings_by_id[fid]["verification"] = verification
            updated += 1
        else:
            missing.append(fid)

    return updated, missing


def main():
    parser = argparse.ArgumentParser(
        description="Record verification results for health scan findings"
    )

    # Mode selectors (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--output", default=None,
        help="Append mode: path to per-category verify JSON array"
    )
    mode_group.add_argument(
        "--findings", default=None,
        help="Single/batch mode: path to health-scan-findings.json"
    )

    # Batch mode
    parser.add_argument(
        "--batch", default=None,
        help="Batch mode: path to JSON array of {id, verification} objects"
    )

    # Finding ID (required for append and single modes)
    parser.add_argument("--id", default=None, help="Finding ID (e.g. F001)")

    # Verification fields
    parser.add_argument(
        "--safety", default=None, choices=VALID_SAFETY,
        help="Safety classification"
    )
    parser.add_argument("--reasoning", default=None,
                        help="Why this classification was chosen")
    parser.add_argument("--impact-analysis", default=None,
                        help="What changes when this finding is addressed")
    parser.add_argument(
        "--dependents", default=None,
        help="Comma-separated list of dependent files/symbols"
    )
    parser.add_argument(
        "--test-coverage", default=None, choices=VALID_TEST_COVERAGE,
        help="Test coverage level"
    )
    parser.add_argument("--proposed-change", default=None,
                        help="Precise instruction for the implementor")
    parser.add_argument("--risk-notes", default="",
                        help="What could go wrong (defaults to empty string)")
    parser.add_argument(
        "--requires-human-approval", action="store_true", default=False,
        help="Flag finding as requiring human approval"
    )

    args = parser.parse_args()

    # ── Append mode: --output + field args ──
    if args.output:
        if not args.id:
            print("Error: --id is required with --output", file=sys.stderr)
            sys.exit(1)
        if not args.safety:
            print("Error: --safety is required with --output", file=sys.stderr)
            sys.exit(1)

        verification = build_verification(args)
        output_path = os.path.abspath(args.output)
        entries = load_array(output_path)
        entries.append({"id": args.id, "verification": verification})
        save_json(output_path, entries)

        print(f"Appended verification for {args.id} ({args.safety}) "
              f"to {os.path.basename(output_path)}", file=sys.stderr)
        return

    # ── Findings mode: --findings + (--batch | --id + fields) ──
    findings_path = os.path.abspath(args.findings)
    if not os.path.isfile(findings_path):
        print(f"Error: findings file not found: {findings_path}",
              file=sys.stderr)
        sys.exit(1)

    try:
        data = load_json(findings_path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: failed to load findings: {e}", file=sys.stderr)
        sys.exit(1)

    if args.batch:
        # ── Batch mode: --findings + --batch ──
        batch_path = os.path.abspath(args.batch)
        if not os.path.isfile(batch_path):
            print(f"Error: batch file not found: {batch_path}",
                  file=sys.stderr)
            sys.exit(1)
        try:
            batch = load_json(batch_path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error: failed to load batch file: {e}", file=sys.stderr)
            sys.exit(1)

        if not isinstance(batch, list):
            print(f"Error: batch file must contain a JSON array",
                  file=sys.stderr)
            sys.exit(1)

        updated, missing = apply_batch(data, batch)
        if missing:
            print(f"Warning: {len(missing)} IDs not found: {', '.join(missing)}",
                  file=sys.stderr)
        print(f"Updated {updated} verifications ({len(missing)} not found)",
              file=sys.stderr)

    else:
        # ── Single mode: --findings + --id + fields ──
        if not args.id:
            print("Error: --id is required (or use --batch)", file=sys.stderr)
            sys.exit(1)
        if not args.safety:
            print("Error: --safety is required with --id", file=sys.stderr)
            sys.exit(1)

        verification = build_verification(args)
        found = apply_single(data, args.id, verification)
        if not found:
            print(f"Warning: finding {args.id} not found in {findings_path}",
                  file=sys.stderr)
            print("Updated 0 verifications (1 not found)", file=sys.stderr)
        else:
            print(f"Updated verification for {args.id} ({args.safety})",
                  file=sys.stderr)

    save_json(findings_path, data)


if __name__ == "__main__":
    main()
