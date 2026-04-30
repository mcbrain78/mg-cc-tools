"""Write last_generated timestamp to docs-scan.json.

Records the current UTC time as the generation baseline for future
incremental scans. Uses atomic write to prevent corruption.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def main():
    parser = argparse.ArgumentParser(
        description="Set last_generated timestamp in docs-scan.json"
    )
    parser.add_argument(
        "--scan-file", required=True, help="Path to docs-scan.json"
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.scan_file)
    data = load_json(scan_path)
    if data is None:
        print("Error: scan file not found", file=sys.stderr)
        sys.exit(1)

    data["last_generated"] = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    save_json(scan_path, data)
    print(f"last_generated set to {data['last_generated']}")


if __name__ == "__main__":
    main()
