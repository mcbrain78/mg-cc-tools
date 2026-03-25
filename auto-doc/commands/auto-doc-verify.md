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

6. **Extract verify context.** Extract the 3 fields the verifier needs from the full scan data:
   ```bash
   python3 {SCRIPTS_DIR}/extract-verify-context.py \
     --scan-file {project_root}/.mg/docs/docs-scan.json \
     --output {project_root}/.mg/docs/tmp/verify-scan-context.json
   ```

7. **Prepare doc review manifest.** Split large docs into chunks and produce a manifest for all docs:
   ```bash
   python3 {SCRIPTS_DIR}/prepare-doc-review.py \
     --docs-dir {docs_dir_abs} \
     --output-dir {project_root}/.mg/docs/tmp/review-chunks \
     --token-limit 5000
   ```

8. **Init agent-specific findings files.** Each agent gets its own isolated findings file:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
     --findings-file {project_root}/.mg/docs/docs-verify-findings-mechanical.json
   python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
     --findings-file {project_root}/.mg/docs/docs-verify-findings-editorial.json
   ```

### Step 2: Spawn Verification Agents

Spawn **two** verification agents in parallel via the Agent tool. Each agent writes to its own isolated findings file. The orchestrator merges them after both complete.

```
Agent(
  description="Verify documentation quality (6 mechanical checks)",
  prompt="You are the documentation verifier agent.

Read and follow the instructions in: {AGENTS_DIR}/verifier.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- scan_context_path: {project_root}/.mg/docs/tmp/verify-scan-context.json
- glossary_path: {docs_dir_abs}/GLOSSARY.md
- style_guide_path: references/style-guide.md
- findings_file: {project_root}/.mg/docs/docs-verify-findings-mechanical.json"
)

Agent(
  description="Editorial review of documentation quality",
  prompt="You are the editorial review agent.

Read and follow the instructions in: {AGENTS_DIR}/editorial-reviewer.md

Parameters:
- project_root: {project_root}
- review_manifest: {project_root}/.mg/docs/tmp/review-chunks/manifest.json
- style_guide_path: references/style-guide.md
- findings_file: {project_root}/.mg/docs/docs-verify-findings-editorial.json"
)
```

Wait for **both** agents to complete before proceeding.

### Step 3: Generate Report

After both agents complete, merge their isolated findings and generate the verification report:

1. **Merge agent findings:**
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py \
     --merge-from {project_root}/.mg/docs/docs-verify-findings-mechanical.json \
     --merge-from {project_root}/.mg/docs/docs-verify-findings-editorial.json \
     --findings-file {project_root}/.mg/docs/docs-verify-findings.json \
     --output {TMP_DIR}/all-findings.json
   ```

2. **Read** `{TMP_DIR}/all-findings.json` to get all recorded findings (both mechanical and editorial).

3. **Identify systemic issues.** Look for patterns across findings:
   - Same broken reference appearing in multiple documents
   - Same glossary term misused across documents
   - Repeated Diataxis mixing patterns in documents of the same type
   - Same editorial issue (e.g., filler content) appearing across multiple documents
   Group these as systemic issues rather than listing each occurrence separately.

4. **Write** `docs-verify-report.md` to `{project_root}/.mg/docs/docs-verify-report.md` with this structure:

```markdown
# Documentation Verification Report

**Verified:** {ISO date}
**Documents checked:** {count}
**Total issues:** {count}

## Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| High     | N |
| Medium   | N |
| Low      | N |
| Info     | N |

## Systemic Issues

{Group related findings that share a root cause. Example: "The function `processData` was renamed to `handleData` -- references are broken in 4 documents." List the affected documents and sections.}

## Critical Issues

### {Issue title}
- **Document:** {file path}
- **Section:** {section name}
- **Check:** {which check found this}
- **Description:** {what's wrong}
- **Suggestion:** {how to fix it}

## High Issues
...

## Medium Issues
...

## Low Issues
...
```

Group issues by severity (critical first). Within each severity group, list issues in the order they were found. **Skip findings already fully described in a Systemic Issues group** — instead include a one-line back-reference: `See Systemic Issue #N above (K findings)`. Include document path, section name, check type, description, and an actionable suggestion for every non-systemic issue. Omit empty severity sections.

**Completeness finding adjustments:** When reporting completeness findings for missing sections, check whether the section heading in the template is marked `<!-- OPTIONAL -->`. If so, downgrade the finding from high to **info** severity and note it was an optional section the writer chose to skip. For section name mismatches (e.g., `documented_sections` says `adding-a-new-scoring-model` but the actual heading is `adding-a-new-finance-metric`), note the mismatch but downgrade to **medium** — the content exists under a different name.

### Step 4: Present Results

1. **Read the report** you just wrote: `{project_root}/.mg/docs/docs-verify-report.md`.

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

### Step 5: Suggest Next Steps

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
- **Two agents run in parallel with isolated findings.** The mechanical verifier (6 checks) and editorial reviewer (22 criteria) each write to their own findings file. The orchestrator merges them after both complete — agents never touch the shared findings file directly.
- **Reference integrity uses `ast.parse()` via a deterministic script (`verify-references.py`).** The agent calls the script as its first step.
- **Reference integrity is manifest-based.** The verifier reads structured manifests from `.mg/docs/reference-manifests/` produced by the generate pipeline. No extraction from markdown is performed.
- **5-tier severity model:** critical, high, medium, low, info. This matches the verifier agent's definition and the report output format.
- **Prefer false negatives over false positives.** Same principle as the verifier agent -- only flag issues with high confidence. A noisy report trains users to ignore it.
- **Verify clears all verify artifacts before each run** via `list-verify-findings.py --clean`. Generate reads findings but never clears them. This ensures each verify run reflects the current documentation state.
- **Use `{SCRIPTS_DIR}` placeholder for script paths** -- resolved by install.sh at install time.
- **Use `{GLOBAL_CONFIG}` placeholder for default config path** -- resolved by install.sh at install time.
