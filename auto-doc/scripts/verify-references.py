#!/usr/bin/env python3
"""Deterministic reference integrity checker for documentation manifests.

Replaces the LLM-driven Check 1 in the verify pipeline. Reads structured
reference manifests from .mg/docs/reference-manifests/, verifies that
file paths exist and symbols are defined in the referenced files using
ast.parse().

Usage:
    python3 verify-references.py \
        --manifests-dir {project_root}/.mg/docs/reference-manifests \
        --project-root {project_root} \
        --scan-file {project_root}/.mg/docs/docs-scan.json \
        --findings-file {findings_file}

Appends findings to --findings-file atomically. Exit 0 always
(findings are data, not errors).

Zero external dependencies -- stdlib only.
"""

import argparse
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json
from lib.symbols import extract_function_signatures, extract_python_symbols


def build_file_cache(file_paths, project_root):
    """Build a cache of file existence, symbol sets, and function signatures.

    Args:
        file_paths: Set of relative file paths to check.
        project_root: Absolute path to resolve relative paths against.

    Returns:
        (cache, signature_cache, parse_errors) where:
        - cache: dict mapping relative path -> set of symbols (or None if missing)
        - signature_cache: dict mapping relative path -> dict of func_name -> [param_names]
        - parse_errors: list of (path, error_message) for .py files with SyntaxError
    """
    cache = {}
    signature_cache = {}
    parse_errors = []

    for rel_path in file_paths:
        abs_path = os.path.join(project_root, rel_path)

        if os.path.isdir(abs_path):
            # Recurse into directory, parse all .py files, union their symbols
            dir_symbols = set()
            dir_signatures = {}
            for dirpath, _dirnames, filenames in os.walk(abs_path):
                for fname in filenames:
                    if fname.endswith(".py"):
                        py_abs = os.path.join(dirpath, fname)
                        py_rel = os.path.relpath(py_abs, project_root)
                        try:
                            with open(py_abs, "r", encoding="utf-8") as f:
                                source = f.read()
                        except OSError:
                            parse_errors.append((py_rel, "Could not read file"))
                            continue

                        symbols = extract_python_symbols(source)
                        if not symbols:
                            try:
                                ast.parse(source)
                            except SyntaxError as e:
                                parse_errors.append((py_rel, str(e)))
                        else:
                            dir_symbols.update(symbols)
                            dir_signatures.update(extract_function_signatures(source))
            cache[rel_path] = dir_symbols
            signature_cache[rel_path] = dir_signatures
        elif not os.path.exists(abs_path):
            cache[rel_path] = None
        elif rel_path.endswith(".py"):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    source = f.read()
            except OSError:
                cache[rel_path] = set()
                parse_errors.append((rel_path, "Could not read file"))
                continue

            symbols = extract_python_symbols(source)
            if not symbols:
                # Check if it was a SyntaxError (vs just empty file)
                try:
                    ast.parse(source)
                    cache[rel_path] = set()
                except SyntaxError as e:
                    cache[rel_path] = set()
                    parse_errors.append((rel_path, str(e)))
            else:
                cache[rel_path] = symbols
                signature_cache[rel_path] = extract_function_signatures(source)
        else:
            # Non-.py file: existence confirmed, no symbol extraction
            cache[rel_path] = set()

    return cache, signature_cache, parse_errors


def _make_finding(document, section, audience, description, suggestion):
    """Create a finding dict with all required fields plus group_id."""
    return {
        "document": document,
        "section": section,
        "audience": audience,
        "check": "reference-integrity",
        "description": description,
        "suggestion": suggestion,
        "group_id": f"{document}/{section}",
    }


def check_manifest(manifest, file_cache, signature_cache, source_material_index):
    """Check a single manifest for reference integrity issues.

    Args:
        manifest: Parsed manifest dict with 'audience' and 'documents'.
        file_cache: Dict mapping relative path -> symbol set or None.
        signature_cache: Dict mapping relative path -> dict of func_name -> [param_names].
        source_material_index: Dict mapping "doc/section" -> {"source_files": [...]}.

    Returns:
        List of finding dicts.
    """
    findings = []
    audience = manifest.get("audience", "unknown")
    documents = manifest.get("documents", {})

    for doc_name, sections in documents.items():
        for section_name, entry in sections.items():
            if section_name == "_written_sections":
                continue

            entry_file_paths = entry.get("file_paths", [])
            entry_symbols = entry.get("symbols", [])

            # File path verification — collect all missing, emit one finding
            missing_files = []
            for path in entry_file_paths:
                if file_cache.get(path) is None:
                    missing_files.append(path)

            if missing_files:
                paths_str = ", ".join(missing_files)
                findings.append(_make_finding(
                    document=doc_name,
                    section=section_name,
                    audience=audience,
                    description=f"{len(missing_files)} missing file(s): {paths_str}",
                    suggestion="Update references to current paths or remove from documentation",
                ))

            # Symbol verification — scan source_files + manifest file_paths
            scan_key = f"{doc_name}/{section_name}"
            scan_entry = source_material_index.get(scan_key, {})
            scan_paths = scan_entry.get("source_files", [])
            # Merge scan source_files with manifest file_paths (dedup, order-preserving)
            check_paths = list(dict.fromkeys(scan_paths + entry_file_paths))

            if entry_symbols:
                # Collect symbol sets from source files (skip missing)
                symbol_sets = []
                for path in check_paths:
                    cached = file_cache.get(path)
                    if cached is not None:
                        symbol_sets.append((path, cached))

                # No source files to check symbols against → skip
                if not symbol_sets:
                    pass
                # All symbol sets empty (non-py files or parse errors) → skip
                elif all(len(s) == 0 for _, s in symbol_sets):
                    pass
                else:
                    all_symbols = set()
                    for _, s in symbol_sets:
                        all_symbols.update(s)

                    # Collect all undefined symbols, emit one finding
                    undefined_symbols = []
                    for symbol in entry_symbols:
                        if symbol not in all_symbols:
                            undefined_symbols.append(symbol)

                    if undefined_symbols:
                        file_list = ", ".join(p for p, _ in symbol_sets)
                        syms_str = ", ".join(undefined_symbols)
                        findings.append(_make_finding(
                            document=doc_name,
                            section=section_name,
                            audience=audience,
                            description=f"{len(undefined_symbols)} undefined symbol(s): {syms_str} (checked in {file_list})",
                            suggestion="Re-generate this section to pick up current symbol names",
                        ))

            # Calls verification — check kwargs against actual function signatures
            entry_calls = entry.get("calls", [])
            if entry_calls:
                # Build merged signature dict from all source files
                all_signatures = {}
                for path in check_paths:
                    sigs = signature_cache.get(path, {})
                    all_signatures.update(sigs)

                for call in entry_calls:
                    symbol = call.get("symbol", "")
                    kwargs = call.get("kwargs", [])
                    if not symbol or not kwargs:
                        continue

                    actual_params = all_signatures.get(symbol)
                    if actual_params is None:
                        # Function not found in signatures — skip gracefully
                        continue

                    bad_kwargs = [k for k in kwargs if k not in actual_params]
                    if bad_kwargs:
                        bad_str = ", ".join(bad_kwargs)
                        actual_str = ", ".join(actual_params)
                        findings.append(_make_finding(
                            document=doc_name,
                            section=section_name,
                            audience=audience,
                            description=(
                                f"Call to {symbol}() uses invalid keyword(s): {bad_str}. "
                                f"Actual parameters: {actual_str}"
                            ),
                            suggestion="Re-generate this section to pick up current function signature",
                        ))

    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Check reference integrity in documentation manifests"
    )
    parser.add_argument(
        "--manifests-dir", required=True,
        help="Path to directory containing reference manifest JSON files",
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Absolute path to project root for resolving file paths",
    )
    parser.add_argument(
        "--scan-file", required=True,
        help="Path to docs-scan.json — source_material_index used for symbol verification",
    )
    parser.add_argument(
        "--findings-file", required=True,
        help="Path to findings JSON file to append results to",
    )

    args = parser.parse_args()
    manifests_dir = os.path.abspath(args.manifests_dir)
    project_root = os.path.abspath(args.project_root)
    findings_file = os.path.abspath(args.findings_file)

    # If manifests dir missing or empty, exit cleanly
    if not os.path.isdir(manifests_dir):
        print("No manifests directory found, skipping reference integrity check", file=sys.stderr)
        sys.exit(0)

    manifest_files = [f for f in os.listdir(manifests_dir) if f.endswith(".json")]
    if not manifest_files:
        print("No manifest files found, skipping reference integrity check", file=sys.stderr)
        sys.exit(0)

    # Load scan file for source_material_index
    scan_data = load_json(os.path.abspath(args.scan_file))
    if scan_data is None:
        print("Error: scan file not found or empty", file=sys.stderr)
        sys.exit(1)
    source_material_index = scan_data.get("source_material_index", {})

    # Load all manifests
    manifests = []
    for fname in sorted(manifest_files):
        path = os.path.join(manifests_dir, fname)
        data = load_json(path)
        if data is not None:
            manifests.append(data)

    # Collect all unique file paths across manifests and scan
    all_file_paths = set()
    for manifest in manifests:
        for sections in manifest.get("documents", {}).values():
            for section_name, entry in sections.items():
                if section_name == "_written_sections":
                    continue
                for fp in entry.get("file_paths", []):
                    all_file_paths.add(fp)
    for entry in source_material_index.values():
        for fp in entry.get("source_files", []):
            all_file_paths.add(fp)

    # Build file cache once
    file_cache, signature_cache, parse_errors = build_file_cache(all_file_paths, project_root)

    # Generate findings for parse errors
    new_findings = []
    for path, error in parse_errors:
        new_findings.append(_make_finding(
            document="(verify-references)",
            section="file-cache",
            audience="all",
            description=f"SyntaxError in {path}: {error}",
            suggestion="Fix the syntax error or accept that symbol verification is skipped for this file",
        ))

    # Check each manifest
    for manifest in manifests:
        new_findings.extend(check_manifest(manifest, file_cache, signature_cache, source_material_index))

    # Load existing findings, extend, save atomically
    existing = load_json(findings_file, default=[])
    existing.extend(new_findings)
    save_json(findings_file, existing)

    # Summary to stderr
    n = len(new_findings)
    print(
        f"Reference integrity: {n} findings",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
