# Phase 7: Install Command - Research

**Researched:** 2026-03-17
**Domain:** CLI tool management (Python stdlib, TOML metadata, SHA256 checksums, interactive slash commands)
**Confidence:** HIGH

## Summary

Phase 7 builds `/mg:install`, a unified Claude Code slash command that replaces manual `install.sh` invocations with an interactive tool management experience. The implementation has two components: `install.md` (the LLM prompt for orchestration and presentation) and `mg-install-lib.py` (a Python script handling all deterministic operations with JSON output). The phase also creates `tool.toml` metadata files for all 11 existing tools and modifies all 11 `install.sh` scripts to call `mg-install-lib.py update-manifest` after every install.

The technical surface is well-defined and fully constrained by the CONTEXT.md decisions. All required libraries (`tomllib`, `hashlib`, `fcntl`, `subprocess`, `json`, `os`) are Python stdlib. The existing install.sh patterns are extremely consistent across tools, making the install.sh modifications mechanical. The primary complexity lies in `mg-install-lib.py` which implements 5 subcommands (scan-status, preflight, update-manifest, validate, adopt) that collectively handle tool discovery, staleness detection, manifest management, and migration.

**Primary recommendation:** Build mg-install-lib.py as a single Python file with 5 subcommand functions, test each subcommand in isolation using temp directories with mock tool structures, then write install.md and tool.toml files, and finally modify all 11 install.sh scripts with the manifest update call. The install.md prompt is the most complex piece but cannot be unit-tested -- validate it manually on road-runner.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single slash command: `/mg:install [target-path]`
- Frontmatter: `allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion`
- Runs from mg-cc-tools directory only -- source is always `./`, no bidirectional path resolution
- Dynamic tool discovery: scan for `tool.toml` + `install.sh` (both must exist)
- TOML format for tool metadata (`tool.toml`), using `tomllib` (stdlib since Python 3.11)
- Fields: `tool.description` (string, required), `tool.exclude` (bool, default false), `preflight.required` (array), `preflight.optional` (array)
- No `category` field
- Step 1 (target): AskUserQuestion with recent targets from `~/.config/mg-cc-tools/targets.json`
- Step 2 (status): Non-interactive text table from `mg-install-lib.py scan-status`
- Step 3 (action): Numbered text prompt (NOT AskUserQuestion). LLM parses response.
- Step 4 (preflight): Non-interactive unless required check fails (hard abort)
- Step 5 (capability probe): `claude -p` from TARGET directory for LSP check. Every invocation.
- Step 6 (install): Delegate to each tool's existing `install.sh`
- Step 7 (validation): Grep for unresolved `{PLACEHOLDER}` patterns
- Step 8 (summary): Status table with actions taken
- Single project version from `pyproject.toml` -- never per-tool versions
- SHA256 checksums of source files (pre-sed), source-to-source comparison
- Five display states: Current, Update, Modified, Corrupt, Available
- Manifest at `.claude/mg-cc-tools.manifest.json` (must be gitignored)
- Manifest written by BOTH `/mg:install` AND standalone `install.sh`
- Every `install.sh` calls `mg-install-lib.py update-manifest` -- no `|| true`, no fallback
- Path to mg-install-lib.py from install.sh: `$(cd "$(dirname "$0")" && pwd)/../install/scripts/mg-install-lib.py`
- 3 simple tools (debug-triage, update-backlog, new-milestone-gsd) get python3 check added
- Preflight checks declared per-tool in `tool.toml`, logic in mg-install-lib.py CHECKS registry
- 8 checks: python3, git, gsd, lsp, ruff, vulture, pyright, jscpd
- Required check failure = hard abort; optional check failure = warn
- LSP probe uses `claude -p --output-format json` from target directory
- Migration: command-to-tool mapping detects pre-existing installs; `adopt` subcommand builds manifest
- Excluded tools: `install` and `cc-regression-test` (shown below separator, `exclude = true`)
- Responsibility split: install.md = orchestration/presentation; mg-install-lib.py = deterministic JSON ops
- Bootstrap: `install/install.sh` self-installs `/mg:install` into mg-cc-tools's own `.claude/commands/mg/`
- Validation target: road-runner (human-verify, not automated test)
- Full pytest suite for mg-install-lib.py (all 5 subcommands)
- Tests use temp directories with mock tool structures

### Claude's Discretion
- Exact JSON output schemas for each mg-install-lib.py subcommand
- `~/.config/mg-cc-tools/targets.json` schema and update logic
- File locking strategy for concurrent manifest writes (edge case for v1)
- Internal code organization of mg-install-lib.py (single file vs modules)
- Exact wording of numbered prompts and status table formatting
- Error handling for edge cases (tool directory deleted after discovery, install.sh fails mid-copy)

### Deferred Ideas (OUT OF SCOPE)
- Installed file integrity checksums (post-sed) to detect manual edits -- v2
- Uninstall / cleanup (remove tool files and manifest entries) -- v2
- Global install support (`--global` targeting `~/.claude/`) -- v2
- Categories in tool.toml for grouping -- removed from design
</user_constraints>

<phase_requirements>
## Phase Requirements

Phase 7 has no formally assigned requirement IDs (TBD in REQUIREMENTS.md). The CONTEXT.md decisions serve as the authoritative requirements. Mapping the decisions to logical requirement groups:

| ID | Description | Research Support |
|----|-------------|-----------------|
| INST-01 | Tool discovery via `tool.toml` + `install.sh` scanning | TOML parsing via stdlib tomllib; discovery pattern documented |
| INST-02 | `tool.toml` metadata format with description, exclude, preflight fields | TOML schema verified with tomllib; see Architecture Patterns |
| INST-03 | Status scan with 5 display states and source checksum comparison | SHA256 via hashlib stdlib; checksum scope analyzed per tool |
| INST-04 | Manifest management (write, read, update) at `.claude/mg-cc-tools.manifest.json` | JSON I/O with atomic write pattern from existing codebase |
| INST-05 | Preflight check registry with command-based, path-exists, and claude-probe types | subprocess for command checks; 8 checks fully specified |
| INST-06 | LSP capability probe via `claude -p --output-format json` from target dir | Runs as subprocess from target directory |
| INST-07 | Migration/adopt flow for pre-manifest projects | Command-to-tool mapping from source `commands/` dirs |
| INST-08 | Post-install validation (placeholder grep, path verification) | Regex pattern for `{...}` placeholders; path existence checks |
| INST-09 | install.md slash command with 8-step interactive flow | AskUserQuestion for target; numbered prompts for action |
| INST-10 | All 11 install.sh scripts modified (manifest update + python3 check) | Existing install.sh patterns analyzed; modification is mechanical |
| INST-11 | Bootstrap installer (`install/install.sh`) for self-install | Follows existing simple install.sh pattern |
| INST-12 | Full pytest suite for mg-install-lib.py | Test patterns established in create-docs/scripts/tests/ |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tomllib` | stdlib (3.11+) | Parse `tool.toml` metadata files | Locked decision; no pip dependency |
| `hashlib` | stdlib | SHA256 checksums of source files | Standard for file integrity checking |
| `json` | stdlib | Manifest and subcommand JSON I/O | All existing scripts use it |
| `subprocess` | stdlib | Run preflight commands, `claude -p` probe | Existing pattern in codebase |
| `os` / `os.path` | stdlib | File system operations, path manipulation | Existing pattern |
| `argparse` | stdlib | CLI argument parsing for mg-install-lib.py | Existing pattern in create-docs scripts |
| `fcntl` | stdlib (Linux/macOS) | File locking for concurrent manifest writes | Advisory locking for safety |
| `tempfile` | stdlib | Atomic file writes (os.replace pattern) | Existing pattern in create-docs scripts |
| `datetime` | stdlib | ISO 8601 timestamps for manifest | Existing pattern |
| `pathlib` | stdlib | Path manipulation (optional, complements os.path) | Cleaner than os.path for glob patterns |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | dev dependency | Testing mg-install-lib.py subcommands | Development only; already in pyproject.toml |
| `ruff` | dev dependency | Linting | Development only; already in pyproject.toml |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tomllib` | `configparser` (INI) | TOML supports arrays natively; locked decision |
| `fcntl.flock` | No locking | Concurrent install.sh could corrupt manifest; flock is simple insurance |
| Single mg-install-lib.py | Multiple scripts | Single file is simpler to path-reference from 11 install.sh scripts |

**Installation:** No pip dependencies. All stdlib. Dev dependencies already declared in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
install/
  tool.toml                     # exclude = true (meta-tool)
  install.sh                    # bootstrap: copies install.md to mg-cc-tools/.claude/commands/mg/
  commands/
    install.md                  # the /mg:install slash command prompt
  scripts/
    mg-install-lib.py           # 5-subcommand CLI script (~500-700 lines)
    tests/
      test_mg_install_lib.py    # pytest suite for all subcommands

<every-tool>/
  tool.toml                     # NEW file: tool metadata
  install.sh                    # MODIFIED: +python3 check, +manifest update call
```

### Pattern 1: Subcommand Dispatch (mg-install-lib.py)
**What:** Single Python script with subcommand dispatch via argparse subparsers
**When to use:** All 5 operations (scan-status, preflight, update-manifest, validate, adopt)
**Example:**
```python
# Follows existing mg-cc-tools pattern of CLI scripts with JSON stdout
import argparse
import json
import sys

def cmd_scan_status(args):
    """Discover tools, compute checksums, compare with manifest."""
    result = scan_status(args.source, args.target)
    json.dump(result, sys.stdout, indent=2)

def cmd_preflight(args):
    """Run preflight checks for given tools."""
    result = run_preflight(args.source, args.target, args.tools)
    json.dump(result, sys.stdout, indent=2)

def cmd_update_manifest(args):
    """Update manifest entry for one tool after install."""
    update_manifest(args.target, args.tool, args.source)

def cmd_validate(args):
    """Validate installed files for placeholder and path issues."""
    result = validate_install(args.target)
    json.dump(result, sys.stdout, indent=2)

def cmd_adopt(args):
    """Detect and adopt pre-manifest installations."""
    result = adopt_tools(args.source, args.target)
    json.dump(result, sys.stdout, indent=2)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan-status")
    p_scan.add_argument("--source", required=True)
    p_scan.add_argument("--target", required=True)
    p_scan.set_defaults(func=cmd_scan_status)

    # ... similar for other subcommands

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
```

### Pattern 2: Atomic Manifest Write with File Locking
**What:** Read-modify-write manifest with advisory file locking to prevent corruption from concurrent install.sh invocations
**When to use:** Every manifest write (update-manifest subcommand)
**Example:**
```python
import fcntl
import json
import os
import tempfile

def write_manifest_atomic(manifest_path, data):
    """Write manifest atomically with file locking."""
    lock_path = manifest_path + ".lock"
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            # Write to temp file, then atomic rename
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(manifest_path),
                suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                os.replace(tmp_path, manifest_path)
            except:
                os.unlink(tmp_path)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
```

### Pattern 3: Source File Checksumming
**What:** Compute SHA256 checksums of source files per tool, using defined include/exclude scope
**When to use:** update-manifest (store checksums) and scan-status (compare checksums)
**Example:**
```python
import hashlib
import os

CHECKSUM_INCLUDE = [
    "commands/*.md",
    "scripts/*.py",
    "scripts/lib/*.py",
    "agents/*.md",
    "references/**/*",
    "install.sh",
]

CHECKSUM_EXCLUDE = [
    "tool.toml",
    "tests/",
    "**/tests/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
]

def compute_tool_checksums(tool_dir):
    """Compute SHA256 checksums for all source files in scope."""
    checksums = {}
    for pattern in CHECKSUM_INCLUDE:
        # Use pathlib.Path.glob for each pattern
        from pathlib import Path
        for path in Path(tool_dir).glob(pattern):
            rel = str(path.relative_to(tool_dir))
            # Skip excluded paths
            if any(excl in rel for excl in ["tests/", "__pycache__", ".pyc", ".pytest_cache"]):
                continue
            if rel == "tool.toml":
                continue
            checksums[rel] = sha256_file(str(path))
    return checksums

def sha256_file(filepath):
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"
```

### Pattern 4: Manifest Update Call in install.sh
**What:** Every install.sh calls mg-install-lib.py update-manifest at the end
**When to use:** All 11 install.sh files
**Example:**
```bash
# At end of install.sh, after all copies and sed resolution
# Note: existing scripts use TARGET_DIR, not INSTALL_DIR
TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$TARGET_DIR" \
  --tool "$(basename "$TOOL_SOURCE_DIR")" \
  --source "$TOOL_SOURCE_DIR"
```

### Pattern 5: Non-.md Files in Commands Directories
**What:** Some tools have non-.md files in `commands/` (e.g., create-context has `context-template.snapshot`)
**When to use:** When building command-to-tool mapping and checksum scope
**Impact:** The command-to-tool mapping should look for `.md` files only (these are the Claude Code commands). Non-.md files are supporting resources that happen to live in `commands/`. Checksum scope already uses `commands/*.md` so this is handled correctly, but the installer should copy all files in `commands/` not just `.md` when doing its inventory.

### Anti-Patterns to Avoid
- **Comparing source vs installed files:** Post-sed installed files will always differ from pre-sed source files. Always compare source-at-install-time vs source-now.
- **Hardcoded tool list:** No `TOOLS = ["create-docs", "codebase-health", ...]`. Discovery is always dynamic from disk.
- **Silent manifest failures:** Never use `|| true` on the manifest update call. A failed manifest update means the install is incomplete.
- **Per-tool version tracking:** One version in pyproject.toml. No per-tool versions to keep in sync.
- **Using AskUserQuestion for action selection:** It has a 4-option limit. Use numbered text prompt instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML parsing | Custom parser | `tomllib` (stdlib) | TOML has edge cases (multiline strings, inline tables) |
| SHA256 hashing | Custom hash | `hashlib.sha256` | Correct, fast, stdlib |
| File locking | Lock file tricks | `fcntl.flock` | OS-level advisory locks, handles process crashes |
| Atomic file writes | Direct overwrite | `tempfile` + `os.replace` | Prevents partial writes on crash |
| Version comparison | String compare | `packaging.version` or simple tuple compare | Semantic version ordering is non-trivial BUT for this project, simple string equality is sufficient since we only check equal/not-equal |
| CLI argument parsing | sys.argv slicing | `argparse` with subparsers | Handles help, errors, type coercion |
| Glob matching | Manual os.walk + fnmatch | `pathlib.Path.glob` | Handles recursive patterns (`**/*`) correctly |

**Key insight:** mg-install-lib.py does not need ANY pip dependencies. Every operation is achievable with Python stdlib. This is consistent with the project's zero-dependency constraint for scripts.

## Common Pitfalls

### Pitfall 1: Variable Name Mismatch in install.sh
**What goes wrong:** The CONCEPT.md uses `$INSTALL_DIR` in the manifest update snippet, but ALL 11 existing install.sh scripts use `$TARGET_DIR` for the installation path.
**Why it happens:** The concept was written independently from the existing code.
**How to avoid:** Use `$TARGET_DIR` in the manifest update call, not `$INSTALL_DIR`. Verified by grep: zero occurrences of `INSTALL_DIR` in any existing install.sh.
**Warning signs:** `mg-install-lib.py update-manifest --target ""` (empty target because variable is unset).

### Pitfall 2: Checksum Scope Missing Edge Cases
**What goes wrong:** Some tools have files outside the standard patterns that are part of the installed product. For example, `create-context/commands/context-template.snapshot` is not a `.md` file but is copied by install.sh.
**Why it happens:** The checksum include patterns (`commands/*.md`) don't cover non-.md files in commands/.
**How to avoid:** Include `commands/*` (all files) in checksum scope, or add explicit handling for non-standard file patterns. The `install.sh` copies whatever it copies -- the checksum scope should match.
**Warning signs:** Tool shows "Current" but install.sh actually copies a changed snapshot file.

### Pitfall 3: install.sh Scripts Have Inconsistent PROJECT_PATH Handling
**What goes wrong:** Some install.sh scripts (debug-triage, gsd-patches, update-backlog, new-milestone-gsd) don't initialize `PROJECT_PATH=""` at the top. If `--project` is used without a path argument, `PROJECT_PATH` may be unset.
**Why it happens:** The simple tools were written with minimal boilerplate.
**How to avoid:** When modifying these install.sh scripts, don't rely on `PROJECT_PATH` for the manifest update. Use `TARGET_DIR` which is always set correctly.
**Warning signs:** `unbound variable` errors in bash with `set -u`.

### Pitfall 4: pyproject.toml Version vs requires-python
**What goes wrong:** `pyproject.toml` currently says `requires-python = ">=3.8"` but the CONTEXT.md says "we require Python 3.13+" and `tomllib` needs Python 3.11+.
**Why it happens:** pyproject.toml was written before the installer design decisions.
**How to avoid:** Update `requires-python` in pyproject.toml when implementing. At minimum it must be `>=3.11` for tomllib. The CONTEXT.md says 3.13+ but the actual hard floor is 3.11 (tomllib availability).
**Warning signs:** ImportError for tomllib on Python 3.10 or earlier.

### Pitfall 5: Concurrent install.sh Manifest Corruption
**What goes wrong:** If multiple install.sh scripts run in parallel (e.g., `/mg:install` delegates installs rapidly), multiple processes may read/modify/write the manifest simultaneously, causing data loss.
**Why it happens:** JSON read-modify-write is not atomic without locking.
**How to avoid:** Use `fcntl.flock` in the `update-manifest` subcommand. Each install.sh calls update-manifest, which acquires an exclusive lock, reads the manifest, updates its tool's entry, and writes atomically.
**Warning signs:** Manifest missing tool entries after bulk install.

### Pitfall 6: mg-gsd-wrappers Cross-Tool Dependency
**What goes wrong:** `mg-gsd-wrappers/install.sh` references `gsd-patches/patches/` via `REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"`. It also copies a patch file to the installed gsd-patches directory if it exists. This is the ONLY cross-tool dependency in the codebase.
**Why it happens:** mg-gsd-wrappers installs a patch that augments gsd-patches behavior.
**How to avoid:** Document this dependency in mg-gsd-wrappers/tool.toml comments. The installer should handle it by installing gsd-patches before mg-gsd-wrappers, or the LLM prompt should note the recommended install order.
**Warning signs:** "Error: missing gsd-patches/patches/" when installing mg-gsd-wrappers alone.

### Pitfall 7: Bootstrap install.sh Must Not Require mg-install-lib.py
**What goes wrong:** The bootstrap `install/install.sh` copies `install.md` into mg-cc-tools's own `.claude/`. If it also tries to call `mg-install-lib.py update-manifest`, it would be calling itself -- but the target is mg-cc-tools, not a project that needs a manifest.
**Why it happens:** The bootstrap is a special case -- it installs into the source repo itself.
**How to avoid:** The bootstrap install.sh should NOT call update-manifest. It's the one exception. mg-cc-tools itself doesn't need a manifest since it IS the source.
**Warning signs:** Infinite path resolution or manifest in the wrong place.

### Pitfall 8: claude -p Probe Timeout
**What goes wrong:** The `claude -p` probe for LSP can take 30+ seconds or hang if Claude Code isn't properly configured.
**Why it happens:** LSP initialization varies by project size and language server.
**How to avoid:** Set a timeout on the subprocess call (e.g., 60 seconds). Catch subprocess.TimeoutExpired and treat as "LSP not available."
**Warning signs:** Install command appears to hang during capability probe step.

## Code Examples

### tool.toml Examples (Verified Pattern)

**Simple tool (no scripts):**
```toml
# debug-triage/tool.toml

[tool]
description = "GSD debug workflow with structured triage"

[preflight]
required = ["gsd"]
```

**Complex tool (scripts, agents, references):**
```toml
# create-docs/tool.toml

[tool]
description = "Multi-step documentation pipeline (scan, generate, verify)"

[preflight]
required = ["python3"]
optional = ["lsp"]
```

**Excluded tool:**
```toml
# install/tool.toml

[tool]
description = "mg-cc-tools installer (internal)"
exclude = true

[preflight]
required = ["python3"]
```

### Manifest Schema (Recommended)
```json
{
  "mg_cc_tools_version": "0.1.0",
  "source_path": "/home/user/mg_projects/mg-cc-tools",
  "last_updated": "2026-03-17T14:30:00+00:00",
  "tools": {
    "create-docs": {
      "version": "0.1.0",
      "installed_at": "2026-03-17T14:30:00+00:00",
      "commands": [
        "create-docs.md",
        "create-docs-scan.md",
        "create-docs-generate.md",
        "create-docs-verify.md",
        "add-docs.md"
      ],
      "source_checksums": {
        "install.sh": "sha256:abc123...",
        "commands/create-docs.md": "sha256:def456...",
        "scripts/check-references.py": "sha256:789ghi..."
      }
    }
  },
  "capabilities": {
    "lsp": true,
    "lsp_languages": ["python"],
    "python_version": "3.12.3",
    "git_available": true,
    "optional_tools": {
      "ruff": false,
      "vulture": false,
      "pyright": false,
      "jscpd": false
    }
  }
}
```

### install.sh Modification Template
```bash
# ---- ADD AT TOP (for simple tools missing python3 check) ----
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi

# ---- ADD AT END (before summary, after all copies and sed) ----
# Update manifest
TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$TARGET_DIR" \
  --tool "$(basename "$TOOL_SOURCE_DIR")" \
  --source "$TOOL_SOURCE_DIR"
```

### scan-status JSON Output Schema (Recommended)
```json
{
  "mg_cc_tools_version": "0.1.0",
  "target": "/home/user/projects/road-runner",
  "manifest_exists": true,
  "tools": [
    {
      "name": "create-docs",
      "description": "Multi-step documentation pipeline (scan, generate, verify)",
      "status": "update",
      "installed_version": "0.0.9",
      "current_version": "0.1.0",
      "changed_files": [],
      "commands": ["create-docs.md", "create-docs-scan.md", "..."],
      "excluded": false
    },
    {
      "name": "debug-triage",
      "description": "GSD debug workflow with structured triage",
      "status": "available",
      "installed_version": null,
      "current_version": "0.1.0",
      "changed_files": [],
      "commands": ["debug-triage.md"],
      "excluded": false
    }
  ],
  "summary": {
    "installed": 6,
    "total": 11,
    "outdated": 1,
    "modified": 1,
    "current": 4,
    "available": 5,
    "corrupt": 0
  }
}
```

### Test Pattern (Following Existing Convention)
```python
"""Tests for mg-install-lib.py -- unified installer library.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "mg-install-lib.py",
)

class TestScanStatus:
    """scan-status subcommand tests."""

    def _make_tool(self, parent, name, description="Test tool", exclude=False,
                   required=None, optional=None):
        """Create a mock tool directory with tool.toml and install.sh."""
        tool_dir = os.path.join(parent, name)
        os.makedirs(os.path.join(tool_dir, "commands"), exist_ok=True)

        # tool.toml
        toml_lines = [f'[tool]\ndescription = "{description}"']
        if exclude:
            toml_lines.append("exclude = true")
        if required or optional:
            toml_lines.append("\n[preflight]")
            if required:
                toml_lines.append(f'required = {json.dumps(required)}')
            if optional:
                toml_lines.append(f'optional = {json.dumps(optional)}')
        with open(os.path.join(tool_dir, "tool.toml"), "w") as f:
            f.write("\n".join(toml_lines))

        # install.sh (minimal)
        with open(os.path.join(tool_dir, "install.sh"), "w") as f:
            f.write("#!/bin/bash\necho installed\n")

        # command file
        with open(os.path.join(tool_dir, "commands", f"{name}.md"), "w") as f:
            f.write(f"---\nname: mg:{name}\n---\nTest command\n")

        return tool_dir

    def test_discovers_tools_with_toml_and_install_sh(self):
        """Only directories with both tool.toml and install.sh are discovered."""
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            target = os.path.join(tmp, "target")
            os.makedirs(source)
            os.makedirs(os.path.join(target, ".claude"))

            self._make_tool(source, "real-tool")

            # Missing install.sh -- should be ignored
            incomplete = os.path.join(source, "incomplete")
            os.makedirs(incomplete)
            with open(os.path.join(incomplete, "tool.toml"), "w") as f:
                f.write('[tool]\ndescription = "Incomplete"')

            # pyproject.toml
            with open(os.path.join(source, "pyproject.toml"), "w") as f:
                f.write('[project]\nversion = "0.1.0"')

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH, "scan-status",
                 "--source", source, "--target", target],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            tool_names = [t["name"] for t in data["tools"]]
            assert "real-tool" in tool_names
            assert "incomplete" not in tool_names
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `install.sh` per tool | `/mg:install` unified command | Phase 7 | Single entry point for all tool management |
| No staleness tracking | SHA256 source checksums in manifest | Phase 7 | Know immediately if tools are outdated |
| No preflight validation | Structured preflight with fix instructions | Phase 7 | Prevent silent runtime failures |
| No capability tracking | LSP probe + capabilities in manifest | Phase 7 | Tools can adapt behavior based on available capabilities |
| No manifest | Central `.claude/mg-cc-tools.manifest.json` | Phase 7 | Complete record of what's installed, when, from where |

**Deprecated/outdated:**
- Nothing deprecated -- this is a new feature. Existing `install.sh` scripts continue to work standalone but now also update the manifest.

## Open Questions

1. **Checksum scope for non-.md files in commands/**
   - What we know: `create-context/commands/context-template.snapshot` exists and is copied by install.sh
   - What's unclear: Should checksum scope be `commands/*` (all files) or `commands/*.md` (only command files)?
   - Recommendation: Use `commands/*` to match what install.sh actually copies. A changed snapshot file should trigger "Modified" status.

2. **pyproject.toml requires-python update**
   - What we know: Currently `>=3.8`, needs to be at least `>=3.11` for tomllib. CONTEXT says 3.13+.
   - What's unclear: Whether to enforce 3.13+ (stricter) or 3.11+ (minimum viable).
   - Recommendation: Set to `>=3.11` (minimum for tomllib). The preflight check enforces the actual minimum at runtime.

3. **mg-gsd-wrappers install order dependency**
   - What we know: mg-gsd-wrappers/install.sh copies a patch from gsd-patches/patches/. It checks but doesn't fail if gsd-patches isn't installed in the target.
   - What's unclear: Whether `/mg:install` should enforce install ordering.
   - Recommendation: Don't enforce ordering in v1. The existing install.sh already handles the missing case gracefully. Note the dependency in the numbered prompt if both are selected.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python3 -m pytest`) |
| Config file | None (uses pyproject.toml defaults) |
| Quick run command | `python3 -m pytest install/scripts/tests/ -x` |
| Full suite command | `python3 -m pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INST-01 | Tool discovery (toml+install.sh) | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus -x` | Wave 0 |
| INST-02 | tool.toml parsing (all fields) | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestToolMetadata -x` | Wave 0 |
| INST-03 | Staleness detection (5 states) | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestStaleness -x` | Wave 0 |
| INST-04 | Manifest read/write/update | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestManifest -x` | Wave 0 |
| INST-05 | Preflight checks (pass/fail) | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestPreflight -x` | Wave 0 |
| INST-06 | LSP probe | manual-only | N/A (requires claude -p runtime) | N/A |
| INST-07 | Migration/adopt flow | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt -x` | Wave 0 |
| INST-08 | Post-install validation | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestValidate -x` | Wave 0 |
| INST-09 | install.md interactive flow | manual-only | N/A (requires Claude Code session) | N/A |
| INST-10 | install.sh modifications | integration | Run modified install.sh on temp dir, check manifest | Wave 0 |
| INST-11 | Bootstrap install.sh | smoke | Run `install/install.sh --target <tmp>`, verify install.md copied | Wave 0 |
| INST-12 | Full test suite passes | suite | `python3 -m pytest install/scripts/tests/ -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest install/scripts/tests/ -x`
- **Per wave merge:** `python3 -m pytest`
- **Phase gate:** Full suite green + manual road-runner validation

### Wave 0 Gaps
- [ ] `install/scripts/tests/test_mg_install_lib.py` -- covers INST-01 through INST-08, INST-12
- [ ] `install/scripts/tests/__init__.py` -- package marker (if needed by test runner)
- [ ] Framework install: N/A -- pytest already in pyproject.toml dev dependencies

## Inventory of install.sh Modifications

All 11 install.sh scripts need modification. Categorized by complexity:

### Simple (command-only, no python3 check currently): 3 tools
These need BOTH a python3 check AND the manifest update call:
| Tool | Current python3 check | Manifest update needed |
|------|----------------------|----------------------|
| debug-triage | NO | YES |
| update-backlog | NO | YES |
| new-milestone-gsd | NO | YES |

### Medium (already have python3 check): 5 tools
These need ONLY the manifest update call:
| Tool | Has python3 check | Has sed resolution | Has scaffolding |
|------|-------------------|-------------------|-----------------|
| codebase-health | YES | YES (complex) | YES (.mg/health-scan/) |
| create-docs | YES | YES (complex) | YES (.mg/docs/) |
| data-provider | YES (warning only) | YES | YES (.mg/data-provider/) |
| permission-hooks | YES | YES | NO |
| cc-regression-test | YES | YES | NO (settings.json merge) |

### Medium (no python3 check, have other dependencies): 3 tools
These need python3 check AND manifest update:
| Tool | Current dependencies | Special handling |
|------|---------------------|-----------------|
| create-context | None (no python3 check) | Non-.md file in commands/ |
| gsd-patches | None (no python3 check) | Patches directory handling |
| mg-gsd-wrappers | None (no python3 check) | Cross-tool gsd-patches reference |

### tool.toml Files Needed: 13 total
11 existing tools + install tool itself + 1 excluded cc-regression-test = 13 (but install + cc-regression-test both already included in the 11 existing dirs, plus the new `install/` directory):

| Tool | exclude | preflight.required | preflight.optional |
|------|---------|-------------------|-------------------|
| codebase-health | false | ["python3"] | ["ruff", "vulture", "pyright", "jscpd"] |
| create-docs | false | ["python3"] | ["lsp"] |
| create-context | false | ["gsd"] | [] |
| data-provider | false | ["python3"] | [] |
| debug-triage | false | ["gsd"] | [] |
| gsd-patches | false | ["gsd"] | [] |
| mg-gsd-wrappers | false | ["gsd"] | [] |
| new-milestone-gsd | false | ["gsd"] | [] |
| update-backlog | false | ["gsd"] | [] |
| permission-hooks | false | ["python3"] | [] |
| cc-regression-test | true | ["python3"] | [] |
| install | true | ["python3"] | [] |

## Sources

### Primary (HIGH confidence)
- Existing install.sh scripts (11 files) -- read and analyzed in full
- CONCEPT.md (`docs/work-queue/todo/install-command-v1/CONCEPT.md`) -- complete specification
- CONTEXT.md (`.planning/phases/07-install-command/07-CONTEXT.md`) -- locked decisions
- Python stdlib documentation (tomllib, hashlib, fcntl, json, subprocess) -- verified in-process
- pyproject.toml -- version and dependency info

### Secondary (MEDIUM confidence)
- Existing test patterns (`create-docs/scripts/tests/test_*.py`) -- subprocess invocation pattern verified

### Tertiary (LOW confidence)
- None. All findings verified against existing codebase or stdlib.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, verified available on system
- Architecture: HIGH -- patterns derived from existing codebase conventions
- Pitfalls: HIGH -- identified from direct analysis of all 11 install.sh scripts and edge cases in the CONCEPT
- Checksum scope: MEDIUM -- the non-.md file in commands/ is a real edge case that needs a decision

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (stable -- no external dependencies to go stale)
