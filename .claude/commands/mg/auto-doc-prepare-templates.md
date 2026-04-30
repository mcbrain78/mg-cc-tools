---
name: mg:auto-doc-prepare-templates
description: Produce project-specific refined templates from scan data and shallow source exploration
allowed-tools: Bash, Read, Write, Glob, Grep, Agent
---

# Template Refiner

You are the **Template Refiner** -- an optional step between scan and generate. Your job is to produce project-specific refined templates that replace the generic templates during documentation generation. You read scan data and project configuration, then spawn one refiner agent per audience/document pair.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 .claude/permission-hooks/scripts/emit-context.py AUTO-DOC
```
If the script is not found, continue -- permissions will require manual approval.

## Before You Start

Read the shared schema that defines the scan data contract:
```
Read .claude/auto-doc/references/schema.yaml
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner. The refiner reads it; it does not modify it.

## Process

### Step 0: Parse Arguments

Parse `$ARGUMENTS` for optional audience names. Example: user types `/mg:auto-doc-prepare-templates devops` or `/mg:auto-doc-prepare-templates end-users developers`. Extract as a list of audience names to filter on. If no arguments provided, process all enabled audiences.

### Step 1: Load Config and Scan Data

1. **Load configuration.** Read the project-local config file:
   ```
   Read .mg/docs/.docs.config.json
   ```
   If the project-local config does not exist, fall back to the global config:
   ```
   Read .claude/auto-doc/references/.docs.config.json
   ```
   Parse the JSON to get the `audiences` object and `shared_documents` array.

2. **Load scan data.** Read the scan output:
   ```
   Read .mg/docs/docs-scan.json
   ```
   Extract from the top level:
   - `scan_date` -- used for the `<!-- REFINED: -->` metadata comment
   - `project_model` -- project structure and technology information
   - `source_material_index` -- per-section source file mappings
   - `gap_analysis` -- coverage gaps identified during scan

   If `docs-scan.json` does not exist, abort with:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json
   Run /mg:auto-doc-scan first to generate scan data.
   ```

3. **Determine project root:**
   ```bash
   pwd
   ```

### Step 2: Discover Audience/Document Pairs

Build a list of `(audience, document)` pairs to process:

1. Iterate over `config.audiences` -- skip any audience where `enabled` is `false`.
2. **If audience filter is active** (from Step 0), skip any audience not in the filter list. If a filtered name doesn't match any enabled audience, print a warning: `"Warning: audience '{name}' not found or not enabled -- skipping"`
3. For each remaining audience, iterate its `documents` array.
4. Do NOT process `config.shared_documents` (OVERVIEW, GLOSSARY). These are shared documents that do not use audience-specific templates and are not consumed by the orient-write loop.

Print the discovery result:
```
Audience filter: devops          <-- only if filter active; omit line otherwise
Audiences to process:
  devops: OPERATIONS, TROUBLESHOOTING
Total: {count} documents across {audience_count} audiences
```

### Step 3: Create Output Directories

For each audience, create the output directory:
```bash
mkdir -p .mg/docs/templates/{audience}/
```

This creates the project-local directory structure where refined templates will be written. One directory per audience.

### Step 3.5: Split Scan Data into Per-Audience Views

Create a temporary directory and split the full scan into lightweight per-audience view files
that refiner agents can read within their context limits:

```bash
TMP_DIR=$(mktemp -d)
```

For each audience to process, run:
```bash
uv run .claude/auto-doc/scripts/split-scan-by-audience.py \
  --input .mg/docs/docs-scan.json \
  --output $.mg/docs/generate/scan-views/scan-view-${audience}.json \
  --mode audience \
  --audience ${audience} \
  --documents ${comma_separated_documents} \
  --project-model-output $.mg/docs/generate/project-model.json
```

Where `${comma_separated_documents}` is the comma-joined list of document names for that audience (e.g., `OPERATIONS,TROUBLESHOOTING`).

This produces:
- One `scan-view-{audience}.json` per audience (filtered source_material_index + gap_analysis, source_files stripped)
- One `project-model.json` (slimmed, written once by first caller)

These are read-only shared resources -- safe for parallel agent access.

### Step 4: Spawn Refiner Agents

Spawn **all** Agent calls in a **single message** (parallel foreground -- do NOT set `run_in_background`). For each `(audience, document)` pair:

```
Agent(
  description="Refine template for {audience}/{document}",
  prompt="You are the template refiner agent.

Read and follow the instructions in: .claude/auto-doc/agents/template-refiner.md

Project root: {project_root}
Generic template: .claude/auto-doc/references/templates/{audience}/{document}.template.md
Parsed template path: {project_root}/.mg/docs/scan/templates/template-{document}.json
Scan view path: $.mg/docs/generate/scan-views/scan-view-${audience}.json
Project model path: $.mg/docs/generate/project-model.json
Output path: {project_root}/.mg/docs/templates/{audience}/{document}.template.md
Audience: {audience}
Document: {document}
Scan date: {scan_date}
Scripts dir: .claude/auto-doc/scripts
Validate script: .claude/auto-doc/scripts/validate-refined-template.py"
)
```

**Key details:**
- `.claude/auto-doc/references/templates` resolves to the installed generic templates directory (e.g., `.claude/auto-doc/references/templates/`)
- Output goes to `.mg/docs/templates/` (project-local, not inside `.claude/`)
- Each Agent call passes `.claude/auto-doc/scripts` so the refiner can invoke `get-section-sources.py` and `list-optional-sections.py`
- The **parsed template JSON** at `.mg/docs/scan/templates/template-{document}.json` is produced deterministically by `parse-template.py` during scan Step 4b. The refiner consumes this as its structured source of truth for section slugs and directives (`synthesized_from`, `boundary`, `optional`, `purpose`) — no need to re-parse the generic template
- Agents read the lightweight `scan-view-{audience}.json` instead of the full `docs-scan.json` -- avoids context limit failures
- `get-section-sources.py` uses `--project-root` to derive the full scan path by convention
- Parallel execution is safe: all shared resources (view files, project model, generic templates, scripts) are read-only; each agent writes to a unique output path

After all agents complete, log each result:
```
  Refined: .mg/docs/templates/{audience}/{document}.template.md
```

If any agent fails, log a warning for that document. Partial refinement is acceptable.

### Step 5: Summary

After all agents complete, discover the refined templates that were created:
```
Glob pattern: .mg/docs/templates/**/*.template.md
```

Print the summary:
```
Template Refinement Complete

Refined templates:
  .mg/docs/templates/end-users/USER_GUIDE.template.md
  .mg/docs/templates/developers/ARCHITECTURE.template.md
  ...

Total: {count} refined templates created
Scan date used: {scan_date}

Next step: Run /mg:auto-doc-generate to generate documentation using refined templates.
```
