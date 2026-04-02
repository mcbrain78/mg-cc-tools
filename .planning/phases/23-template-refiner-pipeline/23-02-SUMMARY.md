---
phase: 23-template-refiner-pipeline
plan: 02
subsystem: auto-doc
tags: [markdown, agent-definition, template-refinement, source-exploration, html-comments]

# Dependency graph
requires:
  - phase: 22-heading-iterator-script
    provides: next-heading.py parse_template() that consumes refined template format
  - phase: 02-templates-agent-definitions
    provides: TEMPLATE.md agent structure pattern and generic template format
provides:
  - template-refiner.md agent definition for per-document template refinement
  - Shallow source exploration pattern (get_symbols_overview for code, full Read for config)
  - PURPOSE vs EXAMPLE content boundary enforcement via MUST/MUST NOT rules
  - OPTIONAL section resolution heuristic (keep if any evidence, drop if none)
affects: [23-template-refiner-pipeline, 24-writer-orient-write-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Refiner agent: shallow source exploration ceiling -- symbol overviews for code, full reads for config, no function bodies"
    - "PURPOSE comments carry project-specific structural facts; EXAMPLE blocks carry generic format demonstrations only"
    - "OPTIONAL section resolution via conservative heuristic: keep if any evidence exists"

key-files:
  created:
    - auto-doc/agents/template-refiner.md
  modified: []

key-decisions:
  - "Agent uses get_symbols_overview (Serena) for Python source exploration with Read fallback when Serena unavailable"
  - "7 MUST NOT rules enforce content boundaries: no heading text changes, no project-specific EXAMPLE values, no function body reads"
  - "OPTIONAL resolution uses conservative keep-if-any-evidence heuristic per CONTEXT.md recommendation"
  - "Agent invokes get-section-sources.py and list-optional-sections.py for deterministic source lookup and OPTIONAL identification"

patterns-established:
  - "Template refiner agent pattern: read generic template, shallow explore sources, decide headings, write refined template"
  - "PURPOSE vs EXAMPLE boundary: project-specific facts in PURPOSE, generic format demos in EXAMPLE"

requirements-completed: [TRF-02, TRF-03, TRF-04, TRF-05, TRF-06, TRF-07]

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 23 Plan 02: Template Refiner Agent Summary

**Template refiner agent definition with shallow source exploration, evidence-based heading decisions, and PURPOSE/EXAMPLE content boundary enforcement via 7 MUST NOT rules**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-02T19:02:57Z
- **Completed:** 2026-04-02T19:05:32Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created template-refiner.md agent definition following TEMPLATE.md and devops-writer.md patterns
- Defined shallow source exploration pattern: get_symbols_overview for Python, full Read for non-code files
- Enforced PURPOSE vs EXAMPLE content boundary with explicit MUST/MUST NOT rules (7 MUST NOT constraints)
- Integrated get-section-sources.py and list-optional-sections.py for deterministic source lookup
- Output format compatible with next-heading.py parse_template() (##-#### headings with PURPOSE/EXAMPLE HTML comments)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create template-refiner agent definition** - `0688fd5` (feat)

## Files Created/Modified
- `auto-doc/agents/template-refiner.md` - Template refiner agent definition (145 lines) with Role, Inputs, Process, Critical Rules, and Output Format sections

## Decisions Made
- Agent uses Serena get_symbols_overview for Python files with standard Read fallback -- matches devops-writer's "Symbols first, Read second" principle
- 7 MUST NOT rules enforce heading preservation, content boundaries, exploration depth, and OPTIONAL resolution
- Conservative OPTIONAL resolution: keep if any evidence exists (source files in index, project_model entries, related components)
- Agent invokes existing scripts (get-section-sources.py, list-optional-sections.py) rather than duplicating their logic

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- template-refiner.md ready for Phase 23 Plan 01 (prepare-templates command) to spawn as Agent subagent per document
- Output format validated against next-heading.py parse_template() expectations for Phase 24 consumption
- install.sh already handles agents/*.md wildcard -- no install changes needed for template-refiner.md

## Self-Check: PASSED

- [x] auto-doc/agents/template-refiner.md exists
- [x] Commit 0688fd5 (feat) exists
- [x] 23-02-SUMMARY.md exists

---
*Phase: 23-template-refiner-pipeline*
*Completed: 2026-04-02*
