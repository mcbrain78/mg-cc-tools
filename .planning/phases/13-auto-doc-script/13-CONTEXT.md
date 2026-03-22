# Phase 13: Auto Doc Script - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/auto-doc-1.1/phase-2-doc-script.md) + discussion

<domain>
## Phase Boundary

Add a new `/mg:auto-doc-script` command that generates a single README.md for standalone scripts and small tools, without the full auto-doc pipeline. Lightweight read-then-write flow — no scan phase, no audience segmentation, no verify step.

</domain>

<decisions>
## Implementation Decisions

### Command interface
- Command name: `/mg:auto-doc-script`
- First positional argument (required): path to a script file or tool directory
- Optional `--output <path>`: custom output location for the generated README
- If `$ARGUMENTS` is empty, show usage message and stop
- If target path does not exist, show error and stop
- Argument parsing: split `$ARGUMENTS` on whitespace; if `--output` present, next token is output path; everything before `--output` is target path
- If `--output` specified and its parent directory does not exist, show error and stop

### Output file
- Default filename: `README.AUTO-DOC.md` (not `README.md`) — makes generated vs hand-written distinction clear at filesystem level
- Default location: same directory as the target file, or inside the target directory (for directory mode)
- Full overwrite on each run — no preservation logic needed since filename signals "auto-generated"

### Single-file mode
- Read the script file
- Extract CLI interface: parse argparse/click/typer definitions, docstrings, `if __name__ == "__main__"` blocks
- Identify prerequisites: imports (what needs installed), env var reads, file/network access
- Write README.AUTO-DOC.md to the target location

### Directory mode (multi-file tools)
- Size threshold: count source files (`.py`, `.js`, `.ts`, `.sh`, `.go`, `.rs`, etc.; exclude tests, `__init__.py`, dotfiles, non-code assets). If count exceeds **20 source files**, print warning ("consider the full `/mg:auto-doc` pipeline") and continue — not a hard stop
- In directory mode with no source files at all: show error and stop
- In directory mode with source files but no obvious entry point: print warning ("No CLI entry point detected") and continue
- Identify entry point(s): `__main__.py`, `cli.py`, scripts with `argparse`
- Read supporting modules for context but don't document each one separately — focus on entry points and their direct imports
- Produce a single README covering the tool as a whole
- If the tool has subcommands, document each subcommand
- Multiple independent entry points: per-script sections with individual Usage/Examples/Options, not a holistic description
- Summary table at top listing all entry points (script name, one-line description, common invocation)
- Brief "Architecture" note for non-entry-point files (one paragraph or bullet list showing directory structure and what supporting files do)
- Order per-script sections by importance/usage (main entry point first, then helpers/utilities)

### Example quality bar
- Examples must be fully runnable with realistic args and expected output shown
- Use ` ```console ` fenced code blocks with `$` prompt prefix for commands, plain text for output
- Number of examples per script/subcommand: Claude's discretion based on complexity (simple scripts may need 1-2, complex scripts with many flags may need more)

### Output structure
- Command reads template at `{TEMPLATES_DIR}/SCRIPT_README.template.md` at runtime for section structure and `<!-- PURPOSE: ... -->` / `<!-- EXAMPLE: ... -->` annotations
- Maximum sections: title/description, Prerequisites, Usage, Examples, Options, Output, Notes
- Omit any section that would only contain "None" or "N/A" — output only sections with substantive content

### Template file
- Create `auto-doc/references/templates/SCRIPT_README.template.md` (~80-100 lines)
- Uses `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comment patterns matching existing templates

### Command frontmatter
- `name: mg:auto-doc-script`
- `description: Generate a README for a standalone script or small tool directory`
- `allowed-tools: Bash, Read, Write, Glob, Grep`
- No `Task` tool (single agent, no subagents)
- No `AskUserQuestion` (fully autonomous generation)

### Router integration
- No integration needed — `/mg:auto-doc` is always project-level, `/mg:auto-doc-script` is always file/directory-level
- Different commands for different purposes, no overlap
- The router does not detect single-script projects — users choose the right command based on intent

### Language support
- One generic prompt, no language-specific extraction instructions
- LLM reads any language's CLI patterns (argparse, click, getopts, commander, etc.) without separate instructions
- Optimize examples for Python since that's the primary use case

### Install changes
- Add `auto-doc-script` to COMMANDS array in `auto-doc/install.sh`
- Existing `{TEMPLATES_DIR}` sed rule and recursive `cp -r` of `references/templates/` already cover the new template file — no new sed rules needed

### Claude's Discretion
- Internal structure of the command .md file (step ordering, prompt phrasing)
- How to handle scripts with no argparse/CLI interface (library modules invoked as scripts)
- Exact wording of warning messages for size threshold and missing entry point
- Whether to include a "How it works" section for non-trivial scripts
- Template exemplar content and detail level

</decisions>

<specifics>
## Specific Ideas

- The command is ~150-200 lines, the template is ~80-100 lines — this is a small, focused phase
- Template uses the same `<!-- PURPOSE: ... -->` / `<!-- EXAMPLE: ... -->` pattern as existing templates in `references/templates/`
- Install.sh already handles `{TEMPLATES_DIR}` sed resolution and recursive `cp -r` of `references/templates/` — only the COMMANDS array entry needs adding
- "A year from now, someone (including your future self) should be able to open the README and use the script without reading the source" — this is the quality bar

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auto-doc/references/templates/` directory structure: already copied recursively by install.sh
- `{TEMPLATES_DIR}` sed resolution: already handled in install.sh
- COMMANDS array pattern in install.sh: just add the new entry
- 13 existing templates demonstrate the `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` HTML comment pattern

### Established Patterns
- Command frontmatter with YAML-style `name:`, `description:`, `allowed-tools:`
- Template `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comment annotations
- Single-agent commands (no Task tool needed) — precedent exists in simpler auto-doc commands

### Integration Points
- `auto-doc/install.sh` COMMANDS array: add `auto-doc-script`
- `auto-doc/references/templates/`: new `SCRIPT_README.template.md` file

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-auto-doc-script*
*Context gathered: 2026-03-22 via context import + discussion*
