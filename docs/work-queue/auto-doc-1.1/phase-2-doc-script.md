# Phase 2: /mg:auto-doc-script — Lightweight Script Documentation

**Goal:** Add a new command that generates a single README.md for standalone scripts and small tools, without the full auto-doc pipeline.

**Depends on:** Phase 1 (rename must complete first so new files use `auto-doc/` paths)

---

## Problem Statement

Standalone scripts and small tools need documentation but don't warrant the full auto-doc pipeline (4 audiences, 13 document types, scan/generate/verify). Examples:

- `road-runner/scripts/def14a_download.py` — SEC filing downloader
- `road-runner/scripts/def14a_validate.py` — filing validation
- `mg-cc-tools/session-analyzer/` — CC session analysis CLI tool

These need a single README.md that answers: what is this, how do I run it, what are the options. A year from now, someone (including your future self) should be able to open the README and use the script without reading the source.

---

## Solution: `/mg:auto-doc-script`

A single-agent command that reads a script or tool directory and generates a README.md.

### Usage

```bash
# Single script — generates README.AUTO-DOC.md next to the script
/mg:auto-doc-script scripts/def14a_download.py

# Directory (multi-file tool) — generates README.AUTO-DOC.md for the tool
/mg:auto-doc-script session-analyzer/

# Custom output location
/mg:auto-doc-script scripts/def14a_download.py --output docs/scripts/def14a.md
```

### Output Structure

Fixed template, always the same sections:

```markdown
# {Script/Tool Name}

{One-paragraph description of what it does and when to use it.}

## Prerequisites

{Dependencies, environment variables, access requirements, setup steps.}

## Usage

{How to run it. Primary invocation pattern.}

## Examples

{2-4 common invocations with expected output.}

## Options

| Flag | Default | Description |
|------|---------|-------------|

## Output

{What the script produces — files, database records, stdout.}

## Notes

{Edge cases, rate limits, known limitations. Optional — omit if none.}
```

### How It Works

Single agent, no pipeline:

1. **Read the target** — script file or directory contents
2. **Extract CLI interface** — parse argparse/click/typer definitions, docstrings, `if __name__ == "__main__"` blocks
3. **Identify prerequisites** — imports (what needs to be installed), env var reads, file/network access
4. **Write README.AUTO-DOC.md** — to the target location (or custom path via `--output`)

No scan phase. No audience segmentation. No reference manifests. No verify step.

### For Multi-File Tools (directory mode)

When given a directory, the agent:

1. Identifies the entry point(s) — `__main__.py`, `cli.py`, scripts with `argparse`
2. Reads supporting modules for context (but doesn't document each one separately)
3. Produces a single README covering the tool as a whole
4. If the tool has subcommands, documents each subcommand

### Relationship to Auto-Doc Pipeline

| | `/mg:auto-doc` (full pipeline) | `/mg:auto-doc-script` |
|--|------|------|
| **Target** | Entire project | Single script or tool directory |
| **Output** | 13 docs across 4 audiences | 1 README.md |
| **Pipeline** | Scan → Generate → Verify | Read → Write |
| **Time** | Minutes | Seconds |
| **When to use** | Project-level documentation | Script/tool-level documentation |

---

## Scope

| Action | Files |
|--------|-------|
| Create | `auto-doc/commands/auto-doc-script.md` (~150-200 lines) |
| Create | `auto-doc/references/templates/SCRIPT_README.template.md` (~80-100 lines) |
| Edit | `auto-doc/install.sh` — add to COMMANDS array |

---

## Decisions

1. **Router integration:** No integration needed. `/mg:auto-doc` is always project-level, `/mg:auto-doc-script` is always file/directory-level. Different commands for different purposes, no overlap.
2. **Language support:** One generic prompt, no language-specific extraction instructions. The LLM reads any language's CLI patterns (argparse, click, getopts, commander, etc.) without separate instructions. Optimize examples for Python since that's the primary use case.
3. **Output filename:** `README.AUTO-DOC.md` (not `README.md`). Makes the generated vs hand-written distinction clear at the filesystem level. Full overwrite on each run — no preservation logic needed since the filename signals "this is auto-generated."
