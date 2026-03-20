---
phase: 11-add-tooling-to-install-command
plan: 01
subsystem: install
tags: [python, cli, argparse, tdd, scenario-logic, action-menu]

# Dependency graph
requires:
  - phase: 10-create-a-renderer-for-the-install-command
    provides: render-status-table, render-tool-picker, resolve-tool-selection, _get_ordered_tools
provides:
  - _determine_scenario() shared helper for scenario A/B/C classification
  - render-action-menu subcommand producing scenario-specific menus
  - resolve-action subcommand mapping menu selections to action+tool lists
  - scan-status --auto-adopt flag for pre-manifest adoption
affects: [11-02-PLAN, 11-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [shared-scenario-helper, menu-rendering, action-resolution]

key-files:
  created: []
  modified:
    - install/scripts/mg-install-lib.py
    - install/scripts/tests/test_mg_install_lib.py

key-decisions:
  - "_determine_scenario is shared by render_action_menu and resolve_action via direct call -- single source of truth prevents scenario drift"
  - "Scenario B triggers on corrupt and adopted statuses in addition to update and modified (INST-51 behavior change)"
  - "_resolve_menu_option helper encapsulates per-scenario option-to-action mapping as a dict lookup"
  - "auto-adopt runs adopt_tools before scan_status when flag set and no manifest, then re-runs scan to get updated statuses"

patterns-established:
  - "Shared scenario helper: _determine_scenario() called by multiple subcommands to prevent classification divergence"
  - "Action resolution: resolve_action falls back to resolve_tool_selection for non-numeric input"

requirements-completed: [INST-43, INST-44, INST-45, INST-51, INST-53, INST-55, INST-57]

# Metrics
duration: 4min
completed: 2026-03-20
---

# Phase 11 Plan 01: Scenario Logic and Action Subcommands Summary

**Shared _determine_scenario helper, render-action-menu and resolve-action subcommands, and scan-status --auto-adopt flag with TDD coverage**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-20T15:41:11Z
- **Completed:** 2026-03-20T15:45:26Z
- **Tasks:** 1 (TDD feature: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Implemented _determine_scenario() shared helper returning A/B/C from scan-status summary counts, including INST-51 behavior change (corrupt/adopted trigger Scenario B)
- Added render-action-menu subcommand producing correct 3/5/4-option menus per scenario with dynamic tool counts
- Added resolve-action subcommand mapping all menu options across 3 scenarios to correct action+tool lists, with fallback to resolve_tool_selection for non-numeric input
- Added --auto-adopt flag to scan-status: adopts detected tools when no manifest exists, backward compatible without flag
- 30 new tests (6 scenario classification + 5 menu output + 13 action resolution + 4 auto-adopt + 2 CLI validation), 115 total passing

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests** - `c057691` (test)
2. **GREEN: Implementation** - `21a5ca7` (feat)

_TDD: RED phase wrote 30 failing tests, GREEN phase implemented all functions to pass._

## Files Created/Modified
- `install/scripts/mg-install-lib.py` - Added _determine_scenario, render_action_menu, _resolve_menu_option, resolve_action, cmd_render_action_menu, cmd_resolve_action, modified cmd_scan_status for --auto-adopt, argparse wiring
- `install/scripts/tests/test_mg_install_lib.py` - Added scenario fixtures (A/B/C), TestDetermineScenario, TestRenderActionMenu, TestResolveAction, TestScanStatusAutoAdopt classes

## Decisions Made
- _determine_scenario is a private function shared by render_action_menu and resolve_action via direct call -- single source of truth for scenario classification
- Scenario B condition: update > 0 OR modified > 0 OR corrupt > 0 OR adopted > 0 (behavior change from v1.2)
- _resolve_menu_option uses dict lookup per scenario rather than nested if/elif for clarity
- Auto-adopt calls adopt_tools() before scan_status() so the subsequent scan sees adopted entries in the manifest
- Three separate fixtures (_make_scenario_a/b/c_fixture) for scenario-specific test isolation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- render-action-menu and resolve-action are ready for install.md prompt integration (Plan 11-03)
- _determine_scenario is ready for use by any future subcommand needing scenario classification
- Plan 11-02 can build get-install-plan, record-result, render-preflight, render-summary, render-validation on the same patterns

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 11-add-tooling-to-install-command*
*Completed: 2026-03-20*
