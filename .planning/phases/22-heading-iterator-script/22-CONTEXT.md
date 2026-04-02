# Phase 22: Heading Iterator Script - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/prepare-templates/phase-docs/phase-22-heading-iterator-script.md)

<domain>
## Phase Boundary

next-heading.py parses refined templates, manages heading queue state, and returns orient/write/done responses with correct depth-first ordering and source file grouping

</domain>

<decisions>
## Implementation Decisions

### CLI interface
- 4 required arguments: `--state-file`, `--template`, `--scan-file`, `--document`
- State file path: `.mg/docs/tmp/heading-state-{audience}.json` — persists parsed template state between calls
- Template path: `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` — the refined template to parse
- Scan file: `.mg/docs/docs-scan.json` — source of `source_material_index` for source file lookups
- Document: the document identifier (e.g., OPERATIONS) used as key prefix in `source_material_index`

### Template parsing (first call)
- On first invocation, parse the refined template: extract heading tree, `<!-- PURPOSE: ... -->` comment, and `<!-- EXAMPLE: ... -->` block per heading
- Look up source files from `source_material_index` in scan file using `{DOCUMENT}/{section-slug}` keys (## section slugs only)
- Persist all parsed state to `--state-file` as JSON for subsequent calls
- Subsequent calls read state from the state file — no re-parsing

### Response types — three JSON response formats
- **Orient response** (emitted at each `##` section boundary): `{"type": "orient", "section": "{slug}", "heading_outline": ["{slug}", "{slug}/{child-slug}", ...], "source_files": [...]}`
- **Write response** (emitted for every heading including `##` itself): `{"type": "write", "heading_path": "{slug}/{child-slug}", "level": 3, "purpose": "...", "example": "...", "parent_path": "{slug}"}`
- **Done response** (emitted after all headings processed): `{"done": true, "headings_processed": N}`

### Processing flow and ordering
- Depth-first traversal through the heading tree
- Orient emitted at each `##` section boundary — before any writes for that section
- Write emitted for every heading: the `##` heading itself first, then its `###` children depth-first, then `####` grandchildren
- For `##`-level write responses, `parent_path` is omitted (no parent)
- Sequence: orient → write × N → orient → write × N → ... → done

### Source file grouping
- Source files are grouped at `##` granularity — looked up from `source_material_index` using `{DOCUMENT}/{section-slug}` keys
- Orient response carries the source file list for the entire `##` section
- Write responses do NOT include source files — the writer already loaded them during orient
- No per-heading source file assignment

### heading_path convention
- Slash-separated path: `{section-slug}/{child-slug}/{grandchild-slug}`
- Maps to write-section.py: last segment → `--section`, everything before → `--parent`
- For `##`-level headings (no `/` in path), `--parent` is omitted

### Design pattern
- Follow the proven `next-section.py` pattern from the verify pipeline — same loop mechanic (call script, process response, call again)
- Script prevents writer from reading ahead — keeps working context focused on one heading at a time
- Writer prompt becomes stateless per heading — state lives in the script

### Verification requirements
- Unit test the orient/write cycle: depth-first ordering, correct source file grouping at `##` boundaries, orient-to-write transitions, done signaling
- Template parsing test: given a refined template, verify the parsed heading tree matches the template's heading hierarchy with correct PURPOSE and EXAMPLE extraction

### Claude's Discretion
- Internal data structures for heading tree representation (list of dicts, tree of nodes, etc.)
- State file JSON schema — the internal format of the persisted state
- Error handling: malformed templates, missing scan data, missing source_material_index keys
- Exact parsing strategy for `<!-- PURPOSE: -->` and `<!-- EXAMPLE: -->` HTML comments (regex, html.parser, line-by-line)
- Whether to validate the refined template's `<!-- REFINED: -->` metadata or just pass it through
- Test fixture design and structure

</decisions>

<specifics>
## Specific Ideas

- Orient response `heading_outline` is slugs only (lightweight) — no PURPOSE/EXAMPLE content. This keeps the orient payload small for the writer's "what am I reading for" orientation
- The refined template format uses HTML comments (`<!-- PURPOSE: ... -->`, `<!-- EXAMPLE: ... -->`) which may span multiple lines — the parser must handle multi-line HTML comments
- `source_material_index` keys in the scan follow `{DOCUMENT}/{section-slug}` format — the script joins `--document` arg with each `##` section's slug to look up source files
- See `auto-doc/scripts/next-section.py` for the pattern to follow (verify pipeline's section iterator)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auto-doc/scripts/next-section.py`: The verify pipeline's section iterator — same loop pattern (script manages queue, caller processes one item at a time). Direct architectural reference for next-heading.py
- `auto-doc/scripts/write-section.py`: The emission script the writer calls — next-heading.py's `heading_path` convention must produce values compatible with write-section.py's `--section` and `--parent` args

### Established Patterns
- Script-gated loops: The project uses Python scripts as state machines that the LLM calls in a loop. The script controls ordering and state; the LLM controls actions. next-heading.py follows this pattern
- JSON response to stdout: All pipeline scripts communicate via JSON on stdout. next-heading.py follows this convention
- State file persistence: Scripts that manage multi-call state use `--state-file` JSON files in `.mg/docs/tmp/`

### Integration Points
- `source_material_index` in `docs-scan.json`: next-heading.py reads this at initialization to map `##` sections to source files
- Refined template at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`: next-heading.py's primary input — produced by Phase 23's template refiner
- Writer agent prompt: Phase 24's devops-writer calls next-heading.py in a loop — the response format is the contract between them

</code_context>

<deferred>
## Deferred Ideas

- Parallel heading writes — sibling headings could be parallelized since they share source context, but sequential loop is simpler and sufficient
- Per-heading source file assignment — source files stay at `##` granularity; splitting to `###` would require refiner changes
- Merge mode for refined templates — overwrite only for now

</deferred>

---

*Phase: 22-heading-iterator-script*
*Context gathered: 2026-04-02 via context import*
