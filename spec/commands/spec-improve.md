# Spec Improve

---
name: mg:spec-improve
description: Iterative subagent-review improvement of a concept spec
argument-hint: "<file-path>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

<objective>
Improve a concept spec through iterative rounds of independent subagent review. Only a subagent — which carries no prior conversation context — can review with truly fresh eyes.

Each round: review → triage → research (if needed) → fix → validate → report → wait for approval. Repeat until the reviewer finds no actionable issues.
</objective>

<context>
Arguments: $ARGUMENTS

Expected: a path to the file to improve (typically a concept spec at `docs/work-queue/todo/{name}/concept.md`).

Concept spec template: `{CONCEPT_TEMPLATE}`

File operations script: `{SCRIPTS_DIR}/improve_files.py`
</context>

<process>

## Setup

1. Parse `$ARGUMENTS` to get the target file path. If missing:
   ```
   ERROR: File path required.

   Usage: /mg:spec-improve <file-path>

   Example:
     /mg:spec-improve docs/work-queue/todo/worktrees/CONCEPT.md
   ```
   Exit.

2. Read the target file. If it doesn't exist or is empty, report the error and exit.

3. Initialize the working session by running:
   ```
   uv run {SCRIPTS_DIR}/improve_files.py init <target-file-path>
   ```
   This backs up the original (once), creates the working copy, and outputs JSON with all resolved paths:
   ```json
   {
     "auto_improve": "...-auto-improve.md",
     "non_goals": "...-NON-GOALS.md",
     "non_goals_exists": true/false,
     "original_backup": "....original.md",
     "backup_created": true/false
   }
   ```
   If `backup_created` is true, report: `Backed up original to <original_backup>`

   Store the paths from the JSON output — use them for all subsequent file references:
   - `AUTO_IMPROVE_FILE` = `auto_improve`
   - `NON_GOALS_FILE` = `non_goals` (may not exist yet; `non_goals_exists` tells you)

**CRITICAL: All modifications happen exclusively on AUTO_IMPROVE_FILE. Do not touch the original until the user explicitly approves.**

## Step 1 — Independent Review

Launch a reviewer subagent (Agent tool) with the following prompt:

```
You are a senior engineer reviewing a file with completely fresh eyes.
You have NO prior context about this project.

Read the file at: {AUTO_IMPROVE_FILE path}

{If non_goals_exists is true, include:}
Also read the non-goals file at: {NON_GOALS_FILE path}
These are explicit scoping decisions — do not flag issues that fall
under a listed non-goal. You may still flag severe bugs in non-goal
areas if they would break something.

Also read the concept spec template at: {CONCEPT_TEMPLATE}
Use this to assess whether expected sections are present and
adequately filled. A thin section is worth flagging if it should
have more depth given the concept's nature.

If the file references existing functionality — by path, code reference,
or concept (e.g., "replaces X", "extends Y") — read that code before
reviewing. You cannot assess a plan without understanding what it builds
on or replaces. All issues must be actionable on the target file only.

Provide a critical review focused on:

1. Internal contradictions or inconsistencies
2. Missing pieces that would block implementation
3. Assumptions that aren't stated or validated
4. Overengineering vs underengineering
5. Whether examples actually match the spec text
6. Decision quality — every decision in the plan must be real:
   - Open questions ("non-blocking", "to resolve during implementation")
     must be resolved now or flagged as critical for the user to decide.
     Deferring to implementation is 5-10x more expensive.
   - Thin decisions that restate a choice without reasoning, tradeoffs,
     or evidence are not decisions — flag them as open questions.
   - Deferred commitments ("future work", "v2", "later phase") that park
     a problem as a future promise. If needed, put it in the plan. If
     not needed, remove it entirely. (Explicit scope exclusions like
     "this plan does NOT cover X" are fine — those are boundaries, not
     deferrals.)
7. Simpler alternatives — now that the full design is laid out, step back:
   could the same goals be achieved with a fundamentally simpler approach?
   A solution that looked necessary during incremental discussion sometimes
   reveals a shorter path when viewed as a whole. Only flag this if you can
   name a concrete simpler alternative and explain why it might be better —
   not a vague "could be simpler."
8. Over-specification — flag implementation code (function bodies, algorithm
   implementations) in the spec. A concept document defines interfaces and
   contracts (CLI flags, JSON schemas, XML structures, data flow). Function
   bodies cross into the implementer's work and risk being copied verbatim
   without thinking about edge cases. The test: if you removed the code and
   left only a prose description of what the function does, would an
   implementer still know what to build? If yes, the code doesn't belong
   in the spec.
9. Verification coverage — check that every row in the Scope table has at
   least one corresponding item in the Verification section. A deliverable
   with no way to verify it is either untestable (rethink the deliverable)
   or under-specified (add the verification criterion).

Be harsh. Flag everything that seems off.
Validate claims against actual data or code where possible.

For each issue, state:
- Severity (critical / major / minor)
- Location in the file (section or line reference)
- What is wrong
- Suggested fix (if you have one)
```

## Step 2 — Triage

Read the reviewer's feedback. For each issue, apply this test — but only consider issues that are solvable without user input and that do not change the intent or scope of the file:

**Exception — unresolved and deferred items:** Do NOT dismiss these because the plan already acknowledges them — that's the problem. Resolve using codebase context, or surface to the user in Step 7. Never pass through silently.

**Fix immediately** if the issue would cause a wrong decision or block implementation — i.e., an implementer reading this file would build the wrong thing, get stuck, or have to come back and ask.

**Fix as a batch** if 3+ minor ambiguities cluster in the same section or topic. Individually they're cosmetic, but clustered they signal the section is underspecified and needs a clarity pass.

**Skip** everything else. Log it as cosmetic in the report and move on.

Fix **up to 5 issues** per round. If fewer than 5 clear the bar, fix only those. If zero clear the bar, skip straight to Step 7 and recommend stopping.

**When running multiple rounds:** Treat each reviewer's output as the complete, canonical list of live issues. If an issue appears again from a previous round, it means it was not fixed — do not dismiss it as "already seen." If an issue from a previous round no longer appears, the reviewer considers it resolved. Never use your memory of prior rounds to filter or deprioritize findings.

## Step 3 — Enforce Cap

Count the issues you marked for fixing in Step 2. If the count exceeds 5, re-read the list, keep only the 5 highest-severity ones, and move the rest to deferred. Do NOT proceed until the count is at most 5.

## Step 4 — Targeted Research

If any of the triaged issues require deeper understanding of the project, launch a research subagent (Agent tool):

```
Read the following project files to gather context needed to resolve
the issues listed below. Do NOT modify any files — only report findings.

Project root: {project root}
Files to inspect: {list relevant dependency files, configs, or types}

Issues to research:
{paste the specific issues that need context}

For each issue, report:
1. What you found in the codebase that is relevant
2. Whether the issue is a true problem or a false positive due to missing context
3. Suggested resolution (if it is a true problem)
```

## Step 5 — Implement Fixes

Apply all fixes to AUTO_IMPROVE_FILE where you are confident in the resolution. For each fix, leave a brief inline comment or commit-style note explaining what changed and why.

When adding detail to resolve a "missing piece" finding, specify the interface contract (CLI flags, data format, behavior description) — not implementation code. If the fix requires showing how something works, describe the algorithm in prose rather than writing the function body.

## Step 6 — Validate

After all fixes are applied:

- Re-read AUTO_IMPROVE_FILE to verify internal consistency
- Confirm no new issues were introduced by the fixes

If validation surfaces new problems, fix them before proceeding.

## Step 7 — Report to User

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

## Step 8 — Approval

After delivering the report, **stop and wait for the user**. Do not proceed until the user responds. The user approves **fixes** and **non-goals** independently.

- **Fixes**:
  - `approve` → run: `uv run {SCRIPTS_DIR}/improve_files.py approve <target-file-path>`
  - `reject` → run: `uv run {SCRIPTS_DIR}/improve_files.py reject <target-file-path>`
  - The user may also request further changes (repeat from Step 5) or another round (repeat from Step 1).

- **Non-goals**: For each proposed non-goal the user approves, run:
  ```
  uv run {SCRIPTS_DIR}/improve_files.py append-non-goal <target-file-path> "<non-goal text>"
  ```
  Drop any the user rejects — they remain fair game for future reviewers.

</process>

<important_notes>
- Only a subagent can review with truly fresh eyes. The main agent carries conversation context that biases the review. Always use the Agent tool for the reviewer.
- The concept spec template at `{CONCEPT_TEMPLATE}` is included in the reviewer prompt so it can assess structural completeness — whether expected sections are present and adequately filled.
- The 5-issue cap per round prevents scope creep and keeps each round focused. If the reviewer finds 15 issues, the 5 most severe get fixed first. The rest surface in subsequent rounds.
- AUTO_IMPROVE_FILE is the safety net. The original is never touched until explicit approval. This allows the user to reject changes cleanly.
- NON_GOALS_FILE accumulates across rounds. Once a non-goal is approved, future reviewers skip it, preventing the same intentional exclusion from being flagged repeatedly.
- When running multiple rounds, each round starts fresh — the reviewer re-reads the file and produces a new list. Do not carry state from previous rounds except for the NON_GOALS_FILE.
- All file operations (backup, copy, delete, approve, reject, non-goal append) are handled by `{SCRIPTS_DIR}/improve_files.py`. Do not perform these operations manually.
</important_notes>
