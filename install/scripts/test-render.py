#!/usr/bin/env python3
"""Test harness for render protocol reliability.

Produces the same content in three formats so we can A/B/C test which
pattern the LLM reproduces faithfully:
  --mode verbatim   (current <verbatim>...</verbatim> approach)
  --mode json       (single-line JSON with "display" field)
  --mode codeblock  (triple-backtick fenced code block)

Three test targets of increasing length:
  --content target-menu    (~10 lines)
  --content action-menu    (~9 lines)
  --content status-table   (~37 lines — this is the one that got dropped)
"""
import argparse
import io
import json
import os
import sys

# Reuse the real renderers from the install lib so content is identical.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import importlib.util

_lib_path = os.path.join(SCRIPT_DIR, "mg-install-lib.py")
_spec = importlib.util.spec_from_file_location("mg_install_lib", _lib_path)
assert _spec is not None and _spec.loader is not None
_lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lib)


def capture(fn, *args, **kwargs):
    """Run a renderer and capture its stdout as a list of lines."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn(*args, **kwargs)
    finally:
        sys.stdout = old
    raw = buf.getvalue().rstrip("\n").split("\n")
    # Strip whatever wrapper the renderer emitted (verbatim tags or code fence);
    # we re-wrap below according to --mode.
    if raw and raw[0].strip() in ("<verbatim>", "```"):
        raw = raw[1:]
    if raw and raw[-1].strip() in ("</verbatim>", "```"):
        raw = raw[:-1]
    return raw


def get_lines(content_kind, source_dir, scan_path):
    if content_kind == "target-menu":
        return capture(_lib.render_target_menu, source_dir)
    if content_kind == "action-menu":
        with open(scan_path) as f:
            scan_data = json.load(f)
        return capture(_lib.render_action_menu, scan_data)
    if content_kind == "status-table":
        with open(scan_path) as f:
            scan_data = json.load(f)
        return capture(_lib.render_status_table, scan_data)
    raise SystemExit(f"unknown content kind: {content_kind}")


def emit_verbatim(lines):
    print("<verbatim>")
    for line in lines:
        print(line)
    print("</verbatim>")


def emit_json(lines):
    payload = {"display": "\n".join(lines), "lines": len(lines)}
    print(json.dumps(payload))


def emit_codeblock(lines):
    print("```")
    for line in lines:
        print(line)
    print("```")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["verbatim", "json", "codeblock"], required=True)
    ap.add_argument(
        "--content",
        choices=["target-menu", "action-menu", "status-table"],
        default="target-menu",
    )
    ap.add_argument("--source", default=".")
    ap.add_argument(
        "--scan",
        default="/tmp/mg-install-mg-cc-tools/scan-status.json",
        help="Path to scan-status.json (needed for action-menu and status-table).",
    )
    args = ap.parse_args()

    lines = get_lines(args.content, args.source, args.scan)

    if args.mode == "verbatim":
        emit_verbatim(lines)
    elif args.mode == "json":
        emit_json(lines)
    else:
        emit_codeblock(lines)


if __name__ == "__main__":
    main()
