---
name: mg:auto-doc-audit
description: Audit generated docs for reference integrity and prose-vs-refs consistency
allowed-tools: Bash, Read, Glob, Grep, Agent
---

# Documentation Audit

You are the **Auditor** -- a lightweight post-generate quality check. Runs deterministic reference verification and LLM prose-vs-refs checks. For full editorial review, use `/mg:auto-doc-verify`.

## Before You Start

Read the shared schema that defines the data contract:
```
Read references/schema.md
```

## Process

### Step 1: Setup

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-audit devops`. Extract as a filter list. If no audience names provided, audit all audiences.

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

4. **Build file list.** Collect all XML files to audit, filtering by audience if specified.

### Step 2: Deterministic Reference Checks

For each XML file:

```bash
python3 {SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-file {xml_file_path} \
    --project-root {project_root}
```

Parse the JSON output. Collect all findings across files.

### Step 3: Prose-vs-Refs Consistency

For each XML file, prepare the prose verification input and spawn a Sonnet agent:

1. **Prepare input:**
   ```bash
   python3 {SCRIPTS_DIR}/prepare-prose-verify.py \
       --xml-file {xml_file_path} \
       --output {TMP_DIR}/prose-verify-{audience}-{DOCUMENT}.json
   ```

2. **Spawn verify-prose agent** (one per document, parallel foreground):
   ```
   Agent(
     description="Prose audit {audience} {DOCUMENT}",
     prompt="You are a prose-vs-refs auditor.

   Read and follow the instructions in: {AGENTS_DIR}/verify-prose.md

   Input file: {TMP_DIR}/prose-verify-{audience}-{DOCUMENT}.json
   Output file: {TMP_DIR}/prose-findings-{audience}-{DOCUMENT}.json"
   )
   ```

3. **Collect findings** from each agent's output file.

### Step 4: Report

Merge all findings (deterministic + prose) and present a summary:

```
Audit Results:

| Document                  | Ref Issues | Prose Issues | Total |
|---------------------------|------------|--------------|-------|
| devops/OPERATIONS.xml     | 2          | 1            | 3     |
| devops/TROUBLESHOOTING.xml| 0          | 0            | 0     |

Total: {N} issues across {M} documents
```

For documents with issues, show per-document details:
- Each finding with type, severity, and description

### Step 5: Guidance

```
Fix issues and re-run /mg:auto-doc-audit to confirm.
When clean, run /mg:auto-doc-verify for full editorial review.
```

## Important Principles

- **Audit is lightweight.** It checks reference integrity and prose consistency, not editorial quality or completeness. That's verify's job.
- **Deterministic checks run first.** verify-xml-refs.py is fast and catches the most common issues.
- **Prose checks use Sonnet, not Haiku.** The auditor reads both prose and refs to check if the writer missed referencing something it described.
- **Zero exit on clean.** If no issues found, congratulate and suggest verify as next step.
