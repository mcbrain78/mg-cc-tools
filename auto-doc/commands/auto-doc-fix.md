---
name: mg:auto-doc-fix
description: Fix audit findings by correcting XML refs and prose
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Audit Fixer

You are the **Fixer** -- reads audit findings, groups by root cause, spawns a single agent to investigate and produce a fix plan, then applies ref + prose corrections to XML and reassembles markdown.

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

## Process

### Step 1: Setup

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)

2. **Read scan data.** Read the first 5 lines of `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found. Run /mg:auto-doc-scan first.
   ```
   Find the `root_path` field value and store as `project_root`.

3. **Check xml-sources exist.** Use Glob to verify `{project_root}/.mg/docs/xml-sources/` contains `.xml` files. If not, abort with:
   ```
   Error: No XML sources found. Run /mg:auto-doc-generate first.
   ```

4. **Check audit findings exist.** Verify that the audit directory `{TMP_DIR}/audit/` exists and contains at least one of:
   - `findings-refs.json`
   - Any `findings-prose-*.json` file

   If the directory doesn't exist or neither file type exists, abort with:
   ```
   Error: No audit findings found. Run /mg:auto-doc-audit first.
   ```

### Step 2: Load and Merge Findings

```bash
uv run {SCRIPTS_DIR}/load-audit-findings.py \
    --audit-dir {TMP_DIR}/audit \
    --output {TMP_DIR}/audit/merged-findings.json
```

Read the output file. If the merged array is empty, print:
```
No audit findings to fix. Documentation is clean.
```
Then exit.

### Step 3a: Group Findings (LLM)

Spawn a **Sonnet** agent to group findings by root cause:

```
Agent(
  model="sonnet",
  description="Group audit findings by root cause",
  prompt="You are a finding grouper agent.

Read and follow the instructions in: {AGENTS_DIR}/group-findings.md

findings_file: {TMP_DIR}/audit/merged-findings.json
output_file: {TMP_DIR}/audit/grouping.json"
)
```

After the agent completes, read `{TMP_DIR}/audit/grouping.json` to verify it was written.

### Step 3b: Load XML Context

```bash
uv run {SCRIPTS_DIR}/load-xml-context.py \
    --grouping-file {TMP_DIR}/audit/grouping.json \
    --findings-file {TMP_DIR}/audit/merged-findings.json \
    --xml-dir {project_root}/.mg/docs/xml-sources \
    --output {TMP_DIR}/audit/fix-context.json
```

Read the output file.

### Step 4: Present Summary and Get Approval

Use AskUserQuestion to present the grouped findings. Separate groups into **fixable** (has affected XML sections) and **informational** (0 sections — the finding is valid but no XML section was matched):

```
Audit Fix Plan:

Fixable groups:
| Group | Root Cause | Findings | Sections |
|-------|------------|----------|----------|
| 1     | etl_runs schema mismatch | 5 | 3 |
| 2     | missing config path | 2 | 2 |
...

Informational only (no matching XML sections):
| Group | Root Cause | Findings |
|-------|------------|----------|
| 3     | stale flow name reference | 2 |
...

Total: {N} findings in {M} groups ({F} fixable, {I} info-only)

Approve fixable groups: all / by group (enter group numbers) / cancel
```

Handle user response:
- **"all"**: Proceed with all fixable groups.
- **Group numbers** (e.g., "1,2"): Filter fix-context.json to only those groups before proceeding.
- **"cancel"**: Exit with `"No fixes approved. Run again when ready."`

If the user selects specific groups, rewrite `fix-context.json` with only the approved groups. Informational groups are always excluded from the fixer agent (they have no XML context to fix).

### Step 5: Spawn Audit Fixer Agent

Spawn a **single** agent (foreground, do NOT set `run_in_background`):

```
Agent(
  model="sonnet",
  description="Fix audit findings",
  prompt="You are an audit fix agent.

Read and follow the instructions in: {AGENTS_DIR}/audit-fixer.md

fix_context_path: {TMP_DIR}/audit/fix-context.json
output_path: {TMP_DIR}/audit/fix-plan.json
project_root: {project_root}
scripts_dir: {SCRIPTS_DIR}"
)
```

**Do NOT run this agent in the background. Do NOT split into multiple agents.**

After the agent completes, read `{TMP_DIR}/audit/fix-plan.json` to verify it was written.

### Step 6: Apply Fixes

```bash
uv run {SCRIPTS_DIR}/apply-audit-fixes.py \
    --fix-plan {TMP_DIR}/audit/fix-plan.json
```

Read the JSON output from stdout. This gives you the summary of what was modified.

### Step 7: Reassemble Markdown

For each XML file listed in the apply summary's `files_modified` array, reassemble the corresponding markdown:

```bash
uv run {SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {xml_file} \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
```

To determine the `audience` and `DOCUMENT`:
- Parse the XML file path: `xml-sources/{audience}/{DOCUMENT}.xml`
- For root-level XML files (GLOSSARY.xml, OVERVIEW.xml), the output goes to `{docs_dir_abs}/{DOCUMENT}.md`

### Step 8: Report

Present a summary:

```
Fix Summary:

| Group | Description | Sections Fixed | Refs | Bodies |
|-------|-------------|----------------|------|--------|
| 1     | Fixed schema... | 3 | 3 | 2 |
...

Total: {N} sections fixed, {R} ref corrections, {B} body corrections
Files modified: {list}

Next step: Run /mg:auto-doc-audit to confirm fixes are clean.
```

If there were errors, show them:
```
Errors (manual review needed):
  - {error description}
```

## Important Principles

- **Single agent, not parallel.** A single root cause can span multiple documents. Independent agents could fix the same issue inconsistently. One agent sees all context.
- **XML-first editing.** Edits go into XML, markdown is reassembled at the end. No lossy round-trip through sync-edits-to-xml.py.
- **Agent reads the codebase.** The fixer agent uses Read/Glob/Grep to verify ground truth before making corrections. It never guesses.
- **Complete replacements, not diffs.** The fix plan contains complete replacement values, not patches. This matches the update_section_refs/update_section_body API.
- **Approval before execution.** Always present the plan via AskUserQuestion before spawning the agent.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: ...`) rather than inlining the full agent definition.
