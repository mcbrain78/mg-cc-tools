# Technology Stack

**Analysis Date:** 2026-03-15

## Languages

**Primary:**
- Markdown (.md) — Command files that serve as LLM instruction prompts; the core deliverable of every tool
- Python 3 (>=3.8) — Deterministic helper scripts for JSON I/O, static analysis wrappers, and hook logic
- Bash — Install scripts (`install.sh`) that deploy tools into Claude Code's `.claude/` directory structure

**Secondary:**
- JSON — Data contract format (health-scan-findings.json schema), configuration files (.health-scan.config.json)
- YAML (minimal) — Parsed manually via regex in `data-provider/scripts/generate.py` (no YAML library used)

## Runtime

**Environment:**
- Python 3.8+ (declared in `pyproject.toml`; dev environment runs Python 3.12.3)
- Bash (POSIX-compatible; all install scripts use `#!/usr/bin/env bash` with `set -euo pipefail`)
- Claude Code runtime — Command .md files are executed as LLM instruction prompts within Claude Code's slash command system

**Package Manager:**
- pip (via `pyproject.toml` at project root)
- Lockfile: Not present (no `requirements.txt` lockfile; `pyproject.toml` declares zero runtime dependencies)

## Frameworks

**Core:**
- Claude Code Slash Commands — The project IS a collection of slash commands under the `/mg:` namespace. No traditional application framework.

**Testing:**
- pytest — Used for Python script tests (`[dev]` extras in `pyproject.toml`)
- ruff — Linting (`[dev]` extras in `pyproject.toml`)

**Build/Dev:**
- No build system — Tools are installed via `install.sh` scripts that copy files and `sed`-replace path placeholders

## Key Dependencies

**Critical (zero runtime dependencies):**
- Python stdlib only — All Python scripts explicitly use only stdlib modules (`json`, `os`, `sys`, `argparse`, `re`, `ast`, `csv`, `io`, `subprocess`, `shutil`, `tempfile`, `pathlib`, `dataclasses`, `typing`, `statistics`, `collections`, `fnmatch`, `glob`, `datetime`, `time`)
- No pip packages are required at runtime

**Dev-only:**
- `pytest` — Test runner (installed via `pip install -e ".[dev]"`)
- `ruff` — Linter (installed via `pip install -e ".[dev]"`)

**External CLI tools (required by codebase-health scanners at runtime in target projects):**
- `vulture` — Python dead code detection; imported as Python API in `codebase-health/scripts/vulture-scan.py`
- `lizard` — Cyclomatic complexity analysis; invoked as subprocess in `codebase-health/scripts/lizard-scan.py`
- `jscpd` — Copy-paste detection; invoked as subprocess (Node.js tool) in `codebase-health/scripts/jscpd-scan.py`
- `pyright` — Python type checker; invoked as subprocess (Node.js tool) in `codebase-health/scripts/pyright-scan.py`

These are NOT dependencies of mg-cc-tools itself. They are required in the target project where codebase-health is installed. The scanner scripts detect their presence and exit with clear error messages if missing.

**Upstream dependency (not a code dependency):**
- [Get Shit Done (GSD)](https://github.com/gsd-build/get-shit-done) — Several tools (`debug-triage`, `update-backlog`, `new-milestone-gsd`, `mg-gsd-wrappers`, `gsd-patches`, `create-context`) require GSD to be installed in the target project. They reference GSD slash commands (`/gsd:debug`, `/gsd:add-phase`, `/gsd:new-milestone`, etc.)

## Configuration

**Environment:**
- `.env` file listed in `.gitignore` — may exist in dev environments but is never required by any tool
- No environment variables are required by any mg-cc-tools script
- All configuration is file-based (JSON config files, .health-ignore files)

**Build/Install Configuration:**
- `pyproject.toml` — Project metadata and dev dependencies only
- `.gitignore` — Standard Python/IDE/OS ignores plus `.claude/` directory

**Per-tool Configuration (created at install time in target projects):**
- `.mg/health-scan/.health-scan.config.json` — Model selection for codebase-health pipeline (scanner_model, verifier_model, implementer_model)
- `.mg/health-scan/.health-ignore` — Gitignore-style file exclusions for health scanning
- `.mg/data-provider/input/fields.yaml` — Field definitions for data-provider mapping
- `.mg/data-provider/input/providers.txt` — Provider names for data-provider mapping

**Path Resolution (install-time):**
- Placeholder tokens in command/agent .md files: `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `{HOOKS_DIR}`, `{SOURCE_DIR}`, `{PATCHES_DIR}`, `{METHODOLOGY_SNAPSHOT}`, `{TEMPLATE_SNAPSHOT}`, `{REFERENCES_DIR}`
- These are `sed`-replaced with absolute paths during `install.sh` execution
- This is the most critical pattern in the codebase: adding a new resource reference in a command file requires a corresponding `sed` replacement in the tool's `install.sh`

## Platform Requirements

**Development:**
- Python 3.8+ (3.12 used in dev)
- Bash shell
- Git (working tree assumed for all tools)
- No OS-specific requirements (Linux/macOS compatible; all scripts use portable constructs)

**Production (target project installation):**
- Claude Code must be installed (the tools are Claude Code slash commands)
- Python 3.8+ (for tools with Python scripts: codebase-health, permission-hooks, data-provider, cc-regression-test)
- For codebase-health pipeline: vulture, lizard (pip), jscpd, pyright (npm)
- For GSD wrapper tools: GSD must be installed in the target project
- Files are installed to `.claude/commands/mg/` (commands) and `.claude/<tool-name>/` (supporting files)

---

*Stack analysis: 2026-03-15*
