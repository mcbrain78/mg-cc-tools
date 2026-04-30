"""Persist confirmed user interfaces to config and scan-project.json.

Updates both the docs config and scan-project.json with the confirmed
user_interfaces array. Uses atomic writes to prevent corruption.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json


def main():
    parser = argparse.ArgumentParser(
        description="Persist confirmed interfaces to config and scan-project"
    )
    parser.add_argument(
        "--config", required=True, help="Path to .docs.config.json"
    )
    parser.add_argument(
        "--scan-project", required=True, help="Path to scan-project.json"
    )
    parser.add_argument(
        "--interfaces", required=True, help="JSON string of interfaces array"
    )
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    scan_project_path = os.path.abspath(args.scan_project)
    interfaces = json.loads(args.interfaces)

    # Persist to config
    config = load_json(config_path, default={})
    config["user_interfaces"] = interfaces
    save_json(config_path, config)

    # Update scan-project.json
    scan = load_json(scan_project_path)
    if scan is None:
        print("Error: scan-project.json not found", file=sys.stderr)
        sys.exit(1)
    scan["project_model"]["user_interfaces"] = interfaces
    save_json(scan_project_path, scan)

    print("Interfaces persisted to config and scan-project.json")


if __name__ == "__main__":
    main()
