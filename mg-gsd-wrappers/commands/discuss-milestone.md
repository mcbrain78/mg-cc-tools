# Discuss Milestone

---
name: mg:discuss-milestone
description: Batch all phase discussions in one session — cross-cutting themes first, then per-phase details
argument-hint: "[milestone-name]"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Skill
---

<objective>
Discuss all phases in a milestone in a single session. First identifies cross-cutting themes that span multiple phases and resolves them, then bootstraps CONTEXT.md per phase with those decisions, and finally runs per-phase discussion to fill in phase-specific details.

This eliminates the context loss between separate discuss-phase sessions and ensures cross-cutting decisions are consistent across all phases.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `[milestone-name]` (optional — defaults to current milestone from STATE.md)

Methodology snapshot: `{METHODOLOGY_SNAPSHOT}`
</context>

<process>

## Step 1: Methodology Drift Check

Before proceeding, verify that the GSD discuss-phase methodology hasn't changed since this command was designed.

1. Read the stored methodology snapshot at `{METHODOLOGY_SNAPSHOT}`
2. Read the live GSD discuss-phase workflow at `.claude/get-shit-done/workflows/discuss-phase.md`
3. Extract these sections from the live file:
   - `<philosophy>` section
   - `<gray_area_identification>` section
   - `<scope_guardrail>` section
   - `<downstream_awareness>` section
   - Question design principles from `discuss_areas` step (the "4 questions then check" philosophy and "options should be concrete" guidelines)
4. Compare structural content against the snapshot (ignore examples and minor formatting differences)

**If identical:** Proceed to Step 2.

**If different:**

Analyze what changed and whether this command's cross-cutting discussion logic is still compatible.

Present via AskUserQuestion:
- header: "Drift"
- question: "GSD's discuss-phase methodology has changed since mg:discuss-milestone was last updated. {summary of what changed}. How should I proceed?"
- options:
  - "Continue anyway" — "Proceed using current methodology. This warning will appear until the command is updated in mg-cc-tools and reinstalled."
  - "Abort" — "Stop. I'll update the command first."

**If "Continue anyway":** Proceed to Step 2. Do NOT update the snapshot.

**If "Abort":**
```
Aborted. Update the snapshot and command in mg-cc-tools, then reinstall:

  cd <mg-cc-tools>
  # Update mg-gsd-wrappers/references/discuss-methodology.snapshot.md
  # Review mg-gsd-wrappers/commands/discuss-milestone.md
  ./mg-gsd-wrappers/install.sh --project <this-project>
```
Exit.

## Step 2: Identify Milestone Phases

Read `.planning/ROADMAP.md` and `.planning/STATE.md`.

**If milestone argument provided:** Find that milestone's section in ROADMAP.md.

**If no argument:** Read STATE.md to determine the current milestone, then find it in ROADMAP.md.

Extract:
- Milestone name and description
- Ordered list of phases with their numbers, names, and goal descriptions
- Phase number range (start and end)

**Check for existing CONTEXT.md files:**

For each phase, Glob for `.planning/phases/{padded}-*/*-CONTEXT.md`.

Present via AskUserQuestion:
- header: "Phases"
- question: "Milestone '{name}' has {total} phases ({with_context} already have context). Which phases should we discuss?"
- options:
  - "Undiscussed only (Recommended)" — "Discuss only phases without existing CONTEXT.md ({without_context} phases)"
  - "All phases" — "Re-discuss all {total} phases (existing context will be enriched)"
  - "Select specific" — "Let me choose which phases to include"

**If "Select specific":** Present phase list with multiSelect for user to pick.

Store the selected phase list for Steps 3-5.

## Step 3: Cross-Cutting Discussion (Pass 1)

Present all selected phase goals to the user as context:

```
## Milestone: {name}

Phases to discuss:

1. **Phase {N}: {Name}** — {goal description}
2. **Phase {M}: {Name}** — {goal description}
...

Before discussing each phase individually, let's identify decisions that span multiple phases.
```

**Apply the methodology snapshot's principles at MILESTONE scope:**

1. **Domain categorization:** What kinds of things are being built across this milestone?
   - Map each phase to its domain type (something users SEE, CALL, RUN, READ, or being ORGANIZED)

2. **Gray area identification:** What decisions span multiple phases?
   - Look for shared infrastructure decisions (database schema, API design, state management)
   - Look for consistency decisions (UI patterns, naming conventions, error handling)
   - Look for dependency decisions (execution order assumptions, shared data contracts)
   - Look for boundary decisions (where does Phase A end and Phase B begin?)

3. **Scope guardrail:** The milestone boundary is fixed — no new capabilities beyond the milestone's scope.

4. **Question design:** Use the same "4 questions then check" cadence, with concrete options.

**Present 3-5 cross-cutting gray areas via AskUserQuestion (multiSelect: true):**
- header: "Cross-cut"
- question: "Which cross-cutting themes do you want to discuss? These affect multiple phases."
- options: 3-4 cross-cutting gray areas, each with:
  - Specific label (not generic)
  - Description noting which phases it affects

**Discuss selected cross-cutting areas:**

For each selected cross-cutting area, use the standard discussion cadence:
1. Announce the area and which phases it affects
2. Ask up to 4 questions via AskUserQuestion with concrete options
3. After 4 questions, check: more questions or next area?
4. Capture decisions made

After all cross-cutting areas are discussed:

**Map decisions to phases:** For each cross-cutting decision, determine which phases it's relevant to. Store as `cross_cutting_decisions[phase_number] = [list of decisions]`.

## Step 4: Write Bootstrap CONTEXT.md Per Phase

For each phase in the selected list:

**4a. Resolve phase directory:**

Pad phase number to 2 digits. Glob for `.planning/phases/{padded}-*/`.

If no directory exists:
```bash
mkdir -p ".planning/phases/${padded_phase}-${phase_slug}"
```

**4b. Check for existing CONTEXT.md:**

If CONTEXT.md already exists (user chose "All phases" in Step 2): read existing content. The cross-cutting decisions will be merged into the existing `<decisions>` section.

**4c. Write bootstrap CONTEXT.md:**

```markdown
# Phase {N}: {Name} - Context

**Gathered:** {today's date}
**Status:** Ready for planning
**Source:** Milestone discussion (cross-cutting pass)

<domain>
## Phase Boundary

{Phase goal from ROADMAP.md}

</domain>

<decisions>
## Implementation Decisions

### Cross-Cutting Decisions
{For each cross-cutting decision relevant to this phase:}
- {Decision text} *(from milestone discussion)*

### Claude's Discretion
All phase-specific details (not yet discussed)

</decisions>

<specifics>
## Specific Ideas

No specific requirements yet — cross-cutting pass only.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within milestone scope.

</deferred>

---

*Phase: {padded}-{slug}*
*Context gathered: {date} via milestone discussion*
```

If merging with existing CONTEXT.md:
- Add cross-cutting decisions as a new subsection within `<decisions>`, before `### Claude's Discretion`
- Update header source to: `**Source:** Merged — original + milestone discussion (cross-cutting pass)`
- Preserve all other existing sections

Write to `{phase_dir}/{padded_phase}-CONTEXT.md`.

## Step 5: Per-Phase Discussion (Pass 2)

For each phase in the selected list (in order):

**5a. Check context window usage:**

Estimate context usage based on conversation length so far.

**If conversation is getting long (≥ 65% estimated context usage):**

Present via AskUserQuestion:
- header: "Context"
- question: "Context window is getting full. Auto-compact to free space before discussing Phase {N}?"
- options:
  - "Compact (Recommended)" — "Compress prior conversation. GSD's load_prior_context will restore what's needed."
  - "Continue" — "Keep going without compacting"

If accepted: use `/compact` or equivalent to compress conversation history. After compacting, the LLM only needs to know:
- Which phases have been discussed (from CONTEXT.md files already written)
- Which phase is next
- GSD's `load_prior_context` step handles reloading prior decisions

**5b. Invoke per-phase discussion:**

Since each phase now has a bootstrap CONTEXT.md with cross-cutting decisions, use `--check-remaining` to focus on phase-specific details:

```
Skill("gsd:discuss-phase", "{phase} --check-remaining \"Milestone-level decisions are already captured. Focus on phase-specific details and gray areas that need individual attention.\"")
```

**5c. Confirm enrichment:**

After `gsd:discuss-phase` completes, verify the CONTEXT.md was enriched (read it and check that phase-specific decisions were added beyond the cross-cutting bootstrap).

Continue to next phase.

## Step 6: Summary

After all phases have been discussed:

```
## Milestone Discussion Complete: {milestone_name}

### CONTEXT.md Files
{For each phase:}
- Phase {N}: {name} — {phase_dir}/{padded}-CONTEXT.md
  - {count} cross-cutting decisions
  - {count} phase-specific decisions

### Summary
- Cross-cutting decisions: {total count}
- Phase-specific decisions: {total count}
- Phases discussed: {count}/{total}

---

## Next Steps

- `/mg:plan-phase {first_phase}` — start planning the first phase (deviation-aware)
- `/gsd:plan-phase {first_phase}` — vanilla planning

---
```

</process>

<important_notes>
- The methodology snapshot at `{METHODOLOGY_SNAPSHOT}` is the baseline this command was designed for. If drift is detected, the snapshot is NOT updated at runtime.
- Cross-cutting decisions use the SAME decision format as `gsd:discuss-phase` — downstream agents (researcher, planner) treat them identically.
- Bootstrap CONTEXT.md files are intentionally minimal — they contain only cross-cutting decisions and mark everything else as "Claude's Discretion" until the per-phase pass enriches them.
- The per-phase pass uses `--check-remaining` so `gsd:discuss-phase` doesn't re-ask about cross-cutting decisions that are already locked.
- Context compaction between phases is offered, not forced. GSD's `load_prior_context` step in discuss-phase handles reloading what's needed.
- This command does NOT modify GSD files — it only writes standard CONTEXT.md files that GSD already understands.
</important_notes>
