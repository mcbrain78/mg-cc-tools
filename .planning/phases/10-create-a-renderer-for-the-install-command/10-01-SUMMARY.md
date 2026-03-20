---
phase: 10-create-a-renderer-for-the-install-command
plan: 01
subsystem: install
tags: [python, argparse, cli, tdd, text-rendering, status-table]

# Dependency graph
requires:
  - phase: 08-install-tool-improvements
    provides: mg-install-lib.py with scan-status, discover_tools, argparse subcommand pattern
provides:
  - render-status-table subcommand for deterministic status table rendering
  - render-tool-picker subcommand for numbered tool selection list
  - resolve-tool-selection subcommand for parsing user selection input
  - _get_ordered_tools shared ordering function for consistent numbering
affects: [install-command-prompt, install-md-simplification]

# Tech tracking
tech-stack:
  added: []
  patterns: [shared-ordering-function, input-via-json-file, stdout-rendering]

key-files:
  created: []
  modified:
    - install/scripts/mg-install-lib.py
    - install/scripts/tests/test_mg_install_lib.py

key-decisions:
  - "Unicode separators (not ASCII) to match existing install.md visual style"
  - "Dynamic column widths computed from actual data (not fixed padding)"
  - "Version and target read from scan-status JSON (no extra CLI arguments)"
  - "_get_ordered_tools preserves scan-status order within tiers (already alphabetical from discover_tools)"
  - "render_status_table uses its own three-tier filtering (needs excluded tier) while picker/resolver share _get_ordered_tools"

patterns-established:
  - "Shared ordering: _get_ordered_tools() is the single source of truth for tool numbering"
  - "Renderer input: --input flag reads pre-computed scan-status JSON file (not --source/--target)"
  - "Renderer output: formatted text to stdout (render) or JSON to stdout (resolve)"

requirements-completed: [INST-35, INST-36, INST-37, INST-38, INST-42]

# Metrics
duration: 6min
completed: 2026-03-20
---

# Phase 10 Plan 01: Renderer Subcommands Summary

**Three deterministic Python subcommands (render-status-table, render-tool-picker, resolve-tool-selection) with TDD coverage via shared _get_ordered_tools ordering function**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-20T11:18:35Z
- **Completed:** 2026-03-20T11:24:35Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- render-status-table produces a three-tier table (standard, optional, excluded) with dynamic column alignment, summary counts scoped to non-excluded tools, version transition annotations, and status legend
- render-tool-picker produces a numbered tool list with Standard/Optional section headers, status annotations for non-available tools, and excluded tool filtering
- resolve-tool-selection parses numbers, ranges, names, mixed input, and "all" -- returning JSON tool list or error JSON
- _get_ordered_tools is a single shared function guaranteeing consistent numbering between picker and resolver
- 29 new tests added (84 total), all passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `ca5bfa7` (test)
2. **Task 1 (GREEN): Implementation** - `ca6b5d8` (feat)

_TDD task: RED committed failing tests, GREEN committed passing implementation. No REFACTOR needed._

## Files Created/Modified
- `install/scripts/mg-install-lib.py` - Added 3 subcommands, 1 shared helper, 3 CLI handlers, argparse wiring (+322 lines)
- `install/scripts/tests/test_mg_install_lib.py` - Added 4 test classes (TestRenderStatusTable, TestRenderToolPicker, TestResolveToolSelection, TestGetOrderedTools) with 29 tests (+584 lines)

## Decisions Made
- Unicode separators match existing install.md visual style (not ASCII)
- Dynamic column widths from data (adapts when tools are added/removed)
- Version and target read from JSON (no extra CLI arguments needed)
- render_status_table does NOT use _get_ordered_tools because it needs the excluded tier too
- Kept status annotations capitalized in picker (e.g., "(Current)", "(Corrupt)") for readability

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Three subcommands ready for install.md prompt simplification (Plan 02)
- install.md Step 2 can now call `render-status-table --input` and display verbatim
- install.md Step 3 can use `render-tool-picker --input` and `resolve-tool-selection --input --selection` for the select-specific-tools flow

## Self-Check: PASSED

- FOUND: install/scripts/mg-install-lib.py
- FOUND: install/scripts/tests/test_mg_install_lib.py
- FOUND: 10-01-SUMMARY.md
- FOUND: ca5bfa7 (RED commit)
- FOUND: ca6b5d8 (GREEN commit)
- 84 tests passing (55 existing + 29 new)

---
*Phase: 10-create-a-renderer-for-the-install-command*
*Completed: 2026-03-20*
