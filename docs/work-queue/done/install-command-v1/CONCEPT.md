# `/mg:install` — Unified Tool Installer & Manager

## Purpose

A Claude Code slash command that installs, updates, and manages mg-cc-tools in target projects. It replaces the current workflow of manually running individual `install.sh` scripts by providing a single interactive entry point with status tracking, preflight checks, capability probing, and version management.

## Problem Statement

Today, managing mg-cc-tools across projects requires:
- Knowing which tools exist and what they do
- Running individual `install.sh` scripts manually per tool
- No way to check if installed tools are outdated
- No preflight validation (LSP availability, external tool dependencies)
- No post-install validation (unresolved sed placeholders fail silently)
- No record of what was installed or when

The result: silent failures at runtime (check-references.py timing out because LSP isn't available, commands referencing unresolved `{SCRIPTS_DIR}` placeholders, missing external tools degrading scan quality without warning).

---

## Command

| Command | Purpose |
|---|---|
| `/mg:install [target-path]` | Interactive installer — status, install, update, preflight, capabilities |

```yaml
name: mg:install
description: Install, update, and manage mg-cc-tools in target projects
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
```

Runs from the **mg-cc-tools directory**. Target project is `$ARGUMENTS` or selected interactively. This is by design — the installer always knows where its source is (the current working directory), avoiding bidirectional path resolution complexity.

---

## Interactive Flow

### Step 1: Target Project

If `$ARGUMENTS` contains a path, use it. Otherwise, present recent targets:

```
AskUserQuestion (header: "Target", multiSelect: false)
  Q: "Which project do you want to manage tools for?"
  Options:  (dynamically populated from ~/.config/mg-cc-tools/targets.json)
    - "/home/user/projects/road-runner"         <- most recent
    - "/home/user/projects/ai-stock-ranker"     <- previous
    - "Current directory"
    - (Other -> manual path entry)
```

Recent targets stored in `~/.config/mg-cc-tools/targets.json` (lightweight history, updated on each install).

### Step 2: Status Scan

Non-interactive text output. Run `mg-install-lib.py scan-status` which:
1. Discovers tools by scanning all top-level directories for `tool.toml` + `install.sh` (both must exist)
2. Reads target's `.claude/mg-cc-tools.manifest.json` (if exists)
3. Reads project version from `pyproject.toml`
4. Computes SHA256 checksums of source files (pre-sed) for each tool
5. Compares against source checksums recorded in the manifest at install time
6. Checks installed command files still exist on disk (via command-to-tool mapping from source `commands/` dirs)

```
mg-cc-tools (0.3.0) — /home/user/projects/road-runner

  Tool                Description                                      Updated        Status
  ────────────────────────────────────────────────────────────────────────────────────────────────
  create-docs         Documentation pipeline (scan, generate, verify)   2 hours ago    ⚠ Update (0.2.0 → 0.3.0)
  codebase-health     Scan, verify, and fix code health issues          3 days ago     ✓ Current (0.3.0)
  data-provider       Research and map external data field sources       5 days ago     ○ Available
  debug-triage        GSD debug workflow with structured triage          2 weeks ago    ○ Available
  update-backlog      Update GSD backlog after milestone completion      2 weeks ago    ○ Available
  new-milestone-gsd   Create new GSD milestone with backlog review       2 weeks ago    ○ Available
  mg-gsd-wrappers     GSD workflow wrappers (plan, execute, discuss)     1 week ago     ✓ Current (0.3.0)
  gsd-patches         Apply GSD methodology patches                     1 week ago     ✓ Current (0.3.0)
  permission-hooks    Claude Code permission guard hooks                 1 week ago     ✓ Current (0.3.0)
  create-context      Create context snapshots for LLM prompts           4 days ago     ⚠ Modified (2 files)
  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
  install             mg-cc-tools installer (internal)                   1 hour ago     ─ Excluded
  cc-regression-test  Claude Code regression test harness (internal)     1 week ago     ─ Excluded

  Installed: 6/11  |  Outdated: 1  |  Modified: 1  |  Current: 4  |  Available: 5
```

**Status definitions:**
- **Current (version)**: Installed, checksums match, version matches
- **Update (old → new)**: Installed, but project version changed since install
- **Modified (N files)**: Installed, same version, but source file checksums differ from what was recorded at install time (unreleased changes)
- **Corrupt**: Manifest says installed but files missing on disk
- **Available**: Not installed
- **Excluded**: Has `exclude = true` in tool.toml — shown but not included in bulk operations

**"Updated" column**: Derived from `git log -1 --format="%ci" -- <tool-dir>/`, displayed as relative time.

### Step 3: Action Selection

Present numbered options as a normal text prompt. The user types a number or free text for specific tool names.

The options are **context-aware** — they adapt based on the scan results.

**Scenario A: Nothing installed (first time)**
```
What would you like to do?

  [1] Install all tools (recommended)
  [2] Select specific tools

Type a number, or tool names separated by commas:
```

**Scenario B: Some outdated / modified**
```
What would you like to do?

  [1] Update 2 outdated tools (recommended)
  [2] Update outdated + install all missing
  [3] Install missing only (5 tools)
  [4] Check capabilities only

Type a number, tool names, or 'all':
```

**Scenario C: All current**
```
What would you like to do?

  [1] Install remaining 5 tools
  [2] Reinstall all
  [3] Check capabilities only

Type a number, tool names, or 'all':
```

**Free text examples**: `create-docs, codebase-health` or `all` or `pipeline tools`.

This avoids AskUserQuestion's 4-option limit entirely. The LLM parses the user's response — it handles numbered selections, tool names, category names, and natural language ("just the GSD ones") equally well.

### Step 4: Preflight Checks

Aggregate preflight requirements from selected tools' `tool.toml` files. Run checks via `mg-install-lib.py preflight`.

```
Preflight checks:

  ✓ python3    3.13.1    (required by: create-docs, codebase-health, data-provider, permission-hooks)
  ✓ git        2.43.0    (used by: create-docs staleness detection)
  ✓ gsd        1.22.4    (required by: debug-triage, mg-gsd-wrappers, update-backlog, new-milestone-gsd, gsd-patches)
  ✗ ruff       missing   (optional: codebase-health scan degraded)
  ✗ vulture    missing   (optional: codebase-health dead code detection unavailable)

  Required: 3/3 ✓
  Optional: 0/2 (degraded features noted)
```

**Required check fails → hard abort:**
```
  ✗ python3    missing   (required by: create-docs, codebase-health)

  ╔════════════════════════════════════════════════════════════╗
  ║  PREFLIGHT FAILED                                          ║
  ╚════════════════════════════════════════════════════════════╝

  python3 is required but not found.

  To fix:
    Ubuntu/Debian:  sudo apt install python3
    macOS:          brew install python3
    Other:          https://python.org/downloads

  After fixing, re-run /mg:install
```

No interaction — hard stop. Clear fix instructions.

**Optional check fails → warn and continue by default:**

Optional failures are reported but don't block installation. The degraded features are noted in the manifest's capabilities section and surfaced in the summary.

### Step 5: Capability Probe

Runs for every invocation (status, install, update). Uses `claude -p` to probe Claude Code session capabilities. Tested and confirmed working.

```bash
cd /path/to/target && claude -p --output-format json \
  "Try to use the LSP tool to look up any symbol definition in this project. \
   Report ONLY a JSON object: {\"lsp_functional\": true/false, \"languages\": [...]}" \
  2>/dev/null
```

**IMPORTANT**: The probe must run from the **target project directory**, not mg-cc-tools. LSP availability is project-specific — it depends on the target's languages and language server configuration.

Output integrated into the flow:
```
Capabilities:
  ✓ lsp        functional (python, javascript)
```

Or:
```
Capabilities:
  ⚠ lsp        not available
               → create-docs-verify: symbol verification will use extraction only
```

LSP failure is never blocking — noted in capabilities and stored in manifest so tools can read it at runtime.

### Step 6: Execute Installs

For each selected tool, delegate to its existing `install.sh`:

```
Installing tools:

  ◆ create-docs...        ✓  5 commands, 6 scripts, 9 agents, 13 templates
  ◆ codebase-health...    ✓  4 commands, 8 scripts, 7 agents
  ◆ debug-triage...       ✓  1 command
  ◆ update-backlog...     ✓  1 command
```

Each `install.sh` writes its entry to the manifest via `mg-install-lib.py update-manifest` at the end.

### Step 7: Post-Install Validation

Run `mg-install-lib.py validate`:

```
Post-install validation:

  ✓ No unresolved placeholders in installed files
  ✓ All resolved paths readable
  ✓ Workspace scaffolding verified (.mg/docs/, .mg/health-scan/)
```

Validation checks:
1. Grep all installed command/agent files for unresolved `{PLACEHOLDER}` patterns
2. Verify sed-resolved absolute paths point to existing files
3. Check workspace directories created by `--project` installs

If validation fails:
```
  ✗ Unresolved placeholder in create-docs-verify.md: {SCRIPTS_DIR}

  This indicates a bug in create-docs/install.sh sed replacement.
  The tool may not function correctly until this is fixed.
```

### Step 8: Summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 mg-cc-tools ► INSTALL COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Target: /home/user/projects/road-runner

  Installed: 3  |  Updated: 2  |  Unchanged: 4  |  Skipped: 2

  Tool                Action       Commands
  ──────────────────────────────────────────────
  create-docs         Updated      5 commands
  codebase-health     Installed    4 commands
  debug-triage        Installed    1 command
  update-backlog      Installed    1 command
  create-context      Updated      2 commands
  permission-hooks    Unchanged    —
  mg-gsd-wrappers     Unchanged    —
  gsd-patches         Unchanged    —

  Capabilities:
    ✓ LSP functional (python, javascript)
    ⚠ ruff, vulture missing — codebase-health scan degraded

  Manifest: .claude/mg-cc-tools.manifest.json
```

---

## Tool Discovery

### Convention

A tool is any top-level directory in mg-cc-tools that contains **both** `tool.toml` and `install.sh`. Both files must exist — `tool.toml` without `install.sh` is ignored (avoids discovering half-built tools that can't actually be installed). Tools with `exclude = true` are shown in the status table but excluded from bulk operations.

```python
# Discovery logic (in mg-install-lib.py)
for entry in os.scandir(source_root):
    if entry.is_dir():
        toml_path = os.path.join(entry.path, "tool.toml")
        install_path = os.path.join(entry.path, "install.sh")
        if os.path.isfile(toml_path) and os.path.isfile(install_path):
            tool = load_tool_metadata(toml_path)
            tool["name"] = entry.name
            tool["commands"] = discover_commands(entry.path)  # scan commands/ subdir
            if not tool.get("exclude", False):
                available_tools.append(tool)
            else:
                excluded_tools.append(tool)
```

Adding a new tool: create the directory with `install.sh` + `tool.toml`. The installer picks it up on next run.

Removing a tool: delete the directory. The installer notices it's gone. If it was installed in a target, the manifest entry becomes orphaned — the status scan can flag this.

### tool.toml

Each tool directory contains a `tool.toml` metadata file (TOML chosen over JSON for human editability and comments, over YAML for explicit typing and no footguns; `tomllib` is stdlib since Python 3.11):

```toml
# create-docs/tool.toml

[tool]
description = "Multi-step documentation pipeline (scan, generate, verify)"
exclude = false

[preflight]
required = ["python3"]
optional = ["lsp"]
```

**Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `tool.description` | string | yes | One-sentence human-readable description shown in status table |
| `tool.exclude` | bool | no | If `true`, excluded from bulk installs. Default `false`. |
| `preflight.required` | array | no | Check IDs that must pass for install to proceed. Default `[]`. |
| `preflight.optional` | array | no | Check IDs that produce warnings but don't block. Default `[]`. |

Note: `category` was removed. Categories added complexity (AskUserQuestion's 4-option limit, fragile grouping) without proportional value. The numbered-prompt UX handles tool selection without needing categories.

---

## Version Management

### Single Project Version

One version number in `pyproject.toml` — never per-tool versions. This is bumped at milestone boundaries (a deliberate human act). No per-tool version to forget to bump.

```toml
# pyproject.toml
[project]
version = "0.3.0"
```

### Staleness Detection via Source File Checksums

The installer compares **current source files** (pre-sed, in the mg-cc-tools repo) against **source file checksums recorded in the manifest at install time**.

This is a source-to-source comparison — always apples-to-apples. The sed substitution gap doesn't matter because we never compare source files against installed files. We compare source-at-install-time vs source-now.

1. At install time, `mg-install-lib.py update-manifest` checksums the **source files** in the tool directory and records them in the manifest
2. At status check time, `mg-install-lib.py scan-status` recomputes source file checksums and compares against the manifest

This detects "source changed since last install" — the primary staleness signal. It does not detect manual edits to installed files, but that's an edge case and post-install placeholder validation catches the dangerous variant (unresolved `{PLACEHOLDER}` patterns).

**Checksum scope** — which source files to include per tool:

| Include | Exclude |
|---|---|
| `commands/*.md` | `tool.toml` (metadata, not installed) |
| `scripts/*.py`, `scripts/lib/*.py` | `tests/`, `**/tests/` |
| `agents/*.md` | `__pycache__/`, `*.pyc` |
| `references/**/*` | `.pytest_cache/` |
| `install.sh` (install logic changes matter) | |

**Installed file integrity check**: In addition to source checksums, the status scan checks that expected installed files exist on disk. For each tool in the manifest, `scan-status` uses the command-to-tool mapping (derived from scanning the tool's `commands/` directory) to verify the command files are present in the target's `.claude/commands/mg/`.

**Five display states:**

| Scenario | Display |
|---|---|
| Version mismatch (pyproject.toml ≠ manifest) | `⚠ Update (0.2.0 → 0.3.0)` |
| Same version, source checksums differ | `⚠ Modified (N files changed)` |
| Same version, checksums match | `✓ Current (0.3.0)` |
| Manifest entry but installed command files missing | `✗ Corrupt` |
| No manifest entry | `○ Available` |

### "Updated" Column

Derived at display time from git — never stored:

```bash
git log -1 --format="%ci" -- create-docs/
```

Shown as relative time ("2 hours ago", "3 days ago"). Zero maintenance, always accurate.

---

## Manifest

### Location

`.claude/mg-cc-tools.manifest.json` in the target project. Central (not per-tool) — one file for full project status.

**Must be gitignored** — it contains `source_path` (absolute machine-specific path to mg-cc-tools). Add to target project's `.gitignore`.

### Written By

Both `/mg:install` **and** standalone `install.sh` scripts. Every `install.sh` calls `mg-install-lib.py update-manifest` at the end. Python 3 is always available (hard requirement for all tools), and `mg-install-lib.py` is always present in the repo. No `|| true`, no silent failures, no brownfield scenarios.

```bash
# At end of every install.sh — no fallback, no silent skip
python3 "$(cd "$(dirname "$0")" && pwd)/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$INSTALL_DIR" \
  --tool "$(basename "$(cd "$(dirname "$0")" && pwd)")" \
  --source "$(cd "$(dirname "$0")" && pwd)"
```

### Schema

```json
{
  "mg_cc_tools_version": "0.3.0",
  "source_path": "/home/user/mg_projects/mg-cc-tools",
  "last_updated": "2026-03-17T14:30:00Z",
  "tools": {
    "create-docs": {
      "version": "0.3.0",
      "installed_at": "2026-03-17T14:30:00Z",
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
        "commands/create-docs-scan.md": "sha256:789ghi...",
        "scripts/check-references.py": "sha256:jkl012...",
        "agents/verifier.md": "sha256:mno345..."
      }
    },
    "debug-triage": {
      "version": "0.3.0",
      "installed_at": "2026-03-17T14:30:00Z",
      "commands": ["debug-triage.md"],
      "source_checksums": {
        "install.sh": "sha256:pqr678...",
        "commands/debug-triage.md": "sha256:stu901..."
      }
    }
  },
  "capabilities": {
    "lsp": true,
    "lsp_languages": ["python", "javascript"],
    "python_version": "3.13.1",
    "git_available": true,
    "optional_tools": {
      "ruff": false,
      "vulture": false,
      "pyright": true,
      "jscpd": false
    }
  }
}
```

The `source_checksums` keys are paths **relative to the tool's source directory** in mg-cc-tools (e.g., `commands/create-docs.md` means `create-docs/commands/create-docs.md`).

The `commands` array lists the command `.md` filenames installed to `.claude/commands/mg/`. This serves as the **command-to-tool mapping** — used for integrity checks (verify files exist in target) and migration (map existing installed commands back to their source tool).

### Migration

For projects that already have tools installed before the manifest existed: the first `/mg:install` status scan uses the **command-to-tool mapping** to detect pre-existing installations. For each discovered tool in mg-cc-tools, `scan-status` scans the tool's `commands/` directory to get its command file names, then checks if those files exist in the target's `.claude/commands/mg/`. If all of a tool's commands are present, it's considered installed but untracked.

The `adopt` subcommand then builds a manifest entry by checksumming the current source files — effectively treating the installed version as "whatever the current source is." On subsequent runs, normal staleness detection kicks in. The user sees adopted tools as "Current" (if source hasn't changed since adoption) or "Modified"/"Update" (if source has changed).

---

## Preflight Check Registry

Checks are declared per-tool in `tool.toml` by ID. The actual check logic, version parsing, and fix instructions live in `mg-install-lib.py` as a built-in registry.

### Registry Structure (in mg-install-lib.py)

```python
CHECKS = {
    "python3": {
        "command": "python3 --version",
        "parse_version": r"Python (\d+\.\d+\.\d+)",
        "min_version": "3.13",
        "fix": {
            "apt": "sudo apt install python3",
            "brew": "brew install python3",
            "url": "https://python.org/downloads",
        },
    },
    "git": {
        "command": "git --version",
        "parse_version": r"git version (\d+\.\d+\.\d+)",
        "fix": {
            "apt": "sudo apt install git",
            "brew": "brew install git",
        },
    },
    "gsd": {
        "type": "path_exists",
        "path": "{target}/.claude/get-shit-done",
        "fix": {
            "manual": "Install GSD: https://github.com/gsd-build/get-shit-done",
        },
    },
    "lsp": {
        "type": "claude_probe",
        "prompt": "Try LSP go-to-definition on any symbol. Report JSON: {\"lsp_functional\": bool, \"languages\": [...]}",
    },
    "ruff": {
        "command": "ruff --version",
        "fix": {"pip": "pip install ruff"},
    },
    "vulture": {
        "command": "vulture --version",
        "fix": {"pip": "pip install vulture"},
    },
    "pyright": {
        "command": "pyright --version",
        "fix": {"pip": "pip install pyright"},
    },
    "jscpd": {
        "command": "jscpd --version",
        "fix": {"npm": "npm install -g jscpd"},
    },
}
```

Adding a new check: one entry in the registry. Tools reference it by ID in `tool.toml`.

---

## Responsibility Split

### install.md (the LLM command prompt)

Orchestration, presentation, user interaction:
- Parse target from arguments or ask via AskUserQuestion
- Call `mg-install-lib.py` subcommands for data (they return JSON)
- Present status table and preflight results as formatted text
- Present numbered options and parse user's response (number, tool names, or free text)
- Call individual `install.sh` scripts via Bash
- Run `claude -p` for LSP capability probe
- Handle errors and present fix instructions

### mg-install-lib.py (the Python script)

Deterministic operations, structured JSON output to stdout:
- `scan-status` — discover tools (scan dirs for tool.toml + install.sh), read manifest, compute source checksums, compare against manifest, check installed command files exist, output JSON
- `preflight` — run checks for given tool list, output JSON with pass/fail/version/fix per check
- `update-manifest` — checksum source files for one tool (using checksum scope rules), record source checksums + command list + version in manifest
- `validate` — grep installed command/agent files for unresolved `{PLACEHOLDER}` patterns, check resolved paths exist
- `adopt` — use command-to-tool mapping to detect pre-existing installs, build manifest entries from current source checksums

All subcommands output JSON to stdout. Human-readable formatting is the LLM's job.

---

## File Structure

### In mg-cc-tools repo

```
install/
├── tool.toml                   <- metadata (exclude = true)
├── install.sh                  <- self-installs /mg:install into mg-cc-tools/.claude/
├── commands/
│   └── install.md              <- the slash command prompt
└── scripts/
    └── mg-install-lib.py       <- checksums, manifest, preflight, validation

<every-tool>/
├── tool.toml                   <- NEW: metadata for the installer
├── install.sh                  <- MODIFIED: adds manifest update call at end
├── commands/
└── [agents/|scripts/|references/]
```

### In target project (after install)

```
.claude/
├── mg-cc-tools.manifest.json   <- central manifest (gitignored)
├── commands/mg/
│   ├── create-docs.md
│   ├── create-docs-scan.md
│   ├── ...
│   └── debug-triage.md
├── create-docs/                <- tool support files
│   ├── agents/
│   ├── scripts/
│   └── references/
└── codebase-health/
    ├── agents/
    ├── scripts/
    └── references/
```

### Bootstrap

The installer self-installs. Running `install/install.sh` copies `install.md` into mg-cc-tools's own `.claude/commands/mg/`. After that, `/mg:install` is available when Claude Code is opened in the mg-cc-tools directory.

For new machine setup:
```bash
cd mg-cc-tools
./install/install.sh    # bootstrap the installer
# Then use /mg:install interactively for everything else
```

---

## Changes to Existing install.sh Scripts

Every `install.sh` gets:

### 1. Python 3 check (for the 3 simple tools that currently lack it)

```bash
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi
```

### 2. Manifest update (at the end, after all copies and sed — no fallback)

```bash
# Update manifest — hard requirement, no || true
python3 "$(cd "$(dirname "$0")" && pwd)/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$INSTALL_DIR" \
  --tool "$(basename "$(cd "$(dirname "$0")" && pwd)")" \
  --source "$(cd "$(dirname "$0")" && pwd)"
```

This is not best-effort. If `mg-install-lib.py` is missing or fails, the install fails. This enforces the invariant that every install updates the manifest — no brownfield scenarios.

---

## Excluded Tools

Two tools are internal and excluded from default installs:

| Tool | Reason |
|---|---|
| `install` | The installer itself — meta-tool, only runs from mg-cc-tools |
| `cc-regression-test` | Test harness for Claude Code behavior — developer-only, modifies settings.json |

Excluded tools:
- Shown in status table (separated by a dashed line, marked `─ Excluded`)
- Not included in "Install all" or bulk operations
- Can be explicitly installed by typing the tool name

---

## Open Items for Implementation

1. **Target history** — `~/.config/mg-cc-tools/targets.json` schema and update logic
2. **mg-install-lib.py JSON output schemas** — exact structure for each subcommand's stdout
3. **Concurrent manifest writes** — if two `install.sh` run in parallel, manifest could corrupt. Use file locking in `mg-install-lib.py`.
4. **Uninstall** — not in v1. Keep focused on install/update/status.
5. **Global install support** — not in v1. Per-project only.

## Deferred to v2

- **Installed file integrity** — checksum installed (post-sed) files to detect manual edits. v1 relies on source checksums for staleness and placeholder validation for integrity.
- **Uninstall / cleanup** — remove tool files and manifest entries from target projects.
- **Global install** — extend to support `--global` targeting `~/.claude/`.
