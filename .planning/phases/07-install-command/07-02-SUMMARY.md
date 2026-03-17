---
phase: 07-install-command
plan: 02
subsystem: infra
tags: [toml, metadata, tool-discovery, python311]

# Dependency graph
requires:
  - phase: none
    provides: "Existing tool directories with install.sh"
provides:
  - "tool.toml metadata files for all 12 tool directories"
  - "install/ directory skeleton (commands/, scripts/)"
  - "pyproject.toml requires-python >= 3.11 for tomllib"
affects: [07-03, 07-04, 07-05]

# Tech tracking
tech-stack:
  added: [tomllib]
  patterns: [tool.toml metadata contract]

key-files:
  created:
    - "codebase-health/tool.toml"
    - "create-docs/tool.toml"
    - "create-context/tool.toml"
    - "data-provider/tool.toml"
    - "debug-triage/tool.toml"
    - "gsd-patches/tool.toml"
    - "mg-gsd-wrappers/tool.toml"
    - "new-milestone-gsd/tool.toml"
    - "update-backlog/tool.toml"
    - "permission-hooks/tool.toml"
    - "cc-regression-test/tool.toml"
    - "install/tool.toml"
  modified:
    - "pyproject.toml"

key-decisions:
  - "Omit exclude field for non-excluded tools (false is the default)"
  - "Omit optional key when array would be empty (cleaner TOML)"
  - "Omit [preflight] section entirely when only required has values and optional is empty -- kept [preflight] for all tools since every tool declares at least required"
  - "Set requires-python to >=3.11 (tomllib floor) rather than >=3.13 per Pitfall 4 recommendation"

patterns-established:
  - "tool.toml schema: [tool] section with description (required), exclude (optional), [preflight] section with required/optional arrays"

requirements-completed: [INST-02]

# Metrics
duration: 1min
completed: 2026-03-17
---

# Phase 7 Plan 02: Tool Metadata Summary

**TOML metadata files for all 12 tools with description, exclusion flags, and preflight dependency declarations**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-17T22:34:16Z
- **Completed:** 2026-03-17T22:35:39Z
- **Tasks:** 1
- **Files modified:** 13

## Accomplishments
- Created tool.toml for all 12 tool directories (11 existing + new install/)
- Excluded tools (install, cc-regression-test) correctly marked with exclude = true
- Preflight declarations match RESEARCH.md inventory: python3 vs gsd required, optional tools for codebase-health and create-docs
- Updated pyproject.toml requires-python from >=3.8 to >=3.11 for tomllib compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tool.toml for all 12 tool directories** - `a1158ad` (feat)

## Files Created/Modified
- `codebase-health/tool.toml` - Complex tool metadata with optional preflight checks (ruff, vulture, pyright, jscpd)
- `create-docs/tool.toml` - Documentation tool metadata with optional LSP preflight
- `create-context/tool.toml` - Context snapshot tool metadata requiring GSD
- `data-provider/tool.toml` - Data provider tool metadata requiring python3
- `debug-triage/tool.toml` - GSD debug tool metadata requiring GSD
- `gsd-patches/tool.toml` - GSD patches tool metadata requiring GSD
- `mg-gsd-wrappers/tool.toml` - GSD wrappers tool metadata requiring GSD
- `new-milestone-gsd/tool.toml` - GSD milestone tool metadata requiring GSD
- `update-backlog/tool.toml` - GSD backlog tool metadata requiring GSD
- `permission-hooks/tool.toml` - Permission hooks tool metadata requiring python3
- `cc-regression-test/tool.toml` - Excluded regression test tool metadata
- `install/tool.toml` - Excluded installer meta-tool metadata
- `pyproject.toml` - Updated requires-python from >=3.8 to >=3.11

## Decisions Made
- Omit `exclude = false` from non-excluded tools (it is the default per CONTEXT.md spec)
- Omit `optional` key when the array would be empty (cleaner TOML, less noise)
- Set `requires-python = ">=3.11"` (tomllib minimum) rather than >=3.13 per Pitfall 4 analysis

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 12 tool.toml files in place for mg-install-lib.py to discover and parse
- install/ directory skeleton created (commands/, scripts/) ready for subsequent plans
- pyproject.toml version constraint aligned with tomllib requirement

---
*Phase: 07-install-command*
*Completed: 2026-03-17*
