# Phase 17: Auto-Doc Generate Docs Improvements - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/auto-doc-v1.2/concept.md) + discussion

<domain>
## Phase Boundary

Improve generate pipeline efficiency by adding Serena guidance to writer agents and splitting docs-scan.json into per-audience view files. No schema changes, no scan pipeline changes, no new commands.

</domain>

<decisions>
## Implementation Decisions

### Serena guidance in writer agents
- Add "Source Code Exploration" principle to all 5 writer agent .md files: `glossary-writer.md`, `end-user-writer.md`, `developer-writer.md`, `agent-writer.md`, `devops-writer.md`
- Writers use `get_symbols_overview` (depth: 1) to understand file structure before reading
- Writers use `find_symbol` with `include_body: true` for specific functions/classes they need to document
- Writers use `find_symbol` with `include_info: true` for signatures and docstrings only
- Writers use `Read` only for files Serena cannot parse (yaml, toml, config, markdown, shell scripts, SQL, Dockerfile, .env.example)
- Writers must never read an entire source file — explore structure first, then read specific symbols
- Pattern is adapted from scan-audience.md but oriented for writers who need more code context (include_body: true is the right default)
- Glossary writer gets the same Serena guidance as audience writers — it benefits from code access for writing accurate term definitions during the initial pass (e.g., understanding what "scoring engine" actually does by reading its implementation)

### Per-audience scan view files
- New script: `split-scan-by-audience.py` with two modes
- **Audience mode** (`--mode audience --audience {name} --documents ARCHITECTURE,DEVELOPER_GUIDE`): extracts `project_model` + `gsd_context` + filtered `source_material_index` + filtered `gap_analysis`. Filters `source_material_index` by matching the document prefix of each key (text before first `/`) against the comma-separated document list
- **Glossary mode** (`--mode glossary`): extracts `project_model` + `gsd_context` + all `source_material_index` keys (preserving `{DOCUMENT}/{section-slug}` structure for term discovery) with `source_files` reduced to filenames only
- Output files: `{TMP_DIR}/scan-view-{audience}.json` for audience mode, `{TMP_DIR}/scan-view-glossary.json` for glossary mode
- View files use same top-level key structure as `docs-scan.json` (`project_model`, `gsd_context`, `source_material_index`, `gap_analysis`) so writer agents' existing access patterns work unchanged
- Keys not relevant to the view (`staleness_report`, `note_classifications`, `scan_date`) are omitted
- Shared documents (OVERVIEW, GLOSSARY) have no `source_material_index` entries and are not affected by view filtering
- Per-audience invocations (one call per audience + one for glossary), not batch mode — matches existing per-audience/per-mode CLI patterns and keeps each invocation independently testable

### Generate orchestrator changes
- Orchestrator calls `split-scan-by-audience.py` once per audience + once for glossary before spawning writer agents
- Orchestrator passes the view file path as `scan_data_path` in each writer agent's prompt (replacing the full docs-scan.json path)
- No changes needed in writer agent .md files for scan view routing — the orchestrator already constructs the prompt and controls `scan_data_path`
- In update mode, all audience views are created eagerly (not just for audiences with approved sections) — views are tiny temp files, no point complicating the orchestrator to filter
- Audience-to-document mapping comes from `.docs.config.json` (single source of truth, already read by orchestrator for writer spawning)

### Per-audience view sizing
- Each audience view targets ~5k tokens (well under 10k Read limit) — one Read per agent, zero chunked reads
- Current docs-scan.json is ~19k tokens, causing 5-6 chunked reads per agent (~30 total across generate run)

### Single-write manifests explicitly out of scope
- The per-entry manifest pattern (20+ individual JSON files per writer, merged via add-manifest-entry.py) is intentionally retained
- Each entry is small and validated individually — prevents a single JSON error from losing the entire manifest
- Tool call overhead is acceptable compared to reliability benefit

### Claude's Discretion
- Internal structure of `split-scan-by-audience.py` (argument parsing, filtering implementation, error handling)
- Test structure and organization for the new script
- Exact wording of Serena guidance in each writer agent (adapt to audience-specific writing patterns)
- Whether to add any logging/metrics to track token reduction

</decisions>

<specifics>
## Specific Ideas

- Evidence from road-runner generate run shows token consumption per agent: Glossary 62.9k, End-users 90.3k, Developers 119.5k, Agents 175.3k (bottleneck at 12m 57s), Devops 126.1k — total ~630k
- The scan agents already have working Serena guidance in `scan-audience.md` — adapt the same pattern for writers
- Agents writer is the bottleneck (175.3k tokens, 12m 57s) because it reads ~25 full files with no Serena
- Glossary writer currently has no instructions to read source code, but quality definitions require understanding implementations — Serena guidance enables this without full file reads

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scan-audience.md`: Contains working Serena guidance pattern (lines 67-74 process, lines 161-171 principles) for scan agents — adapt for writer agents
- `split-findings.py` (codebase-health): Existing precedent for splitting a shared JSON contract into filtered subsets with atomic writes
- `.docs.config.json`: Already defines documents per audience — use as source of truth for `--documents` argument to split-scan

### Established Patterns
- Writer agents receive `scan_data_path` from generate orchestrator — view files slot into this existing mechanism
- Per-entry JSON I/O pattern (add-manifest-entry.py) — retained, not changed
- `{SCRIPTS_DIR}` placeholder pattern for install-time sed resolution of script paths
- Orchestrator design principle (line 560): "Agents receive file paths only; they read files themselves. Do not paste content into prompts."

### Integration Points
- `auto-doc-generate.md` orchestrator: calls new script, routes view paths to writer agents
- 5 writer agent .md files: receive Serena guidance additions
- `install.sh`: must include `split-scan-by-audience.py` in scripts deployment

</code_context>

<deferred>
## Deferred Ideas

- Single-write manifests — explicitly deferred; per-entry pattern retained for reliability
- Wall time estimate precision — rough directional estimates only, not commitments

</deferred>

---

*Phase: 17-auto-doc-generate-docs-improvements*
*Context gathered: 2026-03-23 via context import + discussion*
