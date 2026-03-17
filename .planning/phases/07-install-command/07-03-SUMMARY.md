---
phase: 07-install-command
plan: 03
subsystem: installer
tags: [slash-command, interactive-flow, bootstrap, install-sh, lsp-probe, askuserquestion]

# Dependency graph
requires:
  - phase: 07-01
    provides: mg-install-lib.py with 5 subcommands (scan-status, preflight, validate, adopt, update-manifest)
provides:
  - /mg:install slash command prompt with 8-step interactive flow (388 lines)
  - Bootstrap install.sh for self-installing the command (121 lines)
affects: [07-04, 07-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [8-step-interactive-flow, numbered-text-prompts-over-askuserquestion, bootstrap-self-install]

key-files:
  created:
    - install/commands/install.md
    - install/install.sh
  modified: []

key-decisions:
  - "Script path uses relative ./install/scripts/mg-install-lib.py since command always runs from mg-cc-tools directory -- no sed resolution needed"
  - "AskUserQuestion used ONLY for target selection (Step 1); action selection (Step 3) uses numbered text prompts parsed by the LLM"
  - "Bootstrap install.sh does NOT call update-manifest per Pitfall 7 -- mg-cc-tools is the source repo, not a target"
  - "PROJECT_PATH initialized to empty string in bootstrap install.sh to avoid unbound variable errors with set -u"

patterns-established:
  - "Interactive command pattern: 8-step flow with target selection, status scan, action selection, preflight, capability probe, install, validate, summary"
  - "Bootstrap installer pattern: self-install command that is the exception to manifest-update rule"

requirements-completed: [INST-06, INST-09, INST-11]

# Metrics
duration: 4min
completed: 2026-03-18
---

# Phase 7 Plan 3: install.md and Bootstrap install.sh Summary

**/mg:install slash command with 8-step interactive flow (target, status, action, preflight, LSP probe, install, validate, summary) and bootstrap self-installer**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T23:07:56Z
- **Completed:** 2026-03-17T23:12:39Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Created install.md (388 lines) implementing the full 8-step interactive flow for tool installation, update, and management
- Created bootstrap install.sh (121 lines) following the debug-triage install.sh pattern with all 3 installation modes
- install.md correctly delegates to mg-install-lib.py for all deterministic operations (scan-status, preflight, validate, adopt) and to per-tool install.sh for execution
- Bootstrap installer is the deliberate exception to the manifest-update rule (Pitfall 7)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create install.md slash command prompt** - `3b0eb87` (feat)
2. **Task 2: Create bootstrap install.sh** - `b6b26b6` (feat)

## Files Created/Modified
- `install/commands/install.md` - 388-line LLM prompt implementing the /mg:install 8-step interactive flow
- `install/install.sh` - 121-line bootstrap installer for self-installing the command (executable)

## Decisions Made
- Used relative path `./install/scripts/mg-install-lib.py` directly in the command since it always runs from mg-cc-tools directory -- no sed placeholder resolution needed
- AskUserQuestion is restricted to target selection only; action selection uses numbered text prompts to avoid the 4-option limit
- Bootstrap install.sh initializes `PROJECT_PATH=""` at the top to avoid unbound variable errors (matching the pattern from Pitfall 3 in RESEARCH.md)
- LSP probe uses `timeout 60` wrapper to prevent hangs during capability probing

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- install.md ready for integration testing on road-runner (Plan 05)
- install.sh ready for modification by Plan 04 (adding manifest update calls to all other install.sh scripts)
- Bootstrap can be tested: `./install/install.sh --project` then `/mg:install` in Claude Code

## Self-Check: PASSED

- [x] install/commands/install.md exists (388 lines)
- [x] install/install.sh exists and is executable (121 lines)
- [x] Commit 3b0eb87 found (Task 1)
- [x] Commit b6b26b6 found (Task 2)

---
*Phase: 07-install-command*
*Completed: 2026-03-18*
