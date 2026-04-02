# Phase 24: Writer Orient-Write Integration

> Source: docs/work-queue/todo/prepare-templates/concept.md
> Phase goal: devops-writer uses next-heading.py orient-then-write loop, generate command detects and routes refined templates, and end-to-end pipeline produces complete documents from refined templates
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

## Writer Process Change

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

## Script-Gated Writer Loop (reference)

[See Phase 22 for next-heading.py script specification]

*(built in Phase 22)*

The writer calls next-heading.py in the correct sequence:
```
orient → write × N → orient → write × N → done
```

Each orient response provides heading outline + source files for one `##` section. Each write response provides one heading's PURPOSE + EXAMPLE. The writer emits all headings via write-section.py.

## Generate Command Change

The generate command checks for refined templates before spawning writers:
- If `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` exists → pass the refined template path to the writer agent prompt. The writer uses `next-heading.py` with `--template` pointing to the refined template and `--scan-file` pointing to `docs-scan.json`
- If not → fall back to generic template (backward compatible, current behavior — the writer reads the generic template directly and follows the existing per-heading emission process)
- Print a warning if refined templates are stale (scan date newer than refined date from `<!-- REFINED: -->` metadata)

The `generate-setup.py` script is extended to detect refined templates: for each audience/document, it checks `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` and includes a `refined_templates` dict in its JSON output mapping audience/document to the refined template path (or null if not found). The generate command uses this to decide which writer prompt to construct.

## Design Decisions

### D1: Refined templates replace generic templates for the writer

**Choice:** The refined template is the complete input the writer sees. It carries forward `##` structure from the generic template and adds project-specific `###`/`####` headings. The generic templates remain as the input to the refiner, not the writer.

**Why:** The writer should have one source of truth for document structure. Reading both a generic and refined template splits attention and creates ambiguity about which takes precedence. The refiner's job is to produce a complete, self-contained template.

## Scope

### What gets built (Phase 24)

| Area | Changes |
|------|---------|
| Modified: `devops-writer.md` | Rewritten for orient-then-write loop: Phase 1 reads source files with heading outline context, Phase 2 iterates headings via next-heading.py |
| Modified: `auto-doc-generate.md` | Checks for refined templates, passes template paths to next-heading.py initialization, prints warning if stale |
| Modified: `generate-setup.py` | Adds refined template detection — checks `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` for each audience/document, includes `refined_templates` dict in JSON output |

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
- *heading_path to write-section.py mapping:* The writer splits `heading_path` on `/` — the last segment becomes `--section`, everything before becomes `--parent`. For `##`-level headings (no `/` in path), `--parent` is omitted.

## Verification

1. **Template coverage**: The writer should produce content for every heading in the refined template. No headings skipped, no headings invented outside the template. The refined template defines the target structure; the writer fills it.

2. **Ref accuracy**: Run verify on the new output. Ref findings should be comparable to or fewer than fresh generation with the old recursive model (before audit-fix loops).

3. **Content quality**: Side-by-side comparison of a `###` subsection produced by the new pipeline vs the same subsection from the backup. The new output should be at least as specific and actionable.

6. **Fallback behavior**: Remove refined templates, run generate. Should fall back to generic templates without errors (backward compatible).

7. **Stale template warning**: Update scan data (re-scan after source changes), run generate without re-running prepare-templates. Should print a warning about stale refined templates.

8. **Writer end-to-end**: Run the rewritten devops-writer against a refined template for road-runner. Confirm it calls `next-heading.py` in the correct sequence (orient → write × N → orient → write × N → done), emits all headings via `write-section.py`, and produces a valid XML document after finalize.

---

*Prepared from: docs/work-queue/todo/prepare-templates/concept.md*
*Phase: 24-writer-orient-write-integration*
*Date: 2026-04-02*
