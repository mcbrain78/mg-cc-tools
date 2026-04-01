# Phase 21: Writer Agent Per-Heading Emission - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/recursive-section-xml/phase-docs/phase-21-writer-agent-per-heading-emission.md)

<domain>
## Phase Boundary

Writer agent prompts emit per-heading sections via write-section.py with `--parent`, section markers appear at every heading level, and end-to-end verification confirms round-trip fidelity and ref precision.

This is the final phase of the recursive section XML feature. It changes how writer agents call write-section.py (finer granularity) and validates the full pipeline end-to-end on road-runner.

</domain>

<decisions>
## Implementation Decisions

### Emission granularity change
- Instead of one `write-section.py` call per `##` heading, the writer calls it once for the `##` intro and once for each `###`, `####`, etc. heading within that section
- Each call emits a small body (5-40 lines) with precisely scoped `typed_refs`
- The writer knows exactly which entities it referenced because it just wrote about them — ref-assignment problem shrinks from "which of 30 refs belong to this 200-line body" to "which refs did I just use in these 3 paragraphs"

### Writer agent prompt changes
- Agent prompts change from "for each `##` section, write content and call `write-section.py`" to "for each `##` section, write the intro and call `write-section.py`, then for each `###` heading write its content and call `write-section.py` with `--parent` set to the `##` slug, then for each `####` heading call with `--parent` set to the `##/###` path"
- The writer already processes sections sequentially from the template — this extends the existing loop to recurse into child headings

### Which writers are updated
- Only current-format agents: `devops-writer.md`, `glossary-writer.md`, `overview-writer.md`
- `end-user-writer.md`, `developer-writer.md`, and `agent-writer.md` are NOT updated — they are on a stale format and need a separate modernization effort first

### Writer markdown output unchanged
- The writer produces the same markdown prose with the same headings it does today (D8)
- Only the emission granularity changes — finer-grained write-section.py calls
- Whether a section should have more or fewer headings is a template/content decision independent of how the XML tracks them

### Section markers
- `<!-- section: slug -->` markers at every heading level in generated documents
- Same marker pattern as today, extended to `###`, `####`, etc. — no depth-specific marker variants

### Refs match body constraint
- Each writer must emit `typed_refs` that correspond exactly to the body being written (D6)
- Per-heading emission makes this natural: the writer just wrote about these entities in a 5-40 line body, so the refs are precisely scoped
- A ref in parent's intro that only appears in child content must be moved to the child's refs

### Claude's Discretion
- Exact prompt wording for the recursive emission loop in each writer agent
- Whether to add a shared "nested emission" instruction block referenced by all writers or inline the pattern in each
- How overview-writer.md handles nesting (overview may not have `###` headings)
- Test strategy for end-to-end verification — which road-runner documents to test against

</decisions>

<specifics>
## Specific Ideas

- Verification criteria from concept:
  - **Audit convergence**: Run audit→fix→audit on road-runner with the new model. Expect fewer new findings introduced by the fix step (smaller bodies constrain agent scope creep)
  - Round-trip fidelity, heading-level coverage, body isolation, ref precision (Phase 18 tests should pass end-to-end)
- The prompt change is an extension of the existing sequential processing loop — "recurse into child headings" is the key addition

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `devops-writer.md`, `glossary-writer.md`, `overview-writer.md` — current-format writer agents, extended for nested emission
- write-section.py `--parent` flag (Phase 19) — the CLI interface writers call
- Existing per-section loop pattern in writer agents — extended to recurse into child headings

### Established Patterns
- Writer agents process sections sequentially from template headings
- Each section write calls write-section.py with `--section`, `--content-file`, `--refs-file`
- Writer agents reference `{SCRIPTS_DIR}` for script paths (install-time sed resolution)

### Integration Points
- Writer agents call write-section.py (Phase 19) with `--parent` flag
- Generated XML is consumed by verify-xml-refs.py (Phase 20) for ref checking
- Generated XML is consumed by assemble-markdown.py (Phase 19) for markdown output
- Section markers in generated markdown are consumed by sync-edits-to-xml.py (Phase 20) for round-trip sync

</code_context>

<deferred>
## Deferred Ideas

- Stale writer modernization (`end-user-writer.md`, `developer-writer.md`, `agent-writer.md`) — separate effort, not part of the recursive section XML feature
- Content restructuring (adding/removing headings) — out of scope per D8

</deferred>

---

*Phase: 21-writer-agent-per-heading-emission*
*Context gathered: 2026-04-01 via context import*
