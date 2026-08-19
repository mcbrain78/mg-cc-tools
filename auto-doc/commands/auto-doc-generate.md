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
python3 {MG_INSTALL_EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.yaml
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner (step 1). You read it; you do not modify it.

## Process

### Step 1: Setup

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-generate end-users devops`. Extract as a comma-separated string for the `--audience` flag below. If no audience names provided, omit the flag (all enabled audiences).

Run the setup script to load config, detect mode, build paths, create directories, clean stale artifacts, and split scan data:
```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/generate-setup.py \
  --scan-file .mg/docs/docs-scan.json \
  --config .mg/docs/.docs.config.json \
  --global-config {MG_INSTALL_GLOBAL_CONFIG} \
  --scripts-dir {MG_INSTALL_SCRIPTS_DIR} \
  [--audience AUDIENCES]
```
Add `--audience` only if the user specified audience names.

Parse the JSON output to get all runtime values:
- **Paths:** `project_root`, `docs_dir_abs`, `scan_data_path`, `generate_dir`, `project_model_path`, `database_model_path`, `database_model_summary_path`, `db_table_map_path`, `manifests_dir`, `scan_dir`
- **Mode:** `mode` ("initial" or "update")
- **Audiences:** `audiences` (dict of audience name → {documents: [...]})
- **Audience filter:** `audience_filter_active` (boolean)
- **Scan views:** `scan_views` (dict of audience/glossary → view file path)
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

**Skip this stage entirely if** `mode == "update"` **AND** `{docs_dir_abs}/GLOSSARY.md` already exists. In that case the glossary baseline is already established from a prior run and may carry audit/fix refinements that Stage 1 would overwrite (Stage 1 uses `write-section.py --finalize` without `--merge`, which rebuilds `xml-sources/GLOSSARY.xml` from scratch).

If skipping, print:

```
Stage 1/4: Skipping glossary initial pass (update mode — existing GLOSSARY.md preserved for audit/fix refinements)
```

Stage 3 (reconciliation) still runs unconditionally and merges any writer-proposed terms into the preserved glossary via its existing `--merge` path.

Otherwise (mode is `"initial"`, or `GLOSSARY.md` is absent in update mode — e.g., first filtered run on a project that has other audience docs but no glossary yet):

Print progress: `"Stage 1/4: Building glossary (initial pass)..."`

1. **Spawn a single Agent call** with the glossary-writer agent:

   ```
   Agent(
     description="Build glossary (initial pass)",
     prompt="You are the glossary writer agent.

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/glossary-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views.glossary}
   Project model path: {project_model_path}
   Glossary template path: {MG_INSTALL_TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: initial
   Term proposals dir: {project_root}/.mg/docs/generate/terms/
   Tmp dir: {generate_dir}
   Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
   )
   ```

2. **After agent completes, finalize the glossary state.** Check that the state file exists before running:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {MG_INSTALL_WORKSPACE_DIR}/generate/write-state-glossary.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {MG_INSTALL_WORKSPACE_DIR}/generate/manifest-glossary.json \
       --mode {mode} \
       --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json
   ```

   If the state file does not exist, log a warning and continue. Writers will proceed without a glossary baseline.

3. **Assemble markdown.** If `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/GLOSSARY.xml` exists:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/GLOSSARY.xml \
       --output {docs_dir_abs}/GLOSSARY.md \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json \
       --document GLOSSARY
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

2. **Spawn one Agent call per (audience, document) pair** in `audiences` (from setup output) in a SINGLE message (parallel foreground -- do NOT set `run_in_background`). Each subagent reads its own instructions.

   **Orient-write routing (all audiences).** For each `(audience, document)` pair, check `refined_templates[audience][DOCUMENT]`. If the entry is non-null, spawn a dedicated orient-write Agent for that document. If the entry is null, use the standard prompt for that document.

   When using orient-write, each document gets its OWN Agent call (not a single agent for all documents in an audience) because each document needs its own pre-initialized state file.

   For each document where `refined_templates[audience][DOCUMENT]` is **not null** — orient-write prompt:

   ```
   Agent(
     description="Generate {audience} {DOCUMENT} documentation ({mode} mode, orient-write)",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/{audience_writer_file}

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views[audience]}
   Project model path: {project_model_path}
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {DOCUMENT}
   Mode: {mode}
   Audience: {audience}
   Generate dir: {generate_dir}
   Scripts dir: {MG_INSTALL_SCRIPTS_DIR}
   {additional audience-specific lines}"
   )
   ```

   Where `{audience_writer_file}` resolves per audience:
   - `end-users` → `end-user-writer.md`
   - `developers` → `developer-writer.md`
   - `agents` → `agent-writer.md`
   - `devops` → `devops-writer.md`

   And `{additional audience-specific lines}` are audience-specific prompt additions:
   - `devops`: add `Database model summary path: {database_model_summary_path}` (devops references the DB model summary for high-level schema awareness).
   - `end-users`, `developers`, `agents`: no additional lines.

   For each document where `refined_templates[audience][DOCUMENT]` **is null** — standard prompt (fallback for audiences/documents without a refined template):

   ```
   Agent(
     description="Generate {audience} documentation ({mode} mode)",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/{audience_writer_file}

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views[audience]}
   Project model path: {project_model_path}
   Templates dir: {MG_INSTALL_TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {audiences[audience].documents joined by comma}
   Mode: {mode}"
   )
   ```

   **Key differences in orient-write prompt vs standard prompt:**
   - `Audience` + `Generate dir` replace `Templates dir` -- writer derives paths by convention
   - `Scripts dir` is new -- writer needs it for next-heading.py calls
   - `Documents` is singular (one document per agent call when using orient-write)
   - No file paths for template, state, db-table-map, or db-model -- all pre-initialized by generate-setup.py
   - Since all legacy writers have been migrated to the orient-write protocol, the standard prompt is a pure fallback path for projects that never ran `/mg:auto-doc-prepare-templates`. It will be uncommon in practice; new projects should run prepare-templates.

   The `{audience}` in the templates dir path uses the CONFIG KEY (e.g., `developers/`, `end-users/`, `agents/`, `devops/`).

3. **After all agents complete,** verify each dispatched agent produced output. Build
   `--expect` from the `(audience, document)` pairs you actually spawned agents for:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/check-writer-output.py \
       --generate-dir {MG_INSTALL_WORKSPACE_DIR}/generate \
       --expect "{audience}:{DOCUMENT},{audience}:{DOCUMENT},..."
   ```
   Do **not** check the docs directory here. Writer agents never write markdown — they
   accumulate sections into write-state files, and the documents are not written until
   the Finalize step below. A docs-directory check at this point reports the *previous*
   run's files in update mode and finds nothing but `GLOSSARY.md` on a first run, so it
   would warn when everything succeeded and pass when everything failed.

   `OK` per pair means that agent recorded sections. A non-zero exit lists the pairs
   that produced nothing. Partial generation is acceptable — continue, but carry those
   pairs forward as failed and do not describe their existing files as this run's
   output.

### Finalize Documents

After all writer agents complete, assemble documents from accumulated sections and generate temp manifests.

**For orient-write documents** (any audience + document with a refined template): finalize each per-document state file, all accumulating into the same audience manifest.

For each `write-state-{audience}-{DOCUMENT}.json` file in `{MG_INSTALL_WORKSPACE_DIR}/generate`:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
    --finalize \
    --state-file {MG_INSTALL_WORKSPACE_DIR}/generate/write-state-{audience}-{DOCUMENT}.json \
    --docs-dir {docs_dir_abs} \
    --audience {audience} \
    --manifest-file {MG_INSTALL_WORKSPACE_DIR}/generate/manifest-{audience}.json \
    --mode {mode} \
    --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
    --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json
```

**For standard-prompt documents** (audience + document pairs without a refined template — only possible when `/mg:auto-doc-prepare-templates` was never run for that pair): finalize the single per-audience state file:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
    --finalize \
    --state-file {MG_INSTALL_WORKSPACE_DIR}/generate/write-state-{audience}.json \
    --docs-dir {docs_dir_abs} \
    --audience {audience} \
    --manifest-file {MG_INSTALL_WORKSPACE_DIR}/generate/manifest-{audience}.json \
    --mode {mode} \
    --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
    --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json
```

Skip any audience whose state file(s) do not exist.

This assembles documents from accumulated sections, generates temp manifests, and builds XML source files in `generate/xml-sources/{audience}/`.

### Assemble & Polish

After finalize, reassemble markdown from XML (which now has refs populated from writer-emitted typed_refs). For each XML file produced by finalize:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/{audience}/{DOCUMENT}.xml \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md \
    --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json \
    --audience {audience} \
    --document {DOCUMENT}
```

**This is the point at which documents exist on disk** — not the Stage 2 agent step.
Both writers above record every path they write to the run's ledger, so the report at
the end of this command comes from them rather than from a directory listing.

### Polish Documents

After finalize assembles documents mechanically, spawn a polish subagent per document to smooth the assembled output. Each agent reads the assembled document, improves transitions and consistency, and writes back — but is strictly prohibited from adding new content or references.

For each assembled document file produced by finalize:

```
Agent(
  description="Polish {audience} {DOCUMENT} documentation",
  prompt="You are a documentation polish agent.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/doc-polisher.md

Doc path: {docs_dir_abs}/{audience}/{DOCUMENT}.md"
)
```

Spawn one polish agent per document. Run polish agents in parallel where possible. The polish step does not change symbols or file_paths, so manifests are unaffected.

### Sync Polish Edits to XML

After polish agents complete, sync their edits back to XML and reassemble. For each polished document:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/sync-edits-to-xml.py \
    --md-file {docs_dir_abs}/{audience}/{DOCUMENT}.md \
    --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/{audience}/{DOCUMENT}.xml
```

Then reassemble the final markdown from synced XML:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/{audience}/{DOCUMENT}.xml \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
```

### Manifest Merge

After polish completes, merge temp manifests into persisted location:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/merge-manifests.py \
    --tmp-dir {MG_INSTALL_WORKSPACE_DIR}/generate \
    --output-dir {MG_INSTALL_WORKSPACE_DIR}/generate/reference-manifests \
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

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/glossary-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {scan_views.glossary}
   Project model path: {project_model_path}
   Glossary template path: {MG_INSTALL_TEMPLATES_DIR}/GLOSSARY.template.md
   Style guide path: references/style-guide.md
   Mode: {mode}
   Pass: reconciliation
   Term proposals dir: {project_root}/.mg/docs/generate/terms/
   Tmp dir: {generate_dir}
   Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
   )
   ```

2. **After agent completes, finalize the reconciliation state.** Check that the state file exists before running:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {MG_INSTALL_WORKSPACE_DIR}/generate/write-state-glossary.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {MG_INSTALL_WORKSPACE_DIR}/generate/manifest-glossary.json \
       --mode {mode} \
       --merge \
       --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json
   ```

   If the state file does not exist, the reconciliation produced no changes — continue.

3. **Reassemble.** If `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/GLOSSARY.xml` exists:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/GLOSSARY.xml \
       --output {docs_dir_abs}/GLOSSARY.md \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json \
       --document GLOSSARY
   ```

   The reconciliation log is at `.mg/docs/generate/terms/glossary-reconciliation.log`.

### Stage 4: Generate OVERVIEW.md

**Skip this stage if an audience filter was active in Step 0.** OVERVIEW.md summarizes all audiences and would be incomplete with partial generation. Print: `"Stage 4/4: Skipping OVERVIEW.md (audience filter active)"`

If no audience filter (full generation):

Print progress: `"Stage 4/4: Generating OVERVIEW.md..."`

Generate OVERVIEW.md via a dedicated subagent that reads the actual generated documents through the chunk reader. This ensures OVERVIEW content is derived from what writers actually wrote.

1. **Prepare review chunks** from the generated docs:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/prepare-doc-review.py \
       --docs-dir {docs_dir_abs} \
       --output-dir {MG_INSTALL_WORKSPACE_DIR}/generate/overview-chunks \
       --token-limit 5000
   ```

2. **Spawn the overview writer subagent:**
   ```
   Agent(
     description="Generate OVERVIEW.md from assembled docs",
     prompt="Read and follow: {MG_INSTALL_AGENTS_DIR}/overview-writer.md

     Project root: {project_root}
     Docs dir: {docs_dir_abs}
     Review manifest: {MG_INSTALL_WORKSPACE_DIR}/generate/overview-chunks/manifest.json
     Project model path: {MG_INSTALL_WORKSPACE_DIR}/generate/project-model.json
     Glossary path: {docs_dir_abs}/GLOSSARY.md
     OVERVIEW template: {MG_INSTALL_TEMPLATES_DIR}/OVERVIEW.template.md
     Style guide path: references/style-guide.md
     Tmp dir: {generate_dir}
     Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
   )
   ```

3. **After agent completes, finalize the overview state.** Check that the state file exists before running:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {MG_INSTALL_WORKSPACE_DIR}/generate/write-state-overview.json \
       --docs-dir {docs_dir_abs} \
       --audience "" \
       --manifest-file {MG_INSTALL_WORKSPACE_DIR}/generate/manifest-overview.json \
       --mode {mode} \
       --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json
   ```

   If the state file does not exist, log a warning — the overview agent may have failed.

4. **Reassemble.** If `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/OVERVIEW.xml` exists:

   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/OVERVIEW.xml \
       --output {docs_dir_abs}/OVERVIEW.md \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json \
       --document OVERVIEW
   ```

5. **Verify OVERVIEW.md was created:**
   ```
   Read {docs_dir_abs}/OVERVIEW.md
   ```
   If the file does not exist, log a warning. The pipeline can still complete without OVERVIEW.

### Step 4: Summary and Next Steps

After all generation is complete, present a generation report.

1. **Build the summary from this run's ledger**, not from a listing of the docs
   directory:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/written-docs.py \
       --ledger {MG_INSTALL_WORKSPACE_DIR}/generate/written-docs.json \
       --docs-dir {docs_dir_abs}
   ```
   The ledger holds only paths that `write-section.py --finalize` or
   `assemble-markdown.py` actually wrote this run, so under an audience filter the
   table covers the audiences that were regenerated and leaves the others out —
   which a `{docs_dir_abs}/**/*.md` glob cannot do.

2. **Echo the script's output verbatim.** It emits the table and totals already:

   ```
   Generation Summary:

   | File                          | Sections | Words  |
   |-------------------------------|----------|--------|
   | GLOSSARY.md                   | 5        | 820    |
   | devops/OPERATIONS.md          | 5        | 1,100  |
   | devops/TROUBLESHOOTING.md     | 4        | 800    |

   Total: 3 files, 14 sections, ~2,720 words
   ```

   Do not add rows for documents the script did not list, and do not describe an
   `INCOMPLETE:` or `UNREADABLE:` entry as generated — pass those lines through as
   written. A `WROTE: 0 documents` result means nothing was generated; report that
   rather than falling back to the docs directory.

3. **Show additional stats** (if applicable):
   - If glossary reconciliation added terms: `"New glossary terms: {count} added during reconciliation"` (read from `.mg/docs/generate/terms/glossary-reconciliation.log` if it exists)

4. **Suggest next step:**
   ```
   Next step: Run /mg:auto-doc-auditv2 to verify reference integrity and prose consistency.
   ```

## Key Formats Reference

### File Ownership Header

Every generated file MUST start with this header at the very top, before any other content:

```
<!-- This file is auto-generated by /mg:auto-doc-generate. Manual edits may be overwritten. -->
```

This goes BEFORE the `<!-- DIATAXIS: ... -->` and `<!-- AUDIENCE: ... -->` comments and before the H1 heading:

```markdown
<!-- This file is auto-generated by /mg:auto-doc-generate. Manual edits may be overwritten. -->
<!-- DIATAXIS: explanation + reference -->
<!-- AUDIENCE: developers -->

# Architecture
```

## Important Principles

- **Agents receive file paths only; they read files themselves.** Do not paste source material, templates, or scan data content into subagent prompts. Pass paths as strings. This prevents context limit blowouts on large projects.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: agents/{name}.md`) rather than inlining the full agent definition.
- **File ownership header goes at the very TOP.** Before DIATAXIS comments, before AUDIENCE comments, before the H1 heading.
- **Normalize section identifiers to slug format.** Template headings use Title Case ("System Overview"), but source_material_index uses lowercased-hyphenated slugs ("system-overview"). Always convert to slug format when matching.
- **Generate supports audience filtering** (e.g., `/mg:auto-doc-generate end-users devops`) to speed up iteration. OVERVIEW.md is skipped when filtering.
- **Directory layout, source material key format, and data contracts** are documented in `references/schema.yaml`. Workspace setup (directories, artifact cleanup, scan splitting) is handled by `generate-setup.py`.
