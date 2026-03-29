#!/usr/bin/env python3
"""State tracker for per-document editorial verification.

Manages the editorial processing queue: pairs each document with
each applicable question set, tracks completion, and emits work items.
Each work item is one document × one question set, evaluated by a
single agent that reads the full document.

Two modes:

Single-item mode (default):
    Returns one work item at a time with full details on stdout.

Batch mode (--next-batch):
    Writes self-contained work item files to disk. Stdout contains only
    item indices, names, and work file paths -- no document content or
    full parameter sets flow through the orchestrator's context.

Usage:
    # Single-item mode:
    python3 editorial-next.py \
        --manifest /path/to/manifest.json \
        --checks /path/to/verify-checks.json \
        --state /path/to/editorial-state.json

    # Batch mode (init + first batch):
    python3 editorial-next.py \
        --manifest /path/to/manifest.json \
        --checks /path/to/verify-checks.json \
        --state /path/to/editorial-state.json \
        --next-batch --batch-size 5 \
        --findings-prefix /path/.mg/docs/docs-verify-findings-editorial-mini \
        --tmp-dir /path/.mg/docs/tmp

    # Batch mode (subsequent):
    python3 editorial-next.py \
        --state /path/to/editorial-state.json \
        --next-batch --batch-size 5

    # Mark items done:
    python3 editorial-next.py --state STATE --mark-done 3
    python3 editorial-next.py --state STATE --mark-done-batch 0,1,2,3,4

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def build_work_items(manifest, checks_data):
    """Build the list of (document, question_set) work items.

    Each document × applicable question set becomes one work item.
    Applicable sets are: all universal sets (audience=null) and
    audience-specific sets matching the document's audience.

    Args:
        manifest: List of manifest entries from prepare-doc-review.py.
        checks_data: Parsed verify-checks.json with question_sets.

    Returns:
        List of work item dicts with: doc_file, doc_source,
        audience, question_set, item_name, done.
    """
    question_sets = checks_data["question_sets"]

    work_items = []
    for entry in manifest:
        doc_source = entry["source"]
        audience = entry.get("audience")

        # Determine applicable set IDs for this audience
        applicable_sets = []
        for qs in question_sets:
            qs_audience = qs.get("audience")
            if qs_audience is None:
                # Universal and structural sets apply to all
                applicable_sets.append(qs["id"])
            elif qs_audience == audience:
                # Audience-specific set matches
                applicable_sets.append(qs["id"])

        doc_name = os.path.splitext(os.path.basename(doc_source))[0]
        for set_id in applicable_sets:
            work_items.append({
                "doc_file": doc_source,
                "doc_source": doc_source,
                "audience": audience,
                "question_set": set_id,
                "item_name": f"{doc_name}--{set_id}",
                "done": False,
            })

    return work_items


def emit_single_item(items):
    """Print full work item for first undone item (legacy mode)."""
    total = len(items)
    done_count = sum(1 for item in items if item["done"])

    for idx, item in enumerate(items):
        if not item["done"]:
            result = {
                "item_index": idx,
                "doc_file": item["doc_file"],
                "doc_source": item["doc_source"],
                "audience": item["audience"],
                "question_set": item["question_set"],
                "item_name": item["item_name"],
            }
            print(json.dumps(result, indent=2))
            return

    result = {"status": "DONE", "processed": done_count, "total": total}
    print(json.dumps(result, indent=2))


def emit_batch(items, batch_size, batch_config):
    """Write work files for next batch, print minimal info to stdout.

    Each work file is self-contained: the agent reads it to get all
    parameters (doc_file, checks_file, findings_file, etc.) without
    anything flowing through the orchestrator's context.

    Stdout format:
        {"status": "next", "items": [{"item_index": N, "item_name": "...", "work_file": "..."}, ...]}
        {"status": "DONE", "processed": N, "total": N}
    """
    batch_dir = batch_config["batch_dir"]
    checks_path = batch_config["checks_path"]
    findings_prefix = batch_config["findings_prefix"]
    tmp_dir = batch_config["tmp_dir"]

    os.makedirs(batch_dir, exist_ok=True)

    total = len(items)
    done_count = sum(1 for item in items if item["done"])

    # Collect undone items up to batch_size
    batch_items = []
    for idx, item in enumerate(items):
        if not item["done"]:
            batch_items.append((idx, item))
            if len(batch_items) >= batch_size:
                break

    if not batch_items:
        result = {"status": "DONE", "processed": done_count, "total": total}
        print(json.dumps(result, indent=2))
        return

    # Write work files and build minimal batch output
    output_items = []
    for idx, item in batch_items:
        work_file_path = os.path.join(batch_dir, f"item-{idx}.json")
        work_data = {
            "doc_file": item["doc_file"],
            "doc_source": item["doc_source"],
            "doc_audience": item["audience"],
            "question_set": item["question_set"],
            "item_name": item["item_name"],
            "checks_file": checks_path,
            "findings_file": f"{findings_prefix}-{idx}.json",
            "tmp_dir": tmp_dir,
        }
        save_json(work_file_path, work_data)
        output_items.append({
            "item_index": idx,
            "item_name": item["item_name"],
            "work_file": work_file_path,
        })

    result = {"status": "next", "items": output_items}
    print(json.dumps(result, indent=2))


def _load_state(state_path):
    """Load state with error handling for corruption."""
    try:
        return load_json(state_path)
    except json.JSONDecodeError:
        print(f"Error: corrupted state file: {state_path} — delete it and re-run",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Editorial verification state tracker"
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Path to review manifest (required on first call)",
    )
    parser.add_argument(
        "--checks", default=None,
        help="Path to verify-checks.json (required on first call)",
    )
    parser.add_argument(
        "--state", required=True,
        help="Path to editorial-state.json (created on first call)",
    )
    parser.add_argument(
        "--mark-done", type=int, default=None,
        help="Mark item_index as done and exit",
    )
    parser.add_argument(
        "--mark-done-batch", default=None,
        help="Comma-separated item indices to mark done",
    )
    parser.add_argument(
        "--next-batch", action="store_true",
        help="Batch mode: write work files, print minimal info",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5,
        help="Max items per batch (default: 5)",
    )
    parser.add_argument(
        "--findings-prefix", default=None,
        help="Path prefix for per-item findings files (batch mode, first call)",
    )
    parser.add_argument(
        "--tmp-dir", default=None,
        help="Tmp dir path included in work files (batch mode, first call)",
    )

    args = parser.parse_args()
    state_path = os.path.abspath(args.state)

    # --mark-done mode (single)
    if args.mark_done is not None:
        state = _load_state(state_path)
        if state is None:
            print("Error: state file not found", file=sys.stderr)
            sys.exit(1)

        idx = args.mark_done
        items = state["work_items"]
        if idx < 0 or idx >= len(items):
            print(f"Error: item_index {idx} out of range (0-{len(items) - 1})",
                  file=sys.stderr)
            sys.exit(1)

        items[idx]["done"] = True
        save_json(state_path, state)
        print(f"Marked item {idx} as done", file=sys.stderr)
        return

    # --mark-done-batch mode
    if args.mark_done_batch is not None:
        state = _load_state(state_path)
        if state is None:
            print("Error: state file not found", file=sys.stderr)
            sys.exit(1)

        items = state["work_items"]
        indices = [int(x.strip()) for x in args.mark_done_batch.split(",")]
        for idx in indices:
            if idx < 0 or idx >= len(items):
                print(f"Error: item_index {idx} out of range (0-{len(items) - 1})",
                      file=sys.stderr)
                sys.exit(1)
            items[idx]["done"] = True
        save_json(state_path, state)
        print(f"Marked {len(indices)} items as done", file=sys.stderr)
        return

    # Load or initialize state
    state = _load_state(state_path)

    if state is None:
        # First call — build state from manifest + checks
        if not args.manifest or not args.checks:
            print("Error: --manifest and --checks required on first call",
                  file=sys.stderr)
            sys.exit(1)

        manifest = load_json(os.path.abspath(args.manifest))
        if manifest is None:
            print(f"Error: manifest not found: {args.manifest}",
                  file=sys.stderr)
            sys.exit(1)

        checks_data = load_json(os.path.abspath(args.checks))
        if checks_data is None:
            print(f"Error: checks file not found: {args.checks}",
                  file=sys.stderr)
            sys.exit(1)

        work_items = build_work_items(manifest, checks_data)
        state = {"work_items": work_items}

        # Store batch config in state for subsequent calls
        if args.next_batch:
            if not args.findings_prefix or not args.tmp_dir:
                print("Error: --findings-prefix and --tmp-dir required on first batch call",
                      file=sys.stderr)
                sys.exit(1)
            batch_dir = os.path.join(os.path.abspath(args.tmp_dir), "editorial-batch")
            state["batch_config"] = {
                "batch_dir": batch_dir,
                "checks_path": os.path.abspath(args.checks),
                "findings_prefix": os.path.abspath(args.findings_prefix),
                "tmp_dir": os.path.abspath(args.tmp_dir),
            }

        save_json(state_path, state)

    # Emit results
    items = state["work_items"]

    if args.next_batch:
        batch_config = state.get("batch_config")
        if batch_config is None:
            print("Error: state was not initialized with batch config — "
                  "re-initialize with --findings-prefix and --tmp-dir",
                  file=sys.stderr)
            sys.exit(1)
        emit_batch(items, args.batch_size, batch_config)
    else:
        emit_single_item(items)


if __name__ == "__main__":
    main()
