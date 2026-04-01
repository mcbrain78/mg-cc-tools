# Prepare Context

---
name: mg:spec-prepare-context
description: Split a multi-phase source document into per-phase files for downstream ingestion by mg:spec-create-context
argument-hint: "<start>-<end> <source-file-path>"
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
Read a source document (design doc, scope doc, requirements brief) and split its content into per-phase files based on ROADMAP.md phase goals and REQUIREMENTS.md requirement IDs. Each output file contains the subset of source content relevant to that phase — faithfully preserved with minimal contextual framing.

The output files are consumed by `mg:spec-create-context`, which transforms them into GSD CONTEXT.md format.

This command does NOT transform content into GSD format. It only splits.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<start>-<end> <source-file-path>`

Examples:
- `1-5 docs/work-queue/todo/doc-command/DESIGN.md`
- `3-4 docs/design/pipeline-spec.md`

Single-phase usage is also valid:
- `1 docs/design/foundation-notes.md` (equivalent to `mg:spec-create-context` input prep)
</context>

<process>

## 1. Parse Arguments

Extract from `$ARGUMENTS`:
- **Phase range** — first token. Either `N-M` (range) or `N` (single phase).
- **Source file path** — remaining tokens joined as the file path.

If either is missing:
```
ERROR: Both phase range and source file path are required.

Usage: /mg:spec-prepare-context <start>-<end> <source-file-path>

Examples:
  /mg:spec-prepare-context 1-5 docs/work-queue/todo/doc-command/DESIGN.md
  /mg:spec-prepare-context 3 docs/design/pipeline-spec.md
```
Exit.

Parse the range:
- `N-M` → phases N through M inclusive (integer range)
- `N` → single phase N

## 2. Validate Inputs

**Read the source file.** If it doesn't exist or is empty:
```
ERROR: Source file not found or empty: <path>
```
Exit.

**Read `.planning/ROADMAP.md`.** If it doesn't exist:
```
ERROR: ROADMAP.md not found. Create a roadmap first.
```
Exit.

**Read `.planning/REQUIREMENTS.md`** if it exists. If all phases in the range have `Requirements: TBD`, skip — no requirement-based mapping signals are available. Otherwise, read the full text of each referenced requirement ID to enrich content mapping in Step 3.

**Validate each phase in range exists in ROADMAP.md:**
For each phase number, look for `### Phase {N}:` in the ROADMAP. If any phase in the range is missing:
```
ERROR: Phase {N} not found in ROADMAP.md.
```
Exit.

Extract per phase:
- Phase number, name, slug (derived from name)
- Goal description
- Requirement IDs (from `**Requirements**:` line)
- Success criteria

If REQUIREMENTS.md exists, also read the full text of each requirement ID referenced by the phases.

## 3. Analyze and Map Content

**Read the source document carefully.** Identify its structural units — sections, subsections, list items, specification blocks, tables, code examples. Each unit is a "content chunk" that will be mapped.

**For each content chunk, determine which phase(s) it belongs to:**

Use these signals (in priority order):
1. **Explicit phase references** — content that names a phase or its deliverables directly
2. **Requirement alignment** — content that maps to a specific requirement ID assigned to a phase
3. **Goal alignment** — content whose topic falls within a phase's goal description
4. **Success criteria alignment** — content that addresses a phase's success criteria

**Mapping rules:**
- A chunk can map to **multiple phases** (cross-cutting content). Duplicate it into each.
- A chunk can map to **no phase** — this is the remainder. Track it.
- When a chunk maps to multiple phases, include the full content in each phase file (don't fragment it).
- Preserve the source document's hierarchical structure — if a subsection maps to Phase 3 but its parent heading provides necessary context, include the parent heading (as a minimal framing line, not the full parent section).

**Built-vs-used distinction:** Some content describes things that are *built* in one phase but *consumed* in another. Map to the phase where it's built (that's where implementation decisions are needed). Add a brief note like `*(consumed by Phase N)*` if the usage context is important.

**Remainder handling:** After mapping, check for unmapped content. Present any remainders:
```
## Unmapped Content

The following content from the source document was not mapped to any phase in the range:

- "{section/chunk description}" (lines ~X-Y)
  - ...

This content may be:
- General context not specific to any phase
- Relevant to phases outside the requested range
- Background/research that informs but doesn't constrain implementation
```

Use AskUserQuestion:
- header: "Remainders"
- question: "Some content wasn't mapped to any phase. How should I handle it?"
- options:
  - "Include as shared context (Recommended)" — "Add an 'Additional Context' appendix to every phase file"
  - "Drop it" — "This content isn't needed for planning"
  - "Let me assign it" — "I'll tell you which phase(s) each unmapped chunk belongs to"

If "Include as shared context": Append unmapped content to each phase file under a `## Additional Context` section.
If "Drop it": Proceed without it.
If "Let me assign it": For each unmapped chunk, ask which phase(s) it belongs to, then include accordingly.

## 4. Write Phase Files

Determine the output directory: `{source-file-parent}/phase-docs/`

Check if the directory already exists:

**If it exists and contains files:**

Use AskUserQuestion:
- header: "Existing files"
- question: "phase-docs/ already exists with files from a previous run. Overwrite?"
- options:
  - "Overwrite (Recommended)" — "Delete existing phase-docs/ contents and write fresh"
  - "Abort" — "Keep existing files, stop here"

If "Abort": Exit.
If "Overwrite": Remove existing files in `phase-docs/`.

**Create the output directory:**
```bash
mkdir -p "{source-file-parent}/phase-docs"
```

**For each phase, write a file:** `phase-docs/phase-{NN}-{slug}.md`

Where `{NN}` is zero-padded phase number and `{slug}` is derived from the phase name in ROADMAP.md (lowercase, hyphens, no special chars).

**File structure:**

```markdown
# Phase {N}: {Phase Name}

> Source: {source-file-path}
> Phase goal: {goal from ROADMAP.md}
> Requirements: {requirement IDs}

---

{Content chunks mapped to this phase, preserving original structure}

{If cross-cutting content was included:}
{Content is included verbatim with no annotation needed — it belongs here}

{If "Additional Context" appendix from remainder handling:}

## Additional Context

{Unmapped content included as shared context}

---

*Prepared from: {source-file-path}*
*Phase: {NN}-{slug}*
*Date: {today}*
```

**Content formatting rules:**
- **Preserve original text verbatim.** Do not rewrite, summarize, or redact.
- **Minimal framing allowed:**
  - Header block with source, goal, requirements (helps reader understand scope)
  - Parent heading as a one-line framing note when a subsection is extracted without its full parent
  - Cross-phase pointers: `[See Phase {N} for {topic}]` when content references another phase's domain
  - Built-vs-used notes: `*(consumed by Phase {N})*` or `*(built in Phase {N})*`
- **Do NOT add:** Commentary, analysis, recommendations, restructuring, or any content not in the source document.

## 5. Summary and Auto-Advance

Present the results:

```
## Prepared: {count} phase files

| Phase | File | Content chunks | Cross-cutting |
|-------|------|---------------|---------------|
| {N}: {Name} | phase-{NN}-{slug}.md | {count} | {count shared chunks} |
| ... | ... | ... | ... |

Output: {source-dir}/phase-docs/
{If remainders were handled: "Remainders: {how they were handled}"}
```

Then offer auto-advance:

Use AskUserQuestion:
- header: "Next"
- question: "Phase files are ready. Create CONTEXT.md for each phase?"
- options:
  - "Create all (Recommended)" — "Run mg:spec-create-context for each phase sequentially"
  - "Create specific" — "Let me pick which phases to ingest"
  - "Stop here" — "I'll run mg:spec-create-context manually later"

**If "Create all":**

For each phase in order:
```
---
Creating context for Phase {N}: {Name}...
---
```
```
Skill("mg:spec-create-context", "{phase_number} {source-dir}/phase-docs/phase-{NN}-{slug}.md")
```

After each `spec-create-context` completes, briefly note the result:
```
Phase {N}: ✓ CONTEXT.md created ({decision_count} decisions)
```

After all phases, commit the generated CONTEXT.md files:

```bash
git add .planning/phases/*-CONTEXT.md && git commit -m "$(cat <<'EOF'
docs: create CONTEXT.md for phases {first_phase}-{last_phase}
EOF
)"
```

Then present the summary:

```
## All phases ingested

| Phase | CONTEXT.md | Decisions |
|-------|-----------|-----------|
| {N}: {Name} | .planning/phases/{NN}-{slug}/{NN}-CONTEXT.md | {count} |
| ... | ... | ... |

---

## Next Steps

- `/mg:discuss-milestone` — layer interactive decisions on top of imported context
- `/mg:plan-phase {first_phase}` — skip discussion, plan directly

/clear first → fresh context window

---
```

**If "Create specific":**

Use AskUserQuestion (multiSelect: true):
- header: "Phases"
- question: "Which phases should I create CONTEXT.md for?"
- options: One per phase file

Then run `spec-create-context` for selected phases only.

**If "Stop here":**
```
Phase files ready at: {source-dir}/phase-docs/

To ingest manually:
  /mg:spec-create-context 1 {source-dir}/phase-docs/phase-01-{slug}.md
  /mg:spec-create-context 2 {source-dir}/phase-docs/phase-02-{slug}.md
  ...

---
```

</process>

<important_notes>
- This command splits content — it does NOT transform into GSD CONTEXT.md format. That is `mg:spec-create-context`'s job.
- Content is preserved verbatim. The only additions are: header block, parent heading framing lines, cross-phase pointers, and built-vs-used annotations.
- Cross-cutting content is duplicated in full into every relevant phase file. This is intentional — each phase file must be self-contained for `spec-create-context` to process independently.
- The "built-vs-used" distinction matters: a script defined in Phase 1 but consumed in Phase 3 maps to Phase 1 (where the implementation decisions live). A note indicating Phase 3 consumption is added for context.
- Remainder handling ensures nothing is silently dropped. The user always knows if content wasn't mapped.
- Phase files are ephemeral build artifacts — they exist to feed `spec-create-context` and for user inspection. They are not committed to git.
- The auto-advance runs `spec-create-context` sequentially via Skill invocations. Each invocation gets the focused per-phase source file, avoiding the problem of feeding a large cross-phase doc to `spec-create-context`.
- `spec-create-context` needs a `mkdir -p` fix (separate change) to handle missing phase directories. Until that fix is applied, phase directories must exist before auto-advance runs.
- Range syntax uses dash (`1-5`) which is unambiguous because GSD decimal phases use dots (`2.1`), not dashes.
</important_notes>
