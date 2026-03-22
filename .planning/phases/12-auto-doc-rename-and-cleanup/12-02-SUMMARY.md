---
phase: 12-auto-doc-rename-and-cleanup
plan: 02
subsystem: tooling
tags: [auto-doc, bugfix, staleness-check, note_id, merge-scan, schema-contract]

# Dependency graph
requires:
  - phase: 12-auto-doc-rename-and-cleanup
    provides: Renamed auto-doc directory with all commands, agents, scripts, references
provides:
  - staleness-check.py CLI output wrapped in {"staleness_report": [...]} for merge-scan.py
  - add-note.py and classify-note.py using note_id field matching schema contract
  - add-note.py JSON stdout output for command file consumption
  - Scan pipeline without dead check-references.py call
affects: [13-auto-doc-script, 14-auto-doc-reference-manifest]

# Tech tracking
tech-stack:
  added: []
  patterns: [dual-output pattern (function returns raw data, CLI wraps for consumers)]

key-files:
  created: []
  modified:
    - auto-doc/scripts/staleness-check.py
    - auto-doc/scripts/tests/test_staleness_check.py
    - auto-doc/scripts/add-note.py
    - auto-doc/scripts/tests/test_add_note.py
    - auto-doc/scripts/classify-note.py
    - auto-doc/scripts/tests/test_classify_note.py
    - auto-doc/commands/auto-doc-scan.md

key-decisions:
  - "staleness-check.py internal check_staleness() returns bare list, CLI wraps in dict -- dual-output pattern preserves both API usability and merge compatibility"
  - "note_id wins over id per schema contract -- breaking change accepted since add-to-generate round-trip never completed"
  - "check-references.py removed from scan pipeline but kept for verify pipeline (Phase 14 will retire it)"

patterns-established:
  - "Dual-output pattern: function returns raw data for programmatic use, CLI wraps for pipeline consumers"

requirements-completed: [FIX-C1, FIX-C2, FIX-C3, FIX-C4, FIX-C5]

# Metrics
duration: 3min
completed: 2026-03-22
---

# Phase 12 Plan 02: Auto-Doc Bug Fixes Summary

**Fixed staleness-check merge-scan compatibility, note_id schema mismatch, add-note stdout JSON, and dead check-references scan call**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-22T11:28:06Z
- **Completed:** 2026-03-22T11:31:43Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Fixed staleness-check.py CLI output to wrap entries in `{"staleness_report": [...]}` so merge-scan.py can consume staleness data
- Normalized note_id field across add-note.py and classify-note.py to match schema contract
- Added JSON stdout output to add-note.py (`{"note_id": "NOTE-XXX"}`) for command file consumption
- Removed dead check-references.py invocation from scan pipeline (kept alive for verify pipeline)
- All 106 auto-doc tests pass (105 original + 1 new stdout JSON test)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix staleness-check.py output format and remove dead scan call** - `a3f9c5b` (fix)
2. **Task 2: Fix note_id field mismatch and add-note.py stdout JSON** - `497980d` (fix)

## Files Created/Modified
- `auto-doc/scripts/staleness-check.py` - CLI output wrapped in {"staleness_report": entries} for merge-scan.py
- `auto-doc/scripts/tests/test_staleness_check.py` - CLI tests assert dict wrapper with staleness_report key
- `auto-doc/commands/auto-doc-scan.md` - Removed dead check-references.py invocation and refs-check.json mention
- `auto-doc/scripts/add-note.py` - Uses note_id field, prints JSON to stdout, added import json
- `auto-doc/scripts/tests/test_add_note.py` - All assertions use note_id, new test for stdout JSON
- `auto-doc/scripts/classify-note.py` - Inbox lookup uses note_id instead of id
- `auto-doc/scripts/tests/test_classify_note.py` - Test fixture data uses note_id

## Decisions Made
- staleness-check.py dual-output pattern: internal function returns bare list, CLI wraps in dict with staleness_report key -- preserves API usability while fixing merge compatibility
- note_id wins over id per schema contract -- breaking change accepted per CONTEXT.md since add-to-generate round-trip never completed
- check-references.py removed from scan pipeline only -- verify pipeline (auto-doc-verify.md) still uses it; Phase 14 will retire it

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 latent bugs fixed with updated tests
- auto-doc tool family is fully renamed and cleaned up
- Ready for Phase 13 (auto-doc-script command) and subsequent phases
- 106 auto-doc tests and 259 total relevant tests passing

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 12-auto-doc-rename-and-cleanup*
*Completed: 2026-03-22*
