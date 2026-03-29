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

`git diff -M --name-only` between the last-generation commit and HEAD gives the complete list of added, modified, deleted, and renamed files. The script resolves the generation timestamp to a commit via `git rev-list --max-count=1 --before=<timestamp> HEAD`, then diffs from that commit. Catches everything regardless of process: GSD phases, quick fixes, dependency updates, refactors.

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
    1. Resolve timestamp to commit: git rev-list --max-count=1 --before=<ts> HEAD
       Then: git diff -M --name-only <base-commit> HEAD
    2. Cross-reference changed files against reference manifests
       → which sections reference these files?
    3. Discover GSD phases modified since last generation via
       git log --since=<ts> --name-only --pretty=format:"" -- .planning/phases/
       Then load matching *-SUMMARY.md files for intent context
    4. Classify results:
       - Changed files mapped to existing sections → sections need update
       - New files not mapped to any section → candidates for new docs
       - Deleted files still in manifests → broken references
       - GSD deviations → context for WHY the change happened
    |
    v
Scoped scan (LLM, narrowly focused):
    - Scan command loads previous docs-scan.json as baseline
    - Filters baseline by audience and passes unchanged entries to each agent
    - Scan agents analyze ONLY changed/new files + GSD context
    - Agents write complete output (changed + carried-forward entries)
    - merge-scan.py works unchanged — it sees complete per-audience files
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
  --output <path to .mg/docs/diff-scope.json>
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
      "referenced_in": [
        {"audience": "developers", "document": "ARCHITECTURE.md", "section": "data-model"},
        {"audience": "developers", "document": "DEVELOPER_GUIDE.md", "section": "api-reference"}
      ]
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
  Baseline entries for unchanged sections: [JSON entries from previous docs-scan.json]
  Copy these unchanged entries verbatim into your output.
  New file candidates to classify into sections: [list from diff-scope]
  Auto-classify each into your document sections based on content and location.
  ..."
)
```

---

## Relationship to Other v1.1 Work

**Reference manifest (Phase 3):** The diff phase depends on manifests existing. Manifests are the index that makes incremental scoping possible — without them, we can't cross-reference changed files to affected sections.

**Pipeline cleanup (Phase 1):** `check-references.py` removed from scan pipeline. Incremental scan uses manifests and git diff, not runtime reference extraction.

**Rename (Phase 1):** Must complete before this work. All new files use `auto-doc/` paths.

**Staleness check (`staleness-check.py`):** In incremental mode, `diff-scan.py` replaces the staleness check's scoping role — both use git history to find what changed, but `diff-scan.py` also cross-references manifests and adds GSD context. The staleness check continues to run as a post-generate validation (confirming no section was missed), but no longer drives scoping decisions. The per-manifest timestamp is over-inclusive by design (see Decision 1), meaning it may flag extra sections but never misses changes. Staleness-check.py's per-section docs-meta timestamps serve as an independent correctness check after generation completes.

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

1. **Timestamp source:** Single `"generated"` ISO timestamp per manifest (not a commit SHA — commits can be lost during squash & merge). Resolved to a base commit via `git rev-list --max-count=1 --before=<timestamp> HEAD`, then `git diff -M --name-only <base-commit> HEAD`. The timestamp is captured at the *start* of the generate pipeline, making the next diff over-inclusive rather than under-inclusive — commits that land during generation appear in the next diff (harmless re-scan) rather than being silently missed. This is slightly over-inclusive: when individual sections were regenerated more recently than the manifest timestamp, their source files still appear in the diff even though their docs are current. This is harmless — the scan agent reads the file and concludes "no change needed," costing only extra read time, not incorrect output. Two timestamp systems coexist and are complementary: the manifest timestamp (per-audience) drives diff-scan.py scoping, while docs-meta `last_updated` timestamps (per-section) drive staleness-check.py post-generate validation.
2. **Ad-hoc changes without GSD context:** `gsd_context` field is `null` when no GSD phase covers the change. The scan agent sees `null` and analyzes the changed files on their own merits — same depth as a full scan, just scoped to the changed files.
3. **Rename detection:** Both git commands use `-M` to enable rename detection. The main diff (`git diff -M --name-only <base-commit> HEAD`) reports renames as single entries rather than delete+add pairs, preventing false positives in `deleted_files` and `new_file_candidates`. A separate `git diff -M --diff-filter=R --name-status <base-commit> HEAD` extracts the rename pairs specifically. The diff script parses the `R<score>\told\tnew` output and adds an optional `renames` field to affected section entries mapping old→new paths (e.g., `{"src/db/models.py": "src/db/models_v2.py"}`). The scan agent uses this to update source material index entries and manifest paths without re-analyzing unchanged code.
4. **Carry-forward strategy:** In incremental mode, the scan command loads the previous `docs-scan.json`, filters it by audience, and passes unchanged section entries to each scan agent as baseline data. The agent writes a complete output file — changed entries from its analysis plus carried-forward entries copied verbatim. This means `merge-scan.py` works unchanged (it still receives complete per-audience files). `diff-scope.json` is written to `.mg/docs/` (not `scan-logs/`) to avoid being picked up by the merge script, which reads all `*.json` in `scan-logs/`.
5. **GSD absence:** If `--gsd-dir` does not exist, the script skips GSD entirely: `gsd_phases_since` is `[]` and all `gsd_context` fields are `null`. No error, no warning — GSD is optional context, not a prerequisite.
6. **New file candidates:** Scan agents auto-classify new files into existing document sections based on the file's content, location, and the audience's template structure. No user approval step — there are too many files for manual triage. New files appear as new entries in the agent's `source_material_index` output, tagged with `"source": "incremental"` so the generate step can highlight them for review in the approval diff.
7. **Cross-audience impact:** The diff script does the fan-out. It reads all audience manifests, cross-references changed files, and emits one `affected_sections` entry per audience×document×section combination. The scan command simply filters by audience and passes each agent its slice. Intelligence lives in the deterministic, testable script.
