---
name: mg:auto-doc-fix
description: Fix audit findings by correcting XML refs and prose
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Documentation Audit Fixer

You are the **Fixer** -- reads audit findings, groups by root cause, spawns a single agent to investigate and produce surgical edits, then reassembles markdown.

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

### Step 1: Setup

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{MG_INSTALL_GLOBAL_CONFIG}`. Extract:
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

4. **Check audit findings exist.** Verify that the audit directory `{MG_INSTALL_TMP_DIR}/audit/` exists and contains at least one of:
   - `findings-refs.json`
   - Any `findings-prose-*.json` file

   If the directory doesn't exist or neither file type exists, abort with:
   ```
   Error: No audit findings found. Run /mg:auto-doc-audit first.
   ```

### Step 2: Load and Merge Findings

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/load-audit-findings.py \
    --audit-dir {MG_INSTALL_TMP_DIR}/audit \
    --output {MG_INSTALL_TMP_DIR}/audit/merged-findings.json
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

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/group-findings.md

findings_file: {MG_INSTALL_TMP_DIR}/audit/merged-findings.json
output_file: {MG_INSTALL_TMP_DIR}/audit/grouping.json"
)
```

After the agent completes, read `{MG_INSTALL_TMP_DIR}/audit/grouping.json` to verify it was written.

### Step 4: Present Summary and Get Approval

Read `{MG_INSTALL_TMP_DIR}/audit/grouping.json` and `{MG_INSTALL_TMP_DIR}/audit/merged-findings.json`. Present a table:

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

### Step 5: Initialize Fix Queue and Process Groups

1. Create the fix directory (separate from audit so diffs survive audit re-runs):
   ```bash
   mkdir -p {MG_INSTALL_TMP_DIR}/fix
   ```

2. Build the approved indices string (comma-separated, e.g., `"0,1,2"` or `"0,2"`).

3. Initialize the fix queue:
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/fix-queue.py init \
       --grouping-file {MG_INSTALL_TMP_DIR}/audit/grouping.json \
       --findings-file {MG_INSTALL_TMP_DIR}/audit/merged-findings.json \
       --xml-dir {project_root}/.mg/docs/xml-sources \
       --edit-dir {MG_INSTALL_TMP_DIR}/fix \
       --approved {comma_separated_indices} \
       --state-file {MG_INSTALL_TMP_DIR}/fix/fix-state.json
   ```

4. **Loop** — call `next` repeatedly until done:

   a. Get the next group:
      ```bash
      uv run {MG_INSTALL_SCRIPTS_DIR}/fix-queue.py next \
          --state-file {MG_INSTALL_TMP_DIR}/fix/fix-state.json
      ```

   b. Parse the JSON output from stdout.

   c. If `status` is `"done"`: **break** the loop. Save `files_modified` from the output for Step 6.

   d. If `status` is `"next"`: spawn a **single foreground** agent to edit the group's file:

      ```
      Agent(
        description="Fix group: {group_id}",
        prompt="You are an audit fix agent.

      Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/audit-fixer.md

      edit_file: {edit_file from next output}"
      )
      ```

      **Do NOT run this agent in the background.** Wait for it to complete before calling `next` again.

   e. After the agent completes, go back to step (a). The next `next` call will merge the edits before extracting the next group.

**Key properties:**
- One subagent per group — each gets a fresh context with just one edit file.
- The script enforces sequentiality: each `next` merges the previous group before extracting the next.
- Empty groups (0 matching XML sections) are auto-skipped inside `next`.
- The final group's merge happens on the last `next` call (which returns `"done"`).

### Step 6: Reassemble Markdown

For each modified XML file, reassemble the corresponding markdown:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/assemble-markdown.py \
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

- **Script-controlled sequentiality.** `fix-queue.py` enforces the extract→edit→merge order. The orchestrator never sees more than one group at a time. Each extraction reads the latest master state (after the previous merge).
- **One agent per group.** Each subagent gets a fresh context with a single edit file. This prevents context buildup and ensures consistent behavior across groups.
- **XML-first editing.** Edits go into XML, markdown is reassembled at the end. No lossy round-trip through sync-edits-to-xml.py.
- **Surgical edits via Edit tool.** The fixer agent uses the Edit tool on focused edit XML files — not full-body replacements. This is cheaper and safer.
- **Agent reads the codebase.** The fixer agent uses Read/Glob/Grep to verify ground truth before making corrections. It never guesses.
- **Approval before execution.** Always present the plan via AskUserQuestion before spawning the agent.
- **Subagents read their own instructions via file path.** Agent prompts pass a reference (`Read and follow the instructions in: ...`) rather than inlining the full agent definition.
