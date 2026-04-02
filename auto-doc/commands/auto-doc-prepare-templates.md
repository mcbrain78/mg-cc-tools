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
python3 {EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue -- permissions will require manual approval.

## Before You Start

Read the shared schema that defines the scan data contract:
```
Read references/schema.md
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner. The refiner reads it; it does not modify it.

## Process

### Step 1: Load Config and Scan Data

1. **Load configuration.** Read the project-local config file:
   ```
   Read .mg/docs/.docs.config.json
   ```
   If the project-local config does not exist, fall back to the global config:
   ```
   Read {GLOBAL_CONFIG}
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
2. For each enabled audience, iterate its `documents` array.
3. Do NOT process `config.shared_documents` (OVERVIEW, GLOSSARY). These are shared documents that do not use audience-specific templates and are not consumed by the orient-write loop.

Print the discovery result:
```
Audiences to process:
  end-users: USER_GUIDE
  developers: ARCHITECTURE, DEVELOPER_GUIDE, QUICK_REFERENCE
  agents: SYSTEM_MAP, CONVENTIONS, GOTCHAS, TESTING
  devops: OPERATIONS, TROUBLESHOOTING
Total: {count} documents across {audience_count} audiences
```

### Step 3: Create Output Directories

For each audience, create the output directory:
```bash
mkdir -p .mg/docs/templates/{audience}/
```

This creates the project-local directory structure where refined templates will be written. One directory per audience.

### Step 4: Spawn Refiner Agents

For each `(audience, document)` pair, spawn one Agent call **sequentially** (one agent at a time):

```
Agent(
  description="Refine template for {audience}/{document}",
  prompt="You are the template refiner agent.

Read and follow the instructions in: {AGENTS_DIR}/template-refiner.md

Project root: {project_root}
Generic template: {TEMPLATES_DIR}/{audience}/{document}.template.md
Scan data path: {project_root}/.mg/docs/docs-scan.json
Output path: {project_root}/.mg/docs/templates/{audience}/{document}.template.md
Audience: {audience}
Document: {document}
Scan date: {scan_date}
Scripts dir: {SCRIPTS_DIR}"
)
```

**Key details:**
- `{TEMPLATES_DIR}` resolves to the installed generic templates directory (e.g., `.claude/auto-doc/references/templates/`)
- Output goes to `.mg/docs/templates/` (project-local, not inside `.claude/`)
- Each Agent call passes `{SCRIPTS_DIR}` so the refiner can invoke `get-section-sources.py` and `list-optional-sections.py`
- Spawn agents **sequentially** (one at a time) -- simpler error handling and avoids concurrent reads on shared scan data

After each agent completes, log:
```
  Refined: .mg/docs/templates/{audience}/{document}.template.md
```

If an agent fails, log a warning and continue with the remaining documents. Partial refinement is acceptable.

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
