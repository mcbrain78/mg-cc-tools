---
phase: 12-auto-doc-rename-and-cleanup
plan: 01
subsystem: tooling
tags: [rename, auto-doc, sed, git-mv, migration, install]

# Dependency graph
requires:
  - phase: 05-verify-notes-command-router
    provides: Complete create-docs tool family (5 commands, agents, scripts, references)
provides:
  - auto-doc/ directory with all commands, agents, scripts, references renamed
  - Migration path in install.sh for existing create-docs installations
  - Cross-tool references updated (mg-install-lib.py, install.md, permission-hooks, CLAUDE.md)
affects: [13-auto-doc-script, 14-auto-doc-reference-manifest, 15-auto-doc-enduser-quality, 16-auto-doc-incremental-scan]

# Tech tracking
tech-stack:
  added: []
  patterns: [install.sh migration path for breaking renames]

key-files:
  created: []
  modified:
    - auto-doc/commands/auto-doc.md
    - auto-doc/commands/auto-doc-scan.md
    - auto-doc/commands/auto-doc-generate.md
    - auto-doc/commands/auto-doc-verify.md
    - auto-doc/commands/auto-doc-add.md
    - auto-doc/install.sh
    - auto-doc/tool.toml
    - install/scripts/mg-install-lib.py
    - install/commands/install.md
    - .claude/commands/mg/install.md
    - permission-hooks/hooks/tests/test_permission_guard.py
    - CLAUDE.md

key-decisions:
  - "Bulk sed s/create-docs/auto-doc/g followed by explicit s/add-docs/auto-doc-add/g -- independent patterns, order does not matter"
  - "Migration path in install.sh uses inline python3 for manifest JSON cleanup with non-fatal fallback"
  - "session-analyzer/samples/ and .pytest_cache excluded from verification scope (test data, not tool code)"

patterns-established:
  - "install.sh migration pattern: detect old installation, remove stale files, clean manifest, then deploy new structure"

requirements-completed: [REN-01, REN-02, REN-03, REN-04, REN-05, REN-06, REN-07]

# Metrics
duration: 13min
completed: 2026-03-22
---

# Phase 12 Plan 01: Auto-Doc Rename Summary

**Renamed create-docs tool family to auto-doc namespace with migration path, cross-tool reference updates, and CLAUDE.md documentation**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-22T11:12:08Z
- **Completed:** 2026-03-22T11:25:34Z
- **Tasks:** 2
- **Files modified:** 60

## Accomplishments
- Renamed create-docs/ directory to auto-doc/ with all 5 command files (including non-trivial add-docs -> auto-doc-add)
- Deleted orphaned staleness-scanner.md agent that was never wired into any command
- Added migration path in install.sh that detects old create-docs installations, removes stale files, and cleans the manifest
- Updated all cross-tool references: mg-install-lib.py workspace mapping, install.md (both copies), permission-hooks test data, CLAUDE.md
- Verification grep confirmed zero create-docs/add-docs references outside historical directories

## Task Commits

Each task was committed atomically:

1. **Task 1: Directory move, file renames, delete orphan, and bulk substitution** - `82dc40f` (feat)
2. **Task 2: Cross-tool reference updates, CLAUDE.md update, and verification grep** - `c76dbfb` (feat)

## Files Created/Modified
- `auto-doc/` - Entire tool directory renamed from create-docs/ (55 files)
- `auto-doc/install.sh` - Migration path added, all references updated to auto-doc namespace
- `auto-doc/tool.toml` - [detect].paths updated to .claude/auto-doc/scripts/
- `install/scripts/mg-install-lib.py` - Workspace mapping key: create-docs -> auto-doc
- `install/commands/install.md` - Tool listing: create-docs -> auto-doc
- `.claude/commands/mg/install.md` - Tool listing: create-docs -> auto-doc (installed copy)
- `permission-hooks/hooks/tests/test_permission_guard.py` - Test data: /mg:add-docs -> /mg:auto-doc-add
- `CLAUDE.md` - Added auto-doc as complex tool with pipeline description subsection

## Decisions Made
- Bulk sed `s/create-docs/auto-doc/g` followed by explicit `s/add-docs/auto-doc-add/g` -- independent patterns since `add-docs` is not a substring of `create-docs`
- Migration path uses inline `python3 -c` for manifest JSON cleanup with `2>/dev/null || echo "Warning: ..."` fallback per CONTEXT.md discretion
- `session-analyzer/samples/` persisted test data excluded from verification scope (historical test data, not active tool code)
- Header comment in install.sh updated from "Create-Docs Pipeline" to "Auto-Doc Pipeline"

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed misaligned echo padding in install.sh help and summary**
- **Found during:** Task 1 (after bulk sed)
- **Issue:** The `add-docs` -> `auto-doc-add` substitution left extra whitespace in echo alignment for help text and summary output
- **Fix:** Manually aligned echo spacing for /mg:auto-doc-add lines
- **Files modified:** auto-doc/install.sh
- **Verification:** Visual inspection confirms aligned output
- **Committed in:** 82dc40f (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Cosmetic fix, no scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- auto-doc/ directory is ready for Plan 02 (bug fixes: staleness-check output wrapper, note_id normalization, add-note stdout JSON, dead scan call removal)
- All 105 auto-doc tests pass as baseline before bug fix work begins
- All 202 permission-hooks tests pass after cross-tool reference updates

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 12-auto-doc-rename-and-cleanup*
*Completed: 2026-03-22*
