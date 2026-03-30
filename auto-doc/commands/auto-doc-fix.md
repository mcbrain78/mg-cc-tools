---
name: mg:auto-doc-fix
description: Fix audit findings by correcting XML refs and prose
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Audit Fixer

You are the **Fixer** -- reads audit findings, groups by root cause, spawns a single agent to investigate and produce surgical edits, then reassembles markdown.

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

### Step 3: Group Findings (LLM)

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

### Step 4: Present Summary and Get Approval

Read `{TMP_DIR}/audit/grouping.json` and `{TMP_DIR}/audit/merged-findings.json`. Present a table:

```
Audit Fix Plan:

| # | Group | Root Cause | Findings |
|---|-------|------------|----------|
| 0 | etl-tracking-funcs | ETL tracking functions not named in prose | 5 |
| 1 | missing-config-path | Config path ref declared but not in prose | 2 |
...

Total: {N} findings in {M} groups

Approve: all / by group (enter indices, e.g. 0,2) / cancel
```

Handle user response:
- **"all"**: Approve all group indices.
- **Indices** (e.g., "0,2"): Approve only those groups.
- **"cancel"**: Exit with `"No fixes approved. Run again when ready."`

### Step 5: Prepare and Spawn Fixer Agent

1. Create the edit directory:
   ```bash
   mkdir -p {TMP_DIR}/audit/edits
   ```

2. Build the approved indices string (comma-separated, e.g., `"0,1,2"` or `"0,2"`).

3. Spawn a **single** agent (foreground, do NOT set `run_in_background`):

```
Agent(
  description="Fix audit findings via edit XML loop",
  prompt="You are an audit fix agent.

Read and follow the instructions in: {AGENTS_DIR}/audit-fixer.md

grouping_file: {TMP_DIR}/audit/grouping.json
findings_file: {TMP_DIR}/audit/merged-findings.json
xml_dir: {project_root}/.mg/docs/xml-sources
edit_dir: {TMP_DIR}/audit/edits
approved_indices: {comma_separated_indices}
scripts_dir: {SCRIPTS_DIR}"
)
```

**Do NOT run this agent in the background. Do NOT split into multiple agents.**

After the agent completes, collect the list of modified XML file paths from its output.

### Step 6: Reassemble Markdown

For each modified XML file, reassemble the corresponding markdown:

```bash
uv run {SCRIPTS_DIR}/assemble-markdown.py \
    --xml-file {xml_file} \
    --output {docs_dir_abs}/{audience}/{DOCUMENT}.md
```

To determine the `audience` and `DOCUMENT`:
- Parse the XML file path: `xml-sources/{audience}/{DOCUMENT}.xml`
- For root-level XML files (GLOSSARY.xml, OVERVIEW.xml), the output goes to `{docs_dir_abs}/{DOCUMENT}.md`

### Step 7: Report

Present a summary:

```
Fix Summary:

Groups processed: {N}
Modified XML files: {list}
Markdown files reassembled: {list}

Next step: Run /mg:auto-doc-audit to confirm fixes are clean.
```

If there were errors from any merge step, show them:
```
Errors (manual review needed):
  - {error description}
```

## Important Principles

- **Single agent, not parallel.** A single root cause can span multiple documents. Independent agents could fix the same issue inconsistently. One agent sees all context.
- **XML-first editing.** Edits go into XML, markdown is reassembled at the end. No lossy round-trip through sync-edits-to-xml.py.
- **Surgical edits via Edit tool.** The fixer agent uses the Edit tool on focused edit XML files — not full-body replacements. This is cheaper and safer.
- **Sequential group processing.** Each group's extract→edit→merge cycle completes before the next starts, so each extraction sees the latest master state.
- **Agent reads the codebase.** The fixer agent uses Read/Glob/Grep to verify ground truth before making corrections. It never guesses.
- **Approval before execution.** Always present the plan via AskUserQuestion before spawning the agent.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: ...`) rather than inlining the full agent definition.
