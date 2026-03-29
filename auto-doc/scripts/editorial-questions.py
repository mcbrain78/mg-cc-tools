#!/usr/bin/env python3
"""Question manager for per-document editorial verification.

Manages question sets for a single document: initializes applicable sets
based on audience, writes the first question set to a question file, and
advances through sets one at a time via --advance with a finding-gate.

The orchestrator calls --init once per document to set up state. The
self-driven agent calls --advance after each evaluation round to get the
next question set. A finding-gate ensures agents cannot skip evaluation.

Two modes:

    # Init: filter applicable sets for audience, write first set
    python3 editorial-questions.py \
        --init --checks CHECKS --audience AUDIENCE \
        --state STATE --question-file QFILE

    # Advance: overwrite question file with next set (finding-gate)
    python3 editorial-questions.py \
        --advance --state STATE --question-file QFILE \
        --findings-file FINDINGS  # or --no-findings

Stdout (JSON):
    continue: {"status": "continue", "set_id": "universal-1", "remaining": 6}
    finished: {"status": "finished", "sets_evaluated": 7}

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def get_applicable_sets(checks_data, audience):
    """Return list of full set dicts applicable for the given audience.

    Universal sets (audience=null) apply to all documents.
    Audience-specific sets apply only when the audience matches.

    Args:
        checks_data: Parsed verify-checks.json with question_sets.
        audience: Audience key (e.g., 'developers', 'devops') or None.

    Returns:
        List of dicts with 'id' and 'checks' keys.
    """
    applicable = []
    for qs in checks_data["question_sets"]:
        qs_audience = qs.get("audience")
        if qs_audience is None:
            # Universal and structural sets apply to all
            applicable.append({"id": qs["id"], "checks": qs["checks"]})
        elif qs_audience == audience:
            # Audience-specific set matches
            applicable.append({"id": qs["id"], "checks": qs["checks"]})
    return applicable


def write_question_file(question_file, question_set):
    """Atomically write the current question set to the question file.

    Args:
        question_file: Path to write the question file.
        question_set: Dict with 'id' and 'checks' keys.
    """
    save_json(question_file, {
        "set_id": question_set["id"],
        "checks": question_set["checks"],
    })


def init_state(checks_path, audience, state_path, question_file):
    """Create state file and write first question set.

    Args:
        checks_path: Path to verify-checks.json.
        audience: Audience key for this document.
        state_path: Path to create the state file.
        question_file: Path to write the question file.

    Returns:
        Status dict for stdout.
    """
    checks_data = load_json(checks_path)
    if checks_data is None:
        print(f"Error: checks file not found: {checks_path}", file=sys.stderr)
        sys.exit(1)

    applicable = get_applicable_sets(checks_data, audience)

    if not applicable:
        save_json(state_path, {
            "applicable_sets": [],
            "current_index": 0,
            "findings_count": 0,
        })
        return {"status": "finished", "sets_evaluated": 0}

    state = {
        "applicable_sets": applicable,
        "current_index": 0,
        "findings_count": 0,
    }
    save_json(state_path, state)

    write_question_file(question_file, applicable[0])

    remaining = len(applicable) - 1
    return {"status": "continue", "set_id": applicable[0]["id"], "remaining": remaining}


def advance_state(state_path, question_file, findings_file=None, no_findings=False):
    """Increment index and write next question set, or signal finished.

    Enforces a finding-gate: the caller must prove evaluation happened by
    passing --findings-file (with new entries) or --no-findings.

    Args:
        state_path: Path to the state file.
        question_file: Path to overwrite with next question set.
        findings_file: Path to the doc's findings JSON (optional).
        no_findings: If True, agent evaluated but found nothing.

    Returns:
        Status dict for stdout.
    """
    state = load_json(state_path)
    if state is None:
        print(f"Error: state file not found: {state_path}", file=sys.stderr)
        sys.exit(1)

    # Finding gate: require evidence of evaluation before advancing
    stored_count = state.get("findings_count", 0)
    if findings_file is not None:
        findings_data = load_json(findings_file)
        new_count = len(findings_data) if findings_data is not None else 0
        if new_count > stored_count:
            state["findings_count"] = new_count
        elif no_findings:
            pass  # Agent evaluated, found nothing new — OK
        else:
            print(
                f"Error: findings file has {new_count} entries (stored: {stored_count}). "
                "Must pass --findings-file (with new findings) or --no-findings",
                file=sys.stderr,
            )
            sys.exit(1)
    elif no_findings:
        pass  # No findings file, agent says nothing found — OK
    else:
        print(
            "Error: Must pass --findings-file (with new findings) or --no-findings",
            file=sys.stderr,
        )
        sys.exit(1)

    applicable = state["applicable_sets"]
    next_index = state["current_index"] + 1

    if next_index >= len(applicable):
        return {"status": "finished", "sets_evaluated": len(applicable)}

    state["current_index"] = next_index
    save_json(state_path, state)

    write_question_file(question_file, applicable[next_index])

    remaining = len(applicable) - next_index - 1
    return {"status": "continue", "set_id": applicable[next_index]["id"], "remaining": remaining}


def main():
    parser = argparse.ArgumentParser(
        description="Turn-based question manager for editorial verification"
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize state and write first question set",
    )
    parser.add_argument(
        "--advance", action="store_true",
        help="Advance to next question set",
    )
    parser.add_argument(
        "--checks", default=None,
        help="Path to verify-checks.json (required with --init)",
    )
    parser.add_argument(
        "--audience", default=None,
        help="Audience key for this document (required with --init)",
    )
    parser.add_argument(
        "--state", required=True,
        help="Path to per-document state file",
    )
    parser.add_argument(
        "--question-file", required=True,
        help="Path to question file (overwritten each round)",
    )
    parser.add_argument(
        "--findings-file", default=None,
        help="Path to the doc's findings JSON (used with --advance for finding-gate)",
    )
    parser.add_argument(
        "--no-findings", action="store_true",
        help="Declare that evaluation found nothing (used with --advance for finding-gate)",
    )

    args = parser.parse_args()

    if not args.init and not args.advance:
        print("Error: specify --init or --advance", file=sys.stderr)
        sys.exit(1)

    if args.init and args.advance:
        print("Error: specify only one of --init or --advance", file=sys.stderr)
        sys.exit(1)

    if args.init:
        if not args.checks:
            print("Error: --checks required with --init", file=sys.stderr)
            sys.exit(1)

        result = init_state(
            checks_path=os.path.abspath(args.checks),
            audience=args.audience,
            state_path=os.path.abspath(args.state),
            question_file=os.path.abspath(args.question_file),
        )
    else:
        try:
            load_json(os.path.abspath(args.state))
        except json.JSONDecodeError:
            print(f"Error: corrupted state file: {args.state}", file=sys.stderr)
            sys.exit(1)

        result = advance_state(
            state_path=os.path.abspath(args.state),
            question_file=os.path.abspath(args.question_file),
            findings_file=os.path.abspath(args.findings_file) if args.findings_file else None,
            no_findings=args.no_findings,
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
