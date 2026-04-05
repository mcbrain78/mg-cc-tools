# /mg:discuss-milestone — GSD Batch Milestone Discussion

---
name: mg:discuss-milestone
description: Invoke only via /mg:discuss-milestone — batches all phase discussions with cross-cutting themes first
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

Methodology snapshot: `{MG_INSTALL_METHODOLOGY_SNAPSHOT}`
</context>

<process>

## Step 1: Methodology Drift Check

Before proceeding, verify that the GSD discuss-phase methodology hasn't changed since this command was designed.

1. Read the stored methodology snapshot at `{MG_INSTALL_METHODOLOGY_SNAPSHOT}`
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

**Classify each phase by lifecycle stage:**

For each phase, gather signals:
- `Glob: .planning/phases/{padded}-*/*-SUMMARY.md` → has execution history
- `Glob: .planning/phases/{padded}-*/*-PLAN.md` → has been planned
- `Glob: .planning/phases/{padded}-*/*-CONTEXT.md` → has context
- Check ROADMAP.md for the phase's plan checkboxes → count `[x]` vs `[ ]`
- If CONTEXT.md exists, read its `**Source:**` line to determine origin

**Classification rules (applied in order — first match wins):**

| Stage | Detection | Default |
|---|---|---|
| **Completed** | All ROADMAP plan checkboxes are `[x]`, or all plans have matching SUMMARYs | Exclude |
| **Executing** | Some SUMMARYs exist but not all plans have SUMMARYs | Exclude |
| **Planned** | Has PLANs but no SUMMARYs | Exclude |
| **Discussed** | Has CONTEXT.md with `**Source:**` containing "milestone discussion" or "discuss-phase" | Exclude |
| **Has context (undiscussed)** | Has CONTEXT.md with `**Source:**` containing "Context import", or `**Source:**` line missing/unrecognized | **Include** |
| **Fresh** | No CONTEXT.md | **Include** |

**Source detection heuristic** (read `**Source:**` line from CONTEXT.md):
- Contains "Context import" → imported
- Contains "milestone discussion" → milestone-discussed
- Contains "discuss-phase" → individually discussed
- Missing or unrecognized → treat as imported (conservative — include by default)

**Present status table and selection via AskUserQuestion:**

First, display the status table:

```
## Milestone: {name} — {total} phases

  Phase {N}: {Name}        {STAGE_LABEL} — {inclusion_note}
  Phase {M}: {Name}        {STAGE_LABEL} — {inclusion_note}
  ...

Default: Phases {list of included phase numbers}
```

Where `{STAGE_LABEL}` / `{inclusion_note}` examples:
- `EXECUTING (5/6 plans) — auto-excluded`
- `COMPLETED — auto-excluded`
- `PLANNED — auto-excluded (warning: discussing may conflict with existing plans)`
- `discussed — auto-excluded`
- `imported context — included`
- `fresh — included`

Then present via AskUserQuestion:
- header: "Phases"
- question: "Which phases should we discuss?"
- options:
  - "Default (Recommended)" — "Discuss phases classified as 'imported context' + 'fresh' ({included_count} phases)"
  - "Include started phases" — "Also add Executing/Completed/Planned phases (⚠️ these have locked or in-progress decisions)"
  - "Select specific" — "Let me choose from the full phase list"

**If "Include started phases":** Add all Executing/Completed/Planned phases to the selection. Warn inline: "Including phases with existing plans or execution history — decisions from those phases will be treated as revisable during discussion."

**If "Select specific":** Present full phase list with multiSelect for user to pick, showing stage labels.

Store the selected phase list for subsequent steps. Also store the full classification map (phase → stage) for use in Steps 2b, 3, 4, and 5.

## Step 2b: Load Existing Decisions from Selected Phases

For each selected phase that has an existing CONTEXT.md:

1. Read the `<decisions>` section
2. Extract concrete decisions — skip placeholders like "Claude's Discretion", "TBD", "All phase-specific details (not yet discussed)", or similar non-decision content
3. Store as `existing_decisions[phase_number] = [list of decisions]`

This feeds into Step 3 so cross-cutting discussion is informed by what's already decided.

## Step 3: Cross-Cutting Discussion (Pass 1)

Present all selected phase goals to the user as context, plus fixed constraints from excluded phases:

```
## Milestone: {name}

Phases to discuss:

1. **Phase {N}: {Name}** — {goal description}
2. **Phase {M}: {Name}** — {goal description}
...
```

**Fixed constraints from excluded phases:**

For each excluded phase classified as Completed or Executing:
1. Read its CONTEXT.md `<decisions>` section
2. Extract concrete decisions (skip placeholders)
3. Present as locked constraints:

```
### Fixed (already executing — decisions locked):
- **Phase {N}: {Name}** — {key decisions extracted from CONTEXT.md}

Cross-cutting decisions must be compatible with these locked decisions.
```

**Pre-existing decisions from selected phases with imported context:**

For selected phases that have existing decisions (from Step 2b):

```
### Pre-existing decisions (from imported context — open for revision):
- **Phase {N}: {Name}** — {decisions from existing_decisions[N]}
- **Phase {M}: {Name}** — {decisions from existing_decisions[M]}
...
```

```
Before discussing each phase individually, let's identify decisions that span multiple phases.
These must be compatible with the fixed constraints above.
```

**Apply the methodology snapshot's principles at MILESTONE scope:**

1. **Domain categorization:** What kinds of things are being built across this milestone?
   - Map each phase to its domain type (something users SEE, CALL, RUN, READ, or being ORGANIZED)

2. **Gray area identification:** What decisions span multiple phases?
   Focus on:
   - **Gaps** between existing decisions across phases
   - **Conflicts** between existing decisions that need resolution
   - **Missing cross-cutting concerns** not addressed by any phase's existing context
   - Shared infrastructure decisions (database schema, API design, state management)
   - Consistency decisions (UI patterns, naming conventions, error handling)
   - Dependency decisions (execution order assumptions, shared data contracts)
   - Boundary decisions (where does Phase A end and Phase B begin?)

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

If merging with existing CONTEXT.md (phase has imported or prior context):
1. Read existing `<decisions>` section
2. For each cross-cutting decision, check if it's already captured by an existing decision (semantic match — same topic and same conclusion)
3. **Already captured** → skip (don't duplicate)
4. **New decision** → add under `### Cross-Cutting Decisions` subsection within `<decisions>`, before `### Claude's Discretion`
5. **Contradicts existing decision** → add with `⚠️ CONFLICTS WITH: "{existing decision text}"` annotation so the user can resolve during per-phase discussion (Step 5)
- Update source line to: `**Source:** Merged — {original source} + milestone discussion (cross-cutting pass)`
- Preserve all other existing sections

Write to `{phase_dir}/{padded_phase}-CONTEXT.md`.

## Step 5: Per-Phase Discussion (Pass 2)

After the cross-cutting pass (Step 4) writes/merges CONTEXT.md files, assess each selected phase's context completeness before deciding whether to discuss individually.

**5a. Assess each phase's context completeness:**

For each selected phase, evaluate:
- Count concrete decisions in `<decisions>` (excluding placeholders like "Claude's Discretion", "TBD")
- Check if `<specifics>` has concrete content (not just "No specific requirements yet")
- Check if `<deferred>` was populated with real content
- Check for `⚠️ CONFLICTS WITH:` markers from the merge step
- Estimate decision coverage: do the decisions address the major gray area categories (data contracts, error handling, naming, boundaries)?

**5b. Present recommendation via AskUserQuestion (multiSelect: true):**

```
header: "Per-phase"
question: "Cross-cutting pass complete. Which phases need individual discussion?"
```

Options (one per selected phase, with recommendation):
- `"Phase {N}: {Name} (Recommended: skip)"` — `"{decision_count} decisions already captured, no conflicts. Cross-cutting pass added {new_count} new decisions."`
- `"Phase {M}: {Name} (Recommended: discuss)"` — `"Rich context but ⚠️ {conflict_count} conflict(s) with Phase {X}. Needs resolution."`

**Recommendation logic:**
- **Recommend discuss** if: conflicts exist (`⚠️`), `<specifics>` is empty/placeholder, decision count < 5, or coverage gaps detected
- **Recommend skip** if: no conflicts, `<specifics>` populated, decision count >= 5, and coverage looks adequate

**5c. For phases the user selects for discussion:**

First, check context window usage. Estimate context usage based on conversation length so far.

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

Then invoke per-phase discussion with enhanced context:

```
Skill("gsd:discuss-phase", "{phase} --check-remaining \"Milestone-level cross-cutting decisions and imported context decisions are already captured. Focus on gaps, unresolved conflicts (marked ⚠️), and phase-specific gray areas not covered by existing decisions.\"")
```

After `gsd:discuss-phase` completes, verify the CONTEXT.md was enriched (read it and check that phase-specific decisions were added beyond the cross-cutting bootstrap).

**Important:** `gsd:discuss-phase` will emit its own "Next Up" boilerplate suggesting `/gsd:plan-phase` for the phase it just discussed. Immediately override this with a milestone-context message:

```
---
*(Per-phase discussion complete for Phase {N}. Returning to milestone discussion — ignore the "Next Up" suggestion above.)*
---
```

Continue to next selected phase.

**5d. For phases the user skips:** No action — their CONTEXT.md already has cross-cutting decisions merged in from Step 4.

## Step 6: Summary

After all phases have been discussed:

**Determine first plannable phase:** Scan all milestone phases in order. Find the first phase that has a CONTEXT.md but no PLAN.md files (i.e., discussed but not yet planned). This may differ from the phase just discussed — e.g., if Phase 4 was just discussed but Phase 2 is the first that needs planning, suggest Phase 2.

```
## Milestone Discussion Complete: {milestone_name}

### CONTEXT.md Files
{For each phase in milestone order:}
- Phase {N}: {name} — {phase_dir}/{padded}-CONTEXT.md
  - {count} cross-cutting decisions
  - {count} phase-specific decisions
  - Status: {stage from Step 2 classification}

### Summary
- Cross-cutting decisions: {total count}
- Phase-specific decisions: {total count}
- Phases discussed: {count}/{total}

---

## Next Steps

- `/mg:plan-phase {first_plannable_phase}` — plan Phase {first_plannable_phase}: {name} (deviation-aware)
- `/gsd:plan-phase {first_plannable_phase}` — vanilla planning

/clear first → fresh context window

---
```

</process>

<important_notes>
- The methodology snapshot at `{MG_INSTALL_METHODOLOGY_SNAPSHOT}` is the baseline this command was designed for. If drift is detected, the snapshot is NOT updated at runtime.
- Cross-cutting decisions use the SAME decision format as `gsd:discuss-phase` — downstream agents (researcher, planner) treat them identically.
- Bootstrap CONTEXT.md files are intentionally minimal — they contain only cross-cutting decisions and mark everything else as "Claude's Discretion" until the per-phase pass enriches them.
- The per-phase pass uses `--check-remaining` so `gsd:discuss-phase` doesn't re-ask about cross-cutting decisions that are already locked.
- Context compaction between phases is offered, not forced. GSD's `load_prior_context` step in discuss-phase handles reloading what's needed.
- This command does NOT modify GSD files — it only writes standard CONTEXT.md files that GSD already understands.
- Phase lifecycle classification uses a first-match-wins cascade: Completed > Executing > Planned > Discussed > Has context (undiscussed) > Fresh. This ensures phases with execution history are never accidentally re-discussed.
- The `**Source:**` line in CONTEXT.md is the key signal for distinguishing imported context (needs discussion) from milestone-discussed context (already discussed). Missing or unrecognized Source lines are treated conservatively as imported.
- Decisions from Completed/Executing phases are presented as locked constraints during cross-cutting discussion — they cannot be changed, only accommodated.
- The `⚠️ CONFLICTS WITH:` annotation in merged CONTEXT.md files is a deferred resolution marker — the conflict is flagged but not resolved until per-phase discussion (Step 5) or manual review.
</important_notes>
