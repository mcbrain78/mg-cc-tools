---
phase: 11-add-tooling-to-install-command
plan: 02
subsystem: install-tooling
tags: [python, cli, subcommands, tdd, argparse, json-io]

# Dependency graph
requires:
  - phase: 10-create-a-renderer-for-the-install-command
    provides: render-status-table, render-tool-picker, resolve-tool-selection subcommands and _get_ordered_tools shared helper
provides:
  - get-install-plan subcommand with three install patterns and expected_action computation
  - render-preflight subcommand with PASS/FAIL markers and required/optional grouping
  - record-result subcommand with append-only JSON result tracking
  - render-summary subcommand with action counts, tool table, and capabilities section
  - render-validation subcommand with PASS/WARNING output
  - preflight --output file-based I/O support
  - _get_temp_dir per-target temp directory utility
affects: [11-add-tooling-to-install-command plan 03]

# Tech tracking
tech-stack:
  added: []
  patterns: [append-only JSON result file, render subcommand three-layer pattern, per-target temp directory isolation]

key-files:
  created: []
  modified:
    - install/scripts/mg-install-lib.py
    - install/scripts/tests/test_mg_install_lib.py

key-decisions:
  - "render_summary counts 'installed' and 'updated/reinstalled' as separate categories for summary line"
  - "record-result uses mutually exclusive argparse group for --success/--failed enforcement"
  - "get-install-plan compact stdout returns tool+pattern+post_install (enough for install loop)"
  - "render-preflight shows version for passed checks, error message for failed checks"

patterns-established:
  - "Append-only JSON: record-result creates file with [] if missing, reads-appends-rewrites"
  - "Three-layer subcommand: pure function + CLI handler + argparse wiring (consistent with Plan 01)"

requirements-completed: [INST-46, INST-47, INST-48, INST-49, INST-50, INST-55, INST-56, INST-57]

# Metrics
duration: 8min
completed: 2026-03-20
---

# Phase 11 Plan 02: Install Plan, Result Tracking, and Renderers Summary

**Five new subcommands (get-install-plan, render-preflight, record-result, render-summary, render-validation) plus preflight --output and _get_temp_dir utility, all TDD with 36 tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-20T15:41:12Z
- **Completed:** 2026-03-20T15:49:12Z
- **Tasks:** 1 feature (TDD: RED + GREEN + REFACTOR)
- **Files modified:** 2

## Accomplishments
- get-install-plan correctly determines all three install patterns (copy_only, copy_configure, execute_only) and computes expected_action with " (configured)" suffix
- record-result provides reliable append-only result tracking, creating file on first call and appending on subsequent calls
- render-preflight, render-summary, and render-validation produce deterministic human-readable output replacing LLM-formatted state reconstruction
- preflight gained --output support matching the established scan-status/validate pattern
- _get_temp_dir utility provides per-target temp directory isolation

## Task Commits

Each task was committed atomically (TDD flow):

1. **RED: Failing tests** - `3c3b60f` (test)
2. **GREEN: Implementation** - `a23b273` (feat)
3. **REFACTOR: Python 3.11 compatibility** - `f1f9011` (refactor)

## Files Created/Modified
- `install/scripts/mg-install-lib.py` - Added _get_temp_dir utility, get_install_plan, render_preflight, record_result, render_summary, render_validation functions; modified cmd_preflight for --output; added all CLI handlers and argparse wiring
- `install/scripts/tests/test_mg_install_lib.py` - Added 36 tests across 7 test classes (TestGetTempDir, TestGetInstallPlan, TestPreflightOutput, TestRenderPreflight, TestRecordResult, TestRenderSummary, TestRenderValidation) plus fixture helpers

## Decisions Made
- render_summary classifies actions into installed/updated/failed counts using substring matching ("installed" in action, "updated" or "reinstalled" in action)
- record-result uses argparse mutually_exclusive_group for --success/--failed enforcement at the CLI level (rather than application-level validation)
- get-install-plan compact stdout returns tool+pattern+post_install per entry (enough to drive the install loop without full command lists)
- render-preflight shows version string for passed checks and error message for failed checks on the same line

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Python 3.11 f-string backslash compatibility**
- **Found during:** REFACTOR phase (ruff lint check)
- **Issue:** render_summary used backslash escape in f-string which requires Python 3.12+ (project requires >=3.11)
- **Fix:** Extracted unicode separator to variable before f-string interpolation
- **Files modified:** install/scripts/mg-install-lib.py
- **Verification:** ruff check passes for Plan 02 code; all 151 tests pass
- **Committed in:** f1f9011

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor compatibility fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 new subcommands implemented and tested with 36 tests
- Combined with Plan 01 (scenario logic + action subcommands), all Python subcommands are ready
- Plan 03 (install.md prompt rewrite) can now reference all subcommands

## Self-Check: PASSED

- All created/modified files exist on disk
- All 3 commit hashes verified (3c3b60f, a23b273, f1f9011)
- 151/151 tests pass (85 original + 30 Plan 01 + 36 Plan 02)

---
*Phase: 11-add-tooling-to-install-command*
*Completed: 2026-03-20*
