# Phase 22: Heading Iterator Script

> Source: docs/work-queue/todo/prepare-templates/concept.md
> Phase goal: next-heading.py parses refined templates, manages heading queue state, and returns orient/write/done responses with correct depth-first ordering and source file grouping
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

## Script-Gated Writer Loop

A `next-heading.py` script manages the heading queue, following the same proven pattern as the existing `next-section.py` in the verify pipeline. The writer calls it in a loop — get heading, write, emit, get next heading.

**CLI interface:**
```bash
python3 next-heading.py \
    --state-file .mg/docs/tmp/heading-state-{audience}.json \
    --template .mg/docs/templates/{audience}/{DOCUMENT}.template.md \
    --scan-file .mg/docs/docs-scan.json \
    --document {DOCUMENT}
```

On first call, the script parses the refined template (extracting heading tree, PURPOSE, EXAMPLE per heading) and looks up source files from `source_material_index` in the scan file using `DOCUMENT/section-slug` keys. This parsed state is persisted to `--state-file` for subsequent calls.

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

*(consumed by Phase 24)*

## Refined Template Format (reference)

[See Phase 23 for full refined template format specification]

The refined template is the input that next-heading.py parses. Key properties relevant to parsing:
- `##` sections carry forward slugs from the generic template
- `###`/`####` headings have `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comments
- `<!-- REFINED: date, scan: date -->` metadata in the header
- OPTIONAL markers from the generic template are resolved — sections either become concrete headings or are dropped

## Design Decisions

### D4: Script-gated heading iteration

**Choice:** A `next-heading.py` script manages the heading queue. The writer calls it in a loop — get heading template block, write content, emit, repeat.

**Why:** This is a proven pattern (already used by `next-section.py` in the verify pipeline). It prevents the writer from reading ahead, keeps working context focused on one heading at a time, and makes the writer's prompt simple and stateless per heading. The script handles depth-first ordering, source file grouping, and state persistence.

**Alternatives rejected:** One agent per heading — would lose the source file context loaded during orient phase. One agent per document with full template upfront — the problem we're solving (attention budget consumed by structure).

### D5: Source files loaded per `##` section, not per heading

**Choice:** The writer reads all source files when receiving an orient response for a `##` section. Child headings (`###`/`####`) work from the already-loaded context. Source reading within the write loop is optional.

**Why:** Source files are mapped at `##` granularity in the scan. Reading them once per `##` section gives the writer the full context it needs for all child headings. Per-heading source loading would require the refiner to split source assignments — added complexity for minimal benefit. The writer already has the material in context when it processes children.

### D7: Writer receives heading outline for orientation

**Choice:** The orient response includes the full heading outline (just slugs and hierarchy) for the upcoming `##` section, plus the source file list.

**Why:** Reading source code without knowing the heading structure wastes attention — the writer doesn't know what to look for. The heading outline gives the writer the "what am I reading for" context so it reads source code with purpose. This is lightweight (a list of slug strings) and doesn't bloat context like full PURPOSE + EXAMPLE content would.

### D8: Two-phase per-section processing (orient then write)

**Choice:** Each `##` section is processed in two phases: orient (receive heading outline + source files, read source code) then write (iterate headings one at a time, each with PURPOSE + EXAMPLE from the refined template).

**Why:** Separating "understand the source material" from "write one heading" keeps each task focused. The orient phase builds comprehension with full awareness of what headings are coming. The write phase delivers one heading's template block at a time for focused output. The writer never needs to hold previous headings' content in memory — consistency comes from the template, glossary, and style guide.

## Scope

### What gets built (Phase 22)

| Area | Changes |
|------|---------|
| New script: `next-heading.py` | Script-gated heading iterator. On first call, parses the refined template and looks up source files from the scan's `source_material_index`. Orient mode returns heading outline + source files for a `##` group. Write mode returns one heading's PURPOSE + EXAMPLE. Persists parsed state between calls |

### What does NOT get built

- **Merge mode for refined templates** — overwrite only. Manual edits are re-applied after regeneration if needed.
- **Per-heading source file assignment in the scan** — source files stay at `##` granularity in the scan. The refined template's SOURCES comments in PURPOSE are informational context for the refiner's decisions, not prescriptive assignments consumed by the writer.
- **Automatic prepare-templates invocation from generate** — it's a separate manual command. Generate falls back to generic templates if refined templates don't exist.
- **Stale writer modernization** — `end-user-writer.md`, `developer-writer.md`, `agent-writer.md` are not on the current writer format and are not updated in this work. They need a separate format update first.
- **Glossary and overview writer changes** — `glossary-writer.md` and `overview-writer.md` do not consume audience-specific templates with PURPOSE/EXAMPLE heading trees. The glossary writer produces term definitions from project model data; the overview writer synthesizes from assembled doc chunks. Neither benefits from the orient-then-write loop. They retain their current processes.
- **Parallel heading writes** — sibling headings could theoretically be parallelized since they share source file context, but the sequential loop is simpler and sufficient for now.

## Open Items

None — integration questions resolved inline:
- *heading_path to write-section.py mapping:* The writer splits `heading_path` on `/` — the last segment becomes `--section`, everything before becomes `--parent`. For `##`-level headings (no `/` in path), `--parent` is omitted.

## Verification

5. **next-heading.py state management**: Unit test the orient/write cycle — verify depth-first ordering, correct source file grouping at `##` boundaries, orient-to-write transitions, and done signaling. Include a template parsing test: given a refined template, verify the parsed heading tree matches the template's heading hierarchy with correct PURPOSE and EXAMPLE extraction.

---

*Prepared from: docs/work-queue/todo/prepare-templates/concept.md*
*Phase: 22-heading-iterator-script*
*Date: 2026-04-02*
