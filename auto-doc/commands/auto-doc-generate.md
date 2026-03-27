---
name: mg:auto-doc-generate
description: Generate or update audience-segmented documentation section-by-section
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
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

2. **Read scan data.** Use the Read tool to read the first 5 lines of `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:auto-doc-scan first to analyze the project.
   ```
   Find the `root_path` field value and store as `project_root`. (The full scan is processed by scripts in later steps -- do not load the entire file.)

3. **Extract runtime paths:**
   - `project_root`: from the `root_path` field read above
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

### Step 2: Load Standing Notes

Load notes from the inbox so they can be passed to writer agents as standing instructions.

1. **Read notes inbox.** Run:
   ```bash
   uv run {SCRIPTS_DIR}/list-notes.py \
     --inbox {project_root}/.mg/docs/notes-inbox.json \
     --output {TMP_DIR}/all-notes.json
   ```
   Read the output file. This returns all classified notes (regardless of status).

2. **Group notes by audience.** For each note, use its `classification.audience` field to build a dict mapping audience → list of notes. Store this for use when spawning writer agents in Stage 2.

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

4. **Prepare manifest workspace.**
   ```bash
   mkdir -p {project_root}/.mg/docs/reference-manifests
   ```

   In initial mode only, clear existing manifests for a clean slate:
   ```bash
   rm -f {project_root}/.mg/docs/reference-manifests/*.json
   ```

   Clean temp manifest and write-section files from prior runs:
   ```bash
   rm -f {TMP_DIR}/manifest-*.json {TMP_DIR}/manifest-entry-*.json
   rm -f {TMP_DIR}/write-state-*.json {TMP_DIR}/section-*.md {TMP_DIR}/refs-*.json {TMP_DIR}/header-*.md
   ```

5. **Write last_generated timestamp.** Record the current time as the generation baseline for future incremental scans:
   ```bash
   python3 {SCRIPTS_DIR}/set-last-generated.py \
       --scan-file {project_root}/.mg/docs/docs-scan.json
   ```
   This timestamp is written at pipeline START so the next incremental scan's diff window is over-inclusive (commits during this generation cycle will be re-scanned next time, which is harmless).

6. **Split scan data into per-audience views.** Create lightweight view files so each writer agent reads only the scan entries relevant to its audience, instead of the full `docs-scan.json`.

   For each enabled audience in the config (end-users, developers, agents, devops), run:
   ```bash
   python3 {SCRIPTS_DIR}/split-scan-by-audience.py \
       --input {project_root}/.mg/docs/docs-scan.json \
       --output {TMP_DIR}/scan-view-{audience}.json \
       --mode audience \
       --audience {audience} \
       --documents {comma_separated_documents_from_config} \
       --project-model-output {TMP_DIR}/project-model.json
   ```

   **Note:** `--project-model-output` is passed on **every** audience split call, but the script only writes the file on the first call (skips if already exists). This avoids needing to special-case which call goes first.

   Then create the glossary view:
   ```bash
   python3 {SCRIPTS_DIR}/split-scan-by-audience.py \
       --input {project_root}/.mg/docs/docs-scan.json \
       --output {TMP_DIR}/scan-view-glossary.json \
       --mode glossary
   ```

   The `{audience}` is the config key (e.g., `end-users`, `developers`, `agents`, `devops`). The `{documents}` is the comma-separated list from `audiences.{audience}.documents` in `.docs.config.json` (e.g., `ARCHITECTURE,DEVELOPER_GUIDE,QUICK_REFERENCE` for developers).

   In update mode, all audience views are created eagerly (not filtered to approved audiences only). Views are tiny temp files -- no point complicating the orchestrator to filter.

### Stage 1: Build Glossary (initial pass)

Print progress: `"Stage 1/4: Building glossary (initial pass)..."`

1. **Spawn a single Agent call** with the glossary-writer agent:

   ```
   Agent(
     description="Build glossary (initial pass)",
     prompt="You are the glossary writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/glossary-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {TMP_DIR}/scan-view-glossary.json
   Project model path: {TMP_DIR}/project-model.json
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

Print progress: `"Stage 2/4: Writing audience documents with manifest emission (4 agents in parallel)..."`

1. **Audience name mapping** (config key -> agent file):
   - `end-users` -> `agents/end-user-writer.md`
   - `developers` -> `agents/developer-writer.md`
   - `agents` -> `agents/agent-writer.md`
   - `devops` -> `agents/devops-writer.md`

2. **Spawn one Agent call per enabled audience in a SINGLE message** (parallel foreground — do NOT set `run_in_background`). Each subagent reads its own instructions. For each audience:

   ```
   Agent(
     description="Generate {audience} documentation ({mode} mode)",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/{audience}-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {TMP_DIR}/scan-view-{audience}.json
   Project model path: {TMP_DIR}/project-model.json
   Templates dir: {TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {document_list from config}
   Mode: {mode}

   Standing notes (incorporate into relevant sections):
   {notes for this audience from Step 2, or 'None' if empty}"
   )
   ```

   For standing notes: if the audience has notes from Step 2, format each as:
   `- {note_id} ({document}/{section}): "{note_text}"`
   If no notes exist for this audience, set to `None`.

   The `{audience}` in the templates dir path uses the CONFIG KEY (e.g., `developers/`, `end-users/`, `agents/`, `devops/`).

3. **After all agents complete,** verify output files exist in each audience subdirectory:
   ```
   Glob pattern: {docs_dir_abs}/**/*.md
   ```
   Log which files were created. If an agent failed to produce output, log a warning but continue -- partial generation is acceptable.

### Finalize Documents

After all writer agents complete, assemble documents from accumulated sections and generate temp manifests. For each enabled audience (end-users, developers, agents, devops):

```bash
python3 {SCRIPTS_DIR}/write-section.py \
    --finalize \
    --state-file {TMP_DIR}/write-state-{audience}.json \
    --docs-dir {docs_dir_abs} \
    --audience {audience} \
    --manifest-file {TMP_DIR}/manifest-{audience}.json \
    --mode {mode}
```

Skip any audience whose state file does not exist (writer was not spawned for that audience).

This assembles documents from accumulated sections and generates temp manifests.

### Polish Documents

After finalize assembles documents mechanically, spawn a polish subagent per document to smooth the assembled output. Each agent reads the assembled document, improves transitions and consistency, and writes back — but is strictly prohibited from adding new content or references.

For each assembled document file produced by finalize:

```
Agent(
  description="Polish {audience} {DOCUMENT} documentation",
  prompt="You are a documentation polish agent.

Read and follow the instructions in: {AGENTS_DIR}/doc-polisher.md

Doc path: {docs_dir_abs}/{audience}/{DOCUMENT}.md"
)
```

Spawn one polish agent per document. Run polish agents in parallel where possible. The polish step does not change symbols or file_paths, so manifests are unaffected.

### Manifest Merge

After polish completes, merge temp manifests into persisted location:

```bash
uv run {SCRIPTS_DIR}/merge-manifests.py \
    --tmp-dir {TMP_DIR} \
    --output-dir {project_root}/.mg/docs/reference-manifests \
    --audiences end-users,developers,agents,devops
```

This handles: reading temp manifests, overlaying onto persisted manifests, cleaning up stale sections via `_written_sections` metadata, setting timestamps, and writing atomically. Audiences with no temp manifest are skipped.

### Stage 3: Reconcile Glossary

Print progress: `"Stage 3/4: Reconciling glossary terms..."`

1. **Spawn a single Agent call** with the glossary-writer agent in reconciliation mode:

   ```
   Agent(
     description="Reconcile glossary terms from writer proposals",
     prompt="You are the glossary writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/glossary-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {TMP_DIR}/scan-view-glossary.json
   Project model path: {TMP_DIR}/project-model.json
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

Generate OVERVIEW.md via a dedicated subagent that reads the actual generated documents through the chunk reader. This ensures OVERVIEW content is derived from what writers actually wrote.

1. **Prepare review chunks** from the generated docs:
   ```bash
   python3 {SCRIPTS_DIR}/prepare-doc-review.py \
       --docs-dir {docs_dir_abs} \
       --output-dir {TMP_DIR}/overview-chunks \
       --token-limit 5000
   ```

2. **Spawn the overview writer subagent:**
   ```
   Agent(
     description="Generate OVERVIEW.md from assembled docs",
     prompt="Read and follow: {AGENTS_DIR}/overview-writer.md

     Project root: {project_root}
     Docs dir: {docs_dir_abs}
     Review manifest: {TMP_DIR}/overview-chunks/manifest.json
     Project model path: {TMP_DIR}/project-model.json
     Glossary path: {docs_dir_abs}/GLOSSARY.md
     OVERVIEW template: {TEMPLATES_DIR}/OVERVIEW.template.md
     Style guide path: references/style-guide.md"
   )
   ```

3. **Verify OVERVIEW.md was created:**
   ```
   Read {docs_dir_abs}/OVERVIEW.md
   ```
   If the file does not exist, log a warning. The pipeline can still complete without OVERVIEW.

### Step 4: Summary and Next Steps

After all generation is complete, present a generation report.

1. **Collect stats for each generated file.** For every `.md` file in `{docs_dir_abs}` (including subdirectories):
   - Count sections (`## ` headings)
   - Count words (approximate: split by whitespace, excluding HTML comments and frontmatter)

2. **Present the summary table:**

   ```
   Generation Summary:

   | File                              | Sections | Words  |
   |-----------------------------------|----------|--------|
   | GLOSSARY.md                       | 5        | 820    |
   | end-users/USER_GUIDE.md           | 6        | 1,450  |
   | developers/ARCHITECTURE.md        | 7        | 2,100  |
   | developers/DEVELOPER_GUIDE.md     | 5        | 1,800  |
   | developers/QUICK_REFERENCE.md     | 4        | 650    |
   | agents/SYSTEM_MAP.md              | 6        | 1,200  |
   | agents/CONVENTIONS.md             | 4        | 900    |
   | agents/GOTCHAS.md                 | 3        | 500    |
   | agents/TESTING.md                 | 4        | 700    |
   | devops/OPERATIONS.md              | 5        | 1,100  |
   | devops/TROUBLESHOOTING.md         | 4        | 800    |
   | OVERVIEW.md                       | 4        | 450    |

   Total: 12 files, 57 sections, ~12,470 words
   ```

3. **Show additional stats** (if applicable):
   - If glossary reconciliation added terms: `"New glossary terms: {count} added during reconciliation"` (read from `.mg/docs/scan-logs/glossary-reconciliation.log` if it exists)

4. **Suggest next step:**
   ```
   Next step: Run /mg:auto-doc-verify to check reference integrity and consistency.
   ```

## Key Formats Reference

### File Ownership Header

Every generated file MUST start with this header at the very top, before any other content:

```
<!-- This file is auto-generated by /mg:auto-doc. To add content, use /mg:auto-doc-add. Manual edits may be overwritten. -->
```

This goes BEFORE the `<!-- DIATAXIS: ... -->` and `<!-- AUDIENCE: ... -->` comments and before the H1 heading:

```markdown
<!-- This file is auto-generated by /mg:auto-doc. To add content, use /mg:auto-doc-add. Manual edits may be overwritten. -->
<!-- DIATAXIS: explanation + reference -->
<!-- AUDIENCE: developers -->

# Architecture
```

### docs-meta HTML Comment

After each `## ` section heading, include a metadata comment for staleness tracking:

```markdown
## System Overview
<!-- docs-meta: last-updated: 2026-03-16, sources: [src/app.ts, src/routes/index.ts] -->
```

Format: `<!-- docs-meta: last-updated: {YYYY-MM-DD}, sources: [{comma-separated source file paths}] -->`

The staleness-check.py script in the scan step parses these comments to detect when source files have changed since the section was last generated.

### Output Directory Layout

```
docs/auto-doc/
  OVERVIEW.md          # Shared -- generated last (Stage 4)
  GLOSSARY.md          # Shared -- generated first + reconciled (Stages 1, 3)
  end-users/
    USER_GUIDE.md
  developers/
    ARCHITECTURE.md
    DEVELOPER_GUIDE.md
    QUICK_REFERENCE.md
  agents/
    SYSTEM_MAP.md
    CONVENTIONS.md
    GOTCHAS.md
    TESTING.md
  devops/
    OPERATIONS.md
    TROUBLESHOOTING.md
```

### Source Material Index Key Format

Keys in the `source_material_index` from scan data follow the format `{DOCUMENT_NAME}/{section-slug}`:
- `DOCUMENT_NAME` matches config entries exactly (uppercase, e.g., `"ARCHITECTURE"`)
- `section-slug` is the template heading lowercased with spaces replaced by hyphens (e.g., `"system-overview"`)

Examples: `ARCHITECTURE/system-overview`, `USER_GUIDE/getting-started`, `OPERATIONS/deployment-pipeline`

## Important Principles

- **Agents receive file paths only; they read files themselves.** Do not paste source material, templates, or scan data content into subagent prompts. Pass paths as strings. This prevents context limit blowouts on large projects.

- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: agents/{name}.md`) rather than inlining the full agent definition. This keeps agent instructions out of the orchestrator's context.

- **Create all output directories before spawning writers.** Writer agents assume their target directories exist. Create the full tree in Step 3 before any Stage runs. Failure to do this causes FileNotFoundError in subagents.

- **Clean terms-*.json before each generation run.** Stale term proposal files from prior runs cause the glossary reconciliation to re-add already-reconciled terms. Always delete them in Step 3.

- **OVERVIEW.md is always generated last.** It needs accurate knowledge of what each audience directory contains to build the routing table. Generating it before writers complete produces an inaccurate Audience Guide.

- **Glossary runs first even in update mode.** Even if GLOSSARY.md exists from a prior run, the glossary agent re-runs its initial pass to catch new terms from updated scan data. Skipping it risks terminology drift.

- **File ownership header goes at the very TOP.** Before DIATAXIS comments, before AUDIENCE comments, before the H1 heading. This is the first thing in every generated file. It tells users and tools that the file is machine-owned.

- **Normalize section identifiers to slug format.** Template headings use Title Case ("System Overview"), but source_material_index and staleness_report use lowercased-hyphenated slugs ("system-overview"). Always convert to slug format when matching sections.

- **Notes are standing instructions.** Both generate and update read all notes from the inbox regardless of status. Notes persist until the user explicitly deletes them. Generate passes notes to writer agents per audience; update routes notes to the fix agent or scoped generate.

- **Generate is for full generation, update is for surgical fixes.** Generate always runs all writers for all audiences. For fixing verify findings or integrating notes into existing docs, use `/mg:auto-doc-update` instead.

- **Subagents receive audience-specific view files, not full scan data.** The orchestrator splits `docs-scan.json` into per-audience view files (Step 3 substep 6) and passes view file paths as `scan_data_path` in Agent() prompts. The project model is extracted to a separate `project-model.json` file (passed as `project_model_path`) to avoid duplicating it in every view.
