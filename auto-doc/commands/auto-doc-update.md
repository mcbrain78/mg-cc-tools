---
name: mg:auto-doc-update
description: Fix verify findings and integrate notes into existing documentation
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Updater

You are the **Updater** -- a post-verify step that surgically fixes documentation issues and integrates pending notes. Unlike generate (which creates/recreates full documents), update makes targeted edits to existing docs.

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

## Process

### Step 1: Load Context

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{MG_INSTALL_GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)

2. **Read scan data.** Use the Read tool to read the first 5 lines of `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:auto-doc-scan first.
   ```
   Find the `root_path` field value and store as `project_root`.

3. **Verify docs exist.** Use Glob to check if `{docs_dir}/` contains any `.md` files. If not, abort with:
   ```
   Error: No documentation found in {docs_dir}/.
   Run /mg:auto-doc-generate first to create initial documentation.
   ```

4. **Extract runtime paths:**
   - `project_root`: from the `root_path` field
   - `scan_data_path`: `{project_root}/.mg/docs/docs-scan.json`
   - `docs_dir_abs`: `{project_root}/{docs_dir}`

### Step 2: Gather Work Items

1. **Load verify findings.** Run:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/list-verify-findings.py \
     --findings-file {project_root}/.mg/docs/verify/findings.json \
     --summary \
     --output {MG_INSTALL_WORKSPACE_DIR}/update/findings-summary.json
   ```
   Read the output file. If the file does not exist or total is 0, treat as zero findings.

2. **Load notes.** Run:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/list-notes.py \
     --inbox {project_root}/.mg/docs/notes-inbox.json \
     --output {MG_INSTALL_WORKSPACE_DIR}/update/all-notes.json
   ```
   Read the output file. This returns all classified notes (ignores status).

3. **Check for unclassified notes.** Read `{project_root}/.mg/docs/notes-inbox.json` directly. For any note where `classification` is null or missing, run:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/classify-note.py \
     --text "<note_text>" \
     --note-id <note_id> \
     --inbox {project_root}/.mg/docs/notes-inbox.json
   ```
   Then present each newly classified note to the user via AskUserQuestion for confirmation (same flow as auto-doc-add Step 5). After classification, re-run list-notes.py to refresh the notes list.

4. **Load staleness report** from `docs-scan.json`. Read the `staleness_report` array. Count stale sections by severity.

5. **Check for empty work.** If verify findings total is 0 AND notes list is empty AND staleness report is empty, print:
   ```
   No verify findings, notes, or stale sections found. Nothing to update.
   ```
   Then exit gracefully.

### Step 3: Classify Routing

For each work item, determine the routing:

1. **For each verify finding:** Check if the finding's `section` exists in the target document (use Glob/Read to check `{docs_dir_abs}/{audience}/{DOCUMENT}.md` for a `## ` heading that slugifies to the section name).
   - Section exists → **FIX** (surgical edit via doc-fixer)
   - Section missing (completeness finding) → **GENERATE** (scoped generate via writer)

2. **For each classified note:** Check if the note's classified section exists in the target document.
   - Section exists → **FIX** (incorporate via doc-fixer)
   - Section missing → **GENERATE** (new section via writer)

3. **For staleness entries:** Route as **DEFERRED**. These require source re-analysis, not surgical fixes.

### Step 4: Present Summary + Approval

Use AskUserQuestion to present the update plan:

```
Documentation Update Plan:

Surgical fixes (doc-fixer agent):
  OPERATIONS.md: 2 findings
  ARCHITECTURE.md: 1 finding, 1 note
  Total: {N} findings + {N} notes

New sections (writer agents):
  DEVELOPER_GUIDE.md: 1 section (adding-a-new-scoring-model)
  Total: {N} sections

Deferred (run scan → generate for these):
  {N} stale sections

Approve: all / fixes only / by document / cancel
```

Handle user response:
- **"all"**: Approve everything (fixes + new sections)
- **"fixes only"**: Approve only FIX items, skip GENERATE items
- **"by document"**: Present per-document drill-down via AskUserQuestion, let user approve/skip each
- **"cancel"**: Exit with `"No updates approved. Run again when ready."`

### Step 5: Execute Fixes

Group FIX items by document. Write each document's items to a temp JSON file, then spawn one doc-fixer agent per document. Run fix agents as **parallel foreground** (do NOT set `run_in_background`) so their output is visible inline and errors are immediately apparent:

1. **Write fix items per document.** For each document, write its fix items array to `{MG_INSTALL_WORKSPACE_DIR}/update/fix-items-{DOCUMENT}.json`. Each item follows one of these formats:

   Finding:
   ```json
   {"type": "finding", "section": "deployment-pipeline", "description": "...", "suggestion": "...", "check": "reference-integrity"}
   ```

   Note:
   ```json
   {"type": "note", "section": "auth-flow", "note_text": "...", "note_id": "NOTE-003"}
   ```

2. **Spawn agents.** One per document, all in a single message (parallel foreground — do NOT set `run_in_background`):

   ```
   Agent(
     description="Fix {audience} {DOCUMENT}",
     prompt="You are a documentation fix agent.

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/doc-fixer.md

   doc_path: {docs_dir_abs}/{audience}/{DOCUMENT}.md
   audience: {audience}
   project_model_path: {MG_INSTALL_WORKSPACE_DIR}/update/project-model.json
   glossary_path: {docs_dir_abs}/GLOSSARY.md
   style_guide_path: references/style-guide.md
   items_path: {MG_INSTALL_WORKSPACE_DIR}/update/fix-items-{DOCUMENT}.json

   Read the items_path file to get the JSON array of fix items for this document. Apply all fixes."
   )
   ```

3. **After all fix agents complete,** log their results.

4. **Sync fix edits to XML** (if XML sources exist). Check if `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/` directory exists. If so, for each document that was fixed:

   ```bash
   python3 {MG_INSTALL_SCRIPTS_DIR}/sync-edits-to-xml.py \
       --md-file {docs_dir_abs}/{audience}/{DOCUMENT}.md \
       --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/{audience}/{DOCUMENT}.xml \
       --changed-only
   ```

   Parse the JSON output (list of changed slugs). Then reassemble markdown from the updated XML:

   ```bash
   python3 {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
       --xml-file {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/{audience}/{DOCUMENT}.xml \
       --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
   ```

   Skip any document whose XML file does not exist (e.g., standalone docs that were fixed directly).

### Step 6: Execute Scoped Generate

**Only run this step if** there are approved GENERATE items (new sections).

1. **Prepare workspace.** Ensure output directories exist:
   ```bash
   mkdir -p {docs_dir_abs}/end-users {docs_dir_abs}/developers {docs_dir_abs}/agents {docs_dir_abs}/devops
   ```

   Clean temp files from prior runs:
   ```bash
   rm -f {MG_INSTALL_WORKSPACE_DIR}/update/write-state-*.json {MG_INSTALL_WORKSPACE_DIR}/update/section-*.md {MG_INSTALL_WORKSPACE_DIR}/update/refs-*.json {MG_INSTALL_WORKSPACE_DIR}/update/header-*.md
   rm -f {MG_INSTALL_WORKSPACE_DIR}/update/manifest-*.json
   ```

2. **Split scan data** per audience (same as generate step). For each audience with approved GENERATE items:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/split-scan-by-audience.py \
       --input {project_root}/.mg/docs/docs-scan.json \
       --output {MG_INSTALL_WORKSPACE_DIR}/update/scan-view-{audience}.json \
       --mode audience \
       --audience {audience} \
       --documents {comma_separated_documents} \
       --project-model-output {MG_INSTALL_WORKSPACE_DIR}/update/project-model.json
   ```

3. **Spawn writer agents** for audiences with new sections. Each writer runs with `mode: update` and `update_sections` limited to the new section slugs:

   Collect any relevant notes for sections being generated (notes classified to the new section). Include them as standing instructions.

   ```
   Agent(
     description="Generate new {audience} sections",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/{audience}-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {MG_INSTALL_WORKSPACE_DIR}/update/scan-view-{audience}.json
   Project model path: {MG_INSTALL_WORKSPACE_DIR}/update/project-model.json
   Templates dir: {MG_INSTALL_TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {document_list}
   Mode: update
   Update sections: {new_section_slugs}

   Standing notes (incorporate into relevant sections):
   {notes for these sections}"
   )
   ```

4. **Finalize with --merge** to preserve existing doc content:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/write-section.py \
       --finalize \
       --state-file {MG_INSTALL_WORKSPACE_DIR}/update/write-state-{audience}.json \
       --docs-dir {docs_dir_abs} \
       --audience {audience} \
       --manifest-file {MG_INSTALL_WORKSPACE_DIR}/update/manifest-{audience}.json \
       --mode update \
       --merge
   ```

5. **Merge manifests** for new sections:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/merge-manifests.py \
       --tmp-dir {MG_INSTALL_WORKSPACE_DIR}/update \
       --output-dir {MG_INSTALL_WORKSPACE_DIR}/generate/reference-manifests \
       --audiences {audiences_with_new_sections}
   ```

### Step 7: Summary

Present results:

```
Update Summary:

Fixes applied:
  OPERATIONS.md: 2 findings fixed
  ARCHITECTURE.md: 1 finding + 1 note fixed
  Total: {N} fixed, {N} skipped

New sections generated:
  DEVELOPER_GUIDE.md: 1 section added
  Total: {N} sections

Deferred:
  {N} stale sections (run /mg:auto-doc-scan then /mg:auto-doc-generate)

Next step: Run /mg:auto-doc-verify to check the updated documentation.
```

## Important Principles

- **Update never creates documents from scratch.** It fixes existing docs or adds sections to them. For initial generation, use `/mg:auto-doc-generate`.
- **Fixes are surgical.** The doc-fixer agent edits specific sections, not whole documents. This is cheaper and less error-prone than regeneration.
- **Notes are standing instructions.** Both generate and update read all notes regardless of status. Notes persist until the user explicitly deletes them.
- **Staleness is deferred.** Stale sections need source re-analysis (scan), which update cannot do. Tell the user to run scan → generate instead.
- **Use `--merge` for scoped generate.** When adding new sections, the `--merge` flag on write-section.py finalize preserves all existing content in the document.
- **Agents receive file paths only; they read files themselves.** Do not paste document content, source material, or scan data into subagent prompts. Pass paths as strings.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/doc-fixer.md`) rather than inlining the full agent definition.
- **Generate reads verify findings but NEVER clears verify/findings.json.** Only the verify command clears findings.
