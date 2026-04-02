---
phase: 23-template-refiner-pipeline
plan: 01
subsystem: auto-doc
tags: [template-refinement, agent-spawning, llm-pipeline, markdown-command]

# Dependency graph
requires:
  - phase: 22-heading-iterator-script
    provides: next-heading.py that parses refined template format
provides:
  - prepare-templates command orchestrator for template refinement pipeline
  - install.sh registration for auto-doc-prepare-templates command
affects: [23-template-refiner-pipeline, 24-writer-orient-write-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [sequential-agent-per-document-spawning, config-driven-audience-discovery]

key-files:
  created:
    - auto-doc/commands/auto-doc-prepare-templates.md
  modified:
    - auto-doc/install.sh

key-decisions:
  - "Sequential agent spawning (one per document) for simplicity and deterministic error handling"
  - "Shared documents (OVERVIEW, GLOSSARY) excluded from refinement per Pitfall 7 in RESEARCH.md"
  - "Config-driven audience/document discovery from .docs.config.json (same source of truth as generate command)"

patterns-established:
  - "Template refiner command follows agent-per-document spawning pattern from auto-doc-generate.md Stage 2"
  - "Output to .mg/docs/templates/{audience}/ (project-local, separate from installed generic templates)"

requirements-completed: [TRF-01, TRF-06, TRF-07]

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 23 Plan 01: Prepare-Templates Command Summary

**Orchestrator command for template refinement pipeline with config-driven audience/document discovery and sequential agent-per-document spawning**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-02T19:02:47Z
- **Completed:** 2026-04-02T19:04:47Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Created `auto-doc-prepare-templates.md` command (145 lines) with full orchestration flow: config loading, scan data extraction, audience/document pair discovery, output directory creation, sequential agent spawning, and summary reporting
- Registered the new command in install.sh COMMANDS array and both help text sections
- Command passes all required context to each refiner agent via Agent prompt: project_root, generic template path, scan data path, output path, audience, document, scan_date, scripts_dir
- All 5 sed-resolvable placeholders used correctly: {SCRIPTS_DIR}, {TEMPLATES_DIR}, {AGENTS_DIR}, {GLOBAL_CONFIG}, {EMIT_CONTEXT_SCRIPT}

## Task Commits

Each task was committed atomically:

1. **Task 1: Create prepare-templates command and update install.sh** - `94eaf64` (feat)

## Files Created/Modified

- `auto-doc/commands/auto-doc-prepare-templates.md` - Orchestrator command for template refinement pipeline
- `auto-doc/install.sh` - Added auto-doc-prepare-templates to COMMANDS array and help text

## Decisions Made

- Sequential agent spawning (one per document) for simplicity -- avoids concurrent reads on shared scan data and simplifies error handling
- Shared documents (OVERVIEW, GLOSSARY) excluded from refinement -- these are consumed by overview-writer and glossary-writer which do not use the orient-write loop
- Config-driven audience/document discovery -- reads .docs.config.json to enumerate pairs, same source of truth used by generate command

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Command orchestrator ready for plan 23-02 which creates the template-refiner.md agent definition
- install.sh agent wildcard copy already handles template-refiner.md deployment (no additional install.sh changes needed in plan 02)
- Refined template output format compatible with Phase 22's next-heading.py parse_template() function

## Self-Check: PASSED

- FOUND: auto-doc/commands/auto-doc-prepare-templates.md
- FOUND: commit 94eaf64
- FOUND: 23-01-SUMMARY.md

---
*Phase: 23-template-refiner-pipeline*
*Completed: 2026-04-02*
