# Phase 1: Foundation & Infrastructure - Research

**Researched:** 2026-03-16
**Domain:** Python CLI scripts (stdlib-only), bash install scripts, JSON schema definition, project scaffolding
**Confidence:** HIGH

## Summary

Phase 1 builds the foundational infrastructure for the `/mg:create-docs` tool: five Python scripts, a JSON schema definition, a style guide, an install script, project scaffolding, and a configuration system. The entire domain is well-understood because **the codebase already contains a mature reference implementation** in the `codebase-health/` tool that follows the exact same architectural patterns. Every deliverable in this phase has a direct analog in codebase-health that can be studied and adapted.

The Python scripts use only stdlib (no pip dependencies), follow an established pattern of atomic JSON I/O via `argparse` + `json` + `os.replace()`, and are tested with pytest. The install script follows the three-mode (`--project`, `--global`, `--target`) pattern with sed-based path resolution. The configuration system uses field-level merge (project overrides global, missing fields fall back to defaults). All of these patterns are proven and running in production.

The key risk area is the **path conflict** noted in CONTEXT.md: the milestone discussion decided the install path should be `.claude/create-docs/` (not `.claude/docs/` as referenced in the DESIGN.md and some CONTEXT.md sections). This must be resolved consistently across all deliverables.

**Primary recommendation:** Mirror `codebase-health/` patterns exactly for install.sh, Python script structure, schema format, and config layering. The tool directory should be `create-docs/` in the source repo, installing to `.claude/create-docs/` in target projects, with workspace at `.mg/docs/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `add-note.py` -- Atomic append to `notes-inbox.json`. Uses only stdlib.
- `classify-note.py` -- Deterministic heuristics for note classification (audience -> document -> section with confidence level)
- `check-references.py` -- Verify file paths and symbol names mentioned in docs exist in the codebase
- `merge-scan.py` -- Merge per-audience scan results into single `docs-scan.json`
- `staleness-check.py` -- Git-based section freshness analysis (which source files changed since section was last generated)
- All scripts live in `scripts/` with a shared `lib/` for JSON I/O and git helpers
- Python stdlib only -- no pip dependencies
- Full `docs-scan.json` schema defined in `references/schema.md` (following codebase-health pattern)
- Key top-level fields: `project`, `scan_date`, `root_path`, `mode` (initial|update), `project_model`, `source_material_index`, `staleness_report`, `note_classifications`, `gap_analysis`, `gsd_context`
- Inbox schema: notes with id (NOTE-001 format), text, added (ISO timestamp), context (phase, file), classification (audience, document, section, confidence), status (pending/integrated)
- Cross-audience writing conventions in `references/style-guide.md`
- Install script: three modes `--project [<dir>]`, `--global`, `--target <path>`
- Install destinations: commands -> `.claude/commands/mg/`, agents -> `.claude/create-docs/agents/`, scripts -> `.claude/create-docs/scripts/`, references -> `.claude/create-docs/references/`
- Six sed placeholder replacements: `agents/`, `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}`, `{GLOBAL_CONFIG}`, `references/schema.md`, `references/style-guide.md`
- Project scaffolding: `.mg/docs/` with `.docs.config.json`, `notes-inbox.json` (empty), `scan-logs/` directory
- Config: `.docs.config.json` with `docs_dir`, `audiences` (4 audiences, each with enabled flag and document list), `shared_documents`, `custom_documents`, `gsd_integration`
- Tool directory in mg-cc-tools: `create-docs/`
- Install path: `.claude/create-docs/` (updated from `.claude/docs/` per milestone discussion)
- `/mg:add-docs` command lives inside `create-docs/` tool directory
- Custom documents (DOC-04) deferred to v2 -- keep `custom_documents` in config schema as placeholder but don't implement generation
- Road-runner validation baked into phase success criteria

### Claude's Discretion
- Internal code organization within scripts (module structure, shared utilities design)
- Error handling patterns across scripts
- Logging format and verbosity
- Test structure for Python scripts
- Schema format choice: JSON Schema vs structured markdown in `references/schema.md`
- Style guide organization and section structure

### Deferred Ideas (OUT OF SCOPE)
- Schema drift detection (STL-01) and terminology drift detection (STL-02) -- v2 requirements
- Backlog integration (BKL-01) -- v2 requirement
- Testing strategy details -- cross-cutting open item, applies to all phases
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INF-01 | Python script: add-note.py (atomic append to notes-inbox.json) | Direct analog: `codebase-health/scripts/add-finding.py` -- same atomic JSON append pattern via `argparse` + `json.load` + `os.replace()`. Adapt for notes-inbox.json schema (id, text, added, context, classification, status) |
| INF-02 | Python script: classify-note.py (deterministic heuristics for note classification) | New script, no direct analog. Keyword/pattern matching heuristics to map note text to audience/document/section/confidence. Outputs JSON classification object |
| INF-03 | Python script: check-references.py (verify file paths and symbol names in docs exist) | Partially analogous to `codebase-health/scripts/lib/imports.py` for symbol resolution patterns. Walks markdown files, extracts file paths and symbol references, checks existence against codebase |
| INF-04 | Python script: merge-scan.py (merge per-audience scan results into docs-scan.json) | Direct analog: `codebase-health/scripts/merge-findings.py` -- same merge pattern (collect per-category JSON files, deduplicate, compute summary, write final output). Adapt for docs-scan.json schema |
| INF-05 | Python script: staleness-check.py (git-based section freshness analysis) | New script. Uses `subprocess.run(["git", "log", ...])` to check if source files changed since docs-meta timestamps. No external analog but git operations are stdlib-compatible via subprocess |
| INF-06 | Schema definition: docs-scan.json format in references/schema.md | Direct analog: `codebase-health/references/schema.md` -- structured markdown documenting JSON contract with field descriptions, example values, and conventions. Schema fields fully specified in CONTEXT.md |
| INF-07 | Style guide: cross-audience writing conventions in references/style-guide.md | No direct analog. Content derived from DESIGN.md format conventions per audience. Claude's discretion on organization |
| INF-08 | install.sh with --project, --global, --target modes and sed path resolution | Direct analog: `codebase-health/install.sh` -- identical three-mode pattern, sed replacements, validation, scaffolding. Adapt for create-docs paths and six placeholder replacements |
| INF-09 | Project scaffolding: .mg/docs/ with config, empty inbox, scan-logs directory | Direct analog: codebase-health install.sh lines 225-253 -- scaffolds `.mg/health-scan/` with config and ignore file. Adapt for `.mg/docs/` with config, inbox JSON, and scan-logs |
| INF-10 | Config: .docs.config.json with audience enable/disable, custom documents, docs_dir override | Direct analog: codebase-health config layering (global defaults installed to references/, project overrides at `.mg/`). Field-level merge, missing falls back to defaults. Config schema fully specified in CONTEXT.md |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.8+ (runtime 3.12 on dev machine) | Script runtime | Project minimum per `pyproject.toml`, stdlib-only constraint |
| argparse | stdlib | CLI argument parsing | Every codebase-health script uses this pattern |
| json | stdlib | JSON I/O for all data contracts | Atomic read/write pattern established in add-finding.py |
| os | stdlib | File operations, path handling, atomic replace | `os.replace()` for atomic writes, `os.makedirs()` for directory creation |
| subprocess | stdlib | Git operations (staleness-check.py) | Required for `git log`/`git diff` queries |
| datetime | stdlib | ISO timestamps for scan dates and note timestamps | `datetime.now(timezone.utc).isoformat()` pattern from merge-findings.py |
| glob | stdlib | File pattern matching (merge-scan.py) | Same pattern as merge-findings.py for collecting scan JSON files |
| re | stdlib | Regex for reference extraction (check-references.py) | Markdown parsing for file paths and symbol names |
| pathlib | stdlib | Path manipulation | Used alongside os.path in existing scripts |
| bash | system | Install script | All mg-cc-tools install scripts are bash |
| sed | system | Path resolution at install time | Established pattern for placeholder replacement |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 (dev) | Test runner | Testing all Python scripts |
| ruff | latest (dev) | Linter | Code quality checks |
| tempfile | stdlib | Temp directories for testing | Scripts that do file I/O need temp dirs in tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse | click/typer | External dependency violates stdlib-only constraint |
| os.replace atomic write | direct file.write | os.replace is atomic on POSIX; direct write risks corruption on interruption |
| subprocess for git | gitpython | External dependency violates stdlib-only constraint |
| Structured markdown schema | JSON Schema in .json file | Markdown matches codebase-health pattern and is LLM-readable; JSON Schema would require a validator dependency |

## Architecture Patterns

### Recommended Project Structure
```
create-docs/
├── install.sh                    # Three-mode installer with sed path resolution
├── commands/                     # Slash command .md files (Phase 5 -- not this phase)
│   ├── create-docs.md            # Router (Phase 5)
│   ├── create-docs-scan.md       # Scan step (Phase 3)
│   ├── create-docs-generate.md   # Generate step (Phase 4)
│   ├── create-docs-verify.md     # Verify step (Phase 5)
│   └── add-docs.md               # Note capture (Phase 5)
├── agents/                       # Agent definitions (Phase 2 -- not this phase)
├── scripts/                      # Python helpers (THIS PHASE)
│   ├── add-note.py               # INF-01: Atomic append to notes-inbox.json
│   ├── classify-note.py          # INF-02: Deterministic note classification
│   ├── check-references.py       # INF-03: Verify file paths and symbols
│   ├── merge-scan.py             # INF-04: Merge per-audience scan results
│   ├── staleness-check.py        # INF-05: Git-based section freshness
│   ├── lib/                      # Shared utilities
│   │   ├── __init__.py           # Package marker
│   │   ├── json_io.py            # Atomic JSON load/save helpers
│   │   └── git_helpers.py        # Git subprocess wrappers
│   └── tests/                    # pytest test suite
│       ├── __init__.py           # Package marker
│       ├── test_add_note.py
│       ├── test_classify_note.py
│       ├── test_check_references.py
│       ├── test_merge_scan.py
│       └── test_staleness_check.py
└── references/                   # Static reference files (THIS PHASE)
    ├── schema.md                 # INF-06: docs-scan.json data contract
    ├── style-guide.md            # INF-07: Cross-audience writing conventions
    └── .docs.config.json         # INF-10: Global default configuration
```

### Pattern 1: Atomic JSON I/O (from codebase-health)
**What:** All JSON file writes use a temp-file + os.replace pattern for atomicity
**When to use:** Every script that writes JSON output
**Example:**
```python
# Source: codebase-health/scripts/add-finding.py
def load_json(path):
    """Load a JSON file, or return default if not found."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    """Atomic write: write to .tmp then replace."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
```

### Pattern 2: argparse CLI Script Structure (from codebase-health)
**What:** Each script is a standalone CLI tool with argparse, validation, and stderr output
**When to use:** All five Python scripts
**Example:**
```python
# Source: codebase-health/scripts/add-finding.py (adapted)
#!/usr/bin/env python3
"""Brief description of what this script does.

Usage:
    python3 script-name.py --arg1 value --arg2 value

Atomic writes via temp file + os.replace(). Zero external dependencies.
"""
import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--output", required=True, help="...")
    # ... more args
    args = parser.parse_args()

    # Validate inputs
    # Process
    # Write output atomically

    print(f"Result message", file=sys.stderr)

if __name__ == "__main__":
    main()
```

### Pattern 3: Config Layering (from codebase-health)
**What:** Global defaults + project overrides with field-level merge
**When to use:** Configuration loading in any command that reads `.docs.config.json`
**Example:**
```python
# Field-level merge: project fields override global, missing fall back
def load_config(project_config_path, global_config_path):
    """Load config with project overrides over global defaults."""
    global_config = load_json(global_config_path) or {}
    project_config = load_json(project_config_path) or {}

    # Shallow merge: project keys override global keys
    merged = {**global_config, **project_config}
    return merged
```

### Pattern 4: Install Script Three-Mode Pattern (from codebase-health)
**What:** `--project [<dir>]`, `--global`, `--target <path>` with validation and sed replacements
**When to use:** The install.sh for create-docs
**Reference:** `codebase-health/install.sh` (289 lines, fully functional)

### Pattern 5: Shared Library Module
**What:** Common utilities extracted to `scripts/lib/` to avoid duplication across scripts
**When to use:** JSON I/O helpers and git subprocess wrappers used by multiple scripts
**Example:**
```python
# scripts/lib/json_io.py
"""Shared JSON I/O utilities for create-docs scripts.

Zero external dependencies -- stdlib only.
"""
import json
import os

def load_json(path, default=None):
    """Load JSON from path, returning default if file doesn't exist."""
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    """Atomic write JSON via temp file + os.replace."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
```

### Anti-Patterns to Avoid
- **Non-atomic JSON writes:** Never use `open(path, "w")` directly for JSON output. Always use temp + `os.replace()` pattern. Interrupted writes corrupt the file otherwise.
- **External dependencies in scripts:** All scripts MUST use only Python stdlib. The `pyproject.toml` has zero runtime dependencies.
- **Hardcoded paths in command/agent files:** Use placeholders (`{SCRIPTS_DIR}`, `references/schema.md`, etc.) that get sed-resolved at install time.
- **Inline JSON construction in LLM prompts:** The purpose of Python scripts is to avoid LLM hand-writing JSON. Scripts validate inputs and produce correct output.
- **Mixed concerns in scripts:** Each script does one thing. Don't combine add-note and classify-note into one script.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file writes | Custom locking mechanism | `os.replace()` via temp file | POSIX atomic on same filesystem; proven in codebase-health |
| CLI argument parsing | Manual `sys.argv` parsing | `argparse` | Validates types, generates help, handles errors |
| Install script modes | Custom argument handling | Copy codebase-health's `while/case` pattern | Battle-tested, handles edge cases (optional path after --project) |
| Config merge | Deep recursive merge | Shallow `{**global, **project}` merge | Matches codebase-health; field-level is sufficient for flat config |
| Git operations | Manual git command construction | Dedicated `lib/git_helpers.py` | Centralizes subprocess calls, error handling, encoding |
| JSON schema documentation | JSON Schema validator + .json file | Structured markdown (like codebase-health schema.md) | LLM-readable, no validator dependency, proven format |
| Note ID generation | UUID or random | Sequential `NOTE-{NNN}` format | Human-readable, deterministic, matches finding ID pattern (F001) |
| Timestamp generation | Manual string formatting | `datetime.now(timezone.utc).isoformat()` | Timezone-aware ISO 8601, consistent with codebase-health |

**Key insight:** Every infrastructure piece in this phase has a working reference implementation in codebase-health. Adapting proven patterns is faster and more reliable than designing from scratch.

## Common Pitfalls

### Pitfall 1: Path Conflict Between DESIGN.md and Milestone Discussion
**What goes wrong:** CONTEXT.md notes a conflict -- some sections reference `.claude/docs/` while the milestone discussion decided on `.claude/create-docs/`. Using inconsistent paths breaks install.sh sed replacements and LLM resource resolution.
**Why it happens:** The DESIGN.md was written before the milestone discussion renamed the install path.
**How to avoid:** Use `.claude/create-docs/` everywhere. The source directory is `create-docs/` and the install target is `.claude/create-docs/`. The workspace remains `.mg/docs/` (no conflict there).
**Warning signs:** Any reference to `.claude/docs/agents/` or `.claude/docs/scripts/` in install.sh or command files is using the old path.

### Pitfall 2: Command Files Without Placeholder Stubs
**What goes wrong:** Phase 1 only builds infrastructure (scripts, schema, config, install.sh). But install.sh needs command .md files to validate and copy. If command files don't exist yet, install.sh fails.
**Why it happens:** Commands are built in Phases 3-5, but install.sh is Phase 1.
**How to avoid:** Create minimal stub command files in `create-docs/commands/` with frontmatter only (name, description, allowed-tools) and a placeholder body. The install script can validate and copy these. Phase 3-5 fills in the actual content.
**Warning signs:** `install.sh` validation loop fails because command files don't exist.

### Pitfall 3: Script lib/ Import Path Issues
**What goes wrong:** Python scripts in `scripts/` can't import from `scripts/lib/` when invoked from arbitrary working directories.
**Why it happens:** Python resolves imports relative to the script's directory, but subprocess calls may use different working directories.
**How to avoid:** Each script should add its own directory to `sys.path` at the top:
```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
Or use relative imports within the lib package. The codebase-health scripts handle this by having `lib/` alongside the scripts and using `sys.path.insert`.
**Warning signs:** `ModuleNotFoundError: No module named 'lib'` when running scripts via absolute path.

### Pitfall 4: Kebab-Case Script Filenames and Test Imports
**What goes wrong:** Python scripts use kebab-case filenames (e.g., `add-note.py`), which can't be imported with regular `import` statements.
**Why it happens:** mg-cc-tools convention uses kebab-case for scripts (matches `add-finding.py` pattern).
**How to avoid:** Use `importlib.import_module("add-note")` in tests, following the pattern in `permission-hooks/hooks/tests/test_permission_guard.py`. Or use underscore naming for these new scripts (e.g., `add_note.py`) -- Claude's discretion.
**Warning signs:** `SyntaxError` or `ImportError` when trying `import add-note` in test files.

### Pitfall 5: Git Subprocess Encoding Issues in staleness-check.py
**What goes wrong:** `subprocess.run(["git", "log", ...])` returns bytes on some systems, or paths with non-ASCII characters cause encoding errors.
**Why it happens:** Git output encoding varies by platform and configuration.
**How to avoid:** Always pass `encoding="utf-8"` and `errors="replace"` to subprocess calls. Use `text=True` parameter.
```python
result = subprocess.run(
    ["git", "log", "--format=%H %ai", "--", path],
    capture_output=True, text=True, encoding="utf-8"
)
```
**Warning signs:** `UnicodeDecodeError` when processing git output, or `TypeError: a bytes-like object is required`.

### Pitfall 6: Config Merge Depth
**What goes wrong:** Shallow merge of `audiences` field loses nested audience settings. If project config overrides `audiences.devops.enabled = false`, a shallow merge replaces the entire `audiences` dict, losing other audience settings.
**Why it happens:** The codebase-health config is flat (3 fields), but `.docs.config.json` has nested `audiences` with sub-objects.
**How to avoid:** Implement one-level-deeper merge for the `audiences` key: merge each audience's settings individually rather than replacing the whole `audiences` dict.
**Warning signs:** Disabling one audience in project config removes all other audience configurations.

## Code Examples

Verified patterns from the existing codebase:

### add-note.py Core Logic (adapted from add-finding.py)
```python
# Source: codebase-health/scripts/add-finding.py (adapted for notes)
def main():
    parser = argparse.ArgumentParser(
        description="Append a note to notes-inbox.json"
    )
    parser.add_argument("--inbox", required=True, help="Path to notes-inbox.json")
    parser.add_argument("--text", required=True, help="Note text")
    parser.add_argument("--phase", default=None, help="GSD phase context")
    parser.add_argument("--file", default=None, dest="context_file", help="Active file context")
    args = parser.parse_args()

    inbox_path = os.path.abspath(args.inbox)
    inbox = load_json(inbox_path) or {"notes": []}

    # Generate next ID
    existing_ids = [n["id"] for n in inbox["notes"]]
    next_num = len(existing_ids) + 1
    note_id = f"NOTE-{next_num:03d}"

    note = {
        "id": note_id,
        "text": args.text,
        "added": datetime.now(timezone.utc).isoformat(),
        "context": {"phase": args.phase, "file": args.context_file},
        "classification": None,  # Set by classify-note.py
        "status": "pending"
    }

    inbox["notes"].append(note)
    save_json(inbox_path, inbox)
    print(f"Added note {note_id}: {args.text[:60]}...", file=sys.stderr)
```

### Install Script sed Replacement Pattern
```bash
# Source: codebase-health/install.sh (adapted for create-docs)
SCHEMA_ABSOLUTE="${SUPPORT_DIR}/references/schema.md"
STYLE_GUIDE_ABSOLUTE="${SUPPORT_DIR}/references/style-guide.md"
CONFIG_ABSOLUTE="${SUPPORT_DIR}/references/.docs.config.json"
AGENTS_ABSOLUTE="${SUPPORT_DIR}/agents"
SCRIPTS_ABSOLUTE="${SUPPORT_DIR}/scripts"
TEMPLATES_ABSOLUTE="${SUPPORT_DIR}/references/templates"

# Resolve in command files
for cmd_file in "${COMMANDS_DIR}/"*.md; do
  if grep -q 'references/schema.md' "$cmd_file" 2>/dev/null; then
    sed -i "s|references/schema.md|${SCHEMA_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q 'references/style-guide.md' "$cmd_file" 2>/dev/null; then
    sed -i "s|references/style-guide.md|${STYLE_GUIDE_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q '{GLOBAL_CONFIG}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{GLOBAL_CONFIG}|${CONFIG_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q '{SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q '{TEMPLATES_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{TEMPLATES_DIR}|${TEMPLATES_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q 'agents/' "$cmd_file" 2>/dev/null; then
    sed -i "s|agents/|${AGENTS_ABSOLUTE}/|g" "$cmd_file"
  fi
done
```

### Global Default Configuration
```json
{
  "docs_dir": "docs/auto-doc",
  "audiences": {
    "end-users": {
      "enabled": true,
      "documents": ["USER_GUIDE"]
    },
    "developers": {
      "enabled": true,
      "documents": ["ARCHITECTURE", "DEVELOPER_GUIDE", "QUICK_REFERENCE"]
    },
    "agents": {
      "enabled": true,
      "documents": ["SYSTEM_MAP", "CONVENTIONS", "GOTCHAS", "TESTING"]
    },
    "devops": {
      "enabled": true,
      "documents": ["OPERATIONS", "TROUBLESHOOTING"]
    }
  },
  "shared_documents": ["OVERVIEW", "GLOSSARY"],
  "custom_documents": [],
  "gsd_integration": true
}
```

### Test Pattern for File I/O Scripts
```python
# Source: .planning/codebase/TESTING.md (recommended pattern)
import json
import os
import tempfile

class TestAddNote:
    def test_append_to_empty_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox_path = os.path.join(tmp, "notes-inbox.json")
            # Write empty inbox
            with open(inbox_path, "w") as f:
                json.dump({"notes": []}, f)

            # Run script via subprocess
            result = subprocess.run(
                ["python3", SCRIPT_PATH, "--inbox", inbox_path,
                 "--text", "Test note"],
                capture_output=True, text=True
            )
            assert result.returncode == 0

            # Verify output
            with open(inbox_path) as f:
                data = json.load(f)
            assert len(data["notes"]) == 1
            assert data["notes"][0]["id"] == "NOTE-001"
            assert data["notes"][0]["text"] == "Test note"
            assert data["notes"][0]["status"] == "pending"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM hand-writes JSON | Python scripts produce JSON deterministically | Established in codebase-health (2025) | Eliminates JSON corruption from LLM output errors at scale |
| Flat config files | Layered config (global defaults + project overrides) | Established in codebase-health | Projects can customize without modifying installed defaults |
| Direct file writes | Atomic temp + os.replace | Established in codebase-health | Safe against interrupted writes, concurrent access |

**Deprecated/outdated:**
- None. All patterns used are current and stable (Python stdlib, bash, sed).

## Open Questions

1. **Script Filename Convention: Kebab-case or Underscore?**
   - What we know: Existing codebase-health scripts use kebab-case (`add-finding.py`). CONTEXT.md specifies `add-note.py` (kebab-case). Tests require `importlib` workaround for kebab-case.
   - What's unclear: Whether to continue kebab-case (consistency) or switch to underscore (simpler imports in tests and lib/).
   - Recommendation: Use kebab-case for consistency with existing tools. The `importlib` workaround is proven and documented. Alternatively, use underscores for the lib/ modules since they are imported by other scripts (not invoked from CLI).

2. **Schema Format: Structured Markdown vs JSON Schema**
   - What we know: codebase-health uses structured markdown with JSON code blocks showing field descriptions. CONTEXT.md marks this as Claude's discretion.
   - What's unclear: Whether a formal JSON Schema would help validators in later phases.
   - Recommendation: Use structured markdown (like codebase-health's `schema.md`). It's LLM-readable, proven, and doesn't require a validator dependency. If JSON Schema is needed later, it can be generated from the markdown spec.

3. **Stub Command Files for Phase 1 Install Script**
   - What we know: Install.sh validates that command files exist before copying. Commands aren't written until Phases 3-5.
   - What's unclear: What the minimal stubs should contain.
   - Recommendation: Create stub .md files with frontmatter (name, description, allowed-tools) and a `<!-- Content added in Phase N -->` placeholder. Install.sh validates and copies these. Later phases overwrite with real content.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (implicit discovery, no explicit pytest config) |
| Quick run command | `python3 -m pytest create-docs/scripts/tests/ -x` |
| Full suite command | `python3 -m pytest -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INF-01 | add-note.py appends note to inbox with correct schema | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_add_note.py -x` | Wave 0 |
| INF-02 | classify-note.py classifies note text to audience/doc/section | unit | `python3 -m pytest create-docs/scripts/tests/test_classify_note.py -x` | Wave 0 |
| INF-03 | check-references.py detects valid/invalid file paths and symbols | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | Wave 0 |
| INF-04 | merge-scan.py merges per-audience JSON into docs-scan.json | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_merge_scan.py -x` | Wave 0 |
| INF-05 | staleness-check.py detects changed source files via git | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_staleness_check.py -x` | Wave 0 |
| INF-06 | Schema defines all docs-scan.json fields | manual-only | Review `references/schema.md` against CONTEXT.md field list | N/A |
| INF-07 | Style guide contains cross-audience conventions | manual-only | Review `references/style-guide.md` for completeness | N/A |
| INF-08 | install.sh creates correct directory structure and resolves paths | integration | `bash create-docs/install.sh --project /tmp/test-install && ls -R /tmp/test-install/.claude/` | Wave 0 (bash test) |
| INF-09 | Scaffolding creates .mg/docs/ with config, inbox, scan-logs | integration | Tested as part of INF-08 install.sh --project test | Covered by INF-08 |
| INF-10 | Config layering: project overrides global with field-level merge | unit | `python3 -m pytest create-docs/scripts/tests/test_config.py -x` (if config merge logic in lib/) | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest create-docs/scripts/tests/ -x` (quick, single-tool tests)
- **Per wave merge:** `python3 -m pytest -v` (full suite including existing permission-hooks tests)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `create-docs/scripts/tests/__init__.py` -- empty package marker
- [ ] `create-docs/scripts/tests/test_add_note.py` -- covers INF-01
- [ ] `create-docs/scripts/tests/test_classify_note.py` -- covers INF-02
- [ ] `create-docs/scripts/tests/test_check_references.py` -- covers INF-03
- [ ] `create-docs/scripts/tests/test_merge_scan.py` -- covers INF-04
- [ ] `create-docs/scripts/tests/test_staleness_check.py` -- covers INF-05
- [ ] `create-docs/scripts/tests/test_config.py` -- covers INF-10 (if config merge is in lib/)

## Sources

### Primary (HIGH confidence)
- `codebase-health/install.sh` -- Reference install script (289 lines, three-mode pattern, sed replacements, scaffolding)
- `codebase-health/scripts/add-finding.py` -- Reference atomic JSON append script (170 lines)
- `codebase-health/scripts/merge-findings.py` -- Reference merge script (200 lines, deduplication, summary computation)
- `codebase-health/references/schema.md` -- Reference schema format (structured markdown with JSON examples)
- `codebase-health/scripts/lib/` -- Reference shared library (ignore.py, imports.py patterns)
- `.planning/codebase/TESTING.md` -- Project test conventions and patterns
- `docs/work-queue/todo/doc-command/DESIGN.md` -- Full tool design document
- `CLAUDE.md` -- Project conventions, dev setup, architecture

### Secondary (MEDIUM confidence)
- `create-context/install.sh` -- Simpler install script example (136 lines, single sed replacement)
- `permission-hooks/hooks/tests/test_permission_guard.py` -- Test organization pattern (850 lines, class-based, helpers)

### Tertiary (LOW confidence)
- None. All research is based on existing codebase artifacts.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib, all proven in existing codebase
- Architecture: HIGH -- Direct analogs exist for every deliverable in codebase-health
- Pitfalls: HIGH -- Identified from actual code analysis, not speculation
- Validation: MEDIUM -- Test structure is recommended but tests don't exist yet

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable domain -- stdlib Python and bash don't change)
