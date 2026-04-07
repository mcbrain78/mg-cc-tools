#!/usr/bin/env python3
"""Return uncleared entities for a specific section.

Called by the resolution agent before processing each section to get
fresh entity data (reflecting any propagation from earlier sections).

Usage:
    python3 get-section-entities.py \
        --uncleared-file FILE \
        --section SECTION

Output (JSON to stdout):
    {"entities": ["OperationalError", "pg_settings"], "count": 2}
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json


def get_section_entities(uncleared_file, section):
    """Get entity names for a specific section from the uncleared file.

    Returns:
        Dict with 'entities' (list of names) and 'count' (int).
    """
    uncleared = load_json(uncleared_file, default=[])
    names = [e["name"] for e in uncleared if e["section"] == section]
    return {"entities": names, "count": len(names)}


def main():
    parser = argparse.ArgumentParser(
        description="Return uncleared entities for a specific section",
    )
    parser.add_argument(
        "--uncleared-file", required=True,
        help="Path to uncleared entities JSON file",
    )
    parser.add_argument(
        "--section", required=True,
        help="Section path to filter by",
    )
    args = parser.parse_args()
    result = get_section_entities(args.uncleared_file, args.section)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
