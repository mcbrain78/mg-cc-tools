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

Real-world reference (`road-runner/.planning/ROADMAP.md` — as of this writing 29 phases / 5 milestones: v1.0–v4.0 shipped, **v5.0 active** at Phases 23-29; an earlier snapshot, which this spec originally described, had v4.0 active at 22 phases): two coexisting checklist dialects — non-bold (`- [x] Phase 1:`, the older shipped milestones v1.0–v3.0) and bold (`- [x] **Phase 23:**`, used by **both** shipped v4.0 *and* active v5.0). The dialect does **not** track completion status — v4.0 is shipped yet bold — which is exactly why bold/non-bold can't be used to infer state (D2). Decimal inserted phases (12.1, 17.1, 20.1). The progress table is **uniformly 5-column**; its real defects are *cell-content, not column-count* — shifted rows (10, 11, 12.1 carry `Complete` in the **Plans** column and the date in the **Status** column), mixed Status-cell whitespace (`Complete` from `complete` vs `Complete   ` `padEnd(11)` from `update-plan-progress`), and `0/?` plan placeholders for not-started phases. The active milestone's range appears in **three** un-synced places — the `## Milestones` bullet, the `### ▶` heading, **and woven into the `## Progress` "Execution Order" prose** (all `Phases 23-29`); the two structural copies agree today so drift is latent, but the prose copy lives in free narrative no marker can bound (§1). (The *plan-level* dialect `- [x] NN-01:` from `templates/roadmap.md` is absent here — shipped detail blocks are archived out and active v5.0 phases have no plans yet.) The fork test suite is **reported** green (535/535) — an external fact about the canonical fork, not verifiable from an installed copy.

## Problem

**Root cause:** the same facts are duplicated across loosely-formatted prose surfaces, each edited by independent regex. Every format variant spawns another patch — the entire Bug 1–8 sequence traces here. Concretely:

1. **`add-phase` under-writes (the originating "Bug 8").** `cmdPhaseAdd` writes only the directory + detail block. The checklist row, table row, milestone range, and STATE count are written by **nobody** — the workflow assigns the agent only a "Roadmap Evolution" note. Every other surface was fixed by hand.
2. **Sibling defects.** `cmdPhaseInsert` has the identical under-write (decimal phases' checklist/table rows were all added by hand). `cmdPhaseRemove` decrements only the STATE body line, not the frontmatter count — so `add` (once fixed) and `remove` are asymmetric.
3. **Range drift (latent).** No code maintains the milestone range. For the active milestone it lives in **three** places — the `## Milestones` bullet, the `### ▶` heading, and the `## Progress` "Execution Order" prose — with no synchronizing writer, so they diverge on the next hand-edit. (Not yet observed drifting in the reference file — the risk is structural, not a logged incident. §1 puts the two structural copies under one writer and *flags* the prose copy rather than silently syncing it.)
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

The **range** appears in **two structural surfaces** per milestone — the `## Milestones` bullet **and** either the `<summary>` (shipped) or the `### ` heading (active) — plus, for the active milestone, a **third copy woven into the `## Progress` "Execution Order" prose** (`**v5.0 (Phases 23-29)** continues at Phase 23…`). `setMilestoneRange` updates the **two structural surfaces** (both are stable, fence-able), so those can never drift. The **Execution-Order prose copy is explicitly out of marker scope**: it is free LLM narrative no fence can reliably bound, and regex-replacing a range token inside a sentence is the prose-anchor fragility this design exists to retire. Instead, `roadmap analyze` (§7) **warns** when an active-milestone `Phases N-M` token appears outside a `gsd:range` fence — surfacing the un-synced copy for a human rather than pretending to maintain it. `addIntegerPhase` adds an **unchecked** `- [ ] **Phase N: …**` row (active milestones are in progress), a `gsd:detail N` block, and a table row.

**Locating the active milestone (the core new parsing logic §Scope calls out):** the writers act on the milestone named by the `{milestone}` arg (§2). The module finds that milestone's `gsd:milestone vX.Y` fence and edits the `gsd:checklist` / `gsd:detail` / `gsd:range` regions **within** it — a new checklist row at the end of `gsd:checklist`, a new `gsd:detail N` block just before the `<!-- /gsd:milestone -->` close, and the matching table row located by its `| N.` anchor **within** the `gsd:table` block. The fences bound the search region (no whole-file prose-anchor guessing); inside `gsd:table` the existing row anchor still does the per-row addressing (D1).

**Marker-placement rule (load-bearing — must be enforced by the §Verification regression test; "verified" below means *to be asserted by that test*, not yet proven):**
- **No marker may ever sit on a progress-table row.** The two table-row regexes (`roadmap.cjs:261`, `phase.cjs:740`) are anchored to end-of-line *after the final `|`* (`…\|[ \t]*\r?$`); an inline per-row comment breaks the match. The `gsd:table` fence wraps the whole `## Progress` block at its outer boundary — never per row.
- **The active-milestone range fence must sit *inside the parens*.** `getMilestoneInfo` (`core.cjs` heading branch, ~427) extracts the milestone **name** from the `### ▶ vX.Y …` line by capturing **up to the first `(`** — so `(<!-- gsd:range -->Phases A-B<!-- /gsd:range -->)` is safe, but a fence between the name and the `(` would be swallowed into the name. (Shipped milestones are exempt: `getMilestoneInfo` strips `<details>` *before* parsing, so the in-`<summary>` fence can't reach a name. Road-runner's active milestone uses `▶`, which the bold-bullet `inProgressMatch` does not match — so the heading branch is what runs, making this constraint load-bearing.)
- **Otherwise**, fences sit on their own lines or *after* the closing `**` of a bold checklist span; none of `getMilestoneInfo` (`core.cjs` ~401), `getMilestonePhaseFilter` (`core.cjs` ~454, which matches `### Phase N:` headings — `gsd:detail` fences are on their own line, so unaffected), or the checklist pattern (`roadmap.cjs:196`) read the fenced range text.

### 2. `roadmap-writer.cjs` module

Pure `content → content'` string transforms (no I/O), one test suite. Each primitive locates its target **region** by the §1 fences — `gsd:detail N` for a phase's detail block, the `gsd:checklist` block, the `## Progress` table inside the `gsd:table` block, `gsd:range` for the range. The fence bounds the region; row-level location *inside* `gsd:checklist`/`gsd:table` still matches a per-row anchor (a checklist row by its `Phase N` text; a table row by the Bug-3 end-of-line `| N.` anchor — which **cannot** itself be a fence, per §1) — but now scoped to the bounded block instead of scanning the whole file for a prose anchor. All five commands become thin: `read → validateMarkers → module ops → single write`.

- `ensureMarkers(content)` — **validator + one-shot migration only** (not a per-write heuristic): if markers present, validate/repair; if absent, used solely by the explicit migration path.
- `addIntegerPhase(content, {milestone, number, name})` — detail + checklist row + table row.
- `insertDecimalPhase(content, {afterPhase, number, name})` — decimal detail + checklist row + table row (no count change).
- `removePhase(content, {number, isDecimal})` — removes the fenced surfaces; see §6 for the parts that stay outside the module.
- `setPhaseProgress(content, {number, status, plansDone, plansTotal, date})` — checkbox + table cells + the `### Phase N:` block's `**Plans:** N plans` line. The two current callers write **different** table tails — `complete` rewrites Status+Completed (`Complete` + date, `phase.cjs:745`), `update-plan-progress` rewrites Plans+Status+Completed (`m/n` + `padEnd(11)` status + conditional date, `roadmap.cjs:267`) — so the primitive is **parameterized to reproduce each shape by args**, not one unified output. This **unifies** the two callers' currently-duplicated Bug-3 row anchor into one place — the anchor itself is **retained** (it is still how a table row is found inside the `gsd:table` block, since no marker may sit on a table row per §1), just no longer copy-pasted across two call sites.
- `setMilestoneRange(content, {milestone, hi})` — updates the milestone's `gsd:range` markers (the two structural surfaces; the un-fenced Execution-Order prose copy is out of scope, flagged by `analyze` per §1/§7).

### 3. Authored markers + require/validate

Markers are emitted at every generation point — `templates/roadmap.md` (the initial `## Phases` checklist + `### Phase Details`), the `complete-milestone.md:323` reorg block, and the new-project/new-milestone roadmapper guidance. These are concrete, editable template blocks, so emission is reliable. Writers call `validateMarkers(content)` first and **hard-error** (`"run gsd-tools roadmap ensure-markers"`) when markers are absent — no silent auto-heal on write.

### 4. One-shot supervised migration

`gsd-tools roadmap ensure-markers [--dry-run]` installs markers into an existing (legacy) roadmap by detecting today's sections **once**, under operator review of the diff. Folded into `gsd:health` as a check. Run once per controlled project before its next phase op.

### 5. STATE: `deltaPhases` + percent untouched

- **`add`/`insert` gain a STATE write they don't make today.** Verified: `writeStateMd` is called only by `cmdPhaseRemove` (`phase.cjs:686`) and `cmdPhaseComplete` (`phase.cjs:894`, `{recomputeStatus:true}`); `cmdPhaseAdd`/`cmdPhaseInsert` (`:311`/`:367`) write no STATE at all. Each gains **one** `writeStateMd(…, { deltaPhases })` call passing **neither `recomputeProgress` nor `recomputeStatus`** — so `status` carries forward verbatim (not re-derived), which is what the §Verification "`status` untouched" row depends on.
- Add a signed `deltaPhases` to `writeStateMd`/`buildStateFrontmatter`, applied **only** on the carry-forward branch (`buildStateFrontmatter` `state.cjs:699`, `existingProgress` non-null): `add` `+1`, `insert` `0`, `remove` `−1`. `completed_phases` is untouched.
- **Ordering invariant (load-bearing — not a thing to discover during implementation).** The ROADMAP `### Phase N:` heading **and** the phase directory are written **before** the `deltaPhases` STATE write. On the recompute branch — forced when `existingProgress === null`, i.e. the *first* `add` on a fresh roadmap — the delta is *skipped* (D5) and `buildStateFrontmatter` recounts from disk **and** from the ROADMAP-derived phase set (`getMilestonePhaseFilter`, which counts `### Phase N:` headings); both must already include the new phase for the recount to land on `N+1`. So heading/dir-before-STATE is a **contract**: an implementer who writes STATE first would silently get `N` on the first add. This is the resolution of the former "Open Item," restated as the invariant the test locks.
- **`percent` is not modified.** It is plan-based (`summaries/plans`) in all three computations (`state.cjs:344`, `roadmap.cjs:212`, `commands.cjs:416`); adding an unplanned (0-plan) phase doesn't change it, and milestone-close is guarded by `disk_status`, not percent.

### 6. `remove` specifics

`removePhase` deletes the removed phase's own fenced surfaces (its `gsd:checklist` row, `gsd:table` row, `gsd:detail N` block). The harder part is the **renumber of every surviving higher phase**, which the current 99→down sweep (`phase.cjs:622-664`) does across **five** content surfaces: phase headings, checklist rows, plan-refs (`NN-01`), table rows (`| N.`), and `**Depends on:** Phase N`. Three of those — headings, checklist rows, table rows — are now **inside fences**, and critically the **`gsd:detail N` fence number is NOT a content surface the sweep touches** (the marker reads `gsd:detail 18`, not `Phase 18`). So an integer remove must renumber **content and its enclosing marker in lockstep**: when `### Phase 18:` becomes `### Phase 17:`, its `<!-- gsd:detail 18 -->`/`<!-- /gsd:detail 18 -->` fence must become `17` too, or every surviving fence desyncs from its block by one.

So the renumber must partition across **every** `Phase N` surface, each explicitly assigned — today's global 99→down sweep is *number*-based and catches them all blindly, so the split must not silently drop any:

- **Fenced (module-owned):** `### Phase N:` headings, `gsd:checklist` rows, `gsd:table` `| N.` rows — **and each block's enclosing `gsd:detail N` marker number, renumbered in lockstep** with its heading (the marker is not a `Phase N` token, so the old sweep never touched it — this is the new desync failure mode §Open Items guards against).
- **Out-of-fence prose (scoped sweep, retained behavior):** `**Depends on:** Phase N`, prose plan-refs (`NN-01`), **and** general `Phase N` mentions in free narrative — notably the `## Progress` "Execution Order" paragraph, which names individual phases ("continues at Phase 23", "Track A (23→28)"). Dropping this last class would be a **regression**: `remove` only renumbers phases *above* the removed one, and those higher phases are exactly the active-milestone phases the Execution-Order prose discusses. The sweep therefore **keeps** the existing number-based `(Phase\s+)N` rewrite for this class (bare-number forms like `23→28` stay out of reach — same as today, not a new gap).

The two passes must not double-rewrite a fenced surface the module already renumbered; the contract is *every higher phase's number changes exactly once in content, and its `gsd:detail` marker tracks it* (the algorithm — scope the prose sweep to out-of-fence regions, or sweep the whole document then reconcile marker numbers — is the implementer's call). On-disk directory/file renames (`phase.cjs:488-600`) are retained verbatim — orthogonal to ROADMAP text.

### 7. Inverse structural check

Add the mirror of `missing_phase_details` — phases that have a detail block but no checklist row — surfaced in the `roadmap analyze` result. **Source the checklist membership from the `gsd:checklist` fences, not the existing bold-only regex** (`roadmap.cjs:196` matches `**Phase` only). Shipped milestones use a non-bold dialect, and their phase dirs may still be on disk (so they appear in the detail-phase set), so a bold-only membership set would false-positive **every shipped non-bold phase** as "missing its checklist." Reading the fenced checklist rows (all dialects) makes the check dialect-proof — which is the whole point of marking the surface. The same `analyze` pass also **warns when an active-milestone `Phases N-M` range token appears outside a `gsd:range` fence** (the Execution-Order prose copy, §1) — the design cannot auto-sync free prose, but it can flag the un-synced copy for a human instead of letting it drift silently.

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

**Why:** The phase directory is created (`mkdirSync`) *before* the new STATE write (`phase.cjs:339` add / `:410` insert). On a recompute the disk recount (`state.cjs:671`) already counts the new dir, so a delta on top would double-count — hence carry-forward-only. But `recomputeProgress` is forced whenever `existingProgress === null` — e.g. the **first `phase add` on a fresh roadmap**, a legitimate operation — so an *assert*-`false` would **throw exactly there**. The delta must therefore be *skipped*, not asserted: on recompute the disk recount is authoritative; on carry-forward the delta is. (That fresh-roadmap recount lands on `N+1` only under the §5 **ordering invariant** — heading/dir written before the STATE write; §Open Items carries the regression test that locks it.)

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
- **Inverse structural check** (`missing_phase_checklist`) in `roadmap.cjs` + an **out-of-fence range-drift warning** in the same `analyze` pass (§7).
- **`add-phase.md` workflow update** — drop the manual count/index toil (now CLI-owned); keep the Roadmap-Evolution note; explicitly surface the status-reopen decision to the operator.
- **Realistic test fixture** — deliberately adversarial (a superset of any single real file): all 3 checklist dialects (incl. the plan-level `- [x] NN-01:` road-runner currently lacks, for worst-case coverage), collapsed + open `<details>`, decimals, the real cell-content table defects (a shifted `Complete`-in-Plans row + mixed `padEnd(11)`/plain Status whitespace + a `0/?` placeholder — **not** a mixed-column row, which doesn't occur), all **three** active-range copies incl. an Execution-Order prose mention, `Depends on` lines + an `ensureMarkers` idempotency fixed-point test.

### What does NOT get built

- **Full render-from-model** — rejected (D1).
- **Percent unification / phase-based percent** — rejected (D4).
- **Auto-heal-on-write** — rejected (D2).
- **Fixing pre-existing test failures** — the 8 prior failures were resolved separately; suite is green.
- **Markers in archived `milestones/*.md`** — they are frozen byte-snapshots (`milestone.cjs:139`); correctly left alone.
- **Migrating external / non-controlled GSD installs** — only the ~4 controlled projects are migrated.

## Open Items

All design decisions are resolved (D1–D6). The items below are **verification obligations**, not unresolved decisions:
- **D5 recompute path (resolved → §5 ordering invariant).** The resolution is the heading/dir-before-STATE ordering contract now stated in §5, not an open question. Residual: a regression test asserting a fresh-roadmap first `add` (which forces the recompute branch) yields `total_phases = N+1`, locking the ordering so a future reorder can't silently regress it to `N`.
- **Split renumber partition (resolved → §6 enumeration).** The partition is now enumerated in §6 — fenced surfaces + their `gsd:detail` markers via the module; `**Depends on:** Phase N`, plan-refs, **and** general prose `Phase N` mentions (incl. Execution-Order) via the retained scoped sweep. Residual: a regression test that removes a mid-active-milestone phase and asserts **no** `Phase N` surface — including the Execution-Order prose — is left at a stale number, and every `gsd:detail` marker still matches its heading.
- Confirm the marker fences pass every existing reader regex (regression test, §1 marker-placement rule).

## Verification

- **add-phase** on a marked, milestone-complete fixture → adds checklist row + table row + detail block; bumps the range in **both structural occurrences** (bullet + heading/summary), and `analyze` **warns** if an Execution-Order prose range copy is left stale; STATE `total_phases +1`, `completed_phases` unchanged, `status` untouched; `total_phases` is `N+1`, **not** inflated by decimal phases.
- **insert-phase** → decimal checklist + table + detail; STATE counts unchanged.
- **remove-phase** → removed phase's fenced surfaces gone; **every surviving higher phase renumbered in content AND marker** (each `<!-- gsd:detail N -->` still wraps `### Phase N:` with matching N — no off-by-one desync); on-disk dir/file renames intact; out-of-fence `Depends on`/plan-refs renumbered; frontmatter `total_phases −1` (symmetric with add).
- **complete** → `setPhaseProgress(…, {status:'Complete', …})` reproduces `cmdPhaseComplete`'s current bytes exactly (trailing Status+Completed cells).
- **update-plan-progress** → `setPhaseProgress` in the in-progress case reproduces `cmdRoadmapUpdatePlanProgress`'s current bytes exactly (Plans + `padEnd(11)` Status + conditional date). One primitive, byte-identical **per caller** (no regression).
- **Markers** → `ensureMarkers(ensureMarkers(x)) === ensureMarkers(x)` on the realistic fixture (incl. malformed rows + mixed dialects); a writer on an unmarked file errors with the migration hint; marked content still matches every existing reader regex.
- **Inverse check** → a detail block with no checklist row appears in `missing_phase_checklist`; and an active-milestone `Phases N-M` token outside any `gsd:range` fence raises the out-of-fence range-drift warning.
- **Percent** → unchanged across the suite; milestone-close remains blocked by `disk_status` when an unplanned phase is present.
- **Generation (authored markers)** → `new-project`, `new-milestone`, and the `complete-milestone` reorg each produce a ROADMAP that `validateMarkers` accepts (markers present and well-formed at every generation point) — closing the loop so the require-markers writers never hit a freshly generated, unmarked file.
- **Workflow** → `add-phase.md` no longer instructs the agent to edit counts or index surfaces (now CLI-owned), and the status-reopen decision is surfaced to the operator rather than silently skipped.
- **Suite** → stays green (≥535 passing) with the new tests added.
