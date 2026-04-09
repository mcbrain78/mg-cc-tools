#!/usr/bin/env python3
"""Gateway wrapper for auditv2 resolution agents.

Provides a single entry point with subcommands so the resolution agent
never sees file paths to data files.  All paths are resolved internally
from a session config JSON written by the orchestrator.

Subcommands:
    next-section   — get the next section to process
    get-entities   — get uncleared entities for a section
    file-finding   — file a verification finding
    propagate      — propagate a finding to other sections
    dismiss        — dismiss an entity as not ref-worthy

Usage:
    audit-cmd.py --session SESSION next-section
    audit-cmd.py --session SESSION get-entities --section SEC
    audit-cmd.py --session SESSION file-finding --section SEC --check CHK \
        --description DESC --suggestion SUG
    audit-cmd.py --session SESSION propagate --entity ENT --section SEC \
        --suggestion SUG
    audit-cmd.py --session SESSION dismiss --entity ENT --section SEC
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _delegate(script_name, args):
    """Run a sibling script via subprocess and pass through stdout/stderr."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    result = subprocess.run(
        [sys.executable, script_path, *args],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return result.returncode


def cmd_next_section(session):
    findings_file = session["findings_file"]
    return _delegate("next-section.py", [
        "--state-file", f"{findings_file}.sectionctl",
        "--prose-verify-dir", session["prose_verify_dir"],
        "--sections-filter", session["sections_filter"],
    ])


def cmd_get_entities(session, args):
    return _delegate("get-section-entities.py", [
        "--uncleared-file", session["uncleared_file"],
        "--section", args.section,
    ])


def cmd_file_finding(session, args):
    cmd_args = [
        "--findings-file", session["findings_file"],
        "--document", session["document"],
        "--section", args.section,
        "--audience", session["audience"],
        "--check", args.check,
        "--description", args.description,
        "--suggestion", args.suggestion,
    ]
    if session.get("wave") is not None:
        cmd_args.extend(["--wave", str(session["wave"])])
    return _delegate("add-verify-finding.py", cmd_args)


def cmd_propagate(session, args):
    cmd_args = [
        "--entity", args.entity,
        "--section", args.section,
        "--findings-file", session["findings_file"],
        "--uncleared-file", session["uncleared_file"],
        "--document", session["document"],
        "--audience", session["audience"],
        "--suggestion", args.suggestion,
    ]
    if session.get("wave") is not None:
        cmd_args.extend(["--wave", str(session["wave"])])
    return _delegate("propagate-finding.py", cmd_args)


def cmd_dismiss(session, args):
    cmd_args = [
        "--entity", args.entity,
        "--section", args.section,
        "--uncleared-file", session["uncleared_file"],
        "--dismissed-this-run-file", session["dismissed_this_run_file"],
        "--audience", session["audience"],
        "--document", session["document"],
    ]
    if session.get("protected_entities_file"):
        cmd_args.extend([
            "--protected-entities-file", session["protected_entities_file"],
        ])
    return _delegate("dismiss-entity.py", cmd_args)


def main():
    parser = argparse.ArgumentParser(
        description="Gateway wrapper for auditv2 resolution agents",
    )
    parser.add_argument(
        "--session", required=True,
        help="Path to session config JSON",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    # next-section
    subparsers.add_parser("next-section", help="Get next section to process")

    # get-entities
    p_entities = subparsers.add_parser(
        "get-entities", help="Get entities for a section",
    )
    p_entities.add_argument("--section", required=True)

    # file-finding
    p_finding = subparsers.add_parser(
        "file-finding", help="File a verification finding",
    )
    p_finding.add_argument("--section", required=True)
    p_finding.add_argument("--check", required=True)
    p_finding.add_argument("--description", required=True)
    p_finding.add_argument("--suggestion", required=True)

    # propagate
    p_propagate = subparsers.add_parser(
        "propagate", help="Propagate finding to other sections",
    )
    p_propagate.add_argument("--entity", required=True)
    p_propagate.add_argument("--section", required=True)
    p_propagate.add_argument("--suggestion", required=True)

    # dismiss
    p_dismiss = subparsers.add_parser(
        "dismiss", help="Dismiss entity as not ref-worthy",
    )
    p_dismiss.add_argument("--entity", required=True)
    p_dismiss.add_argument("--section", required=True)

    args = parser.parse_args()

    # Load session config
    session = load_json(args.session)
    if session is None:
        print(
            f"Error: session config not found: {args.session}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Dispatch
    handlers = {
        "next-section": lambda: cmd_next_section(session),
        "get-entities": lambda: cmd_get_entities(session, args),
        "file-finding": lambda: cmd_file_finding(session, args),
        "propagate": lambda: cmd_propagate(session, args),
        "dismiss": lambda: cmd_dismiss(session, args),
    }
    rc = handlers[args.command]()
    sys.exit(rc)


if __name__ == "__main__":
    main()
