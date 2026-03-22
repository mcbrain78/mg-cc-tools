---
name: mg:auto-doc-verify
description: Verify documentation quality -- references, consistency, Diataxis, completeness
allowed-tools: Bash, Read, Write, Glob, Grep, Task
---

# Documentation Verifier

You are the **Verifier** -- step 3 of a 3-step documentation pipeline (scan, generate, verify). Your job is to check generated documentation for quality issues: broken references, inconsistent terminology, Diataxis type mixing, completeness gaps, example validity, and link integrity. **You never modify documentation files.** You only write to the `.mg/docs/` workspace (verification output files).

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

This tells you the JSON format of `docs-scan.json` -- the input produced by the scanner (step 1) and consumed by the generator (step 2). You use it for completeness checks.

Read the verifier agent definition. You will paste its full contents into the Task prompt when spawning the agent:
```
Read agents/verifier.md
```

Store the entire contents of `agents/verifier.md` in memory -- you will need it for Step 3.

## Prerequisites

Before proceeding, confirm these exist:

1. **Scan data:** `.mg/docs/docs-scan.json` must exist. If missing:
   ```
   Error: No scan data found at .mg/docs/docs-scan.json.
   Run /mg:auto-doc-scan first to analyze the project.
   ```

2. **Generated docs directory exists:** The docs directory (from config `docs_dir`, default `docs/auto-doc`) must exist. Check with a simple directory existence test (e.g., `test -d`), NOT by listing files -- the verifier agent handles its own doc file discovery. If missing:
   ```
   Error: No generated documentation found in {docs_dir}.
   Run /mg:auto-doc-generate first to create documentation.
   ```

If either prerequisite fails, abort with the corresponding message and do not proceed.

## Process

### Step 1: Load Context

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)

2. **Read scan data.** Load `.mg/docs/docs-scan.json`. Extract:
   - `root_path` as `project_root`
   - `source_material_index` (needed for completeness checks)

3. **Build runtime paths:**
   - `docs_dir_abs` = `{project_root}/{docs_dir}`
   - `scan_data_path` = `{project_root}/.mg/docs/docs-scan.json`
   - `glossary_path` = `{docs_dir_abs}/GLOSSARY.md`
   - `output_report_path` = `{project_root}/.mg/docs/docs-verify-report.md`
   - `findings_file` = `{project_root}/.mg/docs/docs-verify-findings.json`

4. **Ensure scan-logs directory exists:**
   ```bash
   mkdir -p {project_root}/.mg/docs/scan-logs
   ```

5. **Clear prior verify artifacts.** Remove all verify artifacts from prior runs to start fresh:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py \
     --clean \
     --findings-file {project_root}/.mg/docs/docs-verify-findings.json
   ```
   This ensures each verify run produces findings reflecting the current documentation state. Generate reads findings but never clears them -- only verify clears (per finding lifecycle convention).

### Step 2: Spawn Verifier Agent

Spawn a **single** verifier agent instance via the Task tool. Unlike codebase-health which parallelizes verification by category, documentation verification runs 6 sequential checks in one agent.

Build the Task prompt by pasting the full contents of `agents/verifier.md` and providing these parameters:

```
Task(
  description="Verify documentation quality (6 checks)",
  prompt="You are the documentation verifier agent.

[paste full contents of agents/verifier.md here]

Parameters:
- project_root: {project_root}
- docs_dir: {docs_dir_abs}
- scan_data_path: {project_root}/.mg/docs/docs-scan.json
- glossary_path: {docs_dir_abs}/GLOSSARY.md
- style_guide_path: references/style-guide.md
- output_report_path: {project_root}/.mg/docs/docs-verify-report.md
- findings_file: {project_root}/.mg/docs/docs-verify-findings.json"
)
```

Wait for the agent to complete. The agent writes `docs-verify-report.md` to the `output_report_path`.

### Step 3: Present Results

1. **Read the generated report:** Load `{project_root}/.mg/docs/docs-verify-report.md`.

2. **Parse the severity summary table.** Extract counts for each severity level.

3. **Present a concise summary:**
   ```
   Verification complete -- {total} issues found.
     {N} critical, {N} high, {N} medium, {N} low, {N} info

   Full report: .mg/docs/docs-verify-report.md
   ```

4. **Conditional guidance:**
   - If critical or high issues exist:
     ```
     Run /mg:auto-doc-generate to address verify findings. The generator will present findings as an approval tier alongside staleness and notes.
     ```
   - If no critical or high issues:
     ```
     Documentation quality looks good.
     ```

5. **Documentation gaps note:**
   ```
   Found {N} documentation gaps. Consider adding to .planning/BACKLOG.md as documentation debt.
   ```
   (Where N comes from completeness check issues in the report. If zero gaps, omit this line.)

### Step 4: Suggest Next Steps

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
- **Agent instructions ARE pasted into the Task prompt.** The full contents of `agents/verifier.md` are included in the Task prompt so the spawned agent has its complete instruction set. The agent then reads data files itself via the paths provided.
- **The agent uses LSP documentSymbol for symbol verification against structured manifests.** There is no regex extraction step or Grep fallback.
- **Reference integrity is manifest-based.** The verifier reads structured manifests from `.mg/docs/reference-manifests/` produced by the generate pipeline. No extraction from markdown is performed.
- **5-tier severity model:** critical, high, medium, low, info. This matches the verifier agent's definition and the report output format.
- **Prefer false negatives over false positives.** Same principle as the verifier agent -- only flag issues with high confidence. A noisy report trains users to ignore it.
- **Verify clears all verify artifacts before each run** via `list-verify-findings.py --clean`. Generate reads findings but never clears them. This ensures each verify run reflects the current documentation state.
- **Use `{SCRIPTS_DIR}` placeholder for script paths** -- resolved by install.sh at install time.
- **Use `{GLOBAL_CONFIG}` placeholder for default config path** -- resolved by install.sh at install time.
