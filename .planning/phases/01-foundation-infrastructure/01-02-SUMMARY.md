---
phase: 01-foundation-infrastructure
plan: 02
subsystem: infra
tags: [python, json, cli, classification, merge, notes]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Shared lib modules (json_io.py, git_helpers.py) for atomic JSON I/O"
provides:
  - "add-note.py: atomic note append to notes-inbox.json with sequential IDs"
  - "classify-note.py: deterministic keyword-based note classification to audience/document/section"
  - "merge-scan.py: per-audience scan result merging into single docs-scan.json"
affects: [01-03, 01-04, 03-scan-pipeline, 04-generate-pipeline, 05-verify-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: [keyword-classification-with-confidence, per-audience-scan-merge, sequential-id-generation]

key-files:
  created:
    - create-docs/scripts/add-note.py
    - create-docs/scripts/classify-note.py
    - create-docs/scripts/merge-scan.py
    - create-docs/scripts/tests/test_add_note.py
    - create-docs/scripts/tests/test_classify_note.py
    - create-docs/scripts/tests/test_merge_scan.py
  modified: []

key-decisions:
  - "Confidence uses top_score/total_score formula (not just top/second) to penalize multi-audience ambiguity below 0.5"
  - "merge-scan.py processes all *.json in scan-dir (no scan- prefix filter) for flexibility"
  - "Gap analysis merges as sorted union to ensure deterministic output"

patterns-established:
  - "Keyword classification: count matches per category, normalize by category size, confidence = top/total"
  - "Sequential ID with gap handling: parse max existing NOTE-NNN, add 1 (not length+1)"
  - "Scan merge deduplication: source_material by key (keep more source_files), staleness by (doc,section) keeping highest severity"

requirements-completed: [INF-01, INF-02, INF-04]

# Metrics
duration: 6min
completed: 2026-03-16
---

# Phase 1 Plan 2: Data Flow Scripts Summary

**Three CLI scripts for note lifecycle (add, classify) and scan merging, with 29 passing tests using TDD**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-16T12:21:34Z
- **Completed:** 2026-03-16T12:28:00Z
- **Tasks:** 2
- **Files created:** 6

## Accomplishments

- Implemented add-note.py for atomic note append with sequential NOTE-NNN IDs, ISO timestamps, optional phase/file context, and auto-creation of missing inbox files
- Implemented classify-note.py with keyword-based audience classification using normalized scoring across 4 audiences (devops, developers, end-users, agents) and confidence scoring that penalizes multi-audience ambiguity
- Implemented merge-scan.py that merges per-audience scan JSON files with deduplication of source material (by source file count) and staleness reports (by severity), plus union-merge for gap analysis
- All 29 tests pass across 3 test files, full project suite at 213 tests with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: add-note.py and classify-note.py with tests** - `31f83e0` (test), `720caaf` (feat)
2. **Task 2: merge-scan.py with tests** - `736e92d` (test), `c2237e8` (feat)

_Note: TDD tasks have separate test (RED) and implementation (GREEN) commits._

## Files Created/Modified

- `create-docs/scripts/add-note.py` - Atomic note append to notes-inbox.json (100 lines)
- `create-docs/scripts/classify-note.py` - Deterministic keyword-based note classification (161 lines)
- `create-docs/scripts/merge-scan.py` - Per-audience scan result merger (230 lines)
- `create-docs/scripts/tests/test_add_note.py` - 8 tests for add-note.py (192 lines)
- `create-docs/scripts/tests/test_classify_note.py` - 11 tests for classify-note.py (181 lines)
- `create-docs/scripts/tests/test_merge_scan.py` - 10 tests for merge-scan.py (424 lines)

## Decisions Made

- Used `top_score / total_score` instead of `top_score / (top_score + second_score)` for confidence calculation -- this properly penalizes notes that match keywords across 3-4 audiences (confidence drops below 0.5 for ambiguous notes)
- merge-scan.py processes all `*.json` files in the scan directory rather than filtering by `scan-` prefix -- more flexible and the scan directory is already scoped
- Gap analysis merges use sorted sets for deterministic output (important for testing and diff-friendliness)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed confidence formula for ambiguous notes**
- **Found during:** Task 1 (classify-note.py implementation)
- **Issue:** Original `top / (top + second)` formula always produces >= 0.5, making the "ambiguous note < 0.5 confidence" test impossible
- **Fix:** Changed to `top / total` (sum of all audience scores) so multi-audience ambiguity properly reduces confidence
- **Files modified:** create-docs/scripts/classify-note.py
- **Verification:** Test with 4-audience ambiguous text now produces confidence 0.31
- **Committed in:** 720caaf (part of task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary for correctness -- the plan's test specification required confidence < 0.5 for ambiguous notes.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- add-note.py ready for Phase 5's /mg:add-docs command to invoke
- classify-note.py ready for Phase 3's scan pipeline and Phase 5's /mg:add-docs
- merge-scan.py ready for Phase 3's scan orchestrator to merge per-audience results
- All scripts use the shared lib/json_io.py established in Plan 01
- Test patterns established for remaining scripts (check-references, staleness-check) in Plan 03

## Self-Check: PASSED

All 6 created files verified present. All 4 task commits verified in git log.

---
*Phase: 01-foundation-infrastructure*
*Completed: 2026-03-16*
