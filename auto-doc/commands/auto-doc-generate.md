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

2. **Read scan data.** Load `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:auto-doc-scan first to analyze the project.
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

#### 2a. Parse Staleness Data

1. Read the `staleness_report` array from `docs-scan.json`. Group entries by `document` name. For each document, count sections per severity level (`high`, `medium`, `low`).

2. Read the `note_classifications` array from `docs-scan.json`. Filter for pending notes only -- notes whose `note_id` does NOT already have `"status": "integrated"` in `.mg/docs/notes-inbox.json`. Count pending notes.

3. Load verify findings. Run:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py \
     --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
     --summary \
     --output {TMP_DIR}/findings-summary.json
   ```
   Read the output file. Extract total findings count and per-document/per-severity breakdowns. If the findings file does not exist or is empty, treat as zero findings.

4. If the staleness report is empty AND there are no pending notes AND there are no verify findings, print:
   ```
   No stale sections, verify findings, or pending notes found. Nothing to update.
   ```
   Then exit gracefully (no generation needed).

#### 2b. Present Level 1 Overview

Use AskUserQuestion to present a document-level summary:

```
Documentation Update Report:

Staleness:
  ARCHITECTURE.md:    3 stale sections (2 high, 1 medium)
  DEVELOPER_GUIDE.md: 1 stale section (1 low)
  SYSTEM_MAP.md:      2 stale sections (2 high)

Verify findings:
  OPERATIONS.md:      2 issues (1 high, 1 medium)
  ARCHITECTURE.md:    1 issue (1 medium)
  Total: 3 findings from last verification run

Inbox notes: 2 pending (1 for ARCHITECTURE, 1 for USER_GUIDE)

How would you like to proceed?
  1. Approve all -- update all stale sections, address all findings, and integrate all notes
  2. Select by document -- choose which documents to update
  3. Select by severity -- approve by minimum severity level
  4. Cancel -- exit without changes
```

If any tier has zero items, omit that tier's section from the overview (but always show at least the tiers that have items). The 4 approval options are uniform across all 3 tiers -- the same options regardless of which tiers are present.

#### 2c. Handle User Selection

- **If "Cancel" (option 4):** Exit with message: `"No sections approved for update. Run again when ready."`

- **If "Approve all" (option 1):** Approve all stale sections from the staleness report, all verify findings, and all pending notes. Build the `approved_sections` dict from the full staleness report and all verify findings.

- **If "Select by document" (option 2):** For each document that has stale sections OR verify findings (or both), use AskUserQuestion to show section details and verify findings **merged per document** with unified numbering. One approval per document covers both staleness and findings:

  ```
  OPERATIONS.md -- 0 stale sections, 2 verify findings:
    Verify findings:
      1. deployment-pipeline -- broken file reference (high)
      2. monitoring-setup -- Diataxis mixing (medium)

  Approve: all / none / specific numbers (e.g., "1,2")
  ```

  ```
  ARCHITECTURE.md -- 3 stale sections, 1 verify finding:
    Stale sections:
      1. system-overview -- src/app.ts changed (2026-03-15) [high]
      2. data-model -- schema.prisma changed (2026-03-14) [high]
      3. component-map -- lib/utils.py changed (2026-03-10) [medium]
    Verify findings:
      4. data-model -- Diataxis mixing (medium)

  Approve: all / none / specific numbers (e.g., "1,2,4")
  ```

  Group by document name first, then list staleness sections and findings together under each document with unified numbering (staleness items numbered first, then findings continue the sequence). One approval per document covers both staleness and findings.

  To get per-document findings for the drill-in, run:
  ```bash
  python3 {SCRIPTS_DIR}/list-verify-findings.py \
    --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
    --document {DOCUMENT} \
    --output {TMP_DIR}/findings-{DOCUMENT}.json
  ```
  Read the output file to get findings for that document.

- **If "Select by severity" (option 3):** Use AskUserQuestion to ask for the minimum severity level:

  ```
  Approve by severity:
    1. High only ({N} sections + findings)
    2. High + Medium ({N} sections + findings)
    3. All severities ({N} sections + findings)
  ```
  Approve all staleness sections AND verify findings at or above the selected severity level. The severity filter applies uniformly to both staleness sections and verify findings.

#### 2d. Notes Approval

After staleness approval is complete, present pending inbox notes as a **separate group**:

```
Pending inbox notes:
  NOTE-003: "Add auth flow documentation" -> ARCHITECTURE/auth-flow [confidence: 0.85]
  NOTE-005: "Document the new CLI flags" -> USER_GUIDE/getting-started [confidence: 0.72]

Approve: all / none / specific IDs (e.g., "NOTE-003")
```

Use AskUserQuestion for this approval. Approved notes will be expanded into their classified document/section during generation by the relevant writer agent.

#### 2e. Build Approved Sections Dict

Combine staleness approvals, findings approvals, and note approvals into a single `approved_sections` dict:

```json
{
  "developers": ["system-overview", "data-model"],
  "agents": ["tool-registry"],
  "end-users": ["getting-started"],
  "devops": ["deployment-pipeline", "monitoring-setup"]
}
```

**Normalize section identifiers to slug format:** Template headings use Title Case (e.g., "System Overview"), but `source_material_index` and `staleness_report` use lowercased-hyphenated slugs (e.g., `system-overview`). Always convert to slug format when building `approved_sections`. Writer agents match by slug.

For approved verify findings: add the finding's `section` slug to the appropriate audience's list in `approved_sections`. A finding's `audience` field determines which audience list it belongs to.

For approved findings, also build a separate `approved_findings` structure so writer agents receive the specific finding details (not just section names):
```json
{
  "devops": {
    "deployment-pipeline": [
      {"check": "reference-integrity", "severity": "high", "description": "...", "suggestion": "..."}
    ],
    "monitoring-setup": [
      {"check": "diataxis", "severity": "medium", "description": "...", "suggestion": "..."}
    ]
  },
  "developers": {
    "data-model": [
      {"check": "diataxis", "severity": "medium", "description": "...", "suggestion": "..."}
    ]
  }
}
```

For notes: add the note's classified `section` slug to the appropriate audience's list in `approved_sections` (so the writer agent regenerates that section and includes the note's expanded content).

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

   Clean temp manifest files from prior runs:
   ```bash
   rm -f {TMP_DIR}/manifest-*.json {TMP_DIR}/manifest-entry-*.json
   ```

5. **Write last_generated timestamp.** Record the current time as the generation baseline for future incremental scans:
   ```bash
   python3 {SCRIPTS_DIR}/set-last-generated.py \
       --scan-file {project_root}/.mg/docs/docs-scan.json
   ```
   This timestamp is written at pipeline START so the next incremental scan's diff window is over-inclusive (commits during this generation cycle will be re-scanned next time, which is harmless).

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

Print progress: `"Stage 2/4: Writing audience documents with manifest emission (4 agents in parallel)..."`

1. **Audience name mapping** (config key -> agent file):
   - `end-users` -> `agents/end-user-writer.md`
   - `developers` -> `agents/developer-writer.md`
   - `agents` -> `agents/agent-writer.md`
   - `devops` -> `agents/devops-writer.md`

2. **In update mode:** Only spawn agents for audiences that have approved sections. If an audience has no sections in the `approved_sections` dict from Step 2, skip it entirely to save subagent cost.

3. **Spawn one Agent call per enabled audience in a SINGLE message** (parallel foreground — do NOT set `run_in_background`). Each subagent reads its own instructions. For each audience:

   **In update mode, before spawning each writer:** If the audience has approved findings (entries in the `approved_findings` dict from Step 2e), load the relevant findings for that audience. For each document that the audience will update, run:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py \
     --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
     --document {DOCUMENT} \
     --audience {audience} \
     --output {TMP_DIR}/findings-{audience}-{DOCUMENT}.json
   ```
   Read the output file to get findings for that audience/document combination.

   Then spawn the Agent:

   ```
   Agent(
     description="Generate {audience} documentation ({mode} mode)",
     prompt="You are a {audience} writer agent.

   Read and follow the instructions in: {AGENTS_DIR}/{audience}-writer.md

   Project root: {project_root}
   Docs dir: {docs_dir_abs}
   Scan data path: {project_root}/.mg/docs/docs-scan.json
   Templates dir: {TEMPLATES_DIR}/{audience}/
   Style guide path: references/style-guide.md
   Glossary path: {docs_dir_abs}/GLOSSARY.md
   Documents: {document_list from config}
   Mode: {mode}
   Update sections: {approved_sections_for_audience or empty list}

   Verify findings for your sections (fix these issues from the previous version):
   [paste findings from the output files -- each has description and suggestion]"
   )
   ```

   Only include findings for sections that were approved. If a finding's section was not approved, omit it. If the audience has no approved findings, omit the "Verify findings" block from the prompt entirely.

   The `{audience}` in the templates dir path uses the CONFIG KEY (e.g., `developers/`, `end-users/`, `agents/`, `devops/`).

4. **After all agents complete,** verify output files exist in each audience subdirectory:
   ```
   Glob pattern: {docs_dir_abs}/**/*.md
   ```
   Log which files were created. If an agent failed to produce output, log a warning but continue -- partial generation is acceptable.

### Manifest Merge

After all writer agents complete, merge their temp manifests into persisted location.

For each audience that had a writer agent run (i.e., each audience that was spawned in Stage 2):

1. Check if `{TMP_DIR}/manifest-{audience}.json` exists. If not, skip this audience (agent produced no manifest entries).

2. Read the temp manifest: `{TMP_DIR}/manifest-{audience}.json`

3. Read persisted manifest (if it exists): `{project_root}/.mg/docs/reference-manifests/{audience}.json`
   If it does not exist, start with an empty manifest: `{"audience": "{audience}", "generated": "", "documents": {}}`

4. **Process _written_sections metadata for stale cleanup.** For each document in the temp manifest:
   - Look for an entry with section key `_written_sections`
   - If found, read its `sections_written` list
   - In the persisted manifest for that document, remove any section entries whose slug is NOT in `sections_written` (these are stale sections that were dropped during regeneration)
   - Delete the `_written_sections` entry from the temp manifest (do not persist metadata)

5. **Overlay temp entries onto persisted manifest.** For each document -> section in the temp manifest, replace the matching (document, section) entry in the persisted manifest. Preserve entries in the persisted manifest that are not in the temp manifest (sections that were not regenerated).

6. **Update timestamp.** Set `generated` to the current ISO timestamp.

7. **Write merged manifest** to `{project_root}/.mg/docs/reference-manifests/{audience}.json`.

This merge logic ensures:
- Initial mode: persisted manifests were cleared in Step 3, so merge equals copy
- Update mode: only regenerated sections are upserted, all other sections preserved
- Stale sections from dropped headings are cleaned up via _written_sections metadata

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
     <!-- This file is auto-generated by /mg:auto-doc. To add content, use /mg:auto-doc-add. Manual edits may be overwritten. -->
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

### Step 4: Notes Integration

After all generation stages complete, update the notes inbox to mark integrated notes.

**Only run this step if** notes were approved during Step 2 (update mode) AND writer agents integrated them during generation.

1. **Read the notes inbox:**
   ```
   Read {project_root}/.mg/docs/notes-inbox.json
   ```

2. **For each approved and integrated note,** update its entry in the `notes` array:
   - Set `"status": "integrated"`
   - Add `"integrated_date": "YYYY-MM-DD"` (today's date)
   - Preserve all other fields (`note_id`, `text`, `classified`, `audience`, `document`, `section`, `confidence`, `expansion_outline`)

3. **Write the full updated inbox** back as a single atomic write:
   ```
   Write the complete notes-inbox.json with all notes (integrated and non-integrated)
   to: {project_root}/.mg/docs/notes-inbox.json
   ```
   Do NOT write notes one at a time. Read the full file, update all integrated notes in memory, and write the complete file once. This prevents partial-update corruption.

### Step 5: Summary and Next Steps

After all generation and notes integration is complete, present a generation report.

1. **Collect stats for each generated or updated file.** For every `.md` file in `{docs_dir_abs}` (including subdirectories):
   - Count sections (`## ` headings)
   - Count words (approximate: split by whitespace, excluding HTML comments and frontmatter)
   - Determine status:
     - `Generated` -- file was created in this run (initial mode, or new file in update mode)
     - `Updated` -- file existed before and was modified in this run (update mode)
     - `Unchanged` -- file existed before and was not modified (update mode, no approved sections)

2. **Present the summary table:**

   ```
   Generation Summary:

   | File                              | Sections | Words  | Status    |
   |-----------------------------------|----------|--------|-----------|
   | GLOSSARY.md                       | 5        | 820    | Generated |
   | end-users/USER_GUIDE.md           | 6        | 1,450  | Generated |
   | developers/ARCHITECTURE.md        | 7        | 2,100  | Generated |
   | developers/DEVELOPER_GUIDE.md     | 5        | 1,800  | Generated |
   | developers/QUICK_REFERENCE.md     | 4        | 650    | Generated |
   | agents/SYSTEM_MAP.md              | 6        | 1,200  | Generated |
   | agents/CONVENTIONS.md             | 4        | 900    | Generated |
   | agents/GOTCHAS.md                 | 3        | 500    | Generated |
   | agents/TESTING.md                 | 4        | 700    | Generated |
   | devops/OPERATIONS.md              | 5        | 1,100  | Generated |
   | devops/TROUBLESHOOTING.md         | 4        | 800    | Generated |
   | OVERVIEW.md                       | 4        | 450    | Generated |

   Total: 12 files, 57 sections, ~12,470 words
   ```

3. **Show additional stats** (if applicable):
   - If verify findings were addressed: `"Verify findings addressed: {count} ({severity breakdown, e.g., 1 high, 2 medium})"`
   - If notes were integrated: `"Notes integrated: {count} ({note_id list})"`
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

- **Agents receive file paths only; they read files themselves.** Do not paste source material, templates, or scan data content into subagent prompts. Pass paths as strings. The locked decision says: "Agents receive file paths only, read files themselves." This prevents context limit blowouts on large projects.

- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: agents/{name}.md`) rather than inlining the full agent definition. This keeps agent instructions out of the orchestrator's context.

- **Create all output directories before spawning writers.** Writer agents assume their target directories exist. Create the full tree in Step 3 before any Stage runs. Failure to do this causes FileNotFoundError in subagents.

- **Clean terms-*.json before each generation run.** Stale term proposal files from prior runs cause the glossary reconciliation to re-add already-reconciled terms. Always delete them in Step 3.

- **OVERVIEW.md is always generated last.** It needs accurate knowledge of what each audience directory contains to build the routing table. Generating it before writers complete produces an inaccurate Audience Guide.

- **Glossary runs first even in update mode.** Even if GLOSSARY.md exists from a prior run, the glossary agent re-runs its initial pass to catch new terms from updated scan data. Skipping it risks terminology drift.

- **Only spawn writer agents for audiences with approved sections in update mode.** If a user only approves developer doc updates, do not spawn end-user, agent, or devops writers. This saves subagent cost and avoids unnecessary work.

- **File ownership header goes at the very TOP.** Before DIATAXIS comments, before AUDIENCE comments, before the H1 heading. This is the first thing in every generated file. It tells users and tools that the file is machine-owned.

- **No memory of rejections between runs.** If a user rejects a stale section during the approval flow, it reappears on the next update run. The generate command does not track rejection history. This is intentional -- the user may change their mind, and the staleness data may change.

- **Normalize section identifiers to slug format.** Template headings use Title Case ("System Overview"), but source_material_index and staleness_report use lowercased-hyphenated slugs ("system-overview"). Always convert to slug format when matching sections.

- **Generate reads verify findings but NEVER clears docs-verify-findings.json.** Only the verify command clears findings (at the start of each verify run). Findings the user skips in the approval flow reappear on the next verify run -- this is correct behavior, not a bug.

- **Tier ordering is staleness -> verify findings -> notes.** This follows logical severity ordering: code changes first, quality issues second, user knowledge third.
