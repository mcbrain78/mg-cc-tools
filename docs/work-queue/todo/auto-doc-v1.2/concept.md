# Auto-Doc v1.2 — Generate Pipeline Efficiency

## Situation

Auto-doc v1.1 is functional end-to-end. The scan pipeline uses Serena for efficient code exploration (get_symbols_overview, find_symbol, find_referencing_symbols) and produces quality results with ~363k tokens across 4 parallel audience agents.

The generate pipeline was tested on road-runner (first real target): 12 files, 72 sections, ~29k words, 22m 30s. Output quality is good. The pipeline works.

## Complication

The generate pipeline has two efficiency problems discovered during road-runner testing:

### 1. Writer agents don't use Serena (~630k tokens, should be ~400k)

The scan agents got Serena guidance in scan-audience.md, but the 5 writer/glossary agents still use the old pattern: `Read(file.py, lines 1-80)` across dozens of files. The agents writer consumed 175k tokens reading nearly every source file — most of which could be explored via get_symbols_overview + find_symbol.

Evidence from the road-runner generate run:
- Glossary writer: 62.9k tokens, reads 16 files with `lines 1-60`
- End-users writer: 90.3k tokens, no Serena
- Developers writer: 119.5k tokens, 1 find_symbol call total
- Agents writer: 175.3k tokens (bottleneck at 12m 57s), no Serena, reads ~25 full files
- Devops writer: 126.1k tokens, no Serena

Writers need more code than scan agents (they write *about* the code), so include_body: true is the right default. But they still shouldn't read 25 entire files to document 10 specific functions.

### 2. docs-scan.json exceeds token limit for every agent (19k tokens)

Every agent (glossary + 4 writers + glossary reconciliation = 6 total) hits the 10k Read token limit on docs-scan.json and reads it in 5-6 chunks. That's ~30 chunked reads of the same file per generate run.

Each writer only needs:
- project_model (~3k tokens, common)
- gsd_context (~1k tokens, common)
- source_material_index entries for their audience's documents (~1-3k tokens)
- gap_analysis filtered to their audience

A per-audience "view" file would be ~5k tokens — well under the limit, one Read.

The glossary writer needs cross-audience data but not the full index. A compact glossary view with project_model + gsd_context + all section keys (for term discovery) with source_files reduced to filenames only would also fit under 10k tokens.

## Solution

### A. Serena guidance in writer agents (5 files, ~5 lines each)

Add a "Source Code Exploration" principle to each writer agent:
- `glossary-writer.md`
- `end-user-writer.md`
- `developer-writer.md`
- `agent-writer.md`
- `devops-writer.md`

Pattern (adapted for writers who need more code than scan agents):
```
Use get_symbols_overview (depth: 1) to understand file structure before reading.
Use find_symbol with include_body: true for specific functions/classes you need to document.
Use find_symbol with include_info: true for signatures and docstrings.
Only use Read for files Serena cannot parse (yaml, toml, config, markdown, shell scripts, SQL, Dockerfile, .env.example).
Never read an entire source file — explore structure first, then read specific symbols.
```

### B. Per-audience scan views (1 new script + orchestrator changes)

New script: `split-scan-by-audience.py`

Two modes:
- `--mode audience --audience {name} --documents ARCHITECTURE,DEVELOPER_GUIDE` — extracts project_model + gsd_context + filtered source_material_index + filtered gap_analysis. Filters `source_material_index` by matching the document prefix of each key (text before the first `/`) against the comma-separated document list.
- `--mode glossary` — extracts project_model + gsd_context + all `source_material_index` keys (preserving the `{DOCUMENT}/{section-slug}` structure for term discovery) with `source_files` reduced to filenames only. Shared documents (OVERVIEW, GLOSSARY) have no `source_material_index` entries and are not affected by view filtering.

Output files: `{TMP_DIR}/scan-view-{audience}.json` for audience mode, `{TMP_DIR}/scan-view-glossary.json` for glossary mode. View files use the same top-level key structure as `docs-scan.json` (`project_model`, `gsd_context`, `source_material_index`, `gap_analysis`) so writer agents' existing access patterns work unchanged. Keys not relevant to the view (`staleness_report`, `note_classifications`, `scan_date`) are omitted.

The generate orchestrator calls the script once per audience + once for glossary before spawning writer agents. The orchestrator then passes the view file path as `scan_data_path` in each writer agent's prompt (replacing the full docs-scan.json path). No changes needed in the writer agent .md files for this — the orchestrator already constructs the prompt and controls `scan_data_path`.

## Expected Impact (rough estimates)

| Metric | Current (v1.1) | Estimated (v1.2) |
|--------|---------------|---------------|
| Generate total tokens | ~630k | lower (Serena + view files reduce redundant reads) |
| docs-scan.json chunk reads | ~30 | 0 |
| Generate wall time | 22m 30s | lower (bottleneck agent reads less) |

## Not in scope

**Single-write manifests.** The per-entry manifest pattern (20+ individual JSON files per writer, merged via add-manifest-entry.py) is verbose (~80 tool calls) but intentionally safe. Each entry is small and validated individually by the script. Given that LLM-generated JSON is error-prone (agents scan fails write-scan-output.py validation on every run), the per-entry approach prevents a single JSON error from losing the entire manifest. The tool call overhead is acceptable compared to the reliability benefit.

## Scope

- 5 writer agent .md files updated (Serena guidance)
- 1 command .md updated (auto-doc-generate.md — view file paths + scan_data_path routing)
- 1 new script with tests (split-scan-by-audience.py)
- No schema changes, no scan pipeline changes, no new commands

## Dependencies

- Serena must be installed and configured with correct project root (verified working in v1.1)
- Requires reinstall of auto-doc in target projects after changes

## Verification

- Run generate on road-runner, compare token counts per agent
- Verify all 12 docs regenerate with same quality
- Verify glossary reconciliation still works with compact view
- Verify per-audience view files contain all data each writer needs (spot-check against full docs-scan.json)
