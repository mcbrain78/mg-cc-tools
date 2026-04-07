# Parallel Fix Waves

## Situation

The `auto-doc-fix` command processes audit findings through a script-controlled sequential loop in `fix-queue.py`. The flow is: extract a group's sections into an edit XML file, spawn a single fixer agent to edit it, merge the edits back into master XMLs, then repeat for the next group.

Each fixer agent (`audit-fixer.md`) receives a unique edit XML file and reads the codebase read-only to verify ground truth before making surgical edits. The sequential constraint was designed to prevent conflicting writes when two groups modify the same master XML file — `serialize_xml_doc` writes atomically per file (via `.tmp` + `os.replace()`), but two concurrent merges targeting the same file would race on the `.tmp` path.

The state file (`fix-state.json`) tracks a single `"current": int` field, enforcing one-at-a-time processing. The `next` subcommand merges the current group before extracting the next, ensuring each extraction reads the latest master state.

The rest of the auto-doc pipeline already uses parallel foreground agent spawning — `auto-doc-generate` spawns 4 writer agents in one message, `auto-doc-verify` spawns 4+ checker agents similarly. The fix command is the only sequential bottleneck.

## Problem

1. **Wall-clock time scales linearly with group count.** Agent work (LLM reads codebase, reasons about findings, produces edits) dominates each iteration. With 80 groups (160 findings), this means ~80 sequential LLM calls. Extraction and merge are fast Python scripts — the agent invocation is the bottleneck.

2. **The sequential constraint is overly conservative.** It prevents all concurrent processing even when groups touch entirely different XML files. There is no mechanism to detect which groups are independent, so the system assumes worst-case (everything conflicts with everything).

## Solution

### Overview

After grouping and approval, compute which XML files each group touches. Partition approved groups into **waves** where no two groups in the same wave touch the same XML file. Process waves sequentially (to maintain merge safety), but spawn all agents within a wave in parallel using the existing parallel foreground pattern. This reuses extract-edit-xml.py and merge-edit-xml.py unchanged — the new logic is entirely within `fix-queue.py` as new subcommands, plus a touch-set computation function.

### Touch-set computation

The mapping from group → XML files already exists in `extract-edit-xml.py:79-128`. For each finding in a group, it resolves `(audience, document)` to an XML path via `_build_xml_index()`, then groups by `(xml_path, section_path)`.

A new function `compute_touch_sets(grouping, findings, xml_dir, group_indices)` extracts just the file-resolution step without building the edit XML tree. It returns `{group_index: set(xml_path, ...)}` — the set of XML files each group will modify. This function lives alongside the existing extract logic (in `extract-edit-xml.py` or a shared module) and reuses `_build_xml_index()` and `_find_xml_for_finding()`.

### Wave partitioning

Given touch sets for all queued groups, partition into waves using greedy first-fit:

```
waves = []
for group in queued_groups:
    placed = False
    for wave in waves:
        if no file in touch_sets[group] appears in wave.files_used:
            wave.groups.append(group)
            wave.files_used |= touch_sets[group]
            placed = True
            break
    if not placed:
        waves.append(Wave(groups=[group], files_used=touch_sets[group]))
```

Each wave is capped at 8 groups. When a wave reaches 8, subsequent groups skip to the next wave even if they don't conflict. This is O(n * w) where n = groups and w = waves — trivial for ~80 groups.

### New subcommands in `fix-queue.py`

**`batch`** — Compute and extract the next wave:

1. Compute touch sets for all remaining queued groups.
2. Run greedy first-fit to select the next wave (up to 8 non-conflicting groups).
3. For each group in the wave, call the existing `_extract_group()` function.
4. Skip groups with 0 sections (same as current `next` behavior).
5. Store the wave as `"current_batch"` in the state file (list of `{group_index, group_id, edit_file}`).
6. Return JSON: `{"status": "batch", "groups": [{group_id, edit_file, section_count}, ...]}` or `{"status": "done", ...}` if queue exhausted.

**`merge-batch`** — Merge all groups in the current batch:

1. For each group in `current_batch`, call the existing `_merge_current()` logic sequentially. Since no two groups in the batch touch the same file, the sequential merge is safe and produces the same result regardless of order.
2. Move all groups to `completed`, clear `current_batch`.
3. Save diffs for each group (same as current behavior).
4. Return JSON: `{"status": "merged", "files_modified": [...], "errors": [...]}`.

### State file extension

The state file gains a `"current_batch"` field (list) alongside the existing `"current"` field (kept for backward compatibility with the `next` subcommand):

```json
{
    "config": { "..." },
    "queue": [3, 5, 6],
    "current": null,
    "current_batch": [
        {"group_index": 0, "group_id": "etl-funcs", "edit_file": "/path/to/etl-funcs.xml"},
        {"group_index": 1, "group_id": "config-refs", "edit_file": "/path/to/config-refs.xml"}
    ],
    "completed": [],
    "skipped": [],
    "files_modified": [],
    "diffs": []
}
```

The `next` subcommand ignores `current_batch` and vice versa — they are independent code paths.

### Updated command flow in `auto-doc-fix.md`

The processing loop in Step 5 changes from:

```
Loop:
  fix-queue.py next → {status, group_id, edit_file}
  if done: break
  Agent(description="Fix group: {group_id}", edit_file=...) — foreground
```

To:

```
Loop:
  fix-queue.py batch → {status, groups: [{group_id, edit_file}, ...]}
  if done: break
  Spawn ALL agents in ONE message (parallel foreground):
    Agent(description="Fix group: {g1}", edit_file=...)
    Agent(description="Fix group: {g2}", edit_file=...)
    ...
  fix-queue.py merge-batch
```

All other steps (1-4, 6-7) remain unchanged.

## Design Decisions

### D1: File-level conflict granularity

**Choice:** Two groups conflict if they touch the same XML file, even if they target different sections within that file.

**Why:** `serialize_xml_doc` writes the entire XML file atomically via a `.tmp` + `os.replace()` pattern. Two concurrent merges targeting the same file would race on the `.tmp` path. File-level granularity avoids this entirely and keeps the merge step simple — each file in a wave is written by exactly one group's merge. Section-level granularity would require per-file sequential merge ordering within a wave, adding complexity for marginal parallelism gain.

**Alternatives rejected:** Section-level conflict detection — would allow more parallelism when multiple groups touch different sections of the same large XML file, but requires coordinating merge order per file and risks `.tmp` file races without additional locking.

### D2: Parallel foreground agent spawning

**Choice:** All agents in a wave are spawned as multiple Agent() calls in a single message (parallel foreground pattern).

**Why:** This is the proven pattern used by `auto-doc-generate` (4 writer agents) and `auto-doc-verify` (4+ checker agents). It's simpler than background agents, requires no polling or wait logic, and the orchestrator naturally blocks until all agents complete before proceeding to the merge step.

**Alternatives rejected:** Background agents with `run_in_background` — no precedent in auto-doc commands, would require explicit completion tracking, and adds complexity without benefit since the orchestrator must wait for all agents before merging anyway.

### D3: Wave size capped at 8

**Choice:** Each wave processes at most 8 groups, even if more are independent.

**Why:** Spawning too many concurrent agents risks overwhelming the system (context allocation, API rate limits, memory). A cap of 8 provides substantial speedup (~10x over sequential for 80 groups) while staying within practical limits observed in the codebase (auto-doc-generate uses 4, auto-doc-verify uses ~8).

**Alternatives rejected:** No cap — with 80 mostly-independent groups, a single wave could contain 30+ agents, which is untested territory. Higher caps (12, 16) could be explored later if 8 proves too conservative.

## Scope

### What gets built

| Deliverable | Location | Notes |
|---|---|---|
| `compute_touch_sets()` function | `extract-edit-xml.py` (or shared lib) | Reuses `_build_xml_index`, `_find_xml_for_finding` |
| `batch` subcommand | `fix-queue.py` | Wave computation + multi-group extraction |
| `merge-batch` subcommand | `fix-queue.py` | Sequential merge of current batch |
| State file extension | `fix-queue.py` | `current_batch` field alongside existing `current` |
| Updated processing loop | `auto-doc-fix.md` | Batch loop replacing sequential next loop |
| Tests | `tests/test_fix_queue.py`, `tests/test_extract_edit_xml.py` | Touch-set, wave partitioning, batch/merge-batch, equivalence |

### What does NOT get built

- **Changes to grouping algorithm** — wave partitioning is post-grouping; the group-findings agent is unchanged.
- **Changes to extract-edit-xml.py extraction logic** — reused as-is via existing `_extract_group()`.
- **Changes to merge-edit-xml.py** — reused as-is; called once per group during merge-batch.
- **Changes to audit-fixer.md** — already works on isolated edit files; no awareness of parallelism needed.
- **Background agent patterns** — parallel foreground only (D2).
- **Distributed locking or concurrent state file writes** — wave design makes these unnecessary (D1).
- **Dynamic wave sizing or adaptive caps** — fixed cap of 8 (D3).

## Open Items

None — all decisions resolved during discussion.

## Verification

1. **Touch-set correctness.** Given a grouping with known findings mapping to known XML files, `compute_touch_sets()` returns the expected set of XML files per group. Test with: single-file group, multi-file group, group with findings that don't resolve to any XML file (empty touch set).

2. **Wave partitioning correctness.** Given touch sets, verify: (a) no two groups in the same wave share an XML file, (b) every approved group appears in exactly one wave, (c) no wave exceeds 8 groups. Test with: all groups independent (one wave of 8 + overflow), all groups conflicting (8 waves of 1), mixed independence.

3. **Equivalence with sequential mode.** Run both `batch`+`merge-batch` loop and `next` loop on the same grouping/findings/XML sources (using temp copies). Final XML files must be byte-identical. This validates that wave partitioning + parallel extraction + sequential-per-wave merge produces the same result as fully sequential processing.

4. **State file integrity.** After a full batch run: `queue` is empty, all groups are in `completed` or `skipped`, `current_batch` is null, `files_modified` lists all changed XML files, `diffs` lists all diff files.

5. **Edge cases.** Empty groups (0 matching sections) are skipped within a batch without blocking the wave. Single-group waves work correctly. A wave where all extracted groups turn out empty skips to the next wave.
