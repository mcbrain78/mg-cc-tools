# GSD Phases from Concept

---
name: mg-temp:spec-gsd-phases
description: Analyze a concept doc and create GSD phases for the current milestone
argument-hint: "<source-file-path>"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Skill
---

<objective>
Read a concept doc (or design doc, scope doc), analyze its structure and dependencies, propose a phase breakdown for the current milestone, and create the phases via `gsd:add-phase`. This bridges the gap between having a concept spec and having GSD phases to plan against.

This command does NOT create CONTEXT.md files or generate requirements. It only creates phases in ROADMAP.md with goals. Downstream commands handle the rest:
- `mg-temp:spec-prepare-context` splits the concept content into per-phase files
- `mg-temp:spec-create-context` transforms those into CONTEXT.md (locked decisions)
- `mg:plan-phase` derives requirements from CONTEXT.md decisions
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<source-file-path>`

Examples:
- `docs/work-queue/todo/recursive-section-xml/concept.md`
- `docs/design/auth-overhaul.md`
</context>

<process>

## 1. Parse Arguments

Extract the source file path from `$ARGUMENTS`.

If missing:
```
ERROR: Source file path required.

Usage: /mg-temp:spec-gsd-phases <source-file-path>

Examples:
  /mg-temp:spec-gsd-phases docs/work-queue/todo/recursive-section-xml/concept.md
  /mg-temp:spec-gsd-phases docs/design/auth-overhaul.md
```
Exit.

## 2. Validate Inputs

**Read the source file.** If it doesn't exist or is empty:
```
ERROR: Source file not found or empty: <path>
```
Exit.

**Read `.planning/ROADMAP.md`.** If it doesn't exist:
```
ERROR: ROADMAP.md not found. An open milestone is required — run /gsd:new-milestone first.
```
Exit.

**Read `.planning/STATE.md`** if it exists — note the current milestone and latest phase number.

**Read `.planning/REQUIREMENTS.md`** if it exists — note existing requirement categories for context (the command won't generate requirements, but awareness of existing categories helps propose coherent phases).

**Scan the source file for local file references** (markdown links to other local files like `[text](relative/path.md)`). Read up to 5 referenced files to enrich understanding of the concept.

## 3. Analyze Concept

Read the source document carefully. Identify:

- **Scope units** — distinct deliverables, features, or capabilities that could stand alone
- **Dependency chains** — which parts must be built before others (e.g., a library before the scripts that use it, a data model before the operations on it)
- **Verification boundaries** — natural points where you can test/verify before moving on
- **Complexity clusters** — sections that are tightly coupled and should stay together vs sections that are independent

When determining phase boundaries, prioritize:
1. **Dependency order** — a phase's inputs must come from prior phases or already exist
2. **Testability** — each phase should produce something verifiable on its own
3. **Scope containment** — a phase should be completable without touching the next phase's concerns
4. **Size balance** — avoid one massive phase and several tiny ones

## 4. Propose Phase Breakdown

Present the proposal:

```
## Proposed Phases

Source: {source-file-path}
Milestone: {current milestone name from ROADMAP.md}

| # | Phase Name | Goal | Key Scope |
|---|-----------|------|-----------|
| 1 | {name} | {goal} | {what content/sections map here} |
| 2 | {name} | {goal} | {what content/sections map here} |
| ... | ... | ... | ... |

### Dependencies
- Phase 2 depends on Phase 1: {why}
- Phase 3 depends on Phase 2: {why}
- ...

### Notes
{Any observations about the breakdown — e.g., phases that could be parallelized, optional phases, or phases that are larger than others}
```

**Phase name rules:**
- 5-6 words maximum
- Concise verb-noun or noun-phrase style
- Match the style of existing phases in ROADMAP.md (e.g., "Foundation & Infrastructure", "Fix Verify Feedback Loop")

**Goal rules:**
- One sentence
- Specific and observable — describes what becomes true when the phase is done
- Feeds into `mg:plan-phase`'s requirement generation, so be precise

**Numbering in the table is relative (1, 2, 3...)** — actual GSD phase numbers are assigned by `gsd:add-phase` based on what already exists in the roadmap.

## 5. Approval

Use AskUserQuestion:
- header: "Phases"
- question: "Proposed {count} phases. How should I proceed?"
- options:
  - "Approve" — "Create these phases in ROADMAP.md"
  - "Adjust" — "I want to change the breakdown"
  - "Cancel" — "Don't create anything"

**If "Adjust":**

Ask the user what they want to change (freeform text, NOT AskUserQuestion). Common adjustments:
- Merge two phases into one
- Split a phase into two
- Reorder phases
- Rename a phase
- Change a goal

Update the proposal based on their feedback and re-present the table. Loop back to the AskUserQuestion approval prompt. Continue until the user approves or cancels.

**If "Cancel":**
```
Cancelled. No phases created.
```
Exit.

**If "Approve":** Continue to Step 6.

## 6. Create Phases

For each approved phase **sequentially** (one at a time, wait for each to complete before starting the next — ordering matters for phase numbering):

```
Creating phase {relative_number}/{total}: {phase name}...
```

Spawn an Agent subagent with this prompt (filling in `{phase_name}` and `{goal}`):

```
Create a GSD phase and set its goal. Follow these steps exactly:

1. Invoke Skill("gsd:add-phase", "{phase_name}") and follow the workflow it loads to completion.
2. After the phase is created, read .planning/ROADMAP.md and find the newly created phase entry.
   It will contain: **Goal:** [To be planned]
3. Edit ROADMAP.md to replace `[To be planned]` with: {goal}
4. Report back the phase number that was assigned.
```

**Why a subagent?** The `gsd:add-phase` Skill loads a workflow with its own completion output. Running it directly in the orchestrator causes the workflow's "done" template to interrupt the creation loop. The subagent contains the workflow naturally — the orchestrator only receives a result summary.

**Do NOT call `gsd-tools.cjs phase add` directly via Bash.** The Skill handles STATE.md updates that gsd-tools.cjs does not.

**Important:** Each agent must complete before the next starts — `gsd:add-phase` reads ROADMAP.md to determine the next phase number, so sequential execution is required. Do NOT launch agents in parallel.

After all phases are created, track the first and last phase numbers from the agent results.

## 7. Commit Goal Updates

```bash
git add .planning/ROADMAP.md && git commit -m "docs: set phase goals from concept analysis"
```

Note: `gsd:add-phase` already commits after each phase addition (the roadmap entry + directory creation). This commit only covers the goal text replacements.

## 8. Summary

```
## Phases Created: {count}

Source: {source-file-path}
Milestone: {current milestone name}

| Phase | Name | Goal |
|-------|------|------|
| {N} | {name} | {goal} |
| {N+1} | {name} | {goal} |
| ... | ... | ... |

---

## Next Steps

Split the concept into per-phase files and create CONTEXT.md for each phase:

  /mg-temp:spec-prepare-context {first_phase}-{last_phase} {source-file-path}

/clear first

---
```

</process>

<important_notes>
- This command creates phases with `Requirements: TBD`. Requirement generation happens later in `mg:plan-phase` (Step 5c) which derives REQ-IDs from CONTEXT.md decisions. This is the correct separation — phases exist before requirements are formalized.
- Phase numbers are assigned by `gsd:add-phase`, not by this command. The proposal table uses relative numbers (1, 2, 3) for readability; actual GSD numbers depend on existing phases in the roadmap.
- Goals are edited directly in ROADMAP.md after `gsd:add-phase` creates the entry. There is no gsd-tools command to set a goal — direct file editing is required.
- The analysis and adjustment loop runs in the orchestrator so the concept content stays in context. Phase creation uses subagents to contain the `gsd:add-phase` workflow output — preventing the workflow's completion template from interrupting the creation loop.
- This command does NOT modify REQUIREMENTS.md. It does NOT create CONTEXT.md files. It does NOT run spec-prepare-context or spec-create-context. It only creates phases and sets goals.
- The `gsd:add-phase` Skill updates both ROADMAP.md (via gsd-tools.cjs) and STATE.md (Roadmap Evolution). Calling gsd-tools.cjs directly skips the STATE.md update. Always use the Skill.
- Dependencies between proposed phases are noted in the proposal for the user's benefit, but `gsd:add-phase` sets a default `**Depends on:** Phase {N-1}`. If the dependency structure differs from simple sequential, the user should manually adjust ROADMAP.md after creation.
</important_notes>
