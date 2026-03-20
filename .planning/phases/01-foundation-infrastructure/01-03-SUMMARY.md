---
phase: 01-foundation-infrastructure
plan: 03
subsystem: infra
tags: [python, verification, git, staleness, references, testing]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Shared lib modules (json_io.py, git_helpers.py)"
provides:
  - "check-references.py for file path and symbol verification in docs"
  - "staleness-check.py for git-based section freshness analysis"
  - "30 passing tests across both scripts"
affects: [03-scan-pipeline, 05-verify-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: [docs-meta-parsing, importlib-hyphen-module-loading, git-repo-detection]

key-files:
  created:
    - create-docs/scripts/check-references.py
    - create-docs/scripts/staleness-check.py
    - create-docs/scripts/tests/test_check_references.py
    - create-docs/scripts/tests/test_staleness_check.py
  modified: []

key-decisions:
  - "Used hyphenated filenames (check-references.py, staleness-check.py) matching codebase-health convention; tests use importlib.machinery.SourceFileLoader for import"
  - "Symbol detection is best-effort regex (ClassName.method pattern) not full AST -- catches obvious broken refs without external deps"
  - "staleness-check only uses subprocess for git rev-parse (is-git-repo check); all git log operations go through lib/git_helpers"

patterns-established:
  - "Hyphen-filename import: Use importlib.machinery.SourceFileLoader for testing scripts with hyphenated names"
  - "docs-meta parsing: Regex extracts JSON from <!-- docs-meta: {...} --> HTML comments"
  - "Staleness severity: high = deleted source or 3+ changes, medium = 1-2 changes, low = unknown"

requirements-completed: [INF-03, INF-05]

# Metrics
duration: 6min
completed: 2026-03-16
---

# Phase 1 Plan 3: Verification Scripts Summary

**check-references.py and staleness-check.py with 30 passing tests for doc reference validation and git-based freshness analysis**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-16T12:21:19Z
- **Completed:** 2026-03-16T12:27:25Z
- **Tasks:** 2
- **Files created:** 4

## Accomplishments

- Implemented check-references.py that scans markdown docs for backtick-wrapped file paths and code block symbol references, validates them against the project root, and outputs JSON issues with file/line/reference/status
- Implemented staleness-check.py that parses docs-meta HTML comments, uses lib/git_helpers to detect stale sections, assigns severity levels, and suggests corrective actions
- Both scripts handle edge cases: empty dirs, URLs, anchors, non-git repos, deleted source files, malformed metadata
- All 30 tests pass (16 for check-references, 14 for staleness-check) with no regressions to existing 154+ tests

## Task Commits

Each task was committed atomically:

1. **Task 1: check-references.py with tests (TDD)**
   - `fc6bb96` test(01-03): add failing tests for check-references.py
   - `b19dfe0` feat(01-03): implement check-references.py with passing tests

2. **Task 2: staleness-check.py with tests (TDD)**
   - `0d73d5c` test(01-03): add failing tests for staleness-check.py
   - `21412ae` feat(01-03): implement staleness-check.py with passing tests

## Files Created/Modified

- `create-docs/scripts/check-references.py` - File path and symbol reference verification (365 lines)
- `create-docs/scripts/staleness-check.py` - Git-based section freshness analysis (302 lines)
- `create-docs/scripts/tests/test_check_references.py` - 16 tests for check-references (324 lines)
- `create-docs/scripts/tests/test_staleness_check.py` - 14 tests for staleness-check (373 lines)

## Decisions Made

- Used hyphenated filenames (check-references.py, staleness-check.py) to match the existing codebase-health script naming convention; tests use importlib.machinery.SourceFileLoader to import them
- Symbol detection uses best-effort regex for ClassName.method() patterns rather than full AST analysis -- catches obvious broken references without added complexity
- staleness-check.py uses subprocess only for the is-git-repo check (git rev-parse --git-dir); all actual git log operations go through lib/git_helpers as required

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- check-references.py ready for Phase 5 verify command to use for reference integrity checks
- staleness-check.py ready for Phase 3 scan pipeline and Phase 4 generate-update for detecting stale sections
- Both scripts use lib/ modules as specified, maintaining the established import patterns
- 30 new tests plus all 154+ existing tests pass

## Self-Check: PASSED

All 4 created files verified present. All 4 task commits verified in git log.

---
*Phase: 01-foundation-infrastructure*
*Completed: 2026-03-16*
