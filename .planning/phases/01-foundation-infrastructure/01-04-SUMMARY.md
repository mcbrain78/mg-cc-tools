---
phase: 01-foundation-infrastructure
plan: 04
subsystem: infra
tags: [bash, installer, sed, scaffolding, config]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Command stubs, references, and config files to copy"
  - phase: 01-02
    provides: "Python scripts (add-note, classify-note, merge-scan) to install"
  - phase: 01-03
    provides: "Python scripts (check-references, staleness-check) to install"
provides:
  - "Three-mode install.sh (--project, --global, --target) with sed path resolution"
  - "Project scaffolding: .mg/docs/ with config, inbox, scan-logs"
  - "Complete Phase 1 foundation -- all infrastructure ready for pipeline phases"
affects: [02-templates-agents, 03-scan-pipeline, 04-generate-pipeline, 05-verify-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: [three-mode-installer, sed-placeholder-resolution, idempotent-scaffolding]

key-files:
  created:
    - create-docs/install.sh
  modified: []

key-decisions:
  - "Mirrored codebase-health/install.sh structure exactly for consistency across mg-cc-tools"
  - "Scaffolding checks for .mg/docs/ existence to preserve user customizations on re-install"
  - "Agent directory created empty (Phase 2 fills); sed resolution handles future agent files"

patterns-established:
  - "Install pattern: validate sources, copy files, sed-resolve paths, scaffold workspace"
  - "Idempotent scaffolding: skip .mg/docs/ if it already exists to preserve user data"
  - "Six sed placeholders: references/schema.md, references/style-guide.md, {GLOBAL_CONFIG}, {SCRIPTS_DIR}, {TEMPLATES_DIR}, agents/"

requirements-completed: [INF-08, INF-09]

# Metrics
duration: 4min
completed: 2026-03-16
---

# Phase 1 Plan 4: Install Script Summary

**Three-mode install.sh with 6 sed placeholder resolutions, source validation, and idempotent .mg/docs/ project scaffolding**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-16T12:31:48Z
- **Completed:** 2026-03-16T12:35:48Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments

- Created install.sh (330 lines) supporting --project, --global, and --target install modes following the codebase-health/install.sh pattern
- Implemented 6 sed placeholder resolutions for command and agent files (schema, style-guide, config, scripts, templates, agents paths)
- Source validation verifies all 5 command files, scripts/, scripts/lib/, references/ directory and 3 reference files exist before copying
- Project scaffolding creates .mg/docs/ with .docs.config.json (copy of global defaults), notes-inbox.json (empty), and scan-logs/ directory
- Scaffolding is idempotent -- second install skips .mg/docs/ if it already exists, preserving user data
- All 213 existing tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create install.sh with three-mode support and sed resolution** - `754b6be` (feat)
2. **Task 2: Verify sed placeholder resolution and install modes** - No commit needed (verification-only task, no changes required)

## Files Created/Modified

- `create-docs/install.sh` - Three-mode installer with source validation, file copying, sed path resolution, and project scaffolding (330 lines)

## Decisions Made

- Mirrored codebase-health/install.sh structure exactly (header, arg parsing, source validation, install, resolve, scaffold, summary) for consistency across the mg-cc-tools project
- Scaffolding checks directory existence (`-d .mg/docs`) rather than individual files to keep logic simple and preserve all user customizations
- Agent directory created empty during install (Phase 2 will add agent .md files); sed resolution loop handles future agent files gracefully with glob guard
- --target mode does not scaffold .mg/docs/ (consistent with codebase-health which only scaffolds in --project mode)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 foundation is now complete: all 4 plans executed successfully
- install.sh deploys the full create-docs tool: 5 commands, 6 scripts + lib, 3 references
- Empty agents/ directory is ready for Phase 2 (templates and agents) to populate
- .mg/docs/ workspace scaffold ready for runtime use by scan and generate pipelines
- All sed placeholders are in place; as command stubs get real content in later phases, the placeholders will be resolved automatically during install

## Self-Check: PASSED

All 1 created file verified present. Task 1 commit verified in git log.

---
*Phase: 01-foundation-infrastructure*
*Completed: 2026-03-16*
