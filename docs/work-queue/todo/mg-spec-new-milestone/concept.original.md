# mg:spec-create-milestone — Project a Frozen Spec into a GSD Milestone

## Situation

GSD offers two ways into structured work, at two granularities:

- **Milestone-level — `gsd:new-milestone`** (`.claude/get-shit-done/workflows/new-milestone.md`): top-down. Loads project context → optional 4-agent domain research (`gsd-project-researcher` × Stack/Features/Architecture/Pitfalls + synthesizer → `research/SUMMARY.md`) → per-category requirements elicitation → `gsd-roadmapper` derives phases. It is greenfield-shaped: it *discovers* what to build.
- **Phase-level — `mg:spec-create-context <phase> <doc>`** (`.claude/commands/mg/spec-create-context.md`): projects a source doc into a phase's `CONTEXT.md` as locked decisions, producing a file GSD already understands (no GSD patches). The phase must already exist in `ROADMAP.md`.

Separately, work here is often pre-specced: `mg:spec-draft` → `mg:spec-improve` produce a frozen, code-grounded concept at `docs/work-queue/todo/<slug>/concept.md` (with `D1..Dn` decisions + a sibling `concept-NON-GOALS.md`). Both v4.0 and v5.0 were seeded this way.

Reusable machinery is confirmed present:
- **`gsd-roadmapper`** (`.claude/agents/gsd-roadmapper.md`) reads `REQUIREMENTS.md` + `PROJECT.md`, treats `research/SUMMARY.md` as **optional**, enforces **100% requirement→phase coverage** (one phase per REQ), writes `ROADMAP.md` + `STATE.md`, and rewrites the REQUIREMENTS.md `## Traceability` table. It is spawned standalone today by both `new-project` and `new-milestone` — reusable unchanged.
- **`plan-phase --prd` (step 3.5)** is a working precedent: an external frozen doc → locked decisions (everything in the doc) → the rest of the pipeline runs normally, with uncovered areas flagged as "Claude's Discretion."

## Problem

When a milestone's job is to *implement an already-frozen, code-grounded spec* — a "fix observed issues" milestone, not a greenfield exploration — `gsd:new-milestone`'s top-down front-end is mismatched. Observed empirically on the **v5.0 run (2026-06-30)**: with the L2 concept in hand, `new-milestone` still ran full domain research and derived its own 22 requirements. The output came out faithful (it cited D-numbers, covered D1–D10, respected the NON-GOALS) — but only a hand audit established that, and three distinct failure modes showed up:

1. **Redundant discovery.** It re-ran domain research to *discover what to build* when the spec (post multiple `spec-improve` rounds + code citations) had already settled it — wasted effort/tokens, and it reframes settled decisions as open questions.
2. **Re-elicitation invites silent drift.** The per-category "scope each category" gate re-opens frozen decisions, so the requirements are the tool's *re-derivation*, not a faithful *projection*. Drift is silent: scope was **added** (a FINRA "SHORT" track absent from the concept leaked into the requirements), and a component count slipped ("48" vs ~50 mapped columns) — both caught only by manual audit.
3. **No faithfulness check.** Nothing verifies the requirements are a *complete + non-drifting* projection of the spec (every `Dx` → ≥1 REQ; every REQ → a `Dx` or an explicitly-flagged addition). On v5.0 this required a manual audit before the requirements could be trusted.

The correction is **not** "remove research." Context-aware research *earned its keep once*: it surfaced a real gap the concept omitted — the consumption view needs a `GRANT`, because `CREATE VIEW` doesn't inherit the renamed table's grants. The mismatch is specifically **blind discovery + elicitation**, not **verification**.

## Solution

### Overview

A new command **`mg:spec-create-milestone <version> <spec-path>`** — the milestone-level, spec-first sibling of `mg:spec-create-context` (`spec→phase :: spec→milestone`). It **projects** a frozen concept spec into GSD-native milestone artifacts (`PROJECT.md` milestone section, `REQUIREMENTS.md`, then `ROADMAP.md` via the unchanged roadmapper) instead of eliciting them. It **keeps** a research pass but **re-aims it from discovery to verification** (spec-seeded: "do these decisions still hold against the code, and what did the spec miss?"), and it adds a **faithfulness gate** — the manual v5.0 audit, made a built-in step. **Strict projection is the default**; anything beyond the spec must arrive as a research-surfaced, explicitly operator-approved addition. Output is GSD-native — no GSD patches.

### Interface

`mg:spec-create-milestone <version> <spec-path>` — e.g. `mg:spec-create-milestone v6.0 docs/work-queue/todo/point-in-time-l2/concept.md`.

- `<version>` — the milestone version (dot-format `vN.0`, per the project's versioning convention).
- `<spec-path>` — the frozen concept spec. Sibling `concept-NON-GOALS.md` and any local markdown links are auto-discovered and read (≤5, like `spec-create-context` step 7).
- **Precondition:** the spec is mature/frozen (post `spec-improve`); the project is brownfield (`PROJECT.md` + `MILESTONES.md` exist).

### Stage 1 — Project the spec → `REQUIREMENTS.md`

Emit a GSD-native `REQUIREMENTS.md`:
- **Requirements** grouped by category, `[CAT]-NN` checkboxes — from the spec's `D1..Dn` decisions when present, else from the Solution / Scope / Verification sections (the concept-spec-template's own structure; mirrors the PRD express path's "everything in the doc is a locked decision") — see D7.
- **Out of Scope** table ← `concept-NON-GOALS.md` + the spec's "What does NOT get built."
- **Future (v2) Requirements** ← the spec's deferred items / resolved-as-later Open Items.
- **Scope context (not requirements)** ← the spec's satisfied preconditions, as a non-checkbox note (so already-done work isn't re-scoped).
- **`## Spec Traceability`** — a net-new REQ↔`Dx` table (source→requirement), kept **separate** from the roadmapper-owned `## Traceability` (REQ→Phase) so the roadmapper's rewrite can't clobber it (see D5).

### Stage 2 — Context-aware verification (spec-seeded research)

Spawn **`gsd-project-researcher`** (reuse the agent + its tools) with a **spec-seeded prompt** in its Feasibility mode — *not* the discovery dimensions. Inputs in `<files_to_read>`: the concept spec (`D1..Dn` + NON-GOALS), the just-projected requirements, and the codebase (source dirs + `.planning/codebase/` map). Task: verify each decision still holds against current code; surface gaps, stale assumptions, and missing constraints (the class of finding that caught the `GRANT`). Output: a list of **flagged candidate additions/corrections** — never silently merged.

### Stage 3 — Faithfulness gate (one approval)

Present, for a single approval:
- **Completeness:** every spec `Dx` → ≥1 requirement (no dropped decisions).
- **No drift:** every requirement → a `Dx`, **or** an explicitly **flagged addition** (from Stage 2) the operator accepts/rejects item-by-item.
- Stage-2 findings are the **only** source of beyond-spec scope (D3).

The operator approves, edits, or rejects. This is the gate v5.0 lacked.

### Stage 4 — Roadmap (reuse `gsd-roadmapper`, unchanged)

Spawn `gsd-roadmapper` exactly as `new-milestone` does — `REQUIREMENTS.md` + `PROJECT.md`; phase numbering continues from the last milestone; 100% coverage enforced. It writes `ROADMAP.md` + `STATE.md` and rewrites the `## Traceability` (REQ→Phase) table. **Re-run the faithfulness cross-check after it returns** (the roadmapper edits REQUIREMENTS.md): read back each phase's `**Requirements**:` line and confirm every projected REQ landed in exactly one phase, and the `## Spec Traceability` section is intact.

### Stage 5 — `PROJECT.md` / `STATE.md` + commit

Update `PROJECT.md`'s milestone section + `STATE.md` and commit the artifacts (honoring config `commit_docs`), mirroring `new-milestone` steps 4–6 / 10.

### Template-drift guard

Ship two snapshots — `requirements-template.snapshot` + `roadmap-template.snapshot` under `.claude/spec/references/` — and a **Step-1 compatibility check** diffing each against the live `.claude/get-shit-done/templates/{requirements,roadmap}.md` (mirrors `spec-create-context`'s context-template check: identical → proceed; drift → `AskUserQuestion` Continue-anyway / Abort, snapshot never auto-updated). Because the roadmapper owns `ROADMAP.md`, the roadmap snapshot mainly guards the `### Phase N:` / `**Requirements**:` contract the faithfulness re-check parses.

## Design Decisions

### D1: Project, don't elicit (bottom-up, spec-first)
**Choice:** Derive `REQUIREMENTS.md` as a faithful projection of the frozen spec, not through per-category elicitation.
**Why:** For a "fix observed issues" milestone the scope is already settled in the spec; elicitation re-opens frozen decisions and produces a re-derivation that can silently drift (v5.0 SHORT leak). Projection with a traceability mapping makes drift checkable.
**Alternatives rejected:** `new-milestone`'s elicitation flow (re-litigates the spec); a bare doc→REQUIREMENTS dump with no traceability (no faithfulness signal).

### D2: Keep research — re-aimed from discovery to spec-verification
**Choice:** Retain a research pass, but seed it with the spec + projected requirements + code, tasked to *verify decisions against the code and flag gaps* (Feasibility mode), reusing `gsd-project-researcher` unchanged as the agent with a custom prompt.
**Why:** Blind domain discovery is redundant against a code-grounded spec, but context-aware verification demonstrably catches real gaps the spec missed (the view `GRANT`). Reusing the existing agent avoids a new maintenance surface; its "Verify before asserting" posture already fits.
**Alternatives rejected:** Drop research entirely (loses the gap-catching that earned its keep); author a purpose-built verification agent (another agent to maintain in mg-cc-tools — deferred unless the custom prompt proves insufficient).

### D3: Strict projection; beyond-spec scope only via research-surfaced, gate-approved additions
**Choice:** The command projects only what's in the spec. Scope not in the spec appears **only** if Stage-2 research flagged it *and* the operator accepted it at the faithfulness gate.
**Why:** This is the direct fix for the v5.0 SHORT leak — no path exists for un-vetted scope to enter silently, while genuine gaps (the `GRANT`) still land, with an audit trail.
**Alternatives rejected:** A `--also <note>` freeform input (re-opens the elicitation drift door); silent merge of research findings (removes the operator gate).

### D4: Reuse `gsd-roadmapper` unchanged; run the faithfulness gate around it
**Choice:** Spawn the existing roadmapper for phase derivation; run the completeness/no-drift check before it and re-verify after it.
**Why:** Phase quality then equals `new-milestone`'s, and the roadmapper's 100%-coverage/one-phase-per-REQ enforcement is synergistic with the gate. It rewrites the `## Traceability` table, so the gate must re-verify afterward and the Dx↔REQ mapping must live elsewhere (D5).
**Alternatives rejected:** A bespoke phase deriver (duplicates a maintained agent, diverges in quality).

### D5: Dx↔REQ mapping in a separate `## Spec Traceability` section
**Choice:** Store the source→requirement mapping in its own REQUIREMENTS.md section, distinct from the roadmapper-owned `## Traceability` (REQ→Phase).
**Why:** REQUIREMENTS.md has no native source column, and the roadmapper rewrites `## Traceability` in place — a separate section survives that rewrite and is what the faithfulness gate reads.
**Alternatives rejected:** Overload the `## Traceability` table (clobbered by the roadmapper); a sidecar file (splits the artifact; harder to keep in sync).

### D6: GSD-native output, no GSD patches; installed via mg-cc-tools
**Choice:** Produce only files GSD already understands (`REQUIREMENTS.md`, then roadmapper-written `ROADMAP.md`/`STATE.md`, `PROJECT.md`), shipped as an mg-cc-tools command with two template snapshots + a Step-1 drift check.
**Why:** Matches `spec-create-context`'s proven "no GSD patches" property; the drift guard keeps the projection honest as GSD's templates evolve.
**Alternatives rejected:** Forking `new-milestone` in GSD itself (patch-maintenance burden; couples to GSD's release cadence).

### D7: Projection reads D-blocks when present, falls back to Solution/Scope/Verification otherwise
**Choice:** When the spec has `D1..Dn`, project from them; when it doesn't, extract requirements from the Solution / Scope / Verification sections.
**Why:** Not every spec is decision-structured; the concept-spec-template guarantees those sections exist, and the PRD express path already treats an unstructured doc's content as locked decisions the same way.
**Alternatives rejected:** Require D-blocks (rejects otherwise-usable specs).

## Scope

### What gets built
- The command **`commands/mg/spec-create-milestone.md`** in mg-cc-tools (source repo `/home/mcbrain/mg_projects/mg-cc-tools`; installed to `.claude/commands/mg/` via `spec/install.sh --project <proj>`, checksummed into `.claude/mg-cc-tools.manifest.json`).
- **Two template snapshots** (`requirements-template.snapshot`, `roadmap-template.snapshot`) under `.claude/spec/references/` + the Step-1 drift check.
- **The projection logic** (spec → `REQUIREMENTS.md` incl. `## Spec Traceability`; NON-GOALS → Out of Scope; deferred → Future; preconditions → scope-context note).
- **The spec-seeded researcher prompt** (Feasibility mode; net-new prompt + output contract, reusing the `gsd-project-researcher` spawn/tools).
- **The faithfulness gate** (pre- and post-roadmapper completeness + no-drift checks).
- **The roadmapper spawn** + **PROJECT.md/STATE.md updates + commits** (reuse `new-milestone`'s patterns).

### What does NOT get built
- **No GSD patches** — GSD-native files only (D6).
- **No replacement of `gsd:new-milestone`** — it stays the path for greenfield / no-spec milestones.
- **No spec authoring** — that's `mg:spec-draft` → `mg:spec-improve`, upstream.
- **No new researcher agent** — reuse `gsd-project-researcher` (D2).
- **No blind domain research / per-category elicitation** — the two behaviors being removed.
- **No auto-seeding of phase `CONTEXT.md`s this version** — the command stops at `ROADMAP.md` (the open sub-question is in Open Items).

## Open Items

- **Auto-seed phase CONTEXTs (deferred stretch).** A follow-on could, after Stage 4, auto-run `mg:spec-create-context` per derived phase, seeding each `CONTEXT.md` from its spec slice — feasible now (the roadmapper emits `### Phase N` + `**Requirements**:`; `spec-create-context` takes `<phase> <doc>`). Deferred to keep v1 focused. **Unresolved sub-decision:** does each phase get the *whole* spec, or only the `Dx`-slice mapped (via `## Spec Traceability`) to that phase's REQs? (The slice is cleaner but needs the Dx→REQ→phase join to be reliable.)

## Verification

- **Faithful projection.** Given a spec with `D1..Dn`, the generated `REQUIREMENTS.md` has, for every `Dx`, ≥1 REQ in `## Spec Traceability`, and every REQ maps to a `Dx` or a gate-approved flagged addition. *Acceptance case:* feed the v5.0 L2 `concept.md` → expect the SCHM/QTR/ANN/VIEW/ORCH/CONS families with **no SHORT track** unless research flags it and the operator accepts it.
- **Beyond-spec is never silent.** A scope item absent from the spec lands **only** if Stage 2 flagged it and the operator accepted it. *Drive it two ways:* the `GRANT` case (research flags → operator accepts → lands as CONS's grant clause) and a spurious item (research doesn't flag → never appears).
- **Roadmapper coverage.** After Stage 4, `## Traceability` maps 100% of REQs to exactly one phase (0 unmapped), and the post-roadmapper re-check finds every REQ in some phase's `**Requirements**:` line.
- **Drop-in artifacts.** `gsd:plan-phase <N>` runs against the produced `ROADMAP.md` with no format errors (GSD-native, no patches).
- **Drift guard.** Against an unmodified GSD requirements/roadmap template, Step-1 reports "compatible"; against a mutated template section, it surfaces "Template drift" with Continue/Abort.
- **No blind research.** The Stage-2 pass reads the spec + code and returns verify/gap findings, not ecosystem tables.
