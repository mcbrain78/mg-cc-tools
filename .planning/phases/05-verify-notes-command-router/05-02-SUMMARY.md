---
phase: 05-verify-notes-command-router
plan: 02
subsystem: docs-pipeline
tags: [router, pipeline-state-detection, end-to-end-validation, road-runner, performance-fix]

# Dependency graph
requires:
  - phase: 05-verify-notes-command-router
    plan: 01
    provides: create-docs-verify.md and add-docs.md command prompts
  - phase: 04-generate-pipeline
    provides: create-docs-generate.md command for full pipeline
  - phase: 03-scan-pipeline
    provides: create-docs-scan.md command for full pipeline
provides:
  - create-docs.md router command with 5-state detection and 4-route guidance
  - End-to-end validated documentation pipeline (scan, generate, verify)
  - Performance-optimized check-references.py with index-based symbol lookup
affects: [milestone completion, production readiness]

# Tech tracking
tech-stack:
  added: []
  patterns: [router-state-detection, skip-symbol-check-delegation-to-LSP, index-based-symbol-lookup]

key-files:
  created: []
  modified:
    - create-docs/commands/create-docs.md
    - create-docs/scripts/check-references.py
    - create-docs/scripts/tests/test_check_references.py
    - create-docs/commands/create-docs-verify.md

key-decisions:
  - "Router follows codebase-health.md pattern precisely: state detection + routing, never runs pipeline steps itself"
  - "check-references.py index-based lookup replaces O(symbols x files) per-symbol os.walk to prevent timeouts on real projects"
  - "--skip-symbol-check flag delegates symbol verification to LSP via verifier agent (faster and more accurate than regex)"
  - "Verify-generate feedback loop deferred as future work item (documented in docs/work-queue/todo/)"

patterns-established:
  - "Router pattern: load config, check filesystem state in order, route to correct next step with report summaries"
  - "Performance gate: road-runner validation catches O(n^2) patterns that unit tests miss"

requirements-completed: [CMD-01]

# Metrics
duration: 12h
completed: 2026-03-17
---

# Phase 5 Plan 02: Router Command & End-to-End Validation Summary

**Pipeline router with 5-state detection routing to 4 destinations, plus end-to-end road-runner validation that caught and fixed O(n^2) symbol lookup in check-references.py**

## Performance

- **Duration:** ~12 hours (includes checkpoint wait for human validation on road-runner)
- **Started:** 2026-03-16T22:53:44Z
- **Completed:** 2026-03-17T11:57:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Wrote create-docs.md router command (127 lines) -- full state detection and routing for the 3-step documentation pipeline
- End-to-end pipeline validated on road-runner: scan, generate, verify all produce expected output
- Fixed check-references.py performance: index-based symbol lookup + --skip-symbol-check flag eliminated timeouts on real projects
- All 228 tests passing (1 new test for skip-symbol-check behavior)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write create-docs.md router command** - `985e967` (feat)
2. **Task 2: End-to-end pipeline validation on road-runner** - `6b8a039` (fix)

## Files Created/Modified
- `create-docs/commands/create-docs.md` - Full router command: config loading, 5 ordered state checks (.mg/docs/ exists, docs-scan.json exists, partial scan detection, docs generated, verify report exists), 4 routes (A: fresh start, B: scan complete, C: generation complete, D: pipeline complete), report summary extraction
- `create-docs/scripts/check-references.py` - Index-based symbol lookup replacing per-symbol os.walk; new --skip-symbol-check flag marking symbols as "unchecked" for LSP delegation
- `create-docs/scripts/tests/test_check_references.py` - New test for skip_symbol_check=True verifying symbols get status "unchecked"
- `create-docs/commands/create-docs-verify.md` - Updated to pass --skip-symbol-check to check-references.py; added explanation comment about LSP delegation

## Decisions Made
- Router follows codebase-health.md pattern precisely -- same structure of state detection checks followed by route presentation
- check-references.py index-based lookup replaces O(symbols x files) per-symbol os.walk -- builds index once on first call, then does set lookups
- --skip-symbol-check flag added so verify command extracts symbols without walking project tree; symbol verification delegated to verifier agent via LSP (semantically correct, not regex-based)
- Verify-to-generate feedback loop identified as broken during validation (verify finds issues but generate cannot consume them) -- deferred as future work item, not in scope for this plan

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed O(n^2) symbol lookup in check-references.py**
- **Found during:** Task 2 (road-runner validation)
- **Issue:** check-references.py walked the entire project tree for EACH symbol reference, causing timeouts on real projects with many symbols
- **Fix:** (a) Built a cached index of all classes/functions/methods on first call, then lookup via set membership. (b) Added --skip-symbol-check flag so verify command skips symbol walking entirely since LSP handles it.
- **Files modified:** create-docs/scripts/check-references.py, create-docs/scripts/tests/test_check_references.py, create-docs/commands/create-docs-verify.md
- **Verification:** 228 tests pass, road-runner validation completes without timeout
- **Committed in:** 6b8a039

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Performance fix essential for real-world usage. No scope creep -- check-references.py API is backward compatible.

## Issues Encountered

- **Verify-generate feedback loop:** During road-runner validation, the verify step found issues but the generate step has no mechanism to consume verify results for targeted fixes. This is a design gap, not a bug in this plan's deliverables. Documented as future work item in `docs/work-queue/todo/doc-command-verify-fix/CONCEPT.md`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 5 phases complete -- milestone v1.0 deliverables are done
- Full documentation pipeline (scan, generate, verify) validated end-to-end on road-runner
- Router command ties the pipeline together as the user's entry point
- Future work: verify-generate feedback loop (deferred to v2)

## Self-Check: PASSED

- FOUND: create-docs/commands/create-docs.md
- FOUND: create-docs/scripts/check-references.py
- FOUND: create-docs/scripts/tests/test_check_references.py
- FOUND: create-docs/commands/create-docs-verify.md
- FOUND: commit 985e967 (Task 1)
- FOUND: commit 6b8a039 (Task 2)

---
*Phase: 05-verify-notes-command-router*
*Completed: 2026-03-17*
