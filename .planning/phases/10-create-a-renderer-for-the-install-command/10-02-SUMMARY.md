---
phase: 10-create-a-renderer-for-the-install-command
plan: 02
subsystem: install
tags: [markdown, prompt-engineering, command-simplification, deterministic-rendering]

# Dependency graph
requires:
  - phase: 10-create-a-renderer-for-the-install-command
    plan: 01
    provides: render-status-table, render-tool-picker, resolve-tool-selection subcommands in mg-install-lib.py
provides:
  - Simplified install.md Step 2 using render-status-table subcommand
  - Simplified install.md Step 3 using render-tool-picker and resolve-tool-selection subcommands
  - Deployed copy kept in sync
affects: [install-command-runtime, mg-install-prompt]

# Tech tracking
tech-stack:
  added: []
  patterns: [subcommand-call-plus-verbatim-display, deterministic-rendering-via-python]

key-files:
  created: []
  modified:
    - install/commands/install.md
    - .claude/commands/mg/install.md

key-decisions:
  - "Step 2 uses single render-status-table call with verbatim display directive (replacing ~50 lines of template)"
  - "Step 3 Scenario A option [2] calls render-tool-picker then resolve-tool-selection for specific-tool flows"
  - "Scenarios B/C tool name/number input uses resolve-tool-selection with render-tool-picker as fallback on error"
  - "All three scenario menus (A/B/C) remain as LLM-rendered plain text per INST-41"

patterns-established:
  - "Subcommand + verbatim: call Python renderer, display output unchanged -- no inline templates"
  - "Error recovery: on resolve-tool-selection error, show render-tool-picker output for reference and re-prompt"

requirements-completed: [INST-39, INST-40, INST-41]

# Metrics
duration: 2min
completed: 2026-03-20
---

# Phase 10 Plan 02: Install Prompt Simplification Summary

**Replaced ~50-line inline table template and freestyled tool picker in install.md with deterministic Python subcommand calls plus verbatim display directives**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-20T11:27:27Z
- **Completed:** 2026-03-20T11:29:27Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Step 2 reduced from ~50 lines of table template, example, formatting rules, and legend to a 4-line render-status-table call with verbatim display directive
- Step 3 Scenario A option [2] now calls render-tool-picker for numbered list display, then resolve-tool-selection for parsing user input
- Scenarios B/C tool name/number input now uses resolve-tool-selection with render-tool-picker fallback on error
- All three scenario menus (A/B/C) preserved as LLM-rendered plain text per INST-41
- Source and deployed copies verified byte-identical

## Task Commits

Each task was committed atomically:

1. **Task 1: Simplify Step 2 to use render-status-table** - `0021a10` (feat)
2. **Task 2: Update Step 3 with render-tool-picker/resolve-tool-selection, sync deployed copy** - `27440ca` (feat)

## Files Created/Modified
- `install/commands/install.md` - Step 2 simplified (removed inline template, added subcommand call), Step 3 enhanced (added tool picker and resolver calls)
- `.claude/commands/mg/install.md` - Deployed copy synced byte-identical with source

## Decisions Made
- Step 2 verbatim directive is explicit ("do not modify, reformat, or summarize it") to prevent LLM creative interpretation
- Scenario A [2] sub-flow placed immediately after the Scenario A menu block for locality
- Scenarios B/C resolver placed in the "Parse the user's response" section since it applies to both scenarios
- Error recovery pattern: show render-tool-picker output on resolver error, then re-prompt

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 10 complete: all renderer subcommands built (Plan 01) and integrated into install.md (Plan 02)
- install.md now uses deterministic Python rendering for status tables and tool selection
- LLM-rendered scenario menus preserved as designed (short, static, reliable)

## Self-Check: PASSED

- FOUND: install/commands/install.md
- FOUND: .claude/commands/mg/install.md
- FOUND: 10-02-SUMMARY.md
- FOUND: 0021a10 (Task 1 commit)
- FOUND: 27440ca (Task 2 commit)
- VERIFIED: source and deployed copies identical

---
*Phase: 10-create-a-renderer-for-the-install-command*
*Completed: 2026-03-20*
