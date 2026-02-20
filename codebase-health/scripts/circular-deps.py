#!/usr/bin/env python3
"""Circular dependency analysis for codebase-health pipeline.

Builds a directed import graph from source files, then detects:
- Import cycles (via Tarjan's SCC algorithm)
- God modules (disproportionately high in-degree)
- Layering violations (imports that cross architectural boundaries)

Usage:
    python3 circular-deps.py --root <path> --output <path> [--ignore-file <path>]

Zero external dependencies — stdlib only.
"""

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add parent directory to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ignore import load_ignore_patterns, walk_source_files
from lib.imports import (
    Import,
    detect_language,
    extract_imports,
    is_internal_import,
    resolve_import_to_file,
)

# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------


def build_import_graph(
    root: str, ignore_patterns: List[str]
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], List[dict]]:
    """Build a directed graph of internal imports.

    Returns:
        (forward_graph, reverse_graph, errors)
        - forward_graph: {file -> set of files it imports}
        - reverse_graph: {file -> set of files that import it}
        - errors: list of {file, error} dicts for unparseable files
    """
    forward: Dict[str, Set[str]] = defaultdict(set)
    reverse: Dict[str, Set[str]] = defaultdict(set)
    errors: List[dict] = []

    for fpath in walk_source_files(root, ignore_patterns):
        lang = detect_language(fpath)
        if lang is None:
            continue

        # Ensure node exists even if it has no imports
        rel = os.path.relpath(fpath, root)
        if rel not in forward:
            forward[rel] = set()

        try:
            imports = extract_imports(fpath, lang)
        except Exception as e:
            errors.append({"file": rel, "error": str(e)})
            continue

        for imp in imports:
            if imp.is_type_only:
                continue  # Skip type-only imports for cycle detection
            if not is_internal_import(imp.target, root, fpath, lang):
                continue

            resolved = resolve_import_to_file(imp.target, fpath, root, lang)
            if resolved is None:
                continue

            target_rel = os.path.relpath(resolved, root)
            forward[rel].add(target_rel)
            reverse[target_rel].add(rel)

            # Ensure target node exists
            if target_rel not in forward:
                forward[target_rel] = set()

    return dict(forward), dict(reverse), errors


# ---------------------------------------------------------------------------
# Tarjan's Strongly Connected Components
# ---------------------------------------------------------------------------


def tarjan_scc(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Find all strongly connected components using Tarjan's algorithm.

    Returns list of SCCs with more than one node (i.e., actual cycles).
    """
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    sccs: List[List[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in index:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif neighbor in on_stack:
                lowlink[node] = min(lowlink[node], index[neighbor])

        if lowlink[node] == index[node]:
            scc: List[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    # Use iterative deepening to avoid recursion limits on large codebases
    sys.setrecursionlimit(max(10000, len(graph) * 2))

    for node in graph:
        if node not in index:
            strongconnect(node)

    return sccs


def extract_cycles_from_scc(scc: List[str], graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Extract individual cycle paths from an SCC.

    For small SCCs (<=5), finds all elementary cycles.
    For larger ones, returns the SCC as a single cycle representation.
    """
    scc_set = set(scc)

    if len(scc) <= 5:
        # For small SCCs, find shortest cycle through BFS from each node
        cycles: List[List[str]] = []
        seen_cycle_sets: List[frozenset] = []

        for start in scc:
            # BFS to find shortest cycle back to start
            queue = [(start, [start])]
            visited = {start}
            found = False

            while queue and not found:
                current, path = queue.pop(0)
                for neighbor in graph.get(current, set()):
                    if neighbor == start and len(path) > 1:
                        cycle = path
                        cycle_key = frozenset(cycle)
                        if cycle_key not in seen_cycle_sets:
                            seen_cycle_sets.append(cycle_key)
                            cycles.append(cycle)
                        found = True
                        break
                    if neighbor in scc_set and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor]))

        return cycles if cycles else [scc]
    else:
        return [scc]


# ---------------------------------------------------------------------------
# God module detection
# ---------------------------------------------------------------------------


def detect_god_modules(
    reverse_graph: Dict[str, Set[str]], threshold_multiplier: float = 3.0, min_importers: int = 5
) -> List[dict]:
    """Detect modules with disproportionately many importers.

    A god module has in-degree > threshold_multiplier * median AND > min_importers.
    """
    in_degrees = {node: len(importers) for node, importers in reverse_graph.items()}

    if not in_degrees:
        return []

    values = list(in_degrees.values())
    if not values:
        return []

    median_degree = statistics.median(values) if values else 0
    threshold = max(median_degree * threshold_multiplier, min_importers)

    god_modules = []
    for module, degree in sorted(in_degrees.items(), key=lambda x: -x[1]):
        if degree > threshold:
            god_modules.append({
                "file": module,
                "importer_count": degree,
                "importers": sorted(reverse_graph[module]),
                "median_in_degree": round(median_degree, 1),
                "threshold": round(threshold, 1),
            })

    return god_modules


# ---------------------------------------------------------------------------
# Layering violation detection
# ---------------------------------------------------------------------------

# Heuristic layer mapping from directory names
# Lower number = lower layer (should not import higher layers)
LAYER_KEYWORDS: Dict[str, int] = {
    "utils": 0, "util": 0, "helpers": 0, "helper": 0, "lib": 0, "common": 0, "shared": 0,
    "core": 1, "models": 1, "types": 1, "schemas": 1, "entities": 1,
    "services": 2, "tools": 2, "providers": 2, "repositories": 2, "repo": 2,
    "agents": 3, "handlers": 3, "controllers": 3, "views": 3, "routes": 3,
    "orchestration": 4, "pipeline": 4, "workflows": 4, "app": 4, "commands": 4,
    "config": 0, "settings": 0, "constants": 0,
    "tests": -1, "test": -1, "__tests__": -1, "spec": -1,
}


def _infer_layer(file_path: str) -> Optional[int]:
    """Infer the architectural layer of a file from its directory path."""
    parts = Path(file_path).parts
    for part in parts:
        lower = part.lower()
        if lower in LAYER_KEYWORDS:
            return LAYER_KEYWORDS[lower]
    return None


def detect_layering_violations(graph: Dict[str, Set[str]]) -> List[dict]:
    """Detect imports that violate the expected layering hierarchy.

    A violation occurs when a lower layer imports from a higher layer.
    """
    violations = []

    for source, targets in graph.items():
        source_layer = _infer_layer(source)
        if source_layer is None or source_layer == -1:  # Skip unknown/test layers
            continue

        for target in targets:
            target_layer = _infer_layer(target)
            if target_layer is None or target_layer == -1:
                continue

            if source_layer < target_layer:
                violations.append({
                    "source": source,
                    "source_layer": source_layer,
                    "target": target,
                    "target_layer": target_layer,
                    "description": (
                        f"Lower layer '{_layer_name(source)}' imports from "
                        f"higher layer '{_layer_name(target)}'"
                    ),
                })

    return violations


def _layer_name(file_path: str) -> str:
    """Get a human-readable layer name for a file."""
    parts = Path(file_path).parts
    for part in parts:
        lower = part.lower()
        if lower in LAYER_KEYWORDS:
            return part
    return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def analyze(root: str, ignore_file: Optional[str] = None) -> dict:
    """Run full circular dependency analysis.

    Returns structured JSON-serializable dict.
    """
    patterns = load_ignore_patterns(ignore_file)
    forward_graph, reverse_graph, errors = build_import_graph(root, patterns)

    # Cycle detection
    sccs = tarjan_scc(forward_graph)
    cycles = []
    for scc in sccs:
        for cycle_path in extract_cycles_from_scc(scc, forward_graph):
            cycles.append({
                "files": cycle_path,
                "length": len(cycle_path),
            })

    # God modules
    god_modules = detect_god_modules(reverse_graph)

    # Layering violations
    layering_violations = detect_layering_violations(forward_graph)

    # Graph stats
    total_files = len(forward_graph)
    total_edges = sum(len(targets) for targets in forward_graph.values())

    return {
        "graph_stats": {
            "total_files": total_files,
            "total_edges": total_edges,
            "avg_imports_per_file": round(total_edges / total_files, 1) if total_files else 0,
        },
        "cycles": cycles,
        "god_modules": god_modules,
        "layering_violations": layering_violations,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze circular dependencies in a codebase"
    )
    parser.add_argument(
        "--root", required=True, help="Project root directory"
    )
    parser.add_argument(
        "--output", required=True, help="Output JSON file path"
    )
    parser.add_argument(
        "--ignore-file", default=None, help="Path to .health-ignore file"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Auto-detect .health-ignore if not specified (lives in .health-scan/)
    if args.ignore_file is None:
        default_ignore = os.path.join(root, ".health-scan", ".health-ignore")
        if os.path.isfile(default_ignore):
            args.ignore_file = default_ignore

    result = analyze(root, args.ignore_file)

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Print summary to stderr
    print(f"Scanned {result['graph_stats']['total_files']} files, "
          f"{result['graph_stats']['total_edges']} import edges", file=sys.stderr)
    print(f"Found {len(result['cycles'])} cycles, "
          f"{len(result['god_modules'])} god modules, "
          f"{len(result['layering_violations'])} layering violations", file=sys.stderr)
    if result['errors']:
        print(f"Warnings: {len(result['errors'])} files had parse errors", file=sys.stderr)


if __name__ == "__main__":
    main()
