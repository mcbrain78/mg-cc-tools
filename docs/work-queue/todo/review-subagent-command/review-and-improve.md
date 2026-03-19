# Auto-Improve Command for Claude Code

You will be improving the referenced file with the help of subagents.

## Setup

Create a copy of the file and append `-auto-improve` to the filename (e.g., `spec.md` → `spec-auto-improve.md`). We will refer to this copy as `AUTO_IMPROVE_FILE`.

**CRITICAL: All modifications must happen exclusively on AUTO_IMPROVE_FILE. Do not touch the original until the user explicitly approves.**

## Workflow

### Step 1 — Independent Review

Launch **REVIEWER_SUBAGENT** (see Subagent Definitions below). Only a subagent — which carries no prior conversation context — can review with truly fresh eyes.

### Step 2 — Triage

Read the reviewer's feedback. Select the **5 most important issues** that meet both criteria:

- They are solvable without additional user input.
- Fixing them does not change the intent or scope of the file.

**When running multiple rounds:** Treat each reviewer's output as the complete, canonical list of live issues. If an issue appears again from a previous round, it means it was not fixed — do not dismiss it as "already seen." If an issue from a previous round no longer appears, the reviewer considers it resolved. Never use your memory of prior rounds to filter or deprioritize findings.

### Step 3 — Targeted Research

If any of the 5 selected issues require deeper understanding of the project, launch **RESEARCH_SUBAGENT** (see Subagent Definitions below) with the relevant issues and file paths.

### Step 4 — Implement Fixes

Apply all fixes where you are confident in the resolution. For each fix, leave a brief inline comment or commit-style note explaining what changed and why.

### Step 5 — Validate

After all fixes are applied, run any available validation steps against AUTO_IMPROVE_FILE:

- Lint / type-check / build (if applicable)
- Re-read the file to verify internal consistency
- Confirm no new issues were introduced by the fixes

If validation surfaces new problems, fix them before proceeding.

### Step 6 — Report to User

Provide a summary structured as:

1. **Resolved issues** — what was found, what was changed, and why.
2. **Unresolved issues** — what was found but could not be fixed without user input. For each, state clearly what decision or information is needed.
3. **False positives** — any reviewer flags that turned out to be non-issues after research, with a brief explanation.

Then ask the user to `approve`, request changes, or `reject`.

### Step 7 — Approval

After delivering the report, **stop and wait for the user**. Do not proceed until the user responds.

- If the user types **`approve`** (or equivalent confirmation): copy AUTO_IMPROVE_FILE over the original file, then delete AUTO_IMPROVE_FILE. Confirm the replacement to the user.
- If the user requests further changes: apply them to AUTO_IMPROVE_FILE and repeat from Step 5 (Validate).
- If the user types **`reject`**: delete AUTO_IMPROVE_FILE, leave the original untouched, and confirm.

---

## Subagent Definitions

### REVIEWER_SUBAGENT

Launch as a subagent (Agent tool) with the following prompt:

```
You are a senior engineer reviewing a file with completely fresh eyes.
You have NO prior context about this project.

Read AUTO_IMPROVE_FILE at: <insert_auto_improve_file_path>

If needed, explore the surrounding project directory to understand
imports, shared types, or configuration — but your review targets
only the AUTO_IMPROVE_FILE.

Provide a critical review focused on:

1. Internal contradictions or inconsistencies
2. Missing pieces that would block implementation
3. Assumptions that aren't stated or validated
4. Overengineering vs underengineering
5. Whether examples actually match the spec text

Be harsh. Flag everything that seems off.
Validate claims against actual data or code where possible.

For each issue, state:
- Severity (critical / major / minor)
- Location in the file (section or line reference)
- What is wrong
- Suggested fix (if you have one)
```

### RESEARCH_SUBAGENT

Launch as a subagent (Agent tool) with the following prompt:

```
Read the following project files to gather context needed to resolve
the issues listed below. Do NOT modify any files — only report findings.

Project root: <project_root_path>
Files to inspect: <list relevant dependency files, configs, or types>

Issues to research:
<paste the specific issues that need context>

For each issue, report:
1. What you found in the codebase that is relevant
2. Whether the issue is a true problem or a false positive due to missing context
3. Suggested resolution (if it is a true problem)
```