# Codebase Structure

**Analysis Date:** 2026-03-15

## Directory Layout

```
mg-cc-tools/
├── codebase-health/             # Complex tool: 3-step health pipeline (scan/verify/implement)
│   ├── agents/                  #   14 scanner subagent prompts + implementor + template
│   ├── commands/                #   4 slash command definitions (.md)
│   ├── references/              #   Shared schema (findings.json contract)
│   ├── scripts/                 #   12 Python CLI helpers (JSON I/O, linter wrappers)
│   │   └── lib/                 #     Shared Python modules (imports.py, ignore.py)
│   ├── install.sh               #   Installer
│   └── README.md                #   Tool documentation
├── debug-triage/                # Simple tool: bug triage → routes to debug or phase
│   ├── commands/                #   1 slash command (.md)
│   └── install.sh
├── update-backlog/              # Simple tool: scans .planning/ for deferred items
│   ├── commands/                #   1 slash command (.md)
│   └── install.sh
├── new-milestone-gsd/           # Simple tool: gate for gsd:new-milestone with backlog review
│   ├── commands/                #   1 slash command (.md)
│   └── install.sh
├── create-context/              # Simple tool: generates GSD CONTEXT.md from source doc
│   ├── commands/                #   1 slash command (.md) + 1 snapshot file
│   └── install.sh
├── data-provider/               # Complex tool: field mapping research pipeline
│   ├── commands/                #   1 slash command (.md)
│   ├── references/              #   fields.yaml + researcher/verifier prompts
│   ├── scripts/                 #   3 Python scripts (generate, status, summarize)
│   ├── install.sh
│   ├── DESIGN.md                #   Design document
│   └── README.md
├── permission-hooks/            # Complex tool: PreToolUse permission guard
│   ├── commands/                #   1 slash command (.md)
│   ├── hooks/                   #   permission-guard.py + tests/
│   │   └── tests/               #     pytest test suite for the hook
│   └── install.sh
├── gsd-patches/                 # Simple tool: applies patches to GSD workflow files
│   ├── commands/                #   1 slash command (.md)
│   ├── patches/                 #   6 patch definition files (.md)
│   └── install.sh
├── mg-gsd-wrappers/             # Multi-command tool: deviation-aware GSD wrappers
│   ├── commands/                #   4 slash commands (.md) + methodology snapshot
│   ├── references/              #   discuss-methodology.snapshot.md
│   └── install.sh
├── cc-regression-test/          # Complex tool: Claude Code regression test suite
│   ├── commands/                #   1 slash command (.md)
│   ├── hooks/                   #   intercept-trigger.py (PreToolUse hook)
│   ├── scripts/                 #   trigger.py (test trigger script)
│   └── install.sh
├── docs/                        # Documentation (sparse)
├── .claude/                     # Installed tools for self-hosting (gitignored)
├── .planning/                   # GSD planning artifacts
│   └── codebase/                #   Codebase analysis documents
├── CLAUDE.md                    # Claude Code project instructions
├── pyproject.toml               # Python project config (pytest + ruff dev deps)
├── README.md                    # Project overview and tool listing
└── .gitignore                   # Ignores .claude/, .venv/, __pycache__/, etc.
```

## Directory Purposes

**`codebase-health/`:**
- Purpose: The most complex tool; a 3-step pipeline for auditing and cleaning codebases
- Contains: 4 command files, 15 agent files (14 category scanners + 1 implementor + TEMPLATE), 12 Python scripts + 2 lib modules, 1 schema reference
- Key files: `commands/codebase-health-scan.md` (orchestrator), `references/schema.md` (data contract), `agents/TEMPLATE.md` (agent pattern)

**`debug-triage/`:**
- Purpose: Bug triage that maps full data flow before routing to debug or planning phase
- Contains: Single command file (361 lines of detailed LLM instructions)
- Key files: `commands/debug-triage.md`

**`update-backlog/`:**
- Purpose: Scans `.planning/` for deferred items and syncs to BACKLOG.md
- Contains: Single command file (811 lines covering detection, deduplication, confirmation, writing)
- Key files: `commands/update-backlog.md`

**`new-milestone-gsd/`:**
- Purpose: Gate for `/gsd:new-milestone` that shows backlog status first
- Contains: Single command file
- Key files: `commands/new-milestone-gsd.md`

**`create-context/`:**
- Purpose: Generates a GSD CONTEXT.md from a design document or gap assessment
- Contains: Command file + template snapshot for drift detection
- Key files: `commands/create-context.md`, `commands/context-template.snapshot`

**`data-provider/`:**
- Purpose: Research pipeline for mapping financial data fields to provider APIs
- Contains: Command file, Python scripts (generate/status/summarize), researcher/verifier prompts, field reference YAML
- Key files: `commands/map-fields-research.md`, `scripts/generate.py`, `references/fields.yaml`

**`permission-hooks/`:**
- Purpose: PreToolUse hook that guards against dangerous git/file operations
- Contains: Command file, Python hook script, comprehensive test suite
- Key files: `hooks/permission-guard.py` (the actual hook), `hooks/tests/test_permission_guard.py` (30k+ lines of tests)

**`gsd-patches/`:**
- Purpose: Applies reusable behavioral patches to GSD workflow files in target projects
- Contains: Command file, 6 patch definition files
- Key files: `commands/apply-gsd-patches.md`, `patches/*.md`

**`mg-gsd-wrappers/`:**
- Purpose: Deviation-aware wrappers around GSD discuss/plan/execute commands
- Contains: 4 command files + methodology snapshot reference
- Key files: `commands/discuss-milestone.md`, `commands/discuss-phase.md`, `commands/plan-phase.md`, `commands/execute-phase.md`

**`cc-regression-test/`:**
- Purpose: Regression test suite for Claude Code features (hooks, interactive prompts)
- Contains: Command file, hook script (intercepts Bash calls), trigger script
- Key files: `commands/cc-regression-test.md`, `hooks/intercept-trigger.py`, `scripts/trigger.py`

**`codebase-health/scripts/lib/`:**
- Purpose: Shared Python modules used by multiple codebase-health scripts
- Contains: `imports.py` (import graph parsing), `ignore.py` (gitignore-style pattern matching), `__init__.py`
- Key files: `imports.py` (17.5k lines, the heaviest module)

**`gsd-patches/patches/`:**
- Purpose: Individual patch definitions with anchor/replace pairs for GSD files
- Contains: 6 patch files targeting GSD workflows
- Key files: `discuss-phase-check-remaining.md`, `execute-phase-key-findings.md`, `plan-phase-key-findings.md`, `statusline-context-cache.md`

## Key File Locations

**Entry Points:**
- `<tool>/install.sh`: Installation entry point for each tool
- `<tool>/commands/*.md`: Slash command definitions (user-facing via `/mg:<name>`)

**Configuration:**
- `pyproject.toml`: Python project metadata, dev dependencies (pytest, ruff)
- `CLAUDE.md`: Claude Code project instructions for this repository
- `.gitignore`: Excludes `.claude/`, `.venv/`, `__pycache__/`, IDE files

**Core Logic (Codebase Health):**
- `codebase-health/commands/codebase-health-scan.md`: Scanner orchestrator (508 lines)
- `codebase-health/commands/codebase-health-verify.md`: Verifier (295 lines)
- `codebase-health/commands/codebase-health-implement.md`: Implementor (314 lines)
- `codebase-health/references/schema.md`: Shared findings JSON contract
- `codebase-health/agents/TEMPLATE.md`: Common agent execution pattern

**Core Logic (Scripts):**
- `codebase-health/scripts/add-finding.py`: Records single finding to category JSON
- `codebase-health/scripts/merge-findings.py`: Merges category JSONs into final findings
- `codebase-health/scripts/verify-finding.py`: Records verification results (append/single/batch modes)
- `codebase-health/scripts/update-findings.py`: Records implementation results
- `codebase-health/scripts/split-findings.py`: Splits verified findings into downstream documents
- `codebase-health/scripts/circular-deps.py`: Builds import graph and detects cycles
- `codebase-health/scripts/unused-deps.py`: Checks dependency manifests against actual imports
- `codebase-health/scripts/vulture-scan.py`: Wraps vulture for dead code detection
- `codebase-health/scripts/jscpd-scan.py`: Wraps jscpd for copy-paste detection
- `codebase-health/scripts/pyright-scan.py`: Wraps pyright for type diagnostics
- `codebase-health/scripts/lizard-scan.py`: Wraps lizard for complexity metrics

**Testing:**
- `permission-hooks/hooks/tests/test_permission_guard.py`: Comprehensive tests for permission guard hook

## Naming Conventions

**Files:**
- Command files: `kebab-case.md` matching the slash command name (e.g., `codebase-health-scan.md` -> `/mg:codebase-health-scan`)
- Agent files: `kebab-case.md` matching the scan category (e.g., `orphaned-code.md`, `dead-code-paths.md`)
- Python scripts: `kebab-case.py` matching their function (e.g., `add-finding.py`, `merge-findings.py`)
- Patch files: `kebab-case.md` with descriptive names (e.g., `execute-phase-pyright-gate.md`)
- Snapshot files: `<name>.snapshot.md` or `<name>.snapshot` for drift detection baselines
- Install scripts: Always `install.sh`

**Directories:**
- Tool directories: `kebab-case` matching the tool/command name
- Subdirectories: Functional grouping (`commands/`, `agents/`, `scripts/`, `references/`, `hooks/`, `patches/`)
- Installed location: `<target>/.claude/commands/mg/` for commands, `<target>/.claude/<tool>/` for supporting files

**Slash Commands:**
- All use the `mg:` namespace prefix (e.g., `/mg:codebase-health`, `/mg:debug-triage`)
- Multi-word names use kebab-case

## Where to Add New Code

**New Simple Tool (single command, no scripts):**
1. Create `<tool-name>/` at project root
2. Create `<tool-name>/commands/<tool-name>.md` with YAML frontmatter and instruction prompt
3. Create `<tool-name>/install.sh` following the simple installer pattern from `debug-triage/install.sh`
4. Add to `README.md` tool listing table

**New Complex Tool (multiple commands, scripts, agents):**
1. Create `<tool-name>/` at project root
2. Create `<tool-name>/commands/*.md` for each slash command
3. Create `<tool-name>/scripts/*.py` for deterministic helpers
4. Create `<tool-name>/agents/*.md` for subagent prompts (if using Task tool)
5. Create `<tool-name>/references/` for shared schemas or config
6. Create `<tool-name>/install.sh` following the complex installer pattern from `codebase-health/install.sh`
7. Add path placeholders in source files and corresponding `sed` replacements in install.sh
8. Add to `README.md` tool listing table

**New Scanner Category (for codebase-health):**
1. Create `codebase-health/agents/<category-name>.md` following `agents/TEMPLATE.md`
2. Add the category to the scan category list in `codebase-health/commands/codebase-health-scan.md`
3. Add the category slug to `VALID_CATEGORIES` in `codebase-health/scripts/add-finding.py`
4. If the category needs a linter wrapper, create `codebase-health/scripts/<linter>-scan.py`

**New Python Script:**
- Place in `<tool>/scripts/` directory
- Use Python stdlib where sufficient; 3rd-party packages are fine when they bring real value
- Use `argparse` for CLI interface
- Use atomic writes (temp file + `os.replace()`) for JSON output
- Add `#!/usr/bin/env python3` shebang

**New GSD Patch:**
1. Create `gsd-patches/patches/<descriptive-name>.md` with anchor/replace structure
2. The `apply-gsd-patches` command auto-discovers patches from the directory

**New GSD Wrapper Command:**
1. Add command file to `mg-gsd-wrappers/commands/<command-name>.md`
2. Add to the `COMMANDS` array in `mg-gsd-wrappers/install.sh`
3. Add any placeholder resolution needed

**Tests for a Tool:**
- Place in `<tool>/hooks/tests/` or `<tool>/scripts/tests/` adjacent to the code being tested
- Use pytest (available via `[dev]` extras in `pyproject.toml`)
- Run with `python3 -m pytest <path>`

## Special Directories

**`.claude/` (in this project):**
- Purpose: Installed tools for self-hosting (this project uses its own tools on itself)
- Generated: Yes (by running install scripts targeting this project)
- Committed: No (gitignored)
- Contains: GSD framework, installed mg-cc-tools commands, hooks, settings

**`.mg/` (in target projects):**
- Purpose: Mutable workspace for tool state (scan results, config, work directories)
- Generated: Yes (by tool execution and install scaffolding)
- Committed: No (tools advise adding to .gitignore)
- Contains: `health-scan/` (codebase-health pipeline state), `data-provider/` (field mapping state)

**`.planning/` (in target projects):**
- Purpose: GSD planning artifacts (milestones, phases, backlog, roadmap)
- Generated: Yes (by GSD framework)
- Committed: Yes (planning artifacts are version-controlled)
- Contains: `BACKLOG.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `phases/`, `codebase/`

**`docs/`:**
- Purpose: Documentation files
- Generated: No
- Committed: Yes
- Contains: Sparse content (includes an empty "New folder" subdirectory)

---

*Structure analysis: 2026-03-15*
