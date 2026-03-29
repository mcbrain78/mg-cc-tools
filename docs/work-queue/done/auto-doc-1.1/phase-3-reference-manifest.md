# Phase 3: Reference Manifest — Write-Time Capture, LSP-Based Verification

**Goal:** Capture all symbol and file path references at generate time (via manifest), then verify every entry deterministically at verify time (via LSP and filesystem checks). Replaces the unreliable extraction-and-sampling approach.

**Depends on:** Phase 1 (rename + cleanup must complete — files use `auto-doc/` paths)

---

## Problem Statement

The verify pipeline's reference checking is unreliable and expensive because it reverse-engineers what the docs reference by parsing markdown at verify time. Three failures observed in road-runner testing:

### 1. Symbol extraction is lossy

`check-references.py` only extracts symbols from fenced code blocks using a regex that requires uppercase start (`[A-Z]`). Snake_case symbols in inline backticks (`route_model`, `store_finra_short_interest`) are invisible. These were real broken references that verify missed entirely.

### 2. File path extraction is noisy

364 "broken" file paths extracted, 176 unique after dedup. After agent triage: zero genuine issues. All were noise — Prefect deployment paths, shell commands, example values, database URLs.

### 3. Symbol verification is non-deterministic

The agent spot-checks 10-15 symbols from a pick list. Different runs pick different samples, producing different results. Same codebase, different conclusions.

**Root cause:** All three problems stem from trying to reconstruct reference information at verify time that was known at generate time and discarded.

---

## Solution: Reference Manifest

Capture references at write time (generate), verify deterministically at check time (verify).

### Architecture

```
Generate: writer agents emit docs + reference manifest per section
    |
    v
Manifest: machine-readable record of every symbol and file path referenced
    |
    v
Verify: read manifest, check each entry via LSP/filesystem
    |
    v
Report: every reference checked, none sampled, no parsing
```

### Reference Manifest Format

One manifest file per audience, written alongside the docs. Stored in `.mg/docs/reference-manifests/`.

```json
{
  "audience": "developers",
  "generated": "2026-03-17T14:30:00Z",
  "documents": {
    "ARCHITECTURE": {
      "system-overview": {
        "symbols": ["RoadRunnerBase", "route_model", "fetch_quarterly"],
        "file_paths": ["src/db/models.py", "src/llm/model_routing.py", "config/field-mapping.yaml"]
      },
      "data-model": {
        "symbols": ["SharedBase", "FinanceMetrics", "TABLE_MODEL_MAP"],
        "file_paths": ["src/db/models.py", "src/schemas/golden/"]
      }
    }
  }
}
```

**Field definitions:**
- `symbols` — code identifiers the section references (function names, class names, constants). Exactly as they appear in source code.
- `file_paths` — all files and directories the section references (source, config, scripts, data). Relative to project root. Verified via `os.path.isfile()` / `os.path.isdir()`.

### Generate-Side Changes

Writer agents already receive `source_material_index` entries per section, including the `source_files` list for each section. Writers read these source files and generate content referencing specific identifiers. After writing each section, the agent self-reports which symbols and file paths it referenced:

1. After writing each section, the agent lists every code symbol it referenced (class names, function names, constants, variables) and every file path it mentioned, then emits them via a new script (`add-manifest-entry.py --input /tmp/manifest-entry-{audience}-NNN.json --manifest /tmp/manifest-{audience}.json`). Temp input files are namespaced by audience to avoid collisions between parallel writer agents. This extends the existing per-section loop where writers already emit `docs-meta` comments with source file lists.
2. The script validates the entry and appends atomically (same pattern as `add-verify-finding.py`). Input JSON format:
   ```json
   {"document": "ARCHITECTURE", "section": "system-overview", "symbols": ["RoadRunnerBase", "route_model"], "file_paths": ["src/db/models.py"]}
   ```
   Required fields: `document` (bare name, no `.md`), `section` (slug). At least one of `symbols`/`file_paths` must be non-empty. The upsert key is `(document, section)` — both are required to uniquely identify a manifest entry.
3. After all writer agents complete, the generate orchestrator merges each `/tmp/manifest-{audience}.json` into `.mg/docs/reference-manifests/{audience}.json` (creating the directory if needed). Merge logic: load the persisted manifest, overlay entries from the temp file (replacing matching `(document, section)` keys, preserving non-matching ones), then save. In initial mode the persisted manifest is empty so merge equals copy; in update mode it preserves entries for sections/audiences that were not regenerated.

**Manifest accuracy:** Writer agents are LLMs and may omit symbols or include ones they considered but did not actually use. The manifest catches the important failure class — references to code that no longer exists — because LSP verification is independent of what the writer reports. A missed manifest entry means that reference goes unverified, which is no worse than today's sampling approach where most references are never checked at all.

### Verify-Side Changes

Check 1 (Reference Integrity) becomes:

1. Read all manifests from `.mg/docs/reference-manifests/`
2. For each `file_paths` entry: `os.path.isfile()` or `os.path.isdir()`
3. For each manifest section, use the section's `file_paths` to verify its `symbols` via LSP `documentSymbol` (see below)
4. Broken entries recorded as findings — no triage needed, no sampling

### LSP Integration

The LSP tool requires `filePath` + `line` + `character` for all operations. While `workspaceSymbol` exists for workspace-wide search, we use `documentSymbol` instead because it verifies that a symbol exists in the *specific files* the section references — a symbol defined elsewhere in the codebase but not in the referenced files indicates a wrong reference, which `workspaceSymbol` would miss. Symbol verification uses `documentSymbol` combined with the manifest's own `file_paths`:

1. For each manifest section, iterate its `file_paths` that are files (not directories)
2. Call LSP `documentSymbol` on each file (any line/character, e.g., line 1, char 1) to get all symbols defined in that file
3. Check whether each symbol in the section's `symbols` list appears in the collected `documentSymbol` results
4. If a symbol is not found in any of the section's `file_paths`: broken finding
5. Collect `documentSymbol` results for each unique file path once and reuse for all sections referencing that file — if `src/db/models.py` appears in 3 sections, call `documentSymbol` once and check all 3 sections' symbols against the same result
6. Natural batching — symbols are already grouped by section, and each section lists the files they should appear in

This approach works because the manifest pairs symbols with the files they come from (writers read these files and know which symbols they referenced). LSP `documentSymbol` returns all symbols in a file — classes, functions, constants, methods, variables — resolving re-exports, decorators, and dynamic definitions that regex misses. Match against all symbol names without filtering by `SymbolKind`: file-scoping keeps result sets small (tens of symbols per file), and excluding `Variable` kind would miss module-level variables like `TABLE_MODEL_MAP` that Python LSP servers do not classify as `Constant` unless annotated with `Final`.

Task subagents (spawned via the Task tool) are general-purpose Claude Code agents with access to all tools including LSP. The parent command's `allowed-tools` frontmatter constrains only the orchestrator, not spawned subagents — same pattern used by codebase-health scanner agents.

**Fallback when LSP is unavailable:**
If the first `documentSymbol` call returns an error or empty result on a file known to contain symbols, the verifier switches to Grep-based verification for all remaining symbols. For each manifest symbol, Grep for definition patterns in the section's `file_paths`: Python (`def {symbol}`, `class {symbol}`, `{symbol} =`), JavaScript/TypeScript (`function {symbol}`, `const {symbol}`, `let {symbol}`, `export.*{symbol}`, `interface {symbol}`, `type {symbol}`, `enum {symbol}`). A match on any pattern confirms the symbol exists. No match produces a finding. The verify report flags "LSP unavailable — symbol verification used Grep fallback, results may include false positives for re-exports and third-party symbols."

### What This Replaces

| Current | Proposed |
|---------|----------|
| `check-references.py` extracts refs from markdown | Writer agents emit refs at write time |
| Regex-based symbol detection (lossy) | Manifest captures exact symbol names |
| Regex-based symbol index (false positives) | LSP documentSymbol per file (semantically correct) |
| Agent samples 10-15 symbols (non-deterministic) | Every symbol checked (deterministic) |
| Agent triages 176 noisy file paths | Only real references in manifest |
| 13K tokens of broken refs to paginate | Small, precise manifest per audience |

### Precedent

The `docs-meta` HTML comments already capture source files per section at write time:
```html
<!-- docs-meta: last-updated: 2026-03-16, sources: src/db/models.py, src/llm/model_routing.py -->
```

The reference manifest extends this pattern to symbols and makes it machine-readable. The manifest's `file_paths` is a superset of `docs-meta` `sources` — `docs-meta` tracks the source files that drive staleness detection (code files the section describes), while `file_paths` additionally includes config files, data directories, and other referenced paths. `docs-meta` remains the staleness signal; the manifest serves reference verification only.

---

## Scope

| Action | Files |
|--------|-------|
| Create | `auto-doc/scripts/add-manifest-entry.py` + tests (~120 + 200 lines) |
| Edit | 4 audience-specific writer agents — emit manifest entries per section |
| Edit | `auto-doc/commands/auto-doc-generate.md` — orchestrate manifest collection (~50-80 lines) |
| Edit | `auto-doc/agents/verifier.md` — rewrite Check 1 for manifest + LSP, remove `verify_refs_broken_path` and `verify_refs_symbols_path` inputs (~50-100 lines) |
| Edit | `auto-doc/commands/auto-doc-verify.md` — remove Step 2 (`check-references.py` invocation), add manifest loading, remove verify-refs artifact creation (~40-60 lines) |
| Edit | `auto-doc/references/schema.md` — document manifest format (~30-50 lines) |
| Delete | `auto-doc/scripts/check-references.py` + `tests/test_check_references.py` — retired, replaced by manifest |

### Out of Scope
- Manifest for shared docs (OVERVIEW.md, GLOSSARY.md) — these are not generated by audience-specific writer agents, so no manifest entries are emitted. This is a known regression: `check-references.py` currently extracts references from all docs including shared docs. After this phase, OVERVIEW.md and GLOSSARY.md will have zero reference verification. This is accepted because shared docs contain few direct code references (OVERVIEW.md is high-level prose, GLOSSARY.md defines terms). If verify results show missed breakage in shared docs, a follow-up adds manifest emission to the generate orchestrator (for OVERVIEW.md) and glossary writer (for GLOSSARY.md).

---

## Decisions

1. **Manifest granularity:** Per-audience. Each writer agent runs independently and writes to its own manifest file, so per-audience is the natural unit — no coordination or locking needed between concurrent writers. A single file would require all writers to serialize access. The tradeoff: shared docs (OVERVIEW.md, GLOSSARY.md) span audiences and cannot be captured in a single audience manifest. This is explicitly out of scope (see Out of Scope above) and will be addressed if verify results show coverage gaps.
2. **Symbol format:** Always unqualified identifiers (`RoadRunnerBase`, `fetch_quarterly`), never dotted paths (`FMPClient.fetch_quarterly`). LSP `documentSymbol` returns a hierarchical tree — a method appears as `fetch_quarterly` nested under `FMPClient`, not as `FMPClient.fetch_quarterly`. The verifier flattens the `documentSymbol` tree and matches against all symbol names at any nesting level. When ambiguity exists (e.g., two classes named `Config`), the `file_paths` field in the same section narrows scope.
3. **Update mode:** Upsert, not full rewrite. In update mode, the generate orchestrator skips audiences with no approved sections — those writers never run. A full manifest rewrite would erase manifest entries for non-regenerated audiences/sections, causing verify to report false breakage. The `add-manifest-entry.py` script operates in upsert mode: it replaces entries for sections the writer regenerated and preserves entries for sections it skipped. Same atomic JSON I/O pattern as `add-verify-finding.py`, minimal added complexity. **Stale section cleanup:** each writer agent emits one additional manifest entry with `"section": "_written_sections"` and `"symbols": []`, `"file_paths": []`, plus a new field `"sections_written": ["system-overview", "data-model", ...]` listing every section slug it generated. During the merge step, the generate orchestrator reads this metadata entry, compares against existing manifest entries for that audience+document, and removes entries whose section slug is absent from `sections_written`. The metadata entry itself is stripped before saving. This handles sections dropped during regeneration without fragile markdown heading parsing.
