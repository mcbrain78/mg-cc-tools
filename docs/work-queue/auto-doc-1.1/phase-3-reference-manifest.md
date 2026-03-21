# Phase 3: Reference Manifest — Write-Time Capture, LSP-Based Verification

**Goal:** Capture all symbol and file path references at generate time (via manifest), then verify every entry deterministically at verify time (via LSP and filesystem checks). Replaces the unreliable extraction-and-sampling approach.

**Depends on:** Phase 1 (rename + cleanup must complete — `check-references.py` retired, files use `auto-doc/` paths)

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
    "ARCHITECTURE.md": {
      "system-architecture": {
        "symbols": ["RoadRunnerBase", "route_model", "FMPClient.fetch_quarterly"],
        "file_paths": ["src/db/models.py", "src/llm/model_routing.py"],
        "external_refs": ["config/field-mapping.yaml"]
      },
      "data-model": {
        "symbols": ["SharedBase", "FinanceMetrics", "TABLE_MODEL_MAP"],
        "file_paths": ["src/db/models.py", "src/schemas/golden/"],
        "external_refs": []
      }
    }
  }
}
```

**Field definitions:**
- `symbols` — code identifiers the section references (function names, class names, constants). Exactly as they appear in source code.
- `file_paths` — source files the section describes or references. Relative to project root.
- `external_refs` — config files, scripts, data directories referenced but not source code.

### Generate-Side Changes

Writer agents already receive `source_material_index` entries per section. When writing each section, the agent records which symbols and file paths it actually used:

1. After writing each section, the agent appends to a temp manifest file via a new script (`add-manifest-entry.py --input /tmp/manifest-entry-NNN.json --manifest /tmp/manifest-developers.json`)
2. The script validates the entry (document name, section slug, at least one of symbols/file_paths/external_refs non-empty) and appends atomically (same pattern as `add-verify-finding.py`)
3. After all writer agents complete, the generate orchestrator copies each `/tmp/manifest-{audience}.json` to `.mg/docs/reference-manifests/{audience}.json` (creating the directory if needed)

### Verify-Side Changes

Check 1 (Reference Integrity) becomes:

1. Read all manifests from `.mg/docs/reference-manifests/`
2. For each `file_paths` and `external_refs` entry: `os.path.isfile()` or `os.path.isdir()`
3. For each `symbols` entry: LSP `go-to-definition` (or `textDocument/definition` request)
4. Broken entries recorded as findings — no triage needed, no sampling

### LSP Integration

LSP is already installed in the project. Symbol verification via LSP:

1. For each symbol, construct a `textDocument/definition` request
2. If LSP returns a location: symbol exists (valid)
3. If LSP returns empty/null: symbol doesn't exist (broken finding)
4. Batch symbols by file to minimize LSP round-trips

LSP resolves re-exports, decorators, dynamic definitions, third-party imports — all the cases where regex indexing produces false positives.

**Fallback when LSP is unavailable:**
If no LSP server responds, the verifier agent falls back to Grep-based symbol checking with a warning in the report. Less accurate (false positives for re-exports, third-party symbols) but still better than sampling. The verify report flags "LSP unavailable — symbol verification used Grep fallback, results may include false positives."

### What This Replaces

| Current | Proposed |
|---------|----------|
| `check-references.py` extracts refs from markdown | Writer agents emit refs at write time |
| Regex-based symbol detection (lossy) | Manifest captures exact symbol names |
| Regex-based symbol index (false positives) | LSP go-to-definition (semantically correct) |
| Agent samples 10-15 symbols (non-deterministic) | Every symbol checked (deterministic) |
| Agent triages 176 noisy file paths | Only real references in manifest |
| 13K tokens of broken refs to paginate | Small, precise manifest per audience |

### Precedent

The `docs-meta` HTML comments already capture source files per section at write time:
```html
<!-- docs-meta: last-updated: 2026-03-16, sources: src/db/models.py, src/llm/model_routing.py -->
```

The reference manifest extends this pattern to symbols and makes it machine-readable.

---

## Scope

| Action | Files |
|--------|-------|
| Create | `auto-doc/scripts/add-manifest-entry.py` + tests (~120 + 200 lines) |
| Edit | 4 writer agents — emit manifest entries per section |
| Edit | `auto-doc/commands/auto-doc-generate.md` — orchestrate manifest collection (~50-80 lines) |
| Edit | `auto-doc/agents/verifier.md` — rewrite Check 1 for manifest + LSP (~50-100 lines) |
| Edit | `auto-doc/commands/auto-doc-verify.md` — pass manifest paths (~15-20 lines) |
| Edit | `auto-doc/references/schema.md` — document manifest format (~30-50 lines) |

### Out of Scope
- Manifest for shared docs (OVERVIEW.md, GLOSSARY.md) — aggregate across audiences. Follow-up if needed.
- Incremental manifest updates in generate update mode — first version writes full manifest every time.

---

## Decisions

1. **Manifest granularity:** Per-audience (as shown) or single file? Default: per-audience, aligns with writer agents.
2. **Symbol format:** Just the identifier (`RoadRunnerBase`), not the module path. Writer agents know symbol names but not reliably the full module path. LSP resolves bare identifiers across the workspace. When ambiguity exists (e.g., two classes named `Config`), the `file_paths` field in the same manifest section provides context for LSP to narrow scope.
3. **Update mode:** Full manifest rewrite or patch updated sections only? Default: full rewrite, optimize later.
