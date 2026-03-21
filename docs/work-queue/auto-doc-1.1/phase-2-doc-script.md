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

### Arguments

`$ARGUMENTS` contains the target path and an optional `--output` flag:

- **First positional argument** (required): path to a script file or tool directory
- **`--output <path>`** (optional): custom output location for the generated README

Parsing rules for the command `.md`:
1. Split `$ARGUMENTS` on whitespace
2. If `--output` is present, the next token is the output path; everything before `--output` is the target path
3. If `--output` is absent, output path defaults to `README.AUTO-DOC.md` in the same directory as the target (for a file) or inside the target directory (for a directory)

**Validation (Step 1 of command execution):**
1. If `$ARGUMENTS` is empty, show usage message and stop
2. If the target path does not exist, show error and stop
3. In directory mode: if no source files are found at all (empty directory or only non-code files), show error and stop. If source files exist but no obvious entry point is found, print a warning ("No CLI entry point detected — the README may have limited usage information") and continue
4. If `--output` is specified and its parent directory does not exist, show error and stop

### Output Structure

The command reads the template file at `{TEMPLATES_DIR}/SCRIPT_README.template.md` at runtime to get section structure and `<!-- PURPOSE: ... -->` / `<!-- EXAMPLE: ... -->` annotations. The inline version below is for plan reference only — the runtime template is the source of truth:

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

{Edge cases, rate limits, known limitations.}
```

Omit any section that would only contain "None" or "N/A". The template shows the maximum set of sections; output only those with substantive content.

### How It Works

Single agent, no pipeline:

1. **Read the target** — script file or directory contents
2. **Extract CLI interface** — parse argparse/click/typer definitions, docstrings, `if __name__ == "__main__"` blocks
3. **Identify prerequisites** — imports (what needs to be installed), env var reads, file/network access
4. **Write README.AUTO-DOC.md** — to the target location (or custom path via `--output`)

No scan phase. No audience segmentation. No reference manifests. No verify step.

### For Multi-File Tools (directory mode)

Designed for small tools. **Size threshold:** count source files (any file with a code-related extension — `.py`, `.js`, `.ts`, `.sh`, `.go`, `.rs`, etc.; exclude tests, `__init__.py`, dotfiles, and non-code assets). If the count exceeds **20 source files**, print a warning ("This directory has N source files — consider the full `/mg:auto-doc` pipeline for better coverage") and continue. Not a hard stop — the user explicitly chose this command, so respect that choice.

When given a directory, the agent:

1. Identifies the entry point(s) — `__main__.py`, `cli.py`, scripts with `argparse`
2. Reads supporting modules for context (but doesn't document each one separately — focus on entry points and their direct imports)
3. Produces a single README covering the tool as a whole
4. If the tool has subcommands, documents each subcommand

### Relationship to Auto-Doc Pipeline

| | `/mg:auto-doc` (full pipeline) | `/mg:auto-doc-script` |
|--|------|------|
| **Target** | Entire project | Single script or tool directory |
| **Output** | 13 docs across 4 audiences | 1 README.md |
| **Pipeline** | Scan → Generate → Verify | Read → Write |
| **Time** | Minutes | Seconds to low minutes |
| **When to use** | Project-level documentation | Script/tool-level documentation |

---

## Scope

| Action | Files |
|--------|-------|
| Create | `auto-doc/commands/auto-doc-script.md` (~150-200 lines) |
| Create | `auto-doc/references/templates/SCRIPT_README.template.md` (~80-100 lines) |
| Edit | `auto-doc/install.sh` — add `auto-doc-script` to COMMANDS array; existing `{TEMPLATES_DIR}` sed rule and recursive `cp -r` of `references/templates/` already cover the new template file |

---

## Command Frontmatter

The command file `auto-doc-script.md` uses this frontmatter (consistent with all other auto-doc commands):

```yaml
---
name: mg:auto-doc-script
description: Generate a README for a standalone script or small tool directory
allowed-tools: Bash, Read, Write, Glob, Grep
---
```

No `Task` tool needed (single agent, no subagents). No `AskUserQuestion` needed (fully autonomous generation).

---

## Decisions

1. **Router integration:** No integration needed. `/mg:auto-doc` is always project-level, `/mg:auto-doc-script` is always file/directory-level. Different commands for different purposes, no overlap. The router does not detect single-script projects — users choose the right command based on their intent.
2. **Language support:** One generic prompt, no language-specific extraction instructions. The LLM reads any language's CLI patterns (argparse, click, getopts, commander, etc.) without separate instructions. Optimize examples for Python since that's the primary use case.
3. **Output filename:** `README.AUTO-DOC.md` (not `README.md`). Makes the generated vs hand-written distinction clear at the filesystem level. Full overwrite on each run — no preservation logic needed since the filename signals "this is auto-generated."
4. **Template approach:** The command references the template via `{TEMPLATES_DIR}/SCRIPT_README.template.md` (consistent with the full pipeline). The template file uses `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comment patterns matching existing templates. The `install.sh` already resolves `{TEMPLATES_DIR}` via sed and copies `references/templates/` recursively — no new sed rules needed, only the COMMANDS array entry.
