# Auto-Improve Command for Claude Code

You will be improving the referenced file with the help of subagents.

## Setup

Create a copy of the file and append `-auto-improve` to the filename (e.g., `spec.md` → `spec-auto-improve.md`). We will refer to this copy as `AUTO_IMPROVE_FILE`.

Also check if a non-goals file exists alongside the original (e.g., `spec-NON-GOALS.md`). We will refer to this as `NON_GOALS_FILE`. If it doesn't exist yet, that's fine — it may be created during the workflow.

**CRITICAL: All modifications must happen exclusively on AUTO_IMPROVE_FILE. Do not touch the original until the user explicitly approves.**

## Workflow

### Step 1 — Independent Review

Launch **REVIEWER_SUBAGENT** (see Subagent Definitions below). Only a subagent — which carries no prior conversation context — can review with truly fresh eyes.

### Step 2 — Triage

Read the reviewer's feedback. For each issue, apply this test — but only consider issues that are solvable without user input and that do not change the intent or scope of the file:

**Fix immediately** if the issue would cause a wrong decision or block implementation — i.e., an implementer reading this file would build the wrong thing, get stuck, or have to come back and ask.

**Fix as a batch** if 3+ minor ambiguities cluster in the same section or topic. Individually they're cosmetic, but clustered they signal the section is underspecified and needs a clarity pass.

**Skip** everything else. Log it as cosmetic in the report and move on.

Fix **up to 5 issues** per round. If fewer than 5 clear the bar, fix only those. If zero clear the bar, skip straight to Step 8 and recommend stopping.

**When running multiple rounds:** Treat each reviewer's output as the complete, canonical list of live issues. If an issue appears again from a previous round, it means it was not fixed — do not dismiss it as "already seen." If an issue from a previous round no longer appears, the reviewer considers it resolved. Never use your memory of prior rounds to filter or deprioritize findings.

### Step 3 — Enforce Cap

Count the issues you marked for fixing in Step 2. If the count exceeds 5, re-read the list, keep only the 5 highest-severity ones, and move the rest to deferred. Do NOT proceed until the count is at most 5.

### Step 4 — Targeted Research

If any of the triaged issues require deeper understanding of the project, launch **RESEARCH_SUBAGENT** (see Subagent Definitions below) with the relevant issues and file paths.

### Step 5 — Implement Fixes

Apply all fixes where you are confident in the resolution. For each fix, leave a brief inline comment or commit-style note explaining what changed and why.

### Step 6 — Validate

After all fixes are applied, run any available validation steps against AUTO_IMPROVE_FILE:

- Re-read the file to verify internal consistency
- Confirm no new issues were introduced by the fixes

If validation surfaces new problems, fix them before proceeding.

### Step 7 — Report to User

Provide a summary structured as:

1. **Resolved issues** — what was found, what was changed, and why.
2. **Unresolved issues** — what was found but could not be fixed without user input. For each, state clearly what decision or information is needed.
3. **False positives** — any reviewer flags that turned out to be non-issues after research, with a brief explanation.
4. **Proposed non-goals** — issues the reviewer keeps flagging that are intentional scoping decisions, not problems. For each, state what it is and why it should be excluded from future reviews.

End the report with a **scorecard** so progress is trackable across rounds:

```
Reviewer flagged:           <total>
False positives:           -<count>
Fixed this round:          -<count>
Blocked (need user input): -<count>
Remaining solvable:        =<total minus above>
Non-goals (existing):       <count>
Non-goals (proposed new):   <count>
```

Then ask the user to approve or reject **fixes** and **proposed non-goals** independently.

### Step 8 — Approval

After delivering the report, **stop and wait for the user**. Do not proceed until the user responds. The user approves **fixes** and **non-goals** independently.

- **Fixes**: `approve` copies AUTO_IMPROVE_FILE over the original and deletes AUTO_IMPROVE_FILE. `reject` deletes AUTO_IMPROVE_FILE and leaves the original untouched. The user may also request further changes (repeat from Step 5).
- **Non-goals**: For each proposed non-goal the user approves, append it to NON_GOALS_FILE (create the file if it doesn't exist yet). Drop any the user rejects — they remain fair game for future reviewers.

---

## Subagent Definitions

### REVIEWER_SUBAGENT

Launch as a subagent (Agent tool) with the following prompt:

```
You are a senior engineer reviewing a file with completely fresh eyes.
You have NO prior context about this project.

Read AUTO_IMPROVE_FILE at: <insert_auto_improve_file_path>

[If NON_GOALS_FILE exists, include this line:]
Also read the non-goals file at: <insert_non_goals_file_path>
These are explicit scoping decisions — do not flag issues that fall
under a listed non-goal. You may still flag severe bugs in non-goal
areas if they would break something.

If the file references existing functionality — whether by file path,
code reference, or concept (e.g., "replaces the X pipeline",
"extends Y command") — read that code before reviewing. You cannot
assess a plan without understanding what it builds on or replaces.

All issues must be actionable on the target file only.

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