---
phase: 02-templates-agent-definitions
plan: 04
subsystem: agents
tags: [staleness-scanner, verifier, agent-definitions, install-sh, templates-directory]

# Dependency graph
requires:
  - phase: 01-foundation-infrastructure
    provides: staleness-check.py, check-references.py, install.sh, schema.md
  - phase: 02-templates-agent-definitions
    plan: 01
    provides: TEMPLATE.md agent pattern, glossary-writer.md
provides:
  - Staleness scanner agent for scan pipeline (per-section freshness analysis)
  - Verifier agent for verify pipeline (6 quality checks)
  - install.sh templates directory recursive copy
  - install.sh summary with template and agent counts
affects: [03-scan-pipeline, 05-verify-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Specialized analysis agent pattern: Role, Inputs, Process, Output Format, Principles (non-writer variant)"
    - "install.sh recursive copy with cp -r for directory trees"

key-files:
  created:
    - create-docs/agents/staleness-scanner.md
    - create-docs/agents/verifier.md
  modified:
    - create-docs/install.sh

key-decisions:
  - "Staleness scanner uses conservative classification: only marks stale/broken with concrete evidence from git or dead references"
  - "Verifier agent uses 5-tier severity model (critical/high/medium/low/info) matching docs-verify-report.md format"
  - "install.sh uses cp -r preserving subdirectory structure (end-users/, developers/, agents/, devops/) for templates"

patterns-established:
  - "Analysis agent pattern: same Role/Inputs/Process/Principles structure as writer agents, but Process describes analytical operations and Output Format defines JSON/markdown report structure"
  - "Staleness classification model: fresh (no changes) / stale (source changed) / broken (dead references)"

requirements-completed: [AGT-06, AGT-07]

# Metrics
duration: 5min
completed: 2026-03-16
---

# Phase 02 Plan 04: Non-Writer Agents & Install Patch Summary

**Staleness scanner and verifier analysis agents with install.sh templates directory copy closing the Phase 2 deployment gap**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-16T15:00:02Z
- **Completed:** 2026-03-16T18:04:25Z
- **Tasks:** 2
- **Files created/modified:** 3

## Accomplishments
- Created staleness-scanner.md (99 lines) with per-section freshness analysis using both staleness-check.py and check-references.py
- Created verifier.md (139 lines) with 6 verification checks producing docs-verify-report.md
- Patched install.sh to recursively copy references/templates/ preserving audience subdirectory structure
- Verified install deploys all 13 templates and 8 agent definitions correctly

## Task Commits

Each task was committed atomically:

1. **Task 1: Create staleness-scanner and verifier agent definitions** - `58211d1` (feat)
2. **Task 2: Patch install.sh to copy templates directory and update summary** - `57125b5` (feat)

## Files Created/Modified
- `create-docs/agents/staleness-scanner.md` - Per-section freshness analysis agent for scan pipeline (99 lines)
- `create-docs/agents/verifier.md` - Documentation quality verification agent with 6 check types (139 lines)
- `create-docs/install.sh` - Added templates directory validation, recursive copy, and template/agent counts in summary

## Decisions Made
- Staleness scanner uses a three-tier classification (fresh/stale/broken) with broken taking precedence when both conditions exist
- Verifier outputs a severity-categorized markdown report (docs-verify-report.md) consistent with the schema's verification structure
- install.sh uses simple `cp -r` for templates (preserves entire subdirectory tree without needing to enumerate audience directories)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 8 agent definitions complete: TEMPLATE.md, glossary-writer, 4 writer agents, staleness-scanner, verifier
- All 13 templates exist in references/templates/ with correct audience subdirectory structure
- install.sh deploys everything: commands, scripts, references, templates, agents
- Phase 2 is fully complete -- Phase 3 (scan pipeline) and Phase 5 (verify pipeline) can use these agents

## Self-Check: PASSED

All 3 created/modified files verified on disk. Both task commits (58211d1, 57125b5) verified in git log.

---
*Phase: 02-templates-agent-definitions*
*Completed: 2026-03-16*
