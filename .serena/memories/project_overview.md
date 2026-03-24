# mg-cc-tools — Project Overview

## Purpose
A collection of Claude Code slash commands under the `mg:` namespace. Each tool is a self-contained subdirectory with its own install script, command files (.md), and optional supporting resources (agents, scripts, schemas). Tools are installed into a target project's `.claude/` directory (or `~/.claude/` for global installs) and invoked as `/mg:<tool-name>`.

## Tech Stack
- **Language:** Python 3.11+ (scripts), Markdown (command/agent prompts)
- **Package manager:** uv (not pip)
- **Testing:** pytest
- **Linting:** ruff
- **Platform:** Linux
- **No web framework** — these are CLI tools and LLM instruction prompts

## Key Tools
| Tool | Description |
|------|-------------|
| `codebase-health` | 3-step pipeline (scan → verify → implement) for code quality analysis |
| `auto-doc` | 3-step pipeline (scan → generate → verify) for documentation lifecycle |
| `install` | Meta-installer for deploying tools to target projects |
| `gsd-patches` | Patches for the GSD (Get Shit Done) workflow |
| `debug-triage` | Extends GSD debugging workflow |
| `update-backlog` | Extends GSD backlog management |
| `new-milestone-gsd` | Extends GSD milestone creation |
| `session-analyzer` | Analyzes Claude Code session transcripts |
| `cc-regression-test` | Claude Code regression testing |
| `create-context` | Context creation utility |
| `data-provider` | Data provider utility |
| `permission-hooks` | Permission hook management |
| `mg-gsd-wrappers` | GSD command wrappers |

## Dependencies
- Python 3.11+ (no runtime PyPI dependencies in pyproject.toml)
- Dev: pytest, ruff
- External tools used via subprocess: ruff, vulture, lizard, jscpd, pyright
