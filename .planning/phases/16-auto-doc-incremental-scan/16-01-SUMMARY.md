---
phase: 16-auto-doc-incremental-scan
plan: 01
subsystem: auto-doc
tags: [git-diff, incremental-scan, manifests, diff-scope, subprocess]

# Dependency graph
requires:
  - phase: 14-auto-doc-reference-manifest
    provides: per-audience reference manifests for cross-referencing changed files to sections
provides:
  - "diff-scan.py: deterministic diff scoping script producing diff-scope.json"
  - "Reverse index from file paths to (audience, document, section) tuples via manifest cross-referencing"
  - "Git rename detection with old-to-new path mapping"
  - "Optional GSD phase context enrichment"
affects: [16-02, auto-doc-scan, scan-audience]

# Tech tracking
tech-stack:
  added: []
  patterns: [git-subprocess-diff-scoping, manifest-reverse-index, classify-changes-fanout]

key-files:
  created:
    - auto-doc/scripts/diff-scan.py
    - auto-doc/scripts/tests/test_diff_scan.py
  modified: []

key-decisions:
  - "Git operations kept inside diff-scan.py (not added to lib/git_helpers.py) for self-containment -- these are diff-specific, not general-purpose git helpers"
  - "Backdated initial commits in test fixtures (2025-01-01) to ensure reliable timestamp-to-commit resolution across same-second commit scenarios"
  - "classify_changes uses tuple-keyed deduplication dict for O(1) section lookup, producing one entry per audience x document x section"
  - "Corrupt manifests silently skipped with stderr warning, consistent with over-inclusive design philosophy"

patterns-established:
  - "Backdated git fixtures: use GIT_AUTHOR_DATE/GIT_COMMITTER_DATE env vars to create deterministic timestamp gaps in test repos"
  - "deleted_check_fn callback pattern: classify_changes accepts a callable for filesystem checks, enabling pure unit testing with lambda mocks"

requirements-completed: [ISC-02, ISC-03, ISC-06]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 16 Plan 01: diff-scan.py Deterministic Diff Scoping Script Summary

**Deterministic Python script producing diff-scope.json by cross-referencing git diff output against reference manifests with optional GSD phase enrichment**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T22:05:21Z
- **Completed:** 2026-03-22T23:02:33Z
- **Tasks:** 2 (TDD RED + GREEN; no refactor needed)
- **Files modified:** 2

## Accomplishments
- Built diff-scan.py (~250 lines production logic) with 6 core functions: resolve_commit, get_changed_files, get_renames, build_file_to_sections_index, classify_changes, discover_gsd_phases
- Comprehensive test suite (28 tests) using real git repos in temp directories covering all edge cases
- Rename detection produces single affected_sections entries with old-to-new mapping (not delete+add pairs)
- GSD context is fully optional -- empty list and null context when --gsd-dir omitted or nonexistent

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Write failing tests** - `de633fd` (test)
2. **Task 2: GREEN - Implement diff-scan.py** - `c4e049a` (feat)

_No refactor commit needed -- code clean as written._

## Files Created/Modified
- `auto-doc/scripts/diff-scan.py` - Deterministic diff scoping script with argparse CLI
- `auto-doc/scripts/tests/test_diff_scan.py` - 28 tests covering all functions and CLI integration

## Decisions Made
- Kept git operations inside diff-scan.py rather than extending lib/git_helpers.py -- these functions are diff-specific (rev-list, diff --name-only, diff --diff-filter=R) and not general-purpose helpers
- Used backdated initial commits (GIT_COMMITTER_DATE=2025-01-01) in test fixtures to avoid same-second timestamp ambiguity in git rev-list --before resolution
- classify_changes uses a deleted_check_fn callback parameter allowing pure unit tests with lambda mocks while the CLI uses os.path.exists
- Corrupt manifest JSON files are skipped with a stderr warning rather than raising errors, consistent with the over-inclusive design philosophy

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Git rev-list --before with same-second timestamps returned HEAD instead of the expected earlier commit, causing empty diffs in tests. Fixed by backdating initial commits in test fixtures to 2025-01-01 to create a clear timestamp gap.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- diff-scope.json output matches the locked schema from CONTEXT.md
- Ready for Plan 02: scan command and agent modifications to consume diff-scope.json
- All 118 existing tests pass (no regressions)

## Self-Check: PASSED

- [x] auto-doc/scripts/diff-scan.py exists
- [x] auto-doc/scripts/tests/test_diff_scan.py exists
- [x] 16-01-SUMMARY.md exists
- [x] Commit de633fd exists (RED)
- [x] Commit c4e049a exists (GREEN)

---
*Phase: 16-auto-doc-incremental-scan*
*Completed: 2026-03-22*
