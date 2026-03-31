# Concept Spec Template & Draft-Spec Command

## Situation

The current development workflow for new features follows a pattern: interactive discussion with Claude → concept document → auto-improve rounds → create-context → GSD phase execution. 23 concept documents have been written this way, stored in `docs/work-queue/`. The best documents (Session Analyzer, Install v1, Worktrees) share a consistent structure that emerged organically. The worst documents are missing design rationale or have vague problem statements.

No formal template exists. Document quality depends entirely on what the starting prompt happens to ask for. The auto-improve plan (`docs/work-queue/todo/auto-improve-command-v1/auto-improve-plan.md`) refines existing documents but cannot fix structural omissions — if a section was never written, auto-improve won't add it.

## Problem

Three concrete problems:

**1. Inconsistent structure across concept docs.** Across the 23 existing documents, section usage varies widely: Design Decisions appear in 6/18 completed docs despite being the most valuable section for downstream consumption. Verification appears in 10/18. Evidence/data backing appears in 7/18. Without a template, each new concept starts from scratch.

**2. PRDs and RFCs don't fit this workflow.** PRDs assume cross-functional stakeholders, GTM strategy, and success metrics — none of which apply to a solo developer who is the target audience. RFCs assume formal review processes and emphasize API contracts and system architecture, which are rarely the central concern. The documents that actually work here sit between these formats: they're technical enough to drive implementation but scoped to the decisions that matter, not architectural formalism.

**3. Uncertainty becomes firm statement without a formalization step.** During interactive discussion, ideas are explored tentatively — "maybe we could...", "I'm thinking...". When these get written into a concept document without explicit triage, auto-improve treats them as intentional design choices. A dangling exploration path looks the same as a firm decision. The missing step is formalization: something that takes the raw discussion context, identifies what's decided vs. uncertain vs. contradictory, and structures the output so downstream tools can distinguish them.

## Solution

### The Concept Spec Template

A markdown template that defines the structure for all concept documents. Every section is present in every document — the LLM judges what depth each section needs based on the concept's nature. An underspecified section is a signal worth surfacing, not something to hide by marking it optional.

#### Template structure

```markdown
# {Title}

## Situation

What exists today. Ground in data, measurements, or observed behavior where
available. Not motivation ("why we want this") — that belongs in Problem.
This section establishes the baseline: what IS, before anything changes.

For new features: describe the current workflow or state that the feature
addresses. For changes to existing systems: describe the system's current
behavior with specifics (file counts, response times, user steps).

## Problem

Why the current situation is insufficient. Specific evidence — what breaks,
what's missing, what's slow, what's confusing. Each problem statement should
be concrete enough that you could write a test for it.

If the concept addresses multiple problems, number them. If evidence is
available (measurements, user reports, incident data), include it. Vague
problems ("improve efficiency") produce vague solutions.

## Solution

### Overview

1-2 paragraphs that capture the shape of what's being built. A reader who
stops after the overview should understand the approach well enough to have
an opinion on it, even without implementation details.

### {Component/Aspect sections}

One subsection per major component, workflow step, or design surface. Include
concrete examples (JSON snippets, CLI invocations, file structures, sample
output) where they clarify the design. Prose descriptions of data formats
are almost always less clear than a 5-line example.

The number and naming of these subsections varies by concept. A pipeline
design might have one section per stage. A new command might have sections
for interface, behavior, and integration. A workflow change might have
sections for each actor (human, agent, system).

## Design Decisions

Numbered D1, D2, etc. Each decision captures a choice that was non-obvious,
contested, or has significant downstream consequences. Not every choice
needs a D-block — only those where the rationale matters for future readers
or implementers.

### D1: {Decision title}

**Choice:** What was decided.

**Why:** The reasoning — what constraints or tradeoffs drove this choice.
Include evidence if it exists (measurements, observed behavior, prior
experience). "Because it's simpler" is a valid reason when true, but say
what it's simpler than.

**Alternatives rejected:** What else was considered and why it lost. Skip
this line if there were no real alternatives (the choice was forced by
constraints).

## Scope

### What gets built

Files, commands, scripts, integrations — the concrete deliverables. Include
complexity notes where useful (e.g., "straightforward wiring" vs. "requires
new parsing logic"). File structure diagrams help when the concept introduces
new directories or reorganizes existing ones.

### What does NOT get built

Explicit exclusions with a one-line reason each. These are scope boundaries,
not deferrals — they state what this concept intentionally leaves out, not
what it promises to do later.

Deferred work ("v2", "future phase") should either be promoted into the
solution (if actually needed) or dropped entirely. Parking a problem as a
future promise is not a scope decision.

## Open Items

Decisions that are genuinely unresolved and need user input before
implementation can proceed. Each item states:

- What needs deciding
- What the known options are (if any)
- What depends on this decision (which parts of the solution are blocked)

Open Items are a temporary section. As items get resolved (during
auto-improve rounds or user discussion), they migrate to Design Decisions.
A mature concept spec has few or no Open Items.

## Verification

How to know the implementation is correct. Acceptance criteria, test
scenarios, or observable behaviors — not "it works" but "given X input,
Y happens" or "running Z command produces W output."

For concepts where verification is straightforward (the solution section
already implies how to test it), this section can be brief. For concepts
with subtle correctness requirements, this section earns its space.
```

#### What the template deliberately excludes

- **Target audience / personas** — the developer is the audience; this is known context, not a section to fill.
- **Success metrics / KPIs** — relevant for product teams, not for tool development where "it works correctly" is the bar.
- **Timeline / effort estimates** — volatile and better handled by GSD planning, not concept documents.
- **Alternatives considered (as a top-level section)** — alternatives belong inside the D-blocks where they were evaluated, not in a separate section disconnected from the decision.
- **Risk / mitigation tables** — risks that matter are either scope exclusions (put them in "What does NOT get built") or design constraints (put them in the D-block that addresses them).
- **Research / references section** — research backs specific claims inline where it's relevant, not in a bibliography at the end.

### The Draft-Spec Command

`/mg:draft-spec` takes an existing conversation context — raw ideas, discussion notes, or a sketch document — and formalizes it into a concept spec using the template above. Its primary job is to catch problems *before* they become prose that auto-improve would treat as firm.

#### Inputs

The command accepts one of:
- A file path to an existing idea/sketch document (like `auto-improve-command-v1/idea.md`)
- No file, in which case it works from the current conversation context

#### Workflow

**Phase 1 — Context extraction.** Read the source material (file or conversation). Extract every claim, decision, intention, and open question. Categorize each as:
- **Decided** — clear choice with reasoning present
- **Leaning** — preference expressed without firm commitment or rationale
- **Contradicted** — two statements that can't both be true
- **Dangling** — exploration path that was started but never concluded
- **Assumed** — claim stated as fact without evidence or discussion

**Phase 2 — Targeted research.** For items categorized as Leaning, Contradicted, Dangling, or Assumed: research the codebase to gather context that would help the user make a decision. This research does NOT produce decisions — it produces informed questions. Specifically:
- What existing patterns or conventions are relevant?
- What dependencies or constraints exist that the discussion didn't mention?
- What has been done in similar situations elsewhere in the project?

**Phase 3 — Interactive clarification.** Present findings to the user organized by template section, not by category. For each section of the template:
- State what's already decided (from Phase 1 "Decided" items)
- Surface items that need resolution, with research context from Phase 2
- Ask concrete questions with specific options (not "what do you think about X?" but "X could work as A or B — A has the advantage of..., B avoids the problem of...")

This phase follows a similar cadence to GSD discuss-phase: focused questions per area, checking whether more depth is needed before moving on. The key difference is that questions are organized by spec section, not by implementation gray area.

**Phase 4 — Draft generation.** Write the concept spec using the template. Every section is filled based on the discussion. Items that remain unresolved after Phase 3 go into Open Items with the options and dependencies clearly stated.

**Phase 5 — Contradiction and consistency check.** Before presenting the draft, scan it for:
- Design Decisions that contradict each other
- Solution sections that describe behavior inconsistent with the Design Decisions
- Scope items that are implicitly required by the Solution but listed in "What does NOT get built"
- Open Items that actually have enough information to be resolved

Flag any findings to the user alongside the draft.

#### Output

- Writes the concept spec to `docs/work-queue/todo/{name}/concept.md`
- Creates a companion `concept-NON-GOALS.md` if non-goals emerged during discussion
- Reports what was decided, what was clarified, and what remains open

#### What draft-spec does NOT do

- It does not replace auto-improve. Draft-spec produces the initial document; auto-improve refines it with fresh-eyes review.
- It does not make decisions. Research informs questions to the user; the user decides.
- It does not run without user interaction. Phases 3 requires user input — a concept spec cannot be generated from a sketch alone because the sketch's ambiguities are the whole point.

## Design Decisions

### D1: One template, no variants

**Choice:** A single template structure for all concept documents, regardless of whether the concept is a pipeline design, a new command, a workflow change, or an architectural decision.

**Why:** The existing 23 documents cover everything from CLI tools to documentation pipelines to git worktree workflows. Despite the variety, the same sections (Situation, Problem, Solution, Design Decisions, Scope) appear in all the high-quality ones. The variation is in subsection depth, not in which top-level sections exist. Variants add template-selection complexity without proportional value — the LLM can judge that a simple command concept needs a 2-paragraph Situation while a pipeline redesign needs a data table.

### D2: All sections present, depth varies

**Choice:** Every section appears in every concept spec. The LLM determines appropriate depth based on the concept's nature.

**Why:** An empty or thin section is a diagnostic signal. If Verification is one sentence for a concept with subtle correctness requirements, that's a finding auto-improve should catch. Marking sections as optional hides this signal. The template provides guidance per section on when depth is warranted vs. when brevity is appropriate.

### D3: Research serves questions, not decisions

**Choice:** Draft-spec's research phase produces context that informs questions to the user. It never writes decisions into the spec based on research alone.

**Why:** The whole point of the concept spec is to capture the user's design intent. A researcher that silently resolves ambiguities by reading the codebase would produce a document that looks complete but contains decisions the user never made. Research is valuable for presenting the right options — "the codebase already uses pattern X in three places, do you want to follow that or diverge?" — but the choice is always the user's.

### D4: Five-category extraction in Phase 1

**Choice:** Categorize source material as Decided, Leaning, Contradicted, Dangling, or Assumed.

**Why:** These five categories map directly to what draft-spec needs to do with each item. Decided items flow into the spec as-is. Leaning items need rationale strengthening. Contradicted items need resolution. Dangling items need conclusion or explicit exclusion. Assumed items need validation. Finer categorization (e.g., splitting "Assumed" into "assumed-correct" and "assumed-incorrect") would require judgment that should happen in the user discussion, not in automated categorization.

### D5: Questions organized by template section, not by extraction category

**Choice:** During interactive clarification, present findings grouped by where they'll appear in the spec (Situation, Solution, Design Decisions, etc.), not by their extraction category (Contradicted, Dangling, etc.).

**Why:** The user is thinking about the feature, not about the document structure. But organizing by spec section helps the discussion converge on a complete document rather than ping-ponging between unrelated topics. The extraction category is a tool for the command to prioritize what to ask — it doesn't need to be visible to the user.

### D6: Draft-spec is a command, not a mode

**Choice:** `/mg:draft-spec` is a single-invocation command that runs through its phases, not a persistent mode that stays active across conversation turns.

**Why:** The interactive clarification phase (Phase 3) happens within one command invocation using the question-asking pattern from GSD discuss-phase. This keeps the workflow bounded and produces a clear artifact (the concept spec file) at the end. A mode would blur the boundary between "discussing the concept" and "doing other work" and make it unclear when the spec is done.

## Scope

### What gets built

| Artifact | Description |
|----------|-------------|
| `auto-improve/references/concept-spec-template.md` | The template file, stored alongside auto-improve since both commands share the concept spec lifecycle |
| `draft-spec/commands/draft-spec.md` | The command file defining `/mg:draft-spec` behavior |
| `draft-spec/install.sh` | Installer that deploys the command and template reference |

The template is a reference document (like auto-doc's `references/templates/`), not a command. Draft-spec references it; auto-improve references it (to understand expected structure during review).

### What does NOT get built

- **Template validation tooling** — no linter or schema checker for concept specs. The template is guidance, not a contract. Auto-improve handles quality enforcement.
- **Automatic sketch-to-spec generation** — draft-spec requires user interaction. A sketch alone has too many ambiguities to resolve without discussion.
- **Retrospective template application** — existing concept docs in `docs/work-queue/done/` are not reformatted. The template applies to new work going forward.
- **Integration with auto-improve's reviewer prompt** — auto-improve already reviews for contradictions, gaps, and ambiguity. It doesn't need to know about the template to do this effectively. If template-aware review proves valuable later, it's a separate enhancement.

## Open Items

### O1: Template storage location

The template could live in:
- `auto-improve/references/` — co-located with the tool that refines concept specs
- `draft-spec/references/` — co-located with the tool that creates concept specs
- A shared location like `references/` at the repo root

The template is consumed by both draft-spec (to structure output) and potentially by auto-improve (to understand expected structure). Co-location with draft-spec seems most natural since draft-spec is the primary producer, but this depends on whether auto-improve will reference the template explicitly.

### O2: How draft-spec handles pre-existing concept docs

If a concept doc already exists at the target path (e.g., from a prior draft-spec run or manual writing), should draft-spec:
- Refuse and tell the user to use auto-improve instead?
- Offer to re-draft from scratch using the existing doc as additional context?
- Merge new discussion context into the existing document?

The cleanest option is probably "refuse and redirect to auto-improve" since that's the tool for refining existing docs. But there may be cases where the user wants to restart from a better discussion rather than iterate on a bad draft.

### O3: Conversation context extraction fidelity

When draft-spec works from conversation context (no input file), it needs to extract decisions from the current conversation. Claude Code conversations can be long and cover multiple topics. The extraction quality depends on how well Phase 1 can distinguish "we discussed X and decided Y" from "we mentioned X in passing." This may need a research subagent that reads the conversation in a structured way, or it may work well enough with the main agent's context. Unknown until tried.

## Verification

- **Template completeness:** Apply the template to 2-3 existing concept docs from `docs/work-queue/done/` and verify that every substantive section in the original maps to a template section, and no valuable content is lost.
- **Draft-spec Phase 1 extraction:** Run Phase 1 on a real conversation transcript (or a sketch file like `auto-improve-command-v1/idea.md`) and verify that the five categories (Decided, Leaning, Contradicted, Dangling, Assumed) are assigned correctly for at least 80% of items.
- **Draft-spec end-to-end:** Use draft-spec to create a concept doc for a real upcoming feature, then run auto-improve on the result. The auto-improve reviewer should find fewer structural issues (missing sections, unstated assumptions) compared to manually-written concept docs.
- **Downstream compatibility:** Run create-context on a draft-spec-produced concept doc and verify that Design Decisions map cleanly to CONTEXT.md `<decisions>` sections and Open Items are surfaced appropriately.
