---
phase: 08-install-tool-improvements
plan: 01
subsystem: install
tags: [python, tomllib, checksums, tool-discovery, adopt, scan-status, tdd]

# Dependency graph
requires:
  - phase: 07-install-command
    provides: mg-install-lib.py with 5 subcommands and 48 tests
provides:
  - discover_tools() finds tools with only tool.toml (no install.sh required)
  - read_tool_toml() returns post_install_script and detect_paths fields
  - compute_tool_checksums() includes post-install.md and patches/**/*.md
  - adopt_tools() detects via detect paths in addition to command presence
  - scan_status() reports post_install and has_install_sh per tool
  - scan_status() does not false-flag empty commands as corrupt
affects: [08-02, 08-03, 08-04, 08-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [two-stage install detection, dual-path adopt logic]

key-files:
  created: []
  modified:
    - install/scripts/mg-install-lib.py
    - install/scripts/tests/test_mg_install_lib.py

key-decisions:
  - "Used loop over hardcoded root files ['install.sh', 'post-install.md'] instead of separate checks"
  - "commands=[] in _make_tool() requires explicit None check (falsy empty list vs absent)"

patterns-established:
  - "Root file checksums via loop over hardcoded list: for root_file in ['install.sh', 'post-install.md']"
  - "Dual adopt detection: commands_detected OR detect_detected, skip when both empty"

requirements-completed: [LIB-DISCOVER, LIB-TOML, LIB-CHECKSUMS, LIB-ADOPT, LIB-SCANSTATUS]

# Metrics
duration: 5min
completed: 2026-03-19
---

# Phase 8 Plan 01: Install Library Changes Summary

**Updated mg-install-lib.py with 7 targeted changes for two-stage install model: toml-only discovery, post_install/detect toml sections, patch checksums, detect-path adopt, and install pattern metadata in scan-status**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-19T18:09:00Z
- **Completed:** 2026-03-19T18:14:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- discover_tools() drops install.sh requirement, enabling execute-only tools like gsd-patches
- read_tool_toml() parses [post_install] and [detect] sections for two-stage install support
- compute_tool_checksums() includes post-install.md root file and patches/**/*.md pattern
- adopt_tools() uses dual detection: commands OR detect paths, skipping execute-only
- scan_status() reports has_install_sh and post_install fields, guards corrupt check for empty commands
- All 55 tests pass (48 existing + 7 new), full 145-test cross-tool regression green

## Task Commits

Each task was committed atomically:

1. **Task 1: Write tests for all mg-install-lib.py changes** - `46338f5` (test)
2. **Task 2: Update mg-install-lib.py to pass all tests** - `70c95b5` (feat)

_TDD approach: RED (failing tests) then GREEN (implementation)_

## Files Created/Modified
- `install/scripts/mg-install-lib.py` - Updated 5 functions + 1 constant + 1 CLI handler for two-stage install
- `install/scripts/tests/test_mg_install_lib.py` - Updated _make_tool() helper, added 7 new tests, updated 1 existing test

## Decisions Made
- Used loop over hardcoded root files instead of separate install.sh/post-install.md checks (cleaner, extensible)
- Fixed _make_tool() commands parameter: `commands if commands is not None else [f"{name}.md"]` to distinguish empty list from absent

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Library changes landed first as required -- discover_tools() now supports toml-only tools
- Plans 02-05 can safely add/modify per-tool tool.toml files and remove install.sh from execute-only tools
- scan-status compact output includes has_install_sh and post_install for install.md to determine install pattern

## Self-Check: PASSED

- [x] install/scripts/mg-install-lib.py exists
- [x] install/scripts/tests/test_mg_install_lib.py exists
- [x] 08-01-SUMMARY.md exists
- [x] Commit 46338f5 exists (test RED)
- [x] Commit 70c95b5 exists (feat GREEN)

---
*Phase: 08-install-tool-improvements*
*Completed: 2026-03-19*
