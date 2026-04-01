---
phase: 20-recursive-pipeline-script-updates
plan: 02
subsystem: auto-doc
tags: [lxml, xml, recursive, path-based, extract, merge, sync, heading-level, tdd]

# Dependency graph
requires:
  - phase: 18-recursive-section-xml-core
    provides: "_find_section_by_path, walk_sections, path-based update_section_body/refs"
  - phase: 19-nested-write-section-assembly
    provides: "walk_sections in assemble-markdown.py (reference implementation)"
provides:
  - "Path-based section extraction in extract-edit-xml.py with path attribute on edit XML"
  - "Path-based merge in merge-edit-xml.py reading path attribute with slug fallback"
  - "Heading-level tree reconstruction in sync-edits-to-xml.py via _infer_paths"
  - "Idempotent extract-merge round-trip for nested sections"
affects: [21-writer-agent-per-heading-emission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Path attribute on edit-group XML section elements for round-trip fidelity"
    - "Stack-based heading-level inference for tree reconstruction from flat markdown"
    - "walk_sections() replaces flat doc['sections'] iteration in sync"

key-files:
  created: []
  modified:
    - "auto-doc/scripts/extract-edit-xml.py"
    - "auto-doc/scripts/merge-edit-xml.py"
    - "auto-doc/scripts/sync-edits-to-xml.py"
    - "auto-doc/scripts/tests/test_extract_edit_xml.py"
    - "auto-doc/scripts/tests/test_merge_edit_xml.py"
    - "auto-doc/scripts/tests/test_sync_edits.py"

key-decisions:
  - "Extract edit XML adds path attribute alongside slug; slug is leaf only for display"
  - "Merge reads path attribute as primary key with slug fallback for backward compat"
  - "_infer_paths uses stack-based algorithm: pop on same-or-shallower, push on deeper"
  - "Heading skip (#### under ##) treated as child relationship (stack handles naturally)"
  - "No-heading body defaults to depth 2 (top-level)"

patterns-established:
  - "Edit-group XML carries path='parent/child' attribute for round-trip addressing"
  - "Stack-based heading-level inference: _infer_paths(md_sections) -> (path, slug, body)"

requirements-completed: [RPS-04, RPS-05, RPS-06]

# Metrics
duration: 7min
completed: 2026-04-01
---

# Phase 20 Plan 02: Extract/Merge/Sync Pipeline Migration Summary

**Path-based extract/merge with edit XML path attribute and stack-based heading-level tree reconstruction in sync**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-01T19:48:10Z
- **Completed:** 2026-04-01T19:55:49Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments
- Migrated extract-edit-xml.py from flat findall("section") to _find_section_by_path, adding path attribute to edit XML
- Migrated merge-edit-xml.py to read path attribute (slug fallback) and use _find_section_by_path for nested merge
- Implemented _infer_paths stack-based algorithm in sync-edits-to-xml.py for heading-level tree reconstruction
- Extract-merge round-trip on nested XML confirmed idempotent
- All 1238 project tests pass (688 auto-doc, 14 new in this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for nested extract/merge** - `c524580` (test)
2. **Task 1 (GREEN): Implement path-based extract/merge** - `efdb307` (feat)
3. **Task 2 (RED): Failing tests for sync heading-level reconstruction** - `420aaa2` (test)
4. **Task 2 (GREEN): Implement sync heading-level reconstruction** - `244a883` (feat)

## Files Created/Modified
- `auto-doc/scripts/extract-edit-xml.py` - Path-based section lookup via _find_section_by_path, path attribute on edit XML sections
- `auto-doc/scripts/merge-edit-xml.py` - Path attribute read with slug fallback, path-based merge via _find_section_by_path
- `auto-doc/scripts/sync-edits-to-xml.py` - _infer_paths stack-based heading-level reconstruction, walk_sections path matching
- `auto-doc/scripts/tests/test_extract_edit_xml.py` - Nested XML fixture helper, 4 new tests for path-based extraction
- `auto-doc/scripts/tests/test_merge_edit_xml.py` - Nested fixture helper, 4 new tests for path-based merge including round-trip
- `auto-doc/scripts/tests/test_sync_edits.py` - 8 new _infer_paths unit tests, 2 nested sync integration tests

## Decisions Made
- Extract edit XML adds `path` attribute alongside `slug`; slug is leaf only (via `rsplit("/", 1)[-1]`) for display/logging
- Merge reads `path` attribute as primary key, falls back to `slug` for backward compatibility with pre-path edit XML
- `_infer_paths` uses stack-based algorithm matching CONTEXT.md design: pop on same-or-shallower heading depth, push on deeper
- Heading skip (e.g., `####` directly under `##`) treated as child -- stack naturally handles this since we only pop on same-or-shallower
- Body with no heading defaults to depth 2 (top-level section), matching RESEARCH.md recommendation
- sync() returns changed paths (not slugs) and --changed-only emits paths

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three extract/merge/sync scripts now handle nested sections via path-based navigation
- Plan 01 (verify-xml-refs, prepare-prose-verify, load-audit-findings) handles the other three scripts
- Phase 21 (writer agent per-heading emission) can proceed with full recursive pipeline support

## Self-Check: PASSED

All 7 files verified present. All 4 commit hashes verified in git log.

---
*Phase: 20-recursive-pipeline-script-updates*
*Completed: 2026-04-01*
