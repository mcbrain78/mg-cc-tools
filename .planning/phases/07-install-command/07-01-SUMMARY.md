---
phase: 07-install-command
plan: 01
subsystem: installer
tags: [python, argparse, tomllib, sha256, hashlib, fcntl, json, cli]

# Dependency graph
requires: []
provides:
  - mg-install-lib.py with 5 subcommands (scan-status, preflight, update-manifest, validate, adopt)
  - Comprehensive pytest suite covering all subcommands (38 tests)
  - Atomic manifest write pattern with fcntl.flock + tempfile + os.replace
  - CHECKS registry for preflight validation (8 check types)
  - Source checksum computation with include/exclude scope
affects: [07-02, 07-03, 07-04, 07-05]

# Tech tracking
tech-stack:
  added: [tomllib, fcntl]
  patterns: [subcommand-dispatch-via-argparse, atomic-json-with-flock, source-checksum-comparison]

key-files:
  created:
    - install/scripts/mg-install-lib.py
    - install/scripts/tests/__init__.py
    - install/scripts/tests/test_mg_install_lib.py
  modified: []

key-decisions:
  - "Used commands/* (all files) in checksum scope to match what install.sh actually copies, ensuring non-.md files like context-template.snapshot trigger Modified status"
  - "Corrupt check runs before version/checksum comparison since missing commands is more severe than version drift"
  - "WORKSPACE_DIRS maps tool names to expected scaffold directories for validate subcommand"

patterns-established:
  - "Subcommand dispatch: argparse subparsers with set_defaults(func=handler) for clean CLI routing"
  - "Atomic manifest write: fcntl.flock(LOCK_EX) + tempfile.mkstemp + os.replace for concurrent safety"
  - "Source checksum scope: include patterns via pathlib.glob, exclude via substring matching"
  - "Test pattern: shared _make_tool/_make_pyproject/_make_manifest helpers for isolated temp dir tests"

requirements-completed: [INST-01, INST-03, INST-04, INST-05, INST-07, INST-08, INST-12]

# Metrics
duration: 30min
completed: 2026-03-18
---

# Phase 7 Plan 1: mg-install-lib.py Summary

**5-subcommand Python CLI for installer operations: tool discovery via tomllib, SHA256 staleness detection, atomic manifest writes with flock, preflight check registry, placeholder validation, and pre-manifest adoption**

## Performance

- **Duration:** 30 min
- **Started:** 2026-03-17T22:34:12Z
- **Completed:** 2026-03-18T23:05:03Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files created:** 3

## Accomplishments
- Built mg-install-lib.py (795 lines) with all 5 subcommands outputting JSON to stdout
- Full pytest suite (1171 lines, 38 tests) covering tool discovery, all 5 staleness states, manifest CRUD, preflight checks, placeholder detection, and adopt flow
- Zero pip dependencies -- all stdlib (tomllib, hashlib, fcntl, argparse, pathlib, subprocess)
- Atomic manifest writes using fcntl.flock + tempfile.mkstemp + os.replace pattern
- CHECKS registry with 8 entries (python3, git, gsd, lsp, ruff, vulture, pyright, jscpd)

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Failing test suite** - `fb7ccd9` (test)
2. **Task 1 (TDD GREEN): Implementation + test fixes** - `2c5f435` (feat)

_TDD task with RED (failing tests) then GREEN (implementation) commits_

## Files Created/Modified
- `install/scripts/mg-install-lib.py` - 5-subcommand CLI script (795 lines) for all installer operations
- `install/scripts/tests/__init__.py` - Empty package marker for test discovery
- `install/scripts/tests/test_mg_install_lib.py` - Comprehensive pytest suite (38 tests, 1171 lines)

## Decisions Made
- Used `commands/*` (all files) in checksum scope rather than `commands/*.md` to ensure non-.md files trigger Modified status
- Corrupt status check runs before version/checksum comparison (missing commands is a more severe condition)
- WORKSPACE_DIRS dictionary maps tool names to expected scaffold directories for the validate subcommand
- Absolute path detection regex covers /home, /usr, /opt, /tmp, /var, /etc, /nix prefixes for path validation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed tests missing command files in target for status checks**
- **Found during:** Task 1 (TDD GREEN)
- **Issue:** Tests for "current", "update", and "modified" statuses didn't place command files in the target's .claude/commands/mg/ directory, causing corrupt status to trigger first
- **Fix:** Added command file creation in target directory for all tests that check non-corrupt statuses
- **Files modified:** install/scripts/tests/test_mg_install_lib.py
- **Verification:** All 38 tests pass
- **Committed in:** 2c5f435

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test setup correction needed to match the implementation's corrupt-check-first logic. No scope change.

## Issues Encountered
None beyond the test setup fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- mg-install-lib.py ready for integration by all other plans in phase 7
- Plan 02 (tool.toml files) can reference the CHECKS registry
- Plan 03 (install.md) can call all 5 subcommands
- Plan 04 (install.sh modifications) can call update-manifest subcommand
- Plan 05 (validation on road-runner) can test end-to-end

---
*Phase: 07-install-command*
*Completed: 2026-03-18*
