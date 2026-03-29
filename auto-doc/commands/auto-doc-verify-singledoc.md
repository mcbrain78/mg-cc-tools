---
name: mg:auto-doc-verify-singledoc
description: Verify documentation quality using per-document Sonnet editorial checks with SendMessage turn-based question delivery
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, SendMessage
---

# Documentation Verifier (Single-Doc)

You are the **Verifier (Single-Doc)** -- an alternative verify step that spawns one Sonnet agent per document for editorial checks. Each agent reads its document once, then receives question sets one at a time via SendMessage.

Read the shared schema before starting: `Read references/schema.md`

## Process

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
  --findings-prefix editorial-singledoc
```
Parse the JSON output to get all runtime paths (`project_root`, `docs_dir_abs`, `glossary_path`, `findings_file`, `findings_prefix`, `manifest`, `scan_context_path`, `tmp_dir`, `fact_checker_findings`). If non-zero exit, print the error and abort.

### Step 2: Fact-Checkers

Spawn all 4 agents in a **single parallel message** (model=sonnet, foreground). Each reads its agent .md by file reference:

| Agent | Agent file | Extra params |
|---|---|---|
| Code example verifier | `{AGENTS_DIR}/code-example-verifier.md` | `review_manifest`, `findings_file` (code_example) |
| Data model verifier | `{AGENTS_DIR}/data-model-verifier.md` | `review_manifest`, `scan_context_path`, `findings_file` (data_model) |
| Cross-doc checker | `{AGENTS_DIR}/cross-doc-checker.md` | `review_manifest`, `glossary_path`, `findings_file` (cross_doc) |
| Completeness checker | `{AGENTS_DIR}/completeness-checker.md` | `review_manifest`, `scan_context_path`, `findings_file` (completeness) |

All agents receive `project_root`. The `review_manifest` is the `manifest` path from setup. Wait for all 4.

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
  findings_file={findings_file}, tmp_dir={tmp_dir}, question_file={question_file}")
```

**Turn loop:**
```
loop:
  result = Bash("python3 {SCRIPTS_DIR}/editorial-orchestrate.py --next \
    --state {tmp_dir}/ed-orchestrate-state.json")
  Parse JSON.
  If action is "done" → break.
  For each target in "send": SendMessage to "Editorial: {name}":
    "Read {question_file}. Evaluate checks against the document. Record findings to {findings_file}."
  Wait for all responses.
```

### Step 4: Merge

Merge all findings — 4 explicit fact-checker files + editorial glob:
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
- **Turn-based editorial minimizes token use** — each document is read once, question sets drip-fed via SendMessage.
- **Focused agents with isolated findings** — orchestrator merges after all agents complete.
- **Prefer false negatives over false positives** — a noisy report trains users to ignore it.
- **Verify clears all artifacts before each run** via `list-verify-findings.py --clean`.
- Placeholders `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, `{CHECKS_FILE}`, `{TEMPLATES_DIR}`, `{AGENTS_DIR}` are resolved by install.sh at install time.
