#!/usr/bin/env python3
"""Validate and append a single verify finding to docs-verify-findings.json.

Called by the verifier agent during each check. Supports two modes:

Inline mode (preferred — single Bash call, no temp file):
    python3 add-verify-finding.py \
        --findings-file .mg/docs/docs-verify-findings.json \
        --document "OPERATIONS" \
        --section "deployment" \
        --audience "devops" \
        --check "reference-integrity" \
        --description "..." \
        --suggestion "..."

File mode (legacy — requires writing a temp file first):
    python3 add-verify-finding.py \
        --input {TMP_DIR}/finding-001.json \
        --findings-file .mg/docs/docs-verify-findings.json

Required fields: document, section, audience, check, description, suggestion

Output adds computed fields:
    group_id (document/section) for grouping related findings

Atomic writes via lib/json_io.py. Zero external dependencies.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

REQUIRED_FIELDS = [
    "document", "section", "audience",
    "check", "description", "suggestion",
]

VALID_CHECKS = [
    # Mechanical checks (1-6)
    "reference-integrity", "cross-doc", "diataxis",
    "completeness", "example-validity", "link-integrity",
    # Editorial checks -- universal (7)
    "filler-content", "heading-content-mismatch",
    "dangling-prose-reference",
    "unexplained-code-block", "internal-contradiction",
    "malformed-table", "placeholder-content",
    # Editorial checks -- end-user (4)
    "end-user-jargon", "end-user-missing-expected-result",
    "end-user-implementation-leak", "end-user-missing-goal",
    # Editorial checks -- developer (3)
    "developer-abstract-architecture", "developer-missing-types",
    "developer-adr-missing-alternatives",
    # Editorial checks -- agent (3)
    "agent-ambiguous-constraint", "agent-missing-negative-examples",
    "agent-missing-consequences",
    # Editorial checks -- devops (3)
    "devops-missing-expected-output", "devops-missing-rollback",
    "devops-placeholder-in-command",
    # Editorial checks -- shared (1)
    "overview-missing-audience",
    # Fact-checker checks (verify pipeline restructure)
    "code-example-fact-check",
    "data-model-fact-check",
    "cross-doc-inconsistency",
    # Malformed ref checks (audit pipeline)
    "malformed-ref-unresolved",
]


def validate_finding(finding):
    """Validate a single finding dict.

    Returns:
        (True, None) if valid.
        (False, error_message) if invalid.
    """
    if not isinstance(finding, dict):
        return False, "Input is not a JSON object"

    for field in REQUIRED_FIELDS:
        if field not in finding:
            return False, f"Missing required field: {field}"

    # Normalize document name — strip .md extension for consistency
    doc = finding["document"]
    if doc.endswith(".md"):
        finding["document"] = doc[:-3]

    # Normalize audience — editorial agent uses singular, config uses plural
    _AUDIENCE_ALIASES = {
        "end-user": "end-users",
        "developer": "developers",
        "agent": "agents",
    }
    audience = finding["audience"]
    finding["audience"] = _AUDIENCE_ALIASES.get(audience, audience)

    if finding["check"] not in VALID_CHECKS:
        return False, f"Invalid check type: {finding['check']} (valid: {', '.join(VALID_CHECKS)})"

    return True, None


def save_rejected(input_path, reason):
    """Save rejected input for debugging.

    Writes a JSON object with the rejection reason and the original
    input content to input_path + ".rejected".
    """
    rejected_path = input_path + ".rejected"
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        content = "<file not readable>"

    rejected = {"reason": reason, "original_input": content}
    with open(rejected_path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Rejected input saved to {rejected_path}: {reason}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Validate and append a verify finding"
    )
    parser.add_argument(
        "--input", dest="input_file",
        help="Path to temp file with finding JSON (file mode)",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to docs-verify-findings.json",
    )
    # Inline args — preferred mode, no temp file needed
    parser.add_argument("--document", help="Document name")
    parser.add_argument("--section", help="Section slug")
    parser.add_argument("--audience", help="Target audience")
    parser.add_argument("--check", help="Check type")
    parser.add_argument("--description", help="Finding description")
    parser.add_argument("--suggestion", help="Suggested fix")

    args = parser.parse_args()
    findings_path = os.path.abspath(args.findings_file)

    # Determine input mode: inline args vs file
    inline_fields = {
        "document": args.document, "section": args.section,
        "audience": args.audience, "check": args.check,
        "description": args.description, "suggestion": args.suggestion,
    }
    has_inline = any(v is not None for v in inline_fields.values())

    if has_inline:
        # Inline mode — construct finding from CLI args
        missing = [k for k, v in inline_fields.items() if v is None]
        if missing:
            print(
                f"Error: inline mode requires all 6 fields. Missing: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(2)
        input_data = inline_fields
    elif args.input_file:
        # File mode — read from temp file
        input_path = os.path.abspath(args.input_file)
        try:
            input_data = load_json(input_path)
        except json.JSONDecodeError as e:
            save_rejected(input_path, f"Invalid JSON: {e}")
            sys.exit(1)

        if input_data is None:
            save_rejected(input_path, "Input file not found or empty")
            sys.exit(1)
    else:
        print(
            "Error: provide either --input <file> or inline args "
            "(--document, --section, --audience, --check, --description, --suggestion)",
            file=sys.stderr,
        )
        sys.exit(2)

    # Validate
    is_valid, error = validate_finding(input_data)
    if not is_valid:
        if args.input_file:
            save_rejected(os.path.abspath(args.input_file), error)
        else:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Compute group_id for grouping related findings
    input_data["group_id"] = f"{input_data['document']}/{input_data['section']}"

    # Load existing, append, save atomically
    findings = load_json(findings_path, default=[])
    findings.append(input_data)
    save_json(findings_path, findings)

    doc = input_data["document"]
    section = input_data["section"]
    check = input_data["check"]
    print(
        f"Added finding: {doc}/{section} ({check})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
