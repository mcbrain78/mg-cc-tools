---
phase: 07-install-command
plan: 04
subsystem: installer
tags: [bash, install, manifest, python3-check]

# Dependency graph
requires:
  - phase: 07-01
    provides: mg-install-lib.py with update-manifest subcommand
provides:
  - All 11 install.sh scripts call update-manifest after every install
  - 6 previously-missing python3 checks now present
  - Manifest invariant enforced: every install updates the manifest
affects: [07-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [manifest-update-at-end-of-install, python3-check-before-install]

key-files:
  created: []
  modified:
    - debug-triage/install.sh
    - update-backlog/install.sh
    - new-milestone-gsd/install.sh
    - create-context/install.sh
    - gsd-patches/install.sh
    - mg-gsd-wrappers/install.sh
    - codebase-health/install.sh
    - create-docs/install.sh
    - data-provider/install.sh
    - permission-hooks/install.sh
    - cc-regression-test/install.sh

key-decisions:
  - "Manifest update uses TOOL_SOURCE_DIR (resolved from dirname $0) instead of SCRIPT_DIR to keep the block identical and copy-pasteable across all 11 scripts"
  - "python3 check uses hard-fail (exit 1) consistently across all 6 new additions, matching existing patterns in permission-hooks and cc-regression-test"

patterns-established:
  - "Manifest update block: 5-line snippet added at end of every install.sh, after copies/sed, before summary"
  - "python3 check: 4-line guard after source validation, before install section"

requirements-completed: [INST-10]

# Metrics
duration: 2min
completed: 2026-03-18
---

# Phase 7 Plan 4: Modify install.sh Scripts Summary

**Added python3 checks to 6 scripts and manifest update calls to all 11 install.sh scripts, enforcing the invariant that every standalone install updates the tracking manifest**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T23:08:14Z
- **Completed:** 2026-03-17T23:10:37Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Added python3 availability check to 6 install.sh scripts that lacked it (debug-triage, update-backlog, new-milestone-gsd, create-context, gsd-patches, mg-gsd-wrappers)
- Added manifest update call to all 11 install.sh scripts, using consistent TOOL_SOURCE_DIR resolution pattern
- Verified all 11 scripts use $TARGET_DIR (not $INSTALL_DIR) and none use || true on the manifest update call
- Existing test suite (128 tests) passes without regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Add python3 checks to 6 install.sh scripts** - `b316a04` (feat)
2. **Task 2: Add manifest update call to all 11 install.sh scripts** - `f900fe6` (feat)

## Files Created/Modified
- `debug-triage/install.sh` - Simple tool: added python3 check + manifest update
- `update-backlog/install.sh` - Simple tool: added python3 check + manifest update
- `new-milestone-gsd/install.sh` - Simple tool: added python3 check + manifest update
- `create-context/install.sh` - Medium tool: added python3 check + manifest update
- `gsd-patches/install.sh` - Medium tool: added python3 check + manifest update
- `mg-gsd-wrappers/install.sh` - Medium tool: added python3 check + manifest update
- `codebase-health/install.sh` - Complex tool: added manifest update (python3 check already present)
- `create-docs/install.sh` - Complex tool: added manifest update (python3 check already present)
- `data-provider/install.sh` - Complex tool: added manifest update (python3 check already present as warning)
- `permission-hooks/install.sh` - Hook tool: added manifest update (python3 check already present)
- `cc-regression-test/install.sh` - Hook tool: added manifest update (python3 check already present)

## Decisions Made
- Used TOOL_SOURCE_DIR as the variable name in the manifest update block (rather than reusing SCRIPT_DIR) to keep the block self-contained and copy-pasteable without collision with existing SCRIPT_DIR variables
- Left data-provider's warning-only python3 check as-is (not a hard fail) per plan instructions; the manifest update call will hard-fail if python3 is truly missing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 11 install.sh scripts now update the manifest on every install
- Plan 07-05 (validation on road-runner) can verify end-to-end manifest tracking
- The manifest invariant is complete: every install path updates the manifest

---
*Phase: 07-install-command*
*Completed: 2026-03-18*
