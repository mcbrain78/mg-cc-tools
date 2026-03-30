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

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-audit devops`. Extract as a comma-separated string for the `--audience` flag below. If no audience names provided, omit the flag (all audiences).

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

4. **Create tmp directory:**
   ```bash
   mkdir -p {project_root}/.mg/docs/tmp
   ```

### Step 2: Deterministic Reference Checks

Run verify-xml-refs.py once across all XML sources. It walks the entire xml-sources directory, checks every typed ref against the codebase, and appends findings to a findings file.

```bash
python3 {SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-dir {project_root}/.mg/docs/xml-sources \
    --project-root {project_root} \
    --findings-file {TMP_DIR}/audit-findings.json \
    [--audience AUDIENCE]
```

Add `--audience` only if the user specified audience names (e.g., `--audience devops`).

Read `{TMP_DIR}/audit-findings.json` to get the deterministic findings list.

### Step 3: Prose-vs-Refs Consistency

For each XML file in xml-sources (filtered by audience if specified), prepare prose verification input and spawn a verify-prose agent.

1. **Collect XML files.** Use Glob to find all `.xml` files under `{project_root}/.mg/docs/xml-sources/`. If an audience filter is active, only include files under `xml-sources/{audience}/` and root-level XML files (GLOSSARY.xml, OVERVIEW.xml).

2. **For each XML file, prepare input:**
   ```bash
   python3 {SCRIPTS_DIR}/prepare-prose-verify.py \
       --xml-file {xml_file_path} \
       --output-dir {TMP_DIR}/prose-verify-{audience}-{DOCUMENT}
   ```
   This creates per-section JSON files and a manifest.json.

3. **Spawn verify-prose agents** (one per document, parallel foreground):
   ```
   Agent(
     description="Prose audit {audience} {DOCUMENT}",
     prompt="You are a prose-vs-refs auditor.

   Read and follow the instructions in: {AGENTS_DIR}/verify-prose.md

   Project root: {project_root}
   Prose verify dir: {TMP_DIR}/prose-verify-{audience}-{DOCUMENT}
   Findings file: {TMP_DIR}/prose-findings-{audience}-{DOCUMENT}.json
   Scripts dir: {SCRIPTS_DIR}"
   )
   ```

4. **Collect prose findings** from each agent's output file (`{TMP_DIR}/prose-findings-*.json`). Read each file and accumulate all findings.

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
- Each finding with check type and description

If zero issues found:
```
All clear. No reference integrity or prose consistency issues found.
Next step: Run /mg:auto-doc-verify for full editorial review.
```

### Step 5: Guidance (if issues found)

```
Fix issues and re-run /mg:auto-doc-audit to confirm.
When clean, run /mg:auto-doc-verify for full editorial review.
```

## Important Principles

- **Audit is lightweight.** It checks reference integrity and prose consistency, not editorial quality or completeness. That's verify's job.
- **Deterministic checks run first.** verify-xml-refs.py is fast and catches the most common issues.
- **verify-xml-refs.py runs ONCE for the whole xml-sources directory.** Do not call it per-file.
- **prepare-prose-verify.py takes `--output-dir` (a directory), not `--output` (a file).** It creates per-section JSON files inside that directory.
- **verify-prose agents need project_root, prose_verify_dir, findings_file, and scripts_dir.** Pass all four.
- **Zero exit on clean.** If no issues found, congratulate and suggest verify as next step.
