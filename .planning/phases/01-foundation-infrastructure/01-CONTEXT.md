# Phase 1: Foundation & Infrastructure - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning
**Source:** Merged — Context import (docs/work-queue/todo/doc-command/phase-docs/phase-01-foundation-infrastructure.md) + milestone discussion (cross-cutting pass)

<domain>
## Phase Boundary

All supporting infrastructure exists so pipeline steps and commands can be built on top of them. This includes Python scripts, schema definition, configuration system, install script, style guide, and project scaffolding.

</domain>

<decisions>
## Implementation Decisions

### Python Scripts (INF-01 through INF-05)
- `add-note.py` — Atomic append to `notes-inbox.json`. Uses only stdlib.
- `classify-note.py` — Deterministic heuristics for note classification (audience → document → section with confidence level)
- `check-references.py` — Verify file paths and symbol names mentioned in docs exist in the codebase
- `merge-scan.py` — Merge per-audience scan results into single `docs-scan.json`
- `staleness-check.py` — Git-based section freshness analysis (which source files changed since section was last generated)
- All scripts live in `scripts/` with a shared `lib/` for JSON I/O and git helpers
- Python stdlib only — no pip dependencies

### Schema Definition (INF-06)
- Full `docs-scan.json` schema defined in `references/schema.md` (following codebase-health pattern)
- Key top-level fields: `project`, `scan_date`, `root_path`, `mode` (initial|update), `project_model`, `source_material_index`, `staleness_report`, `note_classifications`, `gap_analysis`, `gsd_context`
- `project_model` contains: `tech_stack`, `entry_points`, `components` (each with name, path, purpose, public_api, dependencies, database_tables), `infrastructure`
- `source_material_index` maps document/section → source files with staleness marker
- `staleness_report` entries have: document, section, reason, changed_files, severity, suggested_action
- `note_classifications` entries have: note_id, audience, document, section, confidence
- `gap_analysis` has: undocumented_components, missing_for_audience (per audience)
- `gsd_context` has: milestone, completed_phases, deviations, new_requirements_completed

### Inbox Schema (notes-inbox.json)
- Each note has: id (NOTE-001 format), text, added (ISO timestamp), context (phase, file), classification (audience, document, section, confidence), status (pending/integrated)
- This structure is consumed by Phase 5's `/mg:add-docs` command and Phase 4's notes integration

### Style Guide (INF-07)
- Cross-audience writing conventions in `references/style-guide.md`
- Open item: exact content TBD during implementation

### Install Script (INF-08)
- Three modes: `--project [<dir>]`, `--global`, `--target <path>`
- Installs: commands → `.claude/commands/mg/`, agents → `.claude/docs/agents/`, scripts → `.claude/docs/scripts/`, references → `.claude/docs/references/`
- Six sed placeholder replacements: `agents/`, `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}`, `{GLOBAL_CONFIG}`, `references/schema.md`, `references/style-guide.md`
- Follows standard mg-cc-tools install pattern (like codebase-health)

### Project Scaffolding (INF-09)
- `--project` mode creates `.mg/docs/` with:
  - `.docs.config.json` (copy of global defaults for user to customize)
  - `notes-inbox.json` (empty: `{"notes": []}`)
  - `scan-logs/` directory
- Tool workspace also holds at runtime: `docs-scan.json`, `docs-update-report.md`, `docs-verify-report.md`

### Configuration (INF-10)
- Global defaults in `.docs.config.json` with: `docs_dir`, `audiences` (4 audiences, each with enabled flag and document list), `shared_documents`, `custom_documents`, `gsd_integration`
- Project overrides at `.mg/docs/.docs.config.json` — fields override global, missing fall back to defaults
- Common overrides: disable audience, add custom documents, change docs_dir, disable GSD integration

### Cross-Cutting Decisions
- Tool directory in mg-cc-tools: `create-docs/` (matches primary command `/mg:create-docs`) *(from milestone discussion)*
- Install path: `.claude/create-docs/` (agents, scripts, references, templates all under this path) *(from milestone discussion)* ⚠️ CONFLICTS WITH: existing references to `.claude/docs/` in Install Script and Integration Points sections — update all paths to `.claude/create-docs/`
- `/mg:add-docs` command lives inside `create-docs/` tool directory — single install script deploys everything *(from milestone discussion)*
- Custom documents (DOC-04) deferred to v2 — keep `custom_documents` in config schema as placeholder but don't implement generation *(from milestone discussion)*
- Road-runner validation baked into phase success criteria — scripts must produce correct output on `../road-runner` *(from milestone discussion)*
- Existing `docs/` directory in mg-cc-tools stays as-is (design documents) — no conflict since tool outputs to TARGET project's `docs/auto-doc/` *(from milestone discussion)*

### Claude's Discretion
- Internal code organization within scripts (module structure, shared utilities design)
- Error handling patterns across scripts
- Logging format and verbosity
- Test structure for Python scripts (open item #8)
- Schema format choice: JSON Schema vs structured markdown in `references/schema.md`
- Style guide organization and section structure

</decisions>

<specifics>
## Specific Ideas

- Follow codebase-health patterns as implementation exemplars:
  - Install script with sed replacements: `codebase-health/install.sh`
  - Atomic JSON I/O scripts: `codebase-health/scripts/add-finding.py`
  - Schema definition format: `codebase-health/references/schema.md`
  - Config layering logic: `codebase-health/commands/codebase-health-scan.md` (config merge section)
- The docs tool mirrors codebase-health's architecture: 3-step pipeline, shared JSON data contract, parallel subagents, Python scripts for deterministic operations, config layering, state detection, `.mg/docs/` workspace
- Key difference from codebase-health: Step 2 is creative (writing docs), not diagnostic

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codebase-health/install.sh`: Reference implementation for three-mode install with sed replacements
- `codebase-health/scripts/add-finding.py`: Pattern for atomic JSON I/O scripts
- `codebase-health/references/schema.md`: Pattern for data contract schema definition

### Established Patterns
- mg-cc-tools install pattern: commands → `.claude/commands/mg/`, supporting files → `.claude/<tool-name>/`
- Python scripts use only stdlib, no pip dependencies
- Config layering: global defaults + project overrides with field-level merge

### Integration Points
- `.claude/commands/mg/` — where command .md files are installed
- `.claude/docs/` — where agents, scripts, references land
- `.mg/docs/` — project workspace created during scaffolding

</code_context>

<deferred>
## Deferred Ideas

- Schema drift detection (STL-01) and terminology drift detection (STL-02) — v2 requirements
- Backlog integration (BKL-01) — v2 requirement
- Testing strategy details — cross-cutting open item, applies to all phases

</deferred>

---

*Phase: 01-foundation-infrastructure*
*Context gathered: 2026-03-16 via context import*
