# Plan Phase (Deviation-Aware)

---
name: mg:plan-phase
description: Deviation-aware wrapper for gsd:plan-phase — checks for conflicts before planning
argument-hint: "<phase-number> [--flags]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - AskUserQuestion
  - Skill
  - Bash
---

<objective>
Scan prior executed phases within the current milestone for deviations that CONFLICT with locked decisions in this phase's CONTEXT.md, surface conflicts to the user, then delegate to `gsd:plan-phase` with any pass-through flags.

This wrapper catches cases where Phase N's implementation deviated in ways that invalidate decisions locked in Phase M's context — before planning wastes effort on stale assumptions.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<phase-number> [--flags]`

The phase number is the first token. Everything after it is pass-through flags for `gsd:plan-phase` (e.g., `--skip-research`, `--auto`, `--prd path`).
</context>

<process>

## 1. Parse Arguments

Extract from `$ARGUMENTS`:
- **Phase number** — first token (integer or decimal like `2.1`)
- **Pass-through flags** — remaining tokens (e.g., `--skip-research --auto`)

If phase number is missing:
```
ERROR: Phase number required.

Usage: /mg:plan-phase <phase-number> [--flags]
```
Exit.

## 2. Identify Current Milestone Phase Range

Read `.planning/ROADMAP.md`.

Find the milestone section that contains this phase number. Extract the phase number range for this milestone (e.g., phases 75-92). Store as `milestone_start` and `milestone_end`.

If ROADMAP.md doesn't exist or the phase isn't found:
```
WARNING: Could not determine milestone range from ROADMAP.md. Skipping deviation scan.
```
Skip to Step 5.

## 3. Scan for Deviations from Prior Executed Phases

Perform the same deviation scan as `mg:discuss-phase`:

**3a. Find prior phase directories:**

Use Glob to find phase directories in `.planning/phases/` where the phase number is within the milestone range AND less than the current phase number.

**3b. Read SUMMARY.md files:**

For each prior phase directory found:
- Glob for `*-SUMMARY.md` files within that directory
- Read the "Deviations from Plan" and "Decisions Made" sections

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

For each prior phase directory within the milestone range:
- Glob for `*-CONTEXT.md`
- Read `<decisions>` sections

## 4. Check for Conflicts with This Phase's CONTEXT.md

Read this phase's CONTEXT.md (Glob for `.planning/phases/{padded}-*/*-CONTEXT.md`).

**If no CONTEXT.md exists for this phase:** Skip to Step 5 — nothing to conflict with.

**If CONTEXT.md exists:**

Compare each deviation/decision from prior phases against the locked decisions in this phase's `<decisions>` section. Look for:
- A deviation that changes an API/interface this phase's decisions assume
- A runtime decision that contradicts a locked choice in CONTEXT.md
- An auto-fix that introduces constraints incompatible with planned approach

**If no conflicts found:** Skip to Step 5.

**If conflicts found:**

For each conflict, present via AskUserQuestion:
- header: "Conflict"
- question: "Phase {source_phase}'s implementation contradicts a decision in your Phase {current_phase} context: {summary}. Discuss before planning?"
- options:
  - "Discuss first (Recommended)" — "Run mg:discuss-phase to update context before planning"
  - "Plan anyway" — "Proceed with current context despite the conflict"

**If "Discuss first":**
```
Skill("mg:discuss-phase", "{phase}")
```
After discussion completes, continue to Step 5.

**If "Plan anyway":** Continue to Step 5.

## 5. Delegate to gsd:plan-phase

Pass the phase number and all pass-through flags:

```
Skill("gsd:plan-phase", "{phase} {pass-through-flags}")
```

</process>

<important_notes>
- This wrapper is read-only until delegation — it only reads SUMMARY.md and CONTEXT.md
- Conflict detection is a best-effort heuristic — LLM judgment determines whether a deviation contradicts a locked decision
- Pass-through flags are forwarded verbatim to `gsd:plan-phase` (e.g., `--skip-research`, `--auto`, `--prd path`)
- The user can always use `gsd:plan-phase` directly for vanilla behavior
- When "Discuss first" is chosen, `mg:discuss-phase` is invoked (which itself does deviation scanning), so the user gets the full deviation-aware discussion flow
</important_notes>
