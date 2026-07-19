# GSD ROADMAP Writer Consolidation & Marker System

> Scope note: the directory slug is `gsd-patch-phase-numbering` (the originating bug was add-phase numbering), but the concept is broader — it consolidates *all* ROADMAP editing. Target: the canonical GSD fork at `external-tools/mg-gsd-fork`; propagated to projects by `bin/install.js`.

## Situation

GSD tracks a project's plan in two files under `.planning/`:

- **`STATE.md`** — YAML frontmatter (`progress: {total_phases, completed_phases, total_plans, completed_plans, percent}`, `status`, …) plus a prose body. **Every** STATE write routes through one choke-point: `writeStateMd → syncStateFrontmatter → buildStateFrontmatter` (`state.cjs:781/770/608`), opts-driven (`recomputeProgress`, `recomputeStatus`). 16 call sites, one writer. Once this was consolidated (the "Bug 6/7" work), STATE stopped generating bugs.
- **`ROADMAP.md`** — LLM-authored Markdown. Each milestone's phase facts are **duplicated across ≥5 surfaces**: the `### Phase N:` detail block, the `- [ ] **Phase N: …**` checklist, a single shared progress table (`| Phase | Milestone | Plans | Status | Completed |`), and the milestone phase-range string ("Phases 14-22") — which appears in **both** a `## Milestones` bullet **and** the milestone block (a `<details><summary>` line for shipped milestones, the `### ` heading for the active one).

ROADMAP has **no central writer**. Five functions each edit those prose surfaces with their own regexes:

| Function | Location | Edits |
|---|---|---|
| `cmdPhaseAdd` | `phase.cjs:311` | dir + detail block only |
| `cmdPhaseInsert` | `phase.cjs:367` | dir + decimal detail block only |
| `cmdPhaseRemove` | `phase.cjs:448` | detail + checkbox + table row; on-disk dir/file renames (`:488-600`); 99→down global renumber sweep (`:622-664`); body-only STATE count (`:668-687`) |
| `cmdPhaseComplete` | `phase.cjs:701` | checkbox + table row (Bug-3 anchor, `:726-758`) + STATE status |
| `cmdRoadmapUpdatePlanProgress` | `roadmap.cjs:221` | table row + detail plan count + checkbox |

Real-world reference (`road-runner/.planning/ROADMAP.md`, 22 phases / 4 milestones): two coexisting checklist dialects — non-bold completed (`- [x] Phase 1:`) and bold active (`- [x] **Phase 14:**`); decimal inserted phases (12.1, 17.1, 20.1); a 5-column progress table with genuinely malformed rows (mixed 4-/5-column); and two milestone range strings (the `## Milestones` bullet *and* the `<summary>`) that **no code keeps in sync** — they happen to agree today (`Phases 14-22` in both), so drift is latent, not yet observed. (A third, *plan-level* checklist dialect `- [x] NN-01:` lives inside active-milestone `### Phase N:` detail blocks per `templates/roadmap.md`, but road-runner's milestones are all shipped and their detail blocks archived out, so it is absent from *this* file.) The fork test suite is currently green (535/535).

## Problem

**Root cause:** the same facts are duplicated across loosely-formatted prose surfaces, each edited by independent regex. Every format variant spawns another patch — the entire Bug 1–8 sequence traces here. Concretely:

1. **`add-phase` under-writes (the originating "Bug 8").** `cmdPhaseAdd` writes only the directory + detail block. The checklist row, table row, milestone range, and STATE count are written by **nobody** — the workflow assigns the agent only a "Roadmap Evolution" note. Every other surface was fixed by hand.
2. **Sibling defects.** `cmdPhaseInsert` has the identical under-write (decimal phases' checklist/table rows were all added by hand). `cmdPhaseRemove` decrements only the STATE body line, not the frontmatter count — so `add` (once fixed) and `remove` are asymmetric.
3. **Range drift (latent).** No code maintains the milestone range; it lives in ≥2 places (the `## Milestones` bullet and the `<summary>`) with no synchronizing writer, so the two copies diverge on the next hand-edit. (Not yet observed drifting in the reference file — the risk is structural, not a logged incident.)
4. **Invisible divergence.** The structural check (`roadmap.cjs:203`) flags only *checklisted-without-detail*, never *detail-without-checklist* — the exact inconsistency `add` creates.
5. **Structural fragility.** Fixes are scattered regex; each new format quirk (bold vs non-bold, 4- vs 5-column, decimals, two range forms) requires another patch.

**Net effect:** the STATE frontmatter and the ROADMAP index drift from reality. The milestone **audit** reads `completed_phases`/`phase_count` (`audit-milestone.md:18`) and is misled. (Note: *premature close* itself is guarded by per-phase `disk_status === 'complete'` at `complete-milestone.md:48` — an unplanned new phase is not disk-complete — so the accurate severity is **inconsistency the audit trusts**, not silent auto-close.)

## Solution

### Overview

Apply STATE's proven pattern to ROADMAP. Wrap each editable ROADMAP surface in greppable, render-invisible HTML-comment **region markers**, and route all five phase-editing functions through a single **`roadmap-writer.cjs`** module that locates and edits those marked regions instead of guessing prose anchors. Markers are **authored** by the templates and the milestone-close workflow (never heuristically inferred), and writers **require** them — erroring with a migration hint if absent. A one-shot, supervised migration installs markers into existing roadmaps. STATE gains a signed `deltaPhases` on its existing choke-point — and `add`/`insert`, which write no STATE today, gain a single carry-forward STATE write that carries it; `percent` is left untouched.

### 1. Marker spec

A ROADMAP renders **shipped** and **active** milestones with **different shapes**, and the markers must fit both. The writers act on the **active** milestone, so its shape governs the design.

**Shipped milestone** — a collapsed `<details>` whose `<summary>` carries the range, wrapping a one-line-per-phase checklist. `complete-milestone` archives the full `### Phase N:` blocks out, so a shipped milestone has **none**:

```markdown
<!-- gsd:milestone v4.0 -->
<details>
<summary>✅ v4.0 Production Hybrid Search (<!-- gsd:range v4.0 -->Phases 14-22<!-- /gsd:range -->) — SHIPPED 2026-06-30</summary>
<!-- gsd:checklist v4.0 -->
- [x] **Phase 14: …**
- [x] **Phase 22: …**
<!-- /gsd:checklist v4.0 -->
</details>
<!-- /gsd:milestone v4.0 -->
```

**Active milestone** — a **bare `###` heading** (no `<details>`, no `<summary>`) that itself carries the range, then a **bold, unchecked** checklist, then the full `### Phase N:` detail blocks — **all inside `## Phases`**. There is **no separate `## Phase Details` section** (that exists only in the v1.0 greenfield template, never in a milestone-grouped roadmap):

```markdown
<!-- gsd:milestone v5.0 -->
### ▶ v5.0 Finance Metrics L2 Redesign (<!-- gsd:range v5.0 -->Phases 23-29<!-- /gsd:range -->) — ACTIVE
<!-- gsd:checklist v5.0 -->
- [ ] **Phase 23: …**
- [ ] **Phase 29: …**
<!-- /gsd:checklist v5.0 -->

<!-- gsd:detail 23 -->
### Phase 23: …
**Goal**: …
**Depends on**: Phase 22
**Plans**: TBD
<!-- /gsd:detail 23 -->
<!-- … one gsd:detail fence per active-milestone phase … -->
<!-- /gsd:milestone v5.0 -->
```

The **range** appears **twice** per milestone — in the `## Milestones` bullet **and** in either the `<summary>` (shipped) or the `### ` heading (active); `setMilestoneRange` updates **all** occurrences, so they can never drift. `addIntegerPhase` adds an **unchecked** `- [ ] **Phase N: …**` row (active milestones are in progress), a `gsd:detail N` block, and a table row.

**Locating the active milestone (the core new parsing logic §Scope calls out):** the writers act on the milestone named by the `{milestone}` arg (§2). The module finds that milestone's `gsd:milestone vX.Y` fence and edits the `gsd:checklist` / `gsd:detail` / `gsd:range` regions **within** it — a new checklist row at the end of `gsd:checklist`, a new `gsd:detail N` block just before the `<!-- /gsd:milestone -->` close, the table row inside `gsd:table`. The fences ARE the boundaries; no prose-anchor guessing (D1).

**Marker-placement rule (load-bearing — must be enforced by the §Verification regression test; "verified" below means *to be asserted by that test*, not yet proven):**
- **No marker may ever sit on a progress-table row.** The two table-row regexes (`roadmap.cjs:261`, `phase.cjs:740`) are anchored to end-of-line *after the final `|`* (`…\|[ \t]*\r?$`); an inline per-row comment breaks the match. The `gsd:table` fence wraps the whole `## Progress` block at its outer boundary — never per row.
- **The active-milestone range fence must sit *inside the parens*.** `getMilestoneInfo` (`core.cjs` heading branch, ~427) extracts the milestone **name** from the `### ▶ vX.Y …` line by capturing **up to the first `(`** — so `(<!-- gsd:range -->Phases A-B<!-- /gsd:range -->)` is safe, but a fence between the name and the `(` would be swallowed into the name. (Shipped milestones are exempt: `getMilestoneInfo` strips `<details>` *before* parsing, so the in-`<summary>` fence can't reach a name. Road-runner's active milestone uses `▶`, which the bold-bullet `inProgressMatch` does not match — so the heading branch is what runs, making this constraint load-bearing.)
- **Otherwise**, fences sit on their own lines or *after* the closing `**` of a bold checklist span; none of `getMilestoneInfo` (`core.cjs` ~401), `getMilestonePhaseFilter` (`core.cjs` ~454, which matches `### Phase N:` headings — `gsd:detail` fences are on their own line, so unaffected), or the checklist pattern (`roadmap.cjs:196`) read the fenced range text.

### 2. `roadmap-writer.cjs` module

Pure `content → content'` string transforms (no I/O), one test suite. Each primitive locates its target by the §1 fences — `gsd:detail N` for a phase's detail block, `gsd:checklist` rows, `gsd:table` rows, `gsd:range` for the range — never by prose anchors. All five commands become thin: `read → validateMarkers → module ops → single write`.

- `ensureMarkers(content)` — **validator + one-shot migration only** (not a per-write heuristic): if markers present, validate/repair; if absent, used solely by the explicit migration path.
- `addIntegerPhase(content, {milestone, number, name})` — detail + checklist row + table row.
- `insertDecimalPhase(content, {afterPhase, number, name})` — decimal detail + checklist row + table row (no count change).
- `removePhase(content, {number, isDecimal})` — removes the fenced surfaces; see §6 for the parts that stay outside the module.
- `setPhaseProgress(content, {number, status, plansDone, plansTotal, date})` — checkbox + table cells + the `### Phase N:` block's `**Plans:** N plans` line. The two current callers write **different** table tails — `complete` rewrites Status+Completed (`Complete` + date, `phase.cjs:745`), `update-plan-progress` rewrites Plans+Status+Completed (`m/n` + `padEnd(11)` status + conditional date, `roadmap.cjs:267`) — so the primitive is **parameterized to reproduce each shape by args**, not one unified output (shared logic retires the duplicated Bug-3 anchor).
- `setMilestoneRange(content, {milestone, hi})` — updates all range markers for the milestone.

### 3. Authored markers + require/validate

Markers are emitted at every generation point — `templates/roadmap.md` (the initial `## Phases` checklist + `### Phase Details`), the `complete-milestone.md:323` reorg block, and the new-project/new-milestone roadmapper guidance. These are concrete, editable template blocks, so emission is reliable. Writers call `validateMarkers(content)` first and **hard-error** (`"run gsd-tools roadmap ensure-markers"`) when markers are absent — no silent auto-heal on write.

### 4. One-shot supervised migration

`gsd-tools roadmap ensure-markers [--dry-run]` installs markers into an existing (legacy) roadmap by detecting today's sections **once**, under operator review of the diff. Folded into `gsd:health` as a check. Run once per controlled project before its next phase op.

### 5. STATE: `deltaPhases` + percent untouched

- **`add`/`insert` gain a STATE write they don't make today.** Verified: `writeStateMd` is called only by `cmdPhaseRemove` (`phase.cjs:686`) and `cmdPhaseComplete` (`phase.cjs:894`, `{recomputeStatus:true}`); `cmdPhaseAdd`/`cmdPhaseInsert` (`:311`/`:367`) write no STATE at all. Each gains **one** `writeStateMd(…, { deltaPhases })` call passing **neither `recomputeProgress` nor `recomputeStatus`** — so `status` carries forward verbatim (not re-derived), which is what the §Verification "`status` untouched" row depends on.
- Add a signed `deltaPhases` to `writeStateMd`/`buildStateFrontmatter`, applied **only** on the carry-forward branch (`buildStateFrontmatter` `state.cjs:699`, `existingProgress` non-null): `add` `+1`, `insert` `0`, `remove` `−1`. `completed_phases` is untouched.
- **`percent` is not modified.** It is plan-based (`summaries/plans`) in all three computations (`state.cjs:344`, `roadmap.cjs:212`, `commands.cjs:416`); adding an unplanned (0-plan) phase doesn't change it, and milestone-close is guarded by `disk_status`, not percent.

### 6. `remove` specifics

`removePhase` deletes the removed phase's own fenced surfaces (its `gsd:checklist` row, `gsd:table` row, `gsd:detail N` block). The harder part is the **renumber of every surviving higher phase**, which the current 99→down sweep (`phase.cjs:622-664`) does across **five** content surfaces: phase headings, checklist rows, plan-refs (`NN-01`), table rows (`| N.`), and `**Depends on:** Phase N`. Three of those — headings, checklist rows, table rows — are now **inside fences**, and critically the **`gsd:detail N` fence number is NOT a content surface the sweep touches** (the marker reads `gsd:detail 18`, not `Phase 18`). So an integer remove must renumber **content and its enclosing marker in lockstep**: when `### Phase 18:` becomes `### Phase 17:`, its `<!-- gsd:detail 18 -->`/`<!-- /gsd:detail 18 -->` fence must become `17` too, or every surviving fence desyncs from its block by one.

So the module owns the renumber of all fenced surfaces **including their `gsd:detail N` marker numbers**; the retained, **tightened** out-of-fence sweep handles only `**Depends on:** Phase N` and prose plan-refs (`NN-01`) that live in detail prose (replacing the current global 99→down sweep). On-disk directory/file renames (`phase.cjs:488-600`) are retained verbatim — orthogonal to ROADMAP text.

### 7. Inverse structural check

Add the mirror of `missing_phase_details` — phases that have a detail block but no checklist row — surfaced in the `roadmap analyze` result. **Source the checklist membership from the `gsd:checklist` fences, not the existing bold-only regex** (`roadmap.cjs:196` matches `**Phase` only). Shipped milestones use a non-bold dialect, and their phase dirs may still be on disk (so they appear in the detail-phase set), so a bold-only membership set would false-positive **every shipped non-bold phase** as "missing its checklist." Reading the fenced checklist rows (all dialects) makes the check dialect-proof — which is the whole point of marking the surface.

## Design Decisions

### D1: Markers + one writer module, mirroring STATE

**Choice:** Greppable region markers + a single `roadmap-writer.cjs` all five functions route through.

**Why:** STATE's single choke-point eliminated its bug class; ROADMAP is the unsolved analog (five independent regex writers). Markers make surface location O(1) and format-variance-proof (we own what's inside the fence).

**Alternatives rejected:** *Full render-from-model* (a `roadmap.json` source of truth that regenerates all prose) — fights GSD upstream's own direct-`.md` writers (`complete-milestone` deletes/recreates the file) on every fork re-sync; high blast radius. *Hardened patch* (byte-range-scoped regex, no markers) — stays in the parse-fragile-prose paradigm; the next format quirk is another patch.

### D2: Markers authored, not inferred; writers require/validate (no auto-heal)

**Choice:** Templates + `complete-milestone` emit markers; writers validate-and-error if absent; `ensureMarkers` is a validator + one-shot migration, never a per-write heuristic.

**Why:** Auto-detection is unreliable — in an active-milestone ROADMAP the bold/non-bold-`Phase` signal cannot separate a `## Phases` milestone-checklist row (`- [ ] **Phase 5:**`) from a completed milestone's non-bold row (`- [x] Phase 1:`) or from a plan-level checkbox inside a `### Phase N:` detail block (`- [ ] 05-01:`, per `templates/roadmap.md`); detection would have to rebuild the milestone-vs-detail tree (the very parsing markers exist to avoid). And the ROADMAP is LLM-authored and **rewritten at milestone boundaries** (`complete-milestone.md:323`), so auto-heal-on-every-write would weaponize any detection miss into per-command corruption + churny diffs.

**Alternatives rejected:** Auto-heal-on-write (heuristic detection at the top of every writer).

### D3: Hard-require markers (error if absent)

**Choice:** Writers error with a migration hint when markers are missing.

**Why:** A single clean code path (the fragile regex path is fully retired). Migration is a cheap one-time supervised pass across the ~4 controlled projects.

**Alternatives rejected:** Legacy-regex fallback + warning during a transition — keeps two code paths and the fragile one alive until every project migrates.

### D4: Leave `percent` untouched

**Choice:** Do not modify `percent` anywhere; only bump `total_phases` via `deltaPhases`.

**Why:** `percent` is plan-based in all three computations; an unplanned (0-plan) phase doesn't change it, so it stays correct. Premature-close is guarded by per-phase `disk_status` (`complete-milestone.md:48`), and the audit's `completed < total` view is corrected by the `total_phases` bump.

**Alternatives rejected:** Unify all percent to phase-based (`completed/total`) — a three-site breaking change that would make `/gsd:progress` and `state json` disagree, and churn the value on every `update-progress`.

### D5: `deltaPhases` strict carry-forward; **skip** (don't assert) on recompute

**Choice:** Apply the signed delta only on the carry-forward branch (`existingProgress` non-null, `state.cjs:699`). On the recompute branch — `recomputeProgress === true || existingProgress === null` (`state.cjs:669`) — **ignore `deltaPhases`**; do **not** error.

**Why:** The phase directory is created (`mkdirSync`) *before* the new STATE write (`phase.cjs:339`/`:411`). On a recompute the disk recount (`state.cjs:671`) already counts the new dir, so a delta on top would double-count — hence carry-forward-only. But `recomputeProgress` is forced whenever `existingProgress === null` — e.g. the **first `phase add` on a fresh roadmap**, a legitimate operation — so an *assert*-`false` would **throw exactly there**. The delta must therefore be *skipped*, not asserted: on recompute the disk recount is authoritative; on carry-forward the delta is. (Residual obligation, §Open Items: confirm the dir filter actually counts the just-created 0-plan dir on the recompute path.)

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
- **Realistic test fixture** — deliberately adversarial (a superset of any single real file): all 3 checklist dialects (incl. the plan-level `- [x] NN-01:` road-runner currently lacks, for worst-case coverage), collapsed + open `<details>`, decimals, a malformed 5-col row, two range strings, `Depends on` lines + an `ensureMarkers` idempotency fixed-point test.

### What does NOT get built

- **Full render-from-model** — rejected (D1).
- **Percent unification / phase-based percent** — rejected (D4).
- **Auto-heal-on-write** — rejected (D2).
- **Fixing pre-existing test failures** — the 8 prior failures were resolved separately; suite is green.
- **Markers in archived `milestones/*.md`** — they are frozen byte-snapshots (`milestone.cjs:139`); correctly left alone.
- **Migrating external / non-controlled GSD installs** — only the ~4 controlled projects are migrated.

## Open Items

All design decisions are resolved (D1–D6). The items below are **verification obligations**, not unresolved decisions:
- **D5 recompute path:** confirm `buildStateFrontmatter`'s milestone dir filter counts the just-created 0-plan phase dir on the recompute branch, so "skip delta on recompute" still yields `total_phases = N+1` (not short by one) on a fresh project's first `add`.
- Confirm the **split** renumber (§6) has no gaps vs the old 99→down sweep: the module renumbers the fenced surfaces (headings, checklist rows, table `| N.`) **and their `gsd:detail N` markers** in lockstep, and the out-of-fence scoped sweep covers `**Depends on:** Phase N` + prose plan-refs (`NN-01`).
- Confirm the marker fences pass every existing reader regex (regression test, §1 marker-placement rule).

## Verification

- **add-phase** on a marked, milestone-complete fixture → adds checklist row + table row + detail block; bumps the range in **all** occurrences; STATE `total_phases +1`, `completed_phases` unchanged, `status` untouched; `total_phases` is `N+1`, **not** inflated by decimal phases.
- **insert-phase** → decimal checklist + table + detail; STATE counts unchanged.
- **remove-phase** → removed phase's fenced surfaces gone; **every surviving higher phase renumbered in content AND marker** (each `<!-- gsd:detail N -->` still wraps `### Phase N:` with matching N — no off-by-one desync); on-disk dir/file renames intact; out-of-fence `Depends on`/plan-refs renumbered; frontmatter `total_phases −1` (symmetric with add).
- **complete** → `setPhaseProgress(…, {status:'Complete', …})` reproduces `cmdPhaseComplete`'s current bytes exactly (trailing Status+Completed cells).
- **update-plan-progress** → `setPhaseProgress` in the in-progress case reproduces `cmdRoadmapUpdatePlanProgress`'s current bytes exactly (Plans + `padEnd(11)` Status + conditional date). One primitive, byte-identical **per caller** (no regression).
- **Markers** → `ensureMarkers(ensureMarkers(x)) === ensureMarkers(x)` on the realistic fixture (incl. malformed rows + mixed dialects); a writer on an unmarked file errors with the migration hint; marked content still matches every existing reader regex.
- **Inverse check** → a detail block with no checklist row appears in `missing_phase_checklist`.
- **Percent** → unchanged across the suite; milestone-close remains blocked by `disk_status` when an unplanned phase is present.
- **Generation (authored markers)** → `new-project`, `new-milestone`, and the `complete-milestone` reorg each produce a ROADMAP that `validateMarkers` accepts (markers present and well-formed at every generation point) — closing the loop so the require-markers writers never hit a freshly generated, unmarked file.
- **Workflow** → `add-phase.md` no longer instructs the agent to edit counts or index surfaces (now CLI-owned), and the status-reopen decision is surfaced to the operator rather than silently skipped.
- **Suite** → stays green (≥535 passing) with the new tests added.
