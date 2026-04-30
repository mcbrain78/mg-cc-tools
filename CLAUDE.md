# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`mg-cc-tools` is a collection of Claude Code slash commands under the `mg:` namespace. Each tool is a self-contained subdirectory with its own `install.sh`, command files (.md), and optional supporting resources (agents, scripts, schemas). Tools are installed into a target project's `.claude/` directory (or `~/.claude/` for global installs) and invoked as `/mg:<tool-name>`.

## Development

```bash
# Set up dev environment (optional — only needed for Python script work)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Run tests
python3 -m pytest

# Run a single test file
python3 -m pytest codebase-health/scripts/tests/test_merge.py

# Lint
ruff check .
```

**Dependencies:** Since many tools invoke external programs (ruff, vulture, lizard) via subprocess or bash, the project's dependency footprint is not visible through `pyproject.toml`. 3rd-party dependencies are fine and are used when they bring real value — prefer well-maintained, known solutions. Do not reinvent the wheel. Declare Python package dependencies so the install process can manage them. The `[dev]` extras install `pytest` and `ruff` for contributors.

## Architecture

### Tool anatomy

Each tool follows the same pattern:

```
<tool-name>/
├── install.sh           ← deploys to .claude/commands/mg/ (and .claude/<tool-name>/ if needed)
├── commands/            ← .md files that define slash commands (LLM instruction prompts)
└── [agents/|scripts/|references/]  ← optional supporting resources
```

**Command files** are markdown documents that serve as LLM instruction prompts. They define the command's name, allowed tools, and step-by-step behavior. The install script copies them into the target's `.claude/commands/mg/` directory.

**Simple tools** (debug-triage, update-backlog, new-milestone-gsd) contain only a single command .md file and a trivial install script. **Complex tools** (codebase-health, auto-doc) have agents, Python scripts, and a shared schema.

### Path resolution at install time

This is the most important pattern to understand. Command files reference supporting resources using **relative placeholders** (`references/schema.md`, `agents/orphaned-code.md`, `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`). During `install.sh`, these are sed-replaced with **absolute paths** so the LLM can locate them at runtime regardless of where the command file lives.

If you add a new resource reference in a command or agent file, you must also add the corresponding `sed` replacement in the tool's `install.sh`.

### Codebase health pipeline (the complex tool)

A 3-step pipeline: **scan** (read-only) → **verify** (read-only) → **implement** (modifies code). Each step enriches a shared `health-scan-findings.json` contract (see `references/schema.md`).

Key layers:
- **Commands** (`commands/*.md`) — orchestrate the pipeline steps, spawn subagents
- **Agents** (`agents/*.md`) — specialized scanner/implementor subagents spawned via the Task tool. Each agent follows `TEMPLATE.md` and records findings via Python scripts
- **Scripts** (`scripts/*.py`) — deterministic Python helpers for JSON I/O (add-finding, merge-findings, verify-finding, update-findings, split-findings) and analysis (circular-deps, unused-deps)
- **Schema** (`references/schema.md`) — shared data contract between all three pipeline steps

### Auto-doc pipeline (the documentation tool)

A pipeline of five commands: **scan** → **prepare-templates** (optional) → **generate** → **auditv2** → **fix**. The scan produces a `docs-scan.json` contract consumed by the rest of the pipeline; auditv2 produces audit findings consumed by fix.

Key layers:
- **Commands** (`commands/*.md`) — orchestrate the five pipeline steps (`auto-doc-scan`, `auto-doc-prepare-templates`, `auto-doc-generate`, `auto-doc-auditv2`, `auto-doc-fix`)
- **Agents** (`agents/*.md`) — audience-specific writer subagents (end-user, developer, agent, devops, glossary, overview) plus scan-audience, template-refiner, doc-polisher, and the auditv2 / fix agent set (extract-prose-entities, resolve-prose-entities, classify-dismissed-entities, assess-convergence, group-findings, audit-fixer)
- **Scripts** (`scripts/*.py`) — deterministic Python helpers for the pipeline (generate-setup, merge-scan, staleness-check, write-section, next-heading, verify-xml-refs, clear-matched-entities, prepare-prose-verify, fix-queue, load-audit-findings, etc.)
- **Schema** (`references/schema.yaml`) — shared `docs-scan.json` and audit-findings data contract between pipeline steps
- **Templates** (`references/templates/`) — three-layer document templates (Diataxis + structure + exemplar) organized by audience

### GSD extension tools

`debug-triage`, `update-backlog`, and `new-milestone-gsd` extend the [Get Shit Done](https://github.com/gsd-build/get-shit-done) workflow. They require GSD to be installed in the target project and reference GSD slash commands (`/gsd:debug`, `/gsd:add-phase`, `/gsd:new-milestone`).

## Conventions

- All commands use the `/mg:` namespace prefix
- Each tool is self-contained — no cross-tool dependencies
- Install scripts support three modes: `--project [<dir>]`, `--global`, `--target <path>`
- Install scripts always validate that source files exist before copying
- Command .md files include YAML-style frontmatter (`name:`, `description:`, `allowed-tools:`)
- Prefer breaking changes instead of backwards compatibility to avoid technical debt. Clearly show when breaking changes will occur.

## Testing

- Never pipe pytest output (e.g. `pytest | tail -20`) — this masks the exit code. Use `pytest --tb=short -q --no-header` instead.

## Git Workflow

- Don't check out new branches, always stay on the current branch.
- Keep commits atomic with clear messages


## Environment setup
- This project uses uv. Dev/test deps are in the `dev` extra.
- Run `uv sync` to install dependencies
- Use `uv run python ...` or `source .venv/bin/activate` to run code
- To add a dependency: `uv add <package>`
- To remove a dependency: `uv remove <package>`

## Separation of markdown and python
Never embed Python code in .md command/agent files. All deterministic logic goes in scripts/*.py and is called via Bash(uv run {SCRIPTS_DIR}/...). The .md file describes what to do; the script implements ho