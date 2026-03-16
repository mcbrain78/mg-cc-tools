# Phase 3: Scan Pipeline - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning
**Source:** Merged — Context import (docs/work-queue/todo/doc-command/phase-docs/phase-03-scan-pipeline.md) + milestone discussion (cross-cutting pass)

<domain>
## Phase Boundary

The scan step analyzes a project and produces a complete docs-scan.json that downstream generation can consume. This is the `/mg:create-docs-scan` command — read-only, does not modify the project.

</domain>

<decisions>
## Implementation Decisions

### Project Orientation (SCN-01)
- Build understanding of: code structure, tech stack, frameworks, entry points
- Scan deployment artifacts: Dockerfile, docker-compose, systemd units, CI/CD pipelines
- Scan existing documentation: docs/, README, CLAUDE.md, inline comments
- Scan database schemas, API contracts, configuration files
- Scan environment files: .env.example, config templates

### Source Material Index (SCN-02)
- Map which code files are relevant to which document and section
- Critical for preventing hallucinations — generation must receive actual source material
- Index structure: `documents → {doc_path} → sections → {section_name} → sources[] + staleness`
- Each source entry is a file path, with a staleness marker (null on initial scan)

### GSD Context Loading (SCN-03)
- If `.planning/` exists, read GSD state:
  - All phase SUMMARY.md files from current/latest milestone (what was built, deviations, decisions, completed requirements)
  - REQUIREMENTS.md traceability table (which features are new)
  - VERIFICATION.md files (known gaps and edge cases worth documenting)
  - MILESTONES.md (historical context)
- These drive targeted updates rather than full rewrites in update mode

### Staleness Detection — Code References (SCN-04)
- Check if file paths, function names, class names mentioned in docs still exist in codebase
- Uses `check-references.py` (built in Phase 1)

### Staleness Detection — Git Freshness (SCN-05)
- Which code files referenced by a doc section changed since that section was last touched?
- Uses `staleness-check.py` (built in Phase 1)
- Open item: how `docs-meta` HTML comments map to git blame for freshness checking; edge cases with reformatted files

### Notes Inbox Classification (SCN-06)
- Classify each pending note from `.mg/docs/notes-inbox.json`
- Classification includes: target audience, document, section, confidence level
- Also produces proposed expansion outline per note

### Gap Analysis (SCN-07)
- Identify code components without documentation for each relevant audience
- Output: `undocumented_components[]` and `missing_for_audience` (per audience)

### Scan Output (SCN-08)
- Output to `.mg/docs/docs-scan.json` (shared data contract defined in Phase 1)
- Contains: project model, source material index, per-section staleness report (if docs exist), note classifications (from inbox), gap analysis

### Scan Command (CMD-02)
- Command: `/mg:create-docs-scan`
- Read-only — analyzes project, does not modify it
- Spawns per-audience scan subagents that merge results via `merge-scan.py` (built in Phase 1)

### Post-Milestone Workflow
- When run after a GSD milestone completion, scan step reads phase SUMMARYs to understand what changed
- REQUIREMENTS.md traceability tells scan which features are new
- VERIFICATION.md highlights gaps worth documenting
- This drives targeted section updates in the generate step, not full rewrites

### Cross-Cutting Decisions
- Scan agents receive file paths only, read files themselves — consistent with all agent context passing *(from milestone discussion)*
- Tool installs to `.claude/create-docs/` — scan command references scripts at `.claude/create-docs/scripts/` *(from milestone discussion)*
- Road-runner validation baked into phase success criteria — scan must produce valid `docs-scan.json` when run on `../road-runner` *(from milestone discussion)*

### Claude's Discretion
- Scan agent orchestration pattern (sequential vs parallel per audience)
- How orientation results are structured before being fed to source material indexing
- Staleness severity thresholds and categorization
- How scan-logs/ files are structured (scan-orientation.md, scan-end-users.md, etc.)
- Schema drift and terminology drift detection approach (noted as v2 features STL-01, STL-02 but basic versions may be needed)

</decisions>

<specifics>
## Specific Ideas

- Follow codebase-health scan patterns as implementation exemplars:
  - Scan orchestration + parallel agent spawning: `codebase-health/commands/codebase-health-scan.md`
  - Orientation step pattern: `codebase-health/commands/codebase-health-scan.md` (orientation section)
  - Per-category scan merge: `codebase-health/scripts/merge-findings.py`
- Staleness detection has two layers: code-reference check (do things still exist?) and git-based freshness (have sources changed since last generation?)
- GSD deviation signals from phase SUMMARYs flag sections that likely need updates

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codebase-health/commands/codebase-health-scan.md`: Reference for scan orchestration and parallel agent spawning
- `codebase-health/scripts/merge-findings.py`: Pattern for merging per-category scan results
- Phase 1 scripts: `check-references.py`, `staleness-check.py`, `merge-scan.py`, `classify-note.py`

### Established Patterns
- Scan commands are read-only — they analyze but don't modify
- Per-category subagents produce partial results that are merged by a Python script
- Orientation step runs first to build project understanding

### Integration Points
- Reads: project source code, existing docs (if any), `.planning/` (if GSD), `.mg/docs/notes-inbox.json`
- Writes: `.mg/docs/docs-scan.json`, `.mg/docs/scan-logs/`
- Consumed by: Phase 4 generate pipeline

</code_context>

<deferred>
## Deferred Ideas

- Schema drift detection (STL-01) — comparing documented DB schemas against actual source (v2)
- Terminology drift detection (STL-02) — glossary terms matching actual code usage (v2)
- GSD deviation signals (STL-03) — phase SUMMARYs flagging stale sections (v2, but basic version may emerge naturally)

</deferred>

---

*Phase: 03-scan-pipeline*
*Context gathered: 2026-03-16 via context import*
