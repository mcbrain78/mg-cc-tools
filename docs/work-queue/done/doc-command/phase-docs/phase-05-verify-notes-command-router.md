# Phase 5: Verify, Notes Command & Router

> Source: docs/work-queue/todo/doc-command/DESIGN.md
> Phase goal: The verify step validates documentation quality, the add-docs command captures notes standalone, and the router ties the full pipeline together
> Requirements: VFY-01, VFY-02, VFY-03, VFY-04, VFY-05, VFY-06, VFY-07, CMD-01, CMD-04, CMD-05

---

## Pipeline > Step 3: Verify (read-only, with approval gate)

Checks the generated/updated documentation for quality issues:

- **Reference integrity**: Every file path, symbol, command mentioned in docs → verify it exists in the codebase (`check-references.py`) *(built in Phase 1)*
- **Cross-doc consistency**: Terms used match glossary, architecture descriptions match developer guide descriptions of the same components
- **Diataxis mixing**: Flag sections where tutorial content creeps into reference docs, or explanation gets buried in how-to guides (the #1 documentation anti-pattern per Diataxis)
- **Completeness**: Major code components have at least basic documentation for each relevant audience
- **Example validity**: Code examples are syntactically valid
- **Link integrity**: Internal markdown links between docs resolve
- **Agent doc quality**: YAML frontmatter is valid, file paths in SYSTEM_MAP.md exist, convention rules reference real patterns

**Output**: `.mg/docs/docs-verify-report.md` with issues categorized by severity. User reviews and can trigger re-generation for flagged sections.

---

## Commands

| Command | Purpose | Pipeline Step |
|---|---|---|
| `/mg:create-docs` | Full pipeline: scan → generate → verify. Entry point that detects state and routes. | All |
| `/mg:create-docs-verify` | Cross-reference check, Diataxis mixing detection, completeness audit | Step 3 (read-only) |
| `/mg:add-docs "note"` | Capture a note to the inbox with auto-classification | Standalone (writes inbox only) |

The main entry point `/mg:create-docs` detects existing state (no docs = initial creation, existing docs = update mode, existing scan = resume) and routes to the appropriate step — same pattern as `/mg:codebase-health`.

---

## `/mg:add-docs` — Notes Inbox

### Use Case

During development, you notice something important to document:
```
/mg:add-docs "Production server is at 10.0.1.50, SSH via bastion.example.com on port 2222"
/mg:add-docs "Flows should only be called once during tests — calling twice causes duplicate DB entries"
/mg:add-docs "Use the .env.staging keys when testing against the staging API, never .env.production"
```

### Behavior

1. Note stored in `.mg/docs/notes-inbox.json` with:
   - Unique ID (`NOTE-001`, `NOTE-002`, ...)
   - Raw text from the user
   - Timestamp
   - Context: active file (if detectable), GSD phase (if applicable)
2. Auto-classified: audience → document → section, with confidence level
3. User sees the classification immediately and can correct it
4. Note stays in inbox until `/mg:create-docs` processes it

---

## GSD Integration

### During Development

- `/mg:add-docs` captures operational knowledge as it's discovered
- Notes carry GSD phase context for better classification routing

### Backlog Integration

Documentation gaps found by the verify step can optionally be added to `.planning/BACKLOG.md` as documentation debt items.

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
- Router / state detection pattern: `codebase-health/commands/codebase-health.md`
- Verification step: `codebase-health/commands/codebase-health-verify.md`
- Verification script pattern: `codebase-health/scripts/verify-finding.py`

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
*Phase: 05-verify-notes-command-router*
*Date: 2026-03-16*
