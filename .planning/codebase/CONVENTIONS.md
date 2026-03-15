# Coding Conventions

**Analysis Date:** 2026-03-15

## Naming Patterns

**Files:**
- Python scripts use **kebab-case**: `add-finding.py`, `merge-findings.py`, `vulture-scan.py`, `permission-guard.py`
- Exception: library modules under `lib/` use **snake_case**: `lib/imports.py`, `lib/ignore.py`
- Install scripts are always `install.sh`
- Command files (markdown) use **kebab-case** matching the slash command name: `debug-triage.md`, `codebase-health-verify.md`
- Test files use `test_` prefix with **snake_case**: `test_permission_guard.py`

**Functions:**
- Use **snake_case** for all functions: `check_command()`, `load_array()`, `save_json()`, `build_import_graph()`
- Private/internal functions use leading underscore: `_ask()`, `_is_claude_internal()`, `_extract_python_imports()`, `_resolve_js_import()`, `_infer_layer()`, `_unquote()`
- Entry points are always `main()` with `if __name__ == "__main__": main()` guard

**Variables:**
- Use **snake_case** for local variables and module-level data: `forward_graph`, `reverse_graph`, `all_findings`
- Use **UPPER_SNAKE_CASE** for module-level constants: `VALID_CATEGORIES`, `SAFE_ABSOLUTE_PATHS`, `CATEGORIES`, `THRESHOLD_NLOC`, `DEAD_CODE_RULES`
- Use **UPPER_SNAKE_CASE** for compiled regex constants: `FILE_MODIFYING_CMDS`, `WRITE_REDIRECT`, `_JS_IMPORT_RE`

**Types / Data Structures:**
- Use `@dataclass` for structured data: `Import` in `codebase-health/scripts/lib/imports.py`
- Use `typing` module type hints for function signatures: `Dict`, `List`, `Optional`, `Set`, `Tuple`, `Iterator`
- Constants for valid values use plain lists: `VALID_CATEGORIES`, `VALID_SEVERITIES`, `VALID_CONFIDENCES`

**Classes:**
- Classes are rare in production code (only `Import` dataclass in `lib/imports.py`)
- Test classes use `Test` prefix with **PascalCase**: `TestGitBranchHistory`, `TestSecretsCredentials`, `TestOutsideProject`

## Code Style

**Formatting:**
- **Ruff** is the linter/formatter (configured in `pyproject.toml` via `[dev]` extras: `pip install ruff`)
- No `.prettierrc`, `.eslintrc`, or `ruff.toml` config file exists -- Ruff uses defaults
- Line length appears to follow default (~88 chars, some lines longer)
- Use double quotes for strings consistently
- Trailing newline after JSON writes: `f.write("\n")` after `json.dump()`

**Linting:**
- Run with: `ruff check .`
- No custom ruff configuration beyond the default ruleset
- No type checking tool configured for the project itself (though `pyright-scan.py` runs pyright on *target* projects)

## Import Organization

**Order:**
1. Standard library imports (`import json`, `import os`, `import sys`, `import re`, `import argparse`)
2. Third-party imports (rare -- only in scanner wrappers: `from vulture import Vulture`)
3. Local/relative imports (`from lib.ignore import load_ignore_patterns`)

**Path Manipulation for Local Imports:**
- Scripts use `sys.path.insert(0, ...)` to enable sibling imports:
  ```python
  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
  from lib.ignore import load_ignore_patterns, walk_source_files
  ```
- This pattern appears in every script under `codebase-health/scripts/` that needs `lib/`:
  - `circular-deps.py`, `unused-deps.py`, `vulture-scan.py`, `jscpd-scan.py`, `pyright-scan.py`, `lizard-scan.py`

**No Path Aliases:**
- No `pyproject.toml` path mapping or custom import resolution
- All imports are explicit relative paths via `sys.path` manipulation

## Error Handling

**Patterns:**

1. **CLI Validation — Print to stderr and `sys.exit(1)`:**
   ```python
   if not os.path.isdir(root):
       print(f"Error: {root} is not a directory", file=sys.stderr)
       sys.exit(1)
   ```
   Used consistently across all scripts for argument validation.

2. **JSON Load Errors — Try/except with warning or fatal:**
   ```python
   try:
       data = load_json(json_file)
   except (json.JSONDecodeError, OSError) as e:
       print(f"Warning: skipping {json_file}: {e}", file=sys.stderr)
       continue
   ```
   Non-critical files get warnings; critical files get `sys.exit(1)`.

3. **Missing External Tools — Graceful error with install instructions:**
   ```python
   try:
       from vulture import Vulture
   except ImportError:
       print("Error: vulture is not installed.\n"
             "Install it with: pip install vulture", file=sys.stderr)
       sys.exit(1)
   ```
   Used in `vulture-scan.py`, `jscpd-scan.py`, `pyright-scan.py`, `lizard-scan.py`.

4. **Hook Scripts — Silent return on bad input:**
   ```python
   try:
       event = json.load(sys.stdin)
   except (json.JSONDecodeError, EOFError):
       return
   ```
   Hooks (`permission-guard.py`, `intercept-trigger.py`) never crash -- they silently pass through.

5. **No Exceptions Raised:**
   - Functions return `None` to indicate "no match/no issue" rather than raising exceptions
   - `check_command()`, `check_file_path()`, `check_sensitive_in_command()` all return `None` on success or a tuple on failure

## Logging

**Framework:** `print()` to stderr

**Patterns:**
- All user-facing status output goes to **stderr** via `file=sys.stderr`
- JSON/structured output goes to **stdout** (for piping)
- Progress messages use f-strings: `print(f"Merged {len(findings)} findings from {len(categories_seen)} categories", file=sys.stderr)`
- Warning messages are prefixed with `"Warning:"`: `print(f"Warning: {len(missing)} IDs not found: ...", file=sys.stderr)`
- Error messages are prefixed with `"Error:"`: `print(f"Error: {root} is not a directory", file=sys.stderr)`
- No logging levels, no logging module, no structured logging

## Comments

**When to Comment:**
- Module-level docstrings describe purpose, usage example, and dependency requirements
- Section separators use comment banners with dashes:
  ```python
  # ── Category definitions ────────────────────────────────────────────────────
  ```
  and
  ```python
  # ---------------------------------------------------------------------------
  # Graph building
  # ---------------------------------------------------------------------------
  ```
- Inline comments explain non-obvious logic (e.g., `# Skip type-only imports for cycle detection`)
- Test classes use category-labeled comments: `# ── Category 1: Git Branch & History ────────────────────────────────────`

**Docstrings:**
- All public functions have single-line or multi-line docstrings
- Use triple-double-quote style: `"""Description."""`
- Args/Returns documented with labeled sections in library code (`lib/imports.py`, `lib/ignore.py`):
  ```python
  def walk_source_files(root, patterns, extensions=None):
      """Yield source files under root that are not ignored.

      Args:
          root: Directory to walk.
          patterns: Ignore patterns (from load_ignore_patterns).
          extensions: Set of file extensions to include.

      Yields:
          Absolute paths to matching source files.
      """
  ```
- CLI scripts use shorter docstrings focused on "what" not "how"

## Function Design

**Size:**
- Functions are generally small (10-40 lines)
- `main()` functions are the longest, handling argument parsing + orchestration
- Largest function: `_extract_python_imports()` in `lib/imports.py` (~50 lines)

**Parameters:**
- Use keyword arguments via `argparse` for CLI interfaces
- Use positional parameters for internal library functions
- Optional parameters use `Optional[T]` type hints with `None` defaults
- No `**kwargs` usage anywhere

**Return Values:**
- Functions that check/validate return `None` for success, tuple for failure
  - `check_command()` returns `(description, category, matched_text)` or `None`
  - `check_file_path()` returns `(description,)` or `None`
- Data functions return structured dicts (JSON-serializable)
- `analyze()` functions in analysis scripts return `dict` suitable for `json.dump()`

## Module Design

**Exports:**
- No `__all__` declarations anywhere
- Public API defined implicitly (non-underscore-prefixed functions)
- `lib/__init__.py` contains only a comment: `# codebase-health scanner helper library`

**Barrel Files:**
- Not used. Each module is imported directly by name

## Atomic File Writes

**Pattern used project-wide:**
```python
def save_json(path, data):
    """Atomic write JSON."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
```
- Write to `.tmp` file, then `os.replace()` for atomicity
- This pattern appears in: `add-finding.py`, `merge-findings.py`, `verify-finding.py`, `update-findings.py`, `split-findings.py`
- Always use `indent=2` and `ensure_ascii=False` for JSON output
- Always append a trailing newline after JSON content

## CLI Script Pattern

All Python CLI scripts follow the same structure:

```python
#!/usr/bin/env python3
"""Module docstring with usage example."""

import argparse
# ... other imports

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--root", required=True, help="...")
    parser.add_argument("--output", required=True, help="...")
    args = parser.parse_args()

    # Validate inputs
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Do work
    result = analyze(root)

    # Write output
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Summary to stderr
    print(f"Found {result['count']} items", file=sys.stderr)

if __name__ == "__main__":
    main()
```

## Install Script Pattern

All install scripts (`install.sh`) follow this structure:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS=(command-name)

# Parse arguments (--project/--global/--target)
# Resolve target directory
# Validate source files exist
# Copy to target
# Resolve placeholders via sed
# Print summary
```

Key conventions:
- Always `set -euo pipefail`
- Always resolve `SCRIPT_DIR` from `BASH_SOURCE[0]`
- Three install modes: `--project [<dir>]`, `--global`, `--target <path>`
- Validate source files exist before copying
- Use `sed -i` to replace placeholders (`{SCRIPTS_DIR}`, `{HOOKS_DIR}`, `{PROJECT_ROOT}`) with absolute paths
- Print clear summary of what was installed and next steps

## Command Markdown Pattern

Command files use this frontmatter format:

```markdown
---
name: mg:command-name
description: One-line description
argument-hint: [optional argument description]
allowed-tools:
  - Read
  - Write
  - Bash
  - Task
  - Glob
  - Grep
---
```

Body uses `<objective>`, `<context>`, `<process>` XML-style tags for structure. Steps are numbered markdown headers (`## Step 1: ...`).

---

*Convention analysis: 2026-03-15*
