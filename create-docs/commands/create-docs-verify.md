---
name: mg:create-docs-verify
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
   Run /mg:create-docs-scan first to analyze the project.
   ```

2. **Generated docs directory exists:** The docs directory (from config `docs_dir`, default `docs/auto-doc`) must exist. Check with a simple directory existence test (e.g., `test -d`), NOT by listing files -- the verifier agent handles its own doc file discovery. If missing:
   ```
   Error: No generated documentation found in {docs_dir}.
   Run /mg:create-docs-generate first to create documentation.
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
   - `verify_refs_broken_path` = `{project_root}/.mg/docs/scan-logs/verify-refs-broken.json`
   - `verify_refs_symbols_path` = `{project_root}/.mg/docs/scan-logs/verify-refs-symbols.json`
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

### Step 2: Reference Extraction (deterministic)

Run `check-references.py` ONCE for the entire docs directory to extract all file path and symbol references:

```bash
python3 {SCRIPTS_DIR}/check-references.py \
  --docs-dir <docs_dir_abs> \
  --project-root <project_root> \
  --skip-symbol-check \
  --output-broken <project_root>/.mg/docs/scan-logs/verify-refs-broken.json \
  --output-symbols <project_root>/.mg/docs/scan-logs/verify-refs-symbols.json
```

**IMPORTANT:** Use `--docs-dir` (directory-level), NOT `--doc-file`. The script iterates all `.md` files in the directory internally.

**IMPORTANT:** Use `--skip-symbol-check` so the script extracts symbols without walking the project tree for each one. Symbol verification is delegated to the verifier agent via LSP (much faster and more accurate).

The script produces two split output files:
- `verify-refs-broken.json` -- broken file path entries only, grouped by reference
- `verify-refs-symbols.json` -- extracted symbols, grouped by reference

Both use a grouped format with `reference`, `type`, `status`, and `locations` fields. Duplicate references from multiple docs are collapsed into a single entry with multiple locations.

If the script fails, log the error and continue. The agent can still run the remaining 5 checks without reference extraction data.

### Step 3: Spawn Verifier Agent

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
- verify_refs_broken_path: {project_root}/.mg/docs/scan-logs/verify-refs-broken.json
- verify_refs_symbols_path: {project_root}/.mg/docs/scan-logs/verify-refs-symbols.json
- findings_file: {project_root}/.mg/docs/docs-verify-findings.json"
)
```

Wait for the agent to complete. The agent writes `docs-verify-report.md` to the `output_report_path`.

### Step 4: Present Results

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
     Run /mg:create-docs-generate to address verify findings. The generator will present findings as an approval tier alongside staleness and notes.
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

### Step 5: Suggest Next Steps

- If this is the last pipeline step:
  ```
  Pipeline complete. Review the report and re-generate as needed.
  ```

- Direct the user to the router for pipeline overview:
  ```
  Run /mg:create-docs for a full pipeline status overview.
  ```

## Important Principles

- **Read-only on documentation files.** Never modify, delete, or create files in the docs directory. Write only to `.mg/docs/` workspace files: `verify-refs-broken.json` and `verify-refs-symbols.json` (scan-logs), `docs-verify-report.md`.
- **Use `--docs-dir` not `--doc-file` for check-references.py.** The script iterates the directory internally. Calling it per-file would be redundant and slower.
- **Agent instructions ARE pasted into the Task prompt.** The full contents of `agents/verifier.md` are included in the Task prompt so the spawned agent has its complete instruction set. The agent then reads data files itself via the paths provided.
- **The agent uses LSP for symbol verification.** DO NOT use check-references.py's symbol status results. The script's regex-based `_symbol_exists_in_project()` misses valid symbols (re-exports, decorators, cross-module imports). The agent uses LSP go-to-definition which resolves semantically.
- **5-tier severity model:** critical, high, medium, low, info. This matches the verifier agent's definition and the report output format.
- **Prefer false negatives over false positives.** Same principle as the verifier agent -- only flag issues with high confidence. A noisy report trains users to ignore it.
- **Do not modify check-references.py.** It is used as-is for reference extraction.
- **Verify clears all verify artifacts before each run** via `list-verify-findings.py --clean`. Generate reads findings but never clears them. This ensures each verify run reflects the current documentation state.
- **Use `{SCRIPTS_DIR}` placeholder for script paths** -- resolved by install.sh at install time.
- **Use `{GLOBAL_CONFIG}` placeholder for default config path** -- resolved by install.sh at install time.
