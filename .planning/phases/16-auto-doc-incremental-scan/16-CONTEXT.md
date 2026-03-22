# Phase 16: Auto Doc Incremental Scan - Context

**Gathered:** 2026-03-22 (imported), 2026-03-22 (supplemental discussion)
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/auto-doc-1.1/phase-5-incremental-scan.md) + supplemental discussion

<domain>
## Phase Boundary

Add an incremental scan mode that uses git diff, GSD phase summaries, and reference manifests to scope updates to only what changed — instead of re-scanning the entire codebase every time. Depends on Phase 14 (reference manifest must exist — manifests are the index that makes scoping possible).

</domain>

<decisions>
## Implementation Decisions

### Two cycles — initial vs incremental
- **Initial generation:** no docs exist → full codebase scan → generate all → verify. Current pipeline unchanged.
- **Incremental update:** docs exist, code changed since last generation → diff phase → scoped scan → generate only affected sections → verify (full, cheap)
- The scan command detects which mode to use based on whether docs and manifests exist

### Three sources of change signal
1. **Git** (authoritative) — `git diff -M --name-only` between last-generation commit and HEAD. Complete list of added, modified, deleted, renamed files.
2. **GSD** (contextual) — phase summaries, deviations, decisions explain WHY changes happened. Loaded from `*-SUMMARY.md` files in `.planning/phases/`.
3. **Code** (structural) — scan agents still read changed files, but only the changed files with full context from sources 1 and 2.

### diff-scan.py — deterministic Python script
- No LLM needed — produces a scoped work order for the scan
- CLI interface:
  ```
  diff-scan.py \
    --project-root <path> \
    --manifests-dir <path to .mg/docs/reference-manifests/> \
    --docs-dir <path to docs/auto-doc/> \
    --since <last generation ISO timestamp> \
    --gsd-dir <path to .planning/phases/> \
    --output <path to .mg/docs/diff-scope.json>
  ```
- Output written to `.mg/docs/diff-scope.json` (NOT `scan-logs/` — avoids being picked up by merge-scan.py which reads all `*.json` in `scan-logs/`)

### diff-scope.json output format
- Top-level: `since`, `summary` (counts), `affected_sections`, `new_file_candidates`, `deleted_files`, `gsd_phases_since`
- `affected_sections`: array of `{audience, document, section, reason, changed_files, gsd_context}` — one entry per audience×document×section combination
- `new_file_candidates`: array of `{file, reason, gsd_context}` — files not in any manifest
- `deleted_files`: array of `{file, referenced_in: [{audience, document, section}]}` — files still in manifests but deleted
- `gsd_phases_since`: array of `{phase, name, deviations, key_decisions}` — GSD phases modified since last generation

### diff-scan.py processing steps
1. Resolve timestamp to commit: `git rev-list --max-count=1 --before=<timestamp> HEAD`, then `git diff -M --name-only <base-commit> HEAD`
2. Cross-reference changed files against reference manifests → which sections reference these files?
3. Discover GSD phases modified since last generation via `git log --since=<ts> --name-only --pretty=format:"" -- .planning/phases/`, then load matching `*-SUMMARY.md` files
4. Classify: changed files mapped to sections → sections need update; new files not mapped → candidates; deleted files in manifests → broken references; GSD deviations → context

### Timestamp source
- Single global `last_generated` ISO timestamp stored as a top-level field in `docs-scan.json` (not per-audience, not per-manifest — one timestamp for the whole pipeline)
- Not a commit SHA — commits can be lost during squash & merge
- Resolved to base commit via `git rev-list --max-count=1 --before=<timestamp> HEAD`
- Written by the generate command at pipeline start — makes next diff over-inclusive rather than under-inclusive
- Over-inclusive by design: commits during generation appear in next diff (harmless re-scan) rather than being silently missed
- If `last_generated` field is missing from `docs-scan.json`, treat as initial mode (full scan). No migration path needed — old docs are deleted before adopting incremental scan
- Two timestamp systems coexist: `last_generated` in docs-scan.json drives diff-scan.py scoping; docs-meta `last_updated` (per-section) drives staleness-check.py post-generate validation
- diff-scan.py reads `--since` from docs-scan.json's `last_generated` field (scan command extracts and passes it)

### Rename detection
- Both git commands use `-M` to enable rename detection
- Main diff reports renames as single entries (not delete+add pairs) — prevents false positives
- Separate `git diff -M --diff-filter=R --name-status <base-commit> HEAD` extracts rename pairs specifically
- Script parses `R<score>\told\tnew` output, adds optional `renames` field to affected section entries mapping old→new paths
- Scan agent uses this to update source material index entries and manifest paths without re-analyzing unchanged code

### Carry-forward strategy
- Scan command loads previous `docs-scan.json`, filters by audience, passes unchanged section entries to each scan agent as baseline
- Agent writes complete output: changed entries from analysis + carried-forward entries copied verbatim
- `merge-scan.py` works unchanged — still receives complete per-audience files

### How scan agents consume diff-scope
- Scan command reads `diff-scope.json` and passes each agent a focused scope
- Agent prompt includes: mode (incremental), changed files list, GSD context, baseline entries for unchanged sections, new file candidates to classify
- Unchanged entries are copied verbatim into output

### Ad-hoc changes without GSD
- `gsd_context` field is `null` when no GSD phase covers the change
- Scan agent analyzes changed files on their own merits — same depth as full scan, just scoped
- If `--gsd-dir` does not exist, script skips GSD entirely: `gsd_phases_since` is `[]`, all `gsd_context` fields are `null`. No error, no warning — GSD is optional context, not a prerequisite.

### New file candidates
- Scan agents auto-classify new files into existing document sections based on content, location, and audience template structure
- No user approval step — too many files for manual triage
- New entries tagged with `"source": "incremental"` so generate step can highlight them in approval diff

### Cross-audience impact
- Diff script does the fan-out: reads all audience manifests, cross-references changed files, emits one `affected_sections` entry per audience×document×section combination
- Scan command simply filters by audience and passes each agent its slice
- Intelligence lives in the deterministic, testable script

### Staleness check relationship
- In incremental mode, `diff-scan.py` replaces staleness check's scoping role
- Staleness check continues as post-generate validation (confirming no section was missed)
- No longer drives scoping decisions

### Verify unchanged
- Runs in full on every cycle (initial and incremental) — manifest + LSP checks are deterministic and fast
- No scoping needed for verify

### Incremental scan summary UX
- After incremental scan completes, show a diff-focused summary: N files changed, N sections affected across M audiences, N new files to classify, N deleted file references
- Do NOT repeat the full project model summary (tech stack, components, etc.) — that's unchanged
- Show the summary only AFTER scan completes, not before (no pre-scan preview)
- Router Route D (pipeline complete) updated to mention that re-scan will be incremental (scoped to changes since last generation)

### Full-scan escape hatch
- No `--full` flag — to force a full scan, user deletes `docs/auto-doc/` and `.mg/docs/docs-scan.json`
- No threshold-based fallback — always run incremental if manifests and `last_generated` exist, regardless of diff size
- Large diffs just mean more sections get updated; the pipeline handles it fine

### No migration path
- Old documentation from pre-Phase-16 projects is deleted before adopting incremental scan
- No need to handle missing timestamps in existing manifests or docs-scan.json gracefully beyond falling back to full scan

### Claude's Discretion
- Internal architecture of `diff-scan.py` (class structure, helper functions)
- Test fixture design and sample data for diff-scope tests
- How to present incremental mode detection in the router (messaging, suggestions)
- Error handling for edge cases (corrupt manifests, missing git history, timestamp before any commits)
- Whether to add a `--dry-run` mode to diff-scan.py for previewing scope without running scan
- How to structure the incremental mode prompt additions in scan-audience.md

</decisions>

<specifics>
## Specific Ideas

- The diff-scope.json example in the source document shows the complete output schema — use it as the reference for implementation and test assertions
- The scan agent Task prompt example shows exactly how scoped input is passed to agents in incremental mode
- `diff-scope.json` goes in `.mg/docs/` specifically to avoid `scan-logs/` where merge-scan.py reads all `*.json`
- Script is ~200-250 lines + 150-200 lines of tests — comparable to other pipeline scripts

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `staleness-check.py` git helpers (`lib/git_helpers`): reusable for `git rev-list` and `git log` operations in diff-scan.py
- `merge-scan.py`: works unchanged with incremental mode — receives complete per-audience files regardless of mode
- Reference manifests (Phase 14): the index that makes incremental scoping possible

### Established Patterns
- Atomic JSON I/O via `os.replace` and temp files: use for diff-scope.json output
- File-based I/O pattern (`--input`/`--output`): consistent with all other pipeline scripts
- Per-audience parallel scan agents: incremental mode passes scoped data per-agent, same parallelism

### Integration Points
- `auto-doc/commands/auto-doc-scan.md`: add incremental mode detection, load previous docs-scan.json, pass scoped input to agents
- `auto-doc/agents/scan-audience.md`: handle scoped input, carry forward unchanged sections
- `auto-doc/commands/auto-doc.md` (router): detect incremental state, suggest scoped scan
- `.mg/docs/reference-manifests/`: read manifests for cross-referencing changed files to sections
- `.mg/docs/diff-scope.json`: output location for the diff script

</code_context>

<deferred>
## Deferred Ideas

None — source document covers phase scope. The incremental scan is the final phase in the v1.1 roadmap.

</deferred>

---

*Phase: 16-auto-doc-incremental-scan*
*Context gathered: 2026-03-22 via context import*
