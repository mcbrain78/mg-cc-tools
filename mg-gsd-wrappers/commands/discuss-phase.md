# /mg:discuss-phase — GSD Deviation-Aware Phase Discussion

---
name: mg:discuss-phase
description: Invoke only via /mg:discuss-phase <number> — wraps gsd:discuss-phase with prior-phase deviation context
argument-hint: "<phase-number>"
allowed-tools:
  - Read
  - Glob
  - Grep
  - AskUserQuestion
  - Skill
  - Bash
---

<objective>
Scan prior executed phases within the current milestone for deviations that could affect the target phase, surface relevant findings to the user, then delegate to `gsd:discuss-phase` with appropriate flags.

This wrapper adds deviation awareness to the standard discussion flow. The user always gets vanilla `gsd:discuss-phase` behavior — this just front-loads relevant context from prior execution.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<phase-number>`
</context>

<process>

## 1. Parse Arguments

Extract the phase number from `$ARGUMENTS` (first token, integer or decimal like `2.1`).

If missing:
```
ERROR: Phase number required.

Usage: /mg:discuss-phase <phase-number>
```
Exit.

## 2. Identify Current Milestone Phase Range

Read `.planning/ROADMAP.md`.

Find the milestone section that contains this phase number. Milestones are typically structured as:
```markdown
## Milestone: vN — Name
### Phase X: ...
### Phase Y: ...
```

Extract the phase number range for this milestone (e.g., phases 75-92 for v12). Store as `milestone_start` and `milestone_end`.

If ROADMAP.md doesn't exist or the phase isn't found:
```
WARNING: Could not determine milestone range from ROADMAP.md. Skipping deviation scan.
```
Skip to Step 5.

## 3. Scan for Deviations from Prior Executed Phases

Scan SUMMARY.md files from executed phases within the milestone range that precede the current phase.

**3a. Find prior phase SUMMARY.md files:**

Glob for `.planning/phases/*-*/*-SUMMARY.md`. Filter results to phases where the leading number (digits before the first `-` in the directory name) is within the milestone range AND less than the current phase number.

**3b. Read SUMMARY.md files:**

For each matching SUMMARY.md file, read the following sections:
  - **"Deviations from Plan"** — implementation changes, auto-fixed issues, unexpected behaviors
  - **"Decisions Made"** — runtime decisions that weren't in the original plan

The deviation format to expect:
```markdown
## Deviations from Plan
### Auto-fixed Issues
**1. [Rule 1 - Bug] Title**
- **Found during:** Task N (context)
- **Issue:** description
- **Fix:** description

## Decisions Made
- Decision as bullet point
```

**3c. Read prior CONTEXT.md files:**

Glob for `.planning/phases/*-*/*-CONTEXT.md`. Filter results to phases within the milestone range AND less than the current phase number. Read the `<decisions>` sections to understand what was originally planned.

**3d. Evaluate relevance:**

For each deviation/decision found, assess: does this deviation represent a decision that could affect the current phase's scope or implementation?

Consider:
- Does the deviation change shared infrastructure this phase depends on?
- Does a runtime decision alter an API, schema, or interface this phase consumes?
- Does an auto-fix introduce a pattern or constraint that this phase should follow?

Collect all relevant deviations with their source phase and summary.

## 4. Present Relevant Deviations

**If no relevant deviations found:** Skip to Step 5.

**If relevant deviations found:**

For each relevant deviation, present via AskUserQuestion:
- header: "Deviation"
- question: "Phase {source_phase} deviated: {summary}. Does this affect Phase {current_phase}?"
- options:
  - "Yes, discuss this" — "Include this finding in the discussion context"
  - "No, not relevant" — "Skip this deviation"

Collect all confirmed-relevant deviations.

## 5. Delegate to gsd:discuss-phase

**If relevant deviations were confirmed AND CONTEXT.md already exists for this phase:**

The deviations are now in conversation context. Use `--check-remaining` to focus discussion on areas affected by the deviations:

```
Skill("gsd:discuss-phase", "{phase} --check-remaining \"Implementation of prior phases surfaced new findings and deviations. Review their implications for this phase and discuss any new gray areas.\"")
```

**If relevant deviations were confirmed but NO CONTEXT.md exists:**

The deviations are in conversation context. Standard discuss-phase will incorporate them naturally:

```
Skill("gsd:discuss-phase", "{phase}")
```

**If no relevant deviations (or all were dismissed):**

Standard delegation:

```
Skill("gsd:discuss-phase", "{phase}")
```

</process>

<important_notes>
- This wrapper is read-only until delegation — it never modifies files, only reads SUMMARY.md and CONTEXT.md
- The deviation scan is a best-effort heuristic — LLM judgment determines relevance
- The user can always bypass this wrapper and use `gsd:discuss-phase` directly for vanilla behavior
- Deviations surfaced here become part of the conversation context, so `gsd:discuss-phase` naturally considers them even without explicit flags
- After completion, suggest the next step: `/mg:plan-phase {phase}` (deviation-aware planning with requirement traceability)
</important_notes>
