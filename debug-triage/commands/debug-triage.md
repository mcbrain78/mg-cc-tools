# Debug Triage

---
name: mg:debug-triage
description: Analyze bug holistically before fixing - maps full data flow, identifies all break points, then routes to debug or phase
argument-hint: [symptom description]
allowed-tools:
  - Read
  - Write
  - Bash
  - Task
  - Glob
  - Grep
---

<objective>
Triage bugs by mapping the full affected subsystem before committing to a fix. Prevents the pattern of fixing one symptom only to discover the next.

**Why this exists:** `gsd:debug` hunts for a single root cause and fixes it. But after schema changes or pipeline rewrites, bugs often have multiple interconnected break points. This skill maps the entire data flow first, identifies ALL issues, then routes to the right tool.

**This skill does not modify application code.** It produces a situation report and routing recommendation. The depth of follow-up investigation depends on the route: debug gets detailed fix guidance, phases get a context handoff for `/gsd:discuss-phase`.
</objective>

<branch_rule>
**CRITICAL: Stay on the current branch.** Do NOT checkout main, do NOT create a new branch, do NOT create a PR. The bug is being observed on the current branch — all investigation, commits, and fixes happen here. When spawning `/gsd:debug` or any subagent, pass this instruction explicitly: "Stay on the current branch. Do NOT checkout main or create a new branch/PR."
</branch_rule>

<context>
User's symptom: $ARGUMENTS

**Routing targets:**
- `/gsd:debug` - For single, isolated issues (passes enriched context to debugger)
- `/gsd:add-phase` or `/gsd:insert-phase` - For multiple interconnected issues that need planned fixes (see Step 6 for which to use)
- Manual investigation - When the analysis needs user domain knowledge to interpret
</context>

<process>

## Step 1: Gather Symptom Context

If `$ARGUMENTS` is empty or vague, ask the user (as normal text, not AskUserQuestion):
1. What's the symptom? (what you observe)
2. What should happen instead?
3. Which part of the system is affected? (e.g., archetype scoring, memo generation, KPI loading)

If `$ARGUMENTS` provides enough context, proceed directly.

## Step 2: Identify the Affected Subsystem

Based on the symptom, identify which pipeline stage(s) and data flow are involved.

Use Glob and Grep to quickly locate the entry points:
- Pipeline steps in `src/pipeline/`
- Flow orchestration in `src/flows/`
- Services in `src/services/`
- Models/schema in `src/models/`
- UI triggers in `src/ui/`

Build a mental model of: **input → transformations → output** for the affected area.

## Step 3: Understand Domain Correctness

**CRITICAL: Before tracing code, understand what "correct" means from the domain perspective.**

The most common triage failure is tracing code flow without understanding the domain configuration that defines correctness. Code that looks "wrong" (e.g., passing unfiltered data) may be correct by design, and code that looks "fine" may be missing a domain-required transformation.

Read the **domain artifacts** that govern the affected subsystem:
- **Prompt templates** (`prompts/*.yaml`, `prompts/*.md`) — What data fields does the prompt expect? What does `mapped_data_fields` specify?
- **Rulesets / config files** (`prompts/*.json`, `src/ruleset/`) — What fields do rules reference? Does the system self-select what it needs, or does it rely on pre-filtered input?
- **Schema definitions** (`src/db/models.py`) — What relationships exist? What's stored vs. computed?
- **Output schemas** (`prompts/*_out_schema.json`) — What does "correct output" look like?

For each subsystem touched by the symptom, answer:
1. **What data should enter?** (defined by config, not by code)
2. **What transformation is required?** (filtering, mapping, formatting — defined where?)
3. **Does the subsystem self-select its data or rely on pre-filtered input?** (A ruleset that only accesses fields it references is fundamentally different from an LLM prompt that receives everything you send it)

Document a **"Correctness Spec"** — a short summary of what correct behavior looks like for each subsystem, derived from the domain artifacts (not from the code).

## Step 4: Spawn Data Flow Mapper

Spawn an Explore agent (subagent_type="Explore", thoroughness="very thorough") to trace the complete data flow. The prompt MUST include the Correctness Spec from Step 3.

```markdown
## Task: Map Data Flow for Bug Triage

**Reported symptom:** {symptom_description}
**Expected behavior:** {expected}
**Affected area:** {subsystem identified in step 2}

### Correctness Spec (from domain artifacts)

{Include the correctness spec from Step 3 here — what data should enter each subsystem, what transformations are required, and whether the subsystem self-selects data or relies on pre-filtered input. This is the ground truth for evaluating whether code is correct.}

### What to do

Trace the COMPLETE data flow for {affected_area} from entry point to final output.
Do NOT stop at the first anomaly — map the entire chain.

**IMPORTANT:** Evaluate each stage against the Correctness Spec above, not just against "does data flow through." A stage that passes all data is only a bug if the downstream consumer doesn't self-select what it needs. A stage that filters data is only correct if it filters to the right set as defined by domain config.

For each stage in the flow, document:
1. **Function/method name** and file location
2. **Input:** What data enters this stage (type, source, how it's fetched)
3. **Transformation:** What happens to the data
4. **Output:** What data leaves this stage
5. **Handoff:** How data is passed to the next stage (same session? new session? parameter? relationship?)
6. **Correctness check:** Compare actual behavior against the Correctness Spec. Is this stage doing what the domain requires? If not, explain the gap.

### Specific things to check
- **Session boundaries:** Are DB sessions shared or independent between stages? Can one stage see another's uncommitted writes?
- **Data filtering/mapping:** If data should be filtered or transformed per the Correctness Spec, is the filter applied? With correct criteria matching the domain config?
- **Schema alignment:** Do the model relationships and foreign keys match how the code accesses them?
- **Fallback paths:** Are there silent fallbacks that mask errors (e.g., returning empty data instead of raising)?
- **Recent changes:** Check git log for recent modifications to these files — what changed and could it have broken the flow?
- **Domain artifacts:** Read the actual config/prompt/ruleset files referenced in the code. Do NOT assume what they contain — read them.

### Output format

Return a structured report:

**CORRECTNESS SPEC SUMMARY:**
For each subsystem, what "correct" looks like per domain artifacts.

**DATA FLOW MAP:**
```
[Stage 1: name] → [Stage 2: name] → ... → [Final output]
```

**STAGE DETAILS:**
For each stage, the 6 points above (including correctness check against spec).

**IDENTIFIED ISSUES:**
Numbered list of ALL potential break points found, with:
- Location (file:line)
- What's wrong (citing which part of the Correctness Spec is violated)
- Confidence (HIGH/MEDIUM/LOW)
- Whether it could cause the reported symptom

**NON-ISSUES (looked suspicious but are correct):**
List anything that looks wrong at first glance but is actually correct per the domain spec. This prevents false positives.

**ISSUE RELATIONSHIPS:**
Are issues independent or connected? Would fixing one resolve others?
```

## Step 5: Present Situation Report

After the Explore agent returns, synthesize a **Situation Report** for the user:

```
--- TRIAGE REPORT ---

Symptom: {original symptom}
Subsystem: {affected area}
Data flow: [Stage 1] → [Stage 2] → ... → [Output]

Issues found: N

  1. {issue} — {file:line} [HIGH/MEDIUM/LOW]
  2. {issue} — {file:line} [HIGH/MEDIUM/LOW]
  ...

Relationships: {independent | cascading | interconnected}

---
```

## Step 6: Route Decision

Based on the number, nature, and scope of issues found, recommend a route. Present the recommendation and wait for the user to confirm before proceeding to Step 7 or Step 8.

### Single isolated issue → Debug
Recommend: `/gsd:debug`

Display:
```
Recommendation: Single isolated fix → /gsd:debug

This will deepen the analysis with fix guidance before spawning the debugger.
```

### Multiple independent issues (2-4) → Sequential Debug
Recommend: Sequential `/gsd:debug` calls

Display:
```
Recommendation: {N} independent issues → sequential /gsd:debug

Issues are independent — fixing one doesn't affect the others.
Each will get its own deepened analysis and debugger session.
```

### Interconnected issues or architectural problem → Phase
Recommend: Dedicated phase

Display:
```
Recommendation: {N} interconnected issues → dedicated phase

This needs coordinated fixes and architectural decisions that go beyond
individual bug fixes. The triage findings will be written as a bootstrap
for /gsd:discuss-phase to build on.
```

### Phase routing — which command

Choose based on milestone position:
- `/gsd:add-phase` — Adding at the **end** of the current milestone (no future phases to insert before). Creates the next integer phase number.
- `/gsd:insert-phase N` — Inserting **between** existing phases (e.g., between Phase 59 and 60 during active execution). Creates a decimal phase (59.1).

**Rule of thumb:** If the last phase in the milestone is already complete, use `/gsd:add-phase`. If you need to squeeze work between phases that haven't all executed yet, use `/gsd:insert-phase`.

### No clear issues found
Display:
```
Triage inconclusive — the data flow looks correct on paper.

Options:
1. Add runtime evidence — Run the failing scenario and share logs/output
2. Spawn debugger anyway — /gsd:debug with the data flow map as context
3. Investigate manually — Use the data flow map as a starting point
```

---

## Step 7: Deepen for Debug (debug route)

**When the user confirms the debug route**, assess whether the diagnosis from Steps 1-5 is sufficient to guide the debugger to a fix — not just to the bug.

### Sufficiency check

The debugger needs three things beyond diagnosis:
1. **Fix direction** — What should change? (e.g., "add a filter call here", "change this query to join on X")
2. **Constraints** — What must NOT change? (e.g., "the UCR scoring path is correct, don't touch it")
3. **Verification** — How will the debugger know the fix works? (e.g., "the rendered prompt should contain only 4 KPI fields")

If the data flow mapper already surfaced enough detail for all three, proceed directly to invoking `/gsd:debug`.

If not — e.g., the issue is clear but the fix direction requires understanding code you haven't read, or there are multiple valid fix approaches — **spawn a targeted Explore agent** to investigate the specific fix area:

```markdown
## Task: Investigate Fix Direction

**Issue:** {specific issue from triage}
**Location:** {file:line}
**What's wrong:** {gap between actual and correct behavior}

### What to investigate

{Targeted questions — e.g., "What does the archive record contain that could replace this column?", "How does the UI currently fetch this data and what would need to change?", "Are there other callers of this function that would break if we change the signature?"}

### Return

- **Recommended fix:** What to change and where
- **Alternative approaches:** If multiple valid options exist
- **Risks:** What could break
- **Verification:** How to confirm the fix works
```

### Invoke debugger

Once you have diagnosis + fix direction + constraints + verification, invoke `/gsd:debug` with an enriched description that gives the debugger a complete picture. **Always include the branch rule in the description passed to the debugger.**

```
/gsd:debug

BRANCH RULE: Stay on the current branch. Do NOT checkout main, create a new branch, or open a PR. All commits go on the current branch.

Issue: {concise description}

Data flow: {abbreviated flow showing where the break is}

Root cause: {what's wrong, file:line, mechanism}

Fix direction: {what should change — be specific about functions, parameters, return values}

Constraints:
- {what must NOT change and why}

Verification:
- {how to confirm the fix works}

Correctness reference:
- {relevant parts of the Correctness Spec from Step 3}
```

For sequential debug (multiple independent issues), repeat this step for each issue before invoking each `/gsd:debug`.

---

## Step 8: Write bootstrap.md (phase route)

**When the user confirms the phase route**, create the phase (via `/gsd:add-phase` or `/gsd:insert-phase`), then write the triage findings as a bootstrap file. The bootstrap is a **context handoff** — it gives `/gsd:discuss-phase` a head start so it doesn't rediscover what the triage already found.

**Why bootstrap.md and not CONTEXT.md:** CONTEXT.md is a GSD framework artifact with specific semantics (produced by `/gsd:discuss-phase`, consumed by planner/researcher/checker). Using it couples the triage to GSD internals that may change. bootstrap.md is our own convention — decoupled and future-proof.

**File location:** `{phase_dir}/{phase_num}-bootstrap.md`

### What to include

The bootstrap documents **what the triage found**, not how to fix it. Fix directions and architectural decisions are `/gsd:discuss-phase`'s job. Include:

- **Goal** — What this phase addresses, in 2-3 sentences
- **Origin** — The symptom that triggered the triage and how it led to this phase
- **Diagnosed issues** — Each issue with root cause, mechanism, exact file:line references, and code snippets where helpful
- **Data flow map** — The abbreviated flow from Step 5 showing where breaks occur
- **Non-issues** — Things that look wrong but are correct by design (prevents discuss-phase from "fixing" working code)
- **Scope signal** — Why this needs a phase rather than a quick fix (interconnected issues, architectural decisions needed, multiple subsystems affected)

**Do NOT include:**
- Fix directions or implementation plans (that's discuss-phase → plan-phase)
- Generic template sections with no content
- Decisions that require user input (flag them as open questions for discuss-phase)

See existing examples for the expected style:
- `.planning/phases/47-*/47-bootstrap.md` — field rename with exact before/after mapping
- `.planning/phases/55-*/55-bootstrap.md` — parallel processing fix with 3 interacting root causes
- `.planning/phases/46-*/46-bootstrap.md` — UI bugs with prompt structure analysis

### Output

After writing, display copy-pasteable command blocks:
```
bootstrap written: {phase_dir}/{phase_num}-bootstrap.md

Next steps (copy each after /clear):

1. /gsd:discuss-phase {phase_num} — take {phase_dir}/{phase_num}-bootstrap.md into consideration. It contains the triage analysis with diagnosed issues, data flow map, and scope justification.

2. /gsd:plan-phase {phase_num} — take {phase_dir}/{phase_num}-bootstrap.md into consideration. It contains the triage analysis with diagnosed issues, data flow map, and scope justification.
```

</process>

<success_criteria>
### Always (Steps 1-6)
- [ ] Symptom understood with enough context to identify affected subsystem
- [ ] Domain artifacts read and Correctness Spec established before code tracing
- [ ] Complete data flow mapped from entry point to output
- [ ] Each stage evaluated against the Correctness Spec (not just "does data flow")
- [ ] Non-issues explicitly identified (things that look wrong but are correct by design)
- [ ] ALL actual break points identified (not just the first one)
- [ ] Issue relationships assessed (independent vs. cascading vs. interconnected)
- [ ] Situation report presented to user
- [ ] Routing recommendation made with clear rationale
- [ ] No application code modified (only planning artifacts written)

### Debug route (Step 7)
- [ ] Fix direction identified (what to change, where)
- [ ] Constraints documented (what must NOT change)
- [ ] Verification criteria defined (how to confirm fix works)
- [ ] Deepened analysis spawned if diagnosis alone was insufficient
- [ ] `/gsd:debug` invoked with enriched context (not just the symptom)

### Phase route (Step 8)
- [ ] bootstrap.md written to phase directory as context handoff
- [ ] Bootstrap contains diagnosis and scope signal, not fix directions
- [ ] Copy-pasteable `/gsd:discuss-phase` command displayed
</success_criteria>
