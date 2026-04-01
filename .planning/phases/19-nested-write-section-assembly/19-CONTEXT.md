# Phase 19: Nested Write-Section & Assembly - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/recursive-section-xml/phase-docs/phase-19-nested-write-section-assembly.md)

<domain>
## Phase Boundary

write-section.py supports `--parent` flag for hierarchical child section emission with nested state format and recursive XML finalization, and assemble-markdown.py concatenates sections depth-first.

This phase builds the generation-side pipeline on top of the recursive xml_doc.py core (Phase 18). Writers call write-section.py once per heading instead of once per `##` section.

</domain>

<decisions>
## Implementation Decisions

### --parent CLI flag
- New `--parent` flag on write-section.py specifies where in the tree to insert a child section
- `--parent` omitted → top-level section (appended to `sections_order`, same as today)
- `--parent` is a slug → child of that top-level section
- `--parent` is a slash-separated path → child at the resolved tree position (e.g., `monitoring-alerting/health-artifact`)
- Parent must exist before child is emitted — writer processes depth-first: heading intro first, then each child heading in order

### State format
- Sections gain `subsections` (dict) and `subsections_order` (list) keys for child sections
- `subsections` maps slug → child section dict (same shape: `content`, `typed_refs`, `subsections`, `subsections_order`)
- Tree is arbitrarily deep — same recursive structure at every level
- `section_write()` traverses the state tree using the parent path, creates `subsections`/`subsections_order` at the resolved parent if they don't exist, then inserts the new section

### Finalize behavior
- Finalize recursively builds nested `<section>` XML elements from the state tree
- Each section in the state tree becomes a `<section>` XML element with its own `<refs>` and `<body>`
- Child sections are nested inside their parent `<section>` element
- Uses xml_doc.py functions from Phase 18 for XML construction

### Merge mode
- `--merge` flag and `parse_existing_sections()` updated for nested sections — not removed (D4 note)
- Merge mode splits on all heading levels (not just `##`), matches by path
- This is the update pipeline path for incremental section updates

### assemble-markdown.py
- Recursive depth-first concatenation: section body, then child section bodies in order
- Output is the same flat markdown as today — nesting only affects how sections are stored/tracked, not the assembled output

### Backward compatibility
- Clean cutover — no dual-format state handling (D4)
- Old flat state files are not migrated; new generation runs produce nested state from scratch

### Claude's Discretion
- Error handling when `--parent` references a non-existent parent path
- Whether finalize validates tree integrity (e.g., orphaned sections) before building XML
- Internal implementation of state tree traversal in `section_write()`
- How `parse_existing_sections()` reconstructs the tree from heading levels during merge

</decisions>

<specifics>
## Specific Ideas

- CLI examples from concept showing three nesting depths:
  - Top-level: `--section monitoring-alerting` (no --parent)
  - Child: `--section etl-run-logging --parent monitoring-alerting`
  - Grandchild: `--section artifact-format --parent monitoring-alerting/health-artifact`
- State format JSON example showing full nested structure with `subsections` and `subsections_order` at each level
- Merge mode splits on all heading levels and reconstructs tree from heading depth — markers provide identity (slug), headings provide hierarchy (depth)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- write-section.py already has `section_write()`, `--section` flag, `--merge` flag, `parse_existing_sections()`, and finalize logic — all extended for nesting
- assemble-markdown.py already concatenates section bodies in order — extended for recursive depth-first traversal
- xml_doc.py recursive functions from Phase 18 (`build_xml_doc`, `_find_section_by_path`) used by finalize

### Established Patterns
- State file is JSON, read/written atomically via temp file + os.replace
- `sections_order` list preserves insertion order — same pattern extended to `subsections_order`
- `--content-file` and `--refs-file` flags for file-based I/O — unchanged

### Integration Points
- Finalize calls xml_doc.py functions to build the XML tree from state
- Writer agents (Phase 21) call write-section.py with `--parent` flag
- assemble-markdown.py consumes the XML produced by finalize

</code_context>

<deferred>
## Deferred Ideas

- Downstream pipeline script updates (verify, extract, merge, sync, prepare, load-audit) — Phase 20
- Writer agent prompt changes for per-heading emission — Phase 21
- Stale writer modernization — separate effort

</deferred>

---

*Phase: 19-nested-write-section-assembly*
*Context gathered: 2026-04-01 via context import*
