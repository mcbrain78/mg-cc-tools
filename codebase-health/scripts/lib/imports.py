"""Import extraction and resolution for multiple languages.

Python: parsed via ast module (accurate).
JS/TS/Go/Rust: parsed via regex (best-effort).

Zero external dependencies — stdlib only.
"""

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Import:
    """Represents a single import statement."""

    source_file: str  # Absolute path of the file containing the import
    target: str  # The imported module/package string
    alias: Optional[str] = None  # Import alias (as ...)
    is_type_only: bool = False  # TYPE_CHECKING or `import type`
    line: int = 0  # Line number in source file


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_TO_LANG: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
}


def detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return _EXT_TO_LANG.get(ext)


# ---------------------------------------------------------------------------
# Python import extraction (via ast — accurate)
# ---------------------------------------------------------------------------

# Standard library module names (top-level) for Python 3.8+
# This is not exhaustive but covers the vast majority
_PYTHON_STDLIB = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
    "cmath", "cmd", "code", "codecs", "codeop", "collections", "colorsys",
    "compileall", "concurrent", "configparser", "contextlib", "contextvars",
    "copy", "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest", "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "fractions",
    "ftplib", "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "lib2to3", "linecache", "locale",
    "logging", "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue",
    "quopri", "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr", "socket",
    "socketserver", "spwd", "sqlite3", "ssl", "stat", "statistics",
    "string", "stringprep", "struct", "subprocess", "sunau", "symtable",
    "sys", "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib",
    "tempfile", "termios", "test", "textwrap", "threading", "time",
    "timeit", "tkinter", "token", "tokenize", "tomllib", "trace",
    "traceback", "tracemalloc", "tty", "turtle", "turtledemo", "types",
    "typing", "unicodedata", "unittest", "urllib", "uu", "uuid", "venv",
    "warnings", "wave", "weakref", "webbrowser", "winreg", "winsound",
    "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport",
    "zlib", "_thread", "__future__", "typing_extensions",
}


def _extract_python_imports(file_path: str, source: str) -> List[Import]:
    """Extract imports from Python source using the ast module."""
    imports: List[Import] = []
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return imports

    # Detect TYPE_CHECKING blocks
    type_checking_ranges: List[range] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = False
            if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
                is_tc = True
            elif isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                is_tc = True
            if is_tc and node.body:
                start = node.body[0].lineno
                end = node.body[-1].end_lineno or node.body[-1].lineno
                type_checking_ranges.append(range(start, end + 1))

    def _in_type_checking(lineno: int) -> bool:
        return any(lineno in r for r in type_checking_ranges)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(Import(
                    source_file=file_path,
                    target=alias.name,
                    alias=alias.asname,
                    is_type_only=_in_type_checking(node.lineno),
                    line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Handle relative imports: dots indicate relative level
            prefix = "." * (node.level or 0)
            target = prefix + module if module else prefix
            for alias in node.names:
                imports.append(Import(
                    source_file=file_path,
                    target=target,
                    alias=alias.asname,
                    is_type_only=_in_type_checking(node.lineno),
                    line=node.lineno,
                ))

    return imports


# ---------------------------------------------------------------------------
# JS/TS import extraction (via regex — best-effort)
# ---------------------------------------------------------------------------

# Matches: import ... from "module"  /  import "module"  /  require("module")
_JS_IMPORT_RE = re.compile(
    r"""(?mx)
    (?:
        # import type { ... } from "module"
        import\s+type\s+.*?\s+from\s+['"]([^'"]+)['"]
        |
        # import ... from "module"
        import\s+.*?\s+from\s+['"]([^'"]+)['"]
        |
        # import "module" (side-effect)
        import\s+['"]([^'"]+)['"]
        |
        # require("module")
        require\s*\(\s*['"]([^'"]+)['"]\s*\)
        |
        # export ... from "module"
        export\s+.*?\s+from\s+['"]([^'"]+)['"]
    )
    """
)

_JS_TYPE_IMPORT_RE = re.compile(
    r"""import\s+type\s+""",
)


def _extract_js_ts_imports(file_path: str, source: str, language: str) -> List[Import]:
    """Extract imports from JS/TS source via regex."""
    imports: List[Import] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        for m in _JS_IMPORT_RE.finditer(line):
            # Groups: (1) type import, (2) regular from, (3) side-effect, (4) require, (5) export from
            target = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
            if target:
                is_type = bool(m.group(1)) or bool(_JS_TYPE_IMPORT_RE.search(line))
                imports.append(Import(
                    source_file=file_path,
                    target=target,
                    is_type_only=is_type,
                    line=i,
                ))
    return imports


# ---------------------------------------------------------------------------
# Go import extraction (via regex)
# ---------------------------------------------------------------------------

_GO_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r'import\s*\((.*?)\)', re.DOTALL)
_GO_IMPORT_LINE_RE = re.compile(r'(?:\w+\s+)?"([^"]+)"')


def _extract_go_imports(file_path: str, source: str) -> List[Import]:
    """Extract imports from Go source via regex."""
    imports: List[Import] = []

    # Single-line imports
    for m in _GO_IMPORT_SINGLE_RE.finditer(source):
        imports.append(Import(
            source_file=file_path,
            target=m.group(1),
            line=source[:m.start()].count("\n") + 1,
        ))

    # Block imports
    for block_m in _GO_IMPORT_BLOCK_RE.finditer(source):
        block_start = source[:block_m.start()].count("\n") + 1
        for i, line in enumerate(block_m.group(1).splitlines()):
            line_m = _GO_IMPORT_LINE_RE.search(line)
            if line_m:
                imports.append(Import(
                    source_file=file_path,
                    target=line_m.group(1),
                    line=block_start + i,
                ))

    return imports


# ---------------------------------------------------------------------------
# Rust import extraction (via regex)
# ---------------------------------------------------------------------------

_RUST_USE_RE = re.compile(r'^\s*use\s+([\w:]+)', re.MULTILINE)


def _extract_rust_imports(file_path: str, source: str) -> List[Import]:
    """Extract use statements from Rust source via regex."""
    imports: List[Import] = []
    for m in _RUST_USE_RE.finditer(source):
        imports.append(Import(
            source_file=file_path,
            target=m.group(1),
            line=source[:m.start()].count("\n") + 1,
        ))
    return imports


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_imports(file_path: str, language: Optional[str] = None) -> List[Import]:
    """Extract imports from a source file.

    Args:
        file_path: Absolute path to the source file.
        language: Language override. If None, detected from extension.

    Returns:
        List of Import instances. Empty list on errors.
    """
    if language is None:
        language = detect_language(file_path)
    if language is None:
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return []

    if language == "python":
        return _extract_python_imports(file_path, source)
    elif language in ("javascript", "typescript"):
        return _extract_js_ts_imports(file_path, source, language)
    elif language == "go":
        return _extract_go_imports(file_path, source)
    elif language == "rust":
        return _extract_rust_imports(file_path, source)
    else:
        return []


def is_internal_import(target: str, root: str, source_file: str, language: Optional[str] = None) -> bool:
    """Determine whether an import target refers to project-internal code.

    Args:
        target: The import string (e.g. "mypackage.utils" or "./utils").
        root: Project root directory.
        source_file: The file containing the import.
        language: Language override.

    Returns:
        True if the import appears to be internal to the project.
    """
    if language is None:
        language = detect_language(source_file)

    if language == "python":
        # Relative imports are always internal
        if target.startswith("."):
            return True
        # Check if top-level module name matches a directory/file in root
        top = target.split(".")[0]
        if top in _PYTHON_STDLIB:
            return False
        # Check if it exists as a package or module in the project
        return (
            os.path.isdir(os.path.join(root, top))
            or os.path.isfile(os.path.join(root, top + ".py"))
        )

    elif language in ("javascript", "typescript"):
        # Relative paths are internal
        return target.startswith(".") or target.startswith("/")

    elif language == "go":
        # Go imports: internal if they share the module path prefix
        go_mod = os.path.join(root, "go.mod")
        if os.path.isfile(go_mod):
            try:
                with open(go_mod, "r") as f:
                    for line in f:
                        if line.startswith("module "):
                            module_path = line.split()[1].strip()
                            return target.startswith(module_path)
            except (OSError, IOError):
                pass
        return False

    elif language == "rust":
        # Rust: crate:: and super:: are internal; std/core/alloc are stdlib
        if target.startswith(("crate::", "super::", "self::")):
            return True
        top = target.split("::")[0]
        return top not in {"std", "core", "alloc", "proc_macro"}

    return False


def resolve_import_to_file(
    target: str,
    source_file: str,
    root: str,
    language: Optional[str] = None,
) -> Optional[str]:
    """Attempt to resolve an import string to a concrete file path.

    Args:
        target: The import string.
        source_file: The file containing the import.
        root: Project root directory.
        language: Language override.

    Returns:
        Absolute path to the resolved file, or None if unresolvable.
    """
    if language is None:
        language = detect_language(source_file)

    if language == "python":
        return _resolve_python_import(target, source_file, root)
    elif language in ("javascript", "typescript"):
        return _resolve_js_import(target, source_file, root, language)
    elif language == "go":
        return _resolve_go_import(target, root)
    elif language == "rust":
        return _resolve_rust_import(target, source_file, root)

    return None


def _resolve_python_import(target: str, source_file: str, root: str) -> Optional[str]:
    """Resolve a Python import to a file path."""
    if target.startswith("."):
        # Relative import
        dots = 0
        for c in target:
            if c == ".":
                dots += 1
            else:
                break
        module_part = target[dots:]
        base = os.path.dirname(source_file)
        for _ in range(dots - 1):
            base = os.path.dirname(base)
    else:
        module_part = target
        base = root

    parts = module_part.split(".") if module_part else []
    path = os.path.join(base, *parts)

    # Try as package
    init = os.path.join(path, "__init__.py")
    if os.path.isfile(init):
        return init

    # Try as module
    mod = path + ".py"
    if os.path.isfile(mod):
        return mod

    return None


def _resolve_js_import(target: str, source_file: str, root: str, language: str) -> Optional[str]:
    """Resolve a JS/TS import to a file path."""
    if not target.startswith(".") and not target.startswith("/"):
        return None  # External package

    base = os.path.dirname(source_file) if target.startswith(".") else root
    resolved = os.path.normpath(os.path.join(base, target))

    # Try exact path
    if os.path.isfile(resolved):
        return resolved

    # Try with extensions
    exts = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"] if language == "typescript" else [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"]
    for ext in exts:
        candidate = resolved + ext
        if os.path.isfile(candidate):
            return candidate

    # Try index files
    for ext in exts:
        candidate = os.path.join(resolved, "index" + ext)
        if os.path.isfile(candidate):
            return candidate

    return None


def _resolve_go_import(target: str, root: str) -> Optional[str]:
    """Resolve a Go import to a directory (Go packages are directories)."""
    go_mod = os.path.join(root, "go.mod")
    if not os.path.isfile(go_mod):
        return None

    try:
        with open(go_mod, "r") as f:
            for line in f:
                if line.startswith("module "):
                    module_path = line.split()[1].strip()
                    if target.startswith(module_path):
                        rel = target[len(module_path):].lstrip("/")
                        pkg_dir = os.path.join(root, rel)
                        if os.path.isdir(pkg_dir):
                            return pkg_dir
                    break
    except (OSError, IOError):
        pass

    return None


def _resolve_rust_import(target: str, source_file: str, root: str) -> Optional[str]:
    """Resolve a Rust use statement to a file path (best-effort)."""
    parts = target.replace("::", "/").split("/")

    if parts[0] == "crate":
        parts = parts[1:]
        base = os.path.join(root, "src")
    elif parts[0] == "super":
        parts = parts[1:]
        base = os.path.dirname(os.path.dirname(source_file))
    elif parts[0] == "self":
        parts = parts[1:]
        base = os.path.dirname(source_file)
    else:
        return None

    path = os.path.join(base, *parts)

    # Try as file
    if os.path.isfile(path + ".rs"):
        return path + ".rs"

    # Try as directory with mod.rs
    mod_rs = os.path.join(path, "mod.rs")
    if os.path.isfile(mod_rs):
        return mod_rs

    return None
