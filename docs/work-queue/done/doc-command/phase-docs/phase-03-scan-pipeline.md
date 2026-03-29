# Phase 3: Scan Pipeline

> Source: docs/work-queue/todo/doc-command/DESIGN.md
> Phase goal: The scan step analyzes a project and produces a complete docs-scan.json that downstream generation can consume
> Requirements: SCN-01, SCN-02, SCN-03, SCN-04, SCN-05, SCN-06, SCN-07, SCN-08, CMD-02

---

## Pipeline > Step 1: Scan (read-only)

**Orientation** — Build understanding of the project:
- Code structure, tech stack, frameworks, entry points
- Deployment artifacts (Dockerfile, docker-compose, systemd units, CI/CD pipelines)
- Existing documentation (docs/, README, CLAUDE.md, inline comments)
- Database schemas, API contracts, configuration files
- Environment files (.env.example, config templates)

**Source Material Index** — Map which code files are relevant to which document and section. This is critical because research shows generating documentation without feeding source material produces hallucinations. The index structure:

```json
{
  "documents": {
    "devops/OPERATIONS.md": {
      "sections": {
        "Infrastructure": {
          "sources": ["deploy/docker-compose.yml", "deploy/config.yml", ".env.example"],
          "staleness": null
        },
        "Deployment": {
          "sources": ["Makefile", "scripts/deploy.sh", ".github/workflows/deploy.yml"],
          "staleness": null
        }
      }
    }
  }
}
```

**GSD Context** (if `.planning/` exists):
- Read all phase SUMMARY.md files from the current/latest milestone to understand what changed
- Read REQUIREMENTS.md traceability table for feature coverage
- Read VERIFICATION.md files for known gaps
- Read MILESTONES.md for historical context
- These drive targeted updates rather than full rewrites in update mode

**Staleness Detection** (if docs already exist):
- **Code-reference check**: Do file paths, function names, class names mentioned in docs still exist? (Python script `check-references.py`) *(built in Phase 1)*
- **Git-based freshness**: Which code files referenced by a doc section changed since that section was last touched? (Python script `staleness-check.py`) *(built in Phase 1)*
- **Schema drift**: Compare documented DB schemas, API contracts against actual source
- **Terminology drift**: Do glossary terms match actual usage in code and docs?
- **GSD deviation signals**: Phase SUMMARYs listing deviations and new decisions flag sections that likely need updates

**Notes Inbox Processing** — Classify each pending note from `.mg/docs/notes-inbox.json`:
- Target audience, document, and section
- Confidence level of the classification
- Proposed expansion outline

**Output**: `.mg/docs/docs-scan.json` — the shared data contract containing:
- Project model (components, APIs, infrastructure discovered)
- Source material index (code file → document → section mapping)
- Per-section staleness report (if docs exist)
- Note classifications (from inbox)
- Gap analysis (what exists in code but isn't documented for each audience)

---

## Commands

| Command | Purpose | Pipeline Step |
|---|---|---|
| `/mg:create-docs-scan` | Analyze project, build source material index, detect staleness | Step 1 (read-only) |

---

## GSD Integration > Post-Milestone Workflow

1. User completes a milestone via GSD
2. User runs `/mg:create-docs`
3. Scan step reads all phase SUMMARY.md files from the completed milestone:
   - What was built (accomplishments)
   - What changed from plan (deviations)
   - What decisions were made (runtime choices)
   - What requirements were completed
4. REQUIREMENTS.md traceability tells the scan which features are new
5. VERIFICATION.md highlights gaps and edge cases worth documenting
6. Writer agents produce targeted section updates (not full rewrites)
7. Notes accumulated during the milestone via `/mg:add-docs` get integrated

---

## Open Items (Phase 3)

6. **Staleness detection granularity** — How `docs-meta` comments map to git blame for freshness checking. Edge cases with reformatted files.

---

## Additional Context

### Purpose

A documentation tool that scans a project and generates/maintains audience-segmented documentation. It integrates with the GSD milestone lifecycle so documentation stays current as the project evolves, and provides a lightweight note-capture command for recording operational knowledge during development.

### Problem Statement

Documentation is manually created (see `ai-stock-ranker/docs/documentation_v3/` for an example of what the user produces by hand). This is time-consuming, falls out of date as code changes, and lacks systematic coverage across audiences. Different consumers of documentation (end users, developers, AI agents, operations staff) need fundamentally different content, formats, and depth levels — but maintaining 4 parallel documentation sets manually is impractical.

### Relationship to Existing mg-cc-tools

#### Follows Codebase-Health Pattern

The docs tool mirrors codebase-health's architecture:
- 3-step pipeline (scan → generate → verify, like scan → verify → implement)
- Shared JSON data contract between steps
- Parallel subagents per category (audiences instead of health categories)
- Python scripts for deterministic operations (JSON I/O, reference checking)
- Config layering (global defaults + project overrides)
- State detection for pipeline resumption
- `.mg/docs/` workspace (like `.mg/health-scan/`)

**Key files to study as implementation exemplars:**
- Scan orchestration + parallel agent spawning: `codebase-health/commands/codebase-health-scan.md`
- Orientation step pattern: `codebase-health/commands/codebase-health-scan.md` (orientation section)
- Per-category scan merge: `codebase-health/scripts/merge-findings.py`

#### Differences from Codebase-Health

- Step 2 is **creative** (writing docs), not diagnostic (verifying findings)
- Has an approval gate between scan and generate (staleness report review)
- Has a companion command (`/mg:add-docs`) for incremental note capture
- Templates drive generation (codebase-health uses agent specialization)
- Output is committed documentation (not a findings JSON + reports)

#### GSD Integration (like debug-triage, update-backlog)

- Reads `.planning/` state when available
- Designed to run post-milestone
- Can feed documentation gaps back to BACKLOG.md
- Notes carry GSD phase context

### Open Item #8

8. **Testing strategy** — Unit tests for Python scripts, integration tests for the pipeline.

---

*Prepared from: docs/work-queue/todo/doc-command/DESIGN.md*
*Phase: 03-scan-pipeline*
*Date: 2026-03-16*
