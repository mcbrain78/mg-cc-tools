# Spec Draft

---
name: mg:spec-draft
description: Formalize conversation context or idea file into a concept spec using the standard template
argument-hint: "[<source-file-path>]"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

<objective>
Take existing context — a raw idea file, sketch document, or the current conversation — and formalize it into a concept spec using the standard template. The primary job is to catch dangling paths, contradictions, and uncertainty *before* they become prose that downstream tools (mg:spec-improve, mg:spec-create-context) would treat as firm decisions.

This command does NOT make decisions. Research informs questions to the user; the user decides.
</objective>

<context>
Arguments: $ARGUMENTS

If a file path is provided, it is the source material to formalize.
If no arguments, work from the current conversation context.

Concept spec template: `{CONCEPT_TEMPLATE}`
</context>

<required_reading>
Read the concept spec template to understand the target structure:
{CONCEPT_TEMPLATE}
</required_reading>

<process>

## 1. Determine Source

**If `$ARGUMENTS` contains a file path:**
- Read the source file
- If the file doesn't exist or is empty, report the error and exit

**If no arguments:**
- Work from the current conversation context
- Summarize what you understand from the conversation so far and confirm with the user before proceeding

## 2. Context Extraction

Read the source material (file or conversation) carefully. For every claim, decision, intention, and open question, categorize it as one of:

- **Decided** — clear choice with reasoning present. The user has committed to this.
- **Leaning** — preference expressed without firm commitment or rationale. The user is inclined but hasn't locked it in.
- **Contradicted** — two statements in the source that cannot both be true. Something needs resolving.
- **Dangling** — exploration path that was started but never concluded. An idea was raised, discussed partially, and left hanging.
- **Assumed** — claim stated as fact without evidence or discussion. May be correct, but hasn't been validated.

Present a summary of this extraction to the user before proceeding:

```
## Context Extraction

### Decided ({count})
- {item}: {brief summary}
- ...

### Leaning ({count})
- {item}: {what the preference is, what's missing}
- ...

### Contradicted ({count})
- {item}: {the two conflicting statements}
- ...

### Dangling ({count})
- {item}: {what was started, where it trails off}
- ...

### Assumed ({count})
- {item}: {what's assumed, why it needs validation}
- ...
```

Use AskUserQuestion:
- header: "Context extraction"
- question: "Here's what I extracted from the source. Does this look right? Any items miscategorized?"
- options:
  - "Looks good" — "Proceed to research"
  - "Corrections needed" — "Let me fix some categorizations"

If corrections needed, adjust and re-confirm.

## 3. Targeted Research

For items categorized as Leaning, Contradicted, Dangling, or Assumed — launch a research subagent to gather codebase context that would help the user make decisions.

**Launch research subagent (Agent tool):**

```
You are researching the codebase to gather context for a concept spec
being drafted. Do NOT modify any files — only report findings.

Project root: {project root}

Items to research:
{paste the Leaning, Contradicted, Dangling, and Assumed items}

For each item, find:
1. Existing patterns or conventions in the codebase that are relevant
2. Dependencies or constraints the discussion may have missed
3. How similar situations were handled elsewhere in the project

Report findings per item. Be specific — cite file paths, function names,
and concrete patterns. Do not suggest decisions — only provide context.
```

Review the research results. For each item, note what context was found that could help the user decide.

## 4. Interactive Clarification

Present findings to the user organized by **template section**, not by extraction category. For each section of the concept spec template:

### Situation
State what context is already clear. If the source material has data or measurements, confirm them. If the Situation is thin, ask:
- What exists today that this concept addresses?
- Are there measurements or observations that ground the problem?

### Problem
State what problems are identified. Surface any **Assumed** items here — problems stated without evidence. Ask:
- Is this actually a problem? What's the evidence?
- Are there additional problems not captured in the source?

### Solution
Present **Decided** items that form the solution. For **Leaning** items, present the research context and ask the user to commit or reconsider. For **Contradicted** items, present both sides with research context and ask for resolution. For **Dangling** items, ask: include in the solution, exclude from scope, or defer as an Open Item?

Ask concrete questions with specific options informed by research:
- Not: "What do you think about X?"
- Instead: "X could work as A or B — A follows the pattern used in {file}, B avoids the constraint of {observation}. Which do you prefer?"

### Design Decisions
For choices that emerged as non-obvious during discussion, confirm the rationale. For **Leaning** items that the user firmed up in the Solution discussion, ask if they warrant a D-block (was the choice non-obvious enough?).

### Scope
Confirm what's in and what's out. Surface any **Dangling** items that were neither included in the solution nor explicitly excluded — they need to land in one bucket or the other.

### Verification
Ask how the user would know the implementation is correct. If the source material doesn't address this, propose verification approaches based on the solution design.

**Cadence:** Work through sections sequentially. After each section, check if the user wants to continue or has feedback on what was covered. Don't rush through all sections in one wall of questions.

## 5. Draft Generation

Write the concept spec using the template structure from `{CONCEPT_TEMPLATE}`.

- Fill every section based on the discussion outcomes
- **Decided** items and resolved **Leaning/Contradicted/Dangling** items become firm content in their respective sections
- Resolved choices with non-obvious rationale become Design Decision D-blocks
- Items that remain unresolved after Phase 4 go into **Open Items** with the options and dependencies clearly stated
- Include concrete examples (JSON, CLI, file structures) where they emerged during discussion

Determine the output name. Use AskUserQuestion:
- header: "Output"
- question: "What should I name this concept? This determines the directory: `docs/work-queue/todo/{name}/concept.md`"
- options: Suggest 2-3 slug-style names derived from the concept's title, plus "Other" for custom input

## 6. Consistency Check

Before presenting the draft, scan the written document for:

- **Design Decisions that contradict each other** — D-blocks whose choices are mutually incompatible
- **Solution sections inconsistent with Design Decisions** — solution describes behavior that a D-block rules out
- **Scope conflicts** — items implicitly required by the Solution but listed in "What does NOT get built"
- **Resolvable Open Items** — items in Open Items that actually have enough information from the discussion to be resolved (they should be Design Decisions instead)

If any findings: report them to the user alongside the draft and fix before finalizing.

If no findings: write the file.

## 7. Open Item Resolution

If the draft contains **any Open Items**, automatically offer to resolve them — do not wait for the user to ask.

Present each open item one at a time using AskUserQuestion. For each item:

1. **Think about your recommendation first.** Consider codebase patterns found during research, consistency with decisions already made, simplicity, and maintainability.
2. **Present numbered options with the recommended option first**, marked "(Recommended)". List 2-4 concrete options. Always include a final option to defer.

Format:

```
**Open Item {n}/{total}: {title}**

{Brief context — what the item is about and why it matters}

Options:
1. (Recommended) {option} — {rationale for recommending}
2. {option} — {tradeoff}
3. {option} — {tradeoff}
{n}. Defer — keep as Open Item for later resolution
```

Use AskUserQuestion:
- header: "Open Item {n}/{total}"
- question: the formatted block above
- options: the numbered options as a list

When the user picks an option (by number or description):
- Promote the resolved item to a Design Decision D-block in the draft
- Update any Solution/Scope sections affected by the resolution
- Move to the next open item

After all items are resolved or deferred, re-run the consistency check (Step 6) on any newly added D-blocks before proceeding to output.

## 8. Output

Write the concept spec to `docs/work-queue/todo/{name}/concept.md`.

If non-goals emerged during discussion (explicit scope exclusions that should persist across review rounds), create `docs/work-queue/todo/{name}/concept-NON-GOALS.md`.

```
## Draft complete

Output: docs/work-queue/todo/{name}/concept.md
{If non-goals file: "Non-goals: docs/work-queue/todo/{name}/concept-NON-GOALS.md"}

Decided: {count} items formalized
Open Items: {count} items still need resolution
Design Decisions: {count} D-blocks captured

---

## Next Steps

- `/mg:spec-improve docs/work-queue/todo/{name}/concept.md` — refine with fresh-eyes subagent review
{If open items remain: "- Resolve remaining Open Items before implementation"}

---
```

</process>

<important_notes>
- This command formalizes — it does NOT invent. Every decision in the output must trace back to user input during Phase 4. Research context informs questions but never writes decisions.
- The five extraction categories (Decided, Leaning, Contradicted, Dangling, Assumed) are a tool for the command to prioritize what to ask. They don't need to be visible in the final spec — they organize the discussion, not the document.
- When working from conversation context (no source file), extraction quality depends on conversation length and topic coverage. If the conversation is thin, Phase 4 will need to do more heavy lifting.
- The concept spec template is at `{CONCEPT_TEMPLATE}`. All sections must be present in the output. The LLM judges appropriate depth per section.
- Open Items are genuinely unresolved — they represent decisions the user could not or chose not to make during this session. They are NOT a parking lot for things the command didn't get to.
</important_notes>
