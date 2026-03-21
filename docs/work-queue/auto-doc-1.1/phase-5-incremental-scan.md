# Phase 5: Incremental Scan — Scoped Updates via Git, GSD, and Code Analysis

**Goal:** Add an incremental scan mode that uses git diff, GSD phase summaries, and reference manifests to scope updates to only what changed — instead of re-scanning the entire codebase every time.

**Depends on:** Phase 3 (reference manifest must exist — manifests are the index that makes scoping possible)

---

## Problem Statement

The current scan pipeline has one mode: full codebase scan. Whether docs are being created for the first time or updated after a small change, every scan agent reads the entire project, re-discovers all components, and rebuilds the full `source_material_index`. This is:

- **Expensive** — 4 parallel scan agents each reading the whole codebase
- **Slow** — minutes of LLM work to rediscover what hasn't changed
- **Noisy** — hard to distinguish "what's new" from "what we already documented"
- **Disconnected from intent** — the scan doesn't know WHY something changed

Meanwhile, the information needed to scope an incremental update is available from three sources the pipeline doesn't combine.

---

## Three Sources of Change Signal

### 1. Git — What changed (authoritative)

`git diff --name-only` since the last generation timestamp gives the complete list of added, modified, and deleted files. Catches everything regardless of process: GSD phases, quick fixes, dependency updates, refactors.

### 2. GSD — Why it changed (contextual)

Phase summaries, deviations, and decisions explain the intent behind changes. A git diff tells you `src/llm/model_routing.py` was modified. GSD tells you "we replaced `route_model()` with provider-specific functions because the single-dispatch pattern couldn't handle streaming."

### 3. Code — How it changed (structural)

The actual implementation. Scan agents still read changed files to understand new APIs and data flows — but only the changed files, with full context from sources 1 and 2.

---

## Two Cycles

### Initial Generation

**Trigger:** No docs exist.
**Scope:** Full codebase.
**Pipeline:** Current pipeline unchanged: full scan → generate all → verify.

### Incremental Update

**Trigger:** Docs exist. Code changed since last generation. Typically after a GSD milestone, but also after ad-hoc work.
**Scope:** Only what changed.

```
Baseline exists (docs + manifests + docs-meta)
    |
    v
Diff phase (deterministic Python script):
    1. git diff --name-only since last generation timestamp
    2. Cross-reference changed files against reference manifests
       → which sections reference these files?
    3. Load GSD phase summaries since last generation
       → what was the intent behind these changes?
    4. Classify results:
       - Changed files mapped to existing sections → sections need update
       - New files not mapped to any section → candidates for new docs
       - Deleted files still in manifests → broken references
       - GSD deviations → context for WHY the change happened
    |
    v
Scoped scan (LLM, narrowly focused):
    - Scan agents receive ONLY changed/new files + GSD context
    - Update source_material_index for affected sections only
    - Carry forward unchanged sections from baseline
    |
    v
Generate (only affected sections, with approval)
    |
    v
Verify (manifests + LSP, full but cheap)
```

---

## Diff Phase — The New Piece

A deterministic Python script (no LLM needed) that produces a scoped work order for the scan:

### Input

```
diff-scan.py \
  --project-root <path> \
  --manifests-dir <path to .mg/docs/reference-manifests/> \
  --docs-dir <path to docs/auto-doc/> \
  --since <last generation ISO timestamp> \
  --gsd-dir <path to .planning/phases/> \
  --output <path to .mg/docs/scan-logs/diff-scope.json>
```

### Output: `diff-scope.json`

```json
{
  "since": "2026-03-17T14:30:00Z",
  "summary": {
    "files_changed": 15,
    "files_added": 3,
    "files_deleted": 1,
    "sections_affected": 8,
    "new_file_candidates": 3
  },
  "affected_sections": [
    {
      "audience": "developers",
      "document": "ARCHITECTURE.md",
      "section": "system-architecture",
      "reason": "source file modified",
      "changed_files": ["src/llm/model_routing.py"],
      "gsd_context": "Phase 6: replaced route_model() with provider-specific functions"
    },
    {
      "audience": "agents",
      "document": "SYSTEM_MAP.md",
      "section": "key-modules",
      "reason": "source file modified",
      "changed_files": ["src/llm/model_routing.py"],
      "gsd_context": "Phase 6: replaced route_model() with provider-specific functions"
    }
  ],
  "new_file_candidates": [
    {
      "file": "src/verify/add-verify-finding.py",
      "reason": "new file, not in any manifest",
      "gsd_context": "Phase 6: new script for verify findings pipeline"
    }
  ],
  "deleted_files": [
    {
      "file": "src/old/legacy.py",
      "referenced_in": ["ARCHITECTURE.md:data-model", "DEVELOPER_GUIDE.md:api-reference"]
    }
  ],
  "gsd_phases_since": [
    {
      "phase": "06",
      "name": "fix-verify-feedback-loop",
      "deviations": [],
      "key_decisions": ["replaced route_model with provider-specific functions"]
    }
  ]
}
```

### How Scan Agents Consume It

The scan command reads `diff-scope.json` and passes each agent a focused scope:

```
Task(
  description="Update source material for developers audience",
  prompt="...
  Mode: incremental
  Only analyze these changed files: [list from diff-scope]
  GSD context for changes: [extracted from diff-scope]
  Carry forward existing source_material_index for unchanged sections.
  Flag new files that need documentation.
  ..."
)
```

---

## Relationship to Other v1.1 Work

**Reference manifest (Phase 3):** The diff phase depends on manifests existing. Manifests are the index that makes incremental scoping possible — without them, we can't cross-reference changed files to affected sections.

**Pipeline cleanup (Phase 1):** `check-references.py` removed from scan pipeline. Incremental scan uses manifests and git diff, not runtime reference extraction.

**Rename (Phase 1):** Must complete before this work. All new files use `auto-doc/` paths.

**Verify:** Runs in full on every cycle (initial and incremental) — manifest + LSP checks are deterministic and fast. No scoping needed.

---

## Scope

| Action | Files |
|--------|-------|
| Create | `auto-doc/scripts/diff-scan.py` + tests (~200-250 + 150-200 lines) |
| Edit | `auto-doc/commands/auto-doc-scan.md` — add incremental mode detection, pass scoped input (~40-50 lines) |
| Edit | `auto-doc/agents/scan-audience.md` — handle scoped input, carry forward unchanged sections (~30-40 lines) |
| Edit | `auto-doc/commands/auto-doc.md` (router) — detect incremental state, suggest scoped scan (~20-30 lines) |

---

## Decisions

1. **Timestamp source:** Single `"generated"` timestamp per manifest. One `git diff --since=<timestamp>` call. Slightly over-inclusive (a section regenerated more recently might get false-positive changed files), but harmless — the scan agent reads the file and concludes "no change needed." Simple implementation, optimize to per-section later if it becomes noisy.
2. **Ad-hoc changes without GSD context:** `gsd_context` field is `null` when no GSD phase covers the change. The scan agent sees `null` and analyzes the changed files on their own merits — same depth as a full scan, just scoped to the changed files.
3. **Rename detection:** `git diff --diff-filter=R` detects renames. The diff script adds an optional `renamed_from` field to affected section entries mapping old→new paths (e.g., `{"src/db/models.py": "src/db/models_v2.py"}`). The scan agent uses this to update source material index entries without re-analyzing unchanged code. The generate step updates the manifest with new paths when it rewrites.
5. **Cross-audience impact:** The diff script does the fan-out. It reads all audience manifests, cross-references changed files, and emits one `affected_sections` entry per audience×document×section combination. The scan command simply filters by audience and passes each agent its slice. Intelligence lives in the deterministic, testable script.
