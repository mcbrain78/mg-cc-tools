---
name: mg:create-docs-scan
description: Scan project and build source material index for documentation generation
allowed-tools: Bash, Read, Write, Glob, Grep, Task
---

# Documentation Scanner

You are the **Scanner** -- step 1 of a 3-step documentation pipeline (scan, generate, verify). Your job is to analyze a project's codebase and produce `docs-scan.json` -- the shared data contract consumed by the generate step. **You never modify project source code.** You only write to the `.mg/docs/` workspace.

## Before You Start

Read the shared schema that defines the output contract:
```
Read references/schema.md
```

This tells you the exact JSON format your output must follow. The generator (step 2) and verifier (step 3) depend on this format being correct.

## Process

### Step 1: Orient

Build an understanding of the project before delegating to scan subagents.

1. **Identify the project root directory.** Ask the user if ambiguous. Confirm by checking for common root indicators (package.json, pyproject.toml, Cargo.toml, go.mod, .git, README).

2. **Read the top-level structure** (2-3 levels deep via Bash `ls` or Glob) to understand the project layout.

3. **Identify languages, frameworks, and package managers.** Look for:
   - `package.json` / `package-lock.json` / `yarn.lock` (Node.js/JS/TS)
   - `pyproject.toml` / `requirements.txt` / `setup.py` (Python)
   - `Cargo.toml` (Rust)
   - `go.mod` (Go)
   - `pom.xml` / `build.gradle` (Java/Kotlin)
   - `Gemfile` (Ruby)

4. **Identify entry points:** main files, route definitions, CLI scripts, event handlers, exported modules, agent entry points.

5. **Scan deployment artifacts:** Dockerfile, docker-compose.yml, CI/CD configs (.github/workflows/, .gitlab-ci.yml), systemd units, Procfile, Makefile.

6. **Scan existing documentation:** docs/ directory, README files, CLAUDE.md, CONTRIBUTING.md, inline comments, API docs.

7. **Scan database schemas, API contracts, configuration files:** SQL migrations, Prisma/Drizzle schemas, OpenAPI specs, GraphQL schemas, config templates.

8. **Scan environment files:** .env.example, config templates, secrets references.

9. **Check for python3** -- Run `python3 --version`. If python3 is not available, abort with:
   ```
   Error: python3 is required for documentation scanning scripts.
   Install Python 3.8+ and try again.
   ```

10. **Load configuration.** Read `.mg/docs/.docs.config.json` from the project root. If not found, read defaults from `{GLOBAL_CONFIG}`. Extract:
    - `docs_dir` (default: `docs/auto-doc`)
    - `audiences` (which are enabled and their document lists)
    - `shared_documents`
    - `gsd_integration` flag

11. **Detect mode.** Check if `{docs_dir}` (from config, default `docs/auto-doc`) contains any `.md` files:
    - If yes: `mode = "update"`
    - If no: `mode = "initial"`
    - **Edge case (Pitfall 4):** If mode is "update" but no prior `docs-scan.json` exists at `.mg/docs/docs-scan.json`, fall back to `mode = "initial"` gracefully. Log a note that previous scan data was not found.

12. **Clear scan-logs (Pitfall 6).** Remove stale data from prior runs to prevent merge contamination:
    ```bash
    rm -f <project_root>/.mg/docs/scan-logs/*.json
    rm -f <project_root>/.mg/docs/scan-logs/*.md
    ```
    **Do NOT delete** `notes-inbox.json` or `.docs.config.json` -- those live in the parent `.mg/docs/` directory, not in `scan-logs/`.

13. **Create workspace** if it does not exist:
    ```bash
    mkdir -p <project_root>/.mg/docs/scan-logs
    ```

14. **Write orientation to TWO files:**

    **a. `scan-orientation.md`** -- Human-readable orientation log for subagents:
    ```
    Write to: <project_root>/.mg/docs/scan-logs/scan-orientation.md
    ```
    Include: project name, structure overview, languages/frameworks, entry points, components discovered, deployment artifacts, existing documentation, environment files, config loaded, mode detected, python3 version.

    **b. `scan-project.json`** -- Structured data for merge-scan.py (Pitfall 3):
    ```
    Write to: <project_root>/.mg/docs/scan-logs/scan-project.json
    ```
    This file participates in the merge. It MUST include the `project_model` object so merge-scan.py picks it up (merge takes project_model from the first file that has it). Include `gsd_context: null` as a placeholder -- Step 2 overwrites it if GSD exists.

    Format for scan-project.json:
    ```json
    {
      "project_model": {
        "tech_stack": ["python", "typescript", "..."],
        "entry_points": [
          {"path": "relative/path", "type": "cli|api|web|worker|config|test", "description": "What it does"}
        ],
        "components": [
          {
            "name": "component_name",
            "path": "relative/path",
            "purpose": "What this component does",
            "public_api": ["function1", "class1"],
            "dependencies": ["dep1"],
            "database_tables": []
          }
        ],
        "infrastructure": {
          "deployment": "How deployed",
          "ci": "CI system or none",
          "config_files": ["pyproject.toml", "..."]
        }
      },
      "gsd_context": null
    }
    ```

### Step 2: GSD Context (conditional)

**Only run this step if** BOTH conditions are met:
1. The `.planning/` directory exists in the project root
2. The config has `gsd_integration: true`

If either condition is false, skip this step. `gsd_context` remains `null` in scan-project.json. **(Pitfall 5)**

**If both conditions are met:**

1. **Read `.planning/STATE.md`** for current position, milestone info, and accumulated decisions.

2. **Read completed phase summaries.** Use Glob to find all `*-SUMMARY.md` files under `.planning/phases/`:
   ```
   Glob pattern: .planning/phases/**/*-SUMMARY.md
   ```
   For each summary, extract: phase name, key changes, deviations, decisions made.

3. **Read `.planning/REQUIREMENTS.md`** traceability table. Note which requirement IDs are checked off (completed).

4. **Read verification files.** Use Glob to find `*-VERIFICATION.md` files under `.planning/phases/`:
   ```
   Glob pattern: .planning/phases/**/*-VERIFICATION.md
   ```
   Extract known gaps and edge cases worth documenting.

5. **Read `.planning/MILESTONES.md`** if it exists for historical context.

6. **Build gsd_context object:**
   ```json
   {
     "milestone": "v1.0",
     "completed_phases": ["01-foundation", "02-templates"],
     "deviations": ["Switched from X to Y in phase 03"],
     "new_requirements_completed": ["REQ-01", "REQ-02"]
   }
   ```

7. **Update scan-project.json.** Overwrite the file, replacing `gsd_context: null` with the populated object. Keep `project_model` unchanged.

### Step 3: Staleness Check (update mode only)

**Only run this step if** mode is `"update"` AND the docs directory contains `.md` files.

If mode is `"initial"`, skip this step entirely.

1. **Run staleness-check.py** to detect sections whose source files have changed since last generation:
   ```bash
   python3 {SCRIPTS_DIR}/staleness-check.py \
       --docs-dir <docs_dir> \
       --project-root <project_root> \
       --output <project_root>/.mg/docs/scan-logs/staleness-results.json
   ```

2. **Run check-references.py** to detect broken file paths and symbol references in existing docs:
   ```bash
   python3 {SCRIPTS_DIR}/check-references.py \
       --docs-dir <docs_dir> \
       --project-root <project_root> \
       --output <project_root>/.mg/docs/scan-logs/refs-check.json
   ```

3. **Note:** These scripts use `--docs-dir` (directory-level), NOT `--doc-file` (per-file). Each script iterates the directory internally. **(Pitfall 1)**

4. Review script output for errors. If a script fails, log the error and continue -- partial staleness data is better than none.

### Step 4: Notes Classification

**Only run this step if** `.mg/docs/notes-inbox.json` exists AND has pending notes (notes where `classified` is false or the field is missing).

1. **Read `notes-inbox.json`** from `<project_root>/.mg/docs/notes-inbox.json`.

2. **For each pending note** (where `classified` is false or missing), run:
   ```bash
   python3 {SCRIPTS_DIR}/classify-note.py \
       --text "<note_text>" \
       --note-id <note_id> \
       --inbox <project_root>/.mg/docs/notes-inbox.json
   ```
   The script writes classification data back to the inbox file AND prints the classification JSON to stdout. Capture the stdout JSON for each note.

3. **Collect classification results** from stdout. Each result has: `note_id`, `audience`, `document`, `section`, `confidence`.

4. **Generate expansion outlines (SCN-06 requirement).** For each classified note, generate a proposed expansion outline -- 3 to 5 bullet points describing how the note's content should be expanded into the target document section. Consider:
   - The note's original text
   - The target audience (what level of detail do they need?)
   - The target document and section (what kind of content belongs there?)
   - The project context from orientation

   Add the outline as an `"expansion_outline"` array of strings to each classification entry:
   ```json
   {
     "note_id": "NOTE-001",
     "audience": "developers",
     "document": "ARCHITECTURE",
     "section": "auth-flow",
     "confidence": 0.85,
     "expansion_outline": [
       "Describe the JWT token flow from login to API access",
       "Document the refresh token rotation strategy",
       "Add sequence diagram showing auth middleware chain",
       "List environment variables required for auth configuration",
       "Note the rate limiting applied to auth endpoints"
     ]
   }
   ```

5. **Write combined classifications** to scan-logs for merge:
   ```bash
   Write to: <project_root>/.mg/docs/scan-logs/note-classifications.json
   ```
   Format: `{ "note_classifications": [ ... ] }` -- an object with a `note_classifications` array containing all classified entries with expansion outlines.

### Step 5: Per-Audience Scan (parallel via Task tool)

For each enabled audience in the config, spawn a scan subagent via the Task tool.

1. **Read the scan-audience agent file:**
   ```
   Read agents/scan-audience.md
   ```
   Store the full contents -- you will paste them into each subagent prompt.

2. **For each enabled audience** in config (e.g., `end-users`, `developers`, `agents`, `devops`):

   Determine the document list:
   - Audience-specific documents from `config.audiences.{audience}.documents`
   - Include any `shared_documents` from config (e.g., `["OVERVIEW", "GLOSSARY"]`) -- these are shared but each audience subagent should index source material for them

3. **Spawn subagents in parallel.** Launch one Task tool call per audience in a single message. Each subagent receives:

   ```
   Task(
     description="Scan source material for {audience} audience",
     prompt="You are a scan subagent for the {audience} audience.

   [paste full contents of agents/scan-audience.md here]

   Project root: {project_root}
   Read orientation: {project_root}/.mg/docs/scan-logs/scan-orientation.md
   Your audience: {audience}
   Your documents: {document_list}
   Templates directory: {TEMPLATES_DIR}
   Write output: {project_root}/.mg/docs/scan-logs/scan-{audience}.json"
   )
   ```

4. **After all subagents complete,** verify output files exist:
   ```
   Check: <project_root>/.mg/docs/scan-logs/scan-{audience}.json
   ```
   If a subagent failed to produce output, log a warning and continue. The merge handles partial results gracefully.

### Step 6: Merge and Present

1. **Run merge-scan.py** to combine all partial results into the final scan output:
   ```bash
   python3 {SCRIPTS_DIR}/merge-scan.py \
       --scan-dir <project_root>/.mg/docs/scan-logs \
       --output <project_root>/.mg/docs/docs-scan.json \
       --project-name "<project_name>" \
       --root-path "<project_root>" \
       --mode <initial|update>
   ```

   The merge script reads ALL `*.json` files in `scan-dir`, which includes:
   - `scan-project.json` (project_model, gsd_context)
   - `scan-{audience}.json` files (source_material_index, gap_analysis per audience)
   - `staleness-results.json` and `refs-check.json` (if update mode)
   - `note-classifications.json` (if notes were classified)

2. **Read the resulting `docs-scan.json`** and verify it has the expected top-level fields: `project`, `scan_date`, `root_path`, `mode`, `project_model`, `source_material_index`, `staleness_report`, `note_classifications`, `gap_analysis`, `gsd_context`.

3. **Present a summary to the user:**
   - **Mode:** initial or update
   - **Project model:** tech stack, component count, entry point count
   - **Source material:** total entries in source_material_index
   - **Staleness issues:** count and severity breakdown (if update mode)
   - **Notes classified:** count, with expansion outlines shown (if any)
   - **Gaps identified:** per-audience summary of undocumented components and missing topics
   - **GSD context:** milestone, completed phases (if applicable)

4. **Tell the user:**
   ```
   Scan complete. Run `/mg:create-docs-generate` to generate documentation.
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

Default config structure (from `{GLOBAL_CONFIG}`):
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
- **Scan agents receive file paths only; they read files themselves.** Do not pass file contents in subagent prompts -- pass paths and let the subagent use the Read tool.
- **The `agents/` prefix in file references gets resolved to absolute paths by install.sh.** At runtime, `agents/scan-audience.md` points to the installed absolute path.
- **If a subagent fails** (no output JSON), log a warning and continue with other audiences. The merge script handles partial results. Missing data is better than a crashed pipeline.
- **If python3 is not available,** abort immediately with install instructions. All scripts require Python 3.8+.
- **Clear scan-logs/ at the start of every run** to prevent stale data from prior scans contaminating the merge (Pitfall 6).
- **Scan-project.json must include project_model** so merge-scan.py picks it up. The merge takes project_model from the first file that has it (Pitfall 3).
- **GSD context loading is conditional** on both `.planning/` directory existence AND `gsd_integration: true` in config (Pitfall 5).
