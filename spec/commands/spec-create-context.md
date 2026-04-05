# Create Context

---
name: mg:spec-create-context
description: Generate a GSD CONTEXT.md from a design document, gap assessment, or scope doc — content becomes locked decisions for planning
argument-hint: "<phase-number> <source-file-path>"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
---

<objective>
Read a source document (gap assessment, design doc, scope doc, requirements brief) and generate a properly formatted GSD CONTEXT.md in the target phase directory. The source content is mapped into the `<decisions>` section so that downstream GSD agents (researcher, planner, checker) treat it as **locked user decisions** — non-negotiable implementation constraints.

This command produces a file that GSD already understands. No GSD patches required.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<phase-number> <source-file-path>`

Examples:
- `86 docs/work_queue/kpi-ingestion-v2/gap-assessment/phase-86-gaps.md`
- `3 docs/design/auth-requirements.md`

Template snapshot: `{MG_INSTALL_TEMPLATE_SNAPSHOT}`
</context>

<required_reading>
Read the GSD context template to understand the target format:
@./.claude/get-shit-done/templates/context.md
</required_reading>

<process>

## 1. Template Compatibility Check

Before generating anything, verify that the GSD context template hasn't changed since this command was last updated.

1. Read the stored template snapshot at `{MG_INSTALL_TEMPLATE_SNAPSHOT}`
2. Read the live GSD template at `.claude/get-shit-done/templates/context.md` (already loaded via required_reading)
3. Compare the **File Template** section and **guidelines** section between the two. Ignore the `<good_examples>` section — examples don't affect the structural format.

**If the structural sections are identical:**
```
Template check: compatible.
```
Proceed to Step 2.

**If different:**

Analyze the differences:
- Are sections renamed? (e.g., `<specifics>` → `<references>`)
- Are new sections added? (e.g., a new `<risks>` section)
- Are sections removed?
- Has the internal structure changed? (e.g., new required subsections within `<decisions>`)

Assess whether this command's process steps (Steps 8-9) are still compatible with the new template format.

Present findings via AskUserQuestion:
- header: "Template drift"
- question: "GSD's context template has changed since mg:spec-create-context was last updated. {summary of what changed and whether the command is still compatible}. How should I proceed?"
- options:
  - "Continue anyway" — "Proceed using the live template as guidance. This warning will appear on every run until the command is updated in mg-cc-tools and reinstalled."
  - "Abort" — "Stop. I'll update the command in mg-cc-tools first."

**If "Continue anyway":** Proceed to Step 2. Do **not** update the snapshot — it represents the version this command was designed for. Preserving it ensures the drift warning keeps appearing until the command source is properly updated and reinstalled.

**If "Abort":**
```
Aborted. Update the snapshot and command process in mg-cc-tools, then reinstall:

  cd <mg-cc-tools>
  # Update spec/references/context-template.snapshot with new template
  # Review spec/commands/spec-create-context.md process steps
  ./spec/install.sh --project <this-project>
```
Exit.

## 2. Parse Arguments

Extract from `$ARGUMENTS`:
- **Phase number** — first token (integer or decimal like `2.1`)
- **Source file path** — remaining tokens joined as the file path

If either is missing:
```
ERROR: Both phase number and source file path are required.

Usage: /mg:spec-create-context <phase-number> <source-file-path>

Examples:
  /mg:spec-create-context 86 docs/gaps/phase-86-gaps.md
  /mg:spec-create-context 3 docs/design/auth-requirements.md
```
Exit.

## 3. Validate Source File

Read the source file at the supplied path.

If the file doesn't exist or is empty:
```
ERROR: Source file not found or empty: <path>
```
Exit.

Store the source content for step 7.

## 4. Resolve Phase Directory

Pad the phase number to 2 digits (3 → "03", 86 → "86", 2.1 → "02.1").

Use Glob to find the phase directory (match the `.gitkeep` file GSD creates in each phase dir):
```
.planning/phases/{padded}-*/.gitkeep
```

Extract the directory path from the matched file (strip the `/.gitkeep` suffix).

If no match, create the directory using the phase name from ROADMAP.md:

1. Read `.planning/ROADMAP.md` and find the phase entry (e.g., `### Phase 3: Scan Pipeline`)
2. Derive the slug from the phase name (lowercase, replace non-alphanumeric with hyphens, trim)
3. Create the directory:
```bash
mkdir -p ".planning/phases/${padded}-${slug}"
```

If ROADMAP.md doesn't contain this phase either:
```
ERROR: Phase {N} not found in ROADMAP.md or .planning/phases/
```
Exit.

Extract from the directory name (whether found or created):
- `phase_dir` — the full relative path (e.g., `.planning/phases/86-flow-chain-completion`)
- `padded_phase` — the zero-padded number (e.g., "86")
- `phase_slug` — the slug portion after the number

## 5. Check for Existing CONTEXT.md

Use Glob to check:
```
{phase_dir}/*-CONTEXT.md
```

**If exists:**

Use AskUserQuestion:
- header: "Existing context"
- question: "Phase {N} already has a CONTEXT.md. How should I handle the source document?"
- options:
  - "Overwrite" — Replace existing CONTEXT.md entirely with content from the source document
  - "Merge" — Append the source document's decisions to the existing CONTEXT.md's `<decisions>` section
  - "Abort" — Cancel, keep existing CONTEXT.md unchanged

If "Abort": Exit.
If "Merge": Read the existing CONTEXT.md for use in step 8.

**If doesn't exist:** Continue.

## 6. Extract Phase Goal from Roadmap

Read `.planning/ROADMAP.md`.

Find the entry for Phase {N} and extract the phase goal text. This goes into the `<domain>` section.

If ROADMAP.md doesn't exist or the phase isn't found, use the phase directory name as a fallback description.

## 7. Read Referenced Documents

Scan the source document for markdown links to other local files:
- `[link text](relative/path.md)`
- `[link text](../sibling/path.md)`

For each link that points to a local file (not a URL):
- Resolve the path relative to the source file's directory
- Read the referenced file
- Note which sections of the source document reference it

This enriches the context — gaps that say "Design: [08-ingestion-flows.md](../08-ingestion-flows.md) section 4" can include the relevant design spec content.

**Limit:** Read at most 5 referenced files to keep context manageable. Prioritize files that are directly referenced by decision items.

## 8. Generate CONTEXT.md

Follow the template format from the required_reading. Create the CONTEXT.md with these sections:

### Header
```markdown
# Phase {N}: {Phase Name} - Context

**Gathered:** {today's date}
**Status:** Ready for planning
**Source:** Context import ({source_file_path})
```

### `<domain>` section

The `<domain>` section describes what the phase **delivers** — the artifacts, capabilities, or behaviors that exist when the phase is done. Do not include validation activities, test strategies, or "how we verify" — those belong in `<specifics>` or are left to the planner.

```markdown
<domain>
## Phase Boundary

{Phase goal from roadmap, or fallback from directory name}

</domain>
```

### `<decisions>` section

This is the critical section — everything here becomes a **locked decision**.

Analyze the source document and structure its content as implementation decisions:

- Each distinct item, gap, requirement, or scope statement becomes a decision under a categorized heading
- Preserve the source's specificity: scope descriptions, acceptance criteria, design references, constraint statements
- If the source has structured items (like gap assessments with Design/Actual/Scope/Acceptance fields), preserve that structure within each decision
- Include relevant content from referenced documents (step 7) inline where it adds clarity

```markdown
<decisions>
## Implementation Decisions

### {Category derived from source content}
- {Decision/requirement as stated in source}
- {Acceptance criteria if present}

### {Another category}
- {Decision/requirement}

### Claude's Discretion
{Identify implementation details that the source document does NOT specify.
These are areas where the planner has freedom to choose the approach.
Examples: specific error handling patterns, logging format, internal API design,
test structure, code organization within modules.}

</decisions>
```

### `<specifics>` section
```markdown
<specifics>
## Specific Ideas

{Concrete references from the source: links to design docs, specific file paths mentioned,
named libraries or tools, code patterns referenced, API endpoints}

{If the source references design documents, note: "See [doc name] for full specification"}

</specifics>
```

### `<code_context>` section
```markdown
<code_context>
## Existing Code Insights

### Reusable Assets
- {Existing code/functions/modules that can be extended or reused for this phase}

### Established Patterns
- {Patterns in the existing codebase that constrain or enable this phase's implementation}

### Integration Points
- {Where new code connects to the existing system — imports, API boundaries, data flow}

</code_context>
```

Populate from: the source document's references to existing code, file paths mentioned, function names discussed. If the source document doesn't reference existing code, use minimal entries noting the key files the phase will touch (derivable from the phase goal and decisions).

### `<deferred>` section
```markdown
<deferred>
## Deferred Ideas

{Items explicitly marked as out-of-scope, future, or "not this phase" in the source}

{If none: "None — source document covers phase scope"}

</deferred>
```

### Footer
```markdown
---

*Phase: {padded}-{slug}*
*Context gathered: {date} via context import*
```

### Merge mode

If the user chose "Merge" in step 5:
- Read the existing CONTEXT.md
- Parse its `<decisions>` section
- Append the new decisions from the source document as additional subsections within `<decisions>`, before `### Claude's Discretion`
- Update `### Claude's Discretion` to reflect the combined coverage
- Preserve all other sections from the existing CONTEXT.md
- Update the header to note the merge: `**Source:** Merged — original + context import ({path})`

## 9. Write File

Write the generated content to:
```
{phase_dir}/{padded_phase}-CONTEXT.md
```

## 10. Completion

```
Context created for Phase {N}: {phase_name}

Source: {source_file_path}
Output: {phase_dir}/{padded_phase}-CONTEXT.md
Decisions: {count} locked decisions extracted
Discretion areas: {count} areas left to planner

---

## Next Steps

- `/gsd:discuss-phase {N}` — layer interactive decisions on top
- `/gsd:plan-phase {N}` — plan directly with this context

---
```

</process>

<important_notes>
- The `<decisions>` section is what makes content "locked" for GSD agents. Everything inside it becomes non-negotiable for the planner.
- The `### Claude's Discretion` subsection explicitly marks areas where the planner has freedom. Without it, agents may ask for clarification on unspecified details.
- This command does NOT require GSD's gsd-tools.cjs. Phase resolution uses Glob, roadmap parsing uses Read.
- discuss-phase handles pre-existing CONTEXT.md gracefully (offers Update/View/Skip), so running this command before discuss-phase is safe.
- The PRD express path in plan-phase (step 3.5) follows a similar pattern — both convert external documents into CONTEXT.md.
- The template snapshot at `{MG_INSTALL_TEMPLATE_SNAPSHOT}` is the baseline this command was designed for. If drift is detected, the snapshot is NOT updated at runtime — it persists until the command is updated in mg-cc-tools and reinstalled.
</important_notes>
