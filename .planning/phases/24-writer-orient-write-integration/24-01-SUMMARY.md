---
phase: 24-writer-orient-write-integration
plan: 01
subsystem: auto-doc
tags: [generate-setup, refined-templates, stale-detection, tdd]

# Dependency graph
requires:
  - phase: 23-template-refiner-pipeline
    provides: refined template format with REFINED metadata comment at .mg/docs/templates/{audience}/{DOCUMENT}.template.md
provides:
  - detect_refined_templates() function in generate-setup.py
  - _check_stale() function with YYYY-MM-DD date normalization
  - _has_headings() function for empty template validation
  - refined_templates dict and stale_templates list in generate-setup.py JSON output
affects: [24-writer-orient-write-integration plan 03 (generate command routing uses refined_templates dict)]

# Tech tracking
tech-stack:
  added: []
  patterns: [date-normalization-to-10-chars for ISO 8601 and date-only format comparison]

key-files:
  created: []
  modified:
    - auto-doc/scripts/generate-setup.py
    - auto-doc/scripts/tests/test_generate_setup.py

key-decisions:
  - "Refined template detection integrated into generate-setup.py (not separate script) to keep all generate metadata in one JSON output"
  - "Date comparison uses [:10] slice normalization to handle both YYYY-MM-DD and ISO 8601 formats"
  - "_has_headings validates templates have at least one ## heading to prevent empty generation"
  - "Direct function testing via importlib alongside CLI integration tests for comprehensive coverage"

patterns-established:
  - "Refined template path convention: .mg/docs/templates/{audience}/{DOCUMENT}.template.md"
  - "Stale detection via REFINED comment scan date vs current scan_date comparison"

requirements-completed: [OWI-02, OWI-03]

# Metrics
duration: 4min
completed: 2026-04-02
---

# Phase 24 Plan 01: Refined Template Detection Summary

**generate-setup.py extended with detect_refined_templates(), _check_stale(), and _has_headings() functions producing refined_templates dict and stale_templates list in JSON output**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-02T19:36:03Z
- **Completed:** 2026-04-02T19:40:25Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Added refined template detection for each audience/document pair via generate-setup.py
- Added stale template warning with YYYY-MM-DD date normalization for ISO 8601 compatibility
- Added empty template validation (_has_headings) to prevent null-content generation
- 16 new tests covering helper functions, detection logic, and full CLI integration
- Full auto-doc test suite green (748 tests, 0 failures)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for refined template detection** - `7e6ddba` (test)
2. **Task 1 GREEN: Implement refined template detection** - `21a6ea3` (feat)

_Note: TDD task with RED + GREEN commits. No refactoring needed._

## Files Created/Modified
- `auto-doc/scripts/generate-setup.py` - Added _read_scan_date(), _has_headings(), _check_stale(), detect_refined_templates(); integrated into main() JSON output
- `auto-doc/scripts/tests/test_generate_setup.py` - Added 16 new tests across TestCheckStale, TestDetectRefinedTemplates, and TestRefinedTemplatesCLI classes

## Decisions Made
- Refined template detection integrated into generate-setup.py (not a separate script) to keep all generate metadata in one JSON output
- Date comparison uses `[:10]` slice normalization to handle both YYYY-MM-DD and ISO 8601 formats (per Pitfall 4)
- `_has_headings` validates templates have at least one `##` heading to prevent empty generation (per Pitfall 5)
- Direct function testing via importlib alongside CLI integration tests for comprehensive coverage

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `refined_templates` dict and `stale_templates` list are now available in generate-setup.py JSON output
- Plan 02 (devops-writer rewrite) and Plan 03 (generate command routing) can consume this data to route writers

---
*Phase: 24-writer-orient-write-integration*
*Completed: 2026-04-02*
