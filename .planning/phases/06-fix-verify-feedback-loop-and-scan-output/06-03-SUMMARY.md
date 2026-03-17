---
phase: 06-fix-verify-feedback-loop-and-scan-output
plan: 03
subsystem: docs-pipeline
tags: [verify-command, router, scan-command, findings-lifecycle, command-wiring]

# Dependency graph
requires:
  - phase: 06-fix-verify-feedback-loop-and-scan-output
    provides: Rewritten verifier.md with two-step workflow and baked-in LSP/glossary (Plan 02)
  - phase: 06-fix-verify-feedback-loop-and-scan-output
    provides: add-verify-finding.py, list-verify-findings.py, write-scan-output.py scripts (Plan 01)
provides:
  - Simplified create-docs-verify.md with no Task prompt overrides and findings lifecycle
  - Findings-aware router (Route E) that detects verify findings and directs to generate
  - Scan command passing scripts_dir to scan-audience agents for write-scan-output.py
affects: [06-04-generate-approval-tier]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Findings lifecycle: verify clears, generate reads, next verify produces fresh findings"
    - "Findings-aware routing: router reads JSON directly for state detection (no script dependency)"

key-files:
  created: []
  modified:
    - create-docs/commands/create-docs-verify.md
    - create-docs/commands/create-docs.md
    - create-docs/commands/create-docs-scan.md

key-decisions:
  - "Verify command simplified to pure parameter passing -- all verification behavior baked into verifier.md agent definition"
  - "Router reads docs-verify-findings.json directly (no list-verify-findings.py dependency) per CONTEXT.md decision"
  - "Route D explicitly labeled 'no outstanding findings' to distinguish from Route E"

patterns-established:
  - "Findings lifecycle: verify clears docs-verify-findings.json before each run, generate reads but never clears"
  - "Command-layer simplification: agents own their behavior, commands only pass parameters"

requirements-completed: [FIX-A4, FIX-A5, FIX-B3]

# Metrics
duration: 2min
completed: 2026-03-17
---

# Phase 6 Plan 03: Command Wiring Summary

**Simplified verify command (removed all Task prompt overrides), added findings-aware Route E to router, and wired scan command to pass scripts_dir for write-scan-output.py**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T21:14:37Z
- **Completed:** 2026-03-17T21:17:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Removed OVERRIDE (Check 1 LSP) and ADDITIONAL (Check 2 glossary) blocks from create-docs-verify.md Task prompt -- verifier.md is now the single source of truth
- Added findings lifecycle: verify clears docs-verify-findings.json before each run, builds findings_file path, passes it to verifier agent
- Router gained Route E that detects non-empty docs-verify-findings.json and directs users to re-run generate
- Scan command now passes {SCRIPTS_DIR} to scan-audience agents so they can call write-scan-output.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Simplify create-docs-verify.md and add findings lifecycle** - `429499d` (feat)
2. **Task 2: Add findings-aware state to router and update scan command** - `7144dce` (feat)

## Files Created/Modified
- `create-docs/commands/create-docs-verify.md` - Simplified Task prompt (no overrides), added findings_file path, clear prior findings, updated guidance
- `create-docs/commands/create-docs.md` - Added Route E for findings-aware state detection, clarified Route D as "no outstanding findings"
- `create-docs/commands/create-docs-scan.md` - Added Scripts directory parameter to scan-audience Task prompt, documented temp-file-then-validate workflow

## Decisions Made
- Verify command simplified to pure parameter passing -- all 6 checks, LSP symbol verification, and glossary reconciliation are now fully defined in verifier.md. The command only clears findings, extracts references, and passes paths.
- Router reads docs-verify-findings.json directly as a simple file check (no script dependency), consistent with CONTEXT.md decision that list-verify-findings.py is not needed in the router.
- Route D explicitly labeled "no outstanding findings" to make the distinction between "pipeline complete and clean" vs "pipeline ran but findings exist" (Route E) clear to users.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 06-04 can now build the 3rd approval tier in create-docs-generate.md knowing that verify findings flow through docs-verify-findings.json
- The verify-generate feedback loop is wired: verify produces findings -> router detects them -> directs to generate -> generate reads findings as 3rd tier
- All three command files are consistent with the updated agent definitions from Plan 02

## Self-Check: PASSED

All 3 modified files verified present. All 2 task commits verified in git log.

---
*Phase: 06-fix-verify-feedback-loop-and-scan-output*
*Completed: 2026-03-17*
