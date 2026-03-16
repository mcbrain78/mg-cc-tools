#!/usr/bin/env python3
"""Check file path and symbol references in documentation.

Scans markdown documentation files for references to file paths and code
symbols, then verifies they exist in the project codebase. Reports broken
references with file, line number, and type.

Used by the verify pipeline step to catch stale or incorrect documentation
references.

Zero external dependencies -- stdlib only.
"""

import argparse
import json
import os
import re
import sys

# Allow importing lib modules when run from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.json_io import save_json


# ── Constants ────────────────────────────────────────────────────────────────

# File extensions that indicate a reference is likely a file path
FILE_EXTENSIONS = {
    ".py", ".ts", ".js", ".md", ".json", ".yaml", ".yml",
    ".sh", ".toml", ".cfg", ".env", ".tsx", ".jsx", ".css",
    ".html", ".sql", ".go", ".rs", ".rb", ".java", ".c",
    ".h", ".cpp", ".hpp",
}

# Pattern for backtick-wrapped content
BACKTICK_PATTERN = re.compile(r"`([^`]+)`")

# Pattern for ClassName.method_name() or module.function() style references
SYMBOL_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:\.[a-z_][A-Za-z0-9_]*)?)\s*\(")


# ── Path Detection ───────────────────────────────────────────────────────────


def _looks_like_file_path(text):
    """Check if a string looks like a file path reference.

    Returns True if the text contains a path separator or ends with
    a known file extension.
    """
    # Skip URLs
    if text.startswith("http://") or text.startswith("https://"):
        return False
    # Skip anchors
    if text.startswith("#"):
        return False
    # Skip shell commands and common non-path patterns
    if text.startswith("-") or text.startswith("$"):
        return False

    # Contains path separator -> likely a path
    if "/" in text:
        _, ext = os.path.splitext(text)
        if ext.lower() in FILE_EXTENSIONS:
            return True
        # Path with slash but no extension could be a directory
        # Only consider if it doesn't look like code
        if not any(c in text for c in ("(", ")", "=", " ", "{", "}")):
            return True

    # No slash but has a file extension
    _, ext = os.path.splitext(text)
    if ext.lower() in FILE_EXTENSIONS:
        return True

    return False


def _extract_file_paths_from_line(line):
    """Extract file path references from a line of markdown.

    Looks for backtick-wrapped paths and bare path-like tokens.
    Returns list of (reference_text, is_from_backtick) tuples.
    """
    paths = []
    for match in BACKTICK_PATTERN.finditer(line):
        text = match.group(1).strip()
        if _looks_like_file_path(text):
            paths.append(text)
    return paths


def _extract_file_paths_from_code_block_line(line):
    """Extract file path references from a code block line.

    In code blocks, look for file-path-like tokens without backticks.
    """
    paths = []
    # Check backtick patterns first (rare in code blocks but possible)
    for match in BACKTICK_PATTERN.finditer(line):
        text = match.group(1).strip()
        if _looks_like_file_path(text):
            paths.append(text)

    # Also scan for bare path-like tokens in the line
    # Split by whitespace and check each token
    tokens = line.split()
    for token in tokens:
        # Clean up common surrounding chars
        cleaned = token.strip("\"',:;()[]{}#")
        if cleaned and _looks_like_file_path(cleaned):
            # Avoid duplicates from backtick extraction
            if cleaned not in paths:
                paths.append(cleaned)

    return paths


# ── Symbol Detection ─────────────────────────────────────────────────────────


def _extract_symbols_from_code_block(lines, start_line):
    """Extract symbol references from code block lines.

    Looks for ClassName() or ClassName.method() patterns.
    Returns list of (symbol_name, line_number) tuples.
    """
    symbols = []
    for i, line in enumerate(lines):
        for match in SYMBOL_PATTERN.finditer(line):
            symbol = match.group(1)
            # Skip common builtins / language constructs
            builtins = {
                "True", "False", "None", "Exception", "TypeError",
                "ValueError", "KeyError", "RuntimeError", "OSError",
                "IOError", "FileNotFoundError", "ImportError",
                "AttributeError", "IndexError", "StopIteration",
                "NotImplementedError", "PermissionError",
                "If", "For", "While", "Return", "Class", "Def",
                "Print", "String", "Integer", "Float", "Dict",
                "List", "Set", "Tuple", "Type", "Any", "Optional",
                "Union", "Callable",
            }
            if symbol.split(".")[0] in builtins:
                continue
            symbols.append((symbol, start_line + i))
    return symbols


def _symbol_exists_in_project(symbol, project_root):
    """Check if a symbol name exists in any Python source file.

    Performs a simple text search -- not full AST analysis.
    Looks for class or function definitions matching the symbol.
    """
    # Split "ClassName.method" into parts
    parts = symbol.split(".")
    class_name = parts[0]

    # Search Python files for the class/function definition
    for dirpath, _dirnames, filenames in os.walk(project_root):
        # Skip hidden dirs, __pycache__, node_modules, etc.
        basename = os.path.basename(dirpath)
        if basename.startswith(".") or basename in ("__pycache__", "node_modules", ".git"):
            continue

        for fname in filenames:
            if not fname.endswith((".py", ".ts", ".js")):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                content = open(fpath, "r", encoding="utf-8", errors="replace").read()
            except (OSError, IOError):
                continue

            # Check for class definition
            if re.search(rf"\bclass\s+{re.escape(class_name)}\b", content):
                # If we have a method part, check for that too
                if len(parts) > 1:
                    method_name = parts[1]
                    if re.search(rf"\bdef\s+{re.escape(method_name)}\b", content):
                        return True
                else:
                    return True

            # Also check for standalone function
            if re.search(rf"\bdef\s+{re.escape(class_name)}\b", content):
                return True

    return False


# ── Main Check Logic ─────────────────────────────────────────────────────────


def check_docs(docs_dir, project_root):
    """Check all markdown docs in docs_dir for broken references.

    Args:
        docs_dir: Directory containing markdown documentation files.
        project_root: Project root directory for resolving file paths.

    Returns:
        List of issue dicts, each with: file, line, reference, type,
        status ("broken" or "valid"), message.
    """
    issues = []

    if not os.path.isdir(docs_dir):
        return issues

    for dirpath, _dirnames, filenames in os.walk(docs_dir):
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dirpath, fname)
            file_issues = _check_file(fpath, project_root)
            issues.extend(file_issues)

    return issues


def _check_file(fpath, project_root):
    """Check a single markdown file for broken references."""
    issues = []

    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, IOError):
        return issues

    in_code_block = False
    code_block_lines = []
    code_block_start = 0

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track code block boundaries
        if stripped.startswith("```"):
            if in_code_block:
                # End of code block -- process accumulated lines for symbols
                symbols = _extract_symbols_from_code_block(
                    code_block_lines, code_block_start
                )
                for symbol, sym_line in symbols:
                    exists = _symbol_exists_in_project(symbol, project_root)
                    issues.append({
                        "file": fpath,
                        "line": sym_line,
                        "reference": symbol,
                        "type": "symbol",
                        "status": "valid" if exists else "broken",
                        "message": (
                            f"Symbol '{symbol}' found in project"
                            if exists
                            else f"Symbol '{symbol}' not found in any source file"
                        ),
                    })
                code_block_lines = []
                in_code_block = False
            else:
                in_code_block = True
                code_block_start = line_num + 1  # next line is first content line
            continue

        if in_code_block:
            code_block_lines.append(line)
            # Check file paths in code block lines
            paths = _extract_file_paths_from_code_block_line(line)
            for ref in paths:
                resolved = os.path.join(project_root, ref)
                exists = os.path.isfile(resolved) or os.path.isdir(resolved)
                issues.append({
                    "file": fpath,
                    "line": line_num,
                    "reference": ref,
                    "type": "file_path",
                    "status": "valid" if exists else "broken",
                    "message": (
                        f"Path '{ref}' exists"
                        if exists
                        else f"Path '{ref}' not found in project"
                    ),
                })
        else:
            # Check file paths in regular markdown lines
            paths = _extract_file_paths_from_line(line)
            for ref in paths:
                resolved = os.path.join(project_root, ref)
                exists = os.path.isfile(resolved) or os.path.isdir(resolved)
                issues.append({
                    "file": fpath,
                    "line": line_num,
                    "reference": ref,
                    "type": "file_path",
                    "status": "valid" if exists else "broken",
                    "message": (
                        f"Path '{ref}' exists"
                        if exists
                        else f"Path '{ref}' not found in project"
                    ),
                })

    return issues


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Check file path and symbol references in documentation."
    )
    parser.add_argument(
        "--docs-dir",
        required=True,
        help="Directory containing markdown docs to check.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Project root for resolving file paths.",
    )
    parser.add_argument(
        "--output",
        help="Path to write JSON results. If omitted, prints to stdout.",
    )

    args = parser.parse_args()

    issues = check_docs(
        docs_dir=args.docs_dir,
        project_root=args.project_root,
    )

    # Write output
    if args.output:
        save_json(args.output, issues)
    else:
        json.dump(issues, sys.stdout, indent=2)
        sys.stdout.write("\n")

    # Print summary to stderr
    total = len(issues)
    broken = sum(1 for i in issues if i["status"] == "broken")
    # Count unique doc files
    doc_files = set(i["file"] for i in issues) if issues else set()
    # Also count docs that had no issues
    if os.path.isdir(args.docs_dir):
        for dirpath, _, filenames in os.walk(args.docs_dir):
            for fname in filenames:
                if fname.endswith(".md"):
                    doc_files.add(os.path.join(dirpath, fname))

    print(
        f"Checked {total} references in {len(doc_files)} files. {broken} broken.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
