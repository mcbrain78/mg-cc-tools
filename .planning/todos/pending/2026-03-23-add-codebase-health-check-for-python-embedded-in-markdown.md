---
created: 2026-03-23T17:03:53.148Z
title: Add codebase-health check for Python embedded in markdown
area: codebase-health
files:
  - auto-doc/commands/auto-doc-scan.md
  - auto-doc/commands/auto-doc-generate.md
  - auto-doc/post-install.md
  - codebase-health/agents/
---

## Problem

During auto-doc development, inline Python code was embedded directly in .md command/agent files (e.g. `python3 -c "..."` blocks in post-install.md, auto-doc-scan.md, auto-doc-generate.md). This violates the project convention that .md files contain LLM instructions while scripts/*.py files contain deterministic logic. The issue was only caught during manual review of a scan run transcript — there was no automated check.

### Verbatim user request

> codebase-health: add check if python is embedded in markdown. it should almost always be separated. INCLUDE THE USER MESSAGE IN VERBATIM

## Solution

Add a new codebase-health scanner (or check within an existing scanner) that:
1. Scans all `.md` files in command/agent directories for inline Python blocks (`python3 -c`, ````python` fenced blocks containing executable code)
2. Flags them as findings with severity "convention" or "warning"
3. Suggests extraction to a corresponding `scripts/` directory
4. Allow exceptions for trivial one-liners if needed (e.g. `python3 -c "import sys; print(sys.version)"`)
