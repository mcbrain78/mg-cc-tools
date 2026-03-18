# Phase 4: Generate Pipeline

> Source: docs/work-queue/todo/doc-command/DESIGN.md
> Phase goal: The generate step creates or updates all audience-segmented documents section-by-section using templates and scan results
> Requirements: GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06, DOC-07, DOC-08, DOC-09, DOC-10, DOC-11, DOC-12, DOC-13, CMD-03

---

## Pipeline > Step 2: Generate/Update (writes docs, with approval gate)

**Initial Mode** (no existing docs):
For each document, generate section-by-section following the three-layer template. For each section:
1. Read the template (heading + purpose + example)
2. Read the source material mapped to this section from the scan
3. Generate the section content
4. Move to next section

Writer agents run in parallel — one per audience (4 total) plus a glossary agent.

**Update Mode** (docs exist):
1. Present staleness report to user: which sections are stale, what changed, draft suggested update
2. Present classified inbox notes: where each note would go, how it would be expanded
3. User approves which updates to apply
4. Generate only approved sections, feeding source material per section
5. Integrate approved inbox notes into their target locations

**Writer Agent Inputs:**
- The audience-specific templates for their documents
- The source material index entries from the scan
- The current doc content (if exists, for update mode)
- The glossary (for terminology consistency)
- The style guide (cross-audience writing conventions)

**Section Ownership Tracking:**
Each generated section includes an HTML comment marker for future staleness detection:
```html
<!-- docs-meta: last-updated: 2026-03-15, sources: [src/flows/scoring.py, src/models/config.py] -->
```
This tells future scans which code files drive this section and when it was last generated.

**Cross-Document Consistency:**
- Writer agents receive the glossary as input
- New terms discovered during writing are proposed for glossary addition
- The glossary agent reconciles all proposals and updates GLOSSARY.md
- OVERVIEW.md is generated last, after all subdirs are complete, so it can accurately route audiences

---

## Commands

| Command | Purpose | Pipeline Step |
|---|---|---|
| `/mg:create-docs-generate` | Create or update documents section-by-section | Step 2 (writes docs) |

---

## Output Directory (committed to git)

```
docs/auto-doc/
├── OVERVIEW.md                     ← Shared: business context, system summary, audience routing
├── GLOSSARY.md                     ← Shared: term definitions (source of truth for terminology)
│
├── end-users/
│   ├── USER_GUIDE.md               ← Task-oriented how-to articles
│   └── [domain-specific].md        ← Project-specific (defined in config)
│
├── developers/
│   ├── ARCHITECTURE.md             ← System design, data model, ADRs
│   ├── DEVELOPER_GUIDE.md          ← Code examples, extension patterns, common tasks
│   └── QUICK_REFERENCE.md          ← Cheat sheet: paths, commands, lookups
│
├── agents/
│   ├── SYSTEM_MAP.md               ← Component registry with file paths + API surface
│   ├── CONVENTIONS.md              ← Code patterns, naming, do/don't rules
│   ├── GOTCHAS.md                  ← Edge cases, ordering constraints, invariants
│   └── TESTING.md                  ← Test patterns, isolation, fixtures
│
└── devops/
    ├── OPERATIONS.md               ← Deployment, service management, config
    └── TROUBLESHOOTING.md          ← Symptom → cause → fix runbook entries
```

---

## Notes Integration During `/mg:create-docs`

During the generate step, classified notes are:
1. Presented to the user for approval (audience, document, section assignment)
2. Expanded from raw note into proper prose matching the target document's style
3. Inserted at the classified location
4. Marked as `"status": "integrated"` in the inbox with the integration date

---

## Open Items (Phase 4)

5. **Section-by-section generation protocol** — Exact mechanism for feeding one section at a time to the writer agent (sequential within an agent, parallel across audiences).
7. **Custom document support** — How project-specific documents get templates (user-provided? generated from description?).

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
- How subagents receive work + write output: `codebase-health/agents/implementor.md`
- Status tracking during multi-agent work: `codebase-health/scripts/update-findings.py`
- Parallel agent coordination: `codebase-health/commands/codebase-health-scan.md` (agent spawning section)

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
*Phase: 04-generate-pipeline*
*Date: 2026-03-16*
