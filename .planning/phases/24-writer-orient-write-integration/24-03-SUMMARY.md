---
phase: 24-writer-orient-write-integration
plan: 03
subsystem: auto-doc
tags: [generate-command, orient-write-routing, refined-templates, stale-warning, devops-writer]

# Dependency graph
requires:
  - phase: 24-writer-orient-write-integration plan 01
    provides: refined_templates dict and stale_templates list in generate-setup.py JSON output
  - phase: 24-writer-orient-write-integration plan 02
    provides: Rewritten devops-writer.md accepting refined_template_path, state_file_path, scripts_dir inputs
provides:
  - Conditional orient-write routing in generate command Stage 2 for devops writers with refined templates
  - Stale template warning printed before generation when templates are outdated
  - Per-document Agent spawning for devops orient-write (state file scoped per document)
  - heading-state-*.json cleanup in generate-setup.py prepare_workspace
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Orient-write routing: generate command checks refined_templates dict to decide standard vs orient-write prompt per document"
    - "Per-document Agent spawning: devops orient-write uses one Agent per document (not one per audience) for state file isolation"

key-files:
  created: []
  modified:
    - auto-doc/commands/auto-doc-generate.md
    - auto-doc/scripts/generate-setup.py

key-decisions:
  - "Devops orient-write spawns one Agent per document (not per audience) because each document needs its own heading-state file"
  - "Stale template warning is non-blocking -- generation continues with stale templates to avoid breaking workflow"
  - "Non-devops audiences always use standard prompt unchanged -- orient-write is devops-only for now"
  - "heading-state-*.json added to generate-setup.py temp cleanup patterns to prevent state collision across runs"

patterns-established:
  - "Orient-write routing pattern: check refined_templates[audience][document] for null vs non-null to decide prompt type"
  - "Per-document state file convention: heading-state-{audience}-{DOCUMENT}.json in tmp dir"

requirements-completed: [OWI-06, OWI-07]

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 24 Plan 03: Generate Command Orient-Write Routing Summary

**Generate command routes devops writers through orient-write prompt with per-document state files when refined templates exist, with stale warning and full backward compatibility**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-02T19:42:59Z
- **Completed:** 2026-04-02T19:45:20Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Modified generate command Stage 2 to conditionally route devops writers through orient-write prompt when refined template exists
- Added stale template warning before Stage 1 when stale_templates list is non-empty
- Added heading-state-*.json to generate-setup.py prepare_workspace temp cleanup patterns
- Preserved standard prompt for all non-devops audiences and devops documents without refined templates
- Full auto-doc test suite green (748 tests, 0 failures)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add refined template routing and stale warning to generate command** - `789bae8` (feat)

## Files Created/Modified
- `auto-doc/commands/auto-doc-generate.md` - Added refined_templates/stale_templates parsing, stale warning, conditional orient-write routing in Stage 2
- `auto-doc/scripts/generate-setup.py` - Added heading-state-*.json to temp cleanup patterns in prepare_workspace()

## Decisions Made
- Devops orient-write spawns one Agent per document (not per audience) because each document needs its own heading-state file
- Stale template warning is non-blocking -- generation continues with stale templates to avoid breaking workflow
- Non-devops audiences always use standard prompt unchanged -- orient-write is devops-only for now
- heading-state-*.json added to generate-setup.py temp cleanup patterns to prevent state collision across runs

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Full orient-write integration complete: generate-setup.py detects refined templates, generate command routes devops through orient-write, devops-writer uses next-heading.py loop
- Pattern established for future writer modernization (end-user, developer, agent writers can adopt orient-write when refined templates are created for them)
- All 3 plans of phase 24 complete

## Self-Check: PASSED

- [x] auto-doc/commands/auto-doc-generate.md exists
- [x] auto-doc/scripts/generate-setup.py exists
- [x] 24-03-SUMMARY.md exists
- [x] Commit 789bae8 (feat) exists

---
*Phase: 24-writer-orient-write-integration*
*Completed: 2026-04-02*
