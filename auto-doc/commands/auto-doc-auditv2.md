---
name: mg:auto-doc-auditv2
description: "Audit docs v2 (extract → clear → resolve). Args: [audience] [waves=2]"
allowed-tools: Bash, Read, Glob, Grep, Agent
---

# Documentation Audit v2

You are the **Auditor v2** — a redesigned post-generate quality check that separates entity extraction from resolution. Runs deterministic reference verification, LLM entity extraction, deterministic clearing, and LLM resolution of uncleared entities only. For full editorial review, use `/mg:auto-doc-verify`.

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
- **Audience filter**: audience names (e.g., `/mg:auto-doc-auditv2 devops`). Extract as a comma-separated string for the `--audience` flag below. If not provided, omit the flag (all audiences).
- **Wave count**: `waves=N` (e.g., `/mg:auto-doc-auditv2 waves=3`). Controls how many resolution waves to run after extraction. Default: 2. More waves = more findings but longer runtime. Total agents per document = 1 (extraction) + N (resolution).

Store the wave count as `num_waves` (integer, minimum 1, default 2).

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

4. **Create auditv2 directory** (preserve not-entities and protected-entities across runs):
   ```bash
   for f in not-entities.json protected-entities.json; do
     if [ -f {MG_INSTALL_WORKSPACE_DIR}/auditv2/$f ]; then
       cp {MG_INSTALL_WORKSPACE_DIR}/auditv2/$f /tmp/_mg_${f%.json}_backup.json
     fi
   done
   rm -rf {MG_INSTALL_WORKSPACE_DIR}/auditv2
   mkdir -p {MG_INSTALL_WORKSPACE_DIR}/auditv2
   for f in not-entities.json protected-entities.json; do
     backup="/tmp/_mg_${f%.json}_backup.json"
     if [ -f "$backup" ]; then
       mv "$backup" {MG_INSTALL_WORKSPACE_DIR}/auditv2/$f
     else
       echo '[]' > {MG_INSTALL_WORKSPACE_DIR}/auditv2/$f
     fi
   done
   echo '[]' > {MG_INSTALL_WORKSPACE_DIR}/auditv2/dismissed-this-run.json
   ```

### Step 2: Deterministic Reference Checks

Run verify-xml-refs.py once across all XML sources. **Do NOT run this in the background** — you need the results before proceeding.

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-dir {MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources \
    --project-root {project_root} \
    --findings-file {MG_INSTALL_WORKSPACE_DIR}/auditv2/findings-refs.json \
    --database-model {MG_INSTALL_WORKSPACE_DIR}/generate/database-model.json \
    [--audience AUDIENCE]
```

Add `--audience` only if the user specified audience names.

Read `{MG_INSTALL_WORKSPACE_DIR}/auditv2/findings-refs.json` to get the deterministic findings list.

### Step 3: Prepare Prose Verification Data

1. **Collect XML files.** Use Glob to find all `.xml` files under `{MG_INSTALL_WORKSPACE_DIR}/generate/xml-sources/`. If an audience filter is active, only include files under `xml-sources/{audience}/` and root-level XML files (GLOSSARY.xml, OVERVIEW.xml).

2. **For each XML file, run prepare-prose-verify.py:**
   ```bash
   uv run {MG_INSTALL_SCRIPTS_DIR}/prepare-prose-verify.py \
       --xml-file {xml_file_path} \
       --output-dir {MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT}
   ```

### Step 4: Wave 1 — Entity Extraction

Spawn extraction agents (one per document, parallel foreground, **model: sonnet**):
```
Agent(
  model="sonnet",
  description="Entity extraction {audience} {DOCUMENT}",
  prompt="You are an entity extraction agent.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/extract-prose-entities.md

Project root: {project_root}
Prose verify dir: {MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT}
Entities file: {MG_INSTALL_WORKSPACE_DIR}/auditv2/entities-{audience}-{DOCUMENT}.json
Scripts dir: {MG_INSTALL_SCRIPTS_DIR}"
)
```

### Step 5: Deterministic Clearing + Check B

After all extraction agents complete, run the clearing script once per document:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/clear-matched-entities.py \
    --entities-file {MG_INSTALL_WORKSPACE_DIR}/auditv2/entities-{audience}-{DOCUMENT}.json \
    --prose-verify-dir {MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT} \
    --uncleared-file {MG_INSTALL_WORKSPACE_DIR}/auditv2/uncleared-{audience}-{DOCUMENT}.json \
    --findings-file {MG_INSTALL_WORKSPACE_DIR}/auditv2/findings-prose-{audience}-{DOCUMENT}.json \
    --document {DOCUMENT} \
    --audience {audience} \
    --not-entities-file {MG_INSTALL_WORKSPACE_DIR}/auditv2/not-entities.json
```

Read the stderr output for the clearing summary (Extracted/Cleared/Uncleared counts).

Read the uncleared file to check if there are any uncleared entities. If the uncleared file is empty (`[]`) for a document, skip that document in waves 2+.

### Step 6: Waves 2–N — Entity Resolution

**Repeat the following for each wave from 1 to `num_waves`:**

a. **Clean up state files** so the next wave's agents start fresh:
```bash
rm -f {MG_INSTALL_WORKSPACE_DIR}/auditv2/*.sectionctl
```

b. **Recompute affected sections.** Propagation within the previous wave pruned the uncleared file, so some sections may now have zero entities. Recompute the affected-sections filter for each document:
```bash
python3 -c "
import json, sys
with open(sys.argv[1]) as f: u = json.load(f)
s = sorted(set(e['section'] for e in u))
with open(sys.argv[2], 'w') as f: json.dump(s, f, indent=2)
" {MG_INSTALL_WORKSPACE_DIR}/auditv2/uncleared-{audience}-{DOCUMENT}.json \
  {MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT}/affected-sections.json
```
If the uncleared file is empty (`[]`) for a document, skip that document for the remaining waves.

c. **Write session config** for each document that still has uncleared entities:
```bash
python3 -c "
import json, os
session = {
    'workspace': '{MG_INSTALL_WORKSPACE_DIR}',
    'document': '{DOCUMENT}',
    'audience': '{audience}',
    'wave': {N},
    'prose_verify_dir': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT}',
    'uncleared_file': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/uncleared-{audience}-{DOCUMENT}.json',
    'findings_file': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/findings-prose-{audience}-{DOCUMENT}.json',
    'sections_filter': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/prose-verify-{audience}-{DOCUMENT}/affected-sections.json',
    'not_entities_file': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/not-entities.json',
    'dismissed_this_run_file': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/dismissed-this-run.json',
    'protected_entities_file': '{MG_INSTALL_WORKSPACE_DIR}/auditv2/protected-entities.json',
}
path = os.path.join('{MG_INSTALL_WORKSPACE_DIR}', 'auditv2', 'session-{audience}-{DOCUMENT}.json')
with open(path, 'w') as f:
    json.dump(session, f, indent=2)
"
```

Where `{N}` is the current wave number (1, 2, 3, ...).

d. **Spawn resolution agents** (one per document that still has uncleared entities, parallel foreground, **model: sonnet**):
```
Agent(
  model="sonnet",
  description="Entity resolution W{N} {audience} {DOCUMENT}",
  prompt="You are an entity resolution agent.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/resolve-prose-entities.md

Scripts dir: {MG_INSTALL_SCRIPTS_DIR}
Session: {MG_INSTALL_WORKSPACE_DIR}/auditv2/session-{audience}-{DOCUMENT}.json
Ref types reference: {MG_INSTALL_AGENTS_DIR}/../references/typed-refs-format.md
Wave: {N}
Num waves: {num_waves}"
)
```

### Step 6.5: Classify Dismissed Entities

After all resolution waves complete, check if any entities were dismissed during this run:

```bash
python3 -c "
import json, sys
with open(sys.argv[1]) as f: d = json.load(f)
print(len(d))
" {MG_INSTALL_WORKSPACE_DIR}/auditv2/dismissed-this-run.json
```

If the count is greater than 0, spawn a classification agent (**model: sonnet**, foreground):
```
Agent(
  model="sonnet",
  description="Classify dismissed entities",
  prompt="You are a dismissed entity classification agent.

Read and follow the instructions in: {MG_INSTALL_AGENTS_DIR}/classify-dismissed-entities.md

Scripts dir: {MG_INSTALL_SCRIPTS_DIR}
Dismissed this run file: {MG_INSTALL_WORKSPACE_DIR}/auditv2/dismissed-this-run.json
Not entities file: {MG_INSTALL_WORKSPACE_DIR}/auditv2/not-entities.json
Protected entities file: {MG_INSTALL_WORKSPACE_DIR}/auditv2/protected-entities.json
Workspace: {MG_INSTALL_WORKSPACE_DIR}/auditv2
Ref types reference: {MG_INSTALL_AGENTS_DIR}/../references/typed-refs-format.md"
)
```

If the count is 0, skip classification (no dismissed entities to classify).

### Step 7: Report

Present a summary combining deterministic and prose findings:

```
Audit v2 Results:

| Document                  | Ref Issues | Prose Issues | Total |
|---------------------------|------------|--------------|-------|
| devops/OPERATIONS         | 2          | 1            | 3     |
| devops/TROUBLESHOOTING    | 0          | 0            | 0     |
| GLOSSARY                  | 1          | 0            | 1     |

Total: {N} issues across {M} documents
```

Collect prose findings from each document's findings file (`{MG_INSTALL_WORKSPACE_DIR}/auditv2/findings-prose-*.json`).

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
Run /mg:auto-doc-fix to correct these issues, then re-run /mg:auto-doc-auditv2 to confirm.
When clean, run /mg:auto-doc-verify for full editorial review.
```

### Step 8: Persist Summary

Write the full summary text from Step 7 to `{MG_INSTALL_WORKSPACE_DIR}/auditv2/summary.md` so it survives beyond the conversation. Then tell the user:
```
Summary written to .mg/docs/auditv2/summary.md
```

## Important Principles

- **Audit is lightweight.** It checks reference integrity and prose consistency, not editorial quality or completeness. That's verify's job.
- **Deterministic checks run first.** verify-xml-refs.py and clear-matched-entities.py are fast and catch the most common issues.
- **verify-xml-refs.py runs ONCE for the whole xml-sources directory.** Do not call it per-file.
- **prepare-prose-verify.py takes `--output-dir` (a directory), not `--output` (a file).**
- **clear-matched-entities.py runs ONCE per document after extraction.** Do not call it per-section.
- **Extraction agents do NOT read refs.** They extract entity names from prose only.
- **Resolution agents only visit affected sections** (via `--sections-filter`). Clean sections are skipped.
- **Skip documents with no uncleared entities** in resolution waves — no work to do.
- **Zero exit on clean.** If no issues found, congratulate and suggest verify as next step.
