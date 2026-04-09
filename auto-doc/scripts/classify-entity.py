#!/usr/bin/env python3
"""Classify a dismissed entity into permanent not-entities or protected-entities.

Called by the post-wave classification agent to move a dismissed entity
from the per-run dismissals list into one of two permanent lists:
- not-entities: universally non-ref-worthy (generic terms, builtins, etc.)
- protected-entities: actually a project-specific ref that should not be dismissed

Usage:
    python3 classify-entity.py \
        --entity NAME \
        --target {not-entities|protected-entities} \
        --reason TEXT \
        --not-entities-file FILE \
        --protected-entities-file FILE
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

VALID_TARGETS = ("not-entities", "protected-entities")


def classify(entity, target, reason, not_entities_file, protected_entities_file):
    """Classify entity into target list (deduped). Warn if in other list.

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

    target_list.append({"name": entity, "reason": reason})
    save_json(target_file, target_list)
    print(
        f"Classified: {entity} → {target} ({reason})",
        file=sys.stderr,
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Classify a dismissed entity into not-entities or protected-entities",
    )
    parser.add_argument(
        "--entity", required=True,
        help="Entity name to classify",
    )
    parser.add_argument(
        "--target", required=True, choices=VALID_TARGETS,
        help="Target list: not-entities or protected-entities",
    )
    parser.add_argument(
        "--reason", required=True,
        help="Reason for classification",
    )
    parser.add_argument(
        "--not-entities-file", required=True,
        help="Path to not-entities JSON file",
    )
    parser.add_argument(
        "--protected-entities-file", required=True,
        help="Path to protected-entities JSON file",
    )

    args = parser.parse_args()
    classify(
        entity=args.entity,
        target=args.target,
        reason=args.reason,
        not_entities_file=args.not_entities_file,
        protected_entities_file=args.protected_entities_file,
    )


if __name__ == "__main__":
    main()
