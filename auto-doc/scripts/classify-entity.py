#!/usr/bin/env python3
"""Classify a dismissed entity into a permanent decision list.

Called by the post-wave classification agent to move a dismissed entity into
one of three permanent decision categories:
- not-entities: universally non-ref-worthy (generic terms, builtins, etc.)
- protected-entities: actually a project-specific ref that should not be dismissed
- covered: resolved by a declared dep/ext ref in this specific section.
  Recorded in covered-entities.json and consulted by clear-matched-entities
  on future audits to durably clear the entity.

When classifying to protected-entities AND finding-emission args are supplied,
also emits one `dangling-prose-reference` finding per section where the entity
was dismissed. This surfaces writer-side misses in the current audit rather
than deferring them to the next one.

Usage:
    python3 classify-entity.py \
        --entity NAME \
        --target {not-entities|protected-entities|covered} \
        --reason TEXT \
        [--not-entities-file FILE --protected-entities-file FILE]   # not-entities/protected
        [--covered-entities-file FILE --section SEC --document DOC \
         --audience AUD --covered-by REF --prose-verify-dir DIR]    # covered
        [--findings-file FILE --sections S1 S2 ...                  # protected only
         --suppress-file FILE]
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.coverage_validator import record_covered, validate_covered_by
from lib.json_io import load_json, save_json

VALID_TARGETS = ("not-entities", "protected-entities", "covered")

ADD_FINDING_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "add-verify-finding.py",
)


def _emit_protected_finding(entity, reason, findings_file, section,
                            audience, document, suppress_file=None):
    """Emit a dangling-prose-reference finding for a newly-protected entity.

    Called after successful classify-to-protected so the writer-side miss
    surfaces in the current audit instead of the next one.
    """
    description = (
        f"Prose mentions `{entity}` which was classified as project-specific: "
        f"{reason}. No declared ref covers it in this section."
    )
    suggestion = (
        f"{reason}. If an existing dep/ext ref in the section covers this "
        "entity, dismiss with --covered-by when the fix agent processes this "
        "finding. Otherwise declare a matching ref (see typed-refs-format.md)."
    )
    cmd = [
        sys.executable, ADD_FINDING_SCRIPT,
        "--findings-file", findings_file,
        "--document", document,
        "--section", section,
        "--audience", audience,
        "--check", "dangling-prose-reference",
        "--description", description,
        "--suggestion", suggestion,
        "--entity", entity,
        "--wave", "0",
    ]
    if suppress_file:
        cmd.extend(["--suppress-file", suppress_file])
    subprocess.run(cmd, capture_output=True, text=True)


def classify_covered(entity, reason, section, document, audience, covered_by,
                     covered_entities_file, prose_verify_dir):
    """Validate and record a coverage decision for this entity in this section.

    Returns 0 on success, 1 if covered-by validation failed.
    """
    valid, validation_reason = validate_covered_by(
        covered_by, section, prose_verify_dir,
    )
    if not valid:
        print(
            f"Cannot classify {entity} as covered: {validation_reason}",
            file=sys.stderr,
        )
        return 1
    added = record_covered(
        entity, section, audience, document, covered_by,
        covered_entities_file,
    )
    if added:
        print(
            f"Classified: {entity} → covered (by {covered_by}) in "
            f"{section}. Reason: {reason}",
            file=sys.stderr,
        )
    else:
        print(
            f"Already classified: {entity} → covered (by {covered_by}) in "
            f"{section}",
            file=sys.stderr,
        )
    return 0


def classify(entity, target, reason, not_entities_file, protected_entities_file,
             contextual=False, findings_file=None, sections=None,
             audience=None, document=None, suppress_file=None):
    """Classify entity into target list (deduped). Warn if in other list.

    Args:
        contextual: If True and target is not-entities, mark the entry with
            "contextual": true. Contextual entities are words that can be
            ref-worthy as identifiers but were used as plain prose.
        findings_file: When target is protected-entities, path to a
            findings-prose-*.json to append a dangling-prose-reference finding
            per section. Requires sections, audience, document.
        sections: List of section paths where the entity was dismissed.
        audience: Audience string for finding attribution.
        document: Document string for finding attribution.
        suppress_file: Optional path to suppressed-findings.json — suppressed
            findings are silently skipped at add-verify-finding.py.

    Returns:
        True if entity was added, False if already present (dedup).
    """
    if target == "not-entities":
        target_file = not_entities_file
        other_file = protected_entities_file
        other_name = "protected-entities"
    else:
        target_file = protected_entities_file
        other_file = not_entities_file
        other_name = "not-entities"

    # Conflict detection: warn if entity is in the OTHER list
    other_list = load_json(other_file, default=[])
    other_names = {
        e["name"] if isinstance(e, dict) else e for e in other_list
    }
    if entity in other_names:
        print(
            f"WARNING: {entity} already exists in {other_name}",
            file=sys.stderr,
        )

    # Add to target list (dedup by name)
    target_list = load_json(target_file, default=[])
    existing_names = {
        e["name"] if isinstance(e, dict) else e for e in target_list
    }
    if entity in existing_names:
        print(
            f"Already classified: {entity} in {target}",
            file=sys.stderr,
        )
        return False

    entry = {"name": entity, "reason": reason}
    if contextual and target == "not-entities":
        entry["contextual"] = True
    target_list.append(entry)
    save_json(target_file, target_list)
    print(
        f"Classified: {entity} → {target} ({reason})",
        file=sys.stderr,
    )

    # Auto-emit findings when newly protected — surfaces writer misses
    # in the current audit rather than deferring to the next.
    if (target == "protected-entities" and findings_file
            and sections and audience and document):
        for section in sections:
            _emit_protected_finding(
                entity, reason, findings_file, section,
                audience, document, suppress_file,
            )
        print(
            f"Filed {len(sections)} dangling-prose-reference finding(s) "
            f"for {entity}",
            file=sys.stderr,
        )

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Classify a dismissed entity into a permanent decision list",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to classify",
    )
    parser.add_argument(
        "--target", required=True, choices=VALID_TARGETS,
        help="Target: not-entities, protected-entities, or covered",
    )
    parser.add_argument(
        "--reason", required=True,
        help="Reason for classification",
    )
    parser.add_argument(
        "--not-entities-file",
        help="Path to not-entities JSON file (required for not-entities/protected targets)",
    )
    parser.add_argument(
        "--protected-entities-file",
        help="Path to protected-entities JSON file (required for not-entities/protected targets)",
    )
    parser.add_argument(
        "--contextual", action="store_true", default=False,
        help="Mark as contextual non-ref (word is ref-worthy as identifier but used as plain prose)",
    )
    # Finding-emission args — active only when target=protected-entities.
    parser.add_argument(
        "--findings-file",
        help="Findings JSON path; triggers auto-finding for protected target",
    )
    parser.add_argument(
        "--sections", nargs="+",
        help="Sections where the entity was dismissed (one finding per section)",
    )
    parser.add_argument("--audience", help="Audience name for the finding or coverage scope")
    parser.add_argument("--document", help="Document name for the finding or coverage scope")
    parser.add_argument(
        "--suppress-file",
        help="Path to suppressed-findings.json (passed through to add-verify-finding.py)",
    )
    # Coverage-target args — required when target=covered.
    parser.add_argument(
        "--section",
        help="Section path for coverage scope (required for covered target)",
    )
    parser.add_argument(
        "--covered-by",
        help="Ref identifier that covers this entity (required for covered target)",
    )
    parser.add_argument(
        "--covered-entities-file",
        help="Path to persistent covered-entities.json (required for covered target)",
    )
    parser.add_argument(
        "--prose-verify-dir",
        help="Path to prose-verify directory for this document/audience "
             "(required for covered target to validate --covered-by)",
    )

    args = parser.parse_args()

    if args.target == "covered":
        required = ["section", "document", "audience", "covered_by",
                    "covered_entities_file", "prose_verify_dir"]
        missing = [f"--{r.replace('_', '-')}" for r in required
                   if not getattr(args, r)]
        if missing:
            parser.error(
                f"--target covered requires: {', '.join(missing)}"
            )
        rc = classify_covered(
            entity=args.entity,
            reason=args.reason,
            section=args.section,
            document=args.document,
            audience=args.audience,
            covered_by=args.covered_by,
            covered_entities_file=args.covered_entities_file,
            prose_verify_dir=args.prose_verify_dir,
        )
        sys.exit(rc)

    # not-entities / protected-entities paths
    if not args.not_entities_file or not args.protected_entities_file:
        parser.error(
            f"--target {args.target} requires --not-entities-file and "
            "--protected-entities-file"
        )
    classify(
        entity=args.entity,
        target=args.target,
        reason=args.reason,
        not_entities_file=args.not_entities_file,
        protected_entities_file=args.protected_entities_file,
        contextual=args.contextual,
        findings_file=args.findings_file,
        sections=args.sections,
        audience=args.audience,
        document=args.document,
        suppress_file=args.suppress_file,
    )


if __name__ == "__main__":
    main()
