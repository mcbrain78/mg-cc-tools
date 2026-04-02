# Phase 23: Template Refiner Pipeline

> Source: docs/work-queue/todo/prepare-templates/concept.md
> Phase goal: prepare-templates command and template-refiner agent produce project-specific refined templates with ###/#### headings, PURPOSE comments, and structural EXAMPLE blocks from scan data and shallow source exploration
> Requirements: TBD

---

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

## Solution Overview

A new pipeline step — `prepare-templates` — runs after scan and before generate. It reads the generic templates, scan data, and does shallow source exploration to produce project-specific refined templates with explicit `###`/`####` heading structure. Each heading carries a project-specific PURPOSE comment and a generic structural EXAMPLE showing expected format. The writer then fills the refined template heading-by-heading via a script-gated loop, spending its full budget on source reading and prose rather than structural decisions.

The pipeline becomes:

```
scan → prepare-templates → generate → verify/audit/fix
         ↑                    |
    (editable artifact)  (reads refined templates)
```

## Prepare-Templates Command

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
- `get_symbols_overview` on key files to understand what's there (public API names, class names)
- Read config files, systemd units, alembic configs to understand the deployment surface
- NOT reading function bodies, NOT understanding implementation logic

## Refined Template Format

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
- `##` sections carry forward the same slugs and structure from the generic template, enriched with project-specific PURPOSE. Slug identity is preserved — the refiner does not rename or reorganize `##` sections. This guarantees refined template `##` slugs match `source_material_index` keys in the scan
- `###`/`####` headings have project-specific PURPOSE (grounded in scan + shallow source reading) and generic structural EXAMPLE (format demonstration, no project-specific values)
- OPTIONAL markers from the generic template are resolved — optional sections either become concrete headings or are dropped based on what the scan found
- EXAMPLE blocks demonstrate format only (table columns, step structure, list style) — the writer fills in concrete values from source code

*(consumed by Phase 22 — next-heading.py parses this format)*
*(consumed by Phase 24 — writer reads refined templates)*

## Design Decisions

### D1: Refined templates replace generic templates for the writer

**Choice:** The refined template is the complete input the writer sees. It carries forward `##` structure from the generic template and adds project-specific `###`/`####` headings. The generic templates remain as the input to the refiner, not the writer.

**Why:** The writer should have one source of truth for document structure. Reading both a generic and refined template splits attention and creates ambiguity about which takes precedence. The refiner's job is to produce a complete, self-contained template.

### D2: Refiner produces generic structural examples, not project-specific values

**Choice:** EXAMPLE blocks in the refined template demonstrate format only (table columns, step structure, list style) using placeholder data. PURPOSE comments are project-specific — they contain structural facts (counts, names, relationships) derived from the refiner's shallow source exploration.

**Why:** PURPOSE comments guide the writer on *what to cover* using facts the refiner can verify from symbol overviews and config file reads (e.g., counting systemd unit files, listing schema names from alembic configs). EXAMPLE blocks guide the writer on *what format to use* — these must not contain project-specific values because the refiner's shallow reads are not deep enough to produce accurate content-level detail. The writer is the authority on concrete values because it reads the actual source code. Generic examples are also safer across regeneration — they don't go stale when the codebase changes.

### D3: Refiner reads source code shallowly for structural decisions

**Choice:** The refiner does shallow source exploration (symbol overviews, config file reads) to make better heading decisions. It does not read function bodies or implementation logic.

**Why:** Quality of heading decisions depends on understanding what's in the source files, not just that they exist. Knowing "db/connection.py has RoadRunnerBase, ArchiveBase, SharedBase" is the difference between creating a Database Schemas subsection or not. The project model provides some of this but not all. "Shallow" means: `get_symbols_overview` for Python files (public API names, class names — no function bodies), full reads for non-code files (systemd units, alembic configs, YAML configs, .env.example). This gives the refiner enough to count schemas, name services, and identify config surfaces without understanding implementation logic.

### D6: Overwrite on re-run

**Choice:** `prepare-templates` overwrites refined templates by default. No merge logic.

**Why:** Refined templates are derived artifacts — same scan data produces same output. Manual edits are intentionally lightweight (review and re-apply after regeneration). A merge mechanism adds complexity for a rare use case.

## Scope

### What gets built (Phase 23)

| Area | Changes |
|------|---------|
| New command: `prepare-templates.md` | Orchestrates template refinement — reads scan data, spawns refiner agent(s), writes refined templates to `.mg/docs/templates/` |
| New agent: `template-refiner.md` | Reads generic template + scan data + shallow source exploration. Produces refined template with `###`/`####` headings, PURPOSE comments, structural EXAMPLE blocks |
| New directory: `.mg/docs/templates/` | Project-local refined templates, one per audience document |

### What does NOT get built

- **Merge mode for refined templates** — overwrite only. Manual edits are re-applied after regeneration if needed.
- **Per-heading source file assignment in the scan** — source files stay at `##` granularity in the scan. The refined template's SOURCES comments in PURPOSE are informational context for the refiner's decisions, not prescriptive assignments consumed by the writer.
- **Automatic prepare-templates invocation from generate** — it's a separate manual command. Generate falls back to generic templates if refined templates don't exist.
- **Stale writer modernization** — `end-user-writer.md`, `developer-writer.md`, `agent-writer.md` are not on the current writer format and are not updated in this work. They need a separate format update first.
- **Glossary and overview writer changes** — `glossary-writer.md` and `overview-writer.md` do not consume audience-specific templates with PURPOSE/EXAMPLE heading trees. The glossary writer produces term definitions from project model data; the overview writer synthesizes from assembled doc chunks. Neither benefits from the orient-then-write loop. They retain their current processes.
- **Parallel heading writes** — sibling headings could theoretically be parallelized since they share source file context, but the sequential loop is simpler and sufficient for now.

## Open Items

None — integration questions resolved inline:
- *Audience scoping:* `prepare-templates` produces refined templates for all configured audiences. Writers that cannot consume refined templates (end-user, developer, agent) ignore them — the generate command's fallback logic passes the generic template instead.

## Verification

4. **Template idempotency**: Run prepare-templates twice on the same scan data. Output refined templates should be structurally equivalent (same heading tree, same PURPOSE topics).

---

*Prepared from: docs/work-queue/todo/prepare-templates/concept.md*
*Phase: 23-template-refiner-pipeline*
*Date: 2026-04-02*
