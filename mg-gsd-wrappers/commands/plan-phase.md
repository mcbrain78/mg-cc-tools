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
  - Agent
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

**3a. Find prior phase SUMMARY.md files:**

Glob for `.planning/phases/*-*/*-SUMMARY.md`. Filter results to phases where the leading number (digits before the first `-` in the directory name) is within the milestone range AND less than the current phase number.

**3b. Read SUMMARY.md files:**

For each matching SUMMARY.md file:
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

Glob for `.planning/phases/*-*/*-CONTEXT.md`. Filter results to phases within the milestone range AND less than the current phase number. Read the `<decisions>` sections from each.

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
- Glob for `.planning/phases/{padded}-*/*-CONTEXT.md` and read the `<decisions>` section

**If no CONTEXT.md exists for this phase:** Skip to Step 6 — nothing to derive requirements from.

**5b. Determine current state:**

- **If `Requirements: TBD` or the Requirements line is missing:** Phase has no requirement IDs → go to Step 5c
- **If requirement IDs exist:** Phase has IDs → go to Step 5d

**5c. Generate requirements (TBD case):**

Use a two-phase generate-then-curate pattern to derive right-sized requirements. Implementation details belong in CONTEXT.md; requirements describe user-observable capabilities.

**Prefix selection:**
- Scan existing requirement categories in REQUIREMENTS.md for a prefix that fits this phase's domain. For example, if the phase is install-related and `INST-` already exists, continue with `INST-`.
- If no existing prefix fits, derive a new short prefix (3-5 uppercase chars) from the phase's feature domain. The prefix represents a category of capabilities, not the phase name.
- Keep consistent with domain conventions — look at how existing prefixes relate to their categories for style guidance.

**Derive requirements (consolidator subagent):**

Spawn a single Agent subagent (subagent_type: "general-purpose") that generates and curates requirements, returning only the final curated list. This keeps the exhaustive candidate list and curation reasoning out of the orchestrator's context.

Prompt for the consolidator:

```
You are a requirement consolidator.

CRITICAL INSTRUCTION: You MUST use the Agent tool to spawn a generator subagent in Step 1.
Do NOT read the CONTEXT.md file yourself. Do NOT generate candidates yourself.
The entire point of this architecture is context isolation — the generator's exhaustive
candidate list must never appear in your context. You only see the generator's final output
via the Agent tool return value, then you curate it.

## Step 1: Generate candidates

Use the Agent tool to spawn a subagent with this prompt:
"Read the file {GENERATOR_PROMPT} and follow its instructions using {context_path} as the context file."

Wait for the agent to return. Its output is the tagged candidate list.

CRITICAL INSTRUCTION: Do NOT use the Read tool on {context_path}. Only the generator reads it.

## Step 2: Curate

The generator is an implementor — it sticks close to code and tends to tag internal mechanisms as capabilities. Treat its tags as hints, not verdicts.

Apply three quality gates. A requirement must pass ALL THREE:

1. **Externally observable** — verifiable by examining outputs or artifacts, not source code
2. **Implementation-independent** — still meaningful after a complete rewrite
3. **Independently meaningful** — not a sub-point, refinement, or negation of another requirement

Tag guidance:
- `capability` → usually passes, but check gate 3 — merge capabilities that describe the same behavior at different granularities
- `constraint` → keep only if cross-cutting (2+ capabilities). Otherwise fold into the parent capability
- `detail` → drop. The detail lives in CONTEXT.md for implementors

Multiple candidates may aggregate into one requirement when they describe facets of the same observable behavior.

Target count: distinct capabilities + cross-cutting constraints. A phase with 15 decisions typically yields 6-10 requirements, not 12+.

## Step 3: Return

CRITICAL INSTRUCTION: Output ONLY the final curated list below. Do NOT include the
candidate list, do NOT include a curation table, do NOT explain your reasoning.
The orchestrator must receive a clean list with zero analysis residue.

- Description of requirement 1
- Description of requirement 2
- ...
```

Replace `{context_path}` with the actual CONTEXT.md path before spawning. The path `{GENERATOR_PROMPT}` is resolved at install time by install.sh

The consolidator returns the curated list. Number the requirements sequentially within the chosen prefix, continuing from the last used number (e.g., if `INST-12` exists, start at `INST-13`).

**Determine category section placement:**
- If continuing an existing prefix: add requirements to the existing `### Category` section in REQUIREMENTS.md
- If using a new prefix: create a new `### Category Name` section under `## v1 Requirements`

**Write requirements:**

1. Add requirement definitions to REQUIREMENTS.md — append to the appropriate `### Category` section (or create a new one before the `## v2 Requirements` or `## Traceability` section). Format: `- [ ] **PREFIX-NN**: Description`

2. Add traceability rows to the `## Traceability` table. Format: `| PREFIX-NN | Phase {N} | Pending |`

3. Update the `**Coverage:**` counts at the bottom of the Traceability section.

4. Update the `*Last updated:*` footer in REQUIREMENTS.md with today's date and trigger (e.g., `*Last updated: 2026-03-19 after Phase 8 requirement generation*`).

5. Update ROADMAP.md — replace `Requirements: TBD` (or add a `**Requirements**:` line) with the comma-separated list of generated IDs.

6. Commit:
```bash
git add .planning/REQUIREMENTS.md .planning/ROADMAP.md && git commit -m "docs(phase-{N}): generate requirement IDs from context decisions"
```

7. Print the generated requirements to console:
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

Write the new requirements to REQUIREMENTS.md (definitions + traceability rows), update ROADMAP.md Requirements line, and commit:
```bash
git add .planning/REQUIREMENTS.md .planning/ROADMAP.md && git commit -m "docs(phase-{N}): add requirement IDs for uncovered decisions"
```

Print:
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
