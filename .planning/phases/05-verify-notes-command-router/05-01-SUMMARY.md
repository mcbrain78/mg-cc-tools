---
phase: 05-verify-notes-command-router
plan: 01
subsystem: docs-pipeline
tags: [verify, notes, inbox, classification, LSP, diataxis, command-prompt]

# Dependency graph
requires:
  - phase: 01-foundation-infrastructure
    provides: check-references.py, add-note.py, classify-note.py scripts and command stubs
  - phase: 02-templates-agent-definitions
    provides: verifier.md agent definition with 6-check process
provides:
  - create-docs-verify.md command prompt orchestrating documentation verification
  - add-docs.md command prompt for standalone note capture with auto-classification
affects: [05-02 router command, end-to-end pipeline validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [verify-command-orchestration, standalone-note-command, LSP-override-in-task-prompt]

key-files:
  created: []
  modified:
    - create-docs/commands/create-docs-verify.md
    - create-docs/commands/add-docs.md

key-decisions:
  - "Verify command uses single verifier agent (not parallel by category) since 6 sequential checks are simpler than per-finding parallelization"
  - "LSP symbol verification override delivered via Task prompt, not by modifying verifier.md agent definition"
  - "AskUserQuestion added to add-docs allowed-tools for classification correction UX per research recommendation"

patterns-established:
  - "Task prompt override pattern: paste agent definition then add OVERRIDE instructions for specific checks"
  - "Standalone companion command pattern: lightweight command calling existing scripts without pipeline state"

requirements-completed: [VFY-01, VFY-02, VFY-03, VFY-04, VFY-05, VFY-06, VFY-07, CMD-04, CMD-05]

# Metrics
duration: 3min
completed: 2026-03-16
---

# Phase 5 Plan 01: Verify & Notes Commands Summary

**Verify command orchestrating 6-check verifier agent via Task tool with LSP symbol override, plus standalone add-docs command for note capture with auto-classification**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-16T22:47:45Z
- **Completed:** 2026-03-16T22:50:52Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Wrote create-docs-verify.md (173 lines) -- full orchestration prompt for 6-check documentation verification
- Wrote add-docs.md (136 lines) -- standalone note capture with auto-classification and user correction flow
- All 227 tests remain passing (no scripts or agents modified)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write create-docs-verify.md command** - `66a4159` (feat)
2. **Task 2: Write add-docs.md command** - `bff43e6` (feat)

## Files Created/Modified
- `create-docs/commands/create-docs-verify.md` - Full verify pipeline command: prerequisites check, check-references.py extraction, verifier agent spawn via Task with LSP override, results presentation with severity summary
- `create-docs/commands/add-docs.md` - Standalone note command: parse arguments, detect GSD/file context, add-note.py for inbox append, classify-note.py for auto-classification, AskUserQuestion for correction

## Decisions Made
- Single verifier agent instance (not parallel by category) -- 6 sequential checks in one agent is simpler and sufficient for docs verification
- LSP override instruction placed in Task prompt rather than modifying agents/verifier.md -- preserves shared infrastructure from Phase 2
- Added AskUserQuestion to add-docs allowed-tools for classification correction UX (was missing from stub)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Verify and add-docs commands complete, ready for Plan 02 (router command + end-to-end validation)
- Router command (create-docs.md) still needs to be written to tie the pipeline together
- End-to-end road-runner validation pending as Phase 5 success gate

## Self-Check: PASSED

- FOUND: create-docs/commands/create-docs-verify.md
- FOUND: create-docs/commands/add-docs.md
- FOUND: commit 66a4159 (Task 1)
- FOUND: commit bff43e6 (Task 2)

---
*Phase: 05-verify-notes-command-router*
*Completed: 2026-03-16*
