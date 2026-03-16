# Phase 5: Verify, Notes Command & Router - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning
**Source:** Merged — Context import (docs/work-queue/todo/doc-command/phase-docs/phase-05-verify-notes-command-router.md) + milestone discussion (cross-cutting pass)

<domain>
## Phase Boundary

The verify step validates documentation quality, the add-docs command captures notes standalone, and the router ties the full pipeline together. Three commands: `/mg:create-docs-verify`, `/mg:add-docs`, and `/mg:create-docs` (router).

</domain>

<decisions>
## Implementation Decisions

### Reference Integrity Check (VFY-01)
- Every file path, symbol, command mentioned in docs → verify it exists in the codebase
- Uses `check-references.py` (built in Phase 1)

### Cross-Doc Consistency (VFY-02)
- Terms used match glossary definitions
- Architecture descriptions match developer guide descriptions of the same components

### Diataxis Mixing Detection (VFY-03)
- Flag sections where tutorial content creeps into reference docs
- Flag explanation buried in how-to guides
- The #1 documentation anti-pattern per Diataxis framework

### Completeness Check (VFY-04)
- Major code components have at least basic documentation for each relevant audience

### Example Validity (VFY-05)
- Code examples in docs are syntactically valid

### Link Integrity (VFY-06)
- Internal markdown links between docs resolve

### Verify Output (VFY-07)
- Output: `.mg/docs/docs-verify-report.md`
- Issues categorized by severity
- User reviews and can trigger re-generation for flagged sections

### Router Command (CMD-01)
- Command: `/mg:create-docs`
- Full pipeline entry point: scan → generate → verify
- Detects existing state: no docs = initial creation, existing docs = update mode, existing scan = resume
- Routes to correct step automatically
- Same pattern as `/mg:codebase-health`

### Verify Command (CMD-04)
- Command: `/mg:create-docs-verify`
- Read-only — checks but does not modify docs
- Cross-reference check, Diataxis mixing detection, completeness audit
- Agent doc quality: YAML frontmatter valid, file paths in SYSTEM_MAP.md exist, convention rules reference real patterns

### Add-Docs Command (CMD-05)
- Command: `/mg:add-docs "note"`
- Standalone command — writes inbox only, does not trigger pipeline
- Note stored in `.mg/docs/notes-inbox.json` with: unique ID (NOTE-001 format), raw text, timestamp, context (active file, GSD phase)
- Auto-classified: audience → document → section, with confidence level
- User sees classification immediately and can correct it
- Note stays in inbox until `/mg:create-docs` processes it
- Notes carry GSD phase context for better classification routing

### Backlog Integration
- Documentation gaps found by verify step can optionally be added to `.planning/BACKLOG.md` as documentation debt items

### Cross-Cutting Decisions
- Verify report includes glossary inconsistency flags from Phase 4's reconciliation pass — these are surfaced alongside VFY-02 cross-doc consistency checks *(from milestone discussion)*
- Agents receive file paths only, read files themselves — verifier agent reads docs and source code via paths *(from milestone discussion)*
- `/mg:add-docs` lives inside `create-docs/` tool directory — deployed by the same install script *(from milestone discussion)*
- Tool installs to `.claude/create-docs/` — verify and router commands reference scripts at `.claude/create-docs/scripts/` *(from milestone discussion)*
- Road-runner validation baked into phase success criteria — full pipeline must run end-to-end on `../road-runner` *(from milestone discussion)*

### Claude's Discretion
- Verify report format and severity categorization (critical, warning, info)
- How verify step presents re-generation options to user
- Add-docs classification correction UX (how the user corrects auto-classification)
- Router state detection heuristics (how to distinguish "partial scan" from "complete scan")
- Whether add-docs should support batch note ingestion
- How backlog integration is triggered (automatic suggestion vs manual)

</decisions>

<specifics>
## Specific Ideas

- Follow codebase-health patterns as implementation exemplars:
  - Router / state detection pattern: `codebase-health/commands/codebase-health.md`
  - Verification step: `codebase-health/commands/codebase-health-verify.md`
  - Verification script pattern: `codebase-health/scripts/verify-finding.py`
- The router detects state and routes — same pattern as `/mg:codebase-health` which detects existing scan results and routes to the appropriate step
- Add-docs is a lightweight companion command, not a full pipeline — runs independently

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codebase-health/commands/codebase-health.md`: Reference for router/state detection pattern
- `codebase-health/commands/codebase-health-verify.md`: Reference for verification step
- `codebase-health/scripts/verify-finding.py`: Pattern for verification script
- Phase 1 scripts: `check-references.py` (for VFY-01), `add-note.py` (for CMD-05), `classify-note.py` (for CMD-05)

### Established Patterns
- Router commands detect state and route to appropriate step
- Verification steps are read-only with approval gates
- Companion commands (like add-docs) operate independently of the main pipeline

### Integration Points
- Verify reads: `docs/auto-doc/` (generated docs), project source code, glossary
- Verify writes: `.mg/docs/docs-verify-report.md`
- Add-docs writes: `.mg/docs/notes-inbox.json`
- Router reads: `.mg/docs/` state files to determine pipeline position

</code_context>

<deferred>
## Deferred Ideas

- Backlog integration as automated pipeline step (BKL-01) — v2 requirement, manual for now
- Real-time sync via file watchers or CI hooks — out of scope
- Custom document template authoring UI — out of scope

</deferred>

---

*Phase: 05-verify-notes-command-router*
*Context gathered: 2026-03-16 via context import*
