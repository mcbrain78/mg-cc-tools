---
phase: 04-generate-pipeline
plan: 01
subsystem: docs-pipeline
tags: [orchestration, subagent-coordination, documentation-generation, interactive-approval]

# Dependency graph
requires:
  - phase: 01-foundation-infrastructure
    provides: scripts, schema, style guide, config format, command stubs
  - phase: 02-templates-agent-definitions
    provides: writer agents (5), templates (13), glossary agent
  - phase: 03-scan-pipeline
    provides: docs-scan.json data contract, scan command pattern
provides:
  - Full generate pipeline orchestration command (create-docs-generate.md)
  - 4-stage generation flow (glossary -> parallel writers -> reconciliation -> OVERVIEW)
  - Interactive update approval flow with AskUserQuestion
  - Notes integration with inbox status tracking
  - Post-generation summary with per-file stats
affects: [05-verify-pipeline, install.sh path resolution]

# Tech tracking
tech-stack:
  added: []
  patterns: [4-stage-pipeline-orchestration, interactive-approval-flow, parallel-subagent-delegation, inline-generation-for-overview]

key-files:
  created: []
  modified:
    - create-docs/commands/create-docs-generate.md

key-decisions:
  - "OVERVIEW.md generated inline by orchestrator (not via subagent) since orchestrator already has generation context"
  - "Update mode approval uses AskUserQuestion with 4 options: approve all, by document, by severity, cancel"
  - "Notes presented as separate approval group after staleness sections"
  - "Section identifiers normalized to slug format to bridge template Title Case and index hyphenated-lowercase"
  - "Notes inbox updated as single atomic write to prevent partial-update corruption"

patterns-established:
  - "4-stage pipeline: glossary initial -> parallel writers -> glossary reconciliation -> OVERVIEW last"
  - "Agent instructions pasted into Task prompts; agent data passed as file paths only"
  - "Interactive tiered approval: overview -> drill-in -> separate notes group"
  - "File ownership header at top of every generated file before DIATAXIS/AUDIENCE comments"

requirements-completed: [GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, DOC-01, DOC-02, DOC-03, DOC-05, DOC-06, DOC-07, DOC-08, DOC-09, DOC-10, DOC-11, DOC-12, DOC-13, CMD-03]

# Metrics
duration: 3min
completed: 2026-03-16
---

# Phase 4 Plan 1: Generate Pipeline Command Summary

**Full generate pipeline orchestration command with 4-stage generation, interactive update approval via AskUserQuestion, notes integration, and post-generation summary**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-16T18:34:35Z
- **Completed:** 2026-03-16T18:38:13Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Replaced stub with full 464-line generate pipeline orchestration command
- Implemented 4-stage generation pipeline: glossary initial pass, 4 parallel writer agents, glossary reconciliation, OVERVIEW.md inline generation
- Built interactive update approval flow with 4 user options (approve all, by document, by severity, cancel) plus separate notes approval group
- Added notes integration marking inbox entries as "integrated" with atomic write
- Added post-generation summary table with per-file section count, word count, and status
- Documented all key formats (ownership header, docs-meta, directory layout, index key format) and 10 operational principles

## Task Commits

Each task was committed atomically:

1. **Task 1: Write initial mode flow (Steps 1-3, Stages 1-4)** - `8b58fe0` (feat)
2. **Task 2: Add update mode approval flow, notes integration, and generation summary** - `bf6efbb` (feat)

## Files Created/Modified
- `create-docs/commands/create-docs-generate.md` - Full generate pipeline orchestration command (464 lines, replacing 7-line stub)

## Decisions Made
- OVERVIEW.md generated inline by the orchestrator rather than via subagent, since the orchestrator already has context of what was generated across all audiences
- Update mode approval uses AskUserQuestion tool with a tiered flow: Level 1 overview, then drill-in by document or severity, with notes as a separate approval group
- Section identifiers always normalized to slug format (lowercased-hyphenated) to bridge template Title Case headings and source_material_index keys
- Notes inbox updated as single atomic write after all generation completes, to prevent partial-update corruption

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Generate command is complete and ready for road-runner validation (plan 04-02)
- All locked decisions from CONTEXT.md implemented in the command
- Command follows create-docs-scan.md structural pattern consistently
- Install.sh already handles this command file (in COMMANDS array, sed resolution covers all placeholders)

## Self-Check: PASSED

- FOUND: create-docs/commands/create-docs-generate.md
- FOUND: .planning/phases/04-generate-pipeline/04-01-SUMMARY.md
- FOUND: commit 8b58fe0 (Task 1)
- FOUND: commit bf6efbb (Task 2)

---
*Phase: 04-generate-pipeline*
*Completed: 2026-03-16*
