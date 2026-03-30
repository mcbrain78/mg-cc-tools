---
name: mg:auto-doc-verify
description: Verify documentation quality -- references, consistency, Diataxis, completeness
allowed-tools: Bash, Read, Write, Glob, Grep, Agent
---

# Documentation Verifier

You are the **Verifier** -- step 3 of a 3-step documentation pipeline (scan, generate, verify). Your job is to check generated documentation for quality issues: broken references, inconsistent terminology, Diataxis type mixing, completeness gaps, example validity, and link integrity. **You never modify documentation files.** You only write to the `.mg/docs/` workspace (verification output files).

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner (step 1) and consumed by the generator (step 2). You use it for completeness checks.

## Prerequisites

Before proceeding, confirm these exist:

1. **Scan data:** `.mg/docs/docs-scan.json` must exist. If missing:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:auto-doc-scan first to analyze the project.
   ```

2. **Generated docs directory exists:** The docs directory (from config `docs_dir`, default `docs/auto-doc`) must exist. Check with a simple directory existence test (e.g., `test -d`), NOT by listing files -- the verifier agents handle their own doc file discovery. If missing:
   ```
   Error: No generated documentation found in {docs_dir}.
   Run /mg:auto-doc-generate first to create documentation.
   ```

If either prerequisite fails, abort with the corresponding message and do not proceed.

## Process

### Step 0: Parse Arguments

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-verify devops end-users`. Extract audience names as a comma-separated string (e.g., `devops,end-users`). If no audience names provided, verify all docs.

### Step 1: Load Context

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)

2. **Read scan data.** Use the Read tool to read the first 5 lines of `.mg/docs/docs-scan.json`. Find the `root_path` field value and store as `project_root`. (The full scan is processed by scripts in later steps -- do not load the entire file.)

3. **Build runtime paths:**
   - `docs_dir_abs` = `{project_root}/{docs_dir}`
   - `glossary_path` = `{docs_dir_abs}/GLOSSARY.md`
   - `output_report_path` = `{project_root}/.mg/docs/docs-verify-report.md`
   - `findings_file` = `{project_root}/.mg/docs/docs-verify-findings.json`

4. **Ensure workspace directories exist:**
   ```bash
   mkdir -p {project_root}/.mg/docs/scan-logs {project_root}/.mg/docs/tmp
   ```

5. **Clear prior verify artifacts.** Remove all verify artifacts from prior runs to start fresh:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py \
     --clean \
     --findings-file {project_root}/.mg/docs/docs-verify-findings.json
   ```
   This ensures each verify run produces findings reflecting the current documentation state. Generate reads findings but never clears them -- only verify clears (per finding lifecycle convention).

6. **Extract verify context.** Extract the fields the verifier needs from the full scan data:
   ```bash
   python3 {SCRIPTS_DIR}/extract-verify-context.py \
     --scan-file {project_root}/.mg/docs/docs-scan.json \
     --output {project_root}/.mg/docs/tmp/verify-scan-context.json \
     --templates-dir {TEMPLATES_DIR} \
     [--audience AUDIENCES --config .mg/docs/.docs.config.json --global-config {GLOBAL_CONFIG}]
   ```
   Add `--audience`, `--config`, and `--global-config` only if the user specified audience names in Step 0.

7. **Prepare doc review manifest.** Split large docs into chunks and produce a manifest for all docs:
   ```bash
   python3 {SCRIPTS_DIR}/prepare-doc-review.py \
     --docs-dir {docs_dir_abs} \
     --output-dir {project_root}/.mg/docs/tmp/review-chunks \
     --token-limit 5000 \
     [--audience AUDIENCES]
   ```
   Add `--audience` only if the user specified audience names in Step 0.

### Step 2: Run Mechanical Scripts

Run the deterministic reference integrity checker directly (not in an agent):
```bash
python3 {SCRIPTS_DIR}/verify-references.py \
    --manifests-dir {project_root}/.mg/docs/reference-manifests \
    --project-root {project_root} \
    --scan-file {project_root}/.mg/docs/docs-scan.json \
    --findings-file {project_root}/.mg/docs/docs-verify-findings.json
```

This checks file paths, symbols, and function call signatures in reference manifests. Findings are written directly to the main findings file. If the script exits non-zero (e.g., no reference-manifests directory yet), log the error and continue -- other agents can still produce useful findings.

**If XML sources exist** (check if `.mg/docs/xml-sources/` directory exists and contains `.xml` files), also run the deterministic XML ref verifier:
```bash
python3 {SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-dir {project_root}/.mg/docs/xml-sources \
    --project-root {project_root} \
    --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
    [--audience AUDIENCES]
```

Add `--audience` only if the user specified audience names in Step 0. This checks every typed ref (db schemas/tables/columns, code classes/functions, flow names, env vars, config paths, enum values) against the actual codebase deterministically.

### Step 3: Init Agent Findings Files

Each agent gets its own isolated findings file. Read the review manifest to determine the per-document editorial files:

```bash
# 4 fact-checker files
python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
  --findings-file {project_root}/.mg/docs/docs-verify-findings-code-example.json
python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
  --findings-file {project_root}/.mg/docs/docs-verify-findings-data-model.json
python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
  --findings-file {project_root}/.mg/docs/docs-verify-findings-cross-doc.json
python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
  --findings-file {project_root}/.mg/docs/docs-verify-findings-completeness.json
```

Read the manifest JSON at `{project_root}/.mg/docs/tmp/review-chunks/manifest.json`. For each entry, compute `doc_name` = basename of `source` without `.md` extension. Init one editorial findings file per document:
```bash
python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
  --findings-file {project_root}/.mg/docs/docs-verify-findings-editorial-{doc_name}.json
```

### Step 4: Spawn All Agents in Parallel

Spawn all agents in a **single message** via the Agent tool (parallel foreground -- do NOT set `run_in_background`). Each agent writes to its own isolated findings file.

**4 fact-checker agents** (one each):

```
Agent(
  description="Verify code examples in documentation",
  model="sonnet",
  prompt="You are the code example verifier agent.

Read and follow the instructions in: {AGENTS_DIR}/code-example-verifier.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- findings_file: {project_root}/.mg/docs/docs-verify-findings-code-example.json"
)

Agent(
  description="Verify data model claims in documentation",
  model="sonnet",
  prompt="You are the data model verifier agent.

Read and follow the instructions in: {AGENTS_DIR}/data-model-verifier.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- scan_context_path: {project_root}/.mg/docs/tmp/verify-scan-context.json
- findings_file: {project_root}/.mg/docs/docs-verify-findings-data-model.json"
)

Agent(
  description="Check cross-document consistency",
  model="sonnet",
  prompt="You are the cross-document checker agent.

Read and follow the instructions in: {AGENTS_DIR}/cross-doc-checker.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- glossary_path: {docs_dir_abs}/GLOSSARY.md
- findings_file: {project_root}/.mg/docs/docs-verify-findings-cross-doc.json"
)

Agent(
  description="Check documentation completeness",
  model="sonnet",
  prompt="You are the completeness checker agent.

Read and follow the instructions in: {AGENTS_DIR}/completeness-checker.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- scan_context_path: {project_root}/.mg/docs/tmp/verify-scan-context.json
- findings_file: {project_root}/.mg/docs/docs-verify-findings-completeness.json"
)
```

**N per-document editorial agents** (one per manifest entry):

For each entry in the manifest, spawn:
```
Agent(
  description="Editorial review of {doc_name}",
  model="sonnet",
  prompt="You are the editorial review agent for {doc_name}.

Read and follow the instructions in: {AGENTS_DIR}/per-doc-editorial.md

Parameters:
- project_root: {project_root}
- doc_source: {entry.source}
- doc_audience: {entry.audience}
- review_files: {JSON array of entry.review_files}
- style_guide_path: references/style-guide.md
- findings_file: {project_root}/.mg/docs/docs-verify-findings-editorial-{doc_name}.json"
)
```

All agents (4 fact-checkers + N editorial) must be spawned in a **single Agent message** so they run in parallel. Wait for all to complete before proceeding.

### Step 5: Merge Findings

Build the `--merge-from` list dynamically from the 4 fact-checker files plus N per-document editorial files:

```bash
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-code-example.json \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-data-model.json \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-cross-doc.json \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-completeness.json \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-editorial-{doc_name_1}.json \
  --merge-from {project_root}/.mg/docs/docs-verify-findings-editorial-{doc_name_2}.json \
  ... (one --merge-from per document) \
  --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
  --output {TMP_DIR}/all-findings.json
```

### Step 6: Generate Report

1. **Read** `{TMP_DIR}/all-findings.json` to get all recorded findings.

2. **Identify systemic issues.** Look for patterns across findings:
   - Same broken reference appearing in multiple documents
   - Same glossary term misused across documents
   - Repeated Diataxis mixing patterns in documents of the same type
   - Same editorial issue (e.g., filler content) appearing across multiple documents
   Group these as systemic issues rather than listing each occurrence separately.

3. **Write** `docs-verify-report.md` to `{project_root}/.mg/docs/docs-verify-report.md` with this structure:

```markdown
# Documentation Verification Report

**Verified:** {ISO date}
**Documents checked:** {count}
**Total issues:** {count}

## Systemic Issues

{Group related findings that share a root cause. Example: "The function `processData` was renamed to `handleData` -- references are broken in 4 documents." List the affected documents and sections.}

## By Document

### {DOCUMENT_NAME} ({N} issues)

#### {Issue title}
- **Section:** {section name}
- **Check:** {which check found this}
- **Description:** {what's wrong}
- **Suggestion:** {how to fix it}

...
```

List systemic issues first (patterns that span multiple documents). Then group remaining findings by document. **Skip findings already fully described in a Systemic Issues group** -- instead include a one-line back-reference: `See Systemic Issue #N above (K findings)`. Within each document group, list issues in the order they were found. Include section name, check type, description, and an actionable suggestion for every non-systemic issue. Omit documents with no issues.

### Step 7: Present Results

1. **Read the report** you just wrote: `{project_root}/.mg/docs/docs-verify-report.md`.

2. **Count total findings** from the merged findings data.

3. **Present a concise summary:**
   ```
   Verification complete -- {total} issues found.

   Full report: .mg/docs/docs-verify-report.md
   ```

4. **Conditional guidance:**
   - If any findings exist:
     ```
     Run /mg:auto-doc-update to fix verify findings. The updater will present findings as an approval tier alongside staleness and notes.
     ```

5. **Documentation gaps note:**
   ```
   Found {N} documentation gaps. Consider adding to .planning/BACKLOG.md as documentation debt.
   ```
   (Where N comes from completeness check issues in the report. If zero gaps, omit this line.)

### Step 8: Suggest Next Steps

- If this is the last pipeline step:
  ```
  Pipeline complete. Review the report and re-generate as needed.
  ```

- Direct the user to the router for pipeline overview:
  ```
  Run /mg:auto-doc for a full pipeline status overview.
  ```

## Important Principles

- **Read-only on documentation files.** Never modify, delete, or create files in the docs directory. Write only to `.mg/docs/` workspace files: `docs-verify-report.md`, `docs-verify-findings.json`.
- **Subagents read their own instructions via file path.** The Agent prompt passes a reference (`Read and follow the instructions in: agents/...`) rather than inlining the full agent definition. This keeps agent instructions out of the orchestrator's context.
- **Focused agents with isolated findings.** Each agent has a narrow scope and writes to its own findings file. The orchestrator merges all findings after agents complete. Agents never touch the shared findings file directly.
- **Reference integrity runs in the orchestrator.** The `verify-references.py` script is deterministic and fast -- it runs directly without an agent wrapper.
- **Reference integrity is manifest-based.** The script reads structured manifests from `.mg/docs/reference-manifests/` produced by the generate pipeline. No extraction from markdown is performed.
- **Prefer false negatives over false positives.** Same principle across all agents -- only flag issues with high confidence. A noisy report trains users to ignore it.
- **Verify clears all verify artifacts before each run** via `list-verify-findings.py --clean`. Generate reads findings but never clears them. This ensures each verify run reflects the current documentation state.
- **Use `{SCRIPTS_DIR}` placeholder for script paths** -- resolved by install.sh at install time.
- **Use `{GLOBAL_CONFIG}` placeholder for default config path** -- resolved by install.sh at install time.
