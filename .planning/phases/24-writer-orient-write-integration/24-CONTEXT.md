# Phase 24: Writer Orient-Write Integration - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/prepare-templates/phase-docs/phase-24-writer-orient-write-integration.md)

<domain>
## Phase Boundary

devops-writer uses next-heading.py orient-then-write loop, generate command detects and routes refined templates, and end-to-end pipeline produces complete documents from refined templates

</domain>

<decisions>
## Implementation Decisions

### devops-writer.md rewrite — orient-then-write loop
- Writer agent prompt rewritten for two-phase per-section processing
- **Initialization (once per document):** Read project model, glossary, style guide — lightweight orientation context, then enter the heading loop
- **Per `##` section — Orient phase:** Receive orient response from next-heading.py (heading outline + source files). Read the source files for this `##` section. The heading outline tells the writer "what am I reading for" — it knows the upcoming subsections before reading source code
- **Per heading — Write phase:** Receive write response from next-heading.py (PURPOSE + EXAMPLE for this heading). Write content matching the PURPOSE, using the format from the EXAMPLE. Emit content + refs via write-section.py (with `--parent` for child headings). Call next-heading.py for the next heading
- Source files are read once per `##` section — the write loop works from already-loaded context. Additional source reading per heading is optional
- The writer never decides what headings to create — that's the template's job. It never worries about document-level structure — that's the heading outline. It focuses entirely on reading source code and writing good prose with accurate refs
- The writer calls next-heading.py in the sequence: orient → write × N → orient → write × N → done

### heading_path to write-section.py mapping
- Writer splits `heading_path` from next-heading.py on `/`
- Last segment becomes `--section` argument to write-section.py
- Everything before becomes `--parent` argument
- For `##`-level headings (no `/` in path), `--parent` is omitted

### generate command changes — auto-doc-generate.md
- Check for refined templates before spawning writers: if `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` exists → pass refined template path to writer agent prompt
- If refined template not found → fall back to generic template (backward compatible, current behavior — writer reads generic template directly and follows existing per-heading emission process)
- Print a warning if refined templates are stale: scan date newer than refined date from `<!-- REFINED: -->` metadata

### generate-setup.py extension — refined template detection
- Extended to detect refined templates for each audience/document
- Checks `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`
- Includes a `refined_templates` dict in JSON output mapping audience/document to the refined template path (or null if not found)
- Generate command uses this dict to decide which writer prompt to construct (orient-write loop vs existing per-heading emission)

### Refined template is the writer's sole structural input
- The refined template completely replaces the generic template for the writer — the writer sees only the refined template, not both
- Generic templates remain as input to the refiner (Phase 23), not the writer
- One source of truth for document structure eliminates ambiguity about which takes precedence

### Verification requirements
- **Template coverage:** Writer produces content for every heading in the refined template — no headings skipped, no headings invented outside the template
- **Ref accuracy:** Verify findings should be comparable to or fewer than fresh generation with old recursive model (before audit-fix loops)
- **Content quality:** Side-by-side comparison of `###` subsection from new pipeline vs backup — new output at least as specific and actionable
- **Fallback behavior:** Remove refined templates, run generate — should fall back to generic templates without errors
- **Stale template warning:** Re-scan after source changes, run generate without re-running prepare-templates — should print stale warning
- **Writer end-to-end:** Run rewritten devops-writer against refined template for road-runner — confirm correct next-heading.py sequence (orient → write × N → orient → write × N → done), all headings emitted via write-section.py, valid XML document after finalize

### Claude's Discretion
- How the devops-writer prompt structures the orient phase source reading (full file reads vs symbol overview reads)
- Whether the writer prompt includes explicit instructions for each response type or a single unified loop instruction
- How the generate command constructs different writer prompts for refined vs generic template paths
- Error handling in the writer when next-heading.py returns unexpected responses
- How stale template detection compares dates (parse `<!-- REFINED: -->` metadata vs scan file timestamp vs scan metadata)
- Test strategy for end-to-end verification — real road-runner run vs synthetic test fixtures

</decisions>

<specifics>
## Specific Ideas

- Only `devops-writer.md` is rewritten in this phase — `end-user-writer.md`, `developer-writer.md`, and `agent-writer.md` are not on the current writer format and are not updated here. They need a separate format update first
- `glossary-writer.md` and `overview-writer.md` are explicitly excluded — they don't consume audience-specific templates with heading trees
- The generate command's refined template detection must be non-breaking: projects without refined templates continue working exactly as before
- The `refined_templates` dict in generate-setup.py output enables the generate command to make routing decisions without filesystem checks at prompt-construction time

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auto-doc/agents/devops-writer.md`: Current writer agent to be rewritten — understand existing structure before replacing
- `auto-doc/commands/auto-doc-generate.md`: Generate orchestrator to be modified — currently spawns writer agents with generic template references
- `auto-doc/scripts/generate-setup.py`: Setup script to be extended — currently produces audience/document metadata without template path information
- `auto-doc/scripts/write-section.py`: Emission script the writer already calls — `--section` and `--parent` args are the interface contract

### Established Patterns
- Writer agent spawning: generate command constructs writer agent prompts with audience-specific context (scan data, template path, output paths). This pattern extends to include refined template paths
- Per-heading emission via write-section.py: writers already call write-section.py with `--parent` for child headings (phases 18-21). The orient-write loop changes how headings are discovered, not how they're emitted
- generate-setup.py JSON output: already includes audience/document metadata consumed by the generate command. `refined_templates` dict extends this existing pattern

### Integration Points
- Phase 22's `next-heading.py`: The writer calls this script in a loop — orient/write/done responses drive the writer's behavior
- Phase 23's refined templates at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`: The generate command detects these and routes accordingly
- `write-section.py --section --parent`: The writer's emission interface — heading_path from next-heading.py maps directly to these args
- `docs-scan.json`: next-heading.py reads source_material_index; generate-setup.py reads audience/document metadata

</code_context>

<deferred>
## Deferred Ideas

- Stale writer modernization — end-user-writer, developer-writer, agent-writer need separate format updates before they can use the orient-write loop
- Glossary and overview writer changes — these writers don't benefit from the orient-write loop
- Parallel heading writes — sequential loop is simpler and sufficient
- Automatic prepare-templates invocation from generate — remains a separate manual command
- Merge mode for refined templates — overwrite only

</deferred>

---

*Phase: 24-writer-orient-write-integration*
*Context gathered: 2026-04-02 via context import*
