# Phase 23: Template Refiner Pipeline - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/prepare-templates/phase-docs/phase-23-template-refiner-pipeline.md)

<domain>
## Phase Boundary

prepare-templates command and template-refiner agent produce project-specific refined templates with ###/#### headings, PURPOSE comments, and structural EXAMPLE blocks from scan data and shallow source exploration

</domain>

<decisions>
## Implementation Decisions

### New command: prepare-templates.md
- New command `/mg:auto-doc-prepare-templates` orchestrating template refinement
- Reads scan data: `project_model`, `source_material_index`, `gap_analysis` from `docs-scan.json`
- For each audience/document, reads the generic template to get `##` sections with PURPOSE/EXAMPLE
- Spawns a refiner agent per document
- Outputs refined templates to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`
- Produces refined templates for all configured audiences — writers that cannot consume refined templates (end-user, developer, agent) ignore them via generate command's fallback logic

### New agent: template-refiner.md
- One refiner agent spawned per document
- Agent does shallow source exploration on source files listed in `source_material_index` for each `##` section:
  - `get_symbols_overview` on Python files — public API names, class names, no function bodies
  - Full reads for non-code files — systemd units, alembic configs, YAML configs, .env.example
  - NOT reading function bodies, NOT understanding implementation logic
- Decides what `###`/`####` headings each `##` section needs based on what the scan and source exploration reveal
- Writes a PURPOSE comment per heading — project-specific, grounded in scan data and shallow source reading (e.g., "3 systemd services", "7 schemas across 2 migration chains")
- Writes a generic structural EXAMPLE per heading — format demonstration only (table columns, step format, list style), no project-specific values

### Refined template format
- Complete replacement for the generic template — the writer sees only the refined template, not both
- `<!-- DIATAXIS: ... -->` and `<!-- AUDIENCE: ... -->` comments preserved from generic template
- `<!-- REFINED: {date}, scan: {date} -->` metadata tracks generation date and source scan date
- `##` sections carry forward same slugs and structure from generic template — refiner does NOT rename or reorganize `##` sections. Slug identity preserved to match `source_material_index` keys in scan
- `###`/`####` headings added with project-specific `<!-- PURPOSE: ... -->` and generic `<!-- EXAMPLE: ... -->` HTML comments
- OPTIONAL markers from generic template resolved — sections either become concrete headings or are dropped based on scan findings
- EXAMPLE blocks demonstrate format only (table columns, step structure, list style) — writer fills concrete values from source code

### PURPOSE vs EXAMPLE content distinction
- PURPOSE comments are project-specific — contain structural facts (counts, names, relationships) the refiner can verify from symbol overviews and config reads
- EXAMPLE blocks are generic — format demonstrations with placeholder data, no project-specific values
- Rationale: refiner's shallow reads are not deep enough for accurate content-level detail. Writer is the authority on concrete values via deep source code reading. Generic examples are also safer across regeneration — don't go stale when codebase changes

### Overwrite behavior
- `prepare-templates` overwrites refined templates by default on re-run — no merge logic
- Refined templates are derived artifacts — same scan data produces same output
- Manual edits are intentionally lightweight — review and re-apply after regeneration if needed

### Output directory
- Refined templates written to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`
- New project-local directory — one file per audience document

### Verification requirement
- Template idempotency: run prepare-templates twice on the same scan data — output refined templates should be structurally equivalent (same heading tree, same PURPOSE topics)

### Claude's Discretion
- Agent prompt structure and tool allowlist for the template-refiner agent
- How the command discovers which audiences/documents to process (from scan data, config, or generic template directory listing)
- Internal organization of the prepare-templates command (sequential vs parallel refiner spawning)
- How the refiner decides to drop vs keep OPTIONAL sections — threshold or heuristic
- Error handling when scan data is missing or generic templates can't be found
- Whether the refiner agent uses Serena tools or standard Read for source exploration

</decisions>

<specifics>
## Specific Ideas

- The refiner's "shallow" source reading is precisely defined: `get_symbols_overview` for Python files (class names, public API — no bodies), full reads for non-code files (systemd units, alembic configs, YAML, .env.example). This gives enough to count schemas, name services, identify config surfaces — without implementation logic
- The refined template example in the concept doc shows a complete OPERATIONS template with 4 `###` headings under `## Infrastructure Overview` — this is the target quality level for the refiner's output
- Slug identity preservation between generic and refined templates is critical — it guarantees `source_material_index` keys (which use `##` section slugs) work unchanged in the generate pipeline

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- Generic templates at `auto-doc/references/templates/` — 13 templates across 4 audience directories plus shared OVERVIEW and GLOSSARY. These are the refiner's input
- `auto-doc/references/schema.md` — documents the `docs-scan.json` contract including `source_material_index` format that the refiner reads
- Existing agent definitions in `auto-doc/agents/` — follow established TEMPLATE.md pattern for agent structure

### Established Patterns
- Agent-per-document spawning: the generate command already spawns one writer agent per audience. prepare-templates follows same pattern with one refiner agent per document
- HTML comment metadata in templates: generic templates already use `<!-- DIATAXIS: ... -->`, `<!-- AUDIENCE: ... -->`, `<!-- PURPOSE: ... -->`, `<!-- EXAMPLE: ... -->`, and `<!-- OPTIONAL -->` comments. The refined template preserves and extends this convention
- `.mg/docs/` directory structure: scan output, tmp files, and config already live under `.mg/docs/`. Templates join as `.mg/docs/templates/`

### Integration Points
- `docs-scan.json` — refiner reads `project_model`, `source_material_index`, and `gap_analysis` to inform heading decisions
- Generic templates at `auto-doc/references/templates/{audience}/{DOCUMENT}.template.md` — refiner's input (installed to `.claude/auto-doc/references/templates/` at install time)
- Phase 22's `next-heading.py` — consumes the refined template format this phase produces (parses heading tree, PURPOSE, EXAMPLE)
- Phase 24's generate command — detects refined templates and routes to orient-write writer loop

</code_context>

<deferred>
## Deferred Ideas

- Merge mode for refined templates — overwrite only for now, merge adds complexity for a rare use case
- Per-heading source file assignment in the scan — source files stay at `##` granularity
- Automatic prepare-templates invocation from generate — it's a separate manual command
- Stale writer modernization — end-user-writer, developer-writer, agent-writer are not on the current writer format and are not updated here
- Glossary and overview writer changes — these writers don't consume audience-specific templates with heading trees
- Parallel heading writes — sequential loop is simpler and sufficient

</deferred>

---

*Phase: 23-template-refiner-pipeline*
*Context gathered: 2026-04-02 via context import*
