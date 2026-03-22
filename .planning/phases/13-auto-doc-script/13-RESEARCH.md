# Phase 13: Auto Doc Script - Research

**Researched:** 2026-03-22
**Domain:** Claude Code slash command authoring (LLM instruction prompt + template file)
**Confidence:** HIGH

## Summary

Phase 13 adds a new `/mg:auto-doc-script` command that generates a single `README.AUTO-DOC.md` for standalone scripts and small tool directories. This is a lightweight, single-agent command with no pipeline (no scan, no verify, no subagents). The deliverables are exactly two files: a command markdown file (~150-200 lines) and a template file (~80-100 lines), plus a one-line addition to the COMMANDS array in `install.sh`.

The implementation is straightforward because all infrastructure already exists. The `auto-doc/install.sh` already handles `{TEMPLATES_DIR}` sed resolution, recursive `cp -r` of the templates directory, and the COMMANDS array loop. The existing 13 templates provide a well-established pattern for `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` annotations that the new template must follow. No Python scripts, no agents, no schema changes.

**Primary recommendation:** Follow existing patterns exactly. The command file should follow the `auto-doc-add.md` structural pattern (single-agent, no Task tool, argument-driven). The template should follow the `QUICK_REFERENCE.template.md` annotation density and style.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Command name: `/mg:auto-doc-script`
- First positional argument (required): path to a script file or tool directory
- Optional `--output <path>`: custom output location for the generated README
- If `$ARGUMENTS` is empty, show usage message and stop
- If target path does not exist, show error and stop
- Argument parsing: split `$ARGUMENTS` on whitespace; if `--output` present, next token is output path; everything before `--output` is target path
- If `--output` specified and its parent directory does not exist, show error and stop
- Default output filename: `README.AUTO-DOC.md` (not `README.md`)
- Default location: same directory as the target file, or inside the target directory (for directory mode)
- Full overwrite on each run
- Single-file mode: read script, extract CLI interface, identify prerequisites, write README
- Directory mode: count source files, warn at >20, error on zero, identify entry points, focus on entry points and direct imports, produce single README
- Multiple independent entry points: per-script sections with summary table at top
- Examples must be fully runnable with realistic args and expected output shown, using ` ```console ` blocks with `$` prompt prefix
- Output structure: title/description, Prerequisites, Usage, Examples, Options, Output, Notes -- omit empty sections
- Template at `{TEMPLATES_DIR}/SCRIPT_README.template.md` with `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` annotations
- Command frontmatter: `name: mg:auto-doc-script`, `description: Generate a README for a standalone script or small tool directory`, `allowed-tools: Bash, Read, Write, Glob, Grep`
- No `Task` tool (single agent, no subagents)
- No `AskUserQuestion` (fully autonomous generation)
- No router integration needed
- One generic prompt, no language-specific extraction instructions
- Add `auto-doc-script` to COMMANDS array in `auto-doc/install.sh`
- No new sed rules needed (existing `{TEMPLATES_DIR}` resolution covers it)

### Claude's Discretion
- Internal structure of the command .md file (step ordering, prompt phrasing)
- How to handle scripts with no argparse/CLI interface (library modules invoked as scripts)
- Exact wording of warning messages for size threshold and missing entry point
- Whether to include a "How it works" section for non-trivial scripts
- Template exemplar content and detail level
- Number of examples per script/subcommand (based on complexity)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Claude Code command .md | N/A | LLM instruction prompt defining `/mg:auto-doc-script` | All mg-cc-tools commands are markdown files with YAML frontmatter |
| Template .md | N/A | `SCRIPT_README.template.md` with `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` | Matches the 13 existing templates in `references/templates/` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| auto-doc/install.sh | N/A | Deployment, sed resolution, COMMANDS array | Already handles everything -- only array entry needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single command .md | Python script + command | Over-engineered -- this is an LLM-driven read-then-write; no deterministic processing needed |
| Subagent architecture | Single-agent | No audience segmentation, no parallel writers -- subagents add complexity for zero benefit |

**Installation:** No new dependencies. No pip install. No new scripts.

## Architecture Patterns

### File Inventory (Complete Phase Deliverables)
```
auto-doc/
├── commands/
│   └── auto-doc-script.md          # NEW: command file (~150-200 lines)
├── references/templates/
│   └── SCRIPT_README.template.md   # NEW: template file (~80-100 lines)
└── install.sh                      # MODIFY: add to COMMANDS array (1 line)
```

### Pattern 1: Command File Structure
**What:** Single-agent autonomous command with argument parsing, validation, file reading, and document generation.
**When to use:** Commands that need no user interaction and no subagents.
**Closest precedent:** `auto-doc-add.md` -- same frontmatter pattern, argument parsing via `$ARGUMENTS`, validation-then-work flow.

The command file should follow this structure:
1. YAML frontmatter (name, description, allowed-tools)
2. One-paragraph role description
3. Arguments section (parsing `$ARGUMENTS`)
4. Process section with numbered steps:
   - Step 1: Parse and validate arguments (target path, --output flag)
   - Step 2: Determine mode (single-file vs directory)
   - Step 3: Read and analyze target (extract CLI interface, prerequisites, entry points)
   - Step 4: Read template for section structure
   - Step 5: Generate README.AUTO-DOC.md
5. Important principles section (quality bar, omit-empty-sections rule)

### Pattern 2: Template File Structure
**What:** Markdown template with `<!-- DIATAXIS -->`, `<!-- AUDIENCE -->` header comments, section headings, `<!-- PURPOSE -->` and `<!-- EXAMPLE -->` annotations per section, and `<!-- OPTIONAL -->` markers for conditional sections.
**When to use:** All auto-doc templates follow this three-layer pattern.
**Source:** All 13 existing templates in `auto-doc/references/templates/`.

Template sections per CONTEXT.md: title/description, Prerequisites, Usage, Examples, Options, Output, Notes. Each gets a `<!-- PURPOSE -->` explaining what to write and an `<!-- EXAMPLE -->` showing a realistic filled-in instance.

### Pattern 3: Install.sh COMMANDS Array
**What:** Adding a command name to the bash array so the install loop picks it up.
**Source:** `auto-doc/install.sh` line 24-30.

```bash
COMMANDS=(
  auto-doc
  auto-doc-scan
  auto-doc-generate
  auto-doc-verify
  auto-doc-add
  auto-doc-script    # <-- add this
)
```

The existing install loop (lines 112-117, 201-205, 260-292) iterates over this array to validate, copy, and sed-resolve each command. No other install.sh changes needed because:
- `{TEMPLATES_DIR}` sed resolution already exists (line 282-283)
- The command references no agents (no `agents/` prefix to resolve)
- The command references no scripts (no `{SCRIPTS_DIR}` to resolve)
- The template file is already covered by `cp -r ... templates` (line 237)

### Anti-Patterns to Avoid
- **Over-engineering the command:** This is NOT a pipeline step. No scan phase, no JSON contracts, no verify step. The LLM reads files, reads the template, writes a README. That is the entire flow.
- **Adding Python scripts:** The LLM handles all analysis (CLI extraction, prerequisite detection) directly. No deterministic scripts needed for this task.
- **Language-specific branches in the prompt:** One generic prompt covers all languages. The LLM recognizes argparse, click, getopts, commander, etc. without separate instructions.
- **Touching the router:** `/mg:auto-doc` and `/mg:auto-doc-script` serve different purposes. No cross-referencing, no routing logic changes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template resolution | Custom template engine | LLM reads template, uses sections as structure guide | Templates are LLM instructions, not machine-parsed formats |
| CLI extraction | Python AST parser | LLM reads source code directly | LLM can parse any language's CLI patterns without tooling |
| Install deployment | New install logic | Existing install.sh COMMANDS array | One-line addition, entire deploy pipeline already works |

**Key insight:** This phase is pure prompt engineering. The LLM IS the engine. The command .md tells it what to do, the template .md tells it what structure to produce. No code needed.

## Common Pitfalls

### Pitfall 1: Template Missing the `<!-- OPTIONAL -->` Marker Pattern
**What goes wrong:** Sections like "Output" or "Notes" get generated with "N/A" content instead of being omitted entirely.
**Why it happens:** The template does not mark conditional sections, so the command prompt must carry the entire burden of "omit if empty."
**How to avoid:** Use `<!-- OPTIONAL -- delete if not applicable -->` markers on sections that may not apply (matching existing template convention, e.g., `QUICK_REFERENCE.template.md` lines 117, 131). Also reinforce the "omit empty sections" rule in the command file's Important Principles.
**Warning signs:** Generated READMEs with "None" or "N/A" sections.

### Pitfall 2: Forgetting to Add to COMMANDS Array
**What goes wrong:** Command file exists in source but never gets copied to target during install.
**Why it happens:** The install.sh validation loop checks that each COMMANDS entry has a corresponding file. If the array is not updated, the file ships in source but install.sh ignores it.
**How to avoid:** Explicitly add `auto-doc-script` to the COMMANDS array as a distinct task step with verification.
**Warning signs:** `install.sh --project` succeeds but `/mg:auto-doc-script` is not available in the target.

### Pitfall 3: Argument Parsing Edge Cases
**What goes wrong:** Paths with spaces break, or `--output` at end of string with no value causes LLM confusion.
**Why it happens:** `$ARGUMENTS` is a flat string. Whitespace splitting is naive.
**How to avoid:** The command prompt must specify clear parsing rules: split on whitespace, `--output` consumes next token, everything before `--output` is the target path. Include edge case guidance (empty args, --output without value).
**Warning signs:** LLM fails on paths like `scripts/my tool/run.py` or `--output` at end of input.

### Pitfall 4: Directory Mode with No Clear Entry Point
**What goes wrong:** The LLM generates a vague README that describes files but does not show how to USE the tool.
**Why it happens:** Some directories have no `__main__.py`, no `cli.py`, no argparse -- they are libraries invoked programmatically.
**How to avoid:** The command prompt must handle the "no entry point" case explicitly: print a warning, then document the module's public API / import usage instead of CLI invocation. This is in Claude's Discretion per CONTEXT.md.
**Warning signs:** README has a "Usage" section with no runnable commands.

### Pitfall 5: Template Exemplar Using Wrong Domain
**What goes wrong:** Template exemplar uses Road Runner (portfolio analytics) like other templates, but the SCRIPT_README is for standalone scripts -- the domain mismatch confuses the LLM.
**Why it happens:** Copying from existing templates without adapting the exemplar domain.
**How to avoid:** Use a standalone script exemplar (e.g., a data conversion script, a log analyzer, a deployment helper) that naturally fits the single-script use case. This aligns with the purpose: documenting small tools.
**Warning signs:** Template exemplar shows multi-service architecture in what should be a single-script README.

## Code Examples

Verified patterns from the existing codebase:

### Command Frontmatter Pattern
```markdown
---
name: mg:auto-doc-script
description: Generate a README for a standalone script or small tool directory
allowed-tools: Bash, Read, Write, Glob, Grep
---
```
Source: Matches `auto-doc-add.md` frontmatter format (lines 1-4).

### Template Section Annotation Pattern
```markdown
## Prerequisites
<!-- PURPOSE: List what must be installed or configured before the script can run.
     Include language runtime, pip/npm packages, environment variables, file access.
     Only list items the user must explicitly set up -- not standard library modules. -->
<!-- EXAMPLE:
- Python 3.8+
- `requests` package: `pip install requests`
- Environment variable `API_TOKEN` set to your service token
-->
```
Source: Follows the `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` pattern from all 13 existing templates (e.g., `OVERVIEW.template.md`, `QUICK_REFERENCE.template.md`).

### Optional Section Marker Pattern
```markdown
## Output
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Describe what the script produces: files, stdout format, side effects.
     Users need to know what to expect after running the script. -->
```
Source: Matches `QUICK_REFERENCE.template.md` lines 117-118 and `USER_GUIDE.template.md` line 112.

### Install.sh COMMANDS Array Modification
```bash
COMMANDS=(
  auto-doc
  auto-doc-scan
  auto-doc-generate
  auto-doc-verify
  auto-doc-add
  auto-doc-script
)
```
Source: `auto-doc/install.sh` lines 24-30. Add one entry at end.

### Console Code Block Pattern (for Generated Output)
```console
$ python3 convert.py --input data.csv --format json
Converting 1,247 rows from CSV to JSON...
Output written to data.json (156 KB)
```
Source: CONTEXT.md specifies ` ```console ` blocks with `$` prompt prefix.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `create-docs` naming | `auto-doc` naming | Phase 12 | New command uses `auto-doc-script` (post-rename) |
| Audience-segmented pipeline | Single-file generation | Phase 13 (new) | Fills gap for scripts too small for full pipeline |

**No deprecated patterns apply.** This phase creates new assets that follow current conventions established after the Phase 12 rename.

## Open Questions

1. **Template exemplar domain choice**
   - What we know: Existing templates use Road Runner (portfolio analytics) and DataForge (pipeline tool) as exemplar domains
   - What's unclear: What exemplar domain best fits a standalone script README
   - Recommendation: Use a realistic standalone script (e.g., a CSV-to-JSON converter or log analyzer) that naturally demonstrates Prerequisites, Usage, Examples, Options. Claude's Discretion per CONTEXT.md.

2. **"How it works" section**
   - What we know: CONTEXT.md lists this as Claude's Discretion
   - What's unclear: Whether to include it in the template as an optional section
   - Recommendation: Include as `<!-- OPTIONAL -->` section in the template. Non-trivial scripts benefit from a brief explanation of internal logic. The command should include it when the script has meaningful processing steps.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via pyproject.toml) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map
This phase produces NO Python scripts and NO testable code. The deliverables are:
- A command .md file (LLM instruction prompt -- not programmatically testable)
- A template .md file (static content -- not programmatically testable)
- A one-line install.sh modification (tested by running install.sh against a temp directory)

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| N/A | Command file exists and has correct frontmatter | smoke | `head -5 auto-doc/commands/auto-doc-script.md` | Wave 0 |
| N/A | Template file exists with PURPOSE/EXAMPLE annotations | smoke | `grep -c 'PURPOSE:' auto-doc/references/templates/SCRIPT_README.template.md` | Wave 0 |
| N/A | install.sh COMMANDS array includes auto-doc-script | smoke | `grep 'auto-doc-script' auto-doc/install.sh` | Wave 0 |
| N/A | install.sh deploys the command to target | integration | `bash auto-doc/install.sh --target /tmp/test-install/.claude && test -f /tmp/test-install/.claude/commands/mg/auto-doc-script.md` | Wave 0 |
| N/A | install.sh deploys the template to target | integration | `test -f /tmp/test-install/.claude/auto-doc/references/templates/SCRIPT_README.template.md` | Wave 0 |
| N/A | Resolved command contains absolute TEMPLATES_DIR path | integration | `grep -v '{TEMPLATES_DIR}' /tmp/test-install/.claude/commands/mg/auto-doc-script.md` | Wave 0 |

### Sampling Rate
- **Per task commit:** Smoke checks (file existence, grep for key content)
- **Per wave merge:** Full install.sh integration test against temp directory
- **Phase gate:** All smoke + integration checks pass

### Wave 0 Gaps
None -- no test files needed. All validation is via smoke/integration checks against the delivered files themselves. The existing test infrastructure (`python3 -m pytest`) covers the broader auto-doc tool; this phase adds no Python code.

## Sources

### Primary (HIGH confidence)
- `auto-doc/install.sh` -- Verified COMMANDS array pattern, sed resolution loop, recursive template copy
- `auto-doc/commands/auto-doc-add.md` -- Verified single-agent command pattern (frontmatter, argument parsing, no Task tool)
- `auto-doc/commands/auto-doc.md` -- Verified router command pattern (confirmed no integration needed)
- `auto-doc/references/templates/QUICK_REFERENCE.template.md` -- Verified `<!-- PURPOSE -->` / `<!-- EXAMPLE -->` / `<!-- OPTIONAL -->` annotation pattern
- `auto-doc/references/templates/OVERVIEW.template.md` -- Verified template header comments and exemplar style
- `auto-doc/references/templates/GLOSSARY.template.md` -- Verified template section annotation density
- `auto-doc/references/templates/end-users/USER_GUIDE.template.md` -- Verified `<!-- OPTIONAL -- delete if not applicable -->` marker pattern
- `auto-doc/tool.toml` -- Verified tool metadata format
- `.planning/phases/13-auto-doc-script/13-CONTEXT.md` -- All locked decisions and discretion areas

### Secondary (MEDIUM confidence)
None needed -- all findings verified against primary sources in the codebase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all patterns verified against existing codebase files
- Architecture: HIGH -- file inventory is exactly 2 new files + 1 one-line edit, all following established patterns
- Pitfalls: HIGH -- identified from direct inspection of existing templates and install.sh behavior

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable -- this is internal tooling with no external dependency drift)
