# Phase 14: Auto Doc Reference Manifest - Context

**Gathered:** 2026-03-22 (imported), 2026-03-22 (discussed)
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/auto-doc-1.1/phase-3-reference-manifest.md) + interactive discussion

<domain>
## Phase Boundary

Capture all symbol and file path references at generate time (via manifest), then verify every entry deterministically at verify time (via LSP and filesystem checks). Replaces the unreliable extraction-and-sampling approach in `check-references.py`.

</domain>

<decisions>
## Implementation Decisions

### Manifest format
- One manifest file per audience, stored in `.mg/docs/reference-manifests/`
- Structure: `{"audience": "...", "generated": "ISO timestamp", "documents": {DOCUMENT: {section: {symbols: [...], file_paths: [...]}}}}`
- `symbols` — code identifiers exactly as they appear in source code (function names, class names, constants)
- `file_paths` — files and directories the section references, relative to project root, verified via `os.path.isfile()` / `os.path.isdir()`
- Per-audience granularity — each writer agent writes to its own manifest, no coordination or locking between concurrent writers

### Symbol format
- Always unqualified identifiers (`RoadRunnerBase`, `fetch_quarterly`), never dotted paths (`FMPClient.fetch_quarterly`)
- LSP `documentSymbol` returns hierarchical trees — verifier flattens and matches against all symbol names at any nesting level
- When ambiguity exists (e.g., two classes named `Config`), the `file_paths` field in the same section narrows scope
- Match against all symbol names without filtering by `SymbolKind` — excluding `Variable` kind would miss module-level variables like `TABLE_MODEL_MAP`

### Generate-side: writer agents emit manifest entries
- After writing each section, each writer agent lists every code symbol and file path it referenced
- Emits via `add-manifest-entry.py --input /tmp/manifest-entry-{audience}-NNN.json --manifest /tmp/manifest-{audience}.json`
- Temp input files namespaced by audience to avoid collisions between parallel writer agents
- Input JSON format: `{"document": "ARCHITECTURE", "section": "system-overview", "symbols": [...], "file_paths": [...]}`
- Required fields: `document` (bare name, no `.md`), `section` (slug). At least one of `symbols`/`file_paths` must be non-empty
- Upsert key is `(document, section)` — both required to uniquely identify a manifest entry
- Same atomic JSON I/O pattern as `add-verify-finding.py`

### Manifest bootstrapping
- Generate command creates `.mg/docs/reference-manifests/` directory on first run (not install.sh scaffolding)
- Generate orchestrator does `mkdir -p` before spawning writers — writers don't handle directory creation
- In initial mode: clear all `.json` files in `reference-manifests/` before generation (clean slate)
- In update mode: preserve existing manifests, upsert only regenerated sections
- No migration path needed — old docs (pre-Phase 14) are deleted, not migrated

### Generate-side: manifest merge
- After all writer agents complete, generate orchestrator merges each `/tmp/manifest-{audience}.json` into `.mg/docs/reference-manifests/{audience}.json`
- Merge logic: load persisted manifest, overlay entries from temp file (replace matching `(document, section)` keys, preserve non-matching ones), save
- In initial mode: persisted manifest is empty (cleared above), merge equals copy
- In update mode: preserves entries for sections/audiences that were not regenerated

### Stale section cleanup
- Each writer agent emits one metadata entry with `"section": "_written_sections"`, `"symbols": []`, `"file_paths": []`, plus `"sections_written": [list of section slugs]`
- During merge, generate orchestrator reads this metadata, compares against existing manifest entries for that audience+document, removes entries whose section slug is absent from `sections_written`
- Metadata entry itself is stripped before saving
- Handles sections dropped during regeneration without fragile markdown heading parsing

### Verify-side: reference integrity check
- Check 1 (Reference Integrity) becomes manifest-based:
  1. Read all manifests from `.mg/docs/reference-manifests/`
  2. For each `file_paths` entry: `os.path.isfile()` or `os.path.isdir()`
  3. For each manifest section, use the section's `file_paths` to verify its `symbols` via LSP `documentSymbol`
  4. Broken entries recorded as findings — no triage needed, no sampling

### LSP symbol verification
- Use `documentSymbol` (not `workspaceSymbol`) — verifies symbols exist in the *specific files* the section references
- For each manifest section, iterate its `file_paths` that are files (not directories)
- Call LSP `documentSymbol` on each file (line 1, char 1) to get all symbols defined in that file
- Check whether each symbol in the section's `symbols` list appears in collected `documentSymbol` results
- If a symbol not found in any of the section's `file_paths`: broken finding
- Cache `documentSymbol` results per unique file path — call once and reuse for all sections referencing that file
- Task subagents have access to all tools including LSP (parent's `allowed-tools` constrains only the orchestrator)

### LSP-only verification (no Grep fallback)
- LSP is required — no Grep-based fallback for symbol verification
- If `documentSymbol` returns error or empty result for a specific file, skip symbol verification for that file
- Record an info-severity finding: "Unverifiable file: {path} — LSP returned no symbols, symbol verification skipped for this file"
- This means: false negatives possible for files in unsupported languages, but never false positives
- Simplifies implementation — no language-specific regex patterns, single verification path

### Update mode behavior
- Upsert, not full rewrite — in update mode, generate orchestrator skips audiences with no approved sections, those writers never run
- Full manifest rewrite would erase entries for non-regenerated audiences/sections, causing false breakage in verify
- `add-manifest-entry.py` replaces entries for regenerated sections and preserves entries for skipped sections

### What this replaces
- `check-references.py` extracting refs from markdown → writer agents emit refs at write time
- Regex-based symbol detection (lossy) → manifest captures exact symbol names
- Regex-based symbol index (false positives) → LSP `documentSymbol` per file (semantically correct)
- Agent sampling 10-15 symbols (non-deterministic) → every symbol checked (deterministic)
- Agent triaging 176 noisy file paths → only real references in manifest

### Retiring check-references.py
- Delete `auto-doc/scripts/check-references.py` and `tests/test_check_references.py`
- Remove from verify pipeline: `auto-doc-verify.md` Step 2 (`check-references.py` invocation)
- Remove `verify_refs_broken_path` and `verify_refs_symbols_path` inputs from verifier agent
- Remove verify-refs artifact creation from verify command

### Verify report presentation
- Broken references grouped by document+section in the verify report (e.g., "ARCHITECTURE.md > system-overview: 2 broken symbols, 1 missing file")
- Distinguish between broken file paths ("Missing file: src/old_module.py") and broken symbols ("Undefined symbol: OldClass (checked in src/api.py, src/models.py)")
- All broken manifest references get high severity — factually incorrect content referencing nonexistent code
- Unverifiable files (LSP returned no symbols) get info severity — not actionable, just informational

### Out of scope
- Manifest for shared docs (OVERVIEW.md, GLOSSARY.md) — not generated by audience-specific writer agents
- Known regression: shared docs will have zero reference verification after this phase
- Accepted because shared docs contain few direct code references (OVERVIEW.md is high-level prose, GLOSSARY.md defines terms)
- If verify results show missed breakage in shared docs, follow-up adds manifest emission to generate orchestrator and glossary writer

### Claude's Discretion
- Internal structure of `add-manifest-entry.py` (argument parsing, validation logic)
- Test organization and fixture design for the new script
- Exact error messages and logging in the manifest merge step
- How to structure the verifier agent rewrite (incremental refactor vs full rewrite of Check 1)
- Whether to batch LSP calls or make them individually per file

</decisions>

<specifics>
## Specific Ideas

- The `docs-meta` HTML comments already capture source files per section at write time — the manifest extends this pattern to symbols and makes it machine-readable
- Manifest's `file_paths` is a superset of `docs-meta` `sources` — `docs-meta` tracks source files for staleness, manifest serves reference verification only
- `add-manifest-entry.py` follows the same atomic JSON I/O pattern as `add-verify-finding.py` (~120 lines + ~200 lines tests)
- Writer agent changes are an extension of the existing per-section loop where writers already emit `docs-meta` comments with source file lists

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `add-verify-finding.py`: atomic JSON I/O pattern to replicate for `add-manifest-entry.py`
- `docs-meta` HTML comment pattern: already captures source files per section — manifest extends this
- Writer agent per-section loop: already emits `docs-meta`, manifest emission goes in the same loop

### Established Patterns
- Atomic JSON I/O via `os.replace` and temp files (used throughout the pipeline)
- Per-audience parallel execution: writers already run concurrently, manifest files are namespaced to avoid collisions
- Upsert pattern for incremental updates (update mode preserves non-regenerated entries)

### Integration Points
- 4 audience-specific writer agents: emit manifest entries per section
- `auto-doc/commands/auto-doc-generate.md`: orchestrate manifest collection and merge (~50-80 lines)
- `auto-doc/agents/verifier.md`: rewrite Check 1 for manifest + LSP
- `auto-doc/commands/auto-doc-verify.md`: remove Step 2 (`check-references.py`), add manifest loading
- `auto-doc/references/schema.md`: document manifest format

</code_context>

<deferred>
## Deferred Ideas

- Manifest for shared docs (OVERVIEW.md, GLOSSARY.md) — add if verify results show coverage gaps
- Phase 16 (incremental scan) depends on manifests existing — manifests are the index that makes incremental scoping possible

</deferred>

---

*Phase: 14-auto-doc-reference-manifest*
*Context gathered: 2026-03-22 via context import + interactive discussion*
