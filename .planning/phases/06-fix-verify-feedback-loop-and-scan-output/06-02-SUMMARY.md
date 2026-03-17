---
phase: 06-fix-verify-feedback-loop-and-scan-output
plan: 02
subsystem: docs-pipeline
tags: [verifier, scan-agent, schema, lsp, glossary, two-step-workflow]

# Dependency graph
requires:
  - phase: 02-templates-agent-definitions
    provides: original verifier.md and scan-audience.md agent definitions
  - phase: 05-verify-notes-command-router
    provides: verify command with Task prompt overrides for LSP and glossary
provides:
  - Rewritten verifier.md with two-step workflow (per-finding recording + report generation)
  - Updated scan-audience.md using write-scan-output.py for validated output
  - Documented docs-verify-findings.json format in schema.md
affects: [06-03-verify-simplification, 06-04-generate-approval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-step agent workflow: per-finding script calls during analysis + report generation from accumulated findings"
    - "Scan output validation: agent writes to temp file, calls validation script, script writes atomically"

key-files:
  created: []
  modified:
    - create-docs/agents/verifier.md
    - create-docs/agents/scan-audience.md
    - create-docs/references/schema.md

key-decisions:
  - "Used {SCRIPTS_DIR} placeholders in agent definitions for consistency with existing install.sh sed resolution pattern"
  - "Baked LSP symbol verification directly into Check 1 and glossary reconciliation into Check 2, eliminating all Task prompt overrides"
  - "Verify findings schema uses flat array with 7 required fields -- no nesting, no dedup in data layer"

patterns-established:
  - "Two-step verification workflow: record findings individually via script during checks, then generate report from accumulated findings"
  - "Agent output validation: write to temp file first, call validation script, script handles atomic write"

requirements-completed: [FIX-A3, FIX-B2]

# Metrics
duration: 3min
completed: 2026-03-17
---

# Phase 6 Plan 02: Agent Rewrites Summary

**Rewritten verifier agent with two-step workflow (per-finding recording via add-verify-finding.py + report from accumulated findings via list-verify-findings.py), LSP and glossary reconciliation baked in, scan-audience output using write-scan-output.py, and verify findings JSON format documented in schema.md**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-17T19:31:38Z
- **Completed:** 2026-03-17T19:34:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Verifier agent fully rewritten with two-step workflow: Step 1 records each finding via add-verify-finding.py during checks, Step 2 reads accumulated findings via list-verify-findings.py and generates editorial report with systemic issue grouping
- LSP symbol verification baked into Check 1 (eliminates OVERRIDE block from create-docs-verify.md)
- Glossary reconciliation baked into Check 2 (eliminates ADDITIONAL block from create-docs-verify.md)
- All 6 verification checks preserved with original severity mappings (critical/high/medium/low/info)
- Scan-audience agent output section updated to use write-scan-output.py for validated atomic writes
- Schema.md documents docs-verify-findings.json format with all 7 required fields, lifecycle description, and example

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite verifier.md with two-step workflow** - `56d5eff` (feat)
2. **Task 2: Update scan-audience.md output section and add verify findings to schema.md** - `e76d117` (feat)

## Files Created/Modified
- `create-docs/agents/verifier.md` - Full rewrite: two-step workflow, LSP baked into Check 1, glossary reconciliation baked into Check 2, findings_file input parameter
- `create-docs/agents/scan-audience.md` - Output section updated: writes to temp file then calls write-scan-output.py for validation
- `create-docs/references/schema.md` - New section documenting docs-verify-findings.json format with required fields table, lifecycle, and example; updated file location convention

## Decisions Made
- Used `{SCRIPTS_DIR}` placeholders (not `{scripts_dir}` runtime parameter) in agent definitions for consistency with the existing install.sh sed resolution pattern already in place for agent files
- Baked LSP symbol verification directly into Check 1 and glossary reconciliation directly into Check 2, making verifier.md the single source of truth for the verification workflow
- Verify findings schema uses a flat array with 7 required fields per finding -- aggregation into systemic patterns happens at the presentation layer (the markdown report), not in the JSON data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 06-03 can now simplify create-docs-verify.md by removing all Task prompt override blocks (OVERRIDE for Check 1, ADDITIONAL for Check 2) since behavior is now baked into verifier.md
- Plan 06-03 needs to add findings_file and verify_refs_path as parameters when spawning the verifier agent
- Plan 06-04 can reference docs-verify-findings.json format from schema.md for the 3rd approval tier

## Self-Check: PASSED

All files verified present, all commit hashes found in git log.

---
*Phase: 06-fix-verify-feedback-loop-and-scan-output*
*Completed: 2026-03-17*
