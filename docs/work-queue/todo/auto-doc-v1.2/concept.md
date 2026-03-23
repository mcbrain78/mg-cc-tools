# Auto-Doc v1.2 — Generate Pipeline Efficiency

## Situation

Auto-doc v1.1 is functional end-to-end. The scan pipeline uses Serena for efficient code exploration (get_symbols_overview, find_symbol, find_referencing_symbols) and produces quality results with ~363k tokens across 4 parallel audience agents.

The generate pipeline was tested on road-runner (first real target): 12 files, 72 sections, ~29k words, 22m 30s. Output quality is good. The pipeline works.

## Complication

The generate pipeline has three efficiency problems discovered during road-runner testing:

### 1. Writer agents don't use Serena (~630k tokens, should be ~400k)

The scan agents got Serena guidance in scan-audience.md, but the 6 writer/glossary agents still use the old pattern: `Read(file.py, lines 1-80)` across dozens of files. The agents writer consumed 175k tokens reading nearly every source file — most of which could be explored via get_symbols_overview + find_symbol.

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

The glossary writer needs cross-audience data but not the full index. A compact glossary view with project_model + gsd_context + flat list of unique source files would also fit under 10k tokens.

### 3. Inline Python for manifest merge

The generate orchestrator has a ~25-line `python3 -c "..."` block for merging temp manifests to the persisted reference-manifests/ directory. This is the last inline Python in the auto-doc command files, violating the convention we enforced in v1.1 (all deterministic logic in scripts/*.py).

## Solution

### A. Serena guidance in writer agents (6 files, ~5 lines each)

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
Only use Read for non-code files (yaml, toml, config, markdown, .env.example).
Never read an entire source file — explore structure first, then read specific symbols.
```

### B. Per-audience scan views (1 new script + orchestrator changes)

New script: `split-scan-by-audience.py`

Two modes:
- `--mode audience --audience {name} --documents {list}` — extracts project_model + gsd_context + filtered source_material_index + filtered gap_analysis
- `--mode glossary` — extracts project_model + gsd_context + flat list of unique source files from all entries

The generate orchestrator calls it once per audience + once for glossary before spawning agents. Each writer reads its small view file (~5k tokens) instead of the full 19k token scan JSON.

### C. Manifest merge script (1 new script + orchestrator change)

New script: `merge-manifests.py`

Takes `--tmp-dir`, `--output-dir`, `--audiences`. Handles:
- Read temp manifest per audience from tmp/
- Remove _written_sections metadata entries
- Overlay onto persisted manifest (update mode: preserve unmodified sections)
- Update generated timestamp
- Write to reference-manifests/

Replaces the inline `python3 -c "..."` block in auto-doc-generate.md.

## Expected Impact

| Metric | Current (v1.1) | Target (v1.2) |
|--------|---------------|---------------|
| Generate total tokens | ~630k | ~400k |
| Agents writer tokens | 175k | ~90-100k |
| docs-scan.json chunk reads | ~30 | 0 |
| Generate wall time | 22m 30s | ~15-17m |
| Inline Python in .md files | 1 block | 0 |

## Not in scope

**Single-write manifests.** The per-entry manifest pattern (20+ individual JSON files per writer, merged via add-manifest-entry.py) is verbose (~80 tool calls) but intentionally safe. Each entry is small and validated individually by the script. Given that LLM-generated JSON is error-prone (agents scan fails write-scan-output.py validation on every run), the per-entry approach prevents a single JSON error from losing the entire manifest. The tool call overhead is acceptable compared to the reliability benefit.

## Scope

- 6 agent .md files updated (Serena guidance)
- 1 command .md updated (auto-doc-generate.md — view file paths + merge script call)
- 2 new scripts with tests (split-scan-by-audience.py, merge-manifests.py)
- No schema changes, no scan pipeline changes, no new commands

## Dependencies

- Serena must be installed and configured with correct project root (verified working in v1.1)
- Requires reinstall of auto-doc in target projects after changes

## Verification

- Run generate on road-runner, compare token counts per agent
- Verify all 12 docs regenerate with same quality
- Verify manifest merge produces identical output to inline Python version
- Verify glossary reconciliation still works with compact view
- Verify single-write manifests contain same section/source data as old per-entry approach
