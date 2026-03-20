# Architecture

**Analysis Date:** 2026-03-15

## Pattern Overview

**Overall:** Plugin Collection with Shared Installation Convention

This is a monorepo of independent Claude Code slash commands (tools) that share a common installation pattern but have no runtime cross-tool dependencies. Each tool is a self-contained directory with markdown-based LLM instruction prompts, optional Python helper scripts, and a bash installer that deploys files into a target project's `.claude/` directory.

**Key Characteristics:**
- Tools are authored here but executed in other projects after installation
- Command files are markdown documents that serve as LLM instruction prompts (not traditional code)
- Install-time path resolution via `sed` replaces relative placeholders with absolute paths
- Two complexity tiers: simple (single command .md) and complex (commands + agents + scripts + schema)
- No runtime dependencies between tools; each is fully self-contained
- Python scripts use only stdlib (zero pip dependencies for runtime)

## Layers

**Command Layer (LLM Instruction Prompts):**
- Purpose: Define slash command behavior as structured markdown prompts consumed by Claude Code
- Location: `<tool>/commands/*.md`
- Contains: YAML frontmatter (`name:`, `description:`, `allowed-tools:`) + step-by-step LLM instructions
- Depends on: Agent files (via embedded content), Python scripts (via `{SCRIPTS_DIR}` placeholder), reference files
- Used by: Claude Code runtime (interprets these as slash command definitions)

**Agent Layer (Subagent Prompts):**
- Purpose: Define specialized subagent behaviors spawned via Claude Code's Task tool
- Location: `codebase-health/agents/*.md`, `data-provider/references/researcher-prompt.md`, `data-provider/references/verifier-prompt.md`
- Contains: Role definitions, detection criteria, input/output contracts, process steps
- Depends on: Python scripts (via `{SCRIPTS_DIR}` placeholder), shared schema
- Used by: Command-layer prompts that copy agent content into Task tool calls

**Script Layer (Deterministic Helpers):**
- Purpose: Handle JSON I/O, data processing, and external tool invocation that LLMs cannot do reliably
- Location: `codebase-health/scripts/*.py`, `codebase-health/scripts/lib/`, `data-provider/scripts/*.py`, `permission-hooks/hooks/permission-guard.py`, `cc-regression-test/hooks/intercept-trigger.py`, `cc-regression-test/scripts/trigger.py`
- Contains: CLI Python scripts currently using stdlib (argparse, json, os, sys, re, glob)
- Depends on: Currently stdlib only; 3rd-party packages may be added when they bring real value
- Used by: Agent and command layers via Bash tool calls

**Reference Layer (Shared Contracts):**
- Purpose: Define data contracts and configuration schemas shared across pipeline steps
- Location: `codebase-health/references/schema.md`, `data-provider/references/fields.yaml`, `mg-gsd-wrappers/references/discuss-methodology.snapshot.md`
- Contains: JSON schema definitions, field specifications, methodology snapshots for drift detection
- Depends on: Nothing
- Used by: All pipeline steps that need to agree on data format

**Installer Layer (Deployment):**
- Purpose: Copy tool files to target project's `.claude/` directory and resolve path placeholders
- Location: `<tool>/install.sh`
- Contains: Bash scripts that validate, copy, and sed-replace paths
- Depends on: Source files in the tool directory
- Used by: Humans running installation manually from the command line

**Patch Layer (GSD Customization):**
- Purpose: Apply behavioral patches to GSD workflow files in target projects
- Location: `gsd-patches/patches/*.md`
- Contains: Structured anchor/replace pairs that modify GSD workflow markdown
- Depends on: GSD framework being installed in target project
- Used by: `mg:apply-gsd-patches` command

## Data Flow

**Codebase Health Pipeline (the complex tool):**

```
SCAN (read-only) ──> VERIFY (read-only) ──> IMPLEMENT (modifies code)
```

1. `/mg:codebase-health` detects pipeline state in `.mg/health-scan/` and routes user to the right step
2. `/mg:codebase-health-scan` spawns 14 category subagents in parallel via Task tool, each writing `scan-<category>.json`
3. Subagents call `add-finding.py` to record individual findings with atomic writes
4. Scanner orchestrator calls `merge-findings.py` to combine category JSONs into `health-scan-findings.json`
5. `/mg:codebase-health-verify` reads findings, verifies each one (possibly via per-category subagents), calls `verify-finding.py` to record results, then `split-findings.py` to produce downstream documents
6. `/mg:codebase-health-implement` reads verified findings, processes them inline or via sequential per-category subagents, calls `update-findings.py` after each change, commits per-finding with git

**Shared contract:** `health-scan-findings.json` (defined in `codebase-health/references/schema.md`)
- Scanner creates it with `findings[].verification: null`
- Verifier populates `findings[].verification` with safety classification
- Implementor populates `findings[].implementation` with status and change details

**Installation Flow:**

1. User runs `<tool>/install.sh --project [<dir>]` from any location
2. Installer validates source files exist
3. Copies command `.md` files to `<target>/.claude/commands/mg/`
4. Copies supporting files (agents, scripts, references) to `<target>/.claude/<tool>/`
5. Runs `sed` to replace placeholders (`{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `agents/`, etc.) with absolute paths
6. Optionally scaffolds project config in `<target-project>/.mg/<tool>/`

**State Management:**
- Codebase health pipeline state lives in `<project>/.mg/health-scan/` (findings JSON, reports, scan logs, config)
- Data provider state lives in `<project>/.mg/data-provider/` (input, tasks, output directories)
- GSD wrapper state is read from `.planning/` directory (managed by GSD framework)
- Update backlog state is read from `.planning/BACKLOG.md` (last scan timestamp in header)
- No persistent state is stored in the mg-cc-tools repo itself

## Key Abstractions

**Tool (Top-level Directory):**
- Purpose: A self-contained Claude Code slash command extension
- Examples: `codebase-health/`, `debug-triage/`, `update-backlog/`, `new-milestone-gsd/`, `create-context/`, `data-provider/`, `permission-hooks/`, `gsd-patches/`, `mg-gsd-wrappers/`, `cc-regression-test/`
- Pattern: Each has `install.sh` + `commands/` at minimum; complex tools add `agents/`, `scripts/`, `references/`

**Command File (.md):**
- Purpose: A Claude Code slash command definition (LLM instruction prompt in markdown)
- Examples: `codebase-health/commands/codebase-health-scan.md`, `debug-triage/commands/debug-triage.md`
- Pattern: YAML frontmatter (`name:`, `description:`, `allowed-tools:`) + structured process steps with XML-style sections (`<objective>`, `<process>`, `<success_criteria>`)

**Scanner Agent (.md in agents/):**
- Purpose: A specialized subagent prompt spawned via Task tool during codebase-health scan
- Examples: `codebase-health/agents/orphaned-code.md`, `codebase-health/agents/circular-deps.md`
- Pattern: All follow `codebase-health/agents/TEMPLATE.md` — role, inputs, process (read orientation, run linter, apply LLM judgment, record findings), principles

**Path Placeholder:**
- Purpose: A token in command/agent files replaced with absolute paths at install time
- Examples: `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `{PATCHES_DIR}`, `{HOOKS_DIR}`, `{SOURCE_DIR}`, `{TEMPLATE_SNAPSHOT}`, `{METHODOLOGY_SNAPSHOT}`, `{REFERENCES_DIR}`
- Pattern: `{UPPERCASE_NAME}` in source files, `sed -i "s|{PLACEHOLDER}|${ABSOLUTE_PATH}|g"` in install.sh

**Linter-Backed Hybrid:**
- Purpose: Pattern where a scanner agent runs an external linter for deterministic findings, then applies LLM judgment for novel detections the linter cannot catch
- Examples: orphaned-code (vulture + ruff F401), anti-patterns (ruff BLE/E722), sprawling-code (lizard)
- Pattern: 1) run linter with JSON output, 2) LLM adds contextual severity and filters false positives, 3) LLM proceeds to novel Grep-based detections skipping already-flagged lines

## Entry Points

**User-Facing (Slash Commands):**
- Location: `<tool>/commands/*.md` (source), `<target>/.claude/commands/mg/*.md` (installed)
- Triggers: User types `/mg:<command-name>` in Claude Code
- Responsibilities: Orchestrate the tool's behavior as defined in the markdown prompt

**Installation:**
- Location: `<tool>/install.sh`
- Triggers: User runs from command line
- Responsibilities: Copy files, resolve paths, scaffold config

**Python Scripts (CLI):**
- Location: `codebase-health/scripts/*.py`, `data-provider/scripts/*.py`
- Triggers: Called via `python3 <script> --args` from within LLM Bash tool calls
- Responsibilities: Deterministic JSON manipulation, external tool wrapping, data processing

**Hook Scripts:**
- Location: `permission-hooks/hooks/permission-guard.py`, `cc-regression-test/hooks/intercept-trigger.py`
- Triggers: Claude Code PreToolUse hook event (fires before Bash/Read/Edit/Write tool calls)
- Responsibilities: Guard against dangerous operations, intercept specific triggers for regression testing

## Error Handling

**Strategy:** Fail-fast with clear user messaging

**Patterns:**
- Install scripts use `set -euo pipefail` and validate all source files before copying
- Python scripts validate CLI arguments and return non-zero exit codes on failure
- Python scripts use atomic writes (temp file + `os.replace()`) to prevent partial JSON corruption
- Scanner subagents use WIP (work-in-progress) state files for checkpoint/resume on context window exhaustion
- Implementor rolls back git changes immediately on test failure (`git checkout -- .` for inline mode, `git reset --hard <checkpoint>` for batch mode)
- Pipeline commands check for prerequisite files before proceeding (e.g., verify checks for scan output)

## Cross-Cutting Concerns

**Logging:** Scan logs written to `.mg/health-scan/scan-logs/` per-category; human-readable reports generated at each pipeline stage

**Validation:** Install scripts validate source file existence; Python scripts validate JSON field values against enums; commands validate prerequisite pipeline state

**Authentication:** Not applicable (local-only tools, no external services)

**Configuration:** Layered config for codebase-health (project `.mg/health-scan/.health-scan.config.json` overrides global defaults); GSD framework config read from `.planning/`

**Idempotency:** Install scripts overwrite previous installations; `apply-gsd-patches` checks for already-applied patches; `update-backlog` deduplicates against existing items

**Drift Detection:** `mg:discuss-milestone` and `mg:create-context` compare methodology/template snapshots against live GSD files to detect breaking changes; `mg:apply-gsd-patches` and `mg:cc-regression-test` verify installed files match source via md5sum

---

*Architecture analysis: 2026-03-15*
