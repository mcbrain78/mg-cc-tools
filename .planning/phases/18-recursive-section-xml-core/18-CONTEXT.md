# Phase 18: Recursive Section XML Core - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/recursive-section-xml/phase-docs/phase-18-recursive-section-xml-core.md)

<domain>
## Phase Boundary

xml_doc.py supports recursive section nesting with `_find_section_by_path`, `walk_sections`, `get_section_paths`, and path-based navigation functions, and schema.md documents the nested XML model.

Currently each `##` heading becomes a flat `<section>` with one `<refs>` block and one `<body>` CDATA containing all `###`/`####` content as unstructured text. This phase makes the XML tree mirror the heading hierarchy so every heading level gets its own `<section>` with its own refs and body.

</domain>

<decisions>
## Implementation Decisions

### XML element model
- One element type (`<section>`), recursively nested — no `<subsection>` or depth-specific types (D1)
- Every heading level (`##`, `###`, `####`, `#####`) produces its own `<section>` — no depth cutoff (D3)
- A section's `<body>` holds only text between its heading and the first child heading — never child content (D2)
- A section's `<refs>` correspond to its `<body>` only — refs match body, always (D6)
- Sections with no child headings work exactly as today (leaf sections)
- `<!-- section: slug -->` markers at every heading level, same pattern, no depth-specific variants

### parse_xml_doc return format
- Returns nested section dicts mirroring the XML tree
- Each section dict has keys: `slug`, `body`, `refs`, `children` (list, may be empty for leaf sections)
- Top-level `sections` is still a list of `##`-level sections
- Each section's `children` contains its nested `###`-level sections, and so on recursively

### walk_sections helper
- New function in `xml_doc.py`: `walk_sections(sections, prefix="")` yields `(path, section_dict)` tuples in depth-first order
- Path is slash-separated: `"monitoring-alerting/etl-run-logging"`
- Used by scripts that need flat iteration over the full tree

### Path-based navigation
- All functions that currently accept a bare `slug` parameter (`update_section_body`, `update_section_refs`, `_find_section`) change to accept a slash-separated path
- A bare slug is a valid path (depth 1) — backward-compatible for top-level sections
- `get_section_slugs(tree)` renamed to `get_section_paths(tree)` — returns slash-separated paths for all sections at all depths

### _find_section_by_path
- Shared implementation in `xml_doc.py` used by `_find_section()` and all downstream scripts (extract, merge, verify)
- Walks the XML tree level by level, matching each slug segment against child `<section>` elements
- Replaces current flat `findall("section")` lookup

### Slug uniqueness
- Slugs must be unique among siblings, not globally (D5)
- Two sections can have a `### Prerequisites` heading under different parents
- Path resolution relies on sibling uniqueness — each path resolves to exactly one node

### Ref tracking model
- Each section's refs declare exactly the entities mentioned in that section's body — no more, no less (D6)
- If the same entity appears in parent's body and child's body, both sections declare it
- If entity only appears in child's body, only the child declares it
- A ref in parent's `<refs>` that only appears in child's body correctly fails parent's audit

### Backward compatibility
- Clean cutover — no code that reads both old and new formats (D4)
- Old flat-section XML files are regenerated from scratch, not migrated
- No migration tool

### schema.md updates
- Updated XML examples showing nested `<section>` elements
- Updated ref type documentation reflecting per-section ref scoping
- Examples at 2-3 levels of nesting

### Claude's Discretion
- Internal implementation of `build_xml_doc` recursive builder (algorithm for constructing nested elements)
- How `add_section` handles the tree insertion (whether it validates parent existence, error behavior)
- Test organization and parameterization strategy for round-trip tests
- Whether `_find_section_by_path` raises or returns None on miss (concept shows returning None)

</decisions>

<specifics>
## Specific Ideas

- XML structure example from concept showing 3-level nesting (monitoring-alerting → etl-run-logging → artifact-format)
- `walk_sections` signature: `walk_sections(sections, prefix="")` yielding `(path, section_dict)` — exact signature specified
- `_find_section_by_path` reference implementation provided in concept (iterative slug matching with `findall("section")`)
- `parse_xml_doc` return format specified with exact JSON structure including `children` key
- Path derivation helpers: leaf slug via `path.rsplit("/", 1)[-1]`, parent path via `path.rsplit("/", 1)[0]`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `xml_doc.py` already has `build_xml_doc`, `parse_xml_doc`, `_find_section`, `update_section_body`, `update_section_refs`, `get_section_slugs` — these are extended, not replaced
- Existing `serialize_xml_doc` handles XML serialization — must be updated for recursive structure

### Established Patterns
- `xml_doc.py` uses `xml.etree.ElementTree` for XML manipulation — same library, same approach
- Section dicts already have `slug`, `body`, `refs` keys — `children` is the new addition
- CDATA wrapping pattern for `<body>` content is unchanged

### Integration Points
- Every downstream script imports from `xml_doc.py` — changes here ripple to Phases 19, 20, 21
- `_find_section_by_path` becomes the shared navigation primitive consumed by extract-edit-xml.py, merge-edit-xml.py, verify-xml-refs.py (Phase 20)
- `walk_sections` becomes the shared iteration primitive for flat traversal of nested trees

</code_context>

<deferred>
## Deferred Ideas

- write-section.py `--parent` flag and nested state format — Phase 19
- assemble-markdown.py recursive concatenation — Phase 19
- Downstream pipeline script updates (verify, extract, merge, sync, prepare, load-audit) — Phase 20
- Writer agent prompt changes for per-heading emission — Phase 21
- Stale writer modernization (end-user-writer, developer-writer, agent-writer) — separate effort, not in scope

</deferred>

---

*Phase: 18-recursive-section-xml-core*
*Context gathered: 2026-04-01 via context import*
