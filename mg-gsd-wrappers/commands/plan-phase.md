# /mg:plan-phase — GSD Deviation-Aware Phase Planner

---
name: mg:plan-phase
description: Invoke only via /mg:plan-phase <number> — wraps gsd:plan-phase with pre-flight deviation conflict checks and requirement traceability
argument-hint: "<phase-number> [--flags]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
  - Skill
  - Bash
---

<objective>
Run two pre-flight checks before delegating to `gsd:plan-phase`:

1. **Deviation conflicts** — Scan prior executed phases for deviations that CONFLICT with locked decisions in this phase's CONTEXT.md
2. **Requirement traceability** — Ensure this phase has requirement IDs in REQUIREMENTS.md so the planner can distribute them across plans and downstream verification works

This wrapper catches stale assumptions and missing traceability before planning wastes effort.
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

## 5. Requirement Traceability Check

Ensure this phase has proper requirement IDs before the planner runs. Without IDs, the planner invents ad-hoc ones that break traceability across planning, execution, verification, and milestone audit.

**5a. Read inputs:**

- Read the `**Requirements**:` line for this phase from `.planning/ROADMAP.md`
- Read `.planning/REQUIREMENTS.md` — note existing category prefixes, the highest used number per prefix, and which phase each requirement maps to
- Read this phase's CONTEXT.md `<decisions>` section (already loaded from Step 4 if it exists)

**If no CONTEXT.md exists:** Skip to Step 6 — nothing to derive requirements from.

**5b. Determine current state:**

- **If `Requirements: TBD` or the Requirements line is missing:** Phase has no requirement IDs → go to Step 5c
- **If requirement IDs exist:** Phase has IDs → go to Step 5d

**5c. Generate requirements (TBD case):**

Analyze the CONTEXT.md `<decisions>` section and generate requirement IDs following GSD conventions:

**Prefix selection:**
- Scan existing requirement categories in REQUIREMENTS.md for a prefix that fits this phase's domain. For example, if the phase is install-related and `INST-` already exists, continue with `INST-`.
- If no existing prefix fits, derive a new short prefix (3-5 uppercase chars) from the phase's feature domain. The prefix represents a category of capabilities, not the phase name.
- Keep consistent with domain conventions — look at how existing prefixes relate to their categories for style guidance.

**Requirement derivation:**
- Read all locked decisions in CONTEXT.md holistically
- Derive requirements that are **specific, testable, and atomic** — each captures one verifiable capability or behavior
- Requirements should describe what the system does or what becomes true, not restate implementation decisions verbatim
- The number of requirements should match the scope — a phase with 3 decisions might produce 5 requirements, a phase with 15 decisions might produce 20+. Let the content drive the count.
- Number sequentially within the chosen prefix, continuing from the last used number (e.g., if `INST-12` exists, start at `INST-13`)

**Determine category section placement:**
- If continuing an existing prefix: add requirements to the existing `### Category` section in REQUIREMENTS.md
- If using a new prefix: create a new `### Category Name` section under `## v1 Requirements`

**Write requirements:**

1. Add requirement definitions to REQUIREMENTS.md — append to the appropriate `### Category` section (or create a new one before the `## v2 Requirements` or `## Traceability` section). Format: `- [ ] **PREFIX-NN**: Description`

2. Add traceability rows to the `## Traceability` table. Format: `| PREFIX-NN | Phase {N} | Pending |`

3. Update the `**Coverage:**` counts at the bottom of the Traceability section.

4. Update ROADMAP.md — replace `Requirements: TBD` (or add a `**Requirements**:` line) with the comma-separated list of generated IDs.

5. Commit:
```bash
git add .planning/REQUIREMENTS.md .planning/ROADMAP.md && git commit -m "docs(phase-{N}): generate requirement IDs from context decisions"
```

6. Print the generated requirements to console:
```
Requirements generated for Phase {N}: {count} IDs ({first_id}..{last_id})

### {Category}
- PREFIX-NN: description
- PREFIX-NN: description
...
```

**5d. Check coverage (IDs exist case):**

Compare the CONTEXT.md decisions against the existing requirement descriptions for this phase. Look for decisions that represent capabilities or behaviors not captured by any existing requirement.

**If all decisions are covered:** Print confirmation and continue.
```
Requirements: {count} IDs verified for Phase {N}
```

**If uncovered decisions found:**

Generate additional requirement IDs for the uncovered decisions, continuing the numbering sequence of the existing prefix.

Write the new requirements to REQUIREMENTS.md (definitions + traceability rows), update ROADMAP.md Requirements line, commit, and print:
```
Requirements: {existing_count} existing + {new_count} added for Phase {N}

Added:
- PREFIX-NN: description
- PREFIX-NN: description
```

## 6. Delegate to gsd:plan-phase

Pass the phase number and all pass-through flags:

```
Skill("gsd:plan-phase", "{phase} {pass-through-flags}")
```

</process>

<important_notes>
- Deviation check (Steps 2-4) is read-only — it only reads SUMMARY.md and CONTEXT.md
- Requirement check (Step 5) writes to REQUIREMENTS.md and ROADMAP.md only when IDs are missing or incomplete
- Requirement generation uses LLM judgment to derive proper GSD requirements from locked decisions — requirements are specific testable capabilities, not restated implementation decisions
- No user approval is needed for requirement generation — the decisions are already locked in CONTEXT.md, requirements are a logical formalization
- Conflict detection is a best-effort heuristic — LLM judgment determines whether a deviation contradicts a locked decision
- Pass-through flags are forwarded verbatim to `gsd:plan-phase` (e.g., `--skip-research`, `--auto`, `--prd path`)
- The user can always use `gsd:plan-phase` directly for vanilla behavior without pre-flight checks
- When "Discuss first" is chosen, `mg:discuss-phase` is invoked (which itself does deviation scanning), so the user gets the full deviation-aware discussion flow
</important_notes>
