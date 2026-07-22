# Concept Spec Template

This template defines the structure for concept documents. Every section is present in every document — the LLM judges what depth each section needs based on the concept's nature. An underspecified section is a signal worth surfacing, not something to hide.

---

# {Title}

## Situation

What exists today. Ground in data, measurements, or observed behavior where available. Not motivation ("why we want this") — that belongs in Problem. This section establishes the baseline: what IS, before anything changes.

For new features: describe the current workflow or state that the feature addresses. For changes to existing systems: describe the system's current behavior with specifics (file counts, response times, user steps).

## Problem

Why the current situation is insufficient. Specific evidence — what breaks, what's missing, what's slow, what's confusing. Each problem statement should be concrete enough that you could write a test for it.

If the concept addresses multiple problems, number them. If evidence is available (measurements, user reports, incident data), include it. Vague problems ("improve efficiency") produce vague solutions.

## Solution

### Overview

1-2 paragraphs that capture the shape of what's being built. A reader who stops after the overview should understand the approach well enough to have an opinion on it, even without implementation details.

### {Component/Aspect sections}

One subsection per major component, workflow step, or design surface. Include concrete examples (JSON snippets, CLI invocations, file structures, sample output) where they clarify the design. Prose descriptions of data formats are almost always less clear than a 5-line example.

The number and naming of these subsections varies by concept. A pipeline design might have one section per stage. A new command might have sections for interface, behavior, and integration. A workflow change might have sections for each actor (human, agent, system).

## Design Decisions

Numbered D1, D2, etc. Each decision captures a choice that was non-obvious, contested, or has significant downstream consequences. Not every choice needs a D-block — only those where the rationale matters for future readers or implementers.

### D1: {Decision title}

**Context:** The situation and the problem this decision resolves, in plain product language a reader without the code in front of them can follow — what is going on, and what tension forces a choice. One to three sentences. Keep code identifiers out of this line; they belong in Why. This is what lets a reviewer judge the decision instead of reverse-engineering it from the answer.

**Choice:** What was decided.

**Why:** The reasoning — what constraints or tradeoffs drove this choice. Include evidence if it exists (measurements, observed behavior, prior experience). "Because it's simpler" is a valid reason when true, but say what it's simpler than. Implementation specifics (file/function/column names, line refs) live here, beneath the plain-language Context.

**Alternatives rejected:** What else was considered and why it lost. Skip this line if there were no real alternatives (the choice was forced by constraints).

## Scope

### What gets built

Files, commands, scripts, integrations — the concrete deliverables. Include complexity notes where useful (e.g., "straightforward wiring" vs. "requires new parsing logic"). File structure diagrams help when the concept introduces new directories or reorganizes existing ones.

**Citation discipline (required):** every top-level bullet in this section must cite the design decision(s) it realizes, as `(Dx)` or `(Dx, Dy)`, referencing the `### Dn:` headings under `## Design Decisions`. A top-level bullet is a line starting at column 0 with `- ` inside this section; indented sub-bullets, prose, code blocks, and file-tree diagrams are illustration and are not required to cite. The citation must appear on the bullet's own single line. A deliverable that no decision motivates is a spec smell — add the decision or drop the deliverable. This lets each deliverable be traced to its decision when the spec is later projected into a milestone (`mg:spec-create-milestone`); the discipline is unconditional — it does not depend on whether the spec will become a milestone.

### What does NOT get built

Explicit exclusions with a one-line reason each. These are scope boundaries, not deferrals — they state what this concept intentionally leaves out, not what it promises to do later.

Deferred work ("v2", "future phase") should either be promoted into the solution (if actually needed) or dropped entirely. Parking a problem as a future promise is not a scope decision.

## Open Items

Decisions that are genuinely unresolved and need user input before implementation can proceed. Each item states:

- What needs deciding
- What the known options are (if any)
- What depends on this decision (which parts of the solution are blocked)

Open Items are a temporary section. As items get resolved (during auto-improve rounds or user discussion), they migrate to Design Decisions. A mature concept spec has few or no Open Items.

## Verification

How to know the implementation is correct. Acceptance criteria, test scenarios, or observable behaviors — not "it works" but "given X input, Y happens" or "running Z command produces W output."

For concepts where verification is straightforward (the solution section already implies how to test it), this section can be brief. For concepts with subtle correctness requirements, this section earns its space.

---

## What the template deliberately excludes

- **Target audience / personas** — the developer is the audience; this is known context, not a section to fill.
- **Success metrics / KPIs** — relevant for product teams, not for tool development where "it works correctly" is the bar.
- **Timeline / effort estimates** — volatile and better handled by GSD planning, not concept documents.
- **Alternatives considered (as a top-level section)** — alternatives belong inside the D-blocks where they were evaluated, not in a separate section disconnected from the decision.
- **Risk / mitigation tables** — risks that matter are either scope exclusions (put them in "What does NOT get built") or design constraints (put them in the D-block that addresses them).
- **Research / references section** — research backs specific claims inline where it's relevant, not in a bibliography at the end.
