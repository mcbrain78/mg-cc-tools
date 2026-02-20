"""Shared ignore-pattern handling for codebase-health scanners.

Reads .health-ignore files (gitignore-style syntax) and provides
filesystem walking that respects ignore patterns.
"""

import fnmatch
import os
from pathlib import Path
from typing import Iterator, List, Optional, Set

DEFAULT_IGNORE_PATTERNS = [
    ".git",
    "node_modules",
    "__pycache__",
    ".health-scan",
    "dist",
    "build",
    ".venv",
    "venv",
    ".mypy_cache",
    "*.pyc",
    ".tox",
    ".eggs",
    "*.egg-info",
    ".next",
    ".nuxt",
    "coverage",
    ".nyc_output",
    "target",  # Rust/Java build output
]


def load_ignore_patterns(
    ignore_file: Optional[str] = None,
    extra_patterns: Optional[List[str]] = None,
) -> List[str]:
    """Load ignore patterns from a .health-ignore file merged with defaults.

    Args:
        ignore_file: Path to .health-ignore file (or None to skip).
        extra_patterns: Additional patterns to include.

    Returns:
        Merged list of ignore patterns.
    """
    patterns = list(DEFAULT_IGNORE_PATTERNS)

    if ignore_file and os.path.isfile(ignore_file):
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)

    if extra_patterns:
        patterns.extend(extra_patterns)

    return patterns


def should_ignore(path: str, patterns: List[str], root: str) -> bool:
    """Check whether a path should be ignored.

    Supports gitignore-style matching:
    - "node_modules" matches any path component named node_modules
    - "*.pyc" matches any file ending in .pyc
    - "build/" matches directories named build
    - "docs/*.md" matches docs/foo.md but not docs/sub/foo.md

    Args:
        path: Absolute or relative path to check.
        patterns: List of ignore patterns.
        root: Project root (for computing relative paths).

    Returns:
        True if the path should be ignored.
    """
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        rel = path

    parts = Path(rel).parts

    for pattern in patterns:
        # Strip trailing slash (directory marker) — we match both
        clean = pattern.rstrip("/")

        # Match against each path component (like gitignore)
        for part in parts:
            if fnmatch.fnmatch(part, clean):
                return True

        # Match against the full relative path
        if fnmatch.fnmatch(rel, clean):
            return True

    return False


# Common source file extensions by language
SOURCE_EXTENSIONS = {
    "python": {".py"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx", ".mts", ".cts"},
    "go": {".go"},
    "rust": {".rs"},
    "java": {".java"},
    "ruby": {".rb"},
    "php": {".php"},
    "c": {".c", ".h"},
    "cpp": {".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"},
}

ALL_SOURCE_EXTENSIONS: Set[str] = set()
for _exts in SOURCE_EXTENSIONS.values():
    ALL_SOURCE_EXTENSIONS.update(_exts)


def walk_source_files(
    root: str,
    patterns: List[str],
    extensions: Optional[Set[str]] = None,
) -> Iterator[str]:
    """Yield source files under root that are not ignored.

    Args:
        root: Directory to walk.
        patterns: Ignore patterns (from load_ignore_patterns).
        extensions: Set of file extensions to include (e.g. {".py", ".js"}).
                    If None, includes all known source extensions.

    Yields:
        Absolute paths to matching source files.
    """
    if extensions is None:
        extensions = ALL_SOURCE_EXTENSIONS

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place (prevents os.walk from descending)
        dirnames[:] = [
            d for d in dirnames
            if not should_ignore(os.path.join(dirpath, d), patterns, root)
        ]

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            ext = os.path.splitext(fname)[1]
            if ext in extensions and not should_ignore(fpath, patterns, root):
                yield fpath
