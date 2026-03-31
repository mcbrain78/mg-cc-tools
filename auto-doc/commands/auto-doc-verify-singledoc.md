---
name: mg:auto-doc-verify-singledoc
description: Verify documentation quality using per-document self-driven editorial checks with audience filtering
allowed-tools: Bash, Read, Write, Glob, Grep, Agent
---

# Documentation Verifier (Single-Doc)

You are the **Verifier (Single-Doc)** -- an alternative verify step that spawns one Sonnet agent per document for editorial checks. Each agent reads its document once, then drives its own question loop via `editorial-questions.py --advance`.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 {EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

Read the shared schema before starting: `Read references/schema.md`

## Process

### Step 0: Parse Arguments

Parse the user's input text for optional audience names. Example: user types `/mg:auto-doc-verify-singledoc devops end-users`. Extract audience names as a comma-separated string (e.g., `devops,end-users`). If no audience names provided, verify all docs.

### Step 1: Setup

Run the setup script to check prerequisites, build paths, run prep scripts, and init findings files:
```bash
python3 {SCRIPTS_DIR}/verify-setup.py \
  --scan-file .mg/docs/docs-scan.json \
  --config .mg/docs/.docs.config.json \
  --global-config {GLOBAL_CONFIG} \
  --checks-file {CHECKS_FILE} \
  --scripts-dir {SCRIPTS_DIR} \
  --templates-dir {TEMPLATES_DIR} \
  --findings-prefix editorial-singledoc \
  [--audience AUDIENCES]
```
Add `--audience` only if the user specified audience names in Step 0.

Parse the JSON output to get all runtime paths (`project_root`, `docs_dir_abs`, `glossary_path`, `findings_file`, `findings_prefix`, `manifest`, `scan_context_path`, `tmp_dir`, `xml_dir`, `fact_checker_findings`). If non-zero exit, print the error and abort.

Note: `xml_dir` is non-null when XML sources exist (produced by generate). This enables deterministic ref verification and narrows the LLM fact-checker scope.

### Step 1.5: Deterministic XML Ref Verification

If `xml_dir` is non-null, run the deterministic XML reference checker **in the orchestrator** (not as a subagent — it's a fast deterministic script):

```bash
python3 {SCRIPTS_DIR}/verify-xml-refs.py \
    --xml-dir {xml_dir} \
    --project-root {project_root} \
    --findings-file {findings_file} \
    [--audience AUDIENCES]
```

Add `--audience` only if the user specified audience names in Step 0.

This checks every typed ref (db schemas/tables/columns, code classes/functions, flow names, env vars, config paths, enum values) against the actual codebase deterministically. No LLM involved.

### Step 2: Fact-Checkers

**If `xml_dir` is non-null:** skip the code-example-verifier and data-model-verifier agents — their checks are now covered deterministically by `verify-xml-refs.py`. Instead, add focused prose-vs-refs verification. The fact-checker step becomes:

1. **Prepare prose verification data** for each XML file:
   ```bash
   python3 {SCRIPTS_DIR}/prepare-prose-verify.py \
       --xml-file {xml_file} \
       --output-dir {tmp_dir}/prose-verify/{audience}/{doc_name}
   ```
   Run this for every XML file in `{xml_dir}` (recursively). Each produces per-section JSON files with body + readable refs summary.

2. **Spawn agents** in a single parallel message:

| Agent | Agent file | Extra params |
|---|---|---|
| Prose-vs-refs verifier (one per XML doc) | `{AGENTS_DIR}/verify-prose.md` | `prose_verify_dir`, `findings_file` (use a per-doc file at `{tmp_dir}/prose-verify-findings-{doc_name}.json`), `scripts_dir` |
| Cross-doc checker | `{AGENTS_DIR}/cross-doc-checker.md` | `review_manifest`, `glossary_path`, `findings_file` (cross_doc) |
| Completeness checker | `{AGENTS_DIR}/completeness-checker.md` | `review_manifest`, `scan_context_path`, `findings_file` (completeness) |

   Initialize each prose-verify findings file before spawning:
   ```bash
   python3 {SCRIPTS_DIR}/list-verify-findings.py --init \
       --findings-file {tmp_dir}/prose-verify-findings-{doc_name}.json
   ```

**If `xml_dir` is null (no XML sources):** fall back to all 4 agents as before:

| Agent | Agent file | Extra params |
|---|---|---|
| Code example verifier | `{AGENTS_DIR}/code-example-verifier.md` | `review_manifest`, `findings_file` (code_example) |
| Data model verifier | `{AGENTS_DIR}/data-model-verifier.md` | `review_manifest`, `scan_context_path`, `findings_file` (data_model) |
| Cross-doc checker | `{AGENTS_DIR}/cross-doc-checker.md` | `review_manifest`, `glossary_path`, `findings_file` (cross_doc) |
| Completeness checker | `{AGENTS_DIR}/completeness-checker.md` | `review_manifest`, `scan_context_path`, `findings_file` (completeness) |

All agents receive `project_root`. The `review_manifest` is the `manifest` path from setup. Wait for all agents.

### Step 3: Editorial

**Init:** Run the editorial orchestrator to create state, write first question files, and get spawn targets:
```bash
python3 {SCRIPTS_DIR}/editorial-orchestrate.py --init \
  --manifest {manifest} --checks {CHECKS_FILE} \
  --findings-prefix {findings_prefix} --tmp-dir {tmp_dir} \
  --state {tmp_dir}/ed-orchestrate-state.json
```
Parse the JSON. If action is "done", skip to Step 4.

**Spawn:** For each doc in the "spawn" result, launch a Sonnet agent in a single parallel message:
```
Agent(model="sonnet", description="Editorial: {name}",
  prompt="Read and follow: {AGENTS_DIR}/editorial-checker-singledoc.md
  Parameters: doc_file={source}, doc_source={source}, audience={audience},
  findings_file={findings_file}, tmp_dir={tmp_dir}, question_file={question_file},
  state_file={state_file}")
```

Wait for all agents to complete. No turn loop needed — each agent drives its own question loop.

### Step 4: Merge

Merge all findings — fact-checker files + editorial glob + prose-verify files (if XML path):

**If `xml_dir` is non-null:**
```bash
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --merge-from {fact_checker_findings.cross_doc} \
  --merge-from {fact_checker_findings.completeness} \
  --merge-glob "{findings_prefix}-*.json" \
  --merge-glob "{tmp_dir}/prose-verify-findings-*.json" \
  --findings-file {findings_file} \
  --output {tmp_dir}/all-findings.json
```

**If `xml_dir` is null:**
```bash
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --merge-from {fact_checker_findings.code_example} \
  --merge-from {fact_checker_findings.data_model} \
  --merge-from {fact_checker_findings.cross_doc} \
  --merge-from {fact_checker_findings.completeness} \
  --merge-glob "{findings_prefix}-*.json" \
  --findings-file {findings_file} \
  --output {tmp_dir}/all-findings.json
```

### Step 5: Triage + Report

Spawn 1 Sonnet agent:
```
Agent(model="sonnet", description="Triage and report",
  prompt="Read and follow: {AGENTS_DIR}/triage-reporter.md
  Parameters:
  - all_findings_file: {tmp_dir}/all-findings.json
  - findings_file: {findings_file}
  - dismissed_file: {project_root}/.mg/docs/docs-verify-findings-dismissed.json
  - report_file: {project_root}/.mg/docs/docs-verify-report.md")
```
Wait for completion.

### Step 6: Present

Read the report at `{project_root}/.mg/docs/docs-verify-report.md`. Print:
```
Verification complete (singledoc) -- {N} issues found.

Full report: .mg/docs/docs-verify-report.md
```
If findings exist: `Run /mg:auto-doc-update to fix verify findings.`
If completeness findings exist: `Found {N} documentation gaps. Consider adding to .planning/BACKLOG.md as documentation debt.`

## Principles

- **Read-only on documentation files.** Write only to `.mg/docs/` workspace files.
- **Subagents read their own instructions via file path** — keeps agent definitions out of orchestrator context.
- **Self-driven editorial agents** — each agent loops through question sets independently, no orchestrator coordination needed.
- **Focused agents with isolated findings** — orchestrator merges after all agents complete.
- **Prefer false negatives over false positives** — a noisy report trains users to ignore it.
- **Verify clears all artifacts before each run** via `list-verify-findings.py --clean`.
- Placeholders `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `{CHECKS_FILE}`, `{TEMPLATES_DIR}`, `{AGENTS_DIR}` are resolved by install.sh at install time.
