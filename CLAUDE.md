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

Python scripts require only stdlib (no pip dependencies). The `[dev]` extras install `pytest` and `ruff` for contributors.

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

**Simple tools** (debug-triage, update-backlog, new-milestone-gsd) contain only a single command .md file and a trivial install script. **Complex tools** (codebase-health) have agents, Python scripts, and a shared schema.

### Path resolution at install time

This is the most important pattern to understand. Command files reference supporting resources using **relative placeholders** (`references/schema.md`, `agents/orphaned-code.md`, `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`). During `install.sh`, these are sed-replaced with **absolute paths** so the LLM can locate them at runtime regardless of where the command file lives.

If you add a new resource reference in a command or agent file, you must also add the corresponding `sed` replacement in the tool's `install.sh`.

### Codebase health pipeline (the complex tool)

A 3-step pipeline: **scan** (read-only) → **verify** (read-only) → **implement** (modifies code). Each step enriches a shared `health-scan-findings.json` contract (see `references/schema.md`).

Key layers:
- **Commands** (`commands/*.md`) — orchestrate the pipeline steps, spawn subagents
- **Agents** (`agents/*.md`) — specialized scanner/implementor subagents spawned via the Task tool. Each agent follows `TEMPLATE.md` and records findings via Python scripts
- **Scripts** (`scripts/*.py`) — deterministic Python helpers for JSON I/O (add-finding, merge-findings, verify-finding, update-findings, split-findings) and analysis (circular-deps, unused-deps). All use only Python stdlib
- **Schema** (`references/schema.md`) — shared data contract between all three pipeline steps

### GSD extension tools

`debug-triage`, `update-backlog`, and `new-milestone-gsd` extend the [Get Shit Done](https://github.com/gsd-build/get-shit-done) workflow. They require GSD to be installed in the target project and reference GSD slash commands (`/gsd:debug`, `/gsd:add-phase`, `/gsd:new-milestone`).

## Conventions

- All commands use the `/mg:` namespace prefix
- Each tool is self-contained — no cross-tool dependencies
- Install scripts support three modes: `--project [<dir>]`, `--global`, `--target <path>`
- Install scripts always validate that source files exist before copying
- Command .md files include YAML-style frontmatter (`name:`, `description:`, `allowed-tools:`)

## Git Workflow

- Don't check out new branches, always stay on the current branch.
- Keep commits atomic with clear messages
