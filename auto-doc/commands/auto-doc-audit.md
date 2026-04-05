---
name: mg:auto-doc-audit
description: "Audit docs for ref integrity + prose consistency. Args: [audience] [waves=3]"
allowed-tools: Bash, Read, Glob, Grep, Agent
---

# Documentation Audit

You are the **Auditor** -- a lightweight post-generate quality check. Runs deterministic reference verification and LLM prose-vs-refs checks. For full editorial review, use `/mg:auto-doc-verify`.

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

Parse the user's input text for optional parameters:
- **Audience filter**: audience names (e.g., `/mg:auto-doc-audit devops`). Extract as a comma-separated string for the `--audience` flag below. If not provided, omit the flag (all audiences).
- **Wave count**: `waves=N` (e.g., `/mg:auto-doc-audit waves=5`). Controls how many prose audit waves to run. Default: 3. Wave 1 uses `verify-prose.md`; waves 2+ use `verify-prose-reaudit.md`. More waves = more findings but longer runtime (~3 min per wave).

Store the wave count as `num_waves` (integer, minimum 1, default 3).

1. **Read configuration.** Load `.mg/docs/.docs.config.json` from the project root. If not found, fall back to `{MG_INSTALL_GLOBAL_CONFIG}`. Extract:
   - `docs_dir` (default: `docs/auto-doc`)
   - `audiences` (which are enabled and their document lists)

2. **Read scan data.** Read the first 5 lines of `.mg/docs/docs-scan.json`. If this file does not exist, abort with:
   ```
   Error: No scan data found. Run /mg:auto-doc-scan first.
   ```
   Find the `root_path` field value and store as `project_root`.

3. **Check xml-sources exist.** Use Glob to verify `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/` contains `.xml` files. If not, abort with:
   ```
   Error: No XML sources found. Run /mg:auto-doc-generate first.
   ```

4. **Create audit directory:**
   ```bash
   rm -rf {MG_INSTALL_WORKSPACE_DIR}/audit
   mkdir -p {MG_INSTALL_WORKSPACE_DIR}/audit
   ```

### Step 2: Deterministic Reference Checks

Run verify-xml-refs.py once across all XML sources. It walks the entire xml-sources directory, checks every typed ref against the codebase, and appends findings to a findings file. **Do NOT run this in the background** — you need the results before proceeding.

Run the verification (this may take 1-2 minutes for large projects):
```bash
python3 {MG_INSTALL_SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
    --project-root {project_root} \
    --findings-file {MG_INSTALL_WORKSPACE_DIR}/audit/findings-refs.json \
    --database-model {MG_INSTALL_WORKSPACE_DIR}/generate/database-model.json \
    [--audience AUDIENCE]
```

Add `--audience` only if the user specified audience names (e.g., `--audience devops`).

Read `{MG_INSTALL_WORKSPACE_DIR}/audit/findings-refs.json` to get the deterministic findings list.

### Step 3: Prose-vs-Refs Consistency (multi-wave audit)

`num_waves` waves of fresh agents audit each document. Each wave spawns new agents that have never seen the sections, preventing shortcutting. All waves write to the same findings file per document (append-only).

#### 3.1. Collect and prepare

1. **Collect XML files.** Use Glob to find all `.xml` files under `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/`. If an audience filter is active, only include files under `xml-sources/{audience}/` and root-level XML files (GLOSSARY.xml, OVERVIEW.xml).

2. **For each XML file, prepare input:**
   ```bash
   python3 {MG_INSTALL_SCRIPTS_DIR}/prepare-prose-verify.py \
       --xml-file {xml_file_path} \
       --output-dir {MG_INSTALL_WORKSPACE_DIR}/audit/prose-verify-{audience}-{DOCUMENT}
   ```
   This creates per-section JSON files and a manifest.json.

#### 3.2. Wave 1 — Initial audit

Spawn verify-prose agents (one per document, parallel foreground, **model: sonnet**):
```
Agent(
  model="sonnet",
  description="Prose audit W1 {audience} {DOCUMENT}",
  prompt="You are a prose-vs-refs auditor.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/verify-prose.md

Project root: {project_root}
Prose verify dir: {MG_INSTALL_WORKSPACE_DIR}/audit/prose-verify-{audience}-{DOCUMENT}
Findings file: {MG_INSTALL_WORKSPACE_DIR}/audit/findings-prose-{audience}-{DOCUMENT}.json
Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
)
```

#### 3.3. Waves 2–N — Re-audit passes

**Repeat the following for each wave from 2 to `num_waves`:**

a. **Clean up state files** so the next wave's agents start fresh:
```bash
rm -f {MG_INSTALL_WORKSPACE_DIR}/audit/*.sectionctl
```

b. **Spawn verify-prose-reaudit agents** (one per document, parallel foreground, **model: sonnet**). They read all prior findings and look for what was missed. Use the **same findings files**:
```
Agent(
  model="sonnet",
  description="Prose audit W{N} {audience} {DOCUMENT}",
  prompt="You are a prose-vs-refs re-auditor.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/verify-prose-reaudit.md

Project root: {project_root}
Prose verify dir: {MG_INSTALL_WORKSPACE_DIR}/audit/prose-verify-{audience}-{DOCUMENT}
Findings file: {MG_INSTALL_WORKSPACE_DIR}/audit/findings-prose-{audience}-{DOCUMENT}.json
Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
)
```

Where `{N}` is the current wave number (2, 3, 4, ...).

#### 3.4. Collect findings

**Collect prose findings** from each document's findings file (`{MG_INSTALL_WORKSPACE_DIR}/audit/findings-prose-*.json`). Read each file and accumulate all findings.

### Step 4: Report

Present a summary combining deterministic and prose findings:

```
Audit Results:

| Document                  | Ref Issues | Prose Issues | Total |
|---------------------------|------------|--------------|-------|
| devops/OPERATIONS         | 2          | 1            | 3     |
| devops/TROUBLESHOOTING    | 0          | 0            | 0     |
| GLOSSARY                  | 1          | 0            | 1     |

Total: {N} issues across {M} documents
```

For documents with issues, show per-document details:
- Findings grouped by category (ref integrity, prose consistency)
- Each finding with section, check type, and description

If you notice a dominant pattern (e.g., the same root cause accounting for many findings), call it out with its impact ("accounts for ~N of M findings").

If zero issues found:
```
All clear. No reference integrity or prose consistency issues found.
Next step: Run /mg:auto-doc-verify for full editorial review.
```

If issues found, end with:
```
Run /mg:auto-doc-fix to correct these issues, then re-run /mg:auto-doc-audit to confirm.
When clean, run /mg:auto-doc-verify for full editorial review.
```

### Step 5: Persist Summary

Write the full summary text from Step 4 to `{MG_INSTALL_WORKSPACE_DIR}/audit/summary.md` so it survives beyond the conversation. Then tell the user:
```
Summary written to .mg/docs/audit/summary.md
```

## Important Principles

- **Audit is lightweight.** It checks reference integrity and prose consistency, not editorial quality or completeness. That's verify's job.
- **Deterministic checks run first.** verify-xml-refs.py is fast and catches the most common issues.
- **verify-xml-refs.py runs ONCE for the whole xml-sources directory.** Do not call it per-file.
- **prepare-prose-verify.py takes `--output-dir` (a directory), not `--output` (a file).** It creates per-section JSON files inside that directory.
- **verify-prose agents need project_root, prose_verify_dir, findings_file, and scripts_dir.** Pass all four.
- **Zero exit on clean.** If no issues found, congratulate and suggest verify as next step.
