---
phase: 22-heading-iterator-script
plan: 01
subsystem: auto-doc
tags: [python, template-parsing, state-machine, iterator, json-io, tdd]

# Dependency graph
requires:
  - phase: 21-writer-agent-per-heading-emission
    provides: Per-heading emission pattern and devops-writer integration point
provides:
  - next-heading.py script-gated heading iterator for writer agent loop
  - Template parser extracting heading tree with PURPOSE/EXAMPLE comments
  - Orient/write/done JSON response protocol for depth-first heading iteration
  - Heading path convention compatible with write-section.py --section/--parent
affects: [23-template-refiner-pipeline, 24-writer-orient-write-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-phase response cycle: orient at ## boundaries, then write per heading"
    - "HTML comment stripping before heading detection to avoid EXAMPLE block false positives"
    - "Flat emission queue built during init, sequential pop per call"

key-files:
  created:
    - auto-doc/scripts/next-heading.py
    - auto-doc/scripts/tests/test_next_heading.py
  modified: []

key-decisions:
  - "Copied slugify_heading() verbatim from write-section.py for heading_path compatibility rather than extracting to shared lib"
  - "Flat emission queue approach (Pitfall 5): build complete orient/write/done sequence at init, no complex two-index tracking"
  - "Strip HTML comments before heading detection to prevent EXAMPLE block headings from being treated as real template headings (Pitfall 3)"
  - "Done response is idempotent: repeated calls after completion keep returning done without advancing state"

patterns-established:
  - "Orient/write/done response protocol: orient groups source files at ## level, write delivers per-heading content, done signals completion"
  - "Template parsing: regex-based extraction of PURPOSE/EXAMPLE multi-line HTML comments with comment-range exclusion for heading detection"

requirements-completed: [HIT-01, HIT-02, HIT-03, HIT-04, HIT-05, HIT-06, HIT-07]

# Metrics
duration: 4min
completed: 2026-04-02
---

# Phase 22 Plan 01: Heading Iterator Script Summary

**Script-gated heading iterator parsing refined templates into depth-first orient/write/done JSON responses with source file grouping at ## boundaries**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-02T18:21:02Z
- **Completed:** 2026-04-02T18:25:30Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Built next-heading.py following next-section.py state machine pattern with template parsing on first call
- Template parser correctly handles multi-line PURPOSE/EXAMPLE HTML comments and excludes headings inside EXAMPLE blocks
- Orient responses at each ## section boundary carry source_files from scan's source_material_index and depth-first heading_outline
- Write responses include heading_path, level, purpose, example with parent_path for ###/#### headings (absent for ## headings)
- 39 tests covering all 7 HIT requirements pass, full 732-test suite green

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Failing tests for all HIT requirements** - `976c628` (test)
2. **Task 2: GREEN - Implement next-heading.py** - `fa04ddf` (feat)

_Note: TDD plan with RED/GREEN phases. No REFACTOR needed -- implementation is clean._

## Files Created/Modified
- `auto-doc/scripts/next-heading.py` - Script-gated heading iterator with template parser and state machine
- `auto-doc/scripts/tests/test_next_heading.py` - 39 tests covering CLI, parsing, orient, write, done, ordering, and path conventions

## Decisions Made
- Copied slugify_heading() verbatim from write-section.py rather than extracting to shared lib -- correctness over refactoring
- Used flat emission queue (build full sequence at init) per RESEARCH.md Pitfall 5 recommendation -- simpler than two-index tracking
- Strip HTML comments before heading detection to solve Pitfall 3 (headings inside EXAMPLE blocks)
- Done response idempotent: index stays at done position, repeated calls re-emit done

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- next-heading.py ready for Phase 23 (template refiner) to produce refined templates it can parse
- Orient/write/done response protocol ready for Phase 24 (writer orient-write integration) to consume
- heading_path convention validated against write-section.py --section/--parent expectations

## Self-Check: PASSED

- [x] auto-doc/scripts/next-heading.py exists
- [x] auto-doc/scripts/tests/test_next_heading.py exists
- [x] 22-01-SUMMARY.md exists
- [x] Commit 976c628 (RED) exists
- [x] Commit fa04ddf (GREEN) exists

---
*Phase: 22-heading-iterator-script*
*Completed: 2026-04-02*
