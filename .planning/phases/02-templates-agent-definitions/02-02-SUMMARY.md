---
phase: 02-templates-agent-definitions
plan: 02
subsystem: templates
tags: [diataxis, three-layer-template, developer-docs, agent-docs, devops-docs, runbook, exemplar]

# Dependency graph
requires:
  - phase: 01-foundation-infrastructure
    provides: "style-guide.md, schema.md, .docs.config.json"
provides:
  - "9 audience-specific templates: developers (3), agents (4), devops (2)"
  - "Three-layer template format established across all audience types"
  - "Consistent DataForge example project across developer templates"
  - "Machine-optimized agent templates with MUST/SHOULD constraint language"
  - "Runbook-structured devops templates with copy-paste-ready commands"
affects: [02-03, 02-04, 04-generate-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Three-layer template: DIATAXIS classification + PURPOSE statements + EXAMPLE exemplars"
    - "Developer templates: code-first with language-tagged blocks and type signatures"
    - "Agent templates: tables for structured data, MUST/SHOULD/MUST NOT constraints, absolute paths"
    - "DevOps templates: runbook structure, deploy+rollback pairs, bash with expected output"

key-files:
  created:
    - "create-docs/references/templates/developers/ARCHITECTURE.template.md"
    - "create-docs/references/templates/developers/DEVELOPER_GUIDE.template.md"
    - "create-docs/references/templates/developers/QUICK_REFERENCE.template.md"
    - "create-docs/references/templates/agents/SYSTEM_MAP.template.md"
    - "create-docs/references/templates/agents/CONVENTIONS.template.md"
    - "create-docs/references/templates/agents/GOTCHAS.template.md"
    - "create-docs/references/templates/agents/TESTING.template.md"
    - "create-docs/references/templates/devops/OPERATIONS.template.md"
    - "create-docs/references/templates/devops/TROUBLESHOOTING.template.md"
  modified: []

key-decisions:
  - "Consistent DataForge example project across all developer and agent templates for coherent cross-template references"
  - "Agent templates use explicit MUST/SHOULD/MUST NOT constraint language per Codified Context paper"
  - "DevOps OPERATIONS template mirrors 02-RESEARCH.md detailed example as primary reference"

patterns-established:
  - "Three-layer template format: all 9 templates follow identical comment structure (DIATAXIS, AUDIENCE, docs-meta, PURPOSE, EXAMPLE, OPTIONAL)"
  - "Exemplar depth: minimum 3-10 lines of concrete content per section with realistic data"
  - "Developer exemplars: code blocks with language tags, type signatures, realistic file paths"
  - "Agent exemplars: tables, constraint blocks, absolute paths, YAML frontmatter"
  - "DevOps exemplars: full bash commands, expected output, success/failure cases, escalation paths"

requirements-completed: [TPL-02]

# Metrics
duration: 9min
completed: 2026-03-16
---

# Phase 02 Plan 02: Audience-Specific Templates Summary

**9 audience-specific templates (developers 3, agents 4, devops 2) with three-layer architecture using consistent DataForge example project**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-16T14:47:10Z
- **Completed:** 2026-03-16T14:56:46Z
- **Tasks:** 3
- **Files created:** 9

## Accomplishments
- Created 3 developer templates (ARCHITECTURE, DEVELOPER_GUIDE, QUICK_REFERENCE) with code-first Stripe/Twilio conventions
- Created 4 agent templates (SYSTEM_MAP, CONVENTIONS, GOTCHAS, TESTING) with machine-optimized formatting and MUST/SHOULD constraints
- Created 2 devops templates (OPERATIONS, TROUBLESHOOTING) with runbook structure, deploy+rollback pairs, and copy-paste-ready bash
- All 9 templates follow consistent three-layer format with DIATAXIS classification, PURPOSE statements, and concrete exemplars

## Task Commits

Each task was committed atomically:

1. **Task 1: Create developer audience templates** - `e402061` (feat)
2. **Task 2: Create agent audience templates** - `06f5658` (feat)
3. **Task 3: Create devops audience templates** - `8d7f591` (feat)

## Files Created/Modified
- `create-docs/references/templates/developers/ARCHITECTURE.template.md` - System design, ADRs, data model, component map (184 lines)
- `create-docs/references/templates/developers/DEVELOPER_GUIDE.template.md` - Setup, structure, common tasks, extension patterns (252 lines)
- `create-docs/references/templates/developers/QUICK_REFERENCE.template.md` - Commands, file paths, config, API surface (143 lines)
- `create-docs/references/templates/agents/SYSTEM_MAP.template.md` - Component registry, file structure, entry points, data flow, API surface (201 lines)
- `create-docs/references/templates/agents/CONVENTIONS.template.md` - Naming, code patterns, do/don't rules, imports (249 lines)
- `create-docs/references/templates/agents/GOTCHAS.template.md` - Edge cases, ordering constraints, invariants, common mistakes (189 lines)
- `create-docs/references/templates/agents/TESTING.template.md` - Test structure, running tests, patterns, writing new tests (294 lines)
- `create-docs/references/templates/devops/OPERATIONS.template.md` - Infrastructure, deployment, service management, config (291 lines)
- `create-docs/references/templates/devops/TROUBLESHOOTING.template.md` - Triage decision tree, common issues, log analysis, health checks (441 lines)

## Decisions Made
- Used consistent DataForge example project (data pipeline tool) across all developer and agent templates for coherent cross-template references
- Agent templates use explicit MUST/SHOULD/MUST NOT constraint language following the Codified Context paper (arXiv:2602.20478)
- DevOps OPERATIONS template structured closely following the detailed example from 02-RESEARCH.md

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 9 audience-specific templates complete and verified
- Combined with Plan 01's shared/end-user templates, the full template inventory is ready for writer agents
- Plan 03 (agent definitions) and Plan 04 (install.sh patch) can proceed
- Templates are self-contained: a writer agent can read any template and understand exactly what sections to generate and what quality level is expected

## Self-Check: PASSED

All 9 template files verified present. All 3 task commits verified in git log. SUMMARY.md exists.

---
*Phase: 02-templates-agent-definitions*
*Completed: 2026-03-16*
