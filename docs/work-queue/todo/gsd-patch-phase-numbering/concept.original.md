# GSD ROADMAP Writer Consolidation & Marker System

> Scope note: the directory slug is `gsd-patch-phase-numbering` (the originating bug was add-phase numbering), but the concept is broader — it consolidates *all* ROADMAP editing. Target: the canonical GSD fork at `external-tools/mg-gsd-fork`; propagated to projects by `bin/install.js`.

## Situation

GSD tracks a project's plan in two files under `.planning/`:

- **`STATE.md`** — YAML frontmatter (`progress: {total_phases, completed_phases, total_plans, completed_plans, percent}`, `status`, …) plus a prose body. **Every** STATE write routes through one choke-point: `writeStateMd → syncStateFrontmatter → buildStateFrontmatter` (`state.cjs:781/770/608`), opts-driven (`recomputeProgress`, `recomputeStatus`). 16 call sites, one writer. Once this was consolidated (the "Bug 6/7" work), STATE stopped generating bugs.
- **`ROADMAP.md`** — LLM-authored Markdown. Each milestone's phase facts are **duplicated across ≥5 surfaces**: the `### Phase N:` detail block, the `- [ ] **Phase N: …**` checklist, a single shared progress table (`| Phase | Milestone | Plans | Status | Completed |`), and the milestone phase-range string ("Phases 14-22") — which appears in **both** a `## Milestones` bullet **and** a `<details><summary>` line.

ROADMAP has **no central writer**. Five functions each edit those prose surfaces with their own regexes:

| Function | Location | Edits |
|---|---|---|
| `cmdPhaseAdd` | `phase.cjs:311` | dir + detail block only |
| `cmdPhaseInsert` | `phase.cjs:367` | dir + decimal detail block only |
| `cmdPhaseRemove` | `phase.cjs:448` | detail + checkbox + table row; on-disk dir/file renames (`:488-600`); 99→down global renumber sweep (`:622-664`); body-only STATE count (`:668-687`) |
| `cmdPhaseComplete` | `phase.cjs:701` | checkbox + table row (Bug-3 anchor, `:726-758`) + STATE status |
| `cmdRoadmapUpdatePlanProgress` | `roadmap.cjs:221` | table row + detail plan count + checkbox |

Real-world reference (`road-runner/.planning/ROADMAP.md`, 22 phases / 4 milestones): three coexisting checklist dialects — non-bold completed (`- [x] Phase 1:`), bold active (`- [x] **Phase 14:**`), and plan-level (`- [x] 14-01-PLAN.md`); decimal inserted phases (17.1, 20.1); a 5-column table with genuinely malformed rows; and two range strings **already drifted** (`Phases 14-22` vs `Phases 14-21`). The fork test suite is currently green (535/535).

## Problem

**Root cause:** the same facts are duplicated across loosely-formatted prose surfaces, each edited by independent regex. Every format variant spawns another patch — the entire Bug 1–8 sequence traces here. Concretely:

1. **`add-phase` under-writes (the originating "Bug 8").** `cmdPhaseAdd` writes only the directory + detail block. The checklist row, table row, milestone range, and STATE count are written by **nobody** — the workflow assigns the agent only a "Roadmap Evolution" note. Every other surface was fixed by hand.
2. **Sibling defects.** `cmdPhaseInsert` has the identical under-write (decimal phases' checklist/table rows were all added by hand). `cmdPhaseRemove` decrements only the STATE body line, not the frontmatter count — so `add` (once fixed) and `remove` are asymmetric.
3. **Range drift.** No code maintains the milestone range; it lives in ≥2 places with different syntax and has already drifted in production.
4. **Invisible divergence.** The structural check (`roadmap.cjs:203`) flags only *checklisted-without-detail*, never *detail-without-checklist* — the exact inconsistency `add` creates.
5. **Structural fragility.** Fixes are scattered regex; each new format quirk (bold vs non-bold, 4- vs 5-column, decimals, two range forms) requires another patch.

**Net effect:** the STATE frontmatter and the ROADMAP index drift from reality. The milestone **audit** reads `completed_phases`/`phase_count` (`audit-milestone.md:18`) and is misled. (Note: *premature close* itself is guarded by per-phase `disk_status === 'complete'` at `complete-milestone.md:48` — an unplanned new phase is not disk-complete — so the accurate severity is **inconsistency the audit trusts**, not silent auto-close.)

## Solution

### Overview

Apply STATE's proven pattern to ROADMAP. Wrap each editable ROADMAP surface in greppable, render-invisible HTML-comment **region markers**, and route all five phase-editing functions through a single **`roadmap-writer.cjs`** module that locates and edits those marked regions instead of guessing prose anchors. Markers are **authored** by the templates and the milestone-close workflow (never heuristically inferred), and writers **require** them — erroring with a migration hint if absent. A one-shot, supervised migration installs markers into existing roadmaps. STATE gains a signed `deltaPhases` on its existing choke-point; `percent` is left untouched.

### 1. Marker spec

Per-milestone, render-invisible fences:

```markdown
<!-- gsd:milestone v4.0 -->
<details open>
<summary>🔄 v4.0 Production Hybrid Search <!-- gsd:range v4.0 -->(Phases 14-22)<!-- /gsd:range --> — IN PROGRESS</summary>
<!-- gsd:checklist v4.0 -->
- [x] **Phase 14: …**
- [ ] **Phase 22: …**
<!-- /gsd:checklist v4.0 -->
</details>
<!-- /gsd:milestone v4.0 -->
```

The single global progress table is wrapped `<!-- gsd:table -->…<!-- /gsd:table -->`. The **range marker may appear multiple times** per milestone (the `## Milestones` bullet *and* the `<summary>`); `setMilestoneRange` updates **all** occurrences, so they can never drift again. **Invariant (load-bearing, must be a tested rule):** comment fences sit on their own lines or *after* the closing `**` of a bold span — verified not to break any existing reader regex (`getMilestoneInfo` `core.cjs:415`, `getMilestonePhaseFilter` `core.cjs:458`, checklist/table patterns `roadmap.cjs:196/261`, `phase.cjs:740`).

### 2. `roadmap-writer.cjs` module

Pure `content → content'` string transforms (no I/O), one test suite. All five commands become thin: `read → validateMarkers → module ops → single write`.

- `ensureMarkers(content)` — **validator + one-shot migration only** (not a per-write heuristic): if markers present, validate/repair; if absent, used solely by the explicit migration path.
- `addIntegerPhase(content, {milestone, number, name})` — detail + checklist row + table row.
- `insertDecimalPhase(content, {afterPhase, number, name})` — decimal detail + checklist row + table row (no count change).
- `removePhase(content, {number, isDecimal})` — removes the fenced surfaces; see §6 for the parts that stay outside the module.
- `setPhaseProgress(content, {number, status, plansDone, plansTotal, date})` — checkbox + table cells (shared by `complete` and `update-plan-progress`, retiring the duplicated Bug-3 logic).
- `setMilestoneRange(content, {milestone, hi})` — updates all range markers for the milestone.

### 3. Authored markers + require/validate

Markers are emitted at every generation point — `templates/roadmap.md` (the initial `## Phases` checklist + `### Phase Details`), the `complete-milestone.md:323` reorg block, and the new-project/new-milestone roadmapper guidance. These are concrete, editable template blocks, so emission is reliable. Writers call `validateMarkers(content)` first and **hard-error** (`"run gsd-tools roadmap ensure-markers"`) when markers are absent — no silent auto-heal on write.

### 4. One-shot supervised migration

`gsd-tools roadmap ensure-markers [--dry-run]` installs markers into an existing (legacy) roadmap by detecting today's sections **once**, under operator review of the diff. Folded into `gsd:health` as a check. Run once per controlled project before its next phase op.

### 5. STATE: `deltaPhases` + percent untouched

- Add a signed `deltaPhases` to `writeStateMd`/`buildStateFrontmatter`, applied **only** on the carry-forward branch (`add` `+1`, `remove` `−1`, `insert` `0`). `completed_phases` is untouched.
- **`percent` is not modified.** It is plan-based (`summaries/plans`) in all three computations (`state.cjs:344`, `roadmap.cjs:212`, `commands.cjs:416`); adding an unplanned (0-plan) phase doesn't change it, and milestone-close is guarded by `disk_status`, not percent.

### 6. `remove` specifics

The module handles the **fenced** checklist + table removal. Everything else `cmdPhaseRemove` does today is **retained**: the on-disk directory/file renames (`phase.cjs:488-600`) verbatim, and a **tightened, scoped** cross-reference renumber for `**Depends on:** Phase N` and plan-refs (`NN-01`) that live in detail prose **outside** any fence (replacing the current 99→down global sweep). The fence replaces only the subset it covers.

### 7. Inverse structural check

Add the mirror of `missing_phase_details`: `missing_phase_checklist = [...detailPhases].filter(p => !checklistPhases.has(p))`, surfaced in the `roadmap analyze` result. Trivial and reliable once surfaces are marked.

## Design Decisions

### D1: Markers + one writer module, mirroring STATE

**Choice:** Greppable region markers + a single `roadmap-writer.cjs` all five functions route through.

**Why:** STATE's single choke-point eliminated its bug class; ROADMAP is the unsolved analog (five independent regex writers). Markers make surface location O(1) and format-variance-proof (we own what's inside the fence).

**Alternatives rejected:** *Full render-from-model* (a `roadmap.json` source of truth that regenerates all prose) — fights GSD upstream's own direct-`.md` writers (`complete-milestone` deletes/recreates the file) on every fork re-sync; high blast radius. *Hardened patch* (byte-range-scoped regex, no markers) — stays in the parse-fragile-prose paradigm; the next format quirk is another patch.

### D2: Markers authored, not inferred; writers require/validate (no auto-heal)

**Choice:** Templates + `complete-milestone` emit markers; writers validate-and-error if absent; `ensureMarkers` is a validator + one-shot migration, never a per-write heuristic.

**Why:** Auto-detection is unreliable on the real file — three checklist dialects coexist and the bold/non-bold signal cannot separate the non-bold *milestone* checklist (`ROADMAP.md:21`) from the non-bold *plan-level* checklist (`:88`); detection would have to rebuild the milestone-vs-detail tree (the very parsing markers exist to avoid). And the ROADMAP is LLM-authored and **rewritten at milestone boundaries** (`complete-milestone.md:323/402`), so auto-heal-on-every-write would weaponize any detection miss into per-command corruption + churny diffs.

**Alternatives rejected:** Auto-heal-on-write (heuristic detection at the top of every writer).

### D3: Hard-require markers (error if absent)

**Choice:** Writers error with a migration hint when markers are missing.

**Why:** A single clean code path (the fragile regex path is fully retired). Migration is a cheap one-time supervised pass across the ~4 controlled projects.

**Alternatives rejected:** Legacy-regex fallback + warning during a transition — keeps two code paths and the fragile one alive until every project migrates.

### D4: Leave `percent` untouched

**Choice:** Do not modify `percent` anywhere; only bump `total_phases` via `deltaPhases`.

**Why:** `percent` is plan-based in all three computations; an unplanned (0-plan) phase doesn't change it, so it stays correct. Premature-close is guarded by per-phase `disk_status` (`complete-milestone.md:48`), and the audit's `completed < total` view is corrected by the `total_phases` bump.

**Alternatives rejected:** Unify all percent to phase-based (`completed/total`) — a three-site breaking change that would make `/gsd:progress` and `state json` disagree, and churn the value on every `update-progress`.

### D5: `deltaPhases` strict carry-forward + assert no recompute

**Choice:** Apply the signed delta only on the carry-forward branch, and assert `recomputeProgress === false`.

**Why:** The phase directory is created *before* the STATE write (`phase.cjs:339/411`). On a bootstrap/recompute (`existingProgress === null` forces `recomputeProgress`, `state.cjs:669`), the disk recount already counts the new dir; a delta on top would double-count.

### D6: Unify add+insert+remove, but keep `remove`'s on-disk renames + a scoped cross-ref sweep

**Choice:** Route all three through the module for fenced surfaces; retain `remove`'s on-disk dir/file renames verbatim and a tightened (scoped) renumber for `Depends on`/plan-refs outside fences.

**Why:** Cross-references live in detail prose outside any fence, so a fence-bounded edit cannot cover them; the on-disk renaming is orthogonal to ROADMAP text. `remove` is also guarded against executed phases (`phase.cjs:478`), so it is low-traffic — not worth over-consolidating.

**Alternatives rejected:** Claiming the module "replaces" the whole renumber sweep — it would silently drop `Depends on`/prose plan-ref rewrites.

## Scope

### What gets built

- **`get-shit-done/bin/lib/roadmap-writer.cjs`** — new module (the six primitives in §2) + dedicated test suite. *Requires new parsing logic — the core effort.*
- **Marker emission** added to `templates/roadmap.md`, the `complete-milestone.md` reorg block, and new-project/new-milestone roadmapper guidance. *Editing existing template blocks.*
- **`ensureMarkers` validator** + `gsd-tools roadmap ensure-markers [--dry-run]` CLI + `gsd:health` check.
- **Route the five writers** (`phase add/insert/remove/complete`, `roadmap update-plan-progress`) through the module — thin orchestration, single read/write each.
- **`deltaPhases`** on `writeStateMd`/`buildStateFrontmatter` (strict carry-forward, D5).
- **Inverse structural check** (`missing_phase_checklist`) in `roadmap.cjs`.
- **`add-phase.md` workflow update** — drop the manual count/index toil (now CLI-owned); keep the Roadmap-Evolution note; explicitly surface the status-reopen decision to the operator.
- **Realistic test fixture** (3 checklist dialects, collapsed + open `<details>`, decimals, a malformed 5-col row, two range strings, `Depends on` lines) + an `ensureMarkers` idempotency fixed-point test.

### What does NOT get built

- **Full render-from-model** — rejected (D1).
- **Percent unification / phase-based percent** — rejected (D4).
- **Auto-heal-on-write** — rejected (D2).
- **Fixing pre-existing test failures** — the 8 prior failures were resolved separately; suite is green.
- **Markers in archived `milestones/*.md`** — they are frozen byte-snapshots (`milestone.cjs:139`); correctly left alone.
- **Migrating external / non-controlled GSD installs** — only the ~4 controlled projects are migrated.

## Open Items

None. All decisions were resolved during drafting (D1–D6). The items below are **verification obligations**, not unresolved decisions:
- Confirm the scoped cross-ref renumber preserves every reference the 99→down sweep covered (headings, checkboxes, `Depends on`, plan-refs `NN-01`, table `| N.`).
- Confirm the marker fences pass every existing reader regex (regression test, §1 invariant).

## Verification

- **add-phase** on a marked, milestone-complete fixture → adds checklist row + table row + detail block; bumps the range in **all** occurrences; STATE `total_phases +1`, `completed_phases` unchanged, `status` untouched; `total_phases` is `N+1`, **not** inflated by decimal phases.
- **insert-phase** → decimal checklist + table + detail; STATE counts unchanged.
- **remove-phase** → fenced surfaces removed; on-disk dir/file renames intact; `Depends on`/plan-refs renumbered; frontmatter `total_phases −1` (symmetric with add).
- **complete** + **update-plan-progress** → checkbox + table via `setPhaseProgress`, byte-identical outcome to current behavior (no regression).
- **Markers** → `ensureMarkers(ensureMarkers(x)) === ensureMarkers(x)` on the realistic fixture (incl. malformed rows + mixed dialects); a writer on an unmarked file errors with the migration hint; marked content still matches every existing reader regex.
- **Inverse check** → a detail block with no checklist row appears in `missing_phase_checklist`.
- **Percent** → unchanged across the suite; milestone-close remains blocked by `disk_status` when an unplanned phase is present.
- **Generation (authored markers)** → `new-project`, `new-milestone`, and the `complete-milestone` reorg each produce a ROADMAP that `validateMarkers` accepts (markers present and well-formed at every generation point) — closing the loop so the require-markers writers never hit a freshly generated, unmarked file.
- **Workflow** → `add-phase.md` no longer instructs the agent to edit counts or index surfaces (now CLI-owned), and the status-reopen decision is surfaced to the operator rather than silently skipped.
- **Suite** → stays green (≥535 passing) with the new tests added.
