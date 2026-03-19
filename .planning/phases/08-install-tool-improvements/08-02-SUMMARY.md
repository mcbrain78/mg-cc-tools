---
phase: 08-install-tool-improvements
plan: 02
subsystem: install
tags: [toml, tool-discovery, adopt-detection, post-install]

# Dependency graph
requires:
  - phase: 08-install-tool-improvements
    provides: "mg-install-lib.py two-stage install support (Plan 01)"
provides:
  - "TEMPLATE-post-install.md with mandated status marker pattern"
  - "11 tool.toml files with [detect], [post_install], and tier settings"
  - "Prerequisite metadata for install.md rewrite (Plan 05)"
affects: [08-03, 08-04, 08-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tool.toml [detect] section for adopt detection paths"
    - "tool.toml [post_install] section for two-stage install"
    - "POST-INSTALL: SUCCESS/FAILED status marker pattern"

key-files:
  created:
    - install/TEMPLATE-post-install.md
  modified:
    - codebase-health/tool.toml
    - create-docs/tool.toml
    - data-provider/tool.toml
    - debug-triage/tool.toml
    - new-milestone-gsd/tool.toml
    - update-backlog/tool.toml
    - permission-hooks/tool.toml
    - gsd-patches/tool.toml
    - mg-gsd-wrappers/tool.toml
    - cc-regression-test/tool.toml
    - create-context/tool.toml

key-decisions:
  - "gsd-patches changed from exclude=true to standard=false (not adoptable, no [detect])"
  - "Template uses natural language path references, no shell variable placeholders"

patterns-established:
  - "[detect] paths use target-relative paths for adopt detection"
  - "[post_install] script field names the post-install.md file"
  - "POST-INSTALL: SUCCESS/FAILED as mandatory status markers"

requirements-completed: [INST-18, INST-19, INST-20]

# Metrics
duration: 2min
completed: 2026-03-19
---

# Phase 8 Plan 02: Template and Tool.toml Updates Summary

**TEMPLATE-post-install.md with status marker pattern plus 11 tool.toml updates for [detect], [post_install], and tier settings**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-19T18:17:52Z
- **Completed:** 2026-03-19T18:19:48Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- Created TEMPLATE-post-install.md mandating POST-INSTALL: SUCCESS/FAILED status markers for all post-install files
- Added [detect] sections to 6 tools for adopt detection (codebase-health, create-docs, data-provider, debug-triage, new-milestone-gsd, update-backlog)
- Updated tier settings for 4 tools: permission-hooks (standard=false), gsd-patches (exclude->standard=false), mg-gsd-wrappers (standard=false), cc-regression-test (added [post_install]+[detect])
- create-context gets [detect] section for adopt detection

## Task Commits

Each task was committed atomically:

1. **Task 1: Create TEMPLATE-post-install.md** - `7ba6a11` (feat)
2. **Task 2: Update all 11 tool.toml files** - `c0742cb` (feat)

## Files Created/Modified
- `install/TEMPLATE-post-install.md` - Template mandating status marker pattern for post-install.md files
- `codebase-health/tool.toml` - Added [detect] paths for scripts directory
- `create-docs/tool.toml` - Added [detect] paths for scripts directory
- `data-provider/tool.toml` - Added [detect] paths for scripts directory
- `debug-triage/tool.toml` - Added [detect] paths for command file
- `new-milestone-gsd/tool.toml` - Added [detect] paths for command file
- `update-backlog/tool.toml` - Added [detect] paths for command file
- `permission-hooks/tool.toml` - standard=false, [post_install], [detect]
- `gsd-patches/tool.toml` - Changed exclude=true to standard=false, added [post_install]
- `mg-gsd-wrappers/tool.toml` - standard=false, [detect]
- `cc-regression-test/tool.toml` - Added [post_install], [detect]
- `create-context/tool.toml` - Added [detect] paths for command file

## Decisions Made
- gsd-patches: changed from exclude=true to standard=false per CONTEXT.md -- no [detect] section since it is execute-only and not adoptable
- Template uses natural language path references ("the target project", "the source directory") rather than shell variable placeholders, matching the subagent execution model

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TEMPLATE-post-install.md ready for Plans 03/04 to create per-tool post-install.md files
- All tool.toml files have correct metadata for the install.md rewrite (Plan 05)
- scan-status still discovers all 12 tools
- All 55 existing tests pass

## Self-Check: PASSED

- All 12 files (1 created, 11 modified) verified on disk
- Both task commits (7ba6a11, c0742cb) verified in git log
- Inline Python verification: ALL CHECKS PASSED
- scan-status: 12 tools discovered
- Regression tests: 55 passed

---
*Phase: 08-install-tool-improvements*
*Completed: 2026-03-19*
