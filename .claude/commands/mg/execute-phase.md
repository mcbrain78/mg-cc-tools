# /mg:execute-phase — GSD Phase Executor with Deviation Flagging

---
name: mg:execute-phase
description: Invoke only via /mg:execute-phase <number> — wraps gsd:execute-phase with post-execution deviation impact analysis
argument-hint: "<phase-number> [--flags]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
---

<objective>
Delegate to `gsd:execute-phase`, then after execution completes, scan the resulting SUMMARY.md for deviations and check whether they impact downstream phases that already have CONTEXT.md files.

This wrapper adds post-execution awareness — catching deviations early so downstream discussions can incorporate them.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<phase-number> [--flags]`

The phase number is the first token. Everything after it is pass-through flags for `gsd:execute-phase`.
</context>

<process>

## 1. Parse Arguments

Extract from `$ARGUMENTS`:
- **Phase number** — first token (integer or decimal like `2.1`)
- **Pass-through flags** — remaining tokens

If phase number is missing:
```
ERROR: Phase number required.

Usage: /mg:execute-phase <phase-number> [--flags]
```
Exit.

## 2. Delegate to gsd:execute-phase

Pass through everything:

```
Skill("gsd:execute-phase", "{phase} {pass-through-flags}")
```

Wait for execution to complete.

## 3. Post-Execution Deviation Check

After execution completes:

**3a. Find this phase's SUMMARY.md:**

Pad the phase number to 2 digits. Glob for `.planning/phases/{padded}-*/*-SUMMARY.md`.

If no SUMMARY.md found, execution may not have completed normally. Report execution result and exit.

**3b. Extract deviations:**

Read each SUMMARY.md found. Extract:
- **"Deviations from Plan"** section — implementation changes, auto-fixed issues
- **"Decisions Made"** section — runtime decisions

If no deviations or decisions found: skip to Step 4.

**3c. Identify downstream phases with existing CONTEXT.md:**

Read `.planning/ROADMAP.md` to find the current milestone's phase range.

For each phase in the milestone range with a number GREATER than the current phase:
- Glob for `.planning/phases/{padded}-*/*-CONTEXT.md`
- If CONTEXT.md exists, read its `<decisions>` section

**3d. Evaluate downstream impact:**

For each downstream phase with CONTEXT.md, assess: do any of the deviations from this execution affect locked decisions in that phase's context?

Consider:
- Does the deviation change shared infrastructure the downstream phase depends on?
- Does a runtime decision alter an API, schema, or interface the downstream phase assumes?
- Does an auto-fix introduce a pattern or constraint that conflicts with downstream plans?

## 4. Report

**If downstream impact detected:**

For each affected downstream phase:
```
Phase {current}'s execution had deviations that may affect Phase {downstream}'s context:
  - {deviation summary}

`/mg:discuss-phase {downstream}` will surface this automatically when you discuss that phase.
```

**If no downstream impact:**

Silent — just confirm execution completed. The standard `gsd:execute-phase` output is sufficient.

**After reporting (both cases), print:**
```
Next step: `/mg:discuss-phase {next_phase}` or `/mg:plan-phase {next_phase}` if context already exists
```

</process>

<important_notes>
- This wrapper does NOT modify any files — it only reads SUMMARY.md and CONTEXT.md after execution
- The post-execution check is informational only — it tells the user about potential impact but doesn't force action
- `mg:discuss-phase` will independently detect these same deviations when the user discusses the downstream phase
- The user can always use `gsd:execute-phase` directly for vanilla behavior
- Pass-through flags are forwarded verbatim (e.g., `--auto`, `--wave N`)
</important_notes>
