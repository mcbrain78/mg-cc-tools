---
phase: 17-auto-doc-generate-docs-improvements
plan: 01
subsystem: auto-doc
tags: [json, cli, filtering, scan-views, per-audience]

# Dependency graph
requires:
  - phase: 03-scan-pipeline
    provides: docs-scan.json contract and source_material_index structure
provides:
  - Per-audience and glossary scan view splitter (split-scan-by-audience.py)
  - Audience mode filtering by document prefix
  - Glossary mode with basename reduction
affects: [17-02-generate-orchestrator, auto-doc-generate]

# Tech tracking
tech-stack:
  added: []
  patterns: [view-file splitting from shared JSON contract, .get() defaults for missing keys]

key-files:
  created:
    - auto-doc/scripts/split-scan-by-audience.py
    - auto-doc/scripts/tests/test_split_scan_by_audience.py
  modified: []

key-decisions:
  - "Empty gap_analysis in input passes through as empty dict (not structured skeleton)"
  - "Audience mode validates --audience and --documents at runtime, not argparse required"

patterns-established:
  - "View file pattern: same 4 top-level keys as full scan for drop-in compatibility with writer agents"
  - "Glossary basename reduction: os.path.basename for source_files to reduce noise for term discovery"

requirements-completed: [GEN-08, GEN-09, GEN-11, GEN-12]

# Metrics
duration: 2min
completed: 2026-03-23
---

# Phase 17 Plan 01: Split Scan by Audience Summary

**CLI script that splits docs-scan.json into per-audience filtered view files (~5k tokens each) and glossary view with basename-reduced source_files**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-23T23:02:55Z
- **Completed:** 2026-03-23T23:05:37Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- split-scan-by-audience.py with audience and glossary modes following all project conventions
- 15 test cases covering audience filtering, glossary basename reduction, key structure, and edge cases
- Full auto-doc test suite passes (133 tests, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests (TDD RED)** - `f54acc1` (test)
2. **Task 2: Implement script (TDD GREEN)** - `e3e2bbe` (feat)

_TDD plan: RED phase committed 15 failing tests, GREEN phase implemented script to pass all tests._

## Files Created/Modified
- `auto-doc/scripts/split-scan-by-audience.py` - Per-audience and glossary scan view splitter (audience mode filters source_material_index by document prefix, glossary mode preserves all keys with basename-reduced source_files)
- `auto-doc/scripts/tests/test_split_scan_by_audience.py` - 15 test cases via subprocess CLI invocation pattern

## Decisions Made
- Empty gap_analysis passes through as `{}` rather than a structured skeleton with empty arrays -- consistent with "missing produces empty" principle
- Audience mode validates --audience/--documents at runtime (not argparse `required=True`) to allow glossary mode to omit them without argparse errors
- Used shallow dict copy for glossary index entries to avoid mutating the original data

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed gap_analysis default for missing input**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** When gap_analysis is absent from input, `data.get("gap_analysis", {})` returns empty dict which `filter_gap_analysis` converts to `{"undocumented_components": [], "missing_for_audience": {}}` instead of `{}`
- **Fix:** Changed to `data.get("gap_analysis")` (default None) with conditional: only call filter_gap_analysis when raw_gap is truthy
- **Files modified:** auto-doc/scripts/split-scan-by-audience.py
- **Verification:** Test 13 passes
- **Committed in:** e3e2bbe (part of GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- split-scan-by-audience.py ready for integration into generate orchestrator (Plan 17-02)
- Orchestrator will call script once per audience + once for glossary, passing view file paths to writer agents
- install.sh already deploys all scripts/*.py files, so no install changes needed for this script

---
## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 17-auto-doc-generate-docs-improvements*
*Completed: 2026-03-23*
