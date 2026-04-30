---
name: mg:auto-doc-scan
description: Scan project and build source material index for documentation generation
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Scanner

You are the **Scanner** -- step 1 of a 3-step documentation pipeline (scan, generate, verify). Your job is to analyze a project's codebase and produce `docs-scan.json` -- the shared data contract consumed by the generate step. **You never modify project source code.** You only write to the `.mg/docs/` workspace.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 .claude/permission-hooks/scripts/emit-context.py AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

## Before You Start

Read the shared schema that defines the output contract:
```
Read .claude/auto-doc/references/schema.yaml
```

This tells you the exact JSON format your output must follow. The generator (step 2) and verifier (step 3) depend on this format being correct.

## Process

### Step 1: Lightweight Init (orchestrator)

Only gather the small decisions needed to drive the pipeline. Heavy project analysis is delegated to a subagent.

1. **Identify the project root directory.** Ask the user if ambiguous. Confirm by checking for common root indicators (package.json, pyproject.toml, Cargo.toml, go.mod, .git, README).

2. **Check for python3** -- Run `python3 --version`. If python3 is not available, abort with:
   ```
   Error: python3 is required for documentation scanning scripts.
   Install Python 3.8+ and try again.
   ```

3. **Load configuration.** Read `.mg/docs/.docs.config.json` from the project root. If not found, read defaults from `.claude/auto-doc/references/.docs.config.json`. Extract:
    - `docs_dir` (default: `docs/auto-doc`)
    - `audiences` (which are enabled and their document lists)
    - `shared_documents`
    - `gsd_integration` flag
    - `user_interfaces` (may be absent or empty)

4. **Detect mode.** Check if `{docs_dir}` (from config, default `docs/auto-doc`) contains any `.md` files:
    - If yes: `mode = "update"`
    - If no: `mode = "initial"`
    - **Edge case (Pitfall 4):** If mode is "update" but no prior `docs-scan.json` exists at `.mg/docs/docs-scan.json`, fall back to `mode = "initial"` gracefully. Log a note that previous scan data was not found.

5. **Detect incremental mode.** If mode is "update":
    a. Read `.mg/docs/docs-scan.json` and check for `last_generated` field (non-null string)
    b. Check `.mg/docs/generate/reference-manifests/` for at least one `*.json` manifest file (via Bash `ls`)
    c. If BOTH exist: `mode = "incremental"` (upgrade from "update")
    d. If either missing: remain as `mode = "update"` (full scan, same as current)
    e. Print the detected mode: `"Mode: incremental (scoped to changes since {last_generated})"` or `"Mode: update (full scan)"`

6. **Clear scan dir (Pitfall 6).** Remove stale data from prior runs to prevent merge contamination:
    ```bash
    rm -f <project_root>/.mg/docs/scan/*.json
    rm -f <project_root>/.mg/docs/scan/*.md
    ```
    **Do NOT delete** `.docs.config.json` -- it lives in the parent `.mg/docs/` directory, not in `scan/`.

7. **Create workspace** if it does not exist:
    ```bash
    mkdir -p <project_root>/.mg/docs/scan <project_root>/.mg/docs/scan/templates <project_root>/.mg/docs/tmp
    ```

### Step 2: Orient (subagent)

Spawn a single orient subagent that does the heavy project analysis and writes the orientation files. This keeps ~400 lines of project data out of the orchestrator's context.

```
Agent(
  description="Orient: analyze project structure for documentation scan",
  prompt="You are the project orientation agent for auto-doc.

Your job: analyze the project, write two orientation files, and return a brief summary.

Project root: {project_root}
Config path: {project_root}/.mg/docs/.docs.config.json
GSD integration: {true|false}

## Instructions

1. **Analyze the project.** Use Glob to find files by pattern (not Bash ls). Use `get_symbols_overview` (with `depth: 1`) on source files to understand their structure (classes, functions, methods). Use `find_symbol` with `include_info: true` for signatures/docstrings when needed. Use `find_referencing_symbols` to understand component relationships. Never read an entire source file — only use `Read` for non-code files (yaml, toml, config). Identify:
   - **Product name** — deterministic extraction, in priority order:
     1. `pyproject.toml` `[project].name` (Python projects)
     2. `package.json` top-level `name` field (JS/TS projects)
     3. README first H1 heading, stripped of markdown syntax (fallback)
     Use the first source that yields a non-empty value. Emit as `project_model.product_name` (string). This is the single source of truth for the product's user-facing display name across all audience docs.
   - Languages, frameworks, package managers (package.json, pyproject.toml, Cargo.toml, go.mod, etc.)
   - Entry points: main files, route definitions, CLI scripts, event handlers, exported modules
   - Components: major directories/modules, their purpose, public API, dependencies, database tables
   - Deployment artifacts: Dockerfile, docker-compose.yml, CI/CD configs, systemd units, Procfile
   - Existing documentation: docs/, README, CLAUDE.md, CONTRIBUTING.md, API docs
   - Database schemas, API contracts, configuration files
   - Environment files: .env.example, config templates (never read .env — may contain secrets)

2. **Database detection.** If ORM models are detected (SQLAlchemy, Django, Prisma, etc.):
   a. Find model definition files (Glob for models.py, models/*.py, schema.prisma, etc.)
   b. Use get_symbols_overview to identify model classes (class names only — already collected in step 1)
   c. Find migration configurations (alembic.ini, alembic/env.py, django settings) to identify the migration tool
   d. Build a lightweight database field: {orm_framework, migration_tool, engine}
   e. Do NOT extract per-model table/schema configuration via find_symbol — that data is stripped by slim_project_model() and re-extracted deterministically by extract-database-model.py at generate time
   f. For components[].database_tables, list the model class names found in that component's directory (from step b). These are preserved in the project model for section-to-table mapping in db-table-map.json; full schema detail is still extracted deterministically by extract-database-model.py at generate time.
   g. If no ORM detected, set database to null

3. **Detect user interfaces.** Apply heuristics:
   - Front-end frameworks with routes/templates (React, Vue, Next.js, Flask+templates, Django+templates) -> type: web
   - CLI frameworks/argument parsers (argparse, click, commander, clap, cobra) -> type: cli
   - API-only frameworks (FastAPI without templates, Express without views) -> type: api
   - Orchestration platforms with dashboards (Airflow, Prefect) -> type: web
   - Mark strongest signal as primary: true, others as primary: false
   - For each, provide name (e.g. 'React Dashboard') and url_pattern (for web) or null

4. **Load GSD context** (only if GSD integration is true AND .planning/ directory exists):
   - Read .planning/STATE.md, .planning/REQUIREMENTS.md
   - Glob .planning/phases/**/*-SUMMARY.md — extract phase names, deviations, decisions
   - Glob .planning/phases/**/*-VERIFICATION.md — extract gaps
   - Read .planning/MILESTONES.md if it exists
   - Build gsd_context object: milestone, completed_phases, deviations, new_requirements_completed
   If GSD integration is false or .planning/ missing, set gsd_context to null.

5. **Read config** from the config path. Check the user_interfaces field:
   - If user_interfaces exists AND is a non-empty array: include it in project_model as-is (Priority 1 — already confirmed)
   - If absent or empty: include your detected interfaces (from step 3) but mark them as unconfirmed

6. **Write scan-orientation.md** to {project_root}/.mg/docs/scan/scan-orientation.md
   Include: project name, structure overview, languages/frameworks, entry points, components, deployment artifacts, existing documentation, environment files, config loaded, python3 version.

7. **Write scan-project.json** to {project_root}/.mg/docs/scan/scan-project.json
   Format:
   {
     'project_model': {
       'product_name': '...',  // from step 1 (pyproject.toml → package.json → README H1)
       'tech_stack': [...],
       'entry_points': [{'path': '...', 'type': '...', 'description': '...'}],
       'components': [{'name': '...', 'path': '...', 'purpose': '...', 'public_api': [...], 'dependencies': [...], 'database_tables': [...]}],
       'infrastructure': {'deployment': '...', 'ci': '...', 'config_files': [...]},
       'user_interfaces': [...],  // from step 5
       'database': {...}  // from step 2 (null if no ORM detected)
     },
     'gsd_context': {...} or null
   }
   This file participates in the merge — project_model MUST be present (Pitfall 3).

8. **Return a brief summary** (this is what the orchestrator sees):
   ORIENT COMPLETE
   product_name: <name>
   tech_stack_count: N
   component_count: N
   entry_point_count: N
   gsd_loaded: true|false
   interfaces_confirmed: true|false
   detected_interfaces: [{type, name, primary}] or []
   database_orm: <name>|none"
)
```

### Step 2b: Interface Confirmation (orchestrator)

**If config already had user_interfaces (non-empty array):** Skip — interfaces are already in scan-project.json.

**If orient subagent returned `interfaces_confirmed: false`:**

1. Parse the `detected_interfaces` from the orient return.

2. **Confirm with user** via AskUserQuestion:
   ```
   AskUserQuestion("Detected user interfaces:\n\n  Primary: {name} ({type})\n  Secondary: {name} ({type})\n\nIs this correct? Reply 'yes' to confirm, or describe corrections.")
   ```

3. **Process response:**
   - User confirms -> use detected interfaces
   - User corrects -> parse corrections into updated interface objects

4. **Persist to config and update scan-project.json** via script (keeps JSON out of orchestrator context):
   ```bash
   uv run .claude/auto-doc/scripts/persist-interfaces.py \
       --config <project_root>/.mg/docs/.docs.config.json \
       --scan-project <project_root>/.mg/docs/scan/scan-project.json \
       --interfaces '$INTERFACES_JSON'
   ```

**Fallback (non-interactive):** If AskUserQuestion is not available:
   - Remove unconfirmed interfaces from scan-project.json via Bash python3 one-liner
   - Writer agents fall back to CLI-style documentation
   - Log: "Interface detection skipped (non-interactive). Writer will default to CLI-style documentation."

### Step 3: Incremental Diff Scoping (incremental mode only)

**Only run this step if** mode is "incremental". If mode is "initial" or "update", skip entirely.

**Important ordering:** In incremental mode, read previous docs-scan.json in this step BEFORE clearing scan dir in Step 1.6. The previous scan data provides baseline entries for carry-forward.

1. **Load previous scan data.** Read `.mg/docs/docs-scan.json` and store the complete object in memory as `previous_scan`. This provides baseline entries for carry-forward.

2. **Run diff-scan.py** to produce the scoped work order:
   ```bash
   uv run .claude/auto-doc/scripts/diff-scan.py \
       --project-root <project_root> \
       --manifests-dir <project_root>/.mg/docs/generate/reference-manifests \
       --docs-dir <docs_dir_abs> \
       --since <last_generated value from docs-scan.json> \
       --gsd-dir <project_root>/.planning/phases \
       --output <project_root>/.mg/docs/scan/diff-scope.json
   ```
   If `--gsd-dir` path doesn't exist, still pass it -- diff-scan.py handles missing dirs gracefully.

3. **Read diff-scope.json** from `<project_root>/.mg/docs/scan/diff-scope.json`. Extract `affected_sections`, `new_file_candidates`, `deleted_files`, `gsd_phases_since`, and `summary`.

4. **Prepare per-audience scoped data.** For each enabled audience, filter:
   - `audience_affected`: entries from `affected_sections` where `audience` matches
   - `audience_new_files`: entries from `new_file_candidates` (all audiences get all new files for classification)
   - `audience_baseline`: from `previous_scan.source_material_index`, extract entries whose key starts with a document name belonging to this audience. These are the unchanged entries to carry forward.

   For baseline extraction: for each key in `source_material_index` (format "DOCUMENT/section-slug"), check if DOCUMENT is in the audience's document list. If so, and if that (DOCUMENT, section-slug) pair is NOT in `audience_affected`, include it as a baseline entry.

5. **Build GSD context string.** From `gsd_phases_since`, format a concise summary:
   ```
   GSD phases since last generation:
     Phase {phase}: {name}
       Deviations: {deviations or "none"}
       Key decisions: {key_decisions or "none"}
   ```
   If `gsd_phases_since` is empty, set to null/omit.

### Step 4: Staleness Check (update mode only)

**If mode is "incremental", skip this step.** In incremental mode, diff-scan.py replaces staleness check's scoping role. Staleness check continues as post-generate validation only.

**Only run this step if** mode is `"update"` AND the XML sources directory (`<docs_dir>/generate/xml-sources/`) exists with `.xml` files.

If mode is `"initial"`, skip this step entirely.

1. **Run staleness-check.py** to detect sections whose source files have changed since last generation. The check reads the XML source documents produced by `generate`, walks each section's typed refs (`config.path` and `code.module`), and compares each referenced source file's git history against the section's `last-updated` attribute:
   ```bash
   uv run .claude/auto-doc/scripts/staleness-check.py \
       --xml-dir <docs_dir>/generate/xml-sources \
       --project-root <project_root> \
       --output <project_root>/.mg/docs/scan/staleness-results.json
   ```

2. **Note:** The staleness-check script uses `--xml-dir` (directory-level), pointing at the top of the XML source tree. It recurses to find root-level shared docs (GLOSSARY.xml, OVERVIEW.xml) alongside per-audience subdirectories. **(Pitfall 1)**

4. Review script output for errors. If a script fails, log the error and continue -- partial staleness data is better than none.

### Step 4b: Parse Templates (deterministic)

Pre-parse all templates into structured JSON so scan agents use deterministic slugs and directives instead of LLM-derived parsing.

1. **Collect unique documents.** From all enabled audiences, build a set of document names (audience-specific + shared documents).

2. **For each document**, run the template parser:
   ```bash
   uv run .claude/auto-doc/scripts/parse-template.py \
       --template .claude/auto-doc/references/templates/{audience}/{DOCUMENT}.template.md \
       --document {DOCUMENT} \
       --output <project_root>/.mg/docs/scan/templates/template-{DOCUMENT}.json
   ```
   For shared documents (OVERVIEW, GLOSSARY), use `.claude/auto-doc/references/templates/{DOCUMENT}.template.md` (no audience subdirectory).

3. **Check stderr** for warnings about invalid `synthesized_from` paths. These indicate template issues but do not block the scan.

**Note:** Template JSON files go to `scan/templates/` subdirectory. `merge-scan.py` globs `scan/*.json` (not recursive), so template files are not picked up by the merge.

### Step 5: Per-Audience Scan (parallel foreground)

For each enabled audience in the config, spawn a scan subagent via the Agent tool. All agents run as parallel foreground (do NOT set `run_in_background`) so progress is visible inline.

1. **For each enabled audience** in config (e.g., `end-users`, `developers`, `agents`, `devops`):

   Determine the document list:
   - Audience-specific documents from `config.audiences.{audience}.documents`
   - Include any `shared_documents` from config (e.g., `["OVERVIEW", "GLOSSARY"]`) -- these are shared but each audience subagent should index source material for them

2. **Spawn subagents in parallel.** Launch one Agent tool call per audience in a single message (parallel foreground). Each subagent receives only parameters -- it reads its own instructions:

   ```
   Agent(
     description="Scan source material for {audience} audience",
     prompt="You are a scan subagent for the {audience} audience.

   Read and follow the instructions in: .claude/auto-doc/agents/scan-audience.md

   Project root: {project_root}
   Read orientation: {project_root}/.mg/docs/scan/scan-orientation.md
   Your audience: {audience}
   Your documents: {document_list}
   Templates directory: .claude/auto-doc/references/templates
   Write output: {project_root}/.mg/docs/scan/scan-{audience}.json
   Scripts directory: .claude/auto-doc/scripts

   Parsed template sections:
   {For each DOCUMENT in document_list, list: DOCUMENT: <project_root>/.mg/docs/scan/templates/template-{DOCUMENT}.json}"
   )
   ```

   **If mode is "incremental"**, append incremental context to the Task prompt:

   ```
   Agent(
     description="Incremental scan for {audience} audience",
     prompt="You are a scan subagent for the {audience} audience.

   Read and follow the instructions in: .claude/auto-doc/agents/scan-audience.md

   Project root: {project_root}
   Read orientation: {project_root}/.mg/docs/scan/scan-orientation.md
   Your audience: {audience}
   Your documents: {document_list}
   Templates directory: .claude/auto-doc/references/templates
   Write output: {project_root}/.mg/docs/scan/scan-{audience}.json
   Scripts directory: .claude/auto-doc/scripts

   Parsed template sections:
   {For each DOCUMENT in document_list, list: DOCUMENT: <project_root>/.mg/docs/scan/templates/template-{DOCUMENT}.json}

   Mode: incremental
   Changed files for your audience: {JSON array of changed_files from audience_affected entries}
   GSD context: {gsd_context_string or 'None'}

   Affected sections to re-analyze:
   {JSON of audience_affected entries with document, section, reason, changed_files, renames}

   Baseline entries for unchanged sections (copy VERBATIM into your output):
   {JSON of audience_baseline entries}

   New file candidates to classify into your document sections:
   {JSON array of audience_new_files entries}"
   )
   ```

4. **After all subagents complete,** check each subagent's return for `status=ok`. If any returned `status=error`, log a warning with the error message. Then verify output files exist via Bash `test -f`:
   ```
   Check: <project_root>/.mg/docs/scan/scan-{audience}.json
   ```
   If a subagent failed to produce output, log a warning and continue. The merge handles partial results gracefully.

   The scan-audience agent writes its output to a temp file first, then validates it via `write-scan-output.py` before writing to the output path. If validation fails, the agent retries once. If it fails again, the merge handles missing audience data gracefully.

### Step 6: Merge and Present

1. **Run merge-scan.py** to combine all partial results into the final scan output:
   ```bash
   uv run .claude/auto-doc/scripts/merge-scan.py \
       --scan-dir <project_root>/.mg/docs/scan \
       --output <project_root>/.mg/docs/docs-scan.json \
       --project-name "<project_name>" \
       --root-path "<project_root>" \
       --mode <initial|update>
   ```

   The merge script reads ALL `*.json` files in `scan-dir`, which includes:
   - `scan-project.json` (project_model, gsd_context)
   - `scan-{audience}.json` files (source_material_index, gap_analysis per audience)
   - `staleness-results.json` (if update mode)

2. **Read the summary counts** from docs-scan.json via script (keeps full JSON out of orchestrator context):
   ```bash
   uv run .claude/auto-doc/scripts/scan-summary.py \
       --scan-file <project_root>/.mg/docs/docs-scan.json
   ```

3. **Present a summary to the user** using the counts from the Bash output:
   - **Mode:** initial or update
   - **Project model:** tech stack count, component count, entry point count
   - **Source material:** total entries in source_material_index
   - **Staleness issues:** count (if update mode)
   - **Gaps identified:** per-audience summary of undocumented components and missing topics
   - **GSD context:** milestone, completed phases (if applicable)

   **If mode is "incremental"**, present a diff-focused summary instead of the full project model summary:

   ```
   Incremental scan complete (scoped to changes since {last_generated}).

     Files changed: {summary.files_changed}
     Files added:   {summary.files_added}
     Files deleted: {summary.files_deleted}
     Sections affected: {summary.sections_affected} across {count unique audiences in affected_sections} audiences
     New files classified: {summary.new_file_candidates}

   Run `/mg:auto-doc-generate` to update affected documentation.
   ```
   Do NOT repeat the full project model summary (tech stack, components, etc.) -- that is unchanged.

4. **Tell the user:**
   ```
   Scan complete.

   Next steps:
   - If this is the first scan for this project, run `/mg:auto-doc-prepare-templates` to produce
     project-specific refined templates before generating. This only needs to be done once.
   - Run `/mg:auto-doc-generate` to generate documentation.
   ```

## Key Formats Reference

### Source Material Index Key Format (Pitfall 2)

Keys MUST follow the format `{DOCUMENT_NAME}/{section-slug}`:
- `DOCUMENT_NAME` matches config entries exactly (e.g., `"ARCHITECTURE"`, not `"architecture"`)
- `section-slug` is the template heading lowercased with spaces replaced by hyphens

Examples:
- `ARCHITECTURE/overview`
- `USER_GUIDE/getting-started`
- `SYSTEM_MAP/tool-registry`
- `OPERATIONS/deployment-pipeline`

### Config File Location

The project config lives at: `<project_root>/.mg/docs/.docs.config.json`

Default config structure (from `.claude/auto-doc/references/.docs.config.json`):
```json
{
  "docs_dir": "docs/auto-doc",
  "audiences": {
    "end-users": { "enabled": true, "documents": ["USER_GUIDE"] },
    "developers": { "enabled": true, "documents": ["ARCHITECTURE", "DEVELOPER_GUIDE", "QUICK_REFERENCE"] },
    "agents": { "enabled": true, "documents": ["SYSTEM_MAP", "CONVENTIONS", "GOTCHAS", "TESTING"] },
    "devops": { "enabled": true, "documents": ["OPERATIONS", "TROUBLESHOOTING"] }
  },
  "shared_documents": ["OVERVIEW", "GLOSSARY"],
  "custom_documents": [],
  "gsd_integration": true
}
```

## Important Principles

- **Read-only on project source code.** Never modify, delete, move, or create files in the project's source directories. The only directory you write to is `.mg/docs/`.
- **Orchestrator stays lean.** Delegate heavy analysis to subagents. The orchestrator only handles lightweight checks, user interaction (AskUserQuestion), mode-dependent routing, and summary presentation. Large file writes (orientation, project model) happen in subagents.
- **Scan agents receive file paths only; they read files themselves.** Do not pass file contents in subagent prompts -- pass paths and let the subagent use the Read tool.
- **The `.claude/auto-doc/agents` placeholder in file references gets resolved to absolute paths by install.sh.** At runtime, `.claude/auto-doc/agents/scan-audience.md` points to the installed absolute path.
- **If a subagent fails** (no output JSON), log a warning and continue with other audiences. The merge script handles partial results. Missing data is better than a crashed pipeline.
- **If python3 is not available,** abort immediately with install instructions. All scripts require Python 3.8+.
- **Clear scan/ at the start of every run** to prevent stale data from prior scans contaminating the merge (Pitfall 6).
- **Scan-project.json must include project_model** so merge-scan.py picks it up. The merge takes project_model from the first file that has it (Pitfall 3).
- **GSD context loading is conditional** on both `.planning/` directory existence AND `gsd_integration: true` in config (Pitfall 5).
