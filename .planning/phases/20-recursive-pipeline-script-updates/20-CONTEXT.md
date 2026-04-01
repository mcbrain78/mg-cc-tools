# Phase 20: Recursive Pipeline Script Updates - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/recursive-section-xml/phase-docs/phase-20-recursive-pipeline-script-updates.md)

<domain>
## Phase Boundary

verify-xml-refs.py, prepare-prose-verify.py, extract-edit-xml.py, merge-edit-xml.py, sync-edits-to-xml.py, and load-audit-findings.py operate on the recursive section tree using slash-separated section paths.

These are the downstream pipeline scripts that consume the recursive XML model built in Phase 18 and the nested write-section output from Phase 19. Each script changes from flat section iteration to recursive tree traversal.

</domain>

<decisions>
## Implementation Decisions

### Finding path format
- Findings use a single `"section"` field with slash-separated paths: `"monitoring-alerting/etl-run-logging"` (D7)
- No separate fields per depth level — one field works at any depth
- Leaf slug: `path.rsplit("/", 1)[-1]`; parent path: `path.rsplit("/", 1)[0]`

### Tree-path navigation
- All scripts use `_find_section_by_path()` from xml_doc.py (built in Phase 18) to locate sections in the XML tree
- Replaces current flat `findall("section")` lookups
- Path resolution relies on sibling slug uniqueness (D5)

### verify-xml-refs.py
- Recursive iteration over nested sections — each section's refs checked against its own body independently
- Finding `"section"` field uses slash-separated paths
- A ref in parent's `<refs>` that only appears in child's body correctly fails the parent's audit

### prepare-prose-verify.py
- Recursively iterates nested sections for prose verification input
- Output files use nested directories mirroring the section tree (e.g., `{output_dir}/monitoring-alerting/etl-run-logging.json`)
- Nested directory structure avoids flat-name collisions

### extract-edit-xml.py
- Uses `_find_section_by_path()` to extract individual sections at any tree depth
- Edit files shrink from ~200 lines to 5-40 lines (smaller bodies)
- `<edit-group>` XML adds a `path` attribute to each `<section>` element carrying the full slash-separated path for merge-back
- `slug` attribute retained for display/logging alongside the new `path` attribute

### merge-edit-xml.py
- Uses the `path` attribute from edit-group XML with `_find_section_by_path()` to locate the correct node in the master XML tree
- Merges back to correct tree position — no longer assumes flat section list

### sync-edits-to-xml.py
- Splits markdown into sections using `<!-- section: slug -->` markers (same as today, finer granularity)
- Flat split by marker gives segments; nesting reconstructed by reading the heading level (`##`, `###`, etc.) in each segment
- A `###` segment following a `##` segment is its child; a `###` following another `###` is a sibling
- Heading level in body content is the authoritative signal for tree position — markers provide identity (slug), headings provide hierarchy (depth)

### load-audit-findings.py
- Handles slash-separated section paths in findings — no structural changes beyond path format support

### fix-queue.py and audit-fixer.md
- fix-queue.py: no structural changes — operates on whatever sections extract produces
- audit-fixer.md: receives smaller edit files naturally; scope creep constrained by body size

### Claude's Discretion
- Error handling when `_find_section_by_path` returns None (section not found in tree)
- How sync-edits-to-xml.py handles malformed heading hierarchies (e.g., `####` directly under `##` with no `###`)
- Whether prepare-prose-verify.py creates nested directories eagerly or lazily
- Test organization — whether to test scripts individually or with shared fixtures for the nested XML tree
- Whether extract-edit-xml.py validates that the `path` attribute matches the actual tree position

</decisions>

<specifics>
## Specific Ideas

- Edit-group XML format example from concept showing `path` attribute: `path="monitoring-alerting/etl-run-logging"` alongside `slug="etl-run-logging"`
- Marker-based body splitting example showing flat split then heading-level reconstruction
- Finding JSON example: `{"document": "OPERATIONS", "section": "monitoring-alerting/etl-run-logging", "audience": "devops", "check": "reference-integrity", ...}`
- Verification criteria: edit extraction size should show >50% token reduction for multi-subsection groups; slash-path resolution must correctly resolve paths to right tree nodes

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_find_section_by_path()` and `walk_sections()` from xml_doc.py (Phase 18) — shared navigation primitives
- `parse_xml_doc()` returns nested section dicts with `children` key (Phase 18) — consumed by all scripts
- All scripts already import from `xml_doc.py` — extending existing import patterns

### Established Patterns
- Scripts use file-based I/O (`--input`/`--output`) — unchanged
- Finding JSON structure has `document`, `section`, `audience`, `check`, `description` fields — `section` field changes from slug to slash-path
- Extract/merge pair uses matching attributes to round-trip sections — `path` attribute extends this

### Integration Points
- verify-xml-refs.py findings feed into extract-edit-xml.py grouping
- extract-edit-xml.py output feeds into audit-fixer.md, which feeds into merge-edit-xml.py
- sync-edits-to-xml.py is the markdown→XML sync path (alternative to write-section.py generation path)
- prepare-prose-verify.py output feeds into the prose verification step

</code_context>

<deferred>
## Deferred Ideas

- Writer agent prompt changes for per-heading emission — Phase 21
- End-to-end audit convergence verification on road-runner — Phase 21
- Stale writer modernization — separate effort

</deferred>

---

*Phase: 20-recursive-pipeline-script-updates*
*Context gathered: 2026-04-01 via context import*
