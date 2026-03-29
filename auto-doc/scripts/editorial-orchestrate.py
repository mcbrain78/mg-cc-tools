#!/usr/bin/env python3
"""Multi-doc editorial state machine for singledoc verify pipeline.

Manages all documents in a single state file. Two modes:

    # Init: read manifest + checks, create state, write first question files
    python3 editorial-orchestrate.py --init \
        --manifest MANIFEST --checks CHECKS \
        --findings-prefix PREFIX --tmp-dir TMP \
        --state STATE

    # Next: advance active docs, return send or done action
    python3 editorial-orchestrate.py --next --state STATE

Stdout (JSON):
    init:  {"action": "spawn", "docs": [...]}
    next:  {"action": "send", "targets": [...], "finished_this_round": [...]}
    done:  {"action": "done", "docs_processed": N}

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import glob as glob_mod
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def get_applicable_sets(checks_data, audience):
    """Return list of set dicts applicable for the given audience.

    Universal sets (audience=null) apply to all documents.
    Audience-specific sets apply only when the audience matches.
    """
    applicable = []
    for qs in checks_data["question_sets"]:
        qs_audience = qs.get("audience")
        if qs_audience is None or qs_audience == audience:
            applicable.append({"id": qs["id"], "checks": qs["checks"]})
    return applicable


def build_doc_entries(manifest, checks_data, findings_prefix, tmp_dir):
    """Build per-document state entries from manifest and checks.

    Args:
        manifest: List of manifest entries from prepare-doc-review.py.
        checks_data: Parsed verify-checks.json.
        findings_prefix: Absolute path prefix for findings files.
        tmp_dir: Absolute path to tmp directory.

    Returns:
        List of doc state dicts.
    """
    docs = []
    for entry in manifest:
        source = entry["source"]
        audience = entry.get("audience")
        doc_name = os.path.splitext(os.path.basename(source))[0]
        applicable = get_applicable_sets(checks_data, audience)

        docs.append({
            "name": doc_name,
            "source": source,
            "audience": audience,
            "applicable_sets": applicable,
            "current_index": 0,
            "active": len(applicable) > 0,
            "question_file": os.path.join(tmp_dir, f"ed-questions-{doc_name}.json"),
            "findings_file": f"{findings_prefix}-{doc_name}.json",
        })

    return docs


def write_question_file(path, question_set):
    """Write a question set to the question file."""
    save_json(path, {
        "set_id": question_set["id"],
        "checks": question_set["checks"],
    })


def do_init(manifest_path, checks_path, findings_prefix, tmp_dir, state_path):
    """Initialize state, write first question files, return spawn action.

    Returns:
        Dict with action and docs list for stdout.
    """
    manifest = load_json(manifest_path)
    if manifest is None:
        print(f"Error: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    checks_data = load_json(checks_path)
    if checks_data is None:
        print(f"Error: checks file not found: {checks_path}", file=sys.stderr)
        sys.exit(1)

    # Clean stale artifacts
    for old_file in glob_mod.glob(os.path.join(tmp_dir, "ed-questions-*.json")):
        os.remove(old_file)

    docs = build_doc_entries(manifest, checks_data, findings_prefix, tmp_dir)

    # Write first question file and create empty findings for each active doc
    active_docs = []
    for doc in docs:
        if not doc["active"]:
            continue
        write_question_file(doc["question_file"], doc["applicable_sets"][0])
        save_json(doc["findings_file"], [])
        active_docs.append({
            "name": doc["name"],
            "source": doc["source"],
            "audience": doc["audience"],
            "question_file": doc["question_file"],
            "findings_file": doc["findings_file"],
        })

    save_json(state_path, {"docs": docs})

    if not active_docs:
        return {"action": "done", "docs_processed": 0}

    return {"action": "spawn", "docs": active_docs}


def do_next(state_path):
    """Advance active docs to next question set, return send or done.

    Returns:
        Dict with action, targets/finished for stdout.
    """
    state = load_json(state_path)
    if state is None:
        print(f"Error: state file not found: {state_path}", file=sys.stderr)
        sys.exit(1)

    docs = state["docs"]
    targets = []
    finished_this_round = []

    for doc in docs:
        if not doc["active"]:
            continue

        next_index = doc["current_index"] + 1
        if next_index >= len(doc["applicable_sets"]):
            doc["active"] = False
            finished_this_round.append(doc["name"])
        else:
            doc["current_index"] = next_index
            write_question_file(
                doc["question_file"],
                doc["applicable_sets"][next_index],
            )
            targets.append({
                "name": doc["name"],
                "question_file": doc["question_file"],
                "findings_file": doc["findings_file"],
            })

    save_json(state_path, state)

    if targets:
        return {
            "action": "send",
            "targets": targets,
            "finished_this_round": finished_this_round,
        }

    total_processed = sum(1 for d in docs if not d["active"])
    return {"action": "done", "docs_processed": total_processed}


def main():
    parser = argparse.ArgumentParser(
        description="Multi-doc editorial state machine"
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize state from manifest + checks",
    )
    parser.add_argument(
        "--next", action="store_true",
        help="Advance active docs to next question set",
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Path to review manifest (required with --init)",
    )
    parser.add_argument(
        "--checks", default=None,
        help="Path to verify-checks.json (required with --init)",
    )
    parser.add_argument(
        "--findings-prefix", default=None,
        help="Absolute path prefix for editorial findings (required with --init)",
    )
    parser.add_argument(
        "--tmp-dir", default=None,
        help="Path to tmp directory (required with --init)",
    )
    parser.add_argument(
        "--state", required=True,
        help="Path to state file",
    )

    args = parser.parse_args()

    if not args.init and not args.next:
        print("Error: specify --init or --next", file=sys.stderr)
        sys.exit(1)

    if args.init and args.next:
        print("Error: specify only one of --init or --next", file=sys.stderr)
        sys.exit(1)

    if args.init:
        if not args.manifest or not args.checks or not args.findings_prefix or not args.tmp_dir:
            print(
                "Error: --manifest, --checks, --findings-prefix, and --tmp-dir "
                "are required with --init",
                file=sys.stderr,
            )
            sys.exit(1)

        result = do_init(
            manifest_path=os.path.abspath(args.manifest),
            checks_path=os.path.abspath(args.checks),
            findings_prefix=os.path.abspath(args.findings_prefix),
            tmp_dir=os.path.abspath(args.tmp_dir),
            state_path=os.path.abspath(args.state),
        )
    else:
        result = do_next(state_path=os.path.abspath(args.state))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
