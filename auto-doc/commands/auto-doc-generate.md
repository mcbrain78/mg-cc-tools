---
name: mg:auto-doc-generate
description: Generate or update audience-segmented documentation section-by-section
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Generator

You are the **Generator** -- step 2 of a 3-step documentation pipeline (scan, generate, verify). Your job is to create or update audience-segmented documentation using templates and scan results. You are the **ONLY** pipeline step that writes documentation files.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 {EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner (step 1). You read it; you do not modify it.

## Process

### Step 1: Setup

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-generate end-users devops`. Extract as a comma-separated string for the `--audience` flag below. If no audience names provided, omit the flag (all enabled audiences).

Run the setup script to load config, detect mode, build paths, create directories, clean stale artifacts, split scan data, and load notes:
```bash
python3 {SCRIPTS_DIR}/generate-setup.py \
  --scan-file .mg/docs/docs-scan.json \
  --config .mg/docs/.docs.config.json \
  --global-config {GLOBAL_CONFIG} \
  --scripts-dir {SCRIPTS_DIR} \
  [--audience AUDIENCES]
```
Add `--audience` only if the user specified audience names.

Parse the JSON output to get all runtime values:
- **Paths:** `project_root`, `docs_dir_abs`, `scan_data_path`, `tmp_dir`, `project_model_path`, `notes_file`, `manifests_dir`, `scan_logs_dir`
- **Mode:** `mode` ("initial" or "update")
- **Audiences:** `audiences` (dict of audience name → {documents: [...]})
- **Audience filter:** `audience_filter_active` (boolean)
- **Scan views:** `scan_views` (dict of audience/glossary → view file path)
- **Notes:** `notes_by_audience` (dict of audience → list of notes)
- **Refined templates:** `refined_templates` (dict of audience → document → `{"path": str, "stale": bool}` or `null`)
- **Stale templates:** `stale_templates` (list of `"audience/document"` strings)

If non-zero exit, print the error and abort.

**Stale template warning:** If `stale_templates` is non-empty, print a warning before continuing:
```
Warning: Refined templates may be stale (scan is newer than template):
  - devops/TROUBLESHOOTING
Run /mg:auto-doc-prepare-templates to refresh.
```
This is a warning only -- do NOT abort. Continue with stale templates.

Print:
```
Mode: {mode}
Docs directory: {docs_dir_abs}
Audiences: {comma-separated audience names}
```

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
   Scan data path: {scan_views.glossary}
   Project model path: {project_model_path}
   Glossary template path: {TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: initial
   Term proposals dir: {project_root}/.mg/docs/scan-logs/
   Tmp dir: {tmp_dir}
   Scripts dir: {SCRIPTS_DIR}"
   )
   ```

2. **After agent completes, finalize the glossary state.** Check that the state file exists before running:

   ```bash
   python3 {SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {TMP_DIR}/write-state-glossary.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {TMP_DIR}/manifest-glossary.json \
       --mode {mode} \
       --xml-dir {project_root}/.mg/docs/xml-sources
   ```

   If the state file does not exist, log a warning and continue. Writers will proceed without a glossary baseline.

3. **Assemble markdown.** If `{project_root}/.mg/docs/xml-sources/GLOSSARY.xml` exists:

   ```bash
   python3 {SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {project_root}/.mg/docs/xml-sources/GLOSSARY.xml \
       --output {docs_dir_abs}/GLOSSARY.md
   ```

4. **Verify** `{docs_dir_abs}/GLOSSARY.md` was created:
   ```
   Read {docs_dir_abs}/GLOSSARY.md
   ```
   If the file does not exist, log a warning and continue.

### Stage 2: Write Audience Documents (parallel)

Print progress: `"Stage 2/4: Writing audience documents with manifest emission (4 agents in parallel)..."`

1. **Audience name mapping** (config key -> agent file):
   - `end-users` -> `agents/end-user-writer.md`
   - `developers` -> `agents/developer-writer.md`
   - `agents` -> `agents/agent-writer.md`
   - `devops` -> `agents/devops-writer.md`

2. **Spawn one Agent call per audience** in `audiences` (from setup output) in a SINGLE message (parallel foreground -- do NOT set `run_in_background`). Each subagent reads its own instructions.

   **For devops audience with orient-write routing:** Check `refined_templates["devops"]` for each document. If a document has a non-null refined template entry, spawn a dedicated orient-write Agent for that document. If a document has a null entry, use the standard prompt for that document.

   When using orient-write, each devops document gets its OWN Agent call (not a single agent for all devops documents) because each document needs its own state file.

   For each devops document where `refined_templates["devops"][DOCUMENT]` is **not null**:

   ```
   Agent(
     description="Generate devops {DOCUMENT} documentation ({mode} mode, orient-write)",
     prompt="You are a devops writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/devops-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views["devops"]}
   Project model path: {project_model_path}
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {DOCUMENT}
   Mode: {mode}
   Refined template path: {refined_templates["devops"][DOCUMENT]["path"]}
   State file path: {tmp_dir}/heading-state-devops-{DOCUMENT}.json
   Scripts dir: {SCRIPTS_DIR}
   Tmp dir: {tmp_dir}

   Standing notes (incorporate into relevant sections):
   {notes for this document, or 'None'}"
   )
   ```

   For each devops document where `refined_templates["devops"][DOCUMENT]` **is null**, use the standard prompt (same as non-devops audiences, with `Templates dir`).

   **For all other audiences (end-users, developers, agents):** Always use the standard prompt (current behavior, unchanged):

   ```
   Agent(
     description="Generate {audience} documentation ({mode} mode)",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/{audience}-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views[audience]}
   Project model path: {project_model_path}
   Templates dir: {TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {audiences[audience].documents joined by comma}
   Mode: {mode}

   Standing notes (incorporate into relevant sections):
   {notes_by_audience[audience] formatted, or 'None' if empty}"
   )
   ```

   **Key differences in orient-write prompt vs standard prompt:**
   - `Refined template path` replaces `Templates dir` -- writer sees ONLY the refined template
   - `State file path` is new -- scoped per document (`heading-state-devops-{DOCUMENT}.json`)
   - `Scripts dir` is new -- writer needs it for next-heading.py calls
   - `Tmp dir` is new -- writer needs it for temp files
   - `Documents` is singular (one document per agent call when using orient-write)

   For standing notes: format each as `- {note_id} ({document}/{section}): "{note_text}"`. If none, set to `None`. For orient-write agents, filter notes to only those matching the specific document.

   The `{audience}` in the templates dir path uses the CONFIG KEY (e.g., `developers/`, `end-users/`, `agents/`, `devops/`).

3. **After all agents complete,** verify output files exist in each audience subdirectory:
   ```
   Glob pattern: {docs_dir_abs}/**/*.md
   ```
   Log which files were created. If an agent failed to produce output, log a warning but continue -- partial generation is acceptable.

### Finalize Documents

After all writer agents complete, assemble documents from accumulated sections and generate temp manifests. For each audience in `audiences` (from setup output):

```bash
python3 {SCRIPTS_DIR}/write-section.py \
    --finalize \
    --state-file {TMP_DIR}/write-state-{audience}.json \
    --docs-dir {docs_dir_abs} \
    --audience {audience} \
    --manifest-file {TMP_DIR}/manifest-{audience}.json \
    --mode {mode} \
    --xml-dir {project_root}/.mg/docs/xml-sources
```

Skip any audience whose state file does not exist (writer was not spawned for that audience).

This assembles documents from accumulated sections, generates temp manifests, and builds XML source files in `.mg/docs/xml-sources/{audience}/`.

### Assemble & Polish

After finalize, reassemble markdown from XML (which now has refs populated from writer-emitted typed_refs). For each XML file produced by finalize:

```bash
python3 {SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {project_root}/.mg/docs/xml-sources/{audience}/{DOCUMENT}.xml \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
```

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

### Sync Polish Edits to XML

After polish agents complete, sync their edits back to XML and reassemble. For each polished document:

```bash
python3 {SCRIPTS_DIR}/sync-edits-to-xml.py \
    --md-file {docs_dir_abs}/{audience}/{DOCUMENT}.md \
    --xml-file {project_root}/.mg/docs/xml-sources/{audience}/{DOCUMENT}.xml
```

Then reassemble the final markdown from synced XML:

```bash
python3 {SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {project_root}/.mg/docs/xml-sources/{audience}/{DOCUMENT}.xml \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
```

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
   Scan data path: {scan_views.glossary}
   Project model path: {project_model_path}
   Glossary template path: {TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: reconciliation
   Term proposals dir: {project_root}/.mg/docs/scan-logs/
   Tmp dir: {tmp_dir}
   Scripts dir: {SCRIPTS_DIR}"
   )
   ```

2. **After agent completes, finalize the reconciliation state.** Check that the state file exists before running:

   ```bash
   python3 {SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {TMP_DIR}/write-state-glossary.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {TMP_DIR}/manifest-glossary.json \
       --mode {mode} \
       --merge \
       --xml-dir {project_root}/.mg/docs/xml-sources
   ```

   If the state file does not exist, the reconciliation produced no changes — continue.

3. **Reassemble.** If `{project_root}/.mg/docs/xml-sources/GLOSSARY.xml` exists:

   ```bash
   python3 {SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {project_root}/.mg/docs/xml-sources/GLOSSARY.xml \
       --output {docs_dir_abs}/GLOSSARY.md
   ```

   The reconciliation log is at `.mg/docs/scan-logs/glossary-reconciliation.log`.

### Stage 4: Generate OVERVIEW.md

**Skip this stage if an audience filter was active in Step 0.** OVERVIEW.md summarizes all audiences and would be incomplete with partial generation. Print: `"Stage 4/4: Skipping OVERVIEW.md (audience filter active)"`

If no audience filter (full generation):

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
     Style guide path: references/style-guide.md
     Tmp dir: {tmp_dir}
     Scripts dir: {SCRIPTS_DIR}"
   )
   ```

3. **After agent completes, finalize the overview state.** Check that the state file exists before running:

   ```bash
   python3 {SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {TMP_DIR}/write-state-overview.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {TMP_DIR}/manifest-overview.json \
       --mode {mode} \
       --xml-dir {project_root}/.mg/docs/xml-sources
   ```

   If the state file does not exist, log a warning — the overview agent may have failed.

4. **Reassemble.** If `{project_root}/.mg/docs/xml-sources/OVERVIEW.xml` exists:

   ```bash
   python3 {SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {project_root}/.mg/docs/xml-sources/OVERVIEW.xml \
       --output {docs_dir_abs}/OVERVIEW.md
   ```

5. **Verify OVERVIEW.md was created:**
   ```
   Read {docs_dir_abs}/OVERVIEW.md
   ```
   If the file does not exist, log a warning. The pipeline can still complete without OVERVIEW.

### Step 4: Summary and Next Steps

After all generation is complete, present a generation report.

1. **Collect stats for each generated file.** For every `.md` file in `{docs_dir_abs}` (including subdirectories):
   - Count sections (`<!-- section:` markers)
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

## Important Principles

- **Agents receive file paths only; they read files themselves.** Do not paste source material, templates, or scan data content into subagent prompts. Pass paths as strings. This prevents context limit blowouts on large projects.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: agents/{name}.md`) rather than inlining the full agent definition.
- **File ownership header goes at the very TOP.** Before DIATAXIS comments, before AUDIENCE comments, before the H1 heading.
- **Normalize section identifiers to slug format.** Template headings use Title Case ("System Overview"), but source_material_index uses lowercased-hyphenated slugs ("system-overview"). Always convert to slug format when matching.
- **Notes are standing instructions.** Generate passes notes to writer agents per audience. Notes persist until the user explicitly deletes them.
- **Generate supports audience filtering** (e.g., `/mg:auto-doc-generate end-users devops`) to speed up iteration. OVERVIEW.md is skipped when filtering. For surgical fixes, use `/mg:auto-doc-update` instead.
- **Directory layout, source material key format, and data contracts** are documented in `references/schema.md`. Workspace setup (directories, artifact cleanup, scan splitting) is handled by `generate-setup.py`.
