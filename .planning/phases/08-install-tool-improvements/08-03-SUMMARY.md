---
phase: 08-install-tool-improvements
plan: 03
subsystem: install
tags: [post-install, settings-json, subagent, snapshot, stale-cleanup]

# Dependency graph
requires:
  - phase: 08-install-tool-improvements
    provides: "TEMPLATE-post-install.md pattern and tool.toml updates (plans 01-02)"
provides:
  - "permission-hooks/post-install.md subagent for settings.json hook registration"
  - "cc-regression-test/post-install.md subagent for settings.json hook merge"
  - "Snapshot files relocated from commands/mg/ to tool-specific references/"
  - "Stale file cleanup in 4 install.sh scripts"
affects: [08-install-tool-improvements, install]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-install subagent pattern: self-contained .md with POST-INSTALL markers"
    - "Stale file cleanup pattern: remove v1.0 artifacts after install"
    - "Snapshot relocation pattern: tool-specific references/ instead of commands/mg/"

key-files:
  created:
    - permission-hooks/post-install.md
    - cc-regression-test/post-install.md
  modified:
    - permission-hooks/install.sh
    - cc-regression-test/install.sh
    - mg-gsd-wrappers/install.sh
    - create-context/install.sh

key-decisions:
  - "permission-hooks post-install.md preserves all 5 steps from original command with path references adapted to subagent prompt prefix"
  - "cc-regression-test post-install.md combines steps 2-5 into a single Python script for atomic settings.json merge"
  - "Snapshot files moved to .claude/<tool-name>/references/ to prevent skill list pollution"

patterns-established:
  - "Post-install subagent docs follow TEMPLATE-post-install.md with natural language path references"
  - "Stale file cleanup runs after install but before manifest update"

requirements-completed: [INST-21, INST-22, INST-25, INST-26, INST-27]

# Metrics
duration: 5min
completed: 2026-03-19
---

# Phase 8 Plan 3: Per-Tool Two-Stage Install Summary

**Post-install subagents for permission-hooks and cc-regression-test, snapshot relocation for mg-gsd-wrappers and create-context, stale file cleanup across all 4 tools**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-19T18:22:43Z
- **Completed:** 2026-03-19T18:27:28Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Created permission-hooks/post-install.md as self-contained subagent doc (5-step hook install + settings.json registration with sync check and smoke test)
- Created cc-regression-test/post-install.md as self-contained subagent doc (settings.json hook merge with idempotent duplicate detection)
- Moved snapshot files from commands/mg/ to tool-specific references/ directories for both mg-gsd-wrappers and create-context
- Simplified install.sh for permission-hooks (removed command copy, added stale cleanup) and cc-regression-test (removed inline Python merge)

## Task Commits

Each task was committed atomically:

1. **Task 1: permission-hooks post-install.md and simplified install.sh** - `ced3ce1` (feat)
2. **Task 2: cc-regression-test post-install.md and simplified install.sh** - `9329060` (feat)
3. **Task 3: mg-gsd-wrappers and create-context snapshot relocation** - `e54ef75` (feat)

## Files Created/Modified
- `permission-hooks/post-install.md` - Self-contained subagent instructions for settings.json hook registration (4 matchers: Bash, Read, Edit, Write)
- `permission-hooks/install.sh` - Simplified: no command copy, stale cleanup, hook file copy preserved
- `cc-regression-test/post-install.md` - Self-contained subagent for settings.json hook merge (idempotent, handles missing file/keys)
- `cc-regression-test/install.sh` - Simplified: inline Python removed, file copies and manifest preserved
- `mg-gsd-wrappers/install.sh` - Snapshot copied to .claude/mg-gsd-wrappers/references/, stale cleanup added
- `create-context/install.sh` - Snapshot copied to .claude/create-context/references/, stale cleanup added

## Decisions Made
- permission-hooks post-install.md preserves all 5 steps from the original install-permission-hooks.md command, adapted to use natural language path references from subagent prompt prefix instead of shell variable placeholders
- cc-regression-test post-install.md consolidates the settings.json merge into a single inline Python script with edge case handling (missing file, missing hooks key, missing PreToolUse array, duplicate detection)
- Snapshot relocation uses `<TARGET_DIR>/<tool-name>/references/` path pattern consistent with how other tools organize their support files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] gsd-patches/install.sh included in Task 1 commit**
- **Found during:** Task 1
- **Issue:** gsd-patches/install.sh had been deleted on disk and staged by a prior session. When staging Task 1 files, the pre-staged deletion was included in the commit.
- **Fix:** The deletion is correct per CONTEXT.md ("Remove install.sh entirely -- nothing to copy anywhere" for gsd-patches execute-only pattern). No rollback needed.
- **Files modified:** gsd-patches/install.sh (deleted)
- **Committed in:** ced3ce1

---

**Total deviations:** 1 auto-fixed (1 blocking -- pre-staged file from prior session)
**Impact on plan:** No scope creep. The deletion was planned work from a different plan that was already staged.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Post-install subagents ready for permission-hooks and cc-regression-test
- Snapshot relocation complete for mg-gsd-wrappers and create-context
- Plan 08-04 (gsd-patches) and 08-05 (install.md orchestration) can proceed

## Self-Check: PASSED

All 6 created/modified files verified on disk. All 3 task commits verified in git log.

---
*Phase: 08-install-tool-improvements*
*Completed: 2026-03-19*
