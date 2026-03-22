# Phase 14: Auto Doc Reference Manifest - Research

**Researched:** 2026-03-22
**Domain:** Reference verification infrastructure (manifest-based symbol and file path tracking)
**Confidence:** HIGH

## Summary

Phase 14 replaces the lossy, regex-based `check-references.py` extraction approach with a structured manifest system. Writer agents emit exact code symbols and file paths at generation time, producing per-audience manifest files. The verifier then reads these manifests and checks every entry deterministically -- file paths via `os.path.isfile()`/`os.path.isdir()`, symbols via LSP `documentSymbol`. This eliminates false positives from regex extraction, false negatives from sampling, and noise from agent triage.

The implementation touches four layers: a new Python script (`add-manifest-entry.py`), modifications to the generate orchestrator command, modifications to all 4 writer agent definitions, and a rewrite of the verifier agent's Check 1. The old `check-references.py` and its tests are deleted, along with the verify command's Step 2 that invoked it.

**Primary recommendation:** Build `add-manifest-entry.py` first (following the `add-verify-finding.py` pattern exactly), then update generate/writer/verify commands in dependency order. The Python script is the only testable unit; all other changes are LLM prompt modifications validated at integration time.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- One manifest file per audience, stored in `.mg/docs/reference-manifests/`
- Structure: `{"audience": "...", "generated": "ISO timestamp", "documents": {DOCUMENT: {section: {symbols: [...], file_paths: [...]}}}}`
- Symbols are always unqualified identifiers (`RoadRunnerBase`, `fetch_quarterly`), never dotted paths
- LSP `documentSymbol` returns hierarchical trees -- verifier flattens and matches against all symbol names at any nesting level
- Match against all symbol names without filtering by `SymbolKind`
- When ambiguity exists, the `file_paths` field in the same section narrows scope
- Writer agents emit manifest entries after writing each section via `add-manifest-entry.py`
- Input JSON format: `{"document": "ARCHITECTURE", "section": "system-overview", "symbols": [...], "file_paths": [...]}`
- Upsert key is `(document, section)` -- both required to uniquely identify a manifest entry
- Same atomic JSON I/O pattern as `add-verify-finding.py`
- Temp input files namespaced by audience to avoid collisions
- Generate orchestrator does `mkdir -p` before spawning writers
- In initial mode: clear all `.json` files in `reference-manifests/` before generation
- In update mode: preserve existing manifests, upsert only regenerated sections
- Stale section cleanup via `_written_sections` metadata entry
- Verify reads all manifests, checks file_paths via filesystem, symbols via LSP `documentSymbol`
- If LSP returns error or empty for a file, skip symbol verification, record info-severity finding
- LSP-only verification -- no Grep fallback
- Delete `check-references.py`, its tests, its verify-pipeline invocation, and verifier agent inputs
- Broken references grouped by document+section in verify report, high severity
- Unverifiable files get info severity

### Claude's Discretion
- Internal structure of `add-manifest-entry.py` (argument parsing, validation logic)
- Test organization and fixture design for the new script
- Exact error messages and logging in the manifest merge step
- How to structure the verifier agent rewrite (incremental refactor vs full rewrite of Check 1)
- Whether to batch LSP calls or make them individually per file

### Deferred Ideas (OUT OF SCOPE)
- Manifest for shared docs (OVERVIEW.md, GLOSSARY.md) -- add if verify results show coverage gaps
- Phase 16 (incremental scan) depends on manifests existing -- manifests are the index that makes incremental scoping possible
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MAN-01 | Per-audience reference manifest files in `.mg/docs/reference-manifests/` with symbols and file paths by document/section | Manifest format locked in CONTEXT.md; `add-manifest-entry.py` creates/upserts entries; generate orchestrator merges temp manifests into persisted location |
| MAN-02 | Writer agents emit manifest entries after each section via `add-manifest-entry.py` | Writer agent definitions get new step in per-section loop after docs-meta emission; follows same pattern as term proposal emission |
| MAN-03 | Symbols stored as unqualified identifiers, verified against all LSP `documentSymbol` results without `SymbolKind` filtering | Verifier agent flattens hierarchical `documentSymbol` trees and matches names at any nesting level |
| MAN-04 | Generate orchestrator merges temp manifests into persisted manifests (upsert by document+section) | New merge logic in generate command between Stage 2 completion and Stage 3 (glossary reconciliation) |
| MAN-05 | Initial mode clears manifests; update mode preserves and upserts | Generate command Step 3 workspace prep clears `reference-manifests/*.json` in initial mode only |
| MAN-06 | Stale section cleanup via `_written_sections` metadata entry | Writer agents emit metadata entry; generate orchestrator reads it during merge to prune absent sections |
| MAN-07 | Verify reads manifests, checks file_paths via filesystem, symbols via LSP `documentSymbol` | Verifier agent Check 1 rewritten to iterate manifest entries instead of reading pre-extracted reference files |
| MAN-08 | LSP error/empty results skip symbol verification with info-severity finding | Verifier agent handles graceful degradation per file |
| MAN-09 | Broken references grouped by document+section, distinguishing missing files from undefined symbols, high severity | Verifier agent report generation restructured around manifest grouping |
| MAN-10 | Delete `check-references.py`, its tests, verify-pipeline invocation, verifier agent inputs | Remove script, test file, verify command Step 2, and `verify_refs_*` parameters from verifier agent |
| MAN-11 | LSP-only verification path -- no Grep fallback | Verifier agent uses only `documentSymbol`, skips files where LSP returns no results |
| MAN-12 | Manifest covers audience-specific docs only -- shared docs have no manifest | Writer agents only run for audience-specific docs; OVERVIEW.md and GLOSSARY.md excluded |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | `add-manifest-entry.py` script | Project convention: stdlib-only scripts, no pip dependencies |
| lib/json_io.py | existing | Atomic JSON load/save | Shared by all auto-doc scripts; uses `os.replace()` for crash safety |
| argparse | stdlib | CLI argument parsing | Used by all existing auto-doc scripts |
| LSP (Claude Code built-in) | N/A | `documentSymbol` for symbol verification | Available to all Task subagents; semantically correct symbol resolution |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os | stdlib | `os.path.isfile()`, `os.path.isdir()` for file path verification | Manifest file_paths verification in verifier agent |
| json | stdlib | JSON parsing/serialization | Manifest format is JSON |
| pytest | dev dependency | Testing `add-manifest-entry.py` | Already in project dev dependencies |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-audience manifest files | Single monolithic manifest | Per-audience avoids locking/coordination between parallel writers -- locked decision |
| LSP `documentSymbol` | Grep-based fallback | Grep has false positives; LSP is semantically correct -- locked decision |
| `_written_sections` metadata | Parse markdown headings | Heading parsing is fragile across template changes -- locked decision |

## Architecture Patterns

### Manifest File Layout
```
<project-root>/
├── .mg/
│   └── docs/
│       ├── reference-manifests/       # NEW -- Phase 14 creates this
│       │   ├── developers.json
│       │   ├── end-users.json
│       │   ├── agents.json
│       │   └── devops.json
│       ├── docs-scan.json
│       ├── docs-verify-findings.json
│       └── ...
```

### Pattern 1: Atomic JSON Upsert (add-manifest-entry.py)
**What:** Validates input, loads existing manifest, upserts entry by `(document, section)` key, saves atomically.
**When to use:** Called by each writer agent after writing each section.
**Example:**
```python
# Source: Adapted from auto-doc/scripts/add-verify-finding.py (existing pattern)
# Input: {"document": "ARCHITECTURE", "section": "system-overview", "symbols": [...], "file_paths": [...]}
# Manifest structure:
# {
#   "audience": "developers",
#   "generated": "2026-03-22T14:30:00Z",
#   "documents": {
#     "ARCHITECTURE": {
#       "system-overview": {
#         "symbols": ["RoadRunnerBase", "fetch_quarterly"],
#         "file_paths": ["src/app.ts", "src/routes/"]
#       }
#     }
#   }
# }

def upsert_entry(manifest, document, section, symbols, file_paths):
    """Upsert a manifest entry by (document, section) key."""
    if "documents" not in manifest:
        manifest["documents"] = {}
    if document not in manifest["documents"]:
        manifest["documents"][document] = {}
    manifest["documents"][document][section] = {
        "symbols": symbols,
        "file_paths": file_paths,
    }
```

### Pattern 2: Writer Agent Manifest Emission
**What:** After writing each section, writer agent lists symbols and file paths it referenced, writes to temp file, calls `add-manifest-entry.py`.
**When to use:** In the per-section loop of every writer agent, after docs-meta comment emission.
**Example:**
```
# In writer agent per-section loop (after writing section content):
# 1. List code symbols referenced in this section (unqualified names only)
# 2. List file paths referenced in this section (relative to project root)
# 3. Write temp input file: /tmp/manifest-entry-{audience}-NNN.json
# 4. Call: python3 {SCRIPTS_DIR}/add-manifest-entry.py \
#      --input /tmp/manifest-entry-{audience}-NNN.json \
#      --manifest /tmp/manifest-{audience}.json
```

### Pattern 3: Generate Orchestrator Manifest Merge
**What:** After all writers complete, merge temp manifests into persisted location.
**When to use:** New step between Stage 2 (writers complete) and Stage 3 (glossary reconciliation).
**Example:**
```
# Generate orchestrator (new step after Stage 2):
# For each audience that ran:
#   1. Read /tmp/manifest-{audience}.json
#   2. Read _written_sections metadata entry, extract sections_written list
#   3. Read .mg/docs/reference-manifests/{audience}.json (existing, may not exist)
#   4. Overlay temp entries onto existing manifest (upsert by document+section)
#   5. Prune sections absent from sections_written list (stale cleanup)
#   6. Strip _written_sections metadata entry
#   7. Write merged manifest to .mg/docs/reference-manifests/{audience}.json
```

### Pattern 4: Verify Manifest-Based Reference Check
**What:** Read all manifests, check every file_path via filesystem, check every symbol via LSP.
**When to use:** Replaces old Check 1 in verifier agent.
**Example:**
```
# Verifier agent Check 1 (rewritten):
# 1. Read all .json files from .mg/docs/reference-manifests/
# 2. Build file_to_symbols cache (unique file paths across all sections)
# 3. For each unique file path:
#    - Call LSP documentSymbol on the file
#    - Cache the result (flattened list of all symbol names)
# 4. For each manifest -> document -> section:
#    a. Check file_paths: os.path.isfile() or os.path.isdir()
#    b. Check symbols: look up in cached documentSymbol results for section's file_paths
#    c. Record findings via add-verify-finding.py
```

### Anti-Patterns to Avoid
- **Extracting references from generated markdown:** The old approach (`check-references.py`) parsed markdown with regex, producing false positives (noise paths, command fragments) and false negatives (symbols not matching regex patterns). The manifest captures exact references at write time.
- **Grep-based symbol verification:** Regex grep for symbol names has false positives (string matches, comments) and misses re-exports. LSP `documentSymbol` is semantically correct.
- **Monolithic manifest file:** A single manifest for all audiences would require coordination between parallel writers. Per-audience files avoid this entirely.
- **Filtering by SymbolKind:** Excluding `Variable` kind would miss module-level constants like `TABLE_MODEL_MAP`. Match all symbol names regardless of kind.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic JSON I/O | Custom file locking | `lib/json_io.py` (`save_json` with `os.replace`) | Already battle-tested across all auto-doc scripts |
| Symbol verification | Regex-based search across files | LSP `documentSymbol` | Semantically correct, handles re-exports, decorators, cross-module imports |
| File path verification | Custom path resolution logic | `os.path.isfile()` / `os.path.isdir()` | Standard library, handles symlinks and edge cases |
| Input validation | Inline checks in agent prompts | Python script with structured validation | Deterministic, testable, provides .rejected file debugging |

**Key insight:** The manifest system moves reference tracking from "extraction from output" to "emission at write time." This is fundamentally more reliable because the writer agent knows exactly what it referenced -- no lossy parsing step.

## Common Pitfalls

### Pitfall 1: Temp File Namespace Collisions
**What goes wrong:** Two writer agents running in parallel both write to `/tmp/manifest-entry-001.json`, overwriting each other.
**Why it happens:** Parallel Task execution with shared temp directory.
**How to avoid:** Namespace temp files by audience: `/tmp/manifest-entry-{audience}-NNN.json`. This is specified in the locked decisions.
**Warning signs:** Manifest entries from one audience appearing in another audience's manifest.

### Pitfall 2: Manifest Not Cleared in Initial Mode
**What goes wrong:** Stale entries from a previous generation persist in the manifest, causing the verifier to check references that no longer exist in docs.
**Why it happens:** Generate command forgets to clear `reference-manifests/*.json` before initial generation.
**How to avoid:** Generate command Step 3 (workspace prep) must include `rm -f {project_root}/.mg/docs/reference-manifests/*.json` when mode is `initial`.
**Warning signs:** Verify reports broken references for sections that were regenerated cleanly.

### Pitfall 3: Update Mode Erases Non-Regenerated Entries
**What goes wrong:** In update mode, only 2 of 4 audiences are regenerated. The merge step replaces the entire manifest for all audiences, erasing entries for the 2 skipped audiences.
**Why it happens:** Full rewrite instead of upsert in merge logic.
**How to avoid:** Only merge temp manifests for audiences that actually ran. Skip audiences with no approved sections entirely.
**Warning signs:** Verify reports massive breakage after a targeted update that only touched one audience.

### Pitfall 4: _written_sections Metadata Leaks Into Persisted Manifest
**What goes wrong:** The `_written_sections` metadata entry (used for stale section cleanup) is not stripped before saving, causing the verifier to try to verify it as a real section.
**Why it happens:** Generate orchestrator forgets to strip metadata after processing.
**How to avoid:** After using `_written_sections` for pruning, delete it from the manifest before saving.
**Warning signs:** Verify errors about a section named `_written_sections` with no symbols or file paths.

### Pitfall 5: LSP documentSymbol Returns Empty for Non-Code Files
**What goes wrong:** A manifest entry references a `.json`, `.yaml`, or `.md` file. LSP returns empty results for these, and the verifier marks all symbols as broken.
**Why it happens:** LSP only provides symbol information for supported languages.
**How to avoid:** Per the locked decision: if LSP returns error or empty, skip symbol verification for that file and record an info-severity finding. Only check symbols against files where LSP returned results.
**Warning signs:** False positive "undefined symbol" findings for symbols defined in non-Python/TS/JS files.

### Pitfall 6: Forgetting to Add Manifest Emission to All 4 Writer Agents
**What goes wrong:** Only 2 of 4 writer agents get the manifest emission step, resulting in incomplete manifests for some audiences.
**Why it happens:** Copy-paste error during implementation.
**How to avoid:** Update all 4 writer agents (end-user, developer, agent, devops) consistently. The glossary writer is excluded (shared doc, out of scope per locked decision).
**Warning signs:** Manifests exist for some audiences but not others.

### Pitfall 7: verify_refs_broken_path and verify_refs_symbols_path Not Removed
**What goes wrong:** After deleting `check-references.py`, the verify command still tries to build `verify_refs_broken_path` and `verify_refs_symbols_path` and pass them to the verifier agent. The agent fails or uses stale data.
**Why it happens:** Incomplete cleanup of the old pipeline.
**How to avoid:** Remove Step 2 from verify command entirely. Remove `verify_refs_broken_path` and `verify_refs_symbols_path` from both the verify command's path construction and the verifier agent's Inputs section.
**Warning signs:** Verifier agent references undefined parameters.

### Pitfall 8: Manifest Directory Not Created Before Writers Run
**What goes wrong:** `add-manifest-entry.py` fails because `.mg/docs/reference-manifests/` does not exist.
**Why it happens:** The directory is created on first run by generate, but the locked decision says generate orchestrator does `mkdir -p` before spawning writers. If this step is missed, writers fail.
**How to avoid:** Generate command Step 3 (workspace prep) must include `mkdir -p .mg/docs/reference-manifests/`. Note: writers write to `/tmp/`, not directly to the persisted directory, so this is actually needed before the merge step, not before writers. But creating it early is safer.
**Warning signs:** `add-manifest-entry.py` errors about missing directory (though it writes to `/tmp/`, so this mainly affects the merge step).

## Code Examples

### add-manifest-entry.py Structure
```python
# Source: Pattern from auto-doc/scripts/add-verify-finding.py
#!/usr/bin/env python3
"""Validate and upsert a manifest entry for reference tracking.

Called by writer agents after writing each section. The agent writes
entry data to a temp file, then invokes this script.

Usage:
    python3 add-manifest-entry.py \
        --input /tmp/manifest-entry-developers-001.json \
        --manifest /tmp/manifest-developers.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

REQUIRED_FIELDS = ["document", "section"]

def validate_entry(entry):
    """Validate input. Returns (True, None) or (False, error)."""
    if not isinstance(entry, dict):
        return False, "Input is not a JSON object"
    for field in REQUIRED_FIELDS:
        if field not in entry:
            return False, f"Missing required field: {field}"
    symbols = entry.get("symbols", [])
    file_paths = entry.get("file_paths", [])
    # Special case: _written_sections metadata entry has neither
    if entry.get("section") != "_written_sections":
        if not symbols and not file_paths:
            return False, "At least one of symbols or file_paths must be non-empty"
    return True, None

def upsert_manifest(manifest, entry):
    """Upsert entry into manifest by (document, section) key."""
    doc = entry["document"]
    section = entry["section"]
    if "documents" not in manifest:
        manifest["documents"] = {}
    if doc not in manifest["documents"]:
        manifest["documents"][doc] = {}
    manifest["documents"][doc][section] = {
        "symbols": entry.get("symbols", []),
        "file_paths": entry.get("file_paths", []),
    }
    # Preserve extra fields for metadata entries
    if "sections_written" in entry:
        manifest["documents"][doc][section]["sections_written"] = entry["sections_written"]
```

### Writer Agent Manifest Emission Step
```markdown
# Added to each writer agent's per-section loop (after docs-meta comment):

After writing each section, emit a manifest entry:
1. List every code symbol you referenced in this section as unqualified identifiers
   (e.g., `RoadRunnerBase`, `fetch_quarterly` -- NOT `FMPClient.fetch_quarterly`)
2. List every file path you referenced, relative to project root
3. Write a temp JSON file:
   ```json
   {"document": "ARCHITECTURE", "section": "system-overview",
    "symbols": ["RoadRunnerBase", "fetch_quarterly"],
    "file_paths": ["src/app.ts", "src/routes/"]}
   ```
   Write to: `/tmp/manifest-entry-{audience}-NNN.json` (increment NNN per section)
4. Call:
   ```bash
   python3 {SCRIPTS_DIR}/add-manifest-entry.py \
     --input /tmp/manifest-entry-{audience}-NNN.json \
     --manifest /tmp/manifest-{audience}.json
   ```
```

### Verifier Agent Check 1 Rewrite (LSP-based)
```markdown
# Replaces old Check 1 in verifier.md:

### Check 1: Reference Integrity (manifest-based)

Read all manifest files from `.mg/docs/reference-manifests/`:

1. For each manifest file (one per audience):
   - Parse the JSON manifest
   - Iterate documents -> sections -> entries

2. For each entry's `file_paths`:
   - Check filesystem: `os.path.isfile(path)` or `os.path.isdir(path)` (resolved relative to project_root)
   - If missing: record HIGH severity finding ("Missing file: {path}")

3. For each entry's `symbols`:
   - Collect the entry's `file_paths` that are files (not directories)
   - For each file, call LSP documentSymbol (use Go to Definition or equivalent)
   - Flatten the hierarchical symbol tree to get all symbol names
   - Cache results per unique file path
   - Check if each symbol appears in the collected results
   - If not found: record HIGH severity finding ("Undefined symbol: {symbol} (checked in {file_list})")
   - If LSP returns error/empty for a file: record INFO severity finding ("Unverifiable file: {path}")
     and skip symbol checks for that file

4. Group findings by document+section in the report.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `check-references.py` extracts refs from markdown via regex | Writer agents emit refs at write time into manifest | Phase 14 | Eliminates false positives from regex extraction |
| Regex-based symbol index (`_symbol_exists_in_project`) | LSP `documentSymbol` per file | Phase 14 | Semantically correct, no false positives from string matches |
| Agent sampling 10-15 symbols (non-deterministic) | Every symbol checked deterministically | Phase 14 | 100% coverage, reproducible results |
| Agent triaging 176 noisy file paths | Only real references in manifest | Phase 14 | Zero noise, no triage needed |

**Deprecated/outdated:**
- `check-references.py`: Deleted entirely -- replaced by manifest system
- `verify-refs-broken.json` and `verify-refs-symbols.json`: No longer produced as verify artifacts
- Verify command Step 2 (check-references.py invocation): Removed
- Verifier agent inputs `verify_refs_broken_path` and `verify_refs_symbols_path`: Removed

## Open Questions

1. **Where exactly does the manifest merge step go in the generate flow?**
   - What we know: It goes after Stage 2 (all writers complete) and before Stage 3 (glossary reconciliation). The generate command currently goes: Step 3 prep -> Stage 1 glossary -> Stage 2 writers -> Stage 3 glossary reconcile -> Stage 4 OVERVIEW.
   - What's unclear: Whether it should be a new named stage (e.g., "Stage 2.5") or folded into Stage 2 as a post-step.
   - Recommendation: Add it as inline logic after Stage 2 completes (not a new named stage). The merge is simple file I/O, not an agent invocation.

2. **Should add-manifest-entry.py handle the _written_sections metadata entry specially?**
   - What we know: The metadata entry has `"section": "_written_sections"` with `"symbols": []`, `"file_paths": []`, plus `"sections_written": [...]`. The validation rule "at least one of symbols/file_paths must be non-empty" would reject it.
   - What's unclear: Whether to add a special case in validation or change the validation rule.
   - Recommendation: Add a special case -- if `section == "_written_sections"`, allow empty symbols and file_paths and require `sections_written` field instead.

3. **Does the verifier agent need a manifest_dir parameter or can it derive it?**
   - What we know: The verifier currently receives `project_root` and `docs_dir`. The manifest directory is at a fixed location: `{project_root}/.mg/docs/reference-manifests/`.
   - What's unclear: Whether to pass it explicitly or have the agent derive it.
   - Recommendation: Derive it from `project_root` -- it's at a fixed, well-known location. No new parameter needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python3 -m pytest`) |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MAN-01 | Manifest files created with correct structure | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x` | Wave 0 |
| MAN-02 | Writer agents emit entries (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-03 | Symbols stored as unqualified identifiers | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py::TestValidation -x` | Wave 0 |
| MAN-04 | Generate orchestrator merges temp->persisted (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-05 | Initial clears, update preserves (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-06 | Stale section cleanup via _written_sections | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py::TestWrittenSections -x` | Wave 0 |
| MAN-07 | Verify reads manifests and checks entries (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-08 | LSP error handling with info finding (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-09 | Broken refs grouped by doc+section (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-10 | check-references.py and artifacts deleted | unit | `python3 -m pytest auto-doc/scripts/tests/ -x` (suite passes without deleted test) | Existing suite |
| MAN-11 | LSP-only verification (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |
| MAN-12 | Manifest covers audience-specific only (LLM prompt change) | manual-only | Validated via end-to-end pipeline run | N/A |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_add_manifest_entry.py` -- covers MAN-01, MAN-03, MAN-06
- No framework install needed -- pytest already in dev dependencies
- No conftest changes needed -- existing test patterns are sufficient

**Note:** Most requirements (MAN-02, MAN-04 through MAN-09, MAN-11, MAN-12) modify LLM prompt files (`.md` commands and agents), not Python code. These are validated by running the auto-doc pipeline end-to-end on a target project, not by automated unit tests. The only automatable unit is `add-manifest-entry.py`.

## Sources

### Primary (HIGH confidence)
- `auto-doc/scripts/add-verify-finding.py` -- pattern to replicate for `add-manifest-entry.py` (validated by reading source)
- `auto-doc/scripts/lib/json_io.py` -- shared atomic JSON I/O (validated by reading source)
- `auto-doc/scripts/check-references.py` -- file to be deleted, understood fully (validated by reading source)
- `auto-doc/commands/auto-doc-generate.md` -- generate orchestrator to modify (validated by reading source)
- `auto-doc/commands/auto-doc-verify.md` -- verify command to modify (validated by reading source)
- `auto-doc/agents/verifier.md` -- verifier agent to modify (validated by reading source)
- `auto-doc/agents/developer-writer.md` -- representative writer agent pattern (validated by reading source)
- `auto-doc/agents/end-user-writer.md` -- writer agent per-section loop (validated by reading source)
- `auto-doc/install.sh` -- install script for deployment (validated by reading source)
- `auto-doc/references/schema.md` -- shared data contract (validated by reading source)
- `auto-doc/scripts/tests/test_add_verify_finding.py` -- test pattern to replicate (validated by reading source)
- `auto-doc/scripts/tests/test_check_references.py` -- test file to be deleted (validated by reading source)
- `.planning/phases/14-auto-doc-reference-manifest/14-CONTEXT.md` -- all locked decisions (primary authority)

### Secondary (MEDIUM confidence)
- None needed -- all decisions are locked and all code is local to this repository

### Tertiary (LOW confidence)
- None -- no external research needed for this phase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools are stdlib Python and existing project patterns, no new dependencies
- Architecture: HIGH -- manifest format, merge logic, and verification approach are fully specified in locked decisions
- Pitfalls: HIGH -- derived from direct analysis of existing code and locked decision constraints

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable -- internal project patterns unlikely to change)
