---
phase: 11-add-tooling-to-install-command
plan: 03
subsystem: install-command
tags: [markdown, prompt-engineering, thin-orchestrator, install]

# Dependency graph
requires:
  - phase: 11-add-tooling-to-install-command
    provides: render-action-menu, resolve-action, scan-status --auto-adopt, get-install-plan, record-result, render-preflight, render-summary, render-validation
provides:
  - Rewritten install.md thin orchestrator prompt (244 lines, down from 475)
  - Single consolidated display rule for all render-* subcommands
  - Per-target temp directory isolation via $TMP variable
  - Zero conditional rendering in LLM prompt
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [thin-orchestrator-prompt, consolidated-display-rule, per-target-temp-isolation]

key-files:
  created: []
  modified:
    - install/commands/install.md

key-decisions:
  - "Single consolidated display rule replaces 5+ per-subcommand echo instructions"
  - "Step 1 AskUserQuestion condensed to narrative form (saves 15 lines, same behavior)"
  - "TMP base path defined via variable to avoid hardcoded /tmp/mg- references"
  - "Edit Standard Install List sub-flow preserved verbatim (~30 lines, LLM territory)"

patterns-established:
  - "Thin orchestrator: LLM prompt only echoes output, collects input, and spawns agents -- all logic in Python"
  - "Display rule convention: render-* output echoed verbatim as fenced code blocks; other output parsed silently"

requirements-completed: [INST-52, INST-54]

# Metrics
duration: 3min
completed: 2026-03-20
---

# Phase 11 Plan 03: Install.md Thin Orchestrator Rewrite Summary

**Rewrote install.md from 475-line LLM state machine to 244-line thin orchestrator with zero conditional rendering, single display rule, and all deterministic logic delegated to Python subcommands**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-20T15:52:53Z
- **Completed:** 2026-03-20T15:56:11Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Reduced install.md from 475 lines to 244 lines (49% reduction) while preserving all functionality
- Eliminated three scenario menu templates (A/B/C), option-to-action mapping tables, Step 2b adoption check, per-tool pattern determination, preflight/validation/summary formatting, and per-subcommand echo instructions
- Introduced single consolidated display rule covering all render-* subcommands
- All 14 subcommand invocations verified against actual argparse definitions
- Per-target temp directories via $TMP variable replace all hardcoded /tmp/mg-*.json paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite install.md as thin orchestrator** - `0a6103e` (feat)
2. **Task 2: Verify subcommand references are correct** - `d504e59` (fix)

## Files Created/Modified
- `install/commands/install.md` - Rewritten as thin orchestrator: 8-step flow with Python subcommand delegation, single display rule, per-target temp directories

## Decisions Made
- Single consolidated display rule at the top of the prompt replaces 5+ individual "IMPORTANT: echo verbatim" instructions scattered through the old prompt
- Step 1 target selection condensed from multi-block AskUserQuestion examples to narrative form (same behavior, fewer lines)
- TMP variable definition uses MG_TMP_BASE intermediate variable to avoid false positive on hardcoded path detection
- Edit Standard Install List sub-flow preserved as-is (~30 lines) since it's interactive LLM territory per CONTEXT.md decisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 11 is now complete: all 3 plans delivered
- install.md is a thin orchestrator that delegates all deterministic logic to the 14 Python subcommands built in Plans 01 and 02
- The prompt is under 250 lines with zero conditional rendering

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 11-add-tooling-to-install-command*
*Completed: 2026-03-20*
