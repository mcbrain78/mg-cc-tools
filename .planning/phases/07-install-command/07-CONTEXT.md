# Phase 7: Install Command - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning
**Source:** Merged — context import (CONCEPT.md) + interactive discussion

<domain>
## Phase Boundary

Build `/mg:install` — a unified Claude Code slash command that installs, updates, and manages mg-cc-tools in target projects. Replaces the current workflow of running individual `install.sh` scripts manually. Provides status tracking, version management, preflight checks, capability probing, and post-install validation. Runs from mg-cc-tools directory, targets other projects.

</domain>

<decisions>
## Implementation Decisions

### Command structure
- Single slash command: `/mg:install [target-path]`
- Frontmatter: `allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion`
- Runs from mg-cc-tools directory only — source is always `./`, no bidirectional path resolution
- Target project is `$ARGUMENTS` or selected interactively via AskUserQuestion

### Tool discovery
- Dynamic: scan all top-level directories for `tool.toml` + `install.sh` (both must exist)
- Directories without both files are ignored (avoids discovering half-built tools)
- `discover_commands()` scans each tool's `commands/` subdir to build command-to-tool mapping
- No hardcoded tool list anywhere — adding a tool = creating directory with `tool.toml` + `install.sh`

### Tool metadata format
- TOML format (`tool.toml`) — chosen over JSON (no comments) and YAML (implicit typing footguns)
- `tomllib` is stdlib since Python 3.11, we require Python 3.13+
- Fields: `tool.description` (string, required), `tool.exclude` (bool, default false), `preflight.required` (array), `preflight.optional` (array)
- No `category` field — removed because AskUserQuestion has 4-option limit making categories fragile, and numbered-prompt UX handles selection without them

### Interactive flow
- Step 1 (target): AskUserQuestion with recent targets from `~/.config/mg-cc-tools/targets.json`
- Step 2 (status): Non-interactive text table output from `mg-install-lib.py scan-status`
- Step 3 (action): Numbered text prompt — NOT AskUserQuestion. User types number, tool names, or free text. LLM parses the response. Context-aware options adapt to scan results (3 scenarios: nothing installed, some outdated, all current)
- Step 4 (preflight): Non-interactive unless required check fails (hard abort with fix instructions)
- Step 5 (capability probe): `claude -p` from TARGET directory for LSP check. Runs on every invocation.
- Step 6 (install): Delegate to each tool's existing `install.sh`
- Step 7 (validation): Grep for unresolved `{PLACEHOLDER}` patterns, verify resolved paths
- Step 8 (summary): Status table with actions taken, capabilities, manifest location

### Version management
- Single project version from `pyproject.toml` — never per-tool versions
- Bumped at milestone boundaries only (deliberate human act, not per-commit)
- No version to forget to bump — eliminates the "Claude forgot to increment" problem

### Staleness detection
- SHA256 checksums of **source files** (pre-sed) compared source-to-source (source-at-install-time vs source-now)
- Never compare source vs installed files — they differ due to sed resolution
- Checksum scope includes: `commands/*.md`, `scripts/*.py`, `scripts/lib/*.py`, `agents/*.md`, `references/**/*`, `install.sh`
- Checksum scope excludes: `tool.toml`, `tests/`, `**/tests/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`
- Five display states: Current, Update (version mismatch), Modified (same version, checksums differ), Corrupt (files missing), Available (not installed)
- Installed file integrity via command existence check (not content hashing) using command-to-tool mapping
- "Updated" column derived from `git log -1` at display time, never stored

### Manifest
- Location: `.claude/mg-cc-tools.manifest.json` in target project (central, not per-tool)
- Must be gitignored — contains absolute `source_path`
- Written by BOTH `/mg:install` AND standalone `install.sh` — no brownfield scenarios
- Every `install.sh` calls `mg-install-lib.py update-manifest` at the end — no `|| true`, no fallback. If it fails, install fails.
- Schema includes: `mg_cc_tools_version`, `source_path`, `last_updated`, per-tool `version`, `installed_at`, `commands` array (command-to-tool mapping), `source_checksums`, and `capabilities` section (LSP, python version, optional tools)

### Manifest update in install.sh
- All 11 install.sh scripts get the manifest update call
- 3 simple tools (debug-triage, update-backlog, new-milestone-gsd) also get python3 check added
- Python 3 is a hard requirement for ALL tools universally
- Path to mg-install-lib.py: `$(cd "$(dirname "$0")" && pwd)/../install/scripts/mg-install-lib.py`

### Preflight checks
- Declared per-tool in `tool.toml` by check ID (e.g., `required = ["python3"]`)
- Check logic, version parsing, and fix instructions live in `mg-install-lib.py` as built-in CHECKS registry
- Check types: command-based (python3, git, ruff, vulture, pyright, jscpd), path-exists (gsd), claude-probe (lsp)
- Required check failure = hard abort with per-platform fix instructions
- Optional check failure = warn, continue, note degraded features in manifest capabilities

### Capability probe (LSP)
- Uses `claude -p --output-format json` to probe LSP availability
- Must run from **target project directory** (not mg-cc-tools) — LSP is project-specific
- Runs on every invocation (status, install, update) — cost (~$0.03) is marginal vs daily Claude usage
- Result stored in manifest `capabilities` section so tools can read it at runtime
- Never blocking — LSP unavailability is noted but doesn't prevent install

### Migration (pre-manifest projects)
- First `/mg:install` on a project without manifest uses command-to-tool mapping to detect pre-existing installs
- For each tool: scan its `commands/` dir for filenames, check if those files exist in target's `.claude/commands/mg/`
- If all commands present → tool is "installed but untracked"
- `adopt` subcommand builds manifest entries using current source checksums
- Adopted tools show as "Current" or "Outdated" on subsequent runs — no special state

### Post-install validation
- Grep all installed command/agent files for unresolved `{PLACEHOLDER}` patterns (catches sed failures)
- Verify sed-resolved absolute paths point to existing files
- Check workspace directories (.mg/docs/, .mg/health-scan/) created by `--project` installs

### Excluded tools
- `install` (exclude = true): meta-tool, only runs from mg-cc-tools
- `cc-regression-test` (exclude = true): developer-only, modifies settings.json
- Shown in status table below separator, marked `─ Excluded`
- Not included in "Install all" or bulk operations
- Can be explicitly installed by typing the tool name

### Responsibility split
- `install.md` (LLM prompt): orchestration, presentation, AskUserQuestion, numbered prompts, calling install.sh, claude -p probe
- `mg-install-lib.py` (Python script): scan-status, preflight, update-manifest, validate, adopt — all output JSON to stdout

### Bootstrap
- `install/install.sh` self-installs the `/mg:install` command into mg-cc-tools's own `.claude/commands/mg/`
- New machine setup: `cd mg-cc-tools && ./install/install.sh` then use `/mg:install` for everything else

### Validation approach
- Road-runner is the validation target (consistent with phases 3-5)
- First run on road-runner tests the migration/adopt flow — road-runner already has tools installed without a manifest
- Human-verify checkpoint (not automated) — interactive commands can't be unit-tested
- Validation covers: 1) bootstrap installer, 2) run /mg:install on road-runner (should detect + adopt existing tools, show status), 3) modify a source file and re-run (should show "Modified"), 4) verify preflight + LSP probe work

### Testing depth
- Full pytest suite for mg-install-lib.py — all 5 subcommands tested (scan-status, preflight, update-manifest, validate, adopt)
- Tests use temp directories with mock tool structures (tool.toml + install.sh + commands/) — isolated, fast, no side effects
- Follows existing `scripts/tests/test_*.py` pattern with pytest fixtures

### Claude's Discretion
- Exact JSON output schemas for each mg-install-lib.py subcommand
- `~/.config/mg-cc-tools/targets.json` schema and update logic
- File locking strategy for concurrent manifest writes (edge case for v1)
- Internal code organization of mg-install-lib.py (single file vs modules)
- Exact wording of numbered prompts and status table formatting
- Error handling for edge cases (tool directory deleted after discovery, install.sh fails mid-copy)

</decisions>

<specifics>
## Specific Ideas

- Follow the existing mg-cc-tools install.sh pattern (--project, --global, --target modes) for the installer's own install.sh
- Status table mockup in concept shows exact column layout: Tool, Description, Updated, Status
- Numbered prompt scenarios are fully specified for 3 states (nothing installed, some outdated, all current)
- Manifest schema is fully specified with example JSON in concept
- Preflight CHECKS registry is fully specified with all 8 current checks
- See `docs/work-queue/todo/install-command-v1/CONCEPT.md` for complete specification

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- All 11 existing `install.sh` scripts: established pattern for `--project/--global/--target` modes, sed resolution, file validation
- `codebase-health/install.sh`: exemplar of complex install with agents, scripts, references, workspace scaffolding
- `pyproject.toml`: contains the single project version used for version tracking

### Established Patterns
- All install.sh scripts follow identical argument parsing (`--project/--global/--target`)
- Sed placeholder resolution: `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `{TEMPLATES_DIR}` etc. — install.sh replaces these with absolute paths
- Workspace scaffolding: `--project` mode creates `.mg/<tool>/` directories with config files
- Python scripts use stdlib only — no pip dependencies

### Integration Points
- Every existing install.sh will be modified (add python3 check + manifest update call)
- `install/scripts/mg-install-lib.py` is referenced from all 11 install.sh via relative path `../install/scripts/mg-install-lib.py`
- Manifest written to target's `.claude/mg-cc-tools.manifest.json` — shared by all tools

</code_context>

<deferred>
## Deferred Ideas

- Installed file integrity checksums (post-sed) to detect manual edits — v2
- Uninstall / cleanup (remove tool files and manifest entries) — v2
- Global install support (`--global` targeting `~/.claude/`) — v2
- Categories in tool.toml for grouping — removed from design, may revisit if tool count grows significantly

</deferred>

---

*Phase: 07-install-command*
*Context gathered: 2026-03-17 via context import*
