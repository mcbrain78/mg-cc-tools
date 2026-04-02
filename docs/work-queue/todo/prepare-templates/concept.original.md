# Prepare-Templates: Template-Driven Documentation Generation

## Situation

The auto-doc pipeline generates audience-segmented documentation through a 3-step process: scan → generate → verify. The scan maps source files to `##`-level sections per document. The writer agent receives a generic template (which defines `##` sections with PURPOSE + EXAMPLE comments) and produces all content — including deciding what `###`/`####` subsections to create from the scan data and source code.

The generic templates are project-agnostic. They define 6 `##` sections for OPERATIONS, 6 for TROUBLESHOOTING, etc., each with a PURPOSE comment explaining the goal and an EXAMPLE block showing format/structure using fictitious project data. The `###` subsection structure is entirely writer-generated.

The recently implemented recursive section XML model (phases 18-21) changed the writer's emission from one `write-section.py` call per `##` section to one call per heading at every level (`##`, `###`, `####`). Each heading gets its own `<section>` element with precisely scoped `<refs>`. This fixed ref accuracy — refs are now scoped to each heading's content rather than spread across a 200-line body.

Current measurements comparing recursive-model output against the previous flat-model output (which went through 2-3 audit-fix loops on road-runner):

| Document | Backup headings | New headings | Backup words | New words |
|----------|----------------|-------------|-------------|----------|
| OPERATIONS | 29 | 22 | 3,811 | 3,478 |
| TROUBLESHOOTING | 31 | 24 | 5,255 | 4,421 |

The word count difference is 10-16%, but the heading count difference is 7-8 dropped `###` subsections per document. The writer produces good content for the subsections it does generate — the content quality per heading is comparable. It just produces fewer headings.

## Problem

1. **Writer attention budget split between structure and content.** The per-heading emission model requires 3 steps per `###` subsection (write content temp file, write refs temp file, call write-section.py with --parent). For a `##` section with 4 children, that's 15 mechanical actions vs 3 in the old flat model. The writer's cognitive budget is consumed by emission mechanics and structural decisions ("what headings should I create?"), leaving less for actual prose and source code comprehension. The result: 7-8 dropped subsections per document while word count only drops 10-16% — the writer isn't producing less content per heading, it's producing fewer headings.

2. **No structural guidance below `##` level.** The generic templates define `##` sections but leave `###` structure entirely to the writer. Different generation runs can produce different subsection structures for the same project and scan data. There's no persistent record of "what subsections should this project's docs have."

3. **No mechanism for structural feedback.** When the audit/fix pipeline identifies missing topics or oversized sections, there's no artifact to edit. The fix can only modify prose within existing sections — it can't add or remove headings because the heading structure is ephemeral, decided fresh by the writer each run.

## Solution

### Overview

A new pipeline step — `prepare-templates` — runs after scan and before generate. It reads the generic templates, scan data, and does shallow source exploration to produce project-specific refined templates with explicit `###`/`####` heading structure. Each heading carries a project-specific PURPOSE comment and a generic structural EXAMPLE showing expected format. The writer then fills the refined template heading-by-heading via a script-gated loop, spending its full budget on source reading and prose rather than structural decisions.

The pipeline becomes:

```
scan → prepare-templates → generate → verify/audit/fix
         ↑                    |
    (editable artifact)  (reads refined templates)
```

### Prepare-Templates Command

A new command `/mg:auto-doc-prepare-templates` that:

1. Reads the scan data (project_model, source_material_index, gap_analysis)
2. For each audience/document, reads the generic template to get `##` sections with PURPOSE/EXAMPLE
3. Spawns a refiner agent per document that:
   - Does shallow source exploration (symbol overviews, config file reads) on the source files listed in the source_material_index for each `##` section
   - Decides what `###`/`####` headings each `##` section needs based on what it finds
   - Writes a PURPOSE comment per heading grounded in what the scan and source exploration revealed
   - Writes a generic structural EXAMPLE per heading (table columns, step format, list style — no project-specific values)
4. Outputs refined templates to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`

The refiner's source reading is shallow and structural:
- `get_symbols_overview` on key files to understand what's there (public API, class names)
- Read config files, systemd units, alembic configs to understand the deployment surface
- NOT reading function bodies, NOT understanding implementation logic

### Refined Template Format

The refined template is a complete replacement for the generic template. It carries forward the `##` structure and adds project-specific `###`/`####` headings:

```markdown
<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: devops -->
<!-- REFINED: 2026-04-02, scan: 2026-04-01 -->

# Operations Guide

## Infrastructure Overview
<!-- PURPOSE: Operators need a single-page mental model of the system's
     deployment topology. 3 systemd services on a single host, PostgreSQL
     on a separate host, Prefect orchestration layer. -->

### Deployment Topology
<!-- PURPOSE: Component-to-host mapping. 3 systemd services (prefect-server,
     finance-data-worker, stock-ranker-worker) plus PostgreSQL on mcbrain-server2. -->
<!-- EXAMPLE:
| Component | Service Unit | Host | Port | Health Check |
|-----------|-------------|------|------|-------------|
| ... | ... | ... | ... | ... |
-->

### External Dependencies
<!-- PURPOSE: 4 external API clients (FMP, FINRA, SEC EDGAR, Google AI)
     with rate limits, timeouts, and fallback behavior. -->
<!-- EXAMPLE:
| Service | Purpose | Client Class | Rate Limit | Fallback |
|---------|---------|-------------|------------|----------|
| ... | ... | ... | ... | ... |
-->

### Database Schemas
<!-- PURPOSE: 7 schemas across 2 migration chains (alembic_road_runner,
     alembic_archive). 3 base classes. Schema-to-table inventory needed
     for migration troubleshooting. -->
<!-- EXAMPLE:
| Schema | Tables | Migration Chain | Base Class |
|--------|--------|----------------|------------|
| ... | ... | ... | ... |
-->

### Architecture Diagram
<!-- PURPOSE: ASCII topology showing 3 systemd services on mcbrain-vmu1,
     PostgreSQL on mcbrain-server2, worker pools and concurrency limits. -->
<!-- EXAMPLE:
```
┌─────────────┐     ┌─────────────┐
│  Service A   │────│  Database    │
│  :port       │    │  :port       │
└─────────────┘     └─────────────┘
```
-->

## Deployment
<!-- PURPOSE: Step-by-step deploy and rollback for 3am operators.
     2 Alembic migration chains to run. -->

### Deploy
<!-- PURPOSE: Pull, migrate, restart services. Covers both alembic configs
     and all 3 systemd services. -->
<!-- EXAMPLE:
**Prerequisites:**
- [ ] Prerequisite 1
- [ ] Prerequisite 2

1. Step one:
   ```bash
   command here
   ```
   Expected output:
   ```
   output here
   ```
-->

...
```

Key properties:
- `<!-- REFINED: date, scan: date -->` metadata tracks when the template was generated and from which scan
- `##` sections carry forward PURPOSE from the generic template, enriched with project specifics
- `###`/`####` headings have project-specific PURPOSE (grounded in scan + shallow source reading) and generic structural EXAMPLE (format demonstration, no project-specific values)
- OPTIONAL markers from the generic template are resolved — optional sections either become concrete headings or are dropped based on what the scan found
- EXAMPLE blocks demonstrate format only (table columns, step structure, list style) — the writer fills in concrete values from source code

### Script-Gated Writer Loop

A `next-heading.py` script manages the heading queue, following the same proven pattern as the existing `next-section.py` in the verify pipeline. The writer calls it in a loop — get heading, write, emit, get next heading.

The script has two response types:

**Orient response** (when the next heading is a `##` section):
```json
{
  "type": "orient",
  "section": "infrastructure-overview",
  "heading_outline": [
    "infrastructure-overview",
    "infrastructure-overview/deployment-topology",
    "infrastructure-overview/external-dependencies",
    "infrastructure-overview/database-schemas",
    "infrastructure-overview/architecture-diagram"
  ],
  "source_files": ["systemd/prefect-server.service", "src/road_runner/db/connection.py", "..."]
}
```

**Write response** (for each heading including the `##` itself):
```json
{
  "type": "write",
  "heading_path": "infrastructure-overview/deployment-topology",
  "level": 3,
  "purpose": "Component-to-host mapping. 3 systemd services...",
  "example": "| Component | Service Unit | Host | Port | Health Check |\n|---|---|---|---|---|\n| ... |",
  "parent_path": "infrastructure-overview"
}
```

**Done response:**
```json
{
  "done": true,
  "headings_processed": 22
}
```

The writer processes the queue as:

```
Call next-heading.py
  → orient: read heading outline + source files for this ## section
Call next-heading.py
  → write: get ## heading's PURPOSE + EXAMPLE, write intro content, emit
Call next-heading.py
  → write: get ### heading's PURPOSE + EXAMPLE, write content, emit
  ...repeat until next orient or done...
Call next-heading.py
  → orient: new ## section, read new source files
  ...continue...
```

### Writer Process Change

The writer agent's process becomes:

**Initialization (once per document):**
1. Read project model, glossary, style guide — lightweight orientation context
2. Enter the heading loop

**Per `##` section (Phase 1 — Orient):**
1. Receive orient response: heading outline + source files
2. Read the source files for this `##` section — knows what material is available
3. The heading outline tells the writer "what am I reading for" — it knows the upcoming subsections

**Per heading (Phase 2 — Write):**
1. Receive write response: PURPOSE + EXAMPLE for this heading
2. Write content matching the PURPOSE, using the format from the EXAMPLE
3. Emit content + refs via write-section.py (with --parent for child headings)
4. Call next-heading.py for the next heading

Source files are read once per `##` section. The write loop works from the already-loaded context — no additional source reading per heading (optional if the writer wants to dig deeper into a specific file).

The writer's prompt becomes remarkably simple: orient on source material, then iterate headings writing content and refs. It never decides what headings to create — that's the template's job. It never worries about document-level structure — that's the heading outline. It focuses entirely on reading source code and writing good prose with accurate refs.

### Generate Command Change

The generate command checks for refined templates before spawning writers:
- If `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` exists → pass to writer via `next-heading.py` initialization
- If not → fall back to generic template (backward compatible, current behavior)
- Print a warning if refined templates are stale (scan date newer than refined date from `<!-- REFINED: -->` metadata)

## Design Decisions

### D1: Refined templates replace generic templates for the writer

**Choice:** The refined template is the complete input the writer sees. It carries forward `##` structure from the generic template and adds project-specific `###`/`####` headings. The generic templates remain as the input to the refiner, not the writer.

**Why:** The writer should have one source of truth for document structure. Reading both a generic and refined template splits attention and creates ambiguity about which takes precedence. The refiner's job is to produce a complete, self-contained template.

### D2: Refiner produces generic structural examples, not project-specific values

**Choice:** EXAMPLE blocks in the refined template demonstrate format only (table columns, step structure, list style) using placeholder data. PURPOSE comments are project-specific, grounded in scan data and shallow source exploration.

**Why:** The refiner doesn't read source files deeply enough to produce accurate concrete values. Project-specific values in examples risk misleading the writer — if the refiner gets a schema name or migration chain wrong, the writer may propagate the error. The writer is the authority on concrete values because it reads the actual source code. Generic examples are also safer across regeneration — they don't go stale when the codebase changes.

### D3: Refiner reads source code shallowly for structural decisions

**Choice:** The refiner does shallow source exploration (symbol overviews, config file reads) to make better heading decisions. It does not read function bodies or implementation logic.

**Why:** Quality of heading decisions depends on understanding what's in the source files, not just that they exist. Knowing "db/connection.py has RoadRunnerBase, ArchiveBase, SharedBase" is the difference between creating a Database Schemas subsection or not. The project model provides some of this but not all. Restricting to shallow reads keeps the refiner fast and cheap while producing well-informed structure.

### D4: Script-gated heading iteration

**Choice:** A `next-heading.py` script manages the heading queue. The writer calls it in a loop — get heading template block, write content, emit, repeat.

**Why:** This is a proven pattern (already used by `next-section.py` in the verify pipeline). It prevents the writer from reading ahead, keeps working context focused on one heading at a time, and makes the writer's prompt simple and stateless per heading. The script handles depth-first ordering, source file grouping, and state persistence.

**Alternatives rejected:** One agent per heading — would lose the source file context loaded during orient phase. One agent per document with full template upfront — the problem we're solving (attention budget consumed by structure).

### D5: Source files loaded per `##` section, not per heading

**Choice:** The writer reads all source files when receiving an orient response for a `##` section. Child headings (`###`/`####`) work from the already-loaded context. Source reading within the write loop is optional.

**Why:** Source files are mapped at `##` granularity in the scan. Reading them once per `##` section gives the writer the full context it needs for all child headings. Per-heading source loading would require the refiner to split source assignments — added complexity for minimal benefit. The writer already has the material in context when it processes children.

### D6: Overwrite on re-run

**Choice:** `prepare-templates` overwrites refined templates by default. No merge logic.

**Why:** Refined templates are derived artifacts — same scan data produces same output. Manual edits are intentionally lightweight (review and re-apply after regeneration). A merge mechanism adds complexity for a rare use case. If users frequently edit refined templates, merge support can be added later following the existing `--merge` pattern in write-section.py.

### D7: Writer receives heading outline for orientation

**Choice:** The orient response includes the full heading outline (just slugs and hierarchy) for the upcoming `##` section, plus the source file list.

**Why:** Reading source code without knowing the heading structure wastes attention — the writer doesn't know what to look for. The heading outline gives the writer the "what am I reading for" context so it reads source code with purpose. This is lightweight (a list of slug strings) and doesn't bloat context like full PURPOSE + EXAMPLE content would.

### D8: Two-phase per-section processing (orient then write)

**Choice:** Each `##` section is processed in two phases: orient (receive heading outline + source files, read source code) then write (iterate headings one at a time, each with PURPOSE + EXAMPLE from the refined template).

**Why:** Separating "understand the source material" from "write one heading" keeps each task focused. The orient phase builds comprehension with full awareness of what headings are coming. The write phase delivers one heading's template block at a time for focused output. The writer never needs to hold previous headings' content in memory — consistency comes from the template, glossary, and style guide.

## Scope

### What gets built

| Area | Changes |
|------|---------|
| New command: `prepare-templates.md` | Orchestrates template refinement — reads scan data, spawns refiner agent(s), writes refined templates to `.mg/docs/templates/` |
| New agent: `template-refiner.md` | Reads generic template + scan data + shallow source exploration. Produces refined template with `###`/`####` headings, PURPOSE comments, structural EXAMPLE blocks |
| New script: `next-heading.py` | Script-gated heading iterator. Orient mode returns heading outline + source files for a `##` group. Write mode returns one heading's PURPOSE + EXAMPLE. Maintains state between calls |
| New script: `parse-refined-template.py` | Parses a refined template into structured JSON — heading tree with PURPOSE, EXAMPLE, and source file assignments per `##` section. Consumed by `next-heading.py` on first call |
| Modified: writer agents (`devops-writer.md`, `glossary-writer.md`, `overview-writer.md`) | Rewritten for orient-then-write loop: Phase 1 reads source files with heading outline context, Phase 2 iterates headings via next-heading.py |
| Modified: `auto-doc-generate.md` | Checks for refined templates, passes template paths to next-heading.py initialization, prints warning if stale |
| New directory: `.mg/docs/templates/` | Project-local refined templates, one per audience document |

### What does NOT get built

- **Merge mode for refined templates** — overwrite only. Manual edits are re-applied after regeneration if needed.
- **Per-heading source file assignment in the scan** — source files stay at `##` granularity in the scan. The refined template's SOURCES comments in PURPOSE are informational context for the refiner's decisions, not prescriptive assignments consumed by the writer.
- **Automatic prepare-templates invocation from generate** — it's a separate manual command. Generate falls back to generic templates if refined templates don't exist.
- **Stale writer modernization** — `end-user-writer.md`, `developer-writer.md`, `agent-writer.md` are not on the current writer format and are not updated in this work. They need a separate format update first.
- **Parallel heading writes** — sibling headings could theoretically be parallelized since they share source file context, but the sequential loop is simpler and sufficient for now.

## Open Items

None — all design questions resolved during discussion.

## Verification

1. **Coverage parity**: Generate devops docs with the new pipeline (prepare-templates → generate) and compare heading count against the backup. The new output should have equal or more `###` subsections than the backup (29 for OPERATIONS, 31 for TROUBLESHOOTING).

2. **Ref accuracy**: Run verify on the new output. Ref findings should be comparable to or fewer than fresh generation with the old recursive model (before audit-fix loops).

3. **Content quality**: Side-by-side comparison of a `###` subsection produced by the new pipeline vs the same subsection from the backup. The new output should be at least as specific and actionable.

4. **Template idempotency**: Run prepare-templates twice on the same scan data. Output refined templates should be structurally equivalent (same heading tree, same PURPOSE topics).

5. **next-heading.py state management**: Unit test the orient/write cycle — verify depth-first ordering, correct source file grouping at `##` boundaries, orient-to-write transitions, and done signaling.

6. **Fallback behavior**: Remove refined templates, run generate. Should fall back to generic templates without errors (backward compatible).

7. **Stale template warning**: Update scan data (re-scan after source changes), run generate without re-running prepare-templates. Should print a warning about stale refined templates.
