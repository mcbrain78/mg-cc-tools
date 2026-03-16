---
name: mg:create-docs-generate
description: Generate or update audience-segmented documentation section-by-section
allowed-tools: Bash, Read, Write, Glob, Grep, Task, AskUserQuestion
---

# Documentation Generator

You are the **Generator** -- step 2 of a 3-step documentation pipeline (scan, generate, verify). Your job is to create or update audience-segmented documentation using templates and scan results. You are the **ONLY** pipeline step that writes documentation files.

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner (step 1). You read it; you do not modify it.

## Process

### Step 1: Load Context and Detect Mode

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)
   - `shared_documents` (e.g., `["OVERVIEW", "GLOSSARY"]`)

2. **Read scan data.** Load `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:create-docs-scan first to analyze the project.
   ```

3. **Extract runtime paths:**
   - `project_root`: from scan data `root_path` field
   - `scan_data_path`: `{project_root}/.mg/docs/docs-scan.json`
   - `docs_dir_abs`: `{project_root}/{docs_dir}` (absolute path to output directory)

4. **Detect mode:**
   - Use Glob to check if `{docs_dir}` contains any `.md` files
   - If yes: `mode = "update"`
   - If no: `mode = "initial"`
   - Cross-check with the scan data `mode` field. If they disagree, trust the filesystem check (docs may have been added or removed since the scan).

5. **Print mode:**
   ```
   Mode: {mode}
   Project: {project name from scan data}
   Docs directory: {docs_dir_abs}
   ```

### Step 2: Update Approval Flow (update mode only)

If mode is `"initial"`, skip this step entirely and proceed to Step 3.

<!-- UPDATE APPROVAL FLOW: Added by Task 2 -->

### Step 3: Prepare Workspace

1. **Create output directories.** Ensure the full directory tree exists before spawning any writer agents:
   ```bash
   mkdir -p {docs_dir_abs}/end-users {docs_dir_abs}/developers {docs_dir_abs}/agents {docs_dir_abs}/devops
   ```

2. **Clean stale term proposals.** Remove leftover `terms-*.json` files from prior runs to prevent the glossary reconciliation pass from re-adding already-reconciled terms:
   ```bash
   rm -f {project_root}/.mg/docs/scan-logs/terms-*.json
   ```

3. **Clean glossary reconciliation log** from prior runs:
   ```bash
   rm -f {project_root}/.mg/docs/scan-logs/glossary-reconciliation.log
   ```

### Stage 1: Build Glossary (initial pass)

Print progress: `"Stage 1/4: Building glossary (initial pass)..."`

1. **Read the glossary writer agent file:**
   ```
   Read agents/glossary-writer.md
   ```
   Store the full file contents.

2. **Spawn a single Task call** with the glossary-writer agent:

   ```
   Task(
     description="Build glossary (initial pass)",
     prompt="You are the glossary writer agent.

   [paste full contents of agents/glossary-writer.md here]

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {project_root}/.mg/docs/docs-scan.json
   Glossary template path: {TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: initial
   Term proposals dir: {project_root}/.mg/docs/scan-logs/"
   )
   ```

3. **Wait for completion.** Verify `{docs_dir_abs}/GLOSSARY.md` was created:
   ```
   Read {docs_dir_abs}/GLOSSARY.md
   ```
   If the file does not exist, log a warning and continue. Writers will proceed without a glossary baseline.

### Stage 2: Write Audience Documents (parallel)

Print progress: `"Stage 2/4: Writing audience documents (4 agents in parallel)..."`

1. **For each enabled audience** in config (e.g., `end-users`, `developers`, `agents`, `devops`), read the corresponding writer agent file:
   ```
   Read agents/{audience}-writer.md
   ```
   Where `{audience}` maps to: `end-user`, `developer`, `agent`, `devops`. Store each file's contents.

   **Audience name mapping** (config key -> agent file):
   - `end-users` -> `agents/end-user-writer.md`
   - `developers` -> `agents/developer-writer.md`
   - `agents` -> `agents/agent-writer.md`
   - `devops` -> `agents/devops-writer.md`

2. **In update mode:** Only spawn agents for audiences that have approved sections. If an audience has no sections in the `approved_sections` dict from Step 2, skip it entirely to save subagent cost.

3. **Spawn one Task call per enabled audience in a SINGLE message** (parallel execution). For each audience:

   ```
   Task(
     description="Generate {audience} documentation ({mode} mode)",
     prompt="You are a {audience} writer agent.

   [paste full contents of agents/{audience}-writer.md here]

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {project_root}/.mg/docs/docs-scan.json
   Templates dir: {TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {document_list from config}
   Mode: {mode}
   Update sections: {approved_sections_for_audience or empty list}"
   )
   ```

   The `{audience}` in the templates dir path uses the CONFIG KEY (e.g., `developers/`, `end-users/`, `agents/`, `devops/`).

4. **After all agents complete,** verify output files exist in each audience subdirectory:
   ```
   Glob pattern: {docs_dir_abs}/**/*.md
   ```
   Log which files were created. If an agent failed to produce output, log a warning but continue -- partial generation is acceptable.

### Stage 3: Reconcile Glossary

Print progress: `"Stage 3/4: Reconciling glossary terms..."`

1. **Read the glossary writer agent file** (same as Stage 1):
   ```
   Read agents/glossary-writer.md
   ```

2. **Spawn a single Task call** with the glossary-writer agent in reconciliation mode:

   ```
   Task(
     description="Reconcile glossary terms from writer proposals",
     prompt="You are the glossary writer agent.

   [paste full contents of agents/glossary-writer.md here]

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {project_root}/.mg/docs/docs-scan.json
   Glossary template path: {TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: reconciliation
   Term proposals dir: {project_root}/.mg/docs/scan-logs/"
   )
   ```

3. **Wait for completion.** The glossary-writer updates `{docs_dir_abs}/GLOSSARY.md` in place and writes a reconciliation log to `.mg/docs/scan-logs/glossary-reconciliation.log`.

### Stage 4: Generate OVERVIEW.md

Print progress: `"Stage 4/4: Generating OVERVIEW.md..."`

Generate OVERVIEW.md **inline** (not via subagent). The orchestrator already has context of what was generated across all audiences.

1. **Read the OVERVIEW template:**
   ```
   Read {TEMPLATES_DIR}/OVERVIEW.template.md
   ```

2. **Survey generated documents.** For each audience directory, list the generated `.md` files and read the first H1 heading from each:
   ```
   Glob pattern: {docs_dir_abs}/**/*.md
   ```
   For each file found, read the first few lines to extract the H1 heading and any introductory text.

3. **Read the scan data** for the project model (tech stack, components, entry points) and the glossary for key concepts.

4. **Generate OVERVIEW.md** following the template structure:
   - **File ownership header** at the very top (before any template content):
     ```
     <!-- This file is auto-generated by /mg:create-docs. To add content, use /mg:add-docs. Manual edits may be overwritten. -->
     ```
   - **DIATAXIS and AUDIENCE comments** from the template
   - **System Purpose** section: project intro from scan data project model
   - **Key Concepts** section: top domain terms from the glossary, with link to full GLOSSARY.md
   - **Architecture at a Glance** section: component overview from scan data project model, ASCII diagram if enough info
   - **Audience Guide** section: routing table linking to each audience's starting document with description of what they will find
   - **docs-meta comment** after each section heading:
     ```
     <!-- docs-meta: last-updated: YYYY-MM-DD, sources: [relevant source files] -->
     ```

5. **Write to** `{docs_dir_abs}/OVERVIEW.md`.

<!-- REMAINING SECTIONS (Step 4: Notes Integration, Step 5: Summary) added by Task 2 -->
